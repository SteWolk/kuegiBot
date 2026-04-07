import logging
import math
#import statistics
import os
import csv
import json

import plotly.graph_objects as go

#import plotly.express as px
from typing import List

from kuegi_bot.bots.trading_bot import TradingBot, PositionDirection
from kuegi_bot.utils.trading_classes import OrderInterface, Bar, Account, Order, Symbol, AccountPosition, \
    PositionStatus, OrderType
from kuegi_bot.utils import log
from datetime import datetime, timezone


class SilentLogger(object):

    def info(self, *args, **kwargs):
        pass

    def warn(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass

    def debug(self, *args, **kwargs):
        pass


class BackTest(OrderInterface):

    def __init__(self, bot: TradingBot, bars: list, funding: dict = None, symbol: Symbol = None,
                 market_slipage_percent=0.15, early_stop_config: dict = None):
        self.bars: List[Bar] = bars
        self.funding = funding
        self.firstFunding = 9999999999
        self.lastFunding = 0
        if funding is not None:
            for key in funding.keys():
                self.firstFunding = min(self.firstFunding, key)
                self.lastFunding = max(self.lastFunding, key)
        self.handles_executions = True
        self.logger = bot.logger
        self.bot = bot
        self.bot.prepare(SilentLogger(), self)
        if hasattr(self.bot, "set_backtest_bars"):
            self.bot.set_backtest_bars(self.bars)

        self.market_slipage_percent = market_slipage_percent
        # Fallback defaults in fractional rates (e.g. 0.00055 = 0.055%)
        self.maker_fee = 0.0002
        self.taker_fee = 0.00055

        if symbol is not None:
            self.symbol = symbol
        else:
            self.symbol: Symbol = Symbol(symbol="XBTUSD", isInverse=True, tickSize=0.5, lotSize=1, makerFee=0.0002,
                                         takerFee=0.00055)
        # Use symbol fee settings if available.
        self.maker_fee = self._normalize_fee_rate(getattr(self.symbol, "makerFee", self.maker_fee), "makerFee")
        self.taker_fee = self._normalize_fee_rate(getattr(self.symbol, "takerFee", self.taker_fee), "takerFee")

        self.account: Account = None
        self.initialEquity = 100  # BTC
        self.drawdown_basis_equity = self.initialEquity

        self.hh = self.initialEquity
        self.maxDD = 0
        self.max_underwater = 0
        self.underwater = 0
        self.maxExposure = 0
        self.lastHHPosition = 0

        self.current_bars: List[Bar] = []
        self.unrealized_equity = 0
        self.cum_funding_for_dd = 0
        self.total_equity_vec = []
        self.equity_vec = []
        self.unrealized_equity_vec = []
        self.hh_vec = []
        self.ll_vec = []
        self.dd_vec = []
        self.maxDD_vec = []
        self.wallet_equity_vec = []
        self.early_stop_config = dict(early_stop_config) if isinstance(early_stop_config, dict) else {}
        self.early_stopped = False
        self.early_stop_reason = None
        self.last_processed_bar = None
        self.reset()

    def _normalize_fee_rate(self, rate, field_name: str) -> float:
        """
        Normalize fee rate to fraction form:
        - 0.00055 => 0.055%
        - 0.055   => interpreted as 0.055% and converted to 0.00055
        """
        try:
            normalized = float(rate)
        except Exception:
            self.logger.warning("Invalid %s=%s, defaulting to 0.", field_name, str(rate))
            return 0.0

        # Backward compatibility for historical script values entered as percent units.
        if abs(normalized) >= 0.01:
            self.logger.warning(
                "Interpreting %s=%s as percent and converting to fraction.", field_name, normalized
            )
            normalized = normalized / 100.0
        return normalized

    def reset(self):
        self.account = Account()
        self.account.open_position.walletBalance = self.initialEquity
        self.account.open_position.quantity = 0
        self.account.equity = self.account.open_position.walletBalance
        self.account.usd_equity = self.initialEquity * self.bars[-1].open
        self.hh = self.initialEquity
        self.maxDD = 0
        self.max_underwater = 0
        self.lastHHPosition = 0
        self.underwater = 0
        self.maxExposure = 0
        self.unrealized_equity=0
        self.cum_funding_for_dd  = 0
        self.drawdown_basis_equity = self.initialEquity
        self.total_equity_vec = []
        self.equity_vec = []
        self.unrealized_equity_vec = []
        self.hh_vec = []
        self.ll_vec = []
        self.dd_vec = []
        self.wallet_equity_vec = []
        self.early_stopped = False
        self.early_stop_reason = None
        self.last_processed_bar = None
        self.bot.reset()
        if hasattr(self.bot, "set_backtest_bars"):
            self.bot.set_backtest_bars(self.bars)

        self.current_bars = []
        for b in self.bars:
            b.did_change = True
            b.bot_data = {"indicators": {}}
        self.bot.init(self.bars[-self.bot.min_bars_needed():], self.account, self.symbol, None)

    # implementing OrderInterface

    def send_order(self, order: Order):
        # check if order is val
        if order.amount == 0:
            self.logger.error("trying to send order without amount")
            return
        posId, order_type = TradingBot.position_id_and_type_from_order_id(order.id)
        if order_type == OrderType.ENTRY:
            unused, direction = TradingBot.split_pos_Id(posId)
            if direction == PositionDirection.LONG and order.amount < 0:
                self.logger.error("sending long entry with negative amount")
            if direction == PositionDirection.SHORT and order.amount > 0:
                self.logger.error("sending short entry with positive amount")

        self.logger.debug("added order %s" % (order.print_info()))

        order.tstamp = self.current_bars[0].tstamp
        if order not in self.account.open_orders:  # bot might add it himself temporarily.
            self.account.open_orders.append(order)

    def update_order(self, order: Order):
        for existing_order in self.account.open_orders:
            if existing_order.id == order.id:
                self.account.open_orders.remove(existing_order)
                self.account.open_orders.append(order)
                order.tstamp = self.current_bars[0].last_tick_tstamp
                self.logger.debug("updated order %s" % (order.print_info()))
                break

    def cancel_order(self, order_to_cancel):
        for order in self.account.open_orders:
            if order.id == order_to_cancel.id:
                order.active = False
                order.final_tstamp = self.current_bars[0].tstamp
                order.final_reason = 'cancel'

                self.account.order_history.append(order)
                self.account.open_orders.remove(order)
                self.logger.debug("canceled order " + order_to_cancel.id)
                break

    # ----------
    def handle_order_execution(self, order: Order, intrabar: Bar, force_taker=False):
        amount = order.amount - order.executed_amount
        order.executed_amount = order.amount
        fee = self.taker_fee
        if order.limit_price and not force_taker:
            price = order.limit_price
            fee = self.maker_fee
        elif order.trigger_price:
            price = int(order.trigger_price * (1 + math.copysign(self.market_slipage_percent,
                                                                 order.amount) / 100) / self.symbol.tickSize) * self.symbol.tickSize
        else:
            price = intrabar.open * (1 + math.copysign(self.market_slipage_percent, order.amount) / 100)
        price = min(intrabar.high,
                    max(intrabar.low, price))  # only prices within the bar. might mean less slipage
        order.executed_price = price
        oldAmount = self.account.open_position.quantity
        if oldAmount != 0:
            oldavgentry = self.account.open_position.avgEntryPrice
            if oldAmount * amount > 0:
                self.account.open_position.avgEntryPrice = (oldavgentry * oldAmount + price * amount) / (
                            oldAmount + amount)
            if oldAmount * amount < 0:
                if abs(oldAmount) < abs(amount):
                    profit = oldAmount * (
                        (price - oldavgentry) if not self.symbol.isInverse else (-1 / price + 1 / oldavgentry))
                    self.account.open_position.walletBalance += profit
                    # close current, open new
                    self.account.open_position.avgEntryPrice = price
                else:
                    # closes the position by "-amount" cause amount is the side and direction of the close
                    profit = -amount * (
                        (price - oldavgentry) if not self.symbol.isInverse else (-1 / price + 1 / oldavgentry))
                    self.account.open_position.walletBalance += profit
        else:
            self.account.open_position.avgEntryPrice = price
        self.account.open_position.quantity += amount
        volume = amount * (price if not self.symbol.isInverse else -1 / price)
        self.account.open_position.walletBalance -= math.fabs(volume) * fee

        order.active = False
        order.execution_tstamp = intrabar.tstamp
        order.final_reason = 'executed'

        self.bot.on_execution(order_id=order.id, amount=amount, executed_price=price, tstamp=intrabar.tstamp)
        self.account.order_history.append(order)
        self.account.open_orders.remove(order)
        self.logger.debug(
            "executed order %s | %.0f %.5f | %.5f@ %.1f" % (
                order.id, self.account.usd_equity, self.account.open_position.quantity, order.executed_amount,
                order.executed_price))

    def orderKeyForSort(self, order):
        if order.trigger_price is None and order.limit_price is None:
            return 0
        # sort buys after sells (higher number) when bar is falling
        long_fac = 1 if self.bars[0].close > self.bars[0].open else 2
        short_fac = 1 if self.bars[0].close < self.bars[0].open else 2
        if order.trigger_price is not None:
            if order.amount > 0:
                return order.trigger_price
            else:
                return -order.trigger_price
        else:  # limit -> bigger numbers to be sorted after the stops
            if order.amount > 0:
                return (self.bars[0].close + self.bars[0].close - order.limit_price) + self.bars[0].close * long_fac
            else:
                return order.limit_price + self.bars[0].close * short_fac

    def check_executions(self, intrabar_to_check: Bar, only_on_close):
        another_round = True
        did_something = False
        allowed_order_ids = None
        if not only_on_close:
            allowed_order_ids = set(map(lambda o: o.id, self.account.open_orders))
        loopbreak = 0
        while another_round:
            if loopbreak > 100:
                print("got loop in backtest execution")
                break
            loopbreak += 1
            another_round = False
            should_execute = False
            orders = self.account.open_orders
            if len(orders) <= 1:
                iterable_orders = orders
            else:
                iterable_orders = sorted(orders, key=self.orderKeyForSort)
            for order in iterable_orders:
                if allowed_order_ids is not None and order.id not in allowed_order_ids:
                    continue
                force_taker = False
                execute_order_only_on_close = only_on_close
                if order.tstamp > intrabar_to_check.tstamp:
                    execute_order_only_on_close = True  # was changed during execution on this bar, might have changed the price. only execute if close triggered it
                if order.limit_price is None and order.trigger_price is None:
                    should_execute = True
                elif order.trigger_price and not order.stop_triggered:
                    if (order.amount > 0 and order.trigger_price < intrabar_to_check.high) or (
                            order.amount < 0 and order.trigger_price > intrabar_to_check.low):
                        order.stop_triggered = True
                        something_changed = True
                        if order.limit_price is None:
                            # execute stop market
                            should_execute = True
                            if only_on_close:  # order just came in and executed right away: execution on the worst price cause can't assume anything better
                                order.trigger_price = intrabar_to_check.low if order.amount < 0 else intrabar_to_check.high

                        elif ((order.amount > 0 and order.limit_price > intrabar_to_check.close) or (
                                order.amount < 0 and order.limit_price < intrabar_to_check.close)):
                            # close below/above limit: got definitly executed
                            should_execute = True
                            force_taker = True  # need to assume taker.
                else:  # means order.limit_price and (order.stop_price is None or order.stop_triggered):
                    # check for limit execution
                    ref = intrabar_to_check.low if order.amount > 0 else intrabar_to_check.high
                    if execute_order_only_on_close:
                        ref = intrabar_to_check.close
                        force_taker = True  # need to assume taker.
                    if (order.amount > 0 and order.limit_price > ref) or (
                            order.amount < 0 and order.limit_price < ref):
                        should_execute = True

                if should_execute:
                    self.handle_order_execution(order, intrabar_to_check, force_taker=force_taker)
                    self.bot.on_tick(self.current_bars, self.account)
                    another_round = True
                    did_something = True
                    break
        return did_something

    def handle_subbar(self, intrabarToCheck: Bar):
        self.current_bars[0].add_subbar(intrabarToCheck)  # so bot knows about the current intrabar
        if len(self.account.open_orders) == 0:
            # No active orders to evaluate against this subbar, so we can directly tick once.
            self.bot.on_tick(self.current_bars, self.account)
        else:
            # first the ones that are there at the beginning
            something_changed_on_existing_orders = self.check_executions(intrabarToCheck, False)
            something_changed_on_second_pass = self.check_executions(intrabarToCheck, True)
            # then the new ones with updated bar

            if not something_changed_on_existing_orders and not something_changed_on_second_pass:  # no execution happened -> execute on tick now
                self.bot.on_tick(self.current_bars, self.account)

        # update equity = balance + current value of open position
        avgEntry = self.account.open_position.avgEntryPrice
        if avgEntry != 0:
            posValue = self.account.open_position.quantity * (
                (intrabarToCheck.close - avgEntry) if not self.symbol.isInverse else (
                        -1 / intrabarToCheck.close + 1 / avgEntry))
        else:
            posValue = 0

        # True economic equity (real wallet includes fees + funding; add unrealized PnL)
        self.account.equity = self.account.open_position.walletBalance + posValue

        # Separate basis for drawdown/statistics:
        # - excludes unrealized PnL noise
        # - excludes funding impact
        # - still includes realized PnL and trading fees
        self.drawdown_basis_equity = self.account.open_position.walletBalance + self.cum_funding_for_dd

        self.account.usd_equity = self.account.equity * intrabarToCheck.close
        self.unrealized_equity = posValue

        self.update_stats()

    def update_stats(self):

        if math.fabs( # TODO: why?
                self.account.open_position.quantity) < 1 or self.lastHHPosition * self.account.open_position.quantity < 0:
            self.hh = max(self.hh, self.drawdown_basis_equity)  # only update HH on closed positions, no open equity
            self.lastHHPosition = self.account.open_position.quantity
        dd = self.hh - self.drawdown_basis_equity
        if dd > self.maxDD:
            self.maxDD = dd

        exposure = abs(self.account.open_position.quantity) * (
            1 / self.current_bars[0].close if self.symbol.isInverse else self.current_bars[0].close)
        self.maxExposure = max(self.maxExposure, exposure)
        # inside write_plot_data, after equity_vec append
        if self.drawdown_basis_equity < self.hh:
            self.underwater += 1
        else:
            self.underwater = 0
        self.max_underwater = max(self.max_underwater, self.underwater)

    def write_plot_data(self):
        avgEntry = self.account.open_position.avgEntryPrice
        if avgEntry != 0:
            unrealized_equity = self.account.open_position.quantity * (
                (self.current_bars[0].close - avgEntry) if not self.symbol.isInverse else (
                        -1 / self.current_bars[0].close + 1 / avgEntry))
        else:
            unrealized_equity = 0

        #self.equity_vec.append(self.drawdown_basis_equity)
        self.equity_vec.append(self.account.open_position.walletBalance)
        self.wallet_equity_vec.append(self.account.open_position.walletBalance)
        self.unrealized_equity_vec.append(unrealized_equity)
        self.total_equity_vec.append(self.account.equity)
        dd_basis = self.drawdown_basis_equity

        self.hh_vec.append(
            dd_basis if len(self.hh_vec) == 0
            else (dd_basis if dd_basis > self.hh_vec[-1] else self.hh_vec[-1])
        )

        self.ll_vec.append(
            dd_basis if len(self.ll_vec) == 0
            else (dd_basis if dd_basis < self.ll_vec[-1] else self.ll_vec[-1])
        )

        self.dd_vec.append(-(self.hh_vec[-1] - dd_basis))

        self.maxDD_vec.append(
            self.dd_vec[0] if len(self.maxDD_vec) == 0
            else (self.dd_vec[-1] if self.dd_vec[-1] < self.maxDD_vec[-1] else self.maxDD_vec[-1])
        )

    def do_funding(self):
        funding = 0
        bar = self.current_bars[0]
        if self.funding is not None and self.firstFunding <= bar.tstamp <= self.lastFunding:
            if bar.tstamp in self.funding:
                funding = self.funding[bar.tstamp]
        else:
            dt = datetime.fromtimestamp(bar.tstamp, tz=timezone.utc)
            if dt.hour in (0, 8, 16):
                funding = 0.0001

        if funding != 0 and self.account.open_position.quantity != 0:
            qty = self.account.open_position.quantity
            if funding != 0 and qty != 0:
                if self.funding is None:
                    funding = abs(funding) if qty > 0 else -abs(funding)

                funding_delta = funding * qty / bar.open
                self.account.open_position.walletBalance -= funding_delta
                self.cum_funding_for_dd += funding_delta

    def _run_initial_plot_warmup(self, min_bars_needed: int):
        for _idx in range(0, min_bars_needed):
            self.write_plot_data()

    def _process_backtest_bar(self, i: int):
        self.current_bars = self.bars[-(i + 1):]
        next_bar = self.bars[-i - 2]
        forming_bar = Bar(
            tstamp=next_bar.tstamp,
            open=next_bar.open,
            high=next_bar.open,
            low=next_bar.open,
            close=next_bar.open,
            volume=0,
            subbars=[],
        )
        self.current_bars.insert(0, forming_bar)
        self.current_bars[0].did_change = True
        self.current_bars[1].did_change = True

        self.do_funding()
        self.bot.on_tick(self.current_bars, self.account)
        self.write_plot_data()

        for subbar in reversed(next_bar.subbars):
            if subbar.last_tick_tstamp < subbar.tstamp + 59:
                subbar.last_tick_tstamp = subbar.tstamp + 59
            self.handle_subbar(subbar)
            self.current_bars[1].did_change = False

        next_bar.bot_data = forming_bar.bot_data
        for bar in self.current_bars:
            if bar.did_change:
                bar.did_change = False
                continue
            break
        self.last_processed_bar = next_bar

    def _current_profit_pct(self) -> float:
        if self.initialEquity <= 0:
            return 0.0
        return 100.0 * (self.account.equity - self.initialEquity) / self.initialEquity

    def _current_max_dd_pct(self) -> float:
        if self.initialEquity <= 0 or len(self.maxDD_vec) == 0:
            return 0.0
        return 100.0 * self.maxDD_vec[-1] / self.initialEquity

    def _current_closed_trades(self) -> int:
        n_closed = 0
        for pos in self.bot.position_history:
            if pos.status == PositionStatus.CLOSED:
                n_closed += 1
        return n_closed

    def _should_early_stop(self, processed_bars: int, total_bars: int) -> bool:
        cfg = self.early_stop_config
        if len(cfg) == 0:
            return False

        check_every = max(1, int(cfg.get("check_every", 1)))
        if processed_bars % check_every != 0 and processed_bars < total_bars:
            return False

        min_bars = max(0, int(cfg.get("min_bars", 0)))
        if processed_bars < min_bars:
            return False

        min_progress = float(cfg.get("min_progress", 0.0))
        progress = (processed_bars / float(total_bars)) if total_bars > 0 else 1.0
        if progress < min_progress:
            return False

        max_trades_closed = cfg.get("max_trades_closed")
        if max_trades_closed is not None:
            current_trades_closed = self._current_closed_trades()
            if current_trades_closed >= int(max_trades_closed):
                self.early_stopped = True
                self.early_stop_reason = "trades_closed=%d reached threshold=%d" % (
                    int(current_trades_closed),
                    int(max_trades_closed),
                )
                return True

        tiers = cfg.get("tiers", [])
        if isinstance(tiers, list) and len(tiers) > 0:
            active = []
            for tier in tiers:
                if not isinstance(tier, dict):
                    continue
                tier_progress = float(tier.get("min_progress", 0.0))
                if progress >= tier_progress:
                    active.append(tier)
            if len(active) > 0:
                active = sorted(active, key=lambda row: float(row.get("min_progress", 0.0)))
                tier = active[-1]
                tier_max_dd = tier.get("max_dd_pct")
                if tier_max_dd is not None:
                    current_dd_pct = self._current_max_dd_pct()
                    if current_dd_pct < float(tier_max_dd):
                        self.early_stopped = True
                        self.early_stop_reason = "tier max_dd_pct=%.2f below threshold=%.2f at progress=%.3f" % (
                            current_dd_pct,
                            float(tier_max_dd),
                            progress,
                        )
                        return True
                tier_min_profit = tier.get("min_profit_pct")
                if tier_min_profit is not None:
                    current_profit_pct = self._current_profit_pct()
                    if current_profit_pct < float(tier_min_profit):
                        self.early_stopped = True
                        self.early_stop_reason = "tier profit_pct=%.2f below threshold=%.2f at progress=%.3f" % (
                            current_profit_pct,
                            float(tier_min_profit),
                            progress,
                        )
                        return True

        max_dd_pct = cfg.get("max_dd_pct")
        if max_dd_pct is not None:
            current_dd_pct = self._current_max_dd_pct()
            if current_dd_pct < float(max_dd_pct):
                self.early_stopped = True
                self.early_stop_reason = "max_dd_pct=%.2f below threshold=%.2f" % (
                    current_dd_pct,
                    float(max_dd_pct),
                )
                return True

        min_profit_pct = cfg.get("min_profit_pct")
        if min_profit_pct is not None:
            current_profit_pct = self._current_profit_pct()
            if current_profit_pct < float(min_profit_pct):
                self.early_stopped = True
                self.early_stop_reason = "profit_pct=%.2f below threshold=%.2f" % (
                    current_profit_pct,
                    float(min_profit_pct),
                )
                return True

        return False

    def _run_price_loop(self, min_bars_needed: int):
        total_bars = max(1, len(self.bars) - min_bars_needed)
        processed_bars = 0
        for i in range(min_bars_needed, len(self.bars)):
            if i == len(self.bars) - 1:
                self.last_processed_bar = self.bars[0]
                self.write_plot_data()
                processed_bars += 1
                if self._should_early_stop(processed_bars=processed_bars, total_bars=total_bars):
                    break
                continue
            self._process_backtest_bar(i)
            processed_bars += 1
            if self._should_early_stop(processed_bars=processed_bars, total_bars=total_bars):
                self.logger.info(
                    "early stop: processed=%d/%d reason=%s",
                    processed_bars,
                    total_bars,
                    str(self.early_stop_reason),
                )
                break

    def _force_close_remaining_position(self):
        if abs(self.account.open_position.quantity) <= self.symbol.lotSize / 10:
            return
        ref_bar = self.last_processed_bar if self.last_processed_bar is not None else self.bars[0]
        if len(ref_bar.subbars) > 0:
            close_bar = ref_bar.subbars[-1]
        else:
            close_bar = Bar(
                tstamp=ref_bar.tstamp,
                open=ref_bar.close,
                high=ref_bar.close,
                low=ref_bar.close,
                close=ref_bar.close,
                volume=0,
                subbars=[],
            )
            close_bar.last_tick_tstamp = close_bar.tstamp + 59
        self.send_order(Order(orderId="endOfTest", amount=-self.account.open_position.quantity))
        self.handle_subbar(close_bar)

    def _closed_positions_for_metrics(self):
        closed_positions = []
        for pos in self.bot.position_history:
            if pos.status != PositionStatus.CLOSED:
                continue
            if pos.exit_tstamp is None:
                pos.exit_tstamp = self.bars[-1].tstamp
            closed_positions.append(pos)
        return closed_positions

    def _count_open_positions(self) -> int:
        nmb = 0
        for position in self.bot.open_positions.values():
            if position.status == PositionStatus.OPEN:
                nmb += 1
        return nmb

    def _compute_performance_metrics(self, n_closed: int):
        final_equity = self.account.equity
        profit = final_equity - self.initialEquity

        first_ts = self.bars[0].tstamp
        last_ts = self.bars[-1].tstamp
        total_days = max(1e-9, abs(last_ts - first_ts) / (60 * 60 * 24))
        max_dd = -self.maxDD_vec[-1]

        if max_dd > 0 and final_equity != self.initialEquity:
            rel = final_equity / max_dd
        else:
            rel = 0.0
        rel_per_year = rel / (total_days / 365) if rel > 0 and total_days > 0 else 0.0

        N0 = 100
        if n_closed > 0:
            trade_factor = math.sqrt(n_closed / (n_closed + N0))
        else:
            trade_factor = 0.0
        rel_per_year_trades = rel_per_year * trade_factor

        years = total_days / 365.0
        if years > 0 and self.initialEquity > 0 and final_equity > 0:
            cagr = (final_equity / self.initialEquity) ** (1.0 / years) - 1.0
        else:
            cagr = 0.0

        if self.initialEquity > 0:
            max_dd_frac = max_dd / self.initialEquity
        else:
            max_dd_frac = 0.0
        if max_dd_frac > 0 and cagr > 0:
            mar_ratio = cagr / max_dd_frac
        else:
            mar_ratio = 0.0

        return {
            "final_equity": final_equity,
            "profit": profit,
            "total_days": total_days,
            "max_dd": max_dd,
            "rel_per_year": rel_per_year,
            "rel_per_year_trades": rel_per_year_trades,
            "cagr": cagr,
            "mar_ratio": mar_ratio,
        }

    def _compute_trade_statistics(self, closed_positions: list):
        trade_R = []
        wins = 0
        losses = 0
        win_sum = 0.0
        loss_sum = 0.0

        for pos in closed_positions:
            if pos.filled_entry is None or pos.filled_exit is None:
                continue
            if pos.max_filled_amount == 0:
                continue

            entry = pos.filled_entry
            exit_ = pos.filled_exit
            if pos.max_filled_amount > 0:
                r = (exit_ - entry) / entry
            else:
                r = (entry - exit_) / entry

            trade_R.append(r)
            if r > 0:
                wins += 1
                win_sum += r
            elif r < 0:
                losses += 1
                loss_sum += r

        if len(trade_R) >= 2:
            mean_R = sum(trade_R) / len(trade_R)
            var_R = sum((r - mean_R) ** 2 for r in trade_R) / (len(trade_R) - 1)
            std_R = math.sqrt(var_R) if var_R > 0 else 0.0
        elif len(trade_R) == 1:
            mean_R = trade_R[0]
            std_R = 0.0
        else:
            mean_R = 0.0
            std_R = 0.0

        if len(trade_R) > 0:
            win_rate = wins / len(trade_R)
        else:
            win_rate = 0.0

        if losses > 0:
            profit_factor = -win_sum / loss_sum if loss_sum < 0 else 0.0
        else:
            profit_factor = float('inf') if wins > 0 else 0.0

        if std_R > 0 and len(trade_R) > 1:
            sqn = (mean_R / std_R) * math.sqrt(len(trade_R))
        else:
            sqn = 0.0

        return {
            "mean_R": mean_R,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "sqn": sqn,
        }

    def _log_backtest_summary(self, n_closed: int, nmb: int, performance: dict, trade_stats: dict):
        self.logger.info(
            "trades: " + str(n_closed)
            + " | open pos: " + str(nmb)
            + " | profit: " + ("%.2f" % (100 * performance["profit"] / self.initialEquity)) + "%"
            + " | unreal.: " + ("%.1f" % (100 * self.unrealized_equity_vec[-1] / self.initialEquity)) + "%"
            + " | maxDD: " + ("%.2f" % (100 * self.maxDD_vec[-1] / self.initialEquity)) + "%"
            + " | maxExp: " + ("%.1f" % (100 * self.maxExposure / self.initialEquity)) + "%"
            + " | relY_final: " + ("%.2f" % (performance["rel_per_year"]))
            + " | relY_final_trades: " + ("%.2f" % (performance["rel_per_year_trades"]))
            + " | CAGR: " + ("%.2f" % (100 * performance["cagr"])) + "%"
            + " | MAR: " + ("%.2f" % (performance["mar_ratio"]))
            + " | winrate: " + ("%.1f" % (100 * trade_stats["win_rate"])) + "%"
            + " | avgR: " + ("%.3f" % (trade_stats["mean_R"]))
            + " | PF: " + ("%.2f" % (trade_stats["profit_factor"] if trade_stats["profit_factor"] != float('inf') else 0.0))
            + " | SQN_trades: " + ("%.2f" % (trade_stats["sqn"]))
        )

    def _finalize_metrics(self):
        if len(self.bot.position_history) == 0:
            self.logger.info("finished with no trades")
            self.metrics = None
            return

        closed_positions = self._closed_positions_for_metrics()
        n_closed = len(closed_positions)
        nmb = self._count_open_positions()
        performance = self._compute_performance_metrics(n_closed)
        trade_stats = self._compute_trade_statistics(closed_positions)
        self._log_backtest_summary(n_closed, nmb, performance, trade_stats)

        self.metrics = {
            "symbol": getattr(self.symbol, "symbol", None) if hasattr(self, "symbol") else None,
            "timeframe_minutes": None,
            "trades_closed": n_closed,
            "open_positions": nmb,
            "initial_equity": self.initialEquity,
            "final_equity": performance["final_equity"],
            "profit_abs": performance["profit"],
            "profit_pct": 100.0 * performance["profit"] / self.initialEquity if self.initialEquity > 0 else 0.0,
            "max_drawdown_abs": performance["max_dd"],
            "max_drawdown_pct": 100.0 * self.maxDD_vec[-1] / self.initialEquity if self.initialEquity > 0 else 0.0,
            "max_exposure_abs": self.maxExposure,
            "max_exposure_pct": 100.0 * self.maxExposure / self.initialEquity if self.initialEquity > 0 else 0.0,
            "total_days": performance["total_days"],
            "relY_final": performance["rel_per_year"],
            "relY_final_trades": performance["rel_per_year_trades"],
            "cagr": performance["cagr"],
            "mar": performance["mar_ratio"],
            "winrate": trade_stats["win_rate"],
            "avg_R": trade_stats["mean_R"],
            "profit_factor": trade_stats["profit_factor"],
            "sqn_trades": trade_stats["sqn"],
        }

    def run(self):
        self.reset()
        self.logger.info(
            "starting backtest with " + str(len(self.bars)) + " bars and " + str(self.account.equity) + " equity")
        min_bars_needed = self.bot.min_bars_needed()
        self._run_initial_plot_warmup(min_bars_needed)
        self._run_price_loop(min_bars_needed)
        if self.early_stopped:
            self.logger.info("backtest stopped early: %s", str(self.early_stop_reason))
        self._force_close_remaining_position()
        self._finalize_metrics()
        return self

    def plot_equity_stats(self):
        self.logger.info("creating equity plot")
        barcenter = (self.bars[0].tstamp - self.bars[1].tstamp) / 2
        time = list(map(lambda b: datetime.fromtimestamp(b.tstamp + barcenter), self.bars))

        #self.unrealized_equity_vec.reverse()
        self.total_equity_vec.reverse()
        #self.hh_vec.reverse()
        #self.ll_vec.reverse()
        self.equity_vec.reverse()
        self.maxDD_vec.reverse()
        self.dd_vec.reverse()

        sub_data ={
            #'unrealized equity':self.unrealized_equity_vec,
            'total equity':self.total_equity_vec,
            #'HH':self.hh_vec,
            #'LL':self.ll_vec,
            'maxDD':self.maxDD_vec,
            'DD':self.dd_vec,
        }

        # only plot wallet equity if the vector exists and has data
        if hasattr(self, "wallet_equity_vec") and len(self.wallet_equity_vec) > 0:
            self.wallet_equity_vec.reverse()
            sub_data['wallet equity'] = self.wallet_equity_vec

        colors = {
            # "unrealized equity": 'black',
            "total equity": 'lightblue',
            #"HH": 'lightgreen',
            # "LL": 'magenta',
            "realized equity": 'blue',
            "wallet equity": 'darkblue',
            "maxDD": 'red',
            "DD": 'orange'
        }

        data_abs = []
        for key in sub_data.keys():
            data_abs.append(
                go.Scatter(x=time, y=sub_data.get(key), name=(key + ': %.1f' % sub_data.get(key)[0]),
                           line=dict(color=colors.get(key, 'gray'), width=2))
            )
        fig_abs = go.Figure(data = data_abs)
        return fig_abs

    def plot_normalized_stats(self):
        self.logger.info("creating plot with normalized indicators")
        barcenter = (self.bars[0].tstamp - self.bars[1].tstamp) / 2

        time = list(map(lambda b: datetime.fromtimestamp(b.tstamp + barcenter), self.bars))
        open = list(map(lambda b: b.open, self.bars))
        high = list(map(lambda b: b.high, self.bars))
        low = list(map(lambda b: b.low, self.bars))
        close = list(map(lambda b: b.close, self.bars))

        normalizing_factor = 100

        # Normalize your price data
        normalized_open = [o / max(open) * normalizing_factor for o in open]
        normalized_high = [h / max(high) * normalizing_factor for h in high]
        normalized_low = [l / max(low) * normalizing_factor for l in low]
        normalized_close = [c / max(close) * normalizing_factor for c in close]

        fig = go.Figure()
        #    data=[go.Candlestick(x=time, open=open, high=high, low=low, close=close, name=self.symbol.symbol)])
        fig.add_trace(go.Candlestick(x=time, open=normalized_open, high=normalized_high, low=normalized_low,
                                     close=normalized_close, name=self.symbol.symbol, opacity=0.5))

        self.logger.info("adding normalized indicators to price chart from strategy and bot")
        self.bot.add_to_normalized_plot(fig, self.bars, time)
        fig.update_layout(xaxis_rangeslider_visible=False)
        fig.update_layout(hovermode='x')
        return fig

    def plot_price_data(self):
        barcenter = (self.bars[0].tstamp - self.bars[1].tstamp) / 2
        self.logger.info("creating price chart")
        time = list(map(lambda b: datetime.fromtimestamp(b.tstamp + barcenter), self.bars))
        open = list(map(lambda b: b.open, self.bars))
        high = list(map(lambda b: b.high, self.bars))
        low = list(map(lambda b: b.low, self.bars))
        close = list(map(lambda b: b.close, self.bars))

        #self.logger.info("creating plot")
        fig = go.Figure(
            data=[go.Candlestick(x=time, open=open, high=high, low=low, close=close, name=self.symbol.symbol)])

        self.logger.info("adding strategy and bot data to price chart")
        self.bot.add_to_price_data_plot(fig, self.bars, time)

        fig.update_layout(xaxis_rangeslider_visible=False)
        return fig

    def write_results_to_files(self):
        # positions
        base = 'results/' + self.bot.uid() + '/'
        try:
            os.makedirs(base)
        except Exception:
            pass

        uid = str(int(datetime.utcnow().timestamp())) + '_' + str(len(self.bot.position_history))
        tradesfilename = base + uid + '_trades.csv'
        self.logger.info("writing" + str(len(self.bot.position_history)) + " trades to file " + tradesfilename)
        with open(tradesfilename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            csv_columns = ['signalTStamp', 'size', 'wantedEntry', 'initialStop', 'openTime', 'openPrice', 'closeTime',
                           'closePrice', 'equityOnExit']
            writer.writerow(csv_columns)
            for position in self.bot.position_history:
                writer.writerow([
                    datetime.fromtimestamp(position.signal_tstamp).isoformat(),
                    position.max_filled_amount,
                    position.wanted_entry,
                    position.initial_stop,
                    datetime.fromtimestamp(position.entry_tstamp).isoformat(),
                    position.filled_entry,
                    datetime.fromtimestamp(position.exit_tstamp).isoformat(),
                    position.filled_exit,
                    position.exit_equity
                ])
            for position in self.bot.open_positions.values():
                writer.writerow([
                    datetime.fromtimestamp(position.signal_tstamp).isoformat(),
                    position.max_filled_amount,
                    position.wanted_entry,
                    position.initial_stop,
                    datetime.fromtimestamp(position.entry_tstamp).isoformat(),
                    position.filled_entry,
                    "",
                    self.bars[0].close,
                    position.exit_equity
                ])

def export_backtest_metrics_to_csv(bt, filepath, append=True):
    """
    Write bt.metrics to CSV. If append=True and file exists, append a row.
    If file does not exist, write header + row.
    """
    if not getattr(bt, "metrics", None):
        return#raise ValueError("BackTest has no metrics to export. Did you run bt.run()?")

    metrics = bt.metrics
    file_exists = os.path.isfile(filepath)

    mode = "a" if append and file_exists else "w"
    with open(filepath, mode, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(metrics.keys()))
        if not file_exists or not append:
            writer.writeheader()
        writer.writerow(metrics)

def export_backtest_metrics_to_json(bt, filepath):
    """
    Write bt.metrics to JSON (one object).
    """
    if not getattr(bt, "metrics", None):
        return#raise ValueError("BackTest has no metrics to export. Did you run bt.run()?")

    with open(filepath, "w") as f:
        json.dump(bt.metrics, f, indent=2)
