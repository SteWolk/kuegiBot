from typing import List

from kuegi_bot.bots.strategies.strat_with_exit_modules import StrategyWithExitModulesAndFilter
from kuegi_bot.bots.trading_bot import TradingBot, PositionDirection
from kuegi_bot.utils.trading_classes import Bar, Account, Symbol, OrderType, Position, Order, PositionStatus


class StrategyTwo(StrategyWithExitModulesAndFilter):
    """
    Mean-reversion StrategyTwo implementation focused on "fast spike reversal" with a 3-factor quality score.

    Score factors:
      - spike quality into level
      - volume not increasing into level
      - left-side structure not staircase/trending
    """

    def __init__(self,
                 lookback: int = 24,
                 level_lookback: int = 55,
                 spike_threshold: float = 0.012,
                 volume_spike_factor: float = 1.4,
                 max_staircase_slope: float = 0.008,
                 min_quality_score: int = 2,
                 sl_buffer: float = 0.003,
                 tp_factor: float = 0.8,
                 max_positions: int = 20):
        super().__init__()
        self.lookback = lookback
        self.level_lookback = level_lookback
        self.spike_threshold = spike_threshold
        self.volume_spike_factor = volume_spike_factor
        self.max_staircase_slope = max_staircase_slope
        self.min_quality_score = min_quality_score
        self.sl_buffer = sl_buffer
        self.tp_factor = tp_factor
        self.max_positions = max_positions

    def myId(self):
        return "strategyTwo"

    def init(self, bars: List[Bar], account: Account, symbol: Symbol):
        super().init(bars, account, symbol)
        self.logger.info("StrategyTwo initialized")

    def min_bars_needed(self) -> int:
        return max(self.lookback + 5, self.level_lookback + 5)

    def got_data_for_position_sync(self, bars: List[Bar]) -> bool:
        return super().got_data_for_position_sync(bars)

    def prep_bars(self, is_new_bar: bool, bars: list):
        pass

    @staticmethod
    def _avg(values: List[float]) -> float:
        if not values:
            return 0.0
        return sum(values) / len(values)

    def _calc_quality(self, bars: List[Bar], is_long: bool):
        # bars[1] is the last closed bar in this framework
        current = bars[1]
        prev = bars[2]

        # F1: fast spike into level
        ret = (current.close - prev.close) / max(prev.close, 1e-9)
        spike_mag = abs(ret)
        f1_spike = spike_mag >= self.spike_threshold

        # F2: volume context (prefer non-rising volume, but allow spike confirmation)
        vol_window = [b.volume for b in bars[2:2 + self.lookback]]
        avg_vol = max(self._avg(vol_window), 1e-9)
        # if the latest bar is huge spike, we still want the prior structure mostly flat/non-rising
        prior_window = [b.volume for b in bars[3:3 + min(6, self.lookback - 1)]]
        prior_avg = self._avg(prior_window)
        f2_volume = (current.volume >= avg_vol * self.volume_spike_factor) and (prior_avg <= avg_vol * 1.05)

        # F3: left-side structure choppy vs staircase using slope of means over windows
        left = bars[2:2 + self.lookback]
        half = max(2, len(left) // 2)
        newer = self._avg([b.close for b in left[:half]])
        older = self._avg([b.close for b in left[half:]])
        slope = abs((newer - older) / max(older, 1e-9))
        f3_structure = slope <= self.max_staircase_slope

        # level touch
        # Use only *prior* bars for level calculation to avoid look-ahead bias.
        # bars[1] is the current closed signal bar, so levels must start at bars[2].
        lvl_window = bars[2:2 + self.level_lookback]
        support = min(b.low for b in lvl_window)
        resistance = max(b.high for b in lvl_window)
        touches_level = current.low <= support * 1.001 if is_long else current.high >= resistance * 0.999

        # directional trigger
        direction_ok = (current.close > prev.close) if is_long else (current.close < prev.close)

        score = int(f1_spike) + int(f2_volume) + int(f3_structure)
        return {
            "score": score,
            "touches_level": touches_level,
            "direction_ok": direction_ok,
            "support": support,
            "resistance": resistance,
            "current": current,
            "ret": ret,
        }

    def _upsert_bracket_orders(self, position: Position, account: Account):
        got_tp = False
        got_sl = False
        for order in account.open_orders:
            order_type = TradingBot.order_type_from_order_id(order.id)
            pos_id = TradingBot.position_id_from_order_id(order.id)
            if pos_id != position.id:
                continue
            if order_type == OrderType.TP:
                got_tp = True
                wanted_amount = self.symbol.normalizeSize(-position.current_open_amount + order.executed_amount)
                if abs(order.amount - wanted_amount) > self.symbol.lotSize / 2:
                    order.amount = wanted_amount
                    self.order_interface.update_order(order)
            elif order_type == OrderType.SL:
                got_sl = True
                wanted_amount = self.symbol.normalizeSize(-position.current_open_amount)
                if abs(order.amount - wanted_amount) > self.symbol.lotSize / 2:
                    order.amount = wanted_amount
                    self.order_interface.update_order(order)

        if not got_tp:
            sl_diff = position.wanted_entry - position.initial_stop
            tp = self.symbol.normalizePrice(position.wanted_entry + sl_diff * self.tp_factor, position.amount > 0)
            self.order_interface.send_order(
                Order(orderId=TradingBot.generate_order_id(position.id, OrderType.TP),
                      amount=-position.current_open_amount,
                      trigger=None,
                      limit=tp)
            )

        if not got_sl:
            self.order_interface.send_order(
                Order(orderId=TradingBot.generate_order_id(position.id, OrderType.SL),
                      amount=-position.current_open_amount,
                      trigger=position.initial_stop,
                      limit=None)
            )

    def position_got_opened_or_changed(self, position: Position, bars: List[Bar], account: Account, open_positions):
        self._upsert_bracket_orders(position, account)

    def manage_open_position(self, p, bars, account, pos_ids_to_cancel):
        pass

    def open_new_trades(self, is_new_bar, directionFilter, bars, account, open_positions, all_open_pos: dict):
        if not is_new_bar or len(bars) < self.min_bars_needed():
            return

        if not self.entries_allowed(bars):
            return

        if len(all_open_pos) >= self.max_positions:
            return

        expected_exit_slip = 0.0015

        # keep only one position per direction for this strategy
        has_long = any(p.amount > 0 and p.status in [PositionStatus.PENDING, PositionStatus.OPEN, PositionStatus.TRIGGERED]
                       for p in open_positions.values())
        has_short = any(p.amount < 0 and p.status in [PositionStatus.PENDING, PositionStatus.OPEN, PositionStatus.TRIGGERED]
                        for p in open_positions.values())

        l = self._calc_quality(bars, is_long=True)
        s = self._calc_quality(bars, is_long=False)

        if (not has_long
                and l["score"] >= self.min_quality_score
                and l["touches_level"]
                and l["direction_ok"]):
            entry = self.symbol.normalizePrice(bars[0].open, False)
            stop = self.symbol.normalizePrice(min(l["current"].low, l["support"]) * (1 - self.sl_buffer), True)
            amount = self.calc_pos_size(self.risk_factor, entry=entry, exitPrice=stop * (1 - expected_exit_slip))
            if amount > 0:
                pos_id = TradingBot.full_pos_id(self.get_signal_id(bars, self.myId()), PositionDirection.LONG)
                open_positions[pos_id] = Position(id=pos_id, entry=entry, amount=amount, stop=stop, tstamp=bars[0].tstamp)
                self.order_interface.send_order(Order(orderId=TradingBot.generate_order_id(pos_id, OrderType.ENTRY),
                                                    amount=amount, limit=entry))

        if (not has_short
                and s["score"] >= self.min_quality_score
                and s["touches_level"]
                and s["direction_ok"]):
            entry = self.symbol.normalizePrice(bars[0].open, True)
            stop = self.symbol.normalizePrice(max(s["current"].high, s["resistance"]) * (1 + self.sl_buffer), False)
            amount = self.calc_pos_size(self.risk_factor, entry=entry, exitPrice=stop * (1 + expected_exit_slip))
            if amount < 0:
                pos_id = TradingBot.full_pos_id(self.get_signal_id(bars, self.myId()), PositionDirection.SHORT)
                open_positions[pos_id] = Position(id=pos_id, entry=entry, amount=amount, stop=stop, tstamp=bars[0].tstamp)
                self.order_interface.send_order(Order(orderId=TradingBot.generate_order_id(pos_id, OrderType.ENTRY),
                                                    amount=amount, limit=entry))
