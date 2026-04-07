import math
from functools import reduce
from random import randint

import plotly.graph_objects as go
from kuegi_bot.bots.trading_bot import TradingBot
from kuegi_bot.utils.trading_classes import Position, Account, Bar, Symbol
from kuegi_bot.utils.telegram import TelegramBot
from typing import List


class Strategy:
    def __init__(self):
        self.logger = None
        self.order_interface = None
        self.symbol = None
        self.risk_factor = 1
        self.risk_type = 0  # 0= all equal, 1= 1 atr eq 1 R
        self.atr_factor_risk = 1
        self.max_risk_mul = 1
        self.telegram: TelegramBot = None
        self._signal_prefix = None
        self._backtest_bars = None

    def myId(self):
        return "gen"

    def get_signal_id(self, bars: List[Bar], sigId=None):
        delta = bars[0].tstamp - bars[1].tstamp

        timepart = f"{self.symbol.symbol}.{int((bars[0].tstamp / delta) % 0xFFF):0>3x}.{randint(0, 0xFFF):0>3x}"
        if sigId is None:
            sigId = self.myId()
        return sigId + "+" + timepart

    def prepare(self, logger, order_interface):
        self.logger = logger
        self.order_interface = order_interface

    def init(self, bars: List[Bar], account: Account, symbol: Symbol):
        self.symbol = symbol

    def set_backtest_bars(self, bars: List[Bar]):
        self._backtest_bars = bars

    def min_bars_needed(self) -> int:
        return 5

    def owns_signal_id(self, signalId: str):
        if self._signal_prefix is None:
            self._signal_prefix = self.myId() + "+"
        return signalId.startswith(self._signal_prefix)

    def got_data_for_position_sync(self, bars: List[Bar]) -> bool:
        raise NotImplementedError

    def get_stop_for_unmatched_amount(self, amount: float, bars: List[Bar]):
        return None

    def prep_bars(self, is_new_bar: bool, bars: list):
        pass

    def position_got_opened_or_changed(self, position: Position, bars: List[Bar], account: Account, open_positions):
        pass

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        pass

    def manage_open_position(self, p, bars, account, pos_ids_to_cancel):
        pass

    def open_new_trades(self, is_new_bar, directionFilter, bars, account, open_positions_of_strat: dict, all_open_pos: dict):
        pass

    def consolidate_positions(self, is_new_bar, bars, account, open_positions_of_strat: dict):
        pass

    def add_to_price_data_plot(self, fig: go.Figure, bars: List[Bar], time):
        pass

    def add_to_normalized_plot(self, fig: go.Figure, bars: List[Bar], time):
        pass

    def with_telegram(self, telegram: TelegramBot):
        self.telegram = telegram

    def withRM(self, risk_factor: float = 0.01, max_risk_mul: float = 2, risk_type: int = 0, atr_factor: float = 1):
        self.risk_factor = risk_factor
        self.risk_type = risk_type  # 0= all equal, 1= 1 atr eq 1 R
        self.max_risk_mul = max_risk_mul
        self.atr_factor_risk = atr_factor
        return self

    def calc_pos_size(self, risk, entry, exitPrice, atr: float = 0):
        if self.risk_type <= 2:
            delta = entry - exitPrice
            if self.risk_type == 1:
                # use atr as delta reference, but max X the actual delta. so risk is never more than X times the
                # wanted risk
                delta = math.copysign(max(abs(delta) / self.max_risk_mul, atr * self.atr_factor_risk), delta)

            if not self.symbol.isInverse:
                size = risk / delta
            else:
                size = -risk / (1 / entry - 1 / (entry - delta))
            size = self.symbol.normalizeSize(size)
            return size


class MultiStrategyBot(TradingBot):

    def __init__(self, logger=None, directionFilter=0):
        super().__init__(logger, directionFilter)
        self.myId = "MultiStrategy"
        self.strategies: List[Strategy] = []
        self._strat_by_prefix = {}

    def add_strategy(self, strategy: Strategy):
        self.strategies.append(strategy)
        self._strat_by_prefix[strategy.myId() + "+"] = strategy

    @staticmethod
    def _signal_prefix(signal_id: str):
        plus_index = signal_id.find("+")
        if plus_index < 0:
            return None
        return signal_id[:plus_index + 1]

    def _strategy_for_position_id(self, position_id: str):
        signal_id, _direction = self.split_pos_Id(position_id)
        prefix = self._signal_prefix(signal_id)
        if prefix is None:
            return None
        return self._strat_by_prefix.get(prefix)

    def set_backtest_bars(self, bars: List[Bar]):
        super().set_backtest_bars(bars)
        for strat in self.strategies:
            strat.set_backtest_bars(bars)

    def prepare(self, logger, order_interface):
        super().prepare(logger, order_interface)
        for strat in self.strategies:
            strat.prepare(logger, order_interface)

    def init(self, bars: List[Bar], account: Account, symbol: Symbol, unique_id: str = ""):
        strategy_names = reduce(
            lambda result, strategy: result + ", " + strategy.myId(),
            self.strategies,
            "",
        )
        self.logger.info("init with strategies: %s" % strategy_names)
        for strat in self.strategies:
            strat.init(bars, account, symbol)
        super().init(bars=bars, account=account, symbol=symbol, unique_id=unique_id)

    def min_bars_needed(self):
        if len(self.strategies) == 0:
            return 5
        max_needed = 5
        for strategy in self.strategies:
            bars_needed = strategy.min_bars_needed()
            if bars_needed > max_needed:
                max_needed = bars_needed
        return max_needed

    def prep_bars(self, bars: list):
        newbar = self.is_new_bar
        #if not self.got_data_for_position_sync(bars):
        #    newbar = True
        for strategy in self.strategies:
            strategy.prep_bars(newbar, bars)

    def got_data_for_position_sync(self, bars: List[Bar]):
        for strategy in self.strategies:
            if not strategy.got_data_for_position_sync(bars):
                return False
        return True

    def position_got_opened_or_changed(self, position: Position, bars: List[Bar], account: Account):
        strat = self._strategy_for_position_id(position.id)
        if strat is not None:
            def on_position_change(open_pos, _all_pos):
                strat.position_got_opened_or_changed(position, bars, account, open_pos)

            self.call_with_open_positions_for_strat(strat, on_position_change)

    def get_stop_for_unmatched_amount(self, amount: float, bars: List[Bar]):
        if len(self.strategies) == 1:
            return self.strategies[0].get_stop_for_unmatched_amount(amount, bars)
        return None

    def call_with_open_positions_for_strat(self, strat, call):
        if len(self.strategies) == 1 and self.strategies[0] is strat:
            target_prefix = strat.myId() + "+"
            all_match = True
            for pos in self.open_positions.values():
                signalId, _direction = self.split_pos_Id(pos.id)
                if not signalId.startswith(target_prefix):
                    all_match = False
                    break
            if all_match:
                call(self.open_positions, self.open_positions)
                return

        open_pos = {}
        pos_ids = set()
        target_prefix = strat.myId() + "+"
        for pos in self.open_positions.values():
            signalId, _direction = self.split_pos_Id(pos.id)
            if signalId.startswith(target_prefix):
                open_pos[pos.id] = pos
                pos_ids.add(pos.id)

        call(open_pos, self.open_positions)
        for pos in open_pos.values():
            pos_ids.discard(pos.id)
            self.open_positions[pos.id] = pos
        for canceled_id in pos_ids:
            del self.open_positions[canceled_id]

    def manage_active_trades(self, bars: List[Bar], account: Account):
        self.sync_executions(bars, account)

        to_cancel = []
        to_update = []
        strat_ctx = {}

        def get_ctx(strat):
            ctx = strat_ctx.get(strat)
            if ctx is not None:
                return ctx

            open_pos = {}
            pos_ids = set()

            split_pos = self.split_pos_Id
            owns = strat.owns_signal_id

            for pos in self.open_positions.values():
                signalId, _direction = split_pos(pos.id)
                if owns(signalId):
                    open_pos[pos.id] = pos
                    pos_ids.add(pos.id)

            strat_ctx[strat] = (open_pos, pos_ids)
            return open_pos, pos_ids

        for order in account.open_orders:
            posId = self.position_id_from_order_id(order.id)
            if posId not in self.open_positions:
                continue
            strat = self._strategy_for_position_id(posId)
            if strat is not None:
                open_pos, _pos_ids = get_ctx(strat)
                strat.manage_open_order(
                    order,
                    self.open_positions[posId],
                    bars,
                    to_update,
                    to_cancel,
                    open_pos,
                )

        # Write back changes and handle deletions in a single flush per strategy
        for strat, (open_pos, pos_ids) in strat_ctx.items():
            # Update/add positions
            for pos in open_pos.values():
                self.open_positions[pos.id] = pos
                pos_ids.discard(pos.id)

            # Remove canceled positions
            for canceled_id in pos_ids:
                if canceled_id in self.open_positions:
                    del self.open_positions[canceled_id]

        for order in to_cancel:
            self.order_interface.cancel_order(order)

        for order in to_update:
            self.order_interface.update_order(order)

        pos_ids_to_cancel = []
        for p in self.open_positions.values():
            strat = self._strategy_for_position_id(p.id)
            if strat is not None:
                strat.manage_open_position(p, bars, account, pos_ids_to_cancel)

        for posId in pos_ids_to_cancel:
            self.cancel_all_orders_for_position(posId, account)
            if posId in self.open_positions:
                del self.open_positions[posId]

    def open_new_trades(self, bars: List[Bar], account: Account):
        for strat in self.strategies:
            def run_new_entries(open_pos, all_open_pos):
                strat.open_new_trades(
                    self.is_new_bar,
                    self.directionFilter,
                    bars,
                    account,
                    open_pos,
                    all_open_pos,
                )

            self.call_with_open_positions_for_strat(strat, run_new_entries)

    def consolidate_open_positions(self, bars: List[Bar], account: Account):
        for strat in self.strategies:
            def run_consolidation(open_pos, _all_open_pos):
                strat.consolidate_positions(self.is_new_bar, bars, account, open_pos)

            self.call_with_open_positions_for_strat(strat, run_consolidation)

    def add_to_price_data_plot(self, fig: go.Figure, bars: List[Bar], time):
        super().add_to_price_data_plot(fig, bars, time)
        for strat in self.strategies:
            strat.add_to_price_data_plot(fig, bars, time)

    def add_to_normalized_plot(self, fig: go.Figure, bars: List[Bar], time):
        super().add_to_normalized_plot(fig, bars, time)
        for strat in self.strategies:
            strat.add_to_normalized_plot(fig, bars, time)
