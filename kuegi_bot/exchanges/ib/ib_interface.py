import math
from datetime import datetime, timezone
from typing import Dict, List, Optional

from kuegi_bot.utils.trading_classes import Account, AccountPosition, Bar, ExchangeInterface, Order, Symbol, TickerData

try:
    from ib_insync import CFD, Contract, Forex, Future, IB, LimitOrder, MarketOrder, Stock, StopLimitOrder, StopOrder
except Exception as imp_err:
    IB = None
    _IB_IMPORT_ERROR = imp_err
else:
    _IB_IMPORT_ERROR = None


class IBInterface(ExchangeInterface):
    _ACTIVE_STATUSES = {"ApiPending", "PendingSubmit", "PendingCancel", "PreSubmitted", "Submitted"}
    _DONE_STATUSES = {"Filled", "Cancelled", "Inactive", "ApiCancelled"}

    def __init__(self, settings, logger, on_tick_callback=None, on_execution_callback=None):
        if IB is None:
            raise RuntimeError(
                "Interactive Brokers adapter requires 'ib-insync'. "
                "Install with: pip install ib-insync"
            ) from _IB_IMPORT_ERROR

        super().__init__(settings, logger, on_tick_callback, on_execution_callback)
        self.handles_executions = True
        self.symbol = settings.SYMBOL
        self.baseCoin = getattr(settings, "BASE", "USD")

        self.host = getattr(settings, "IB_HOST", "127.0.0.1")
        self.port = int(getattr(settings, "IB_PORT", 7497 if getattr(settings, "IS_TEST", False) else 7496))
        self.client_id = int(getattr(settings, "IB_CLIENT_ID", 77))
        self.account_code = getattr(settings, "IB_ACCOUNT", None)
        self._connect_timeout = float(getattr(settings, "IB_CONNECT_TIMEOUT_SEC", 12))
        self._use_rth = bool(getattr(settings, "IB_USE_RTH", False))
        self._what_to_show = getattr(settings, "IB_WHAT_TO_SHOW", "TRADES")
        self._outside_rth = bool(getattr(settings, "IB_OUTSIDE_RTH", False))
        self._tif = getattr(settings, "IB_TIF", "GTC")

        self.ib = IB()
        self._orders: Dict[str, Order] = {}
        self._trades_by_exchange_id = {}
        self._last_price = 0.0
        self._position = AccountPosition(self.symbol, 0.0, 0.0, 0.0)

        self._connect()
        self.contract = self._qualify_contract()
        self.symbol_info = self.get_instrument()
        self._subscribe_market_data()
        self._refresh_orders()
        self._refresh_position()

    def _connect(self):
        connected = self.ib.connect(
            host=self.host,
            port=self.port,
            clientId=self.client_id,
            timeout=self._connect_timeout,
            readonly=bool(getattr(self.settings, "IB_READ_ONLY", False)),
        )
        if not connected:
            raise RuntimeError(f"Could not connect to TWS/Gateway at {self.host}:{self.port}.")

        self.ib.errorEvent += self._on_ib_error
        self.ib.execDetailsEvent += self._on_exec_details
        self.logger.info(
            f"Connected to Interactive Brokers at {self.host}:{self.port} "
            f"(clientId={self.client_id}, account={self.account_code or 'default'})."
        )

    def _build_contract(self):
        sec_type = str(getattr(self.settings, "IB_SEC_TYPE", "FUT")).upper()
        symbol = getattr(self.settings, "IB_SYMBOL", self.symbol)
        currency = getattr(self.settings, "IB_CURRENCY", self.baseCoin)
        exchange = getattr(self.settings, "IB_EXCHANGE", "GLOBEX")
        con_id = getattr(self.settings, "IB_CON_ID", None)

        if con_id:
            return Contract(
                conId=int(con_id),
                secType=sec_type,
                exchange=str(exchange),
                currency=str(currency),
                symbol=str(symbol),
            )

        if sec_type == "FUT":
            local_symbol = getattr(self.settings, "IB_LOCAL_SYMBOL", None)
            expiry = getattr(self.settings, "IB_LAST_TRADE_DATE_OR_CONTRACT_MONTH", None)
            if local_symbol:
                contract = Future(localSymbol=str(local_symbol), exchange=exchange, currency=currency)
            else:
                if not expiry:
                    raise ValueError(
                        "IB futures require either IB_LOCAL_SYMBOL or "
                        "IB_LAST_TRADE_DATE_OR_CONTRACT_MONTH (YYYYMM / YYYYMMDD)."
                    )
                contract = Future(
                    symbol=str(symbol),
                    lastTradeDateOrContractMonth=str(expiry),
                    exchange=exchange,
                    currency=currency,
                )
            multiplier = getattr(self.settings, "IB_MULTIPLIER", None)
            if multiplier:
                contract.multiplier = str(multiplier)
            return contract

        if sec_type == "STK":
            primary_ex = getattr(self.settings, "IB_PRIMARY_EXCHANGE", "SMART")
            return Stock(str(symbol), primary_ex, str(currency))

        if sec_type == "FX":
            return Forex(str(symbol))

        if sec_type == "CFD":
            return CFD(str(symbol), exchange=str(exchange), currency=str(currency))

        raise ValueError(f"Unsupported IB_SEC_TYPE '{sec_type}'. Use FUT/STK/FX/CFD.")

    def _qualify_contract(self):
        contract = self._build_contract()
        qualified = self.ib.qualifyContracts(contract)
        if not qualified:
            raise RuntimeError(f"Could not qualify IB contract for symbol {self.symbol}.")
        return qualified[0]

    @staticmethod
    def _to_unix(value) -> int:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return int(value.timestamp())
        return int(datetime.now(timezone.utc).timestamp())

    @staticmethod
    def _price_precision(tick_size: float) -> int:
        if tick_size <= 0:
            return 2
        text = f"{tick_size:.10f}".rstrip("0")
        if "." not in text:
            return 0
        return len(text.split(".")[1])

    @staticmethod
    def _safe_float(value) -> Optional[float]:
        try:
            parsed = float(value)
        except Exception:
            return None
        if not math.isfinite(parsed):
            return None
        return parsed

    @staticmethod
    def _ib_bar_size(timeframe_minutes: int) -> str:
        if timeframe_minutes <= 0:
            return "1 min"
        if timeframe_minutes < 60:
            return f"{timeframe_minutes} mins" if timeframe_minutes > 1 else "1 min"
        hours = timeframe_minutes / 60.0
        if abs(hours - round(hours)) < 1e-9:
            hours = int(round(hours))
            return "1 hour" if hours == 1 else f"{hours} hours"
        return f"{timeframe_minutes} mins"

    @staticmethod
    def _duration_from_need(timeframe_minutes: int, min_bars_needed: int) -> str:
        total_minutes = max(300, timeframe_minutes * max(min_bars_needed, 80))
        total_days = int(math.ceil(total_minutes / 1440.0)) + 2
        if total_days <= 365:
            return f"{total_days} D"
        years = int(math.ceil(total_days / 365.0))
        return f"{years} Y"

    def _bar_from_ib(self, ib_bar) -> Bar:
        ts = self._to_unix(ib_bar.date)
        sub = Bar(
            tstamp=ts,
            open=float(ib_bar.open),
            high=float(ib_bar.high),
            low=float(ib_bar.low),
            close=float(ib_bar.close),
            volume=float(ib_bar.volume),
        )
        bar = Bar(
            tstamp=ts,
            open=float(ib_bar.open),
            high=float(ib_bar.high),
            low=float(ib_bar.low),
            close=float(ib_bar.close),
            volume=float(ib_bar.volume),
            subbars=[sub],
        )
        bar.last_tick_tstamp = ts
        return bar

    def _request_historical(self, timeframe_minutes: int, min_bars_needed: int, duration_override: str = None):
        return self.ib.reqHistoricalData(
            self.contract,
            endDateTime="",
            durationStr=duration_override or self._duration_from_need(timeframe_minutes, min_bars_needed),
            barSizeSetting=self._ib_bar_size(timeframe_minutes),
            whatToShow=self._what_to_show,
            useRTH=self._use_rth,
            formatDate=2,
            keepUpToDate=False,
        )

    def _trade_exchange_id(self, trade) -> str:
        order_id = getattr(trade.order, "orderId", None)
        if order_id is not None:
            return str(order_id)
        return str(getattr(trade.order, "permId", ""))

    def _sync_order_from_trade(self, trade):
        exchange_id = self._trade_exchange_id(trade)
        if exchange_id == "":
            return

        ib_order = trade.order
        status_obj = trade.orderStatus
        existing = self._orders.get(exchange_id)
        side_mult = 1 if str(ib_order.action).upper() == "BUY" else -1
        order_type = str(ib_order.orderType).upper()

        trigger = None
        if order_type in {"STP", "STP LMT"} and self._safe_float(getattr(ib_order, "auxPrice", None)) is not None:
            trigger = float(ib_order.auxPrice)
        limit = None
        if order_type in {"LMT", "STP LMT"} and self._safe_float(getattr(ib_order, "lmtPrice", None)) is not None:
            limit = float(ib_order.lmtPrice)

        order_id = ib_order.orderRef if ib_order.orderRef else (existing.id if existing else f"ib_{exchange_id}")
        amount = side_mult * float(ib_order.totalQuantity or 0.0)
        order = existing if existing is not None else Order(orderId=order_id, trigger=trigger, limit=limit, amount=amount)

        order.id = order_id
        order.amount = amount
        order.trigger_price = trigger
        order.limit_price = limit
        order.exchange_id = exchange_id

        filled = float(status_obj.filled or 0.0)
        order.executed_amount = side_mult * filled
        avg_fill = self._safe_float(status_obj.avgFillPrice)
        if avg_fill is not None and avg_fill > 0:
            order.executed_price = avg_fill

        status = str(status_obj.status or "")
        if status in self._ACTIVE_STATUSES:
            order.active = True
        elif status in self._DONE_STATUSES:
            order.active = False
        else:
            order.active = filled < float(ib_order.totalQuantity or 0.0)

        now_ts = int(datetime.now(timezone.utc).timestamp())
        if order.tstamp == 0:
            order.tstamp = now_ts
        if not order.active and order.executed_amount != 0 and order.execution_tstamp == 0:
            order.execution_tstamp = now_ts

        self._orders[exchange_id] = order
        self._trades_by_exchange_id[exchange_id] = trade

    def _refresh_orders(self):
        if not self.ib.isConnected():
            return

        for trade in self.ib.trades():
            if getattr(trade.contract, "conId", None) != getattr(self.contract, "conId", None):
                continue
            self._sync_order_from_trade(trade)

        now_ts = int(datetime.now(timezone.utc).timestamp())
        stale = []
        for exchange_id, order in self._orders.items():
            if order.active:
                continue
            reference_ts = order.execution_tstamp or order.tstamp
            if reference_ts and now_ts - reference_ts > 24 * 3600:
                stale.append(exchange_id)
        for exchange_id in stale:
            self._orders.pop(exchange_id, None)
            self._trades_by_exchange_id.pop(exchange_id, None)

    def _get_account_equity(self) -> float:
        values = self.ib.accountSummary()
        best = None
        for row in values:
            if self.account_code and row.account != self.account_code:
                continue
            if row.tag != "NetLiquidation":
                continue
            if row.currency == self.baseCoin:
                return float(row.value)
            if row.currency == "USD" and best is None:
                best = float(row.value)
        return best if best is not None else 0.0

    def _refresh_position(self):
        quantity = 0.0
        avg_entry = 0.0
        for pos in self.ib.positions():
            if self.account_code and pos.account != self.account_code:
                continue
            if getattr(pos.contract, "conId", None) != getattr(self.contract, "conId", None):
                continue
            quantity = float(pos.position)
            avg_entry = float(pos.avgCost)
            break

        self._position = AccountPosition(
            symbol=self.symbol,
            quantity=quantity,
            avgEntryPrice=avg_entry if quantity != 0 else 0.0,
            walletBalance=self._get_account_equity(),
        )

    def _subscribe_market_data(self):
        try:
            self.ib.reqMktData(self.contract, "", False, False)
        except Exception as e:
            self.logger.warning(f"IB market data subscription failed (continuing with historical polling): {e}")

    def _order_to_ib_order(self, order: Order):
        action = "BUY" if order.amount > 0 else "SELL"
        qty = abs(float(order.amount))

        if order.trigger_price is not None and order.limit_price is not None:
            ib_order = StopLimitOrder(
                action=action,
                totalQuantity=qty,
                lmtPrice=float(order.limit_price),
                stopPrice=float(order.trigger_price),
                tif=self._tif,
                outsideRth=self._outside_rth,
            )
        elif order.trigger_price is not None:
            ib_order = StopOrder(
                action=action,
                totalQuantity=qty,
                stopPrice=float(order.trigger_price),
                tif=self._tif,
                outsideRth=self._outside_rth,
            )
        elif order.limit_price is not None:
            ib_order = LimitOrder(
                action=action,
                totalQuantity=qty,
                lmtPrice=float(order.limit_price),
                tif=self._tif,
                outsideRth=self._outside_rth,
            )
        else:
            ib_order = MarketOrder(
                action=action,
                totalQuantity=qty,
                tif=self._tif,
                outsideRth=self._outside_rth,
            )

        ib_order.orderRef = order.id
        if self.account_code:
            ib_order.account = self.account_code
        return ib_order

    def _on_ib_error(self, req_id, error_code, error_string, contract):
        if error_code in {2104, 2106, 2158}:
            return
        self.logger.warning(f"IB error reqId={req_id} code={error_code}: {error_string}")

    def _on_exec_details(self, trade, fill):
        self._sync_order_from_trade(trade)
        self._refresh_position()

        if self.on_execution_callback is None:
            return

        exchange_id = self._trade_exchange_id(trade)
        mapped = self._orders.get(exchange_id)
        order_id = mapped.id if mapped is not None else (trade.order.orderRef or f"ib_{exchange_id}")

        side = str(getattr(fill.execution, "side", "")).upper()
        side_mult = 1 if side in {"BOT", "BUY"} else -1
        qty = side_mult * float(getattr(fill.execution, "shares", 0.0))
        price = float(getattr(fill.execution, "price", 0.0))
        ts = self._to_unix(getattr(fill.execution, "time", datetime.now(timezone.utc)))

        self.on_execution_callback(order_id=order_id, executed_price=price, amount=qty, tstamp=ts)
        if self.on_tick_callback is not None:
            self.on_tick_callback(fromAccountAction=True)

    def exit(self):
        if self.ib.isConnected():
            self.ib.disconnect()

    def internal_cancel_order(self, order: Order):
        if order.exchange_id and order.exchange_id in self._trades_by_exchange_id:
            trade = self._trades_by_exchange_id[order.exchange_id]
            self.ib.cancelOrder(trade.order)
            self.ib.sleep(0.05)
            self._sync_order_from_trade(trade)
            return

        for trade in self.ib.openTrades():
            if trade.order.orderRef == order.id:
                self.ib.cancelOrder(trade.order)
                self.ib.sleep(0.05)
                self._sync_order_from_trade(trade)
                return

    def internal_send_order(self, order: Order):
        ib_order = self._order_to_ib_order(order)
        trade = self.ib.placeOrder(self.contract, ib_order)
        self.ib.sleep(0.1)
        self._sync_order_from_trade(trade)
        order.exchange_id = self._trade_exchange_id(trade)

    def internal_update_order(self, order: Order):
        if not order.exchange_id or order.exchange_id not in self._trades_by_exchange_id:
            self.internal_send_order(order)
            return

        trade = self._trades_by_exchange_id[order.exchange_id]
        replacement = self._order_to_ib_order(order)

        trade.order.orderType = replacement.orderType
        trade.order.action = replacement.action
        trade.order.totalQuantity = replacement.totalQuantity
        trade.order.tif = replacement.tif
        trade.order.outsideRth = replacement.outsideRth
        trade.order.orderRef = replacement.orderRef
        if hasattr(replacement, "lmtPrice"):
            trade.order.lmtPrice = replacement.lmtPrice
        if hasattr(replacement, "auxPrice"):
            trade.order.auxPrice = replacement.auxPrice

        self.ib.placeOrder(self.contract, trade.order)
        self.ib.sleep(0.05)
        self._sync_order_from_trade(trade)

    def resyncOrders(self):
        self._refresh_orders()

    def get_orders(self) -> List[Order]:
        self._refresh_orders()
        return list(self._orders.values())

    def get_bars(self, timeframe_minutes, start_offset_minutes, min_bars_needed=600) -> List[Bar]:
        bars_raw = self._request_historical(timeframe_minutes, min_bars_needed=min_bars_needed)
        bars = [self._bar_from_ib(b) for b in bars_raw]
        bars.sort(key=lambda x: x.tstamp, reverse=True)

        if start_offset_minutes > 0 and timeframe_minutes > 0:
            offset_bars = int(start_offset_minutes / timeframe_minutes)
            if offset_bars > 0:
                bars = bars[offset_bars:]

        if not bars:
            raise RuntimeError(
                f"IB returned no historical bars for {self.symbol}. "
                f"Check market data permissions and contract settings."
            )

        if bars:
            self._last_price = bars[0].close
        return bars

    def recent_bars(self, timeframe_minutes, start_offset_minutes) -> List[Bar]:
        seconds = max(1800, int(timeframe_minutes * 60 * 8))
        bars_raw = self._request_historical(
            timeframe_minutes,
            min_bars_needed=30,
            duration_override=f"{seconds} S",
        )
        bars = [self._bar_from_ib(b) for b in bars_raw]
        bars.sort(key=lambda x: x.tstamp, reverse=True)

        if start_offset_minutes > 0 and timeframe_minutes > 0:
            offset_bars = int(start_offset_minutes / timeframe_minutes)
            if offset_bars > 0:
                bars = bars[offset_bars:]

        if bars:
            self._last_price = bars[0].close
        return bars

    def get_instrument(self, symbol=None):
        details = self.ib.reqContractDetails(self.contract)
        if not details:
            return Symbol(
                symbol=self.symbol,
                isInverse=False,
                lotSize=1,
                tickSize=0.25,
                makerFee=0,
                takerFee=0,
                baseCoin=self.baseCoin,
                pricePrecision=2,
                quantityPrecision=0,
            )

        detail = details[0]
        tick_size = float(detail.minTick or 0.25)
        price_precision = self._price_precision(tick_size)
        return Symbol(
            symbol=self.symbol,
            isInverse=False,
            lotSize=1,
            tickSize=tick_size,
            makerFee=0,
            takerFee=0,
            baseCoin=self.baseCoin,
            pricePrecision=price_precision,
            quantityPrecision=0,
        )

    def get_ticker(self, symbol=None):
        last = self._last_price
        bid = None
        ask = None
        try:
            tickers = self.ib.reqTickers(self.contract)
            if tickers:
                ticker = tickers[0]
                bid = self._safe_float(getattr(ticker, "bid", None))
                ask = self._safe_float(getattr(ticker, "ask", None))
                live_last = self._safe_float(getattr(ticker, "last", None))
                close_last = self._safe_float(getattr(ticker, "close", None))
                if live_last is not None:
                    last = live_last
                elif close_last is not None:
                    last = close_last
        except Exception:
            pass

        if last is None or last == 0:
            bars = self.recent_bars(timeframe_minutes=1, start_offset_minutes=0)
            if bars:
                last = bars[0].close

        last = float(last or 0.0)
        self._last_price = last
        if bid is None:
            bid = last
        if ask is None:
            ask = last
        return TickerData(bid=bid, ask=ask, last=last)

    def get_position(self, symbol=None):
        self._refresh_position()
        return self._position

    def is_open(self):
        return self.ib.isConnected()

    def check_market_open(self):
        return self.is_open()

    def update_account(self, account: Account):
        self._refresh_position()
        account.open_position = self._position
        account.equity = float(self._position.walletBalance or 0.0)
        account.usd_equity = account.equity if str(self.baseCoin).upper() == "USD" else account.equity * float(
            self._last_price or 0.0
        )
