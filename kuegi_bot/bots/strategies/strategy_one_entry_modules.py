from dataclasses import dataclass
from typing import Any, Callable, List

from kuegi_bot.bots.strategies.strategy_one_entry_context import StrategyOneEntryContext
from kuegi_bot.bots.strategies.strategy_one_entry_levels import calc_entry_and_exit
from kuegi_bot.bots.strategies.trend_enums import MarketDynamic
from kuegi_bot.bots.trading_bot import PositionDirection


@dataclass
class EntryExecutionContext:
    strategy: Any
    bars: list
    account: Any
    open_positions: dict
    direction_filter: int
    entry_context: StrategyOneEntryContext
    longed: bool = False
    shorted: bool = False


def _len_at_least(series, n: int) -> bool:
    return series is not None and len(series) >= n


class EntryModule:
    name = "entry_module"

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        return True

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        return True

    def run(self, ctx: EntryExecutionContext) -> None:
        raise NotImplementedError


class CallableEntryModuleAdapter(EntryModule):
    def __init__(self, fn: Callable, name: str = None):
        self._fn = fn
        self.name = name or getattr(fn, "__name__", fn.__class__.__name__)

    def run(self, ctx: EntryExecutionContext) -> None:
        longed, shorted = self._fn(
            strategy=ctx.strategy,
            bars=ctx.bars,
            account=ctx.account,
            open_positions=ctx.open_positions,
            directionFilter=ctx.direction_filter,
            entry_context=ctx.entry_context,
            longed=ctx.longed,
            shorted=ctx.shorted,
        )
        ctx.longed = longed
        ctx.shorted = shorted


class ObjectEntryModuleAdapter(EntryModule):
    def __init__(self, obj: Any, name: str):
        self._obj = obj
        self.name = name

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        if hasattr(self._obj, "enabled"):
            return self._obj.enabled(ctx)
        return True

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        if hasattr(self._obj, "is_ready"):
            return self._obj.is_ready(ctx)
        return True

    def run(self, ctx: EntryExecutionContext) -> None:
        self._obj.run(ctx)


def module_name(module: Any) -> str:
    name = getattr(module, "name", None)
    if isinstance(name, str) and len(name) > 0:
        return name
    return module.__class__.__name__


def as_entry_module(module: Any) -> EntryModule:
    if isinstance(module, EntryModule):
        return module
    if callable(module) and not hasattr(module, "run"):
        return CallableEntryModuleAdapter(module)
    if hasattr(module, "run"):
        return ObjectEntryModuleAdapter(module, module_name(module))
    raise TypeError("Entry module must be callable or provide run(ctx)")


class Entry1Module(EntryModule):
    name = "entry_1"

    def __init__(self, active=None, entry_1_atr_fac: float = 1, entry_1_vol_fac: float = 2.0):
        self.active = active
        self.entry_1_atr_fac = entry_1_atr_fac
        self.entry_1_vol_fac = entry_1_vol_fac

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        active = bool(self.active)
        return active and not ctx.shorted and ctx.strategy.shortsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        talibbars = ctx.entry_context.talibbars
        return (
            _len_at_least(ctx.bars, 1)
            and _len_at_least(talibbars.close_daily, 1)
            and _len_at_least(talibbars.open_daily, 1)
            and _len_at_least(talibbars.high_daily, 1)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.highs_trail_4h_vec, 7)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.volume_sma_4h_vec, 1)
            and ctx.strategy.ta_data_trend_strat.volume_4h is not None
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        talibbars = ctx.entry_context.talibbars
        condition_1 = talibbars.close_daily[-1] < talibbars.open_daily[-1]
        condition_2 = (
            talibbars.high_daily[-1] > ctx.strategy.ta_data_trend_strat.highs_trail_4h_vec[-6]
            or talibbars.high_daily[-1] > ctx.strategy.ta_data_trend_strat.highs_trail_4h_vec[-7]
        )
        condition_3 = ctx.entry_context.market_bearish
        condition_4 = (
            ctx.strategy.ta_data_trend_strat.volume_sma_4h_vec[-1] * self.entry_1_vol_fac
            < ctx.strategy.ta_data_trend_strat.volume_4h
        )
        if condition_1 and condition_2 and condition_3 and condition_4:
            ctx.strategy.logger.info("Shorting daily sfp")
            if ctx.strategy.telegram is not None:
                ctx.strategy.telegram.send_log("Shorting daily sfp")
            ctx.strategy.open_new_position(
                entry=ctx.bars[0].close,
                stop=ctx.bars[0].close + ctx.entry_context.atr_trail_mix * self.entry_1_atr_fac,
                open_positions=ctx.open_positions,
                bars=ctx.bars,
                direction=PositionDirection.SHORT,
                ExecutionType="Market",
            )


class Entry10Module(EntryModule):
    name = "entry_10"

    def __init__(self, active=None, entry_10_natr: float = 2, entry_10_natr_ath: float = 2, entry_10_rsi_4h: int = 50):
        self.active = active
        self.entry_10_natr = entry_10_natr
        self.entry_10_natr_ath = entry_10_natr_ath
        self.entry_10_rsi_4h = entry_10_rsi_4h

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        active = bool(self.active)
        return active and not ctx.longed and ctx.strategy.longsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        return (
            _len_at_least(ctx.bars, 5)
            and _len_at_least(ctx.entry_context.talibbars.close, 1)
            and _len_at_least(ctx.strategy.ta_strat_one.taData_strat_one.h_highs_trail_vec, 2)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.rsi_4h_vec, 1)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.volume_sma_4h_vec, 1)
            and ctx.strategy.ta_data_trend_strat.rsi_d is not None
            and ctx.entry_context.natr_4h is not None
            and ctx.strategy.ta_data_trend_strat.volume_4h is not None
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        closes = ctx.entry_context.talibbars.close
        ath = closes[-1] == max(closes)
        condition_1 = ctx.bars[1].close > ctx.strategy.ta_strat_one.taData_strat_one.h_highs_trail_vec[-2]
        condition_2 = ctx.entry_context.natr_4h < self.entry_10_natr
        condition_2b = ctx.entry_context.natr_4h < self.entry_10_natr_ath
        condition_3 = ctx.strategy.ta_data_trend_strat.rsi_4h_vec[-1] < self.entry_10_rsi_4h
        condition_4 = not ctx.entry_context.market_bearish
        condition_5 = ctx.bars[1].close - ctx.bars[1].open > ctx.bars[2].close - ctx.bars[2].open
        condition_6 = ctx.bars[1].open > ctx.bars[4].close
        condition_7 = ctx.strategy.ta_data_trend_strat.rsi_d > 50
        condition_8 = not ctx.entry_context.market_trending
        condition_9 = ctx.strategy.ta_data_trend_strat.volume_sma_4h_vec[-1] * 2.6 > ctx.strategy.ta_data_trend_strat.volume_4h
        conditions_set_1 = (
            condition_1 and condition_2 and condition_3 and condition_4
            and condition_5 and condition_7 and condition_8 and condition_9
        )
        conditions_set_2 = condition_1 and condition_2b and ath and condition_3 and condition_4 and condition_6
        if conditions_set_1 or conditions_set_2:
            ctx.longed = True
            ctx.strategy.logger.info("Longing confirmed trail breakout.")
            if ctx.strategy.telegram is not None:
                ctx.strategy.telegram.send_log("Longing confirmed trail breakout.")
            ctx.strategy.open_new_position(
                entry=ctx.bars[0].close,
                stop=ctx.bars[1].low - ctx.entry_context.atr * 0.2,
                open_positions=ctx.open_positions,
                bars=ctx.bars,
                direction=PositionDirection.LONG,
                ExecutionType="Market",
            )
            ctx.strategy.logger.info("Sending additional long.")
            if ctx.strategy.telegram is not None:
                ctx.strategy.telegram.send_log("Sending additional long.")
            entry = ctx.bars[0].close - 0.2 * ctx.entry_context.atr
            ctx.strategy.open_new_position(
                entry=entry,
                stop=entry - ctx.entry_context.atr_min,
                open_positions=ctx.open_positions,
                bars=ctx.bars,
                direction=PositionDirection.LONG,
                ExecutionType="Limit",
            )


class Entry2Module(EntryModule):
    name = "entry_2"

    def __init__(
        self,
        active=None,
        entry_2_max_natr: float = 1,
        entry_2_min_rsi_4h: int = 50,
        entry_2_min_rsi_d: int = 80,
        entry_2_min_natr: float = 1,
        entry_2_min_rsi_4h_short: int = 50,
        entry_2_min_rsi_d_short: int = 50,
    ):
        self.active = active
        self.entry_2_max_natr = entry_2_max_natr
        self.entry_2_min_rsi_4h = entry_2_min_rsi_4h
        self.entry_2_min_rsi_d = entry_2_min_rsi_d
        self.entry_2_min_natr = entry_2_min_natr
        self.entry_2_min_rsi_4h_short = entry_2_min_rsi_4h_short
        self.entry_2_min_rsi_d_short = entry_2_min_rsi_d_short

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        active = bool(self.active)
        return active

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        return (
            _len_at_least(ctx.bars, 45)
            and _len_at_least(ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_4h_vec, 1)
            and ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_d is not None
            and ctx.entry_context.natr_4h is not None
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        longEntry, shortEntry, stopLong, stopShort, longAmount, shortAmount, alreadyLonged, alreadyShorted = calc_entry_and_exit(ctx.strategy, ctx.bars)
        if longEntry is not None and shortEntry is not None:
            condition_1 = ctx.entry_context.natr_4h < self.entry_2_max_natr
            condition_2 = ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_4h_vec[-1] < self.entry_2_min_rsi_4h
            condition_3 = ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_d > self.entry_2_min_rsi_d
            condition_8 = not ctx.entry_context.market_bearish
            condition_9 = not ctx.entry_context.market_trending
            bullish_conditions = condition_1 and condition_2 and condition_3 and condition_8 and condition_9
            bearish_conditions = False
            foundLong = False
            foundShort = False
            if bullish_conditions or bearish_conditions:
                foundLong, foundShort = ctx.strategy.update_existing_entries(
                    ctx.account, ctx.open_positions, longEntry, shortEntry, stopLong, stopShort, longAmount, shortAmount
                )
            if not foundLong and ctx.strategy.longsAllowed and ctx.direction_filter >= 0 and bullish_conditions:
                ctx.strategy.open_new_position(PositionDirection.LONG, ctx.bars, stopLong, ctx.open_positions, longEntry, "StopLimit")
                if ctx.strategy.telegram is not None:
                    ctx.strategy.telegram.send_log("Entry strategy 2: Sending long StopLimit entry order.")
            if not foundShort and ctx.strategy.shortsAllowed and ctx.direction_filter <= 0 and shortEntry is not None and bearish_conditions:
                ctx.strategy.open_new_position(PositionDirection.SHORT, ctx.bars, stopShort, ctx.open_positions, shortEntry, "StopLimit")
                if ctx.strategy.telegram is not None:
                    ctx.strategy.telegram.send_log("Entry strategy 2: Sending short StopLimit entry order.")


class Entry3Module(EntryModule):
    name = "entry_3"

    def __init__(self, active=None, entry_3_max_natr: float = 2, entry_3_rsi_4h: int = 50, entry_3_atr_fac: float = 1, entry_3_vol_fac: float = 2.0):
        self.active = active
        self.entry_3_max_natr = entry_3_max_natr
        self.entry_3_rsi_4h = entry_3_rsi_4h
        self.entry_3_atr_fac = entry_3_atr_fac
        self.entry_3_vol_fac = entry_3_vol_fac

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        active = bool(self.active)
        return active and not ctx.longed and ctx.strategy.longsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        return (
            _len_at_least(ctx.bars, 2)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.highs_trail_4h_vec, 2)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.rsi_4h_vec, 1)
            and ctx.strategy.ta_data_trend_strat.rsi_d is not None
            and ctx.entry_context.natr_4h is not None
            and ctx.entry_context.std is not None
            and ctx.entry_context.atr is not None
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        condition_1 = ctx.bars[1].high > ctx.strategy.ta_data_trend_strat.highs_trail_4h_vec[-2]
        condition_3 = ctx.strategy.ta_data_trend_strat.rsi_4h_vec[-1] > self.entry_3_rsi_4h
        condition_4 = ctx.strategy.ta_data_trend_strat.rsi_d > 50
        condition_5 = ctx.bars[1].open > ctx.bars[1].close
        condition_8 = not ctx.entry_context.market_trending
        condition_9 = self.entry_3_max_natr > ctx.entry_context.natr_4h
        condition_10 = ctx.entry_context.std < 4 * ctx.entry_context.atr
        if condition_1 and condition_5 and ctx.entry_context.market_bullish and condition_3 and condition_4 and condition_8 and condition_9 and condition_10:
            ctx.longed = True
            ctx.strategy.logger.info("Longing trail break pullback.")
            if ctx.strategy.telegram is not None:
                ctx.strategy.telegram.send_log("Longing trail break pullback.")
            entry = ctx.bars[0].close - self.entry_3_atr_fac * ctx.entry_context.atr
            sl = entry - ctx.entry_context.atr
            ctx.strategy.open_new_position(
                entry=entry,
                stop=sl,
                open_positions=ctx.open_positions,
                bars=ctx.bars,
                direction=PositionDirection.LONG,
                ExecutionType="Limit",
            )


class Entry14Module(EntryModule):
    name = "entry_14"

    def __init__(self, active=None):
        self.active = active

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        active = bool(self.active)
        return active and not ctx.longed and ctx.strategy.longsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        return (
            _len_at_least(ctx.bars, 2)
            and _len_at_least(ctx.strategy.ta_strat_one.taData_strat_one.h_highs_trail_vec, 2)
            and _len_at_least(ctx.strategy.ta_strat_one.taData_strat_one.h_lows_trail_vec, 1)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.rsi_4h_vec, 1)
            and ctx.strategy.ta_data_trend_strat.rsi_d is not None
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        condition_1 = ctx.bars[1].high > ctx.strategy.ta_strat_one.taData_strat_one.h_highs_trail_vec[-2] > ctx.bars[1].close
        condition_3 = ctx.strategy.ta_data_trend_strat.rsi_4h_vec[-1] > 60
        condition_4 = ctx.strategy.ta_data_trend_strat.rsi_d > 0
        limit = (
            ctx.strategy.ta_strat_one.taData_strat_one.h_lows_trail_vec[-1]
            + 0.7 * (
                ctx.strategy.ta_strat_one.taData_strat_one.h_highs_trail_vec[-1]
                - ctx.strategy.ta_strat_one.taData_strat_one.h_lows_trail_vec[-1]
            )
        )
        condition_5 = ctx.bars[1].close < limit
        if condition_1 and condition_3 and condition_4 and condition_5 and ctx.entry_context.market_bullish:
            ctx.longed = True
            ctx.strategy.logger.info("Longing trail breakout by limit order.")
            if ctx.strategy.telegram is not None:
                ctx.strategy.telegram.send_log("Longing trail breakout by limit order.")
            entry = ctx.bars[0].close
            sl = entry - 1.2 * ctx.entry_context.atr
            ctx.strategy.open_new_position(
                entry=entry,
                stop=sl,
                open_positions=ctx.open_positions,
                bars=ctx.bars,
                direction=PositionDirection.LONG,
                ExecutionType="Market",
            )


class Entry4Module(EntryModule):
    name = "entry_4"

    def __init__(self, active=None, entry_4_std_fac: float = 1, entry_4_std_fac_reclaim: float = 1):
        self.active = active
        self.entry_4_std_fac = entry_4_std_fac
        self.entry_4_std_fac_reclaim = entry_4_std_fac_reclaim

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        active = bool(self.active)
        return active

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        return (
            _len_at_least(ctx.bars, 2)
            and _len_at_least(ctx.entry_context.middleband_vec, 2)
            and _len_at_least(ctx.entry_context.std_vec, 2)
            and ctx.entry_context.range_limit > 1
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        sold_off_bband = False
        upper = min(ctx.entry_context.range_limit, len(ctx.bars))
        for i in range(1, upper, 1):
            sell_off_level = ctx.entry_context.middleband_vec[-i] - ctx.entry_context.std_vec[-i] * self.entry_4_std_fac
            reclaim_level = sell_off_level + ctx.entry_context.std_vec[-i] * self.entry_4_std_fac_reclaim
            if ctx.bars[i].close > reclaim_level and i > 1:
                sold_off_bband = False
                break
            if ctx.bars[i].close <= sell_off_level:
                sold_off_bband = True
                break
        if sold_off_bband:
            sell_off_level = ctx.entry_context.middleband_vec[-1] - ctx.entry_context.std_vec[-1] * self.entry_4_std_fac
            reclaim_level = sell_off_level + ctx.entry_context.std_vec[-1] * self.entry_4_std_fac_reclaim
            condition_1 = ctx.bars[1].close > reclaim_level
            if condition_1 and not ctx.longed and ctx.strategy.longsAllowed:
                ctx.longed = True
                ctx.strategy.logger.info("Longing bollinger bands reclaim 1.")
                if ctx.strategy.telegram is not None:
                    ctx.strategy.telegram.send_log("Longing bollinger bands reclaim 1.")
                ctx.strategy.open_new_position(
                    entry=ctx.bars[0].close,
                    stop=ctx.bars[0].close - ctx.strategy.sl_atr_fac * ctx.entry_context.atr_trail_mix,
                    open_positions=ctx.open_positions,
                    bars=ctx.bars,
                    direction=PositionDirection.LONG,
                    ExecutionType="Market",
                )


class Entry5Module(EntryModule):
    name = "entry_5"

    def __init__(
        self,
        active=None,
        entry_5_rsi_d: int = 40,
        entry_5_rsi_4h: int = 80,
        entry_5_atr_fac: float = 0.8,
        entry_5_trail_1_period: int = 10,
        entry_5_trail_2_period: int = 10,
        entry_5_vol_fac: float = 2.0,
    ):
        self.active = active
        self.entry_5_rsi_d = entry_5_rsi_d
        self.entry_5_rsi_4h = entry_5_rsi_4h
        self.entry_5_atr_fac = entry_5_atr_fac
        self.entry_5_trail_1_period = entry_5_trail_1_period
        self.entry_5_trail_2_period = entry_5_trail_2_period
        self.entry_5_vol_fac = entry_5_vol_fac

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        active = bool(self.active)
        return active and not ctx.shorted and ctx.strategy.shortsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        needed = max(self.entry_5_trail_1_period, self.entry_5_trail_2_period) + 2
        return (
            _len_at_least(ctx.bars, 2)
            and _len_at_least(ctx.strategy.ta_strat_one.taData_strat_one.h_body_lows_trail_vec, needed)
            and ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_d is not None
            and _len_at_least(ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_4h_vec, 1)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.volume_sma_4h_vec, 1)
            and ctx.strategy.ta_data_trend_strat.volume_4h is not None
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        trail_broke = (
            ctx.bars[1].close
            < ctx.strategy.ta_strat_one.taData_strat_one.h_body_lows_trail_vec[-self.entry_5_trail_1_period:-2]
        ).all()
        opened_above_trail = (
            ctx.bars[1].open
            > ctx.strategy.ta_strat_one.taData_strat_one.h_body_lows_trail_vec[-self.entry_5_trail_2_period:-2]
        ).all()
        condition_2 = ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_d < self.entry_5_rsi_d
        condition_3 = ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_4h_vec[-1] < self.entry_5_rsi_4h
        condition_4 = (
            ctx.strategy.ta_data_trend_strat.volume_sma_4h_vec[-1] * self.entry_5_vol_fac
            < ctx.strategy.ta_data_trend_strat.volume_4h
        )
        if trail_broke and opened_above_trail and condition_2 and condition_3 and condition_4:
            ctx.strategy.logger.info("Shorting trail break.")
            if ctx.strategy.telegram is not None:
                ctx.strategy.telegram.send_log("Shorting trail break.")
            ctx.shorted = True
            ctx.strategy.open_new_position(
                entry=ctx.bars[0].close,
                stop=min(ctx.bars[1].high, ctx.bars[0].close + ctx.entry_context.atr_trail_mix * self.entry_5_atr_fac),
                open_positions=ctx.open_positions,
                bars=ctx.bars,
                direction=PositionDirection.SHORT,
                ExecutionType="Market",
            )


class Entry6Module(EntryModule):
    name = "entry_6"

    def __init__(self, active=None, entry_6_rsi_4h_max: int = 90, entry_6_max_natr: float = 2, entry_6_atr_fac: float = 5):
        self.active = active
        self.entry_6_rsi_4h_max = entry_6_rsi_4h_max
        self.entry_6_max_natr = entry_6_max_natr
        self.entry_6_atr_fac = entry_6_atr_fac

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        active = bool(self.active)
        return active

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        return (
            _len_at_least(ctx.bars, 44)
            and _len_at_least(ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_4h_vec, 1)
            and ctx.entry_context.natr_4h is not None
            and ctx.strategy.ta_data_trend_strat.ema_w is not None
            and ctx.entry_context.atr is not None
            and ctx.entry_context.atr_trail_mix is not None
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        depth = 40
        foundSwingHigh = False
        foundSwingLow = False
        idxSwingHigh = 0
        idxSwingLow = 0
        for i in range(3, depth):
            if ctx.bars[i + 2].close < ctx.bars[i + 1].close < ctx.bars[i].close > ctx.bars[i - 1].close:
                foundSwingHigh = True
                idxSwingHigh = i
                break
        if foundSwingHigh:
            close_values = [bar.close for bar in ctx.bars[2:idxSwingHigh]]
            alreadyLonged = any(close > ctx.bars[idxSwingHigh].high for close in close_values)
        else:
            alreadyLonged = True
        for i in range(3, depth):
            if (
                ctx.bars[i + 3].low > ctx.bars[i + 2].low > ctx.bars[i + 1].low
                > ctx.bars[i].low < ctx.bars[i - 1].low < ctx.bars[i - 2].low
            ):
                foundSwingLow = True
                idxSwingLow = i
                break
        if foundSwingLow:
            close_values = [bar.close for bar in ctx.bars[2:idxSwingLow]]
            alreadyShorted = any(close < ctx.bars[idxSwingLow].low for close in close_values)
        else:
            alreadyShorted = True
        if foundSwingHigh and foundSwingLow and not ctx.longed and not alreadyLonged and not alreadyShorted and ctx.strategy.longsAllowed:
            condition_1 = self.entry_6_rsi_4h_max > ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_4h_vec[-1] > 75
            condition_2 = ctx.entry_context.natr_4h < self.entry_6_max_natr
            condition_3 = not ctx.entry_context.market_bearish
            if ctx.bars[1].close > ctx.bars[idxSwingHigh].high and condition_2 and condition_1 and condition_3:
                ctx.strategy.logger.info("Longing swing breakout.")
                if ctx.strategy.telegram is not None:
                    ctx.strategy.telegram.send_log("Longing swing breakout.")
                ctx.longed = True
                sl = (
                    ctx.bars[1].low
                    if ctx.bars[1].close > ctx.bars[1].open
                    else ctx.bars[1].low - self.entry_6_atr_fac * ctx.entry_context.atr_trail_mix
                )
                ctx.strategy.open_new_position(
                    entry=ctx.bars[0].close,
                    stop=sl,
                    open_positions=ctx.open_positions,
                    bars=ctx.bars,
                    direction=PositionDirection.LONG,
                    ExecutionType="Market",
                )
        if foundSwingLow and foundSwingHigh and not ctx.shorted and not alreadyShorted and not alreadyLonged and ctx.strategy.shortsAllowed:
            condition_2 = ctx.bars[1].open > ctx.strategy.ta_data_trend_strat.ema_w
            condition_10 = (ctx.bars[1].high - ctx.bars[1].low) < ctx.entry_context.atr
            if ctx.bars[1].close < ctx.bars[idxSwingLow].low and condition_2 and condition_10:
                ctx.strategy.logger.info("Shorting swing break.")
                if ctx.strategy.telegram is not None:
                    ctx.strategy.telegram.send_log("Shorting swing break.")
                ctx.shorted = True
                ctx.strategy.open_new_position(
                    entry=ctx.bars[0].close,
                    stop=max(ctx.bars[1].high, ctx.bars[2].high),
                    open_positions=ctx.open_positions,
                    bars=ctx.bars,
                    direction=PositionDirection.SHORT,
                    ExecutionType="Market",
                )


class Entry7Module(EntryModule):
    name = "entry_7"

    def __init__(self, active=None, entry_7_std_fac: float = 1, entry_7_4h_rsi: float = 2.5, entry_7_vol_fac: float = 2):
        self.active = active
        self.entry_7_std_fac = entry_7_std_fac
        self.entry_7_4h_rsi = entry_7_4h_rsi
        self.entry_7_vol_fac = entry_7_vol_fac

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        active = bool(self.active)
        return active and not ctx.shorted and ctx.strategy.shortsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        return _len_at_least(ctx.bars, 4) and _len_at_least(ctx.strategy.ta_strat_one.taData_strat_one.h_highs_trail_vec, 3)

    def run(self, ctx: EntryExecutionContext) -> None:
        condition_1 = ctx.bars[2].high > ctx.bars[1].high
        condition_2 = ctx.bars[2].high > ctx.strategy.ta_strat_one.taData_strat_one.h_highs_trail_vec[-3]
        condition_3 = abs(ctx.bars[1].close - ctx.bars[1].open) > abs(ctx.bars[1].close - ctx.bars[1].low)
        condition_5 = ctx.bars[2].high - max(ctx.bars[2].close, ctx.bars[2].open) > abs(ctx.bars[2].close - ctx.bars[2].open)
        condition_10 = not ctx.entry_context.market_trending
        if condition_1 and condition_2 and condition_3 and condition_5 and condition_10:
            ctx.strategy.logger.info("Shorting 4H SFP")
            if ctx.strategy.telegram is not None:
                ctx.strategy.telegram.send_log("Shorting 4H SFP")
            ctx.shorted = True
            ctx.strategy.open_new_position(
                entry=ctx.bars[0].close,
                stop=max(ctx.bars[2].high, ctx.bars[1].high, ctx.bars[3].high),
                open_positions=ctx.open_positions,
                bars=ctx.bars,
                direction=PositionDirection.SHORT,
                ExecutionType="Market",
            )


class Entry8Module(EntryModule):
    name = "entry_8"

    def __init__(self, active=None, entry_8_vol_fac: float = 2.0):
        self.active = active
        self.entry_8_vol_fac = entry_8_vol_fac

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        active = bool(self.active)
        return active and not ctx.shorted and ctx.strategy.shortsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        return (
            _len_at_least(ctx.bars, 9)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.volume_sma_4h_vec, 1)
            and ctx.strategy.ta_data_trend_strat.volume_4h is not None
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        condition_1 = (
            ctx.bars[1].high > ctx.bars[2].high
            and ctx.bars[1].high > ctx.bars[3].high
            and ctx.bars[1].high > ctx.bars[4].high
            and ctx.bars[1].high > ctx.bars[5].close
            and ctx.bars[1].high > ctx.bars[6].close
            and ctx.bars[1].open > ctx.bars[7].close
            and ctx.bars[1].open > ctx.bars[8].close
        )
        condition_2 = (
            ctx.bars[2].close > ctx.bars[1].close
            and ctx.bars[3].close > ctx.bars[1].close
            and ctx.bars[4].close > ctx.bars[1].close
            and ctx.bars[5].close > ctx.bars[1].close
            and ctx.bars[6].close > ctx.bars[1].close
            and ctx.bars[7].close > ctx.bars[1].close
            and ctx.bars[8].close > ctx.bars[1].close
        )
        condition_4 = ctx.strategy.ta_data_trend_strat.volume_sma_4h_vec[-1] * self.entry_8_vol_fac > ctx.strategy.ta_data_trend_strat.volume_4h
        condition_6 = ctx.strategy.ta_trend_strat.taData_trend_strat.marketDynamic == MarketDynamic.RANGING
        if condition_1 and condition_2 and condition_4 and condition_6:
            ctx.strategy.logger.info("Shorting rapid sell-off")
            if ctx.strategy.telegram is not None:
                ctx.strategy.telegram.send_log("Shorting rapid sell-off")
            ctx.shorted = True
            ctx.strategy.open_new_position(
                entry=ctx.bars[0].close,
                stop=ctx.bars[1].high,
                open_positions=ctx.open_positions,
                bars=ctx.bars,
                direction=PositionDirection.SHORT,
                ExecutionType="Market",
            )


class Entry9Module(EntryModule):
    name = "entry_9"

    def __init__(self, active=None, entry_9_std: float = 1, entry_9_4h_rsi: int = 50, entry_9_atr: float = 2):
        self.active = active
        self.entry_9_std = entry_9_std
        self.entry_9_4h_rsi = entry_9_4h_rsi
        self.entry_9_atr = entry_9_atr

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        active = bool(self.active)
        return active and not ctx.shorted and ctx.strategy.shortsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        return (
            _len_at_least(ctx.bars, 3)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.lows_trail_4h_vec, 2)
            and _len_at_least(ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_4h_vec, 1)
            and _len_at_least(ctx.entry_context.middleband_vec, 2)
            and _len_at_least(ctx.entry_context.std_vec, 2)
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        condition_1 = ctx.bars[1].low < ctx.strategy.ta_data_trend_strat.lows_trail_4h_vec[-2] < ctx.bars[1].close < ctx.bars[1].open
        condition_2 = ctx.bars[1].open < ctx.bars[2].open
        condition_3 = ctx.bars[1].close > ctx.entry_context.middleband_vec[-2] - ctx.entry_context.std_vec[-2] * self.entry_9_std
        condition_5 = ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_4h_vec[-1] < self.entry_9_4h_rsi
        condition_7 = ctx.strategy.ta_trend_strat.taData_trend_strat.marketDynamic == MarketDynamic.RANGING
        if condition_1 and condition_2 and condition_3 and condition_5 and condition_7:
            ctx.strategy.logger.info("Shorting short trail tap")
            if ctx.strategy.telegram is not None:
                ctx.strategy.telegram.send_log("Shorting short trail tap")
            ctx.shorted = True
            ctx.strategy.open_new_position(
                entry=ctx.bars[0].close,
                stop=ctx.bars[1].high + self.entry_9_atr * ctx.entry_context.atr,
                open_positions=ctx.open_positions,
                bars=ctx.bars,
                direction=PositionDirection.SHORT,
                ExecutionType="Market",
            )


class Entry11Module(EntryModule):
    name = "entry_11"

    def __init__(self, active=None, entry_11_vol: float = 3.0, entry_11_atr: float = 3.0, entry_11_natr: float = 3.0):
        self.active = active
        self.entry_11_vol = entry_11_vol
        self.entry_11_atr = entry_11_atr
        self.entry_11_natr = entry_11_natr

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        active = bool(self.active)
        return active and not ctx.longed and ctx.strategy.longsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        return (
            _len_at_least(ctx.bars, 2)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.volume_sma_4h_vec, 1)
            and ctx.strategy.ta_data_trend_strat.volume_4h is not None
            and ctx.entry_context.natr_4h is not None
            and ctx.entry_context.atr is not None
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        condition_1 = ctx.strategy.ta_data_trend_strat.volume_sma_4h_vec[-1] * self.entry_11_vol > ctx.strategy.ta_data_trend_strat.volume_4h
        condition_2 = (ctx.bars[1].close - ctx.bars[1].open) > self.entry_11_atr * ctx.entry_context.atr
        condition_3 = ctx.entry_context.natr_4h < self.entry_11_natr
        if condition_1 and condition_2 and condition_3:
            ctx.strategy.logger.info("Longing momentum")
            if ctx.strategy.telegram is not None:
                ctx.strategy.telegram.send_log("Longing momentum")
            ctx.longed = True
            ctx.strategy.open_new_position(
                entry=ctx.bars[0].close,
                stop=ctx.bars[0].close - ctx.strategy.sl_atr_fac * ctx.entry_context.atr,
                open_positions=ctx.open_positions,
                bars=ctx.bars,
                direction=PositionDirection.LONG,
                ExecutionType="Market",
            )
            ctx.strategy.logger.info("Sending additional long")
            if ctx.strategy.telegram is not None:
                ctx.strategy.telegram.send_log("Sending additional long")
            entry = ctx.bars[0].close - ctx.entry_context.atr
            ctx.strategy.open_new_position(
                entry=entry,
                stop=entry - 2 * ctx.entry_context.atr_min,
                open_positions=ctx.open_positions,
                bars=ctx.bars,
                direction=PositionDirection.LONG,
                ExecutionType="Limit",
            )


class Entry12Module(EntryModule):
    name = "entry_12"

    def __init__(self, active=None, entry_12_vol: float = 3.0, entry_12_rsi_4h: int = 3, entry_12_atr: float = 3.0, entry_12_max_rsi_4h: int = 90):
        self.active = active
        self.entry_12_vol = entry_12_vol
        self.entry_12_rsi_4h = entry_12_rsi_4h
        self.entry_12_atr = entry_12_atr
        self.entry_12_max_rsi_4h = entry_12_max_rsi_4h

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        active = bool(self.active)
        return active and not ctx.longed and ctx.strategy.longsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        talibbars = ctx.entry_context.talibbars
        return (
            _len_at_least(ctx.bars, 5)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.atr_4h_vec, 4)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.volume_sma_4h_vec, 4)
            and _len_at_least(talibbars.volume, 3)
            and _len_at_least(ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_4h_vec, 1)
            and ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_d is not None
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        condition_1 = (ctx.bars[4].open - ctx.bars[4].close) > self.entry_12_atr * ctx.strategy.ta_data_trend_strat.atr_4h_vec[-4]
        condition_3 = ctx.bars[2].open < ctx.bars[4].open > ctx.bars[2].low > ctx.bars[4].low
        condition_4 = (
            ctx.bars[4].low < ctx.bars[1].low < ctx.bars[4].open > ctx.bars[1].open > ctx.bars[4].low
            and ctx.bars[4].open > ctx.bars[1].close
        )
        condition_6 = (
            self.entry_12_max_rsi_4h < ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_d
            or ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_4h_vec[-1] > self.entry_12_rsi_4h
        )
        condition_10 = ctx.strategy.ta_data_trend_strat.volume_sma_4h_vec[-4] * self.entry_12_vol > ctx.entry_context.talibbars.volume[-3]
        condition_8 = not ctx.entry_context.market_trending
        if condition_1 and condition_3 and condition_4 and condition_6 and condition_10 and condition_8:
            ctx.strategy.logger.info("Longing reversal")
            if ctx.strategy.telegram is not None:
                ctx.strategy.telegram.send_log("Longing reversal.")
            ctx.longed = True
            ctx.strategy.open_new_position(
                entry=ctx.bars[0].close,
                stop=ctx.bars[0].close - ctx.strategy.sl_atr_fac * ctx.entry_context.atr_min,
                open_positions=ctx.open_positions,
                bars=ctx.bars,
                direction=PositionDirection.LONG,
                ExecutionType="Market",
            )


def default_entry_modules(config=None) -> List[EntryModule]:
    def cfg(name, default):
        if config is None:
            return default
        if isinstance(config, dict):
            return config.get(name, default)
        return getattr(config, name, default)

    return [
        Entry1Module(active=cfg("entry_1", False), entry_1_atr_fac=cfg("entry_1_atr_fac", 1), entry_1_vol_fac=cfg("entry_1_vol_fac", 2.0)),
        Entry10Module(active=cfg("entry_10", False), entry_10_natr=cfg("entry_10_natr", 2), entry_10_natr_ath=cfg("entry_10_natr_ath", 2), entry_10_rsi_4h=cfg("entry_10_rsi_4h", 50)),
        Entry2Module(
            active=cfg("entry_2", False),
            entry_2_max_natr=cfg("entry_2_max_natr", 1),
            entry_2_min_rsi_4h=cfg("entry_2_min_rsi_4h", 50),
            entry_2_min_rsi_d=cfg("entry_2_min_rsi_d", 80),
            entry_2_min_natr=cfg("entry_2_min_natr", 1),
            entry_2_min_rsi_4h_short=cfg("entry_2_min_rsi_4h_short", 50),
            entry_2_min_rsi_d_short=cfg("entry_2_min_rsi_d_short", 50),
        ),
        Entry3Module(
            active=cfg("entry_3", False),
            entry_3_max_natr=cfg("entry_3_max_natr", 2),
            entry_3_rsi_4h=cfg("entry_3_rsi_4h", 50),
            entry_3_atr_fac=cfg("entry_3_atr_fac", 1),
            entry_3_vol_fac=cfg("entry_3_vol_fac", 2.0),
        ),
        Entry14Module(active=cfg("entry_14", False)),
        Entry4Module(active=cfg("entry_4", False), entry_4_std_fac=cfg("entry_4_std_fac", 1), entry_4_std_fac_reclaim=cfg("entry_4_std_fac_reclaim", 1)),
        Entry5Module(
            active=cfg("entry_5", False),
            entry_5_rsi_d=cfg("entry_5_rsi_d", 40),
            entry_5_rsi_4h=cfg("entry_5_rsi_4h", 80),
            entry_5_atr_fac=cfg("entry_5_atr_fac", 0.8),
            entry_5_trail_1_period=cfg("entry_5_trail_1_period", 10),
            entry_5_trail_2_period=cfg("entry_5_trail_2_period", 10),
            entry_5_vol_fac=cfg("entry_5_vol_fac", 2.0),
        ),
        Entry6Module(active=cfg("entry_6", False), entry_6_rsi_4h_max=cfg("entry_6_rsi_4h_max", 90), entry_6_max_natr=cfg("entry_6_max_natr", 2), entry_6_atr_fac=cfg("entry_6_atr_fac", 5)),
        Entry7Module(active=cfg("entry_7", False), entry_7_std_fac=cfg("entry_7_std_fac", 1), entry_7_4h_rsi=cfg("entry_7_4h_rsi", 2.5), entry_7_vol_fac=cfg("entry_7_vol_fac", 2)),
        Entry8Module(active=cfg("entry_8", False), entry_8_vol_fac=cfg("entry_8_vol_fac", 2.0)),
        Entry9Module(active=cfg("entry_9", False), entry_9_std=cfg("entry_9_std", 1), entry_9_4h_rsi=cfg("entry_9_4h_rsi", 50), entry_9_atr=cfg("entry_9_atr", 2)),
        Entry11Module(active=cfg("entry_11", False), entry_11_vol=cfg("entry_11_vol", 3.0), entry_11_atr=cfg("entry_11_atr", 3.0), entry_11_natr=cfg("entry_11_natr", 3.0)),
        Entry12Module(
            active=cfg("entry_12", False),
            entry_12_vol=cfg("entry_12_vol", 3.0),
            entry_12_rsi_4h=cfg("entry_12_rsi_4h", 3),
            entry_12_atr=cfg("entry_12_atr", 3.0),
            entry_12_max_rsi_4h=cfg("entry_12_max_rsi_4h", 90),
        ),
    ]
