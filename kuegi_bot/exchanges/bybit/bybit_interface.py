import logging
import math
from datetime import datetime
import time
import requests


from typing import List

import pybit
from pybit.unified_trading import HTTP
from pybit.exceptions import InvalidRequestError, FailedRequestError

from kuegi_bot.exchanges.bybit.bybit_websocket import BybitWebsocket
from kuegi_bot.utils.trading_classes import Order, Bar, TickerData, AccountPosition, \
    Symbol, process_low_tf_bars, parse_utc_timestamp
from ..ExchangeWithWS import ExchangeWithWS
from kuegi_bot.bots.trading_bot import TradingBot
from kuegi_bot.utils.trading_classes import OrderType


def strOrNone(input):
    if input is None:
        return None
    else:
        return str(input)


class ByBitInterface(ExchangeWithWS):

    def __init__(self, settings, logger, on_tick_callback=None, on_api_error=None, on_execution_callback=None):
        self.on_api_error = on_api_error
        self.pybit = HTTP(testnet = settings.IS_TEST, api_key=settings.API_KEY, api_secret=settings.API_SECRET)
        logging.basicConfig(filename="pybit.log", level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")
        #hosts = ["wss://stream-testnet.bybit.com/realtime"] if settings.IS_TEST \
        #    else ["wss://stream.bybit.com/realtime", "wss://stream.bytick.com/realtime"]
        self.longPos = AccountPosition(settings.SYMBOL, 0, 0, 0)
        self.shortPos = AccountPosition(settings.SYMBOL, 0, 0, 0)
        if settings.EXCHANGE == 'bybit-linear':
            self.category = 'linear'
        elif settings.EXCHANGE == 'bybit-spot':
            self.category = 'spot'
        else:
            self.category = 'inverse'
        if settings.IS_TEST:
            privateURL = "wss://stream-testnet.bybit.com/v5/private?max_alive_time=5m"
            publicURL = f"wss://stream-testnet.bybit.com/v5/public/{self.category}"
        else:
            privateURL = "wss://stream.bybit.com/v5/private?max_alive_time=5m"
            publicURL = f"wss://stream.bybit.com/v5/public/{self.category}"
        hosts = [privateURL, publicURL]
        super().__init__(settings, logger,
                         ws=BybitWebsocket(wsURLs=hosts,
                                           api_key=settings.API_KEY,
                                           api_secret=settings.API_SECRET,
                                           logger=logger,
                                           callback=self.socket_callback,
                                           symbol=settings.SYMBOL,
                                           minutesPerBar=settings.MINUTES_PER_BAR,
                                           category = self.category),
                         on_tick_callback=on_tick_callback,
                         on_execution_callback= on_execution_callback)
        self.handles_executions= True

    def is_open(self):
        # ws is always a BybitLinearWebsocket which has a publicWS
        return not self.ws.exited and not self.ws.public.exited

    def initOrders(self):
        activeOrders_result = self.handle_result(lambda: self.pybit.get_open_orders(category=self.category,symbol=self.symbol,orderFilter='Order'),context="get_open_orders(Order)")
        if activeOrders_result is not None:
            activeOrders = activeOrders_result.get("list", [])
        else:
            activeOrders = []

        conditionalOrders_result = self.handle_result(lambda: self.pybit.get_open_orders(category=self.category,symbol=self.symbol,orderFilter='StopOrder'),context="get_open_orders(StopOrder)")
        if conditionalOrders_result is not None:
            conditionalOrders = conditionalOrders_result.get("list", [])
        else:
            conditionalOrders = []

        tpslOrders_result = self.handle_result(lambda: self.pybit.get_open_orders(category=self.category,symbol=self.symbol,orderFilter='tpslOrder'),context="get_open_orders(tpslOrder)")
        if tpslOrders_result is not None:
            tpslOrders = tpslOrders_result.get("list", [])
        else:
            tpslOrders = []

        apiOrders = activeOrders + conditionalOrders + tpslOrders
        self.processOrders(apiOrders)

        for order in self.orders.values():
            self.logger.debug(str(order))

    def initPositions(self):
        # --- positions ---
        positions_result = self.handle_result(lambda: self.pybit.get_positions(category=self.category,symbol=self.symbol),context="get_positions")
        if positions_result is not None:
            api_positions = positions_result.get("list", [])
        else:
            self.logger.error("Could not load positions from Bybit (get_positions returned None).")
            api_positions = []

        # --- wallet / balance ---
        wallet_result = self.handle_result(lambda: self.pybit.get_wallet_balance(accountType="UNIFIED",coin=self.baseCoin),context="get_wallet_balance")

        balance = 0.0  # safe default

        if wallet_result is not None:
            wallet_list = wallet_result.get("list", [])
            if wallet_list:
                coins = wallet_list[0].get("coin", [])
                for coin in coins:
                    if coin.get("coin") == self.baseCoin:
                        try:
                            balance = float(coin.get("walletBalance", "0"))
                        except (TypeError, ValueError):
                            self.logger.warning(
                                f"Could not parse walletBalance for {self.baseCoin}: {coin.get('walletBalance')!r}"
                            )
                            balance = 0.0
                        break
            else:
                self.logger.warning("Wallet list empty when querying get_wallet_balance.")
        else:
            self.logger.error("Could not load wallet balance from Bybit (get_wallet_balance returned None).")

        # --- initialize AccountPosition objects ---
        self.longPos = AccountPosition(self.symbol, 0.0, 0.0, balance)
        self.shortPos = AccountPosition(self.symbol, 0.0, 0.0, balance)

        # --- apply existing positions from API ---
        for pos in api_positions:
            side = pos.get("side")
            size = float(pos.get("size", 0.0))
            avg_price = float(pos.get("avgPrice", 0.0))

            if side == "Sell":
                self.shortPos.avgEntryPrice = avg_price
                self.shortPos.quantity = -size
            elif side == "Buy":
                self.longPos.avgEntryPrice = avg_price
                self.longPos.quantity = size

        self.updatePosition_internally()

    def get_funding_history(self, start_ts_sec: int, end_ts_sec: int) -> dict[int, float]:
        """
        Fetch funding history from Bybit public REST and return {unix_seconds: fundingRate}.
        Uses /v5/market/funding/history and paginates backwards via endTime.

        start_ts_sec/end_ts_sec are unix seconds.
        """
        if start_ts_sec is None or end_ts_sec is None:
            return {}

        if start_ts_sec > end_ts_sec:
            start_ts_sec, end_ts_sec = end_ts_sec, start_ts_sec

        base_url = "https://api-testnet.bybit.com" if self.settings.IS_TEST else "https://api.bybit.com"
        url = f"{base_url}/v5/market/funding/history"

        start_ms = int(start_ts_sec * 1000)
        end_ms = int(end_ts_sec * 1000)

        out: dict[int, float] = {}
        page_end = end_ms

        # Bybit limit is 200 per request
        limit = 200

        while True:
            params = {
                "category": self.category,   # 'linear' or 'inverse'
                "symbol": self.symbol,
                "startTime": start_ms,
                "endTime": page_end,
                "limit": limit
            }

            r = requests.get(url, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()

            if data.get("retCode", 0) != 0:
                self.logger.warning(f"Funding fetch retCode != 0: {data}")
                break

            rows = (data.get("result") or {}).get("list") or []
            if not rows:
                break

            min_seen = None
            for row in rows:
                try:
                    ts_ms = int(row["fundingRateTimestamp"])
                    rate = float(row["fundingRate"])
                except Exception:
                    continue

                ts_sec = ts_ms // 1000
                if start_ts_sec <= ts_sec <= end_ts_sec:
                    out[ts_sec] = rate

                if min_seen is None or ts_ms < min_seen:
                    min_seen = ts_ms

            # If the earliest item in this page is already at/behind startTime, we are done
            if min_seen is None or min_seen <= start_ms:
                break

            # paginate backward
            page_end = min_seen - 1

            # be gentle
            time.sleep(0.05)

        return out

    def get_avg_price_for_position(self, pos) -> float | None:
        """
        Return the average entry price for the given Position from Bybit,
        or None if not found / not available.
        """
        positions_result = self.handle_result(lambda: self.pybit.get_positions(category=self.category,symbol=self.symbol),context="get_positions")
        if positions_result is None:
            return None

        api_positions = positions_result.get("list", [])
        if not api_positions:
            return None

        for p in api_positions:
            side = p.get("side")
            size_str = p.get("size", "0")
            try:
                size = float(size_str)
            except (TypeError, ValueError):
                continue

            if size == 0:
                continue

            # Match long vs short by side and sign of pos.amount
            if pos.amount > 0 and side == "Buy":
                return float(p.get("avgPrice", 0.0))
            if pos.amount < 0 and side == "Sell":
                return float(p.get("avgPrice", 0.0))

        return None

    def updatePosition_internally(self):
        if self.longPos.quantity > -self.shortPos.quantity:
            entry = self.longPos.avgEntryPrice
        else:
            entry = self.shortPos.avgEntryPrice

        if self.symbol in self.positions.keys() and \
                self.positions[self.symbol].quantity != self.longPos.quantity + self.shortPos.quantity:
            self.logger.info("position changed %.5f -> %.5f" % (
                self.positions[self.symbol].quantity, self.longPos.quantity + self.shortPos.quantity))

        self.positions[self.symbol] = AccountPosition(self.symbol,
                                                      quantity=self.longPos.quantity + self.shortPos.quantity,
                                                      avgEntryPrice=entry,
                                                      walletBalance=self.longPos.walletBalance)

    def internal_cancel_order(self, order: Order):
        if order.exchange_id in self.orders.keys():
            self.orders[order.exchange_id].active = False
        result = self.handle_result(lambda:self.pybit.cancel_order(category=self.category,orderId=order.exchange_id, symbol=self.symbol))
        self.logger.info("cancel order result: %s" % (str(result)))

    def internal_send_order(self, order: Order):
        self.logger.info("Received order placement request: %s" % (str(order)))

        orderType = TradingBot.order_type_from_order_id(order.id)
        triggerDirection = None

        if order.trigger_price is not None:
            # conditional
            # types: entry / stop-limit, SL, TP, etc.
            # execution type: Market and Limit
            if self.last < order.trigger_price:
                triggerDirection = 1 # triggered when market price rises to triggerPrice
            else:
                triggerDirection = 2 # triggered when market price falls to triggerPrice

            self.logger.info("Trigger direction: %s" % (str(triggerDirection)))

            if orderType != OrderType.SL:
                if (self.last - order.trigger_price) * order.amount >= 0:
                    # condition is already true for ENTRY/TP
                    self.logger.warning(
                        f"Removed trigger price because condition considered true. "
                        f"last={self.last}, trigger={order.trigger_price}, amount={order.amount}, orderId={order.id}"
                    )
                    order.trigger_price = None
        else:
            self.logger.info("No trigger direction and no trigger_price.")

        if order.limit_price is not None:
            # limit order
            # types: entry / stop-limit, (TP)
            # execution type: Limit
            order_type = "Limit"
        else:
            # execution type: Market
            order_type = "Market"

        if orderType == OrderType.ENTRY or orderType == OrderType.TP:
            if order.trigger_price is not None:
                # conditional order
                self.orders_by_link_id[order.id] = order
                result = self.handle_result(lambda:self.pybit.place_order(
                    side=("Buy" if order.amount > 0 else "Sell"),
                    category=self.category,
                    symbol=self.symbol,
                    orderType=order_type,
                    qty=strOrNone(self.symbol_info.normalizeSize(abs(order.amount))),
                    price=strOrNone(order.limit_price),
                    triggerDirection = int(triggerDirection),
                    triggerPrice=strOrNone(order.trigger_price),
                    orderLinkId=order.id,
                    timeInForce="GTC",
                    positionIdx = int(0)))
                if result is not None:
                    order.exchange_id = result['orderId']
                    self.orders[order.exchange_id] = order
            else:
                self.orders_by_link_id[order.id] = order
                result =  self.handle_result(lambda:self.pybit.place_order(
                    side=("Buy" if order.amount > 0 else "Sell"),
                    symbol=self.symbol,
                    category = self.category,
                    orderType=order_type,
                    qty=strOrNone(self.symbol_info.normalizeSize(abs(order.amount))),
                    price=strOrNone(order.limit_price),
                    orderLinkId=order.id,
                    timeInForce="GTC",
                    positionIdx = int(0)))
                if result is not None:
                    order.exchange_id = result['orderId']
                    self.orders[order.exchange_id] = order
        elif orderType == OrderType.SL:
            if order.trigger_price is not None:
                # conditional order
                self.orders_by_link_id[order.id] = order
                result = self.handle_result(lambda: self.pybit.place_order(
                    side=("Buy" if order.amount > 0 else "Sell"),
                    category=self.category,
                    symbol=self.symbol,
                    orderType=order_type,
                    slOrderType = "Market",
                    qty=strOrNone(self.symbol_info.normalizeSize(abs(order.amount))),
                    triggerDirection=int(triggerDirection),
                    triggerPrice=strOrNone(order.trigger_price),
                    tpslMode = "Full",
                    orderLinkId=order.id,
                    timeInForce="GTC",
                    positionIdx = int(0)))
                if result is not None:
                    order.exchange_id = result['orderId']
                    self.orders[order.exchange_id] = order
                    self.logger.info("Response to SL order: %s" % (str(result)))
        else:
            self.logger.info("Order type is not ENTRY, TP, SL: %s" % (str(orderType)))
            self.orders_by_link_id[order.id] = order
            result = self.handle_result(lambda: self.pybit.place_order(
                side=("Buy" if order.amount > 0 else "Sell"),
                symbol=self.symbol,
                category=self.category,
                orderType="Market",
                qty=strOrNone(self.symbol_info.normalizeSize(abs(order.amount))),
                orderLinkId=order.id,
                timeInForce="GTC",
                positionIdx=int(0)))
            if result is not None:
                order.exchange_id = result['orderId']
                self.orders[order.exchange_id] = order

    def internal_update_order(self, order: Order):
        orderType = TradingBot.order_type_from_order_id(order.id)
        if order.trigger_price is not None:
            if self.last < order.trigger_price:
                triggerDirection = 1
            else:
                triggerDirection = 2
        if orderType == OrderType.ENTRY or orderType == OrderType.TP:
            if order.trigger_price is not None:
                self.handle_result(lambda:self.pybit.amend_order(
                    orderId=order.exchange_id,
                    category = self.category,
                    symbol=self.symbol,
                    qty=strOrNone(self.symbol_info.normalizeSize(abs(order.amount))),
                    triggerPrice=strOrNone(self.symbol_info.normalizePrice(order.trigger_price, order.amount > 0)),
                    price=strOrNone(self.symbol_info.normalizePrice(order.limit_price, order.amount < 0))))
            else:
                self.handle_result(lambda:self.pybit.amend_order(
                    orderId=order.exchange_id,
                    category = self.category,
                    symbol=self.symbol,
                    qty=strOrNone(self.symbol_info.normalizeSize(abs(order.amount))),
                    price=strOrNone(self.symbol_info.normalizePrice(order.limit_price,order.amount < 0))))
        elif orderType == OrderType.SL:
            if order.trigger_price is not None:
                # conditional order
                result = self.handle_result(lambda: self.pybit.amend_order(
                    orderId=order.exchange_id,
                    side=("Buy" if order.amount > 0 else "Sell"),
                    category=self.category,
                    symbol=self.symbol,
                    orderType="Market",
                    slOrderType = "Market",
                    qty=strOrNone(self.symbol_info.normalizeSize(abs(order.amount))),
                    triggerDirection=int(triggerDirection),
                    triggerPrice=strOrNone(order.trigger_price),
                    tpslMode = "Full",
                    orderLinkId=order.id,
                    timeInForce="GTC"))
                if result is not None:
                    order.exchange_id = result['orderId']
                    #self.orders[order.exchange_id] = order
        else:
            print("Case not covered")
            self.logger.info("Case not covered")

    def get_current_liquidity(self) -> tuple:
        book_result = self.handle_result(lambda: self.pybit.get_orderbook(category=self.category,symbol=self.symbol,limit=50),context="get_orderbook(liquidity)")

        if book_result is None:
            self.logger.error("Could not load orderbook for liquidity calculation.")
            return 0.0, 0.0

        # V5-like structure: b = bids, a = asks, each entry is [price, size, ...]
        bids = book_result.get("b") or []
        asks = book_result.get("a") or []

        buy = 0.0
        sell = 0.0

        for level in bids:
            try:
                size = float(level[1])
            except (IndexError, TypeError, ValueError):
                continue
            buy += size

        for level in asks:
            try:
                size = float(level[1])
            except (IndexError, TypeError, ValueError):
                continue
            sell += size

        return buy, sell

    def get_bars(self, timeframe_minutes, start_offset_minutes, min_bars_needed=600) -> List[Bar]:
        limit = 200  # entries per message
        tf = 1 if timeframe_minutes <= 60 else 60  # minutes per candle requested from exchange
        time_now = int(datetime.now().timestamp() * 1000)
        start = int(time_now - (limit - 1) * tf * 60 * 1000)  # request 200 * tf

        apibars_result = self.handle_result(lambda: self.pybit.get_kline(category=self.category,symbol=self.symbol,interval=str(tf),start=start,limit=limit),context="get_kline(initial)")

        if apibars_result is None:
            self.logger.error("Could not load initial kline data from Bybit.")
            return []

        apibars = apibars_result.get("list", [])
        if not apibars:
            self.logger.warning("Initial kline list from Bybit is empty.")
            return []

        # get more history to fill enough
        mult = timeframe_minutes / tf  # multiplier
        min_needed_tf_candles = min_bars_needed * mult  # number of required tf-sized candles
        number_of_requests = 1 + math.ceil(min_needed_tf_candles / limit)  # number of requests

        for idx in range(number_of_requests):
            if not apibars:
                break  # nothing to extend from

            start = int(apibars[-1][0]) - limit * tf * 60 * 1000

            bars1_result = self.handle_result(lambda: self.pybit.get_kline(category=self.category,symbol=self.symbol,interval=str(tf),start=start,limit=limit),context="get_kline(history)")

            if bars1_result is None:
                self.logger.warning("Stopping extra kline history load because get_kline returned None.")
                break

            bars1 = bars1_result.get("list", [])
            if not bars1:
                self.logger.info("No more historical kline data returned from Bybit.")
                break

            apibars = apibars + bars1

        return self._aggregate_bars(reversed(apibars), timeframe_minutes, start_offset_minutes)

    def _aggregate_bars(self, apibars, timeframe_minutes, start_offset_minutes) -> List[Bar]:
        subbars = []
        for b in apibars:
            if 'open' in b:
                if b['open'] is None:
                    continue

            subbars.append(self.barDictToBar(b))
        return process_low_tf_bars(subbars, timeframe_minutes, start_offset_minutes)

    def get_instrument(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        fees_result = self.handle_result(lambda:self.pybit.get_fee_rates(category = self.category, symbol =symbol),context="get_fee_rates")
        if fees_result is not None:
            fees_list = fees_result.get("list", [])
            if fees_list:
                makerFeeRate = float(fees_list[0].get("makerFeeRate", 0.0))
                takerFeeRate = float(fees_list[0].get("takerFeeRate", 0.0))
            else:
                self.logger.warning(f"get_fee_rates returned empty list for symbol {symbol}. Using 0 fees.")
                makerFeeRate = 0.0
                takerFeeRate = 0.0
        else:
            self.logger.error(f"get_fee_rates failed for symbol {symbol}. Using 0 fees.")
            makerFeeRate = 0.0
            takerFeeRate = 0.0
        instr_result = self.handle_result(lambda: self.pybit.get_instruments_info(category=self.category,symbol=symbol),context="get_instruments_info")

        if instr_result is None:
            self.logger.error(f"get_instruments_info failed for symbol {symbol}.")
            return None

        for entry in instr_result.get("list", []):
            if entry.get("symbol") == symbol:
                return Symbol(
                    symbol=entry['symbol'],
                    baseCoin=self.baseCoin,
                    isInverse=True if self.category == 'inverse' else False,
                    lotSize=float(entry['lotSizeFilter']['qtyStep']),
                    tickSize=float(entry['priceFilter']['tickSize']),
                    makerFee=makerFeeRate,
                    takerFee=takerFeeRate,
                    pricePrecision=int(entry['priceScale']),
                    quantityPrecision=5 if entry.get("quoteCoin") == "USDT" else 0  # FIXME: still hardcoded 5
                )

        self.logger.error(f"Instrument {symbol} not found in get_instruments_info response.")
        return None

    def get_ticker(self, symbol=None):
        if symbol is None:
            symbol = self.symbol

        symbolData_result = self.handle_result(lambda: self.pybit.get_orderbook(category=self.category,symbol=symbol,limit=1),context="get_orderbook(ticker)")

        tickerData_result = self.handle_result(lambda: self.pybit.get_tickers(category=self.category,symbol=symbol),context="get_tickers")

        if symbolData_result is None or tickerData_result is None:
            self.logger.error("get_ticker failed because orderbook or ticker data is None.")
            return None

        # V5 /v5/market/orderbook: result is a dict with 'b' and 'a' arrays
        try:
            bid = float(symbolData_result["b"][0][0])
            ask = float(symbolData_result["a"][0][0])
        except (KeyError, IndexError, TypeError, ValueError) as e:
            self.logger.error(f"Failed to parse bid/ask from orderbook: {e}, raw={symbolData_result!r}")
            return None

        # V5 /v5/market/tickers: result has 'list' with entries containing lastPrice
        try:
            lastPrice = float(tickerData_result["list"][0]["lastPrice"])
        except (KeyError, IndexError, TypeError, ValueError) as e:
            self.logger.error(f"Failed to parse lastPrice from ticker data: {e}, raw={tickerData_result!r}")
            return None

        return TickerData(bid=bid, ask=ask, last=lastPrice)

    # internal methods

    def processOrders(self, apiOrders):
        if apiOrders is not None:
            for o in apiOrders:
                order = self.orderDictToOrder(o)
                if order.active:
                    self.logger.info("order: %s" % (str(order)))
                    self.orders[order.exchange_id] = order

    def socket_callback(self, topic):
        try:
            gotTick = False
            msgs = self.ws.get_data(topic)
            while len(msgs) > 0:
                if topic == 'order' or topic == 'stopOrder':
                    # {'orderId': 'c9cc56cb-164c-4978-811e-2d2e4ef6153a', 'orderLinkId': '', 'blockTradeId': '',
                    # 'symbol': 'BTCUSD', 'price': '0.00', 'qty': '10', 'side': 'Buy', 'isLeverage': '', 'positionIdx': 0,
                    # 'orderStatus': 'Untriggered', 'cancelType': 'UNKNOWN', 'rejectReason': 'EC_NoError', 'avgPrice': '0',
                    # 'leavesQty': '10', 'leavesValue': '0', 'cumExecQty': '0', 'cumExecValue': '0', 'cumExecFee': '0',
                    # 'timeInForce': 'IOC', 'orderType': 'Market', 'stopOrderType': 'StopLoss', 'orderIv': '',
                    # 'triggerPrice': '38000.00', 'takeProfit': '0.00', 'stopLoss': '0.00', 'tpTriggerBy': 'UNKNOWN',
                    # 'slTriggerBy': 'UNKNOWN', 'triggerDirection': 1, 'triggerBy': 'LastPrice',
                    # 'lastPriceOnCreated': '36972.00', 'reduceOnly': True, 'closeOnTrigger': True, 'smpType': 'None',
                    # 'smpGroup': 0, 'smpOrderId': '', 'tpslMode': 'Full', 'tpLimitPrice': '', 'slLimitPrice': '',
                    # 'placeType': '', 'createdTime': '1701099868909', 'updatedTime': '1701099868909'}
                    #self.logger.info("order msg arrived")
                    for o in msgs:
                        if o['symbol'] != self.symbol:
                            continue  # ignore orders not of my symbol
                        order = self.orderDictToOrder(o)
                        prev: Order = self.orders[
                            order.exchange_id] if order.exchange_id in self.orders.keys() else None
                        if prev is not None:
                            if prev.tstamp > order.tstamp or abs(prev.executed_amount) > abs(order.executed_amount):
                                # already got newer information, probably the info of the stop order getting
                                # triggered, when i already got the info about execution
                                self.logger.info("ignoring delayed update for %s " % prev.id)
                                continue
                            # ws removes stop price when executed
                            if order.trigger_price is None:
                                order.trigger_price = prev.trigger_price
                                order.stop_triggered= True # there was a stop and its no longer there -> it was triggered and order turned to linear
                            if order.limit_price is None:
                                order.limit_price = prev.limit_price
                        else:
                            self.logger.info("Order unknown: %s" % (str(order)))
                        prev = order
                        if not prev.active and prev.execution_tstamp == 0:
                            prev.execution_tstamp = datetime.utcnow().timestamp()
                        self.orders[order.exchange_id] = prev
                        self.logger.info("order update: %s" % (str(order)))
                elif topic == 'execution':
                    for execution in msgs:
                        if execution['symbol'] != self.symbol:
                            self.logger.info("INFO: order execution in:" + str(execution['symbol']))
                            continue

                        order = None

                        # 1) First try exchange orderId (normal case)
                        if execution['orderId'] in self.orders:
                            order = self.orders[execution['orderId']]
                        else:
                            # 2) Fallback: try to match by client order id (orderLinkId)
                            link_id = execution.get('orderLinkId')
                            if link_id:
                                order = self.orders_by_link_id.get(link_id)
                                if order is not None:
                                    self.logger.info(
                                        f"Matched execution via orderLinkId for unknown orderId: {execution['orderId']} / {link_id}"
                                    )
                                    # If we didn't know exchange_id yet, set it now
                                    if not getattr(order, "exchange_id", None):
                                        order.exchange_id = execution['orderId']
                                    # And register in self.orders for future lookups
                                    self.orders[order.exchange_id] = order

                        if order is None:
                            # Still unknown: log and skip
                            self.logger.warning(
                                "Execution for unknown order. orderId=%s, orderLinkId=%s, known orders=%s" %
                                (execution.get('orderId'), execution.get('orderLinkId'), list(self.orders.keys()))
                            )
                            continue

                        sideMulti = 1 if execution['side'] == "Buy" else -1
                        order.executed_amount = (float(execution['orderQty']) - float(
                            execution['leavesQty'])) * sideMulti
                        if (order.executed_amount - order.amount) * sideMulti >= 0:
                            order.active = False

                        self.on_execution_callback(
                            order_id=order.id,
                            executed_price=float(execution['execPrice']),
                            amount=float(execution['execQty']) * sideMulti,
                            tstamp=int(int(execution['execTime']) / 1000),
                        )

                        self.logger.info(
                            "got order execution: %s %.4f @ %.4f " %
                            (execution['orderLinkId'], float(execution['execQty']) * sideMulti,
                             float(execution['execPrice']))
                        )
                elif topic == 'position':
                    #print('position msg arrived:')
                    # {'bustPrice': '0.00', 'category': 'inverse', 'createdTime': '1627542388255',
                    # 'cumRealisedPnl': '0.04030169', 'entryPrice': '0', 'leverage': '100', 'liqPrice': '',
                    # 'markPrice': '41835.00', 'positionBalance': '0', 'positionIdx': 0, 'positionMM': '0',
                    # 'positionIM': '0', 'positionStatus': 'Normal', 'positionValue': '0', 'riskId': 1,
                    # 'riskLimitValue': '150', 'side': 'None', 'size': '0', 'stopLoss': '0.00', 'symbol': 'BTCUSD',
                    # 'takeProfit': '0.00', 'tpslMode': 'Full', 'tradeMode': 0, 'autoAddMargin': 1,
                    # 'trailingStop': '0.00', 'unrealisedPnl': '0', 'updatedTime': '1702819920894',
                    # 'adlRankIndicator': 0, 'seq': 31244873358, 'isReduceOnly': False, 'mmrSysUpdateTime': '',
                    # 'leverageSysUpdatedTime': ''}
                    for pos in msgs:
                        #self.logger.info("pos message arrived: %s" % (str(pos)))
                        if pos['symbol'] == self.symbol:
                            if pos["side"] == "Sell":
                                self.shortPos.quantity = -float(pos['size'])
                                self.shortPos.avgEntryPrice = float(pos['entryPrice'])
                                sizefac = -1
                            elif pos["side"] == "Buy":
                                self.longPos.quantity = float(pos['size'])
                                self.longPos.avgEntryPrice = float(pos['entryPrice'])
                                sizefac = 1
                            elif pos["side"] == "None" or len(pos["side"]) == 0:
                                self.longPos.quantity = 0
                                self.longPos.avgEntryPrice = 0
                                self.shortPos.quantity = 0
                                self.shortPos.avgEntryPrice = 0
                                sizefac = 0
                            else:
                                self.logger.info('WARNING: unknown value for side. Value: '+str(pos["side"]))
                                sizefac = 0

                            if pos['symbol'] not in self.positions.keys():
                                self.logger.info("Symbol was not in keys. Adding...")
                                self.positions[pos['symbol']] = AccountPosition(pos['symbol'],
                                                                                avgEntryPrice=float(pos["entryPrice"]),
                                                                                quantity=float(pos["size"]) * sizefac,
                                                                                walletBalance=float(pos['positionBalance']))
                            self.updatePosition_internally()

                elif topic.startswith('kline.') and topic.endswith('.' + self.symbol):
                    for b in msgs:
                        #print('kline message: ')
                        #print(b)
                        b['start'] = int(int(b['start'])/1000)
                        b['end'] = int(int(b['end']) / 1000)
                        b['timestamp'] = int(int(b['timestamp']) / 1000)
                    msgs.sort(key=lambda temp: temp['start'], reverse=True)
                    if len(self.bars) > 0:
                        for b in reversed(msgs):
                            if int(self.bars[0]['start']) >= b['start'] >= self.bars[-1]['start']:
                                # find bar to fix
                                for idx in range(0, len(self.bars)):
                                    if b['start'] == self.bars[idx]['start']:
                                        self.bars[idx] = b
                                        break
                            elif b['start'] > self.bars[0]['start']:
                                self.bars.insert(0, b)
                                gotTick = True
                            # ignore old bars
                    else:
                        self.bars = msgs
                        gotTick = True
                elif topic == 'trade.' + self.symbol:
                    last_trade = msgs[0]
                    self.last = float(last_trade["price"])
                elif topic == 'tickers.' + self.symbol:
                    # msgs is usually a list with one dict, but be defensive:
                    ticker = msgs[0] if isinstance(msgs, list) and msgs else msgs
                    if isinstance(ticker, dict) and ticker.get("symbol") == self.symbol:
                        # V5 uses lastPrice as string
                        lp = ticker.get("lastPrice")
                        if lp is not None:
                            try:
                                self.last = float(lp)
                            except ValueError:
                                self.logger.warning(f"Could not parse lastPrice from ticker: {lp!r}")
                elif topic == 'wallet':
                    #print(str(topic))
                    for wallet in msgs:
                        for coin in wallet['coin']:
                            #print(coin)
                            if self.baseCoin == coin['coin']:
                                #print("wallet balance is:")
                                #print(float(wallet["walletBalance"]))
                                self.longPos.walletBalance = float(coin["walletBalance"])
                                self.shortPos.walletBalance = float(coin["walletBalance"])
                    self.updatePosition_internally()
                    #for coin in wallet['coin']:
                    #    #pass
                    #self.logger.info("wallet message arrived")
                    #    if self.baseCurrency == coin['coin']:
                    #        self.longPos.walletBalance = float(wallet["walletBalance"])
                    #        self.shortPos.walletBalance = float(wallet["walletBalance"])
                    #        self.update_account()
                    ##        self.positions[pos['symbol']]
                    #        accountPos.walletBalance = float(pos['walletBalance'])
                else:
                    self.logger.error('got unkown topic in callback: ' + topic)
                msgs = self.ws.get_data(topic)

            # new bars is handling directly in the message, because we get a new one on each tick
            if topic in ["order", "stopOrder", "execution", "wallet"]:
                gotTick = True
                self.reset_order_sync_timer() # only when something with orders changed
            if gotTick and self.on_tick_callback is not None:
                self.on_tick_callback(
                    fromAccountAction=topic in ["order", "stopOrder", "execution", "wallet"])  # got something new
        except Exception as e:
            self.logger.error("error in socket data (%s): %s " % (topic, str(e)))

    def handle_result(self, call, *, context: str = ""):
        try:
            result = call()

            if not isinstance(result, dict):
                self.logger.error(f"Unexpected response type from Bybit ({context}): {result!r}")
                if self.on_api_error:
                    self.on_api_error(f"unexpected response type from Bybit ({context})")
                return None

            ret_code = result.get("retCode")
            ret_msg = result.get("retMsg")
            if ret_code is not None and ret_code != 0:
                self.logger.error(
                    f"Bybit API error ({context}): retCode={ret_code}, retMsg={ret_msg}, raw={result!r}"
                )
                if self.on_api_error:
                    self.on_api_error(f"Bybit API error ({context}): {ret_code} {ret_msg}")
                return None

            inner = result.get("result")
            if inner is not None:
                return inner

            self.logger.warning(
                f"Bybit returned retCode=0 but result=None ({context}). Raw={result!r}"
            )
            return None

        except (InvalidRequestError, FailedRequestError) as e:
            self.logger.error(f"Bybit request failed ({context}): {e}")
            if self.on_api_error:
                self.on_api_error(f"Bybit request failed ({context}): {e}")
            return None

        except Exception as e:
            self.logger.error(f"Unexpected API error ({context}): {repr(e)}")
            if self.on_api_error:
                self.on_api_error(f"unexpected error in request ({context}): {repr(e)}")
            return None

    def orderDictToOrder(self, o):
        # side & size
        sideMulti = 1 if o["side"] == "Buy" else -1

        # trigger price (conditional orders)
        stop = None
        if "triggerPrice" in o and o["triggerPrice"]:
            stop = float(o["triggerPrice"])

        order = Order(
            orderId=o.get("orderLinkId") or o["orderId"],
            trigger=stop,
            limit=float(o["price"]) if o.get("price") not in (None, "", "0", "0.0") else None,
            amount=sideMulti * float(o["qty"]),
        )

        # status mapping (V5)
        status = o.get("orderStatus", "")
        order.active = status in ("New", "Untriggered", "PartiallyFilled")
        order.stop_triggered = status in ("Triggered", "PartiallyFilled", "Filled")

        # execution info
        execution_qty = float(o.get("cumExecQty", 0.0))
        order.executed_amount = execution_qty * sideMulti

        # timestamps are ms in V5
        t_raw = o.get("updatedTime") or o.get("createdTime")
        if t_raw is not None:
            order.tstamp = int(int(t_raw) / 1000)

        # exchange id
        order.exchange_id = o["orderId"]

        # executed price
        cum_value_str = o.get("cumExecValue")
        if cum_value_str is not None and cum_value_str not in ("", "0", "0.0") and execution_qty != 0:
            v = float(cum_value_str)
            if self.category == "inverse":
                # inverse: value ≈ qty / price  => price ≈ qty / value
                order.executed_price = execution_qty / v
            else:
                # linear: value ≈ qty * price => price ≈ value / qty
                order.executed_price = v / execution_qty
        else:
            order.executed_price = None

        return order

    @staticmethod
    def barDictToBar(b):
        #tstamp = int(b['open_time'] if 'open_time' in b.keys() else b['start'])
        #bar = Bar(tstamp=tstamp, open=float(b['open']), high=float(b['high']),
        #          low=float(b['low']), close=float(b['close']), volume=float(b['volume']))

        if 'open_time' in b:
            tstamp = int(b['open_time'])
            bar = Bar(tstamp=tstamp, open=float(b['open']), high=float(b['high']),
                      low=float(b['low']), close=float(b['close']), volume=float(b['volume']))
        elif 'start' in b:
            tstamp = int(b['start'])
            bar = Bar(tstamp=tstamp, open=float(b['open']), high=float(b['high']),
                      low=float(b['low']), close=float(b['close']), volume=float(b['volume']))
        else: # bybit
            bar = Bar(tstamp = int(int(b[0])/1000), open=float(b[1]), high=float(b[2]),
                      low=float(b[3]), close=float(b[4]), volume=float(b[5]))
        #if 'timestamp' in b:
        #    bar.last_tick_tstamp = b['timestamp'] / 1000.0
        return bar
