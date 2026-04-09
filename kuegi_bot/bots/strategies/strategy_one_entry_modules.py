from __future__ import annotations

"""
StrategyOne entry pipeline (single file map):
1. Runtime contexts + common option models
2. Core gate/context/entry-level helpers
3. Shared execution/common-rule helpers
4. EntryModule base + adapters
5. Concrete entry modules (Entry1..Entry22)
6. default_entry_modules() registry builder
"""

from dataclasses import dataclass
from typing import Any, Callable, List, Optional

from kuegi_bot.bots.strategies.trend_enums import (
    MarketDynamic,
    MarketRegime,
    OIFundingState,
    OIPriceFlowState,
    normalize_oi_funding_state,
    normalize_oi_price_flow_state,
    oi_funding_state_from_metrics,
    oi_price_flow_state_from_returns,
)
from kuegi_bot.bots.trading_bot import PositionDirection, TradingBot
from kuegi_bot.utils.trading_classes import OrderType


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


@dataclass(frozen=True)
class ExecutionOptions:
    order_type: str = "legacy"
    entry_offset_atr: float = 0.0
    entry_offset_pct: float = 0.0
    sl_module_enabled: bool = False
    sl_module_atr_mult: float = 1.2
    stop_mode: str = "legacy"
    stop_atr_mult: float = 1.0
    stop_ref_bar_index: int = 1
    stop_buffer_atr: float = 0.0
    stop_ref_profile_enabled: bool = False
    stop_ref_bar_1_source: str = "off"
    stop_ref_bar_2_source: str = "off"
    stop_ref_bar_3_source: str = "off"
    stop_ref_bar_4_source: str = "off"
    stop_ref_bar_5_source: str = "off"
    secondary_enabled: bool = False
    secondary_entry_offset_atr: float = 0.0
    secondary_stop_atr_mult: float = 1.0
    fixed_stop_price: Optional[float] = None


@dataclass(frozen=True)
class CommonRuleOptions:
    confirm_rsi_4h_min_enabled: bool = False
    confirm_rsi_4h_min: float = 0.0
    confirm_rsi_4h_max_enabled: bool = False
    confirm_rsi_4h_max: float = 100.0
    confirm_rsi_d_min_enabled: bool = False
    confirm_rsi_d_min: float = 0.0
    confirm_rsi_d_max_enabled: bool = False
    confirm_rsi_d_max: float = 100.0
    confirm_natr_min_enabled: bool = False
    confirm_natr_min: float = 0.0
    confirm_natr_max_enabled: bool = False
    confirm_natr_max: float = 10.0
    confirm_vol_ratio_min_enabled: bool = False
    confirm_vol_ratio_min: float = 0.0
    confirm_vol_ratio_max_enabled: bool = False
    confirm_vol_ratio_max: float = 10.0
    confirm_require_green_body: bool = False
    confirm_require_red_body: bool = False
    filter_forbid_market_bearish: bool = False
    filter_forbid_market_bullish: bool = False
    filter_require_market_bullish: bool = False
    filter_require_market_bearish: bool = False
    filter_forbid_market_trending: bool = False
    filter_require_market_ranging: bool = False
    filter_require_market_trending: bool = False
    filter_natr_max_enabled: bool = False
    filter_natr_max: float = 10.0
    filter_rsi_4h_max_enabled: bool = False
    filter_rsi_4h_max: float = 100.0
    filter_rsi_d_min_enabled: bool = False
    filter_rsi_d_min: float = 0.0
    filter_rsi_d_max_enabled: bool = False
    filter_rsi_d_max: float = 100.0
    filter_vol_ratio_max_enabled: bool = False
    filter_vol_ratio_max: float = 10.0
    filter_oi_ratio_4h_min_enabled: bool = False
    filter_oi_ratio_4h_min: float = 0.0
    filter_oi_ratio_4h_max_enabled: bool = False
    filter_oi_ratio_4h_max: float = 10.0
    filter_oi_4h_min_enabled: bool = False
    filter_oi_4h_min: float = 0.0
    filter_oi_above_sma_enabled: bool = False
    filter_atr_std_ratio_max_enabled: bool = False
    filter_atr_std_ratio_max: float = 50.0
    filter_close_above_bb_max_enabled: bool = False
    filter_close_above_bb_max_std: float = 3.0
    filter_bar1_green_upper_wick_lt_body_enabled: bool = False
    filter_body_expansion_enabled: bool = False
    filter_body_compare_lookback: int = 2
    filter_open_above_bar4_close_enabled: bool = False
    filter_oi_flow_state: str = "off"
    filter_forbid_oi_flow_state: str = "off"
    filter_oi_flow_lookback: int = 3
    filter_oi_flow_price_min_pct: float = 0.0
    filter_oi_flow_oi_min_pct: float = 0.0
    filter_oi_funding_state: str = "off"
    filter_forbid_oi_funding_state: str = "off"
    filter_oi_funding_lookback: int = 3
    filter_oi_funding_oi_up_min_pct: float = 0.0
    filter_oi_funding_oi_down_min_pct: float = 0.0
    filter_oi_funding_pos_min: float = 0.0
    filter_oi_funding_neg_min: float = 0.0
    filter_max_bar_range_atr_enabled: bool = False
    filter_max_bar_range_atr: float = 10.0
    filter_min_bar_range_atr_enabled: bool = False
    filter_min_bar_range_atr: float = 0.0


@dataclass(frozen=True)
class StrategyOneEntryContext:
    std: Any
    std_vec: Any
    atr: Any
    atr_trail_mix: Any
    natr_4h: Any
    atr_min: Any
    middleband: Any
    middleband_vec: Any
    market_bullish: bool
    market_bearish: bool
    market_ranging: bool
    market_trending: bool
    range_limit: int
    talibbars: Any


ENTRY_MODULE_DEFAULT_ALLOW = {
    "entry_1": (False, True),
    "entry_2": (True, True),
    "entry_3": (True, False),
    "entry_4": (True, False),
    "entry_5": (False, True),
    "entry_6": (True, True),
    "entry_7": (False, True),
    "entry_8": (False, True),
    "entry_9": (False, True),
    "entry_10": (True, False),
    "entry_11": (True, False),
    "entry_12": (True, False),
    "entry_15": (True, False),
    "entry_16": (True, False),
    "entry_17": (False, True),
    "entry_18": (True, False),
    "entry_19": (True, False),
    "entry_20": (True, False),
    "entry_21": (False, True),
    "entry_22": (True, False),
    "entry_23": (True, False),
    "entry_23_secondary": (True, False),
    "entry_24": (True, False),
}


def _cfg_get(config: Any, name: str, default: Any):
    if config is None:
        return default
    if isinstance(config, dict):
        return config.get(name, default)
    return getattr(config, name, default)


def _allow_flags_by_module(config: Any):
    return {
        module_id: _module_allow_flags(config, module_id, defaults[0], defaults[1])
        for module_id, defaults in ENTRY_MODULE_DEFAULT_ALLOW.items()
    }


def build_entry_context(strategy) -> StrategyOneEntryContext:
    ta_data = strategy.ta_data_trend_strat
    atr = ta_data.atr_4h
    natr_4h = ta_data.natr_4h
    atr_min = atr
    if natr_4h < 1:
        atr_min = atr + atr * (1 - natr_4h)

    middleband_vec = ta_data.bbands_4h.middleband_vec
    return StrategyOneEntryContext(
        std=ta_data.bbands_4h.std,
        std_vec=ta_data.bbands_4h.std_vec,
        atr=atr,
        atr_trail_mix=ta_data.atr_trail_mix,
        natr_4h=natr_4h,
        atr_min=atr_min,
        middleband=ta_data.bbands_4h.middleband,
        middleband_vec=middleband_vec,
        market_bullish=ta_data.marketRegime == MarketRegime.BULL,
        market_bearish=ta_data.marketRegime == MarketRegime.BEAR,
        market_ranging=ta_data.marketRegime == MarketRegime.RANGING,
        market_trending=ta_data.marketDynamic == MarketDynamic.TRENDING,
        range_limit=len(middleband_vec),
        talibbars=strategy.ta_trend_strat.taData_trend_strat.talibbars,
    )


def entry_gate_passes(strategy, is_new_bar, bars, open_positions, all_open_pos):
    eps = 1e-12
    if not is_new_bar:
        return False

    if not strategy.entries_allowed(bars):
        strategy.logger.info("New entries not allowed")
        if strategy.telegram is not None:
            strategy.telegram.send_log("New entries not allowed")
        return False

    if strategy.ta_data_trend_strat.atr_4h is None:
        strategy.logger.info("atr not available")
        return False

    if strategy.ta_data_trend_strat.marketRegime == MarketRegime.NONE:
        strategy.logger.info("Market regime unknown")
        return False

    if len(all_open_pos) >= strategy.maxPositions and strategy.consolidate is False:
        strategy.logger.info("Reached max Positions: " + str(len(all_open_pos)))
        if strategy.telegram is not None:
            strategy.telegram.send_log("Reached max Positions")
        return False

    if strategy.reduceRisk:
        total_worst_case = 0
        for pos in open_positions.values():
            filled_entry = pos.filled_entry
            amount = pos.amount
            if filled_entry is not None:
                for o in pos.connectedOrders:
                    order_type = TradingBot.order_type_from_order_id(o.id)
                    if order_type == OrderType.SL:
                        initial_stop = pos.initial_stop
                        wanted_entry = pos.wanted_entry
                        sl = o.trigger_price
                        if (
                            initial_stop is None
                            or wanted_entry is None
                            or sl is None
                            or filled_entry is None
                        ):
                            continue
                        if strategy.symbol.isInverse:
                            if (
                                abs(sl) < eps
                                or abs(filled_entry) < eps
                                or abs(wanted_entry) < eps
                                or abs(initial_stop) < eps
                            ):
                                continue
                            inverse_denom = (1 / wanted_entry) - (1 / initial_stop)
                            if abs(inverse_denom) < eps:
                                continue
                            worst_case = (1 / sl - 1 / filled_entry) / inverse_denom
                            initial_risk = amount / initial_stop - amount / wanted_entry
                        else:
                            direct_denom = wanted_entry - initial_stop
                            if abs(direct_denom) < eps:
                                continue
                            worst_case = (sl - filled_entry) / direct_denom
                            initial_risk = amount * direct_denom

                        total_worst_case += (worst_case * initial_risk)

        if abs(strategy.risk_ref) < eps:
            strategy.logger.info("risk_ref is zero. No new entries.")
            return False
        total_worst_case = total_worst_case / strategy.risk_ref
        if total_worst_case < -strategy.max_r:
            strategy.logger.info("Too much active risk. No new entries.")
            if strategy.telegram is not None:
                strategy.telegram.send_log("Too much active risk. No new entries.")
                strategy.telegram.send_log("totalWorstCase:" + str(total_worst_case))
            return False

    return True


def calc_entry_and_exit(strategy, bars, swing_depth: int = 40, entry_buffer_atr: float = 0.05):
    depth = max(8, int(swing_depth))
    buffer_atr = max(0.0, float(entry_buffer_atr))
    found_swing_high = False
    found_swing_low = False
    idx_swing_high = 0
    idx_swing_low = 0
    for i in range(3, depth):
        condition_1 = bars[i + 2].close < bars[i].close
        condition_2 = bars[i + 1].close < bars[i].close
        condition_3 = bars[i - 2].close < bars[i].close > bars[i - 1].close
        condition_5 = bars[i + 3].close < bars[i].close
        if condition_1 and condition_2 and condition_3 and condition_5:
            found_swing_high = True
            idx_swing_high = i
            break

    if found_swing_high:
        high_values = [bar.close for bar in bars[1:idx_swing_high]]
        already_longed = any(high > bars[idx_swing_high].close for high in high_values)
    else:
        already_longed = True

    for i in range(5, depth):
        cond_1 = bars[i + 2].close > bars[i + 1].close
        cond_2 = bars[i + 1].close > bars[i].close
        cond_3 = bars[i - 2].close > bars[i].close < bars[i - 1].close
        if cond_1 and cond_2 and cond_3:
            found_swing_low = True
            idx_swing_low = i
            break
    if found_swing_low:
        low_values = [bar.close for bar in bars[1:idx_swing_low]]
        already_shorted = any(low < bars[idx_swing_low].close for low in low_values)
    else:
        already_shorted = True

    if found_swing_high and not already_longed and found_swing_low and not already_shorted:
        long_entry = strategy.symbol.normalizePrice(
            bars[idx_swing_high].high + strategy.ta_data_trend_strat.atr_4h * buffer_atr,
            roundUp=True,
        )
        short_entry = strategy.symbol.normalizePrice(
            bars[idx_swing_low].low - strategy.ta_data_trend_strat.atr_4h * buffer_atr,
            roundUp=False,
        )

        stop_long = long_entry - strategy.ta_data_trend_strat.atr_4h * strategy.sl_atr_fac
        stop_short = short_entry + strategy.ta_data_trend_strat.atr_4h * strategy.sl_atr_fac

        stop_long = strategy.symbol.normalizePrice(stop_long, roundUp=False)
        stop_short = strategy.symbol.normalizePrice(stop_short, roundUp=True)

        expected_entry_slippage_per = 0.0015 if strategy.limit_entry_offset_perc is None else 0
        expected_exit_slippage_per = 0.0015
        long_amount = strategy.calc_pos_size(
            risk=strategy.risk_factor,
            exitPrice=stop_long * (1 - expected_exit_slippage_per),
            entry=long_entry * (1 + expected_entry_slippage_per),
            atr=0,
        )
        short_amount = strategy.calc_pos_size(
            risk=strategy.risk_factor,
            exitPrice=stop_short * (1 + expected_exit_slippage_per),
            entry=short_entry * (1 - expected_entry_slippage_per),
            atr=0,
        )
    else:
        long_entry = None
        short_entry = None
        stop_long = None
        stop_short = None
        long_amount = None
        short_amount = None

    return long_entry, short_entry, stop_long, stop_short, long_amount, short_amount, already_longed, already_shorted


def _len_at_least(series, n: int) -> bool:
    return series is not None and len(series) >= n


def _cfg_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    return bool(value)


def _direction_sign(direction: PositionDirection) -> float:
    return 1.0 if direction == PositionDirection.LONG else -1.0


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _pct_return(curr: Any, prev: Any) -> float:
    curr_f = _as_float(curr, float("nan"))
    prev_f = _as_float(prev, float("nan"))
    if curr_f != curr_f or prev_f != prev_f or abs(prev_f) <= 1e-12:
        return float("nan")
    return ((curr_f - prev_f) / abs(prev_f)) * 100.0


def _oi_price_flow_state_from_ta(
    ta_data: Any,
    *,
    lookback: int,
    price_min_pct: float,
    oi_min_pct: float,
) -> OIPriceFlowState:
    talibbars = getattr(ta_data, "talibbars", None)
    close_vec = getattr(talibbars, "close", None)
    oi_vec = getattr(ta_data, "oi_4h_vec", None)

    lb = max(1, int(lookback))
    if not _len_at_least(close_vec, lb + 1) or not _len_at_least(oi_vec, lb + 1):
        return OIPriceFlowState.NEUTRAL

    price_ret = _pct_return(close_vec[-1], close_vec[-(lb + 1)])
    oi_ret = _pct_return(oi_vec[-1], oi_vec[-(lb + 1)])
    if price_ret != price_ret or oi_ret != oi_ret:
        return OIPriceFlowState.NEUTRAL

    return oi_price_flow_state_from_returns(
        price_ret_pct=float(price_ret),
        oi_ret_pct=float(oi_ret),
        price_min_pct=float(price_min_pct),
        oi_min_pct=float(oi_min_pct),
    )


def _oi_funding_state_from_ta(
    ta_data: Any,
    *,
    lookback: int,
    oi_up_min_pct: float,
    oi_down_min_pct: float,
    funding_pos_min: float,
    funding_neg_min: float,
) -> OIFundingState:
    oi_vec = getattr(ta_data, "oi_4h_vec", None)
    funding_vec = getattr(ta_data, "funding_4h_vec", None)

    lb = max(1, int(lookback))
    if not _len_at_least(oi_vec, lb + 1) or not _len_at_least(funding_vec, 1):
        return OIFundingState.NEUTRAL

    oi_ret = _pct_return(oi_vec[-1], oi_vec[-(lb + 1)])
    funding_now = _as_float(funding_vec[-1], float("nan"))
    if oi_ret != oi_ret or funding_now != funding_now:
        return OIFundingState.NEUTRAL

    return oi_funding_state_from_metrics(
        oi_ret_pct=float(oi_ret),
        funding_rate=float(funding_now),
        oi_up_min_pct=float(oi_up_min_pct),
        oi_down_min_pct=float(oi_down_min_pct),
        funding_pos_min=float(funding_pos_min),
        funding_neg_min=float(funding_neg_min),
    )


def _normalize_order_type(order_type: str, default_order_type: str) -> str:
    if order_type is None:
        return default_order_type
    normalized = str(order_type).strip()
    if normalized == "" or normalized.lower() == "legacy":
        return default_order_type
    if normalized in ("Limit", "StopLimit", "StopLoss", "Market"):
        return normalized
    return default_order_type


def _bar_index(bars: list, wanted: int) -> int:
    if len(bars) == 0:
        return 0
    idx = max(0, min(len(bars) - 1, int(wanted)))
    return idx


STOP_REF_BAR_SOURCE_CHOICES = ("off", "open", "close", "high", "low", "min_oc")
ENTRY23_BAR_SOURCE_CHOICES = STOP_REF_BAR_SOURCE_CHOICES


ENTRY_MODULES_WITH_NATIVE_SL_SETTINGS = {
    "entry_2",
}


def _default_sl_module_enabled(module_id: str) -> bool:
    return str(module_id) not in ENTRY_MODULES_WITH_NATIVE_SL_SETTINGS


def _normalize_bar_source(value: Any, default: str = "off") -> str:
    raw = "" if value is None else str(value).strip().lower()
    if raw in ("", "none", "null", "disable", "disabled", "false"):
        raw = "off"
    if raw in STOP_REF_BAR_SOURCE_CHOICES:
        return raw
    fallback = str(default).strip().lower()
    if fallback in STOP_REF_BAR_SOURCE_CHOICES:
        return fallback
    return "off"


def _bar_price_by_source(bars: list, lookback: int, source: str) -> Optional[float]:
    normalized = _normalize_bar_source(source, default="off")
    if normalized == "off":
        return None
    if not _len_at_least(bars, int(lookback) + 1):
        return None
    bar = bars[_bar_index(bars, int(lookback))]
    if normalized == "min_oc":
        value = min(_as_float(getattr(bar, "open", None), float("nan")), _as_float(getattr(bar, "close", None), float("nan")))
    else:
        value = getattr(bar, normalized, None)
    out = _as_float(value, float("nan"))
    if out != out:
        return None
    return out


def _resolve_entry_price(ctx: EntryExecutionContext, direction: PositionDirection, base_entry: float, options: ExecutionOptions) -> float:
    atr = _as_float(ctx.entry_context.atr, 0.0)
    sign = _direction_sign(direction)
    price = _as_float(base_entry, 0.0)
    price += sign * atr * _as_float(options.entry_offset_atr, 0.0)
    price *= 1.0 + sign * _as_float(options.entry_offset_pct, 0.0)
    return price


def _stop_from_mode(
    ctx: EntryExecutionContext,
    direction: PositionDirection,
    entry_price: float,
    base_stop: float,
    options: ExecutionOptions,
) -> float:
    atr = _as_float(ctx.entry_context.atr, 0.0)
    mode = str(options.stop_mode or "legacy")
    atr_mult = _as_float(options.stop_atr_mult, 1.0)
    bar_idx = _bar_index(ctx.bars, _as_int(options.stop_ref_bar_index, 1))

    if bool(options.sl_module_enabled) and mode in ("", "legacy") and (not bool(options.stop_ref_profile_enabled)):
        sl_mult = max(0.0, _as_float(options.sl_module_atr_mult, 1.2))
        if direction == PositionDirection.LONG:
            stop = entry_price - sl_mult * atr
        else:
            stop = entry_price + sl_mult * atr
    elif bool(options.stop_ref_profile_enabled):
        ref_prices: List[float] = []
        for lookback, source in (
            (1, options.stop_ref_bar_1_source),
            (2, options.stop_ref_bar_2_source),
            (3, options.stop_ref_bar_3_source),
            (4, options.stop_ref_bar_4_source),
            (5, options.stop_ref_bar_5_source),
        ):
            ref_price = _bar_price_by_source(ctx.bars, lookback=lookback, source=source)
            if ref_price is not None:
                ref_prices.append(ref_price)
        if len(ref_prices) > 0:
            if direction == PositionDirection.LONG:
                stop = min(ref_prices)
            else:
                stop = max(ref_prices)
        else:
            stop = _as_float(base_stop, 0.0)
    elif mode in ("", "legacy"):
        stop = _as_float(base_stop, 0.0)
    elif mode == "atr_from_entry":
        if direction == PositionDirection.LONG:
            stop = entry_price - atr_mult * atr
        else:
            stop = entry_price + atr_mult * atr
    elif mode == "atr_from_bar_extreme":
        ref_bar = ctx.bars[bar_idx]
        if direction == PositionDirection.LONG:
            stop = ref_bar.low - atr_mult * atr
        else:
            stop = ref_bar.high + atr_mult * atr
    elif mode == "swing_extreme":
        start = 1
        end = _bar_index(ctx.bars, bar_idx) + 1
        window = ctx.bars[start : end + 1]
        if len(window) == 0:
            stop = _as_float(base_stop, 0.0)
        elif direction == PositionDirection.LONG:
            stop = min(bar.low for bar in window) - atr_mult * atr
        else:
            stop = max(bar.high for bar in window) + atr_mult * atr
    elif mode == "fixed_price":
        if options.fixed_stop_price is None:
            stop = _as_float(base_stop, 0.0)
        else:
            stop = _as_float(options.fixed_stop_price, _as_float(base_stop, 0.0))
    elif mode == "hybrid_minmax":
        ref_bar = ctx.bars[bar_idx]
        if direction == PositionDirection.LONG:
            atr_stop = ref_bar.low - atr_mult * atr
            stop = min(_as_float(base_stop, atr_stop), atr_stop)
        else:
            atr_stop = ref_bar.high + atr_mult * atr
            stop = max(_as_float(base_stop, atr_stop), atr_stop)
    else:
        stop = _as_float(base_stop, 0.0)

    buffer_atr = _as_float(options.stop_buffer_atr, 0.0) * atr
    if direction == PositionDirection.LONG:
        return stop - buffer_atr
    return stop + buffer_atr


def _open_with_execution(
    ctx: EntryExecutionContext,
    *,
    direction: PositionDirection,
    base_entry: float,
    base_stop: float,
    default_order_type: str,
    options: ExecutionOptions,
    mark_opened: bool = True,
):
    entry = _resolve_entry_price(ctx, direction, base_entry, options)
    stop = _stop_from_mode(ctx, direction, entry, base_stop, options)
    order_type = _normalize_order_type(options.order_type, default_order_type)
    ctx.strategy.open_new_position(
        entry=entry,
        stop=stop,
        open_positions=ctx.open_positions,
        bars=ctx.bars,
        direction=direction,
        ExecutionType=order_type,
    )
    if mark_opened:
        if direction == PositionDirection.LONG:
            ctx.longed = True
        else:
            ctx.shorted = True
    return entry, stop, order_type


def _build_execution_options(config, module_id: str, *, secondary_defaults=None) -> ExecutionOptions:
    secondary_defaults = secondary_defaults or {}
    missing = object()
    default_sl_module = _default_sl_module_enabled(module_id)

    def _exec_cfg(suffix: str, default: Any):
        value = _cfg_get(config, f"{module_id}_{suffix}", missing)
        if value is missing:
            return default
        return value

    return ExecutionOptions(
        order_type=_exec_cfg("order_type", "legacy"),
        entry_offset_atr=_as_float(_exec_cfg("entry_offset_atr", 0.0), 0.0),
        entry_offset_pct=_as_float(_exec_cfg("entry_offset_pct", 0.0), 0.0),
        sl_module_enabled=_cfg_bool(_exec_cfg("sl_module_enabled", default_sl_module), default_sl_module),
        sl_module_atr_mult=_as_float(_exec_cfg("sl_module_atr_mult", 1.2), 1.2),
        stop_mode=_exec_cfg("stop_mode", "legacy"),
        stop_atr_mult=_as_float(_exec_cfg("stop_atr_mult", 1.0), 1.0),
        stop_ref_bar_index=_as_int(_exec_cfg("stop_ref_bar_index", 1), 1),
        stop_buffer_atr=_as_float(_exec_cfg("stop_buffer_atr", 0.0), 0.0),
        stop_ref_profile_enabled=_cfg_bool(
            _exec_cfg("stop_ref_profile_enabled", False),
            False,
        ),
        stop_ref_bar_1_source=_normalize_bar_source(
            _exec_cfg("stop_ref_bar_1_source", "off"),
            default="off",
        ),
        stop_ref_bar_2_source=_normalize_bar_source(
            _exec_cfg("stop_ref_bar_2_source", "off"),
            default="off",
        ),
        stop_ref_bar_3_source=_normalize_bar_source(
            _exec_cfg("stop_ref_bar_3_source", "off"),
            default="off",
        ),
        stop_ref_bar_4_source=_normalize_bar_source(
            _exec_cfg("stop_ref_bar_4_source", "off"),
            default="off",
        ),
        stop_ref_bar_5_source=_normalize_bar_source(
            _exec_cfg("stop_ref_bar_5_source", "off"),
            default="off",
        ),
        secondary_enabled=_cfg_bool(
            _exec_cfg("secondary_enabled", secondary_defaults.get("enabled", False)),
            secondary_defaults.get("enabled", False),
        ),
        secondary_entry_offset_atr=_as_float(
            _exec_cfg("secondary_entry_offset_atr", secondary_defaults.get("entry_offset_atr", 0.0)),
            secondary_defaults.get("entry_offset_atr", 0.0),
        ),
        secondary_stop_atr_mult=_as_float(
            _exec_cfg("secondary_stop_atr_mult", secondary_defaults.get("stop_atr_mult", 1.0)),
            secondary_defaults.get("stop_atr_mult", 1.0),
        ),
        fixed_stop_price=_exec_cfg("fixed_stop_price", None),
    )


def _module_allow_flags(config, module_id: str, default_long: bool, default_short: bool):
    allow_long = _cfg_bool(_cfg_get(config, f"{module_id}_allow_long", default_long), default_long)
    allow_short = _cfg_bool(_cfg_get(config, f"{module_id}_allow_short", default_short), default_short)
    return allow_long, allow_short


def _build_common_rule_options(config, module_id: str) -> CommonRuleOptions:
    missing = object()

    def _cfg_local(suffix: str, default: Any):
        return _cfg_get(config, f"{module_id}_{suffix}", default)

    def _cfg_with_legacy(suffix: str, default: Any, *legacy_suffixes: str):
        value = _cfg_get(config, f"{module_id}_{suffix}", missing)
        if value is not missing:
            return value
        for legacy_suffix in legacy_suffixes:
            legacy_value = _cfg_get(config, f"{module_id}_{legacy_suffix}", missing)
            if legacy_value is not missing:
                return legacy_value
        return default

    def _has_key(suffix: str) -> bool:
        return _cfg_get(config, f"{module_id}_{suffix}", missing) is not missing

    return CommonRuleOptions(
        confirm_rsi_4h_min_enabled=_cfg_bool(_cfg_local("confirm_rsi_4h_min_enabled", False), False),
        confirm_rsi_4h_min=_as_float(_cfg_local("confirm_rsi_4h_min", 0.0), 0.0),
        confirm_rsi_4h_max_enabled=_cfg_bool(_cfg_local("confirm_rsi_4h_max_enabled", False), False),
        confirm_rsi_4h_max=_as_float(_cfg_local("confirm_rsi_4h_max", 100.0), 100.0),
        confirm_rsi_d_min_enabled=_cfg_bool(_cfg_local("confirm_rsi_d_min_enabled", False), False),
        confirm_rsi_d_min=_as_float(_cfg_local("confirm_rsi_d_min", 0.0), 0.0),
        confirm_rsi_d_max_enabled=_cfg_bool(_cfg_local("confirm_rsi_d_max_enabled", False), False),
        confirm_rsi_d_max=_as_float(_cfg_local("confirm_rsi_d_max", 100.0), 100.0),
        confirm_natr_min_enabled=_cfg_bool(_cfg_local("confirm_natr_min_enabled", False), False),
        confirm_natr_min=_as_float(_cfg_local("confirm_natr_min", 0.0), 0.0),
        confirm_natr_max_enabled=_cfg_bool(_cfg_local("confirm_natr_max_enabled", False), False),
        confirm_natr_max=_as_float(_cfg_local("confirm_natr_max", 10.0), 10.0),
        confirm_vol_ratio_min_enabled=_cfg_bool(_cfg_local("confirm_vol_ratio_min_enabled", False), False),
        confirm_vol_ratio_min=_as_float(_cfg_local("confirm_vol_ratio_min", 0.0), 0.0),
        confirm_vol_ratio_max_enabled=_cfg_bool(_cfg_local("confirm_vol_ratio_max_enabled", False), False),
        confirm_vol_ratio_max=_as_float(_cfg_local("confirm_vol_ratio_max", 10.0), 10.0),
        confirm_require_green_body=_cfg_bool(_cfg_local("confirm_require_green_body", False), False),
        confirm_require_red_body=_cfg_bool(_cfg_local("confirm_require_red_body", False), False),
        filter_forbid_market_bearish=_cfg_bool(_cfg_local("filter_forbid_market_bearish", False), False) or _cfg_bool(_cfg_local("require_not_bearish", False), False),
        filter_forbid_market_bullish=_cfg_bool(_cfg_local("filter_forbid_market_bullish", False), False),
        filter_require_market_bullish=_cfg_bool(_cfg_local("filter_require_market_bullish", False), False),
        filter_require_market_bearish=_cfg_bool(_cfg_local("filter_require_market_bearish", False), False),
        filter_forbid_market_trending=_cfg_bool(_cfg_local("filter_forbid_market_trending", False), False) or _cfg_bool(_cfg_local("require_not_trending", False), False),
        filter_require_market_ranging=_cfg_bool(_cfg_local("filter_require_market_ranging", False), False),
        filter_require_market_trending=_cfg_bool(_cfg_local("filter_require_market_trending", False), False),
        filter_natr_max_enabled=_cfg_bool(_cfg_with_legacy("filter_natr_max_enabled", False), False) or _has_key("natr_max"),
        filter_natr_max=_as_float(_cfg_with_legacy("filter_natr_max", 10.0, "natr_max"), 10.0),
        filter_rsi_4h_max_enabled=_cfg_bool(_cfg_with_legacy("filter_rsi_4h_max_enabled", False), False) or _cfg_bool(_cfg_local("filter_rsi_4h_max_enabled", False), False),
        filter_rsi_4h_max=_as_float(_cfg_with_legacy("filter_rsi_4h_max", 100.0, "rsi_4h_max"), 100.0),
        filter_rsi_d_min_enabled=_cfg_bool(_cfg_with_legacy("filter_rsi_d_min_enabled", False), False) or _cfg_bool(_cfg_local("filter_rsi_d_min_enabled", False), False),
        filter_rsi_d_min=_as_float(_cfg_with_legacy("filter_rsi_d_min", 0.0, "rsi_d_min"), 0.0),
        filter_rsi_d_max_enabled=_cfg_bool(_cfg_with_legacy("filter_rsi_d_max_enabled", False), False) or _cfg_bool(_cfg_local("filter_rsi_d_max_enabled", False), False),
        filter_rsi_d_max=_as_float(_cfg_with_legacy("filter_rsi_d_max", 100.0, "rsi_d_max"), 100.0),
        filter_vol_ratio_max_enabled=_cfg_bool(_cfg_with_legacy("filter_vol_ratio_max_enabled", False), False) or _cfg_bool(_cfg_local("filter_vol_ratio_max_enabled", False), False),
        filter_vol_ratio_max=_as_float(_cfg_with_legacy("filter_vol_ratio_max", 10.0, "vol_ratio_max"), 10.0),
        filter_oi_ratio_4h_min_enabled=_cfg_bool(_cfg_with_legacy("filter_oi_ratio_4h_min_enabled", False), False) or _cfg_bool(_cfg_local("filter_oi_ratio_4h_min_enabled", False), False),
        filter_oi_ratio_4h_min=_as_float(_cfg_with_legacy("filter_oi_ratio_4h_min", 0.0, "oi_ratio_4h_min"), 0.0),
        filter_oi_ratio_4h_max_enabled=_cfg_bool(_cfg_with_legacy("filter_oi_ratio_4h_max_enabled", False), False) or _cfg_bool(_cfg_local("filter_oi_ratio_4h_max_enabled", False), False),
        filter_oi_ratio_4h_max=_as_float(_cfg_with_legacy("filter_oi_ratio_4h_max", 10.0, "oi_ratio_4h_max"), 10.0),
        filter_oi_4h_min_enabled=_cfg_bool(_cfg_with_legacy("filter_oi_4h_min_enabled", False), False) or _cfg_bool(_cfg_local("filter_oi_4h_min_enabled", False), False),
        filter_oi_4h_min=_as_float(_cfg_with_legacy("filter_oi_4h_min", 0.0, "oi_4h_min"), 0.0),
        filter_oi_above_sma_enabled=_cfg_bool(_cfg_with_legacy("filter_oi_above_sma_enabled", False), False) or _cfg_bool(_cfg_local("filter_oi_above_sma_enabled", False), False),
        filter_atr_std_ratio_max_enabled=_cfg_bool(_cfg_with_legacy("filter_atr_std_ratio_max_enabled", False), False) or _cfg_bool(_cfg_local("filter_atr_std_ratio_max_enabled", False), False),
        filter_atr_std_ratio_max=_as_float(_cfg_with_legacy("filter_atr_std_ratio_max", 50.0, "atr_std_ratio_max"), 50.0),
        filter_close_above_bb_max_enabled=_cfg_bool(_cfg_with_legacy("filter_close_above_bb_max_enabled", False), False) or _cfg_bool(_cfg_local("filter_close_above_bb_max_enabled", False), False),
        filter_close_above_bb_max_std=_as_float(_cfg_with_legacy("filter_close_above_bb_max_std", 3.0, "close_above_bb_max_std"), 3.0),
        filter_bar1_green_upper_wick_lt_body_enabled=_cfg_bool(_cfg_with_legacy("filter_bar1_green_upper_wick_lt_body_enabled", False), False) or _cfg_bool(_cfg_local("filter_bar1_green_upper_wick_lt_body_enabled", False), False),
        filter_body_expansion_enabled=_cfg_bool(_cfg_with_legacy("filter_body_expansion_enabled", False, "require_body_expansion"), False),
        filter_body_compare_lookback=max(2, _as_int(_cfg_with_legacy("filter_body_compare_lookback", 2, "body_compare_lookback"), 2)),
        filter_open_above_bar4_close_enabled=_cfg_bool(_cfg_local("filter_open_above_bar4_close_enabled", False), False),
        filter_oi_flow_state=normalize_oi_price_flow_state(_cfg_local("oi_flow_state", "off"), default="off"),
        filter_forbid_oi_flow_state=normalize_oi_price_flow_state(_cfg_local("filter_forbid_oi_flow_state", "off"), default="off"),
        filter_oi_flow_lookback=max(1, _as_int(_cfg_local("oi_flow_lookback", 3), 3)),
        filter_oi_flow_price_min_pct=max(0.0, _as_float(_cfg_local("oi_flow_price_min_pct", 0.0), 0.0)),
        filter_oi_flow_oi_min_pct=max(0.0, _as_float(_cfg_local("oi_flow_oi_min_pct", 0.0), 0.0)),
        filter_oi_funding_state=normalize_oi_funding_state(_cfg_local("oi_funding_state", "off"), default="off"),
        filter_forbid_oi_funding_state=normalize_oi_funding_state(_cfg_local("filter_forbid_oi_funding_state", "off"), default="off"),
        filter_oi_funding_lookback=max(1, _as_int(_cfg_local("oi_funding_lookback", 3), 3)),
        filter_oi_funding_oi_up_min_pct=max(0.0, _as_float(_cfg_local("oi_funding_oi_up_min_pct", 0.0), 0.0)),
        filter_oi_funding_oi_down_min_pct=max(0.0, _as_float(_cfg_local("oi_funding_oi_down_min_pct", 0.0), 0.0)),
        filter_oi_funding_pos_min=max(0.0, _as_float(_cfg_local("oi_funding_pos_min", 0.0), 0.0)),
        filter_oi_funding_neg_min=max(0.0, _as_float(_cfg_local("oi_funding_neg_min", 0.0), 0.0)),
        filter_max_bar_range_atr_enabled=_cfg_bool(_cfg_local("filter_max_bar_range_atr_enabled", False), False),
        filter_max_bar_range_atr=_as_float(_cfg_local("filter_max_bar_range_atr", 10.0), 10.0),
        filter_min_bar_range_atr_enabled=_cfg_bool(_cfg_local("filter_min_bar_range_atr_enabled", False), False),
        filter_min_bar_range_atr=_as_float(_cfg_local("filter_min_bar_range_atr", 0.0), 0.0),
    )


def _passes_common_confirmation(ctx: EntryExecutionContext, opts: CommonRuleOptions) -> bool:
    ta = ctx.strategy.ta_data_trend_strat
    rsi_4h = None
    if _len_at_least(ta.rsi_4h_vec, 1):
        rsi_4h = ta.rsi_4h_vec[-1]
    rsi_d = ta.rsi_d
    natr = ctx.entry_context.natr_4h
    volume_sma = None
    if _len_at_least(ta.volume_sma_4h_vec, 1):
        volume_sma = ta.volume_sma_4h_vec[-1]
    volume_now = ta.volume_4h

    if opts.confirm_rsi_4h_min_enabled:
        if rsi_4h is None or rsi_4h < opts.confirm_rsi_4h_min:
            return False
    if opts.confirm_rsi_4h_max_enabled:
        if rsi_4h is None or rsi_4h > opts.confirm_rsi_4h_max:
            return False
    if opts.confirm_rsi_d_min_enabled:
        if rsi_d is None or rsi_d < opts.confirm_rsi_d_min:
            return False
    if opts.confirm_rsi_d_max_enabled:
        if rsi_d is None or rsi_d > opts.confirm_rsi_d_max:
            return False
    if opts.confirm_natr_min_enabled:
        if natr is None or natr < opts.confirm_natr_min:
            return False
    if opts.confirm_natr_max_enabled:
        if natr is None or natr > opts.confirm_natr_max:
            return False
    if opts.confirm_vol_ratio_min_enabled:
        if volume_sma is None or volume_sma == 0 or volume_now is None:
            return False
        if (volume_now / volume_sma) < opts.confirm_vol_ratio_min:
            return False
    if opts.confirm_vol_ratio_max_enabled:
        if volume_sma is None or volume_sma == 0 or volume_now is None:
            return False
        if (volume_now / volume_sma) > opts.confirm_vol_ratio_max:
            return False
    if opts.confirm_require_green_body:
        if len(ctx.bars) < 2 or not (ctx.bars[1].close > ctx.bars[1].open):
            return False
    if opts.confirm_require_red_body:
        if len(ctx.bars) < 2 or not (ctx.bars[1].close < ctx.bars[1].open):
            return False
    return True


def _passes_market_state_filters(ctx: EntryExecutionContext, opts: CommonRuleOptions) -> bool:
    if opts.filter_forbid_market_bearish and ctx.entry_context.market_bearish:
        return False
    if opts.filter_forbid_market_bullish and ctx.entry_context.market_bullish:
        return False
    if opts.filter_require_market_bullish and not ctx.entry_context.market_bullish:
        return False
    if opts.filter_require_market_bearish and not ctx.entry_context.market_bearish:
        return False
    if opts.filter_forbid_market_trending and ctx.entry_context.market_trending:
        return False
    if opts.filter_require_market_ranging and not ctx.entry_context.market_ranging:
        return False
    if opts.filter_require_market_trending and not ctx.entry_context.market_trending:
        return False
    return True


def _passes_primary_indicator_filters(ctx: EntryExecutionContext, ta, opts: CommonRuleOptions) -> bool:
    natr = ctx.entry_context.natr_4h
    if opts.filter_natr_max_enabled:
        if natr is None or natr > opts.filter_natr_max:
            return False

    rsi_4h = ta.rsi_4h_vec[-1] if _len_at_least(ta.rsi_4h_vec, 1) else None
    if opts.filter_rsi_4h_max_enabled:
        if rsi_4h is None or rsi_4h > opts.filter_rsi_4h_max:
            return False

    rsi_d = ta.rsi_d
    if opts.filter_rsi_d_min_enabled:
        if rsi_d is None or rsi_d < opts.filter_rsi_d_min:
            return False
    if opts.filter_rsi_d_max_enabled:
        if rsi_d is None or rsi_d > opts.filter_rsi_d_max:
            return False

    volume_sma = ta.volume_sma_4h_vec[-1] if _len_at_least(ta.volume_sma_4h_vec, 1) else None
    volume_now = ta.volume_4h
    if opts.filter_vol_ratio_max_enabled:
        if volume_sma is None or volume_sma == 0 or volume_now is None:
            return False
        if (volume_now / volume_sma) > opts.filter_vol_ratio_max:
            return False
    return True


def _passes_oi_ratio_filters(ta, opts: CommonRuleOptions) -> bool:
    oi_ratio_4h = _as_float(ta.oi_ratio_4h, float("nan"))
    oi_4h = _as_float(ta.oi_4h, float("nan"))
    if opts.filter_oi_ratio_4h_min_enabled:
        if (oi_ratio_4h != oi_ratio_4h) or (oi_ratio_4h < opts.filter_oi_ratio_4h_min):
            return False
    if opts.filter_oi_ratio_4h_max_enabled:
        if (oi_ratio_4h != oi_ratio_4h) or (oi_ratio_4h > opts.filter_oi_ratio_4h_max):
            return False
    if opts.filter_oi_4h_min_enabled:
        if (oi_4h != oi_4h) or (oi_4h < opts.filter_oi_4h_min):
            return False
    if opts.filter_oi_above_sma_enabled:
        if (oi_ratio_4h != oi_ratio_4h) or (oi_ratio_4h < 1.0):
            return False
    return True


def _passes_atr_std_ratio_filter(ctx: EntryExecutionContext, ta, opts: CommonRuleOptions) -> bool:
    if not opts.filter_atr_std_ratio_max_enabled:
        return True
    if not _len_at_least(ta.atr_4h_vec, 1) or not _len_at_least(ctx.entry_context.std_vec, 1):
        return False
    atr_prev = _as_float(ta.atr_4h_vec[-1], float("nan"))
    std_prev = _as_float(ctx.entry_context.std_vec[-1], float("nan"))
    if (std_prev != std_prev) or abs(std_prev) <= 1e-12:
        return False
    atr_std_ratio = atr_prev / std_prev
    if (atr_std_ratio != atr_std_ratio) or (atr_std_ratio > opts.filter_atr_std_ratio_max):
        return False
    return True


def _passes_bb_and_shape_filters(ctx: EntryExecutionContext, opts: CommonRuleOptions) -> bool:
    if opts.filter_close_above_bb_max_enabled:
        if len(ctx.bars) < 2 or not _len_at_least(ctx.entry_context.middleband_vec, 1) or not _len_at_least(ctx.entry_context.std_vec, 1):
            return False
        bb_middle_prev = _as_float(ctx.entry_context.middleband_vec[-1], float("nan"))
        bb_std_prev = _as_float(ctx.entry_context.std_vec[-1], float("nan"))
        if (bb_middle_prev != bb_middle_prev) or (bb_std_prev != bb_std_prev):
            return False
        bb_max_level = bb_middle_prev + bb_std_prev * opts.filter_close_above_bb_max_std
        if ctx.bars[1].close > bb_max_level:
            return False

    if opts.filter_bar1_green_upper_wick_lt_body_enabled:
        if len(ctx.bars) < 2:
            return False
        bar1 = ctx.bars[1]
        is_green = _as_float(bar1.close, 0.0) > _as_float(bar1.open, 0.0)
        upper_wick = abs(_as_float(bar1.high, 0.0) - _as_float(bar1.close, 0.0))
        body = abs(_as_float(bar1.close, 0.0) - _as_float(bar1.open, 0.0))
        if (not is_green) or not (upper_wick < body):
            return False

    if opts.filter_body_expansion_enabled:
        lookback = max(2, int(opts.filter_body_compare_lookback))
        if not _len_at_least(ctx.bars, lookback + 1):
            return False
        body_bar1 = _as_float(ctx.bars[1].close, 0.0) - _as_float(ctx.bars[1].open, 0.0)
        body_prev = _as_float(ctx.bars[lookback].close, 0.0) - _as_float(ctx.bars[lookback].open, 0.0)
        if not (body_bar1 > body_prev):
            return False

    if opts.filter_open_above_bar4_close_enabled:
        if not _len_at_least(ctx.bars, 5):
            return False
        if not (_as_float(ctx.bars[1].open, 0.0) > _as_float(ctx.bars[4].close, 0.0)):
            return False
    return True


def _passes_oi_state_filters(ta, opts: CommonRuleOptions) -> bool:
    wanted_flow = normalize_oi_price_flow_state(opts.filter_oi_flow_state, default="off")
    forbidden_flow = normalize_oi_price_flow_state(opts.filter_forbid_oi_flow_state, default="off")
    if wanted_flow != "off" or forbidden_flow != "off":
        flow_state = _oi_price_flow_state_from_ta(
            ta,
            lookback=opts.filter_oi_flow_lookback,
            price_min_pct=opts.filter_oi_flow_price_min_pct,
            oi_min_pct=opts.filter_oi_flow_oi_min_pct,
        )
        if wanted_flow != "off" and flow_state.value != wanted_flow:
            return False
        if forbidden_flow != "off" and flow_state.value == forbidden_flow:
            return False

    wanted_oi_funding = normalize_oi_funding_state(opts.filter_oi_funding_state, default="off")
    forbidden_oi_funding = normalize_oi_funding_state(opts.filter_forbid_oi_funding_state, default="off")
    if wanted_oi_funding != "off" or forbidden_oi_funding != "off":
        oi_funding_state = _oi_funding_state_from_ta(
            ta,
            lookback=opts.filter_oi_funding_lookback,
            oi_up_min_pct=opts.filter_oi_funding_oi_up_min_pct,
            oi_down_min_pct=opts.filter_oi_funding_oi_down_min_pct,
            funding_pos_min=opts.filter_oi_funding_pos_min,
            funding_neg_min=opts.filter_oi_funding_neg_min,
        )
        if wanted_oi_funding != "off" and oi_funding_state.value != wanted_oi_funding:
            return False
        if forbidden_oi_funding != "off" and oi_funding_state.value == forbidden_oi_funding:
            return False
    return True


def _passes_bar_range_atr_filters(ctx: EntryExecutionContext, opts: CommonRuleOptions) -> bool:
    atr = ctx.entry_context.atr
    if atr is not None and atr > 0 and len(ctx.bars) >= 2:
        bar_range_atr = (ctx.bars[1].high - ctx.bars[1].low) / atr
        if opts.filter_max_bar_range_atr_enabled and bar_range_atr > opts.filter_max_bar_range_atr:
            return False
        if opts.filter_min_bar_range_atr_enabled and bar_range_atr < opts.filter_min_bar_range_atr:
            return False
        return True
    if opts.filter_max_bar_range_atr_enabled or opts.filter_min_bar_range_atr_enabled:
        return False
    return True


def _passes_common_filters(ctx: EntryExecutionContext, opts: CommonRuleOptions) -> bool:
    # Confirmation checks are treated as part of the unified filter layer.
    if not _passes_common_confirmation(ctx, opts):
        return False

    ta = ctx.strategy.ta_data_trend_strat
    return (
        _passes_market_state_filters(ctx, opts)
        and _passes_primary_indicator_filters(ctx, ta, opts)
        and _passes_oi_ratio_filters(ta, opts)
        and _passes_atr_std_ratio_filter(ctx, ta, opts)
        and _passes_bb_and_shape_filters(ctx, opts)
        and _passes_oi_state_filters(ta, opts)
        and _passes_bar_range_atr_filters(ctx, opts)
    )


def module_passes_common_rules(module: Any, ctx: EntryExecutionContext) -> bool:
    opts = getattr(module, "common_rules", None)
    if opts is None:
        return True
    return _passes_common_filters(ctx, opts)


def _attach_common_rules(module: Any, config, module_id: str):
    setattr(module, "common_rules", _build_common_rule_options(config, module_id))
    return module


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

    def __init__(
        self,
        active=None,
        entry_1_atr_fac: float = 1,
        entry_1_vol_fac: float = 2.0,
        entry_1_trail_lookback_1: int = 6,
        entry_1_trail_lookback_2: int = 7,
        entry_1_require_red_daily: bool = True,
        entry_1_require_market_bearish: bool = True,
        allow_long: bool = False,
        allow_short: bool = True,
        execution: ExecutionOptions = ExecutionOptions(),
    ):
        self.active = active
        self.entry_1_atr_fac = entry_1_atr_fac
        self.entry_1_vol_fac = entry_1_vol_fac
        self.entry_1_trail_lookback_1 = max(1, int(entry_1_trail_lookback_1))
        self.entry_1_trail_lookback_2 = max(1, int(entry_1_trail_lookback_2))
        self.entry_1_require_red_daily = bool(entry_1_require_red_daily)
        self.entry_1_require_market_bearish = bool(entry_1_require_market_bearish)
        self.allow_long = allow_long
        self.allow_short = allow_short
        self.execution = execution

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        return bool(self.active) and self.allow_short and not ctx.shorted and ctx.strategy.shortsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        talibbars = ctx.entry_context.talibbars
        needed_trail = max(self.entry_1_trail_lookback_1, self.entry_1_trail_lookback_2)
        return (
            _len_at_least(ctx.bars, 1)
            and _len_at_least(talibbars.close_daily, 1)
            and _len_at_least(talibbars.open_daily, 1)
            and _len_at_least(talibbars.high_daily, 1)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.highs_trail_4h_vec, needed_trail)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.volume_sma_4h_vec, 1)
            and ctx.strategy.ta_data_trend_strat.volume_4h is not None
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        talibbars = ctx.entry_context.talibbars
        condition_1 = (not self.entry_1_require_red_daily) or (talibbars.close_daily[-1] < talibbars.open_daily[-1])
        condition_2 = (
            talibbars.high_daily[-1] > ctx.strategy.ta_data_trend_strat.highs_trail_4h_vec[-self.entry_1_trail_lookback_1]
            or talibbars.high_daily[-1] > ctx.strategy.ta_data_trend_strat.highs_trail_4h_vec[-self.entry_1_trail_lookback_2]
        )
        condition_3 = (not self.entry_1_require_market_bearish) or ctx.entry_context.market_bearish
        condition_4 = (
            ctx.strategy.ta_data_trend_strat.volume_sma_4h_vec[-1] * self.entry_1_vol_fac
            < ctx.strategy.ta_data_trend_strat.volume_4h
        )
        if condition_1 and condition_2 and condition_3 and condition_4:
            ctx.strategy.logger.info("Shorting daily sfp")
            if ctx.strategy.telegram is not None:
                ctx.strategy.telegram.send_log("Shorting daily sfp")
            base_entry = ctx.bars[0].close
            base_stop = ctx.bars[0].close + ctx.entry_context.atr_trail_mix * self.entry_1_atr_fac
            _open_with_execution(
                ctx,
                direction=PositionDirection.SHORT,
                base_entry=base_entry,
                base_stop=base_stop,
                default_order_type="Market",
                options=self.execution,
            )


class Entry10Module(EntryModule):
    name = "entry_10"

    def __init__(
        self,
        active=None,
        entry_10_natr: float = 2,
        entry_10_natr_ath: float = 2,
        entry_10_rsi_4h: int = 50,
        entry_10_rsi_d_min: int = 50,
        entry_10_vol_cap_mult: float = 2.6,
        entry_10_sl_atr_mult: float = 0.2,
        entry_10_require_not_bearish: bool = True,
        entry_10_require_body_expansion: bool = True,
        entry_10_require_open_above_bar4_close: bool = True,
        entry_10_require_not_trending: bool = True,
        allow_long: bool = True,
        allow_short: bool = False,
        execution: ExecutionOptions = ExecutionOptions(),
    ):
        self.active = active
        self.entry_10_natr = entry_10_natr
        self.entry_10_natr_ath = entry_10_natr_ath
        self.entry_10_rsi_4h = entry_10_rsi_4h
        self.entry_10_rsi_d_min = entry_10_rsi_d_min
        self.entry_10_vol_cap_mult = entry_10_vol_cap_mult
        self.entry_10_sl_atr_mult = entry_10_sl_atr_mult
        self.entry_10_require_not_bearish = bool(entry_10_require_not_bearish)
        self.entry_10_require_body_expansion = bool(entry_10_require_body_expansion)
        self.entry_10_require_open_above_bar4_close = bool(entry_10_require_open_above_bar4_close)
        self.entry_10_require_not_trending = bool(entry_10_require_not_trending)
        self.allow_long = allow_long
        self.allow_short = allow_short
        self.execution = execution

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        return bool(self.active) and self.allow_long and not ctx.longed and ctx.strategy.longsAllowed

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
        condition_4 = (not self.entry_10_require_not_bearish) or (not ctx.entry_context.market_bearish)
        condition_5 = (not self.entry_10_require_body_expansion) or (
            ctx.bars[1].close - ctx.bars[1].open > ctx.bars[2].close - ctx.bars[2].open
        )
        condition_6 = (not self.entry_10_require_open_above_bar4_close) or (ctx.bars[1].open > ctx.bars[4].close)
        condition_7 = ctx.strategy.ta_data_trend_strat.rsi_d > self.entry_10_rsi_d_min
        condition_8 = (not self.entry_10_require_not_trending) or (not ctx.entry_context.market_trending)
        condition_9 = (
            ctx.strategy.ta_data_trend_strat.volume_sma_4h_vec[-1] * self.entry_10_vol_cap_mult
            > ctx.strategy.ta_data_trend_strat.volume_4h
        )
        conditions_set_1 = (
            condition_1 and condition_2 and condition_3 and condition_4
            and condition_5 and condition_7 and condition_8 and condition_9
        )
        conditions_set_2 = condition_1 and condition_2b and ath and condition_3 and condition_4 and condition_6
        if not (conditions_set_1 or conditions_set_2):
            return

        ctx.strategy.logger.info("Longing confirmed trail breakout.")
        if ctx.strategy.telegram is not None:
            ctx.strategy.telegram.send_log("Longing confirmed trail breakout.")

        base_entry = ctx.bars[0].close
        base_stop = ctx.bars[1].low - _as_float(ctx.entry_context.atr, 0.0) * self.entry_10_sl_atr_mult
        primary_entry, _, _ = _open_with_execution(
            ctx,
            direction=PositionDirection.LONG,
            base_entry=base_entry,
            base_stop=base_stop,
            default_order_type="Market",
            options=self.execution,
        )

        if self.execution.secondary_enabled:
            ctx.strategy.logger.info("Sending additional long.")
            if ctx.strategy.telegram is not None:
                ctx.strategy.telegram.send_log("Sending additional long.")
            secondary_entry = primary_entry - self.execution.secondary_entry_offset_atr * _as_float(ctx.entry_context.atr, 0.0)
            secondary_stop = secondary_entry - self.execution.secondary_stop_atr_mult * _as_float(ctx.entry_context.atr_min, 0.0)
            ctx.strategy.open_new_position(
                entry=secondary_entry,
                stop=secondary_stop,
                open_positions=ctx.open_positions,
                bars=ctx.bars,
                direction=PositionDirection.LONG,
                ExecutionType="Limit",
            )


class Entry23Module(EntryModule):
    name = "entry_23"
    TRAIL_TRIGGER_LOOKBACK = 2

    def __init__(
        self,
        active=None,
        allow_long: bool = True,
        allow_short: bool = False,
        execution: ExecutionOptions = ExecutionOptions(),
    ):
        self.active = active
        # Entry23 trigger definition is fixed:
        # close(bar[1]) > highs_trail_4h_vec[-2]
        self.entry_23_trail_ref_lookback = int(self.TRAIL_TRIGGER_LOOKBACK)
        self.allow_long = allow_long
        self.allow_short = allow_short
        self.execution = execution

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        # Intentionally ignore ctx.longed so split entry modules can fire sequentially.
        return bool(self.active) and self.allow_long and ctx.strategy.longsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        return (
            _len_at_least(ctx.bars, 2)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.highs_trail_4h_vec, self.TRAIL_TRIGGER_LOOKBACK)
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        # Entry idea stays strategy-specific and hard-coded.
        if ctx.bars[1].close <= ctx.strategy.ta_data_trend_strat.highs_trail_4h_vec[-2]:
            return

        ctx.strategy.logger.info("Longing confirmed trail breakout (regular).")
        if ctx.strategy.telegram is not None:
            ctx.strategy.telegram.send_log("Longing confirmed trail breakout (regular).")

        base_entry = ctx.bars[0].close
        # In generic-SL mode, base_stop is a fallback only.
        base_stop = ctx.bars[1].low
        _open_with_execution(
            ctx,
            direction=PositionDirection.LONG,
            base_entry=base_entry,
            base_stop=base_stop,
            default_order_type="Market",
            options=self.execution,
        )


class Entry23SecondaryModule(EntryModule):
    name = "entry_23_secondary"
    TRAIL_TRIGGER_LOOKBACK = 2

    def __init__(
        self,
        active=None,
        allow_long: bool = True,
        allow_short: bool = False,
        execution: ExecutionOptions = ExecutionOptions(),
    ):
        self.active = active
        self.allow_long = allow_long
        self.allow_short = allow_short
        self.execution = execution

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        # Intentionally ignore ctx.longed so both entry_23 modules can fire on the same signal.
        return bool(self.active) and self.allow_long and ctx.strategy.longsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        return (
            _len_at_least(ctx.bars, 2)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.highs_trail_4h_vec, self.TRAIL_TRIGGER_LOOKBACK)
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        if ctx.bars[1].close <= ctx.strategy.ta_data_trend_strat.highs_trail_4h_vec[-2]:
            return

        ctx.strategy.logger.info("Longing confirmed trail breakout (secondary).")
        if ctx.strategy.telegram is not None:
            ctx.strategy.telegram.send_log("Longing confirmed trail breakout (secondary).")

        _open_with_execution(
            ctx,
            direction=PositionDirection.LONG,
            base_entry=ctx.bars[0].close,
            base_stop=ctx.bars[1].low,
            default_order_type="Limit",
            options=self.execution,
        )


class Entry24Module(EntryModule):
    name = "entry_24"

    def __init__(
        self,
        active=None,
        allow_long: bool = True,
        allow_short: bool = False,
        execution: ExecutionOptions = ExecutionOptions(),
    ):
        self.active = active
        self.allow_long = allow_long
        self.allow_short = allow_short
        self.execution = execution

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        # Intentionally ignore ctx.longed so split entry modules can fire sequentially.
        return bool(self.active) and self.allow_long and ctx.strategy.longsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        return (
            _len_at_least(ctx.bars, 5)
            and _len_at_least(ctx.entry_context.talibbars.close, 1)
            and _len_at_least(ctx.strategy.ta_strat_one.taData_strat_one.h_highs_trail_vec, 2)
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        closes = ctx.entry_context.talibbars.close
        ath = closes[-1] == max(closes)
        condition_1 = ctx.bars[1].close > ctx.strategy.ta_strat_one.taData_strat_one.h_highs_trail_vec[-2]
        if not (condition_1 and ath):
            return

        ctx.strategy.logger.info("Longing ATH trail breakout.")
        if ctx.strategy.telegram is not None:
            ctx.strategy.telegram.send_log("Longing ATH trail breakout.")

        base_entry = ctx.bars[0].close
        base_stop = ctx.bars[1].low
        primary_entry, _, _ = _open_with_execution(
            ctx,
            direction=PositionDirection.LONG,
            base_entry=base_entry,
            base_stop=base_stop,
            default_order_type="Market",
            options=self.execution,
        )

        if self.execution.secondary_enabled:
            ctx.strategy.logger.info("Sending additional long.")
            if ctx.strategy.telegram is not None:
                ctx.strategy.telegram.send_log("Sending additional long.")
            secondary_entry = primary_entry - self.execution.secondary_entry_offset_atr * _as_float(ctx.entry_context.atr, 0.0)
            secondary_stop = secondary_entry - self.execution.secondary_stop_atr_mult * _as_float(ctx.entry_context.atr_min, 0.0)
            ctx.strategy.open_new_position(
                entry=secondary_entry,
                stop=secondary_stop,
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
        entry_2_swing_depth: int = 40,
        entry_2_entry_buffer_atr: float = 0.05,
        entry_2_max_natr: float = 1,
        entry_2_min_rsi_4h: int = 50,
        entry_2_min_rsi_d: int = 80,
        entry_2_min_natr: float = 1,
        entry_2_min_rsi_4h_short: int = 50,
        entry_2_min_rsi_d_short: int = 50,
        entry_2_use_min_natr: bool = False,
        entry_2_enable_short: bool = False,
        entry_2_require_not_bearish_long: bool = True,
        entry_2_require_not_trending_long: bool = True,
        entry_2_require_not_bullish_short: bool = True,
        entry_2_require_not_trending_short: bool = True,
        entry_2_expected_exit_slippage_pct: float = 0.0015,
        entry_2_expected_entry_slippage_pct: float = 0.0015,
        allow_long: bool = True,
        allow_short: bool = True,
        execution: ExecutionOptions = ExecutionOptions(),
    ):
        self.active = active
        self.entry_2_swing_depth = max(8, int(entry_2_swing_depth))
        self.entry_2_entry_buffer_atr = max(0.0, float(entry_2_entry_buffer_atr))
        self.entry_2_max_natr = entry_2_max_natr
        self.entry_2_min_rsi_4h = entry_2_min_rsi_4h
        self.entry_2_min_rsi_d = entry_2_min_rsi_d
        self.entry_2_min_natr = entry_2_min_natr
        self.entry_2_min_rsi_4h_short = entry_2_min_rsi_4h_short
        self.entry_2_min_rsi_d_short = entry_2_min_rsi_d_short
        self.entry_2_use_min_natr = entry_2_use_min_natr
        self.entry_2_enable_short = entry_2_enable_short
        self.entry_2_require_not_bearish_long = bool(entry_2_require_not_bearish_long)
        self.entry_2_require_not_trending_long = bool(entry_2_require_not_trending_long)
        self.entry_2_require_not_bullish_short = bool(entry_2_require_not_bullish_short)
        self.entry_2_require_not_trending_short = bool(entry_2_require_not_trending_short)
        self.entry_2_expected_exit_slippage_pct = entry_2_expected_exit_slippage_pct
        self.entry_2_expected_entry_slippage_pct = entry_2_expected_entry_slippage_pct
        self.allow_long = allow_long
        self.allow_short = allow_short
        self.execution = execution

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        return bool(self.active)

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        needed_bars = max(45, self.entry_2_swing_depth + 3)
        return (
            _len_at_least(ctx.bars, needed_bars)
            and _len_at_least(ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_4h_vec, 1)
            and ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_d is not None
            and ctx.entry_context.natr_4h is not None
            and ctx.entry_context.atr is not None
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        long_entry, short_entry, stop_long, stop_short, long_amount, short_amount, _, _ = calc_entry_and_exit(
            ctx.strategy,
            ctx.bars,
            swing_depth=self.entry_2_swing_depth,
            entry_buffer_atr=self.entry_2_entry_buffer_atr,
        )
        if long_entry is None or short_entry is None:
            return

        condition_1 = ctx.entry_context.natr_4h < self.entry_2_max_natr
        condition_2 = ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_4h_vec[-1] < self.entry_2_min_rsi_4h
        condition_3 = ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_d > self.entry_2_min_rsi_d
        condition_8 = (not self.entry_2_require_not_bearish_long) or (not ctx.entry_context.market_bearish)
        condition_9 = (not self.entry_2_require_not_trending_long) or (not ctx.entry_context.market_trending)
        min_natr_pass = True
        if self.entry_2_use_min_natr:
            min_natr_pass = ctx.entry_context.natr_4h > self.entry_2_min_natr
        bullish_conditions = condition_1 and condition_2 and condition_3 and condition_8 and condition_9 and min_natr_pass

        bearish_conditions = False
        if self.entry_2_enable_short:
            bearish_conditions = (
                ctx.entry_context.natr_4h > self.entry_2_min_natr
                and ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_4h_vec[-1] > self.entry_2_min_rsi_4h_short
                and ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_d > self.entry_2_min_rsi_d_short
                and ((not self.entry_2_require_not_bullish_short) or (not ctx.entry_context.market_bullish))
                and ((not self.entry_2_require_not_trending_short) or (not ctx.entry_context.market_trending))
            )

        if self.execution.order_type != "legacy" or self.execution.entry_offset_atr != 0 or self.execution.entry_offset_pct != 0:
            long_entry = _resolve_entry_price(ctx, PositionDirection.LONG, long_entry, self.execution)
            short_entry = _resolve_entry_price(ctx, PositionDirection.SHORT, short_entry, self.execution)

        if (
            self.execution.sl_module_enabled
            or self.execution.stop_mode != "legacy"
            or self.execution.stop_buffer_atr != 0
            or self.execution.stop_ref_profile_enabled
        ):
            stop_long = _stop_from_mode(ctx, PositionDirection.LONG, long_entry, stop_long, self.execution)
            stop_short = _stop_from_mode(ctx, PositionDirection.SHORT, short_entry, stop_short, self.execution)

            expected_exit_slippage_per = self.entry_2_expected_exit_slippage_pct
            expected_entry_slippage_per = (
                self.entry_2_expected_entry_slippage_pct if ctx.strategy.limit_entry_offset_perc is None else 0
            )
            long_amount = ctx.strategy.calc_pos_size(
                risk=ctx.strategy.risk_factor,
                exitPrice=stop_long * (1 - expected_exit_slippage_per),
                entry=long_entry * (1 + expected_entry_slippage_per),
                atr=0,
            )
            short_amount = ctx.strategy.calc_pos_size(
                risk=ctx.strategy.risk_factor,
                exitPrice=stop_short * (1 + expected_exit_slippage_per),
                entry=short_entry * (1 - expected_entry_slippage_per),
                atr=0,
            )

        found_long = False
        found_short = False
        if bullish_conditions or bearish_conditions:
            found_long, found_short = ctx.strategy.update_existing_entries(
                ctx.account,
                ctx.open_positions,
                long_entry,
                short_entry,
                stop_long,
                stop_short,
                long_amount,
                short_amount,
            )

        if (
            not found_long
            and self.allow_long
            and ctx.strategy.longsAllowed
            and ctx.direction_filter >= 0
            and bullish_conditions
        ):
            execution_type = _normalize_order_type(self.execution.order_type, "StopLimit")
            ctx.strategy.open_new_position(
                PositionDirection.LONG,
                ctx.bars,
                stop_long,
                ctx.open_positions,
                long_entry,
                execution_type,
            )
            if ctx.strategy.telegram is not None:
                ctx.strategy.telegram.send_log("Entry strategy 2: Sending long StopLimit entry order.")

        if (
            not found_short
            and self.allow_short
            and ctx.strategy.shortsAllowed
            and ctx.direction_filter <= 0
            and short_entry is not None
            and bearish_conditions
        ):
            execution_type = _normalize_order_type(self.execution.order_type, "StopLimit")
            ctx.strategy.open_new_position(
                PositionDirection.SHORT,
                ctx.bars,
                stop_short,
                ctx.open_positions,
                short_entry,
                execution_type,
            )
            if ctx.strategy.telegram is not None:
                ctx.strategy.telegram.send_log("Entry strategy 2: Sending short StopLimit entry order.")


class Entry3Module(EntryModule):
    name = "entry_3"

    def __init__(
        self,
        active=None,
        entry_3_max_natr: float = 2,
        entry_3_rsi_4h: int = 50,
        entry_3_atr_fac: float = 1,
        entry_3_vol_fac: float = 2.0,
        entry_3_use_vol_filter: bool = False,
        entry_3_rsi_d_min: int = 50,
        entry_3_max_std_atr: float = 4.0,
        entry_3_stop_atr_mult: float = 1.0,
        entry_3_require_red_trigger_bar: bool = True,
        entry_3_require_market_bullish: bool = True,
        entry_3_require_not_trending: bool = True,
        allow_long: bool = True,
        allow_short: bool = False,
        execution: ExecutionOptions = ExecutionOptions(),
    ):
        self.active = active
        self.entry_3_max_natr = entry_3_max_natr
        self.entry_3_rsi_4h = entry_3_rsi_4h
        self.entry_3_atr_fac = entry_3_atr_fac
        self.entry_3_vol_fac = entry_3_vol_fac
        self.entry_3_use_vol_filter = entry_3_use_vol_filter
        self.entry_3_rsi_d_min = entry_3_rsi_d_min
        self.entry_3_max_std_atr = entry_3_max_std_atr
        self.entry_3_stop_atr_mult = entry_3_stop_atr_mult
        self.entry_3_require_red_trigger_bar = bool(entry_3_require_red_trigger_bar)
        self.entry_3_require_market_bullish = bool(entry_3_require_market_bullish)
        self.entry_3_require_not_trending = bool(entry_3_require_not_trending)
        self.allow_long = allow_long
        self.allow_short = allow_short
        self.execution = execution

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        return bool(self.active) and self.allow_long and not ctx.longed and ctx.strategy.longsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        return (
            _len_at_least(ctx.bars, 2)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.highs_trail_4h_vec, 2)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.rsi_4h_vec, 1)
            and ctx.strategy.ta_data_trend_strat.rsi_d is not None
            and ctx.entry_context.natr_4h is not None
            and ctx.entry_context.std is not None
            and ctx.entry_context.atr is not None
            and _len_at_least(ctx.strategy.ta_data_trend_strat.volume_sma_4h_vec, 1)
            and ctx.strategy.ta_data_trend_strat.volume_4h is not None
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        condition_1 = ctx.bars[1].high > ctx.strategy.ta_data_trend_strat.highs_trail_4h_vec[-2]
        condition_3 = ctx.strategy.ta_data_trend_strat.rsi_4h_vec[-1] > self.entry_3_rsi_4h
        condition_4 = ctx.strategy.ta_data_trend_strat.rsi_d > self.entry_3_rsi_d_min
        condition_5 = (not self.entry_3_require_red_trigger_bar) or (ctx.bars[1].open > ctx.bars[1].close)
        condition_8 = (not self.entry_3_require_not_trending) or (not ctx.entry_context.market_trending)
        condition_9 = self.entry_3_max_natr > ctx.entry_context.natr_4h
        condition_10 = ctx.entry_context.std < self.entry_3_max_std_atr * ctx.entry_context.atr
        condition_11 = True
        if self.entry_3_use_vol_filter:
            condition_11 = (
                ctx.strategy.ta_data_trend_strat.volume_sma_4h_vec[-1] * self.entry_3_vol_fac
                < ctx.strategy.ta_data_trend_strat.volume_4h
            )

        market_bullish_ok = (not self.entry_3_require_market_bullish) or ctx.entry_context.market_bullish
        if condition_1 and condition_5 and market_bullish_ok and condition_3 and condition_4 and condition_8 and condition_9 and condition_10 and condition_11:
            ctx.strategy.logger.info("Longing trail break pullback.")
            if ctx.strategy.telegram is not None:
                ctx.strategy.telegram.send_log("Longing trail break pullback.")
            base_entry = ctx.bars[0].close - self.entry_3_atr_fac * ctx.entry_context.atr
            base_stop = base_entry - self.entry_3_stop_atr_mult * ctx.entry_context.atr
            _open_with_execution(
                ctx,
                direction=PositionDirection.LONG,
                base_entry=base_entry,
                base_stop=base_stop,
                default_order_type="Limit",
                options=self.execution,
            )


class Entry4Module(EntryModule):
    name = "entry_4"

    def __init__(
        self,
        active=None,
        entry_4_breakout_atr_mult: float = 1.0,
        entry_4_rearm_lookback: int = 300,
        allow_long: bool = True,
        allow_short: bool = False,
        execution: ExecutionOptions = ExecutionOptions(),
    ):
        self.active = active
        self.entry_4_breakout_atr_mult = max(0.0, float(entry_4_breakout_atr_mult))
        self.entry_4_rearm_lookback = max(20, int(entry_4_rearm_lookback))
        self.allow_long = allow_long
        self.allow_short = allow_short
        self.execution = execution

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        return bool(self.active) and self.allow_long and not ctx.longed and ctx.strategy.longsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        atr_vec = ctx.strategy.ta_data_trend_strat.atr_4h_vec
        return (
            _len_at_least(ctx.bars, 2)
            and _len_at_least(ctx.entry_context.middleband_vec, 1)
            and _len_at_least(atr_vec, 1)
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        middle_vec = ctx.entry_context.middleband_vec
        atr_vec = ctx.strategy.ta_data_trend_strat.atr_4h_vec
        max_scan = min(
            int(self.entry_4_rearm_lookback),
            len(ctx.bars) - 1,
            len(middle_vec),
            len(atr_vec),
        )
        if max_scan < 2:
            return

        atr_mult = self.entry_4_breakout_atr_mult

        def signal_at(idx: int) -> bool:
            close_i = _as_float(ctx.bars[idx].close, float("nan"))
            middle_i = _as_float(middle_vec[-idx], float("nan"))
            atr_i = _as_float(atr_vec[-idx], float("nan"))
            if close_i != close_i or middle_i != middle_i or atr_i != atr_i or atr_i <= 0.0:
                return False
            return close_i > middle_i + atr_i * atr_mult

        def wick_below_middle_at(idx: int) -> bool:
            middle_i = _as_float(middle_vec[-idx], float("nan"))
            low_i = _as_float(ctx.bars[idx].low, float("nan"))
            if middle_i != middle_i or low_i != low_i:
                return False
            return low_i < middle_i

        # Core trigger: previous close above BB middle + ATR multiple.
        if not signal_at(1):
            return

        # Stateless re-arm gate: from most recent history backwards, first event
        # must be a wick below middleband; if a prior breakout comes first, block.
        rearmed = True
        for idx in range(2, max_scan + 1):
            if wick_below_middle_at(idx):
                rearmed = True
                break
            if signal_at(idx):
                rearmed = False
                break
        if not rearmed:
            return

        ctx.strategy.logger.info("Longing BB-middle ATR breakout (entry_4).")
        if ctx.strategy.telegram is not None:
            ctx.strategy.telegram.send_log("Longing BB-middle ATR breakout (entry_4).")

        base_entry = ctx.bars[0].close
        base_stop = ctx.bars[1].low
        _open_with_execution(
            ctx,
            direction=PositionDirection.LONG,
            base_entry=base_entry,
            base_stop=base_stop,
            default_order_type="Market",
            options=self.execution,
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
        allow_long: bool = False,
        allow_short: bool = True,
        execution: ExecutionOptions = ExecutionOptions(),
    ):
        self.active = active
        self.entry_5_rsi_d = entry_5_rsi_d
        self.entry_5_rsi_4h = entry_5_rsi_4h
        self.entry_5_atr_fac = entry_5_atr_fac
        self.entry_5_trail_1_period = entry_5_trail_1_period
        self.entry_5_trail_2_period = entry_5_trail_2_period
        self.entry_5_vol_fac = entry_5_vol_fac
        self.allow_long = allow_long
        self.allow_short = allow_short
        self.execution = execution

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        return bool(self.active) and self.allow_short and not ctx.shorted and ctx.strategy.shortsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        needed = max(self.entry_5_trail_1_period, self.entry_5_trail_2_period) + 2
        return (
            _len_at_least(ctx.bars, 2)
            and _len_at_least(ctx.strategy.ta_strat_one.taData_strat_one.h_body_lows_trail_vec, needed)
            and ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_d is not None
            and _len_at_least(ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_4h_vec, 1)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.volume_sma_4h_vec, 1)
            and ctx.strategy.ta_data_trend_strat.volume_4h is not None
            and ctx.entry_context.atr_trail_mix is not None
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
            base_entry = ctx.bars[0].close
            base_stop = min(ctx.bars[1].high, ctx.bars[0].close + ctx.entry_context.atr_trail_mix * self.entry_5_atr_fac)
            _open_with_execution(
                ctx,
                direction=PositionDirection.SHORT,
                base_entry=base_entry,
                base_stop=base_stop,
                default_order_type="Market",
                options=self.execution,
            )


class Entry6Module(EntryModule):
    name = "entry_6"

    def __init__(
        self,
        active=None,
        entry_6_rsi_4h_max: int = 90,
        entry_6_rsi_4h_min: int = 75,
        entry_6_max_natr: float = 2,
        entry_6_atr_fac: float = 5,
        entry_6_short_max_bar_range_atr: float = 1.0,
        entry_6_swing_depth: int = 40,
        entry_6_require_not_bearish_long: bool = True,
        entry_6_require_short_open_above_ema: bool = True,
        allow_long: bool = True,
        allow_short: bool = True,
        execution: ExecutionOptions = ExecutionOptions(),
    ):
        self.active = active
        self.entry_6_rsi_4h_max = entry_6_rsi_4h_max
        self.entry_6_rsi_4h_min = entry_6_rsi_4h_min
        self.entry_6_max_natr = entry_6_max_natr
        self.entry_6_atr_fac = entry_6_atr_fac
        self.entry_6_short_max_bar_range_atr = entry_6_short_max_bar_range_atr
        self.entry_6_swing_depth = max(5, int(entry_6_swing_depth))
        self.entry_6_require_not_bearish_long = bool(entry_6_require_not_bearish_long)
        self.entry_6_require_short_open_above_ema = bool(entry_6_require_short_open_above_ema)
        self.allow_long = allow_long
        self.allow_short = allow_short
        self.execution = execution

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        return bool(self.active)

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
        depth = self.entry_6_swing_depth
        found_swing_high = False
        found_swing_low = False
        idx_swing_high = 0
        idx_swing_low = 0
        for i in range(3, depth):
            if ctx.bars[i + 2].close < ctx.bars[i + 1].close < ctx.bars[i].close > ctx.bars[i - 1].close:
                found_swing_high = True
                idx_swing_high = i
                break
        if found_swing_high:
            close_values = [bar.close for bar in ctx.bars[2:idx_swing_high]]
            already_longed = any(close > ctx.bars[idx_swing_high].high for close in close_values)
        else:
            already_longed = True
        for i in range(3, depth):
            if (
                ctx.bars[i + 3].low > ctx.bars[i + 2].low > ctx.bars[i + 1].low
                > ctx.bars[i].low < ctx.bars[i - 1].low < ctx.bars[i - 2].low
            ):
                found_swing_low = True
                idx_swing_low = i
                break
        if found_swing_low:
            close_values = [bar.close for bar in ctx.bars[2:idx_swing_low]]
            already_shorted = any(close < ctx.bars[idx_swing_low].low for close in close_values)
        else:
            already_shorted = True

        if (
            found_swing_high
            and found_swing_low
            and self.allow_long
            and not ctx.longed
            and not already_longed
            and not already_shorted
            and ctx.strategy.longsAllowed
        ):
            condition_1 = (
                self.entry_6_rsi_4h_max > ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_4h_vec[-1]
                > self.entry_6_rsi_4h_min
            )
            condition_2 = ctx.entry_context.natr_4h < self.entry_6_max_natr
            condition_3 = (not self.entry_6_require_not_bearish_long) or (not ctx.entry_context.market_bearish)
            if ctx.bars[1].close > ctx.bars[idx_swing_high].high and condition_2 and condition_1 and condition_3:
                ctx.strategy.logger.info("Longing swing breakout.")
                if ctx.strategy.telegram is not None:
                    ctx.strategy.telegram.send_log("Longing swing breakout.")
                if ctx.bars[1].close > ctx.bars[1].open:
                    base_stop = ctx.bars[1].low
                else:
                    base_stop = ctx.bars[1].low - self.entry_6_atr_fac * ctx.entry_context.atr_trail_mix
                _open_with_execution(
                    ctx,
                    direction=PositionDirection.LONG,
                    base_entry=ctx.bars[0].close,
                    base_stop=base_stop,
                    default_order_type="Market",
                    options=self.execution,
                )

        if (
            found_swing_low
            and found_swing_high
            and self.allow_short
            and not ctx.shorted
            and not already_shorted
            and not already_longed
            and ctx.strategy.shortsAllowed
        ):
            condition_2 = (not self.entry_6_require_short_open_above_ema) or (ctx.bars[1].open > ctx.strategy.ta_data_trend_strat.ema_w)
            condition_10 = (
                (ctx.bars[1].high - ctx.bars[1].low)
                < self.entry_6_short_max_bar_range_atr * ctx.entry_context.atr
            )
            if ctx.bars[1].close < ctx.bars[idx_swing_low].low and condition_2 and condition_10:
                ctx.strategy.logger.info("Shorting swing break.")
                if ctx.strategy.telegram is not None:
                    ctx.strategy.telegram.send_log("Shorting swing break.")
                _open_with_execution(
                    ctx,
                    direction=PositionDirection.SHORT,
                    base_entry=ctx.bars[0].close,
                    base_stop=max(ctx.bars[1].high, ctx.bars[2].high),
                    default_order_type="Market",
                    options=self.execution,
                )


class Entry7Module(EntryModule):
    name = "entry_7"

    def __init__(
        self,
        active=None,
        entry_7_std_fac: float = 1,
        entry_7_4h_rsi: float = 2.5,
        entry_7_vol_fac: float = 2,
        entry_7_use_std_filter: bool = False,
        entry_7_use_rsi_filter: bool = False,
        entry_7_use_vol_filter: bool = False,
        entry_7_require_prev_body_gt_lower_wick: bool = True,
        entry_7_require_sfp_upper_wick_gt_body: bool = True,
        entry_7_require_not_trending: bool = True,
        allow_long: bool = False,
        allow_short: bool = True,
        execution: ExecutionOptions = ExecutionOptions(),
    ):
        self.active = active
        self.entry_7_std_fac = entry_7_std_fac
        self.entry_7_4h_rsi = entry_7_4h_rsi
        self.entry_7_vol_fac = entry_7_vol_fac
        self.entry_7_use_std_filter = entry_7_use_std_filter
        self.entry_7_use_rsi_filter = entry_7_use_rsi_filter
        self.entry_7_use_vol_filter = entry_7_use_vol_filter
        self.entry_7_require_prev_body_gt_lower_wick = bool(entry_7_require_prev_body_gt_lower_wick)
        self.entry_7_require_sfp_upper_wick_gt_body = bool(entry_7_require_sfp_upper_wick_gt_body)
        self.entry_7_require_not_trending = bool(entry_7_require_not_trending)
        self.allow_long = allow_long
        self.allow_short = allow_short
        self.execution = execution

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        return bool(self.active) and self.allow_short and not ctx.shorted and ctx.strategy.shortsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        return (
            _len_at_least(ctx.bars, 4)
            and _len_at_least(ctx.strategy.ta_strat_one.taData_strat_one.h_highs_trail_vec, 3)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.rsi_4h_vec, 1)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.volume_sma_4h_vec, 1)
            and ctx.strategy.ta_data_trend_strat.volume_4h is not None
            and ctx.entry_context.std is not None
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        condition_1 = ctx.bars[2].high > ctx.bars[1].high
        condition_2 = ctx.bars[2].high > ctx.strategy.ta_strat_one.taData_strat_one.h_highs_trail_vec[-3]
        condition_3 = (not self.entry_7_require_prev_body_gt_lower_wick) or (
            abs(ctx.bars[1].close - ctx.bars[1].open) > abs(ctx.bars[1].close - ctx.bars[1].low)
        )
        condition_5 = (not self.entry_7_require_sfp_upper_wick_gt_body) or (
            ctx.bars[2].high - max(ctx.bars[2].close, ctx.bars[2].open) > abs(ctx.bars[2].close - ctx.bars[2].open)
        )
        condition_10 = (not self.entry_7_require_not_trending) or (not ctx.entry_context.market_trending)

        condition_11 = True
        if self.entry_7_use_std_filter:
            condition_11 = abs(ctx.bars[1].close - ctx.bars[1].open) > self.entry_7_std_fac * _as_float(ctx.entry_context.std, 0.0)
        condition_12 = True
        if self.entry_7_use_rsi_filter:
            condition_12 = ctx.strategy.ta_data_trend_strat.rsi_4h_vec[-1] > self.entry_7_4h_rsi
        condition_13 = True
        if self.entry_7_use_vol_filter:
            condition_13 = (
                ctx.strategy.ta_data_trend_strat.volume_sma_4h_vec[-1] * self.entry_7_vol_fac
                < ctx.strategy.ta_data_trend_strat.volume_4h
            )

        if condition_1 and condition_2 and condition_3 and condition_5 and condition_10 and condition_11 and condition_12 and condition_13:
            ctx.strategy.logger.info("Shorting 4H SFP")
            if ctx.strategy.telegram is not None:
                ctx.strategy.telegram.send_log("Shorting 4H SFP")
            _open_with_execution(
                ctx,
                direction=PositionDirection.SHORT,
                base_entry=ctx.bars[0].close,
                base_stop=max(ctx.bars[2].high, ctx.bars[1].high, ctx.bars[3].high),
                default_order_type="Market",
                options=self.execution,
            )


class Entry8Module(EntryModule):
    name = "entry_8"

    def __init__(
        self,
        active=None,
        entry_8_vol_fac: float = 2.0,
        entry_8_require_ranging_regime: bool = True,
        allow_long: bool = False,
        allow_short: bool = True,
        execution: ExecutionOptions = ExecutionOptions(),
    ):
        self.active = active
        self.entry_8_vol_fac = entry_8_vol_fac
        self.entry_8_require_ranging_regime = bool(entry_8_require_ranging_regime)
        self.allow_long = allow_long
        self.allow_short = allow_short
        self.execution = execution

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        return bool(self.active) and self.allow_short and not ctx.shorted and ctx.strategy.shortsAllowed

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
        condition_6 = (not self.entry_8_require_ranging_regime) or (
            ctx.strategy.ta_trend_strat.taData_trend_strat.marketDynamic == MarketDynamic.RANGING
        )
        if condition_1 and condition_2 and condition_4 and condition_6:
            ctx.strategy.logger.info("Shorting rapid sell-off")
            if ctx.strategy.telegram is not None:
                ctx.strategy.telegram.send_log("Shorting rapid sell-off")
            _open_with_execution(
                ctx,
                direction=PositionDirection.SHORT,
                base_entry=ctx.bars[0].close,
                base_stop=ctx.bars[1].high,
                default_order_type="Market",
                options=self.execution,
            )


class Entry9Module(EntryModule):
    name = "entry_9"

    def __init__(
        self,
        active=None,
        entry_9_std: float = 1,
        entry_9_4h_rsi: int = 50,
        entry_9_atr: float = 2,
        entry_9_require_lower_open: bool = True,
        entry_9_require_ranging_regime: bool = True,
        allow_long: bool = False,
        allow_short: bool = True,
        execution: ExecutionOptions = ExecutionOptions(),
    ):
        self.active = active
        self.entry_9_std = entry_9_std
        self.entry_9_4h_rsi = entry_9_4h_rsi
        self.entry_9_atr = entry_9_atr
        self.entry_9_require_lower_open = bool(entry_9_require_lower_open)
        self.entry_9_require_ranging_regime = bool(entry_9_require_ranging_regime)
        self.allow_long = allow_long
        self.allow_short = allow_short
        self.execution = execution

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        return bool(self.active) and self.allow_short and not ctx.shorted and ctx.strategy.shortsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        return (
            _len_at_least(ctx.bars, 3)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.lows_trail_4h_vec, 2)
            and _len_at_least(ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_4h_vec, 1)
            and _len_at_least(ctx.entry_context.middleband_vec, 2)
            and _len_at_least(ctx.entry_context.std_vec, 2)
            and ctx.entry_context.atr is not None
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        condition_1 = ctx.bars[1].low < ctx.strategy.ta_data_trend_strat.lows_trail_4h_vec[-2] < ctx.bars[1].close < ctx.bars[1].open
        condition_2 = (not self.entry_9_require_lower_open) or (ctx.bars[1].open < ctx.bars[2].open)
        condition_3 = ctx.bars[1].close > ctx.entry_context.middleband_vec[-2] - ctx.entry_context.std_vec[-2] * self.entry_9_std
        condition_5 = ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_4h_vec[-1] < self.entry_9_4h_rsi
        condition_7 = (not self.entry_9_require_ranging_regime) or (
            ctx.strategy.ta_trend_strat.taData_trend_strat.marketDynamic == MarketDynamic.RANGING
        )
        if condition_1 and condition_2 and condition_3 and condition_5 and condition_7:
            ctx.strategy.logger.info("Shorting short trail tap")
            if ctx.strategy.telegram is not None:
                ctx.strategy.telegram.send_log("Shorting short trail tap")
            base_entry = ctx.bars[0].close
            base_stop = ctx.bars[1].high + self.entry_9_atr * ctx.entry_context.atr
            _open_with_execution(
                ctx,
                direction=PositionDirection.SHORT,
                base_entry=base_entry,
                base_stop=base_stop,
                default_order_type="Market",
                options=self.execution,
            )


class Entry11Module(EntryModule):
    name = "entry_11"

    def __init__(
        self,
        active=None,
        entry_11_vol: float = 3.0,
        entry_11_atr: float = 3.0,
        entry_11_natr: float = 3.0,
        allow_long: bool = True,
        allow_short: bool = False,
        execution: ExecutionOptions = ExecutionOptions(),
    ):
        self.active = active
        self.entry_11_vol = entry_11_vol
        self.entry_11_atr = entry_11_atr
        self.entry_11_natr = entry_11_natr
        self.allow_long = allow_long
        self.allow_short = allow_short
        self.execution = execution

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        return bool(self.active) and self.allow_long and not ctx.longed and ctx.strategy.longsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        return (
            _len_at_least(ctx.bars, 2)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.volume_sma_4h_vec, 1)
            and ctx.strategy.ta_data_trend_strat.volume_4h is not None
            and ctx.entry_context.natr_4h is not None
            and ctx.entry_context.atr is not None
            and ctx.entry_context.atr_min is not None
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        condition_1 = ctx.strategy.ta_data_trend_strat.volume_sma_4h_vec[-1] * self.entry_11_vol > ctx.strategy.ta_data_trend_strat.volume_4h
        condition_2 = (ctx.bars[1].close - ctx.bars[1].open) > self.entry_11_atr * ctx.entry_context.atr
        condition_3 = ctx.entry_context.natr_4h < self.entry_11_natr
        if not (condition_1 and condition_2 and condition_3):
            return

        ctx.strategy.logger.info("Longing momentum")
        if ctx.strategy.telegram is not None:
            ctx.strategy.telegram.send_log("Longing momentum")
        primary_entry, _, _ = _open_with_execution(
            ctx,
            direction=PositionDirection.LONG,
            base_entry=ctx.bars[0].close,
            base_stop=ctx.bars[0].close - ctx.strategy.sl_atr_fac * ctx.entry_context.atr,
            default_order_type="Market",
            options=self.execution,
        )

        if self.execution.secondary_enabled:
            ctx.strategy.logger.info("Sending additional long")
            if ctx.strategy.telegram is not None:
                ctx.strategy.telegram.send_log("Sending additional long")
            secondary_entry = primary_entry - self.execution.secondary_entry_offset_atr * _as_float(ctx.entry_context.atr, 0.0)
            secondary_stop = secondary_entry - self.execution.secondary_stop_atr_mult * _as_float(ctx.entry_context.atr_min, 0.0)
            ctx.strategy.open_new_position(
                entry=secondary_entry,
                stop=secondary_stop,
                open_positions=ctx.open_positions,
                bars=ctx.bars,
                direction=PositionDirection.LONG,
                ExecutionType="Limit",
            )


class Entry12Module(EntryModule):
    name = "entry_12"

    def __init__(
        self,
        active=None,
        entry_12_vol: float = 3.0,
        entry_12_rsi_4h: int = 3,
        entry_12_atr: float = 3.0,
        entry_12_max_rsi_4h: int = 90,
        entry_12_require_structure_1: bool = True,
        entry_12_require_structure_2: bool = True,
        entry_12_require_not_trending: bool = True,
        allow_long: bool = True,
        allow_short: bool = False,
        execution: ExecutionOptions = ExecutionOptions(),
    ):
        self.active = active
        self.entry_12_vol = entry_12_vol
        self.entry_12_rsi_4h = entry_12_rsi_4h
        self.entry_12_atr = entry_12_atr
        self.entry_12_max_rsi_4h = entry_12_max_rsi_4h
        self.entry_12_require_structure_1 = bool(entry_12_require_structure_1)
        self.entry_12_require_structure_2 = bool(entry_12_require_structure_2)
        self.entry_12_require_not_trending = bool(entry_12_require_not_trending)
        self.allow_long = allow_long
        self.allow_short = allow_short
        self.execution = execution

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        return bool(self.active) and self.allow_long and not ctx.longed and ctx.strategy.longsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        talibbars = ctx.entry_context.talibbars
        return (
            _len_at_least(ctx.bars, 5)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.atr_4h_vec, 4)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.volume_sma_4h_vec, 4)
            and _len_at_least(talibbars.volume, 3)
            and _len_at_least(ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_4h_vec, 1)
            and ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_d is not None
            and ctx.entry_context.atr_min is not None
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        condition_1 = (ctx.bars[4].open - ctx.bars[4].close) > self.entry_12_atr * ctx.strategy.ta_data_trend_strat.atr_4h_vec[-4]
        condition_3 = (not self.entry_12_require_structure_1) or (
            ctx.bars[2].open < ctx.bars[4].open > ctx.bars[2].low > ctx.bars[4].low
        )
        condition_4_raw = (
            ctx.bars[4].low < ctx.bars[1].low < ctx.bars[4].open > ctx.bars[1].open > ctx.bars[4].low
            and ctx.bars[4].open > ctx.bars[1].close
        )
        condition_4 = (not self.entry_12_require_structure_2) or condition_4_raw
        condition_6 = (
            self.entry_12_max_rsi_4h < ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_d
            or ctx.strategy.ta_trend_strat.taData_trend_strat.rsi_4h_vec[-1] > self.entry_12_rsi_4h
        )
        condition_10 = ctx.strategy.ta_data_trend_strat.volume_sma_4h_vec[-4] * self.entry_12_vol > ctx.entry_context.talibbars.volume[-3]
        condition_8 = (not self.entry_12_require_not_trending) or (not ctx.entry_context.market_trending)
        if condition_1 and condition_3 and condition_4 and condition_6 and condition_10 and condition_8:
            ctx.strategy.logger.info("Longing reversal")
            if ctx.strategy.telegram is not None:
                ctx.strategy.telegram.send_log("Longing reversal.")
            _open_with_execution(
                ctx,
                direction=PositionDirection.LONG,
                base_entry=ctx.bars[0].close,
                base_stop=ctx.bars[0].close - ctx.strategy.sl_atr_fac * ctx.entry_context.atr_min,
                default_order_type="Market",
                options=self.execution,
            )


class Entry15Module(EntryModule):
    name = "entry_15"

    def __init__(
        self,
        active=None,
        entry_15_squeeze_lookback: int = 6,
        entry_15_broad_core: bool = False,
        entry_15_squeeze_range_atr: float = 1.0,
        entry_15_breakout_buffer_atr: float = 0.1,
        allow_long: bool = True,
        allow_short: bool = False,
        execution: ExecutionOptions = ExecutionOptions(),
    ):
        self.active = active
        self.entry_15_squeeze_lookback = entry_15_squeeze_lookback
        self.entry_15_broad_core = entry_15_broad_core
        self.entry_15_squeeze_range_atr = entry_15_squeeze_range_atr
        self.entry_15_breakout_buffer_atr = entry_15_breakout_buffer_atr
        self.allow_long = allow_long
        self.allow_short = allow_short
        self.execution = execution

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        return bool(self.active) and self.allow_long and not ctx.longed and ctx.strategy.longsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        lookback = max(2, int(self.entry_15_squeeze_lookback))
        return (
            _len_at_least(ctx.bars, lookback + 3)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.highs_trail_4h_vec, 2)
            and ctx.entry_context.atr is not None
            and ctx.entry_context.atr > 0
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        lookback = max(2, int(self.entry_15_squeeze_lookback))
        atr = _as_float(ctx.entry_context.atr, 0.0)
        broad_core = bool(self.entry_15_broad_core)
        squeeze_window = ctx.bars[2 : 2 + lookback]
        squeeze_ranges = [(bar.high - bar.low) / atr for bar in squeeze_window]
        if broad_core:
            squeeze_ok = max(squeeze_ranges) <= self.entry_15_squeeze_range_atr * 1.15
        else:
            squeeze_ok = max(squeeze_ranges) <= self.entry_15_squeeze_range_atr
        local_high = max(bar.high for bar in squeeze_window)
        breakout_buffer = self.entry_15_breakout_buffer_atr
        if broad_core:
            breakout_buffer = max(0.0, breakout_buffer * 0.7)
        breakout_level = local_high + breakout_buffer * atr
        breakout_ok = (
            ctx.bars[1].close > breakout_level
            and ctx.bars[1].high > ctx.strategy.ta_data_trend_strat.highs_trail_4h_vec[-2]
        )
        if not (squeeze_ok and breakout_ok):
            return

        ctx.strategy.logger.info("Longing squeeze breakout.")
        if ctx.strategy.telegram is not None:
            ctx.strategy.telegram.send_log("Longing squeeze breakout.")
        stop_ref_low = min(bar.low for bar in ctx.bars[1 : 2 + lookback])
        base_entry = ctx.bars[0].close
        base_stop = stop_ref_low
        _open_with_execution(
            ctx,
            direction=PositionDirection.LONG,
            base_entry=base_entry,
            base_stop=base_stop,
            default_order_type="Market",
            options=self.execution,
        )


class Entry16Module(EntryModule):
    name = "entry_16"

    def __init__(
        self,
        active=None,
        entry_16_dump_atr: float = 2.0,
        entry_16_broad_core: bool = False,
        entry_16_band_std: float = 1.5,
        entry_16_reclaim_frac: float = 0.5,
        allow_long: bool = True,
        allow_short: bool = False,
        execution: ExecutionOptions = ExecutionOptions(),
    ):
        self.active = active
        self.entry_16_dump_atr = entry_16_dump_atr
        self.entry_16_broad_core = entry_16_broad_core
        self.entry_16_band_std = entry_16_band_std
        self.entry_16_reclaim_frac = entry_16_reclaim_frac
        self.allow_long = allow_long
        self.allow_short = allow_short
        self.execution = execution

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        return bool(self.active) and self.allow_long and not ctx.longed and ctx.strategy.longsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        return (
            _len_at_least(ctx.bars, 3)
            and _len_at_least(ctx.entry_context.middleband_vec, 3)
            and _len_at_least(ctx.entry_context.std_vec, 3)
            and ctx.entry_context.atr is not None
            and ctx.entry_context.atr > 0
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        atr = _as_float(ctx.entry_context.atr, 0.0)
        broad_core = bool(self.entry_16_broad_core)
        dump_range = ctx.bars[2].open - ctx.bars[2].close
        dump_mult = self.entry_16_dump_atr
        band_std = self.entry_16_band_std
        reclaim_frac = self.entry_16_reclaim_frac
        if broad_core:
            dump_mult = max(0.25, dump_mult * 0.65)
            band_std = max(0.3, band_std * 0.75)
            reclaim_frac = max(0.15, reclaim_frac * 0.5)
        dump_ok = dump_range > dump_mult * atr
        overshoot_level = ctx.entry_context.middleband_vec[-3] - ctx.entry_context.std_vec[-3] * band_std
        overshoot_ok = ctx.bars[2].low < overshoot_level
        reclaim_level = ctx.bars[2].close + dump_range * reclaim_frac
        reclaim_ok = ctx.bars[1].close > reclaim_level
        if broad_core:
            reclaim_ok = reclaim_ok or ctx.bars[1].close > (ctx.bars[2].close + 0.15 * dump_range)
        if not (dump_ok and overshoot_ok and reclaim_ok):
            return

        ctx.strategy.logger.info("Longing exhaustion reclaim.")
        if ctx.strategy.telegram is not None:
            ctx.strategy.telegram.send_log("Longing exhaustion reclaim.")
        base_entry = ctx.bars[0].close
        base_stop = min(ctx.bars[1].low, ctx.bars[2].low)
        _open_with_execution(
            ctx,
            direction=PositionDirection.LONG,
            base_entry=base_entry,
            base_stop=base_stop,
            default_order_type="Market",
            options=self.execution,
        )


class Entry17Module(EntryModule):
    name = "entry_17"

    def __init__(
        self,
        active=None,
        entry_17_break_lookback: int = 6,
        entry_17_fail_close_buffer_atr: float = 0.1,
        entry_17_wick_excess_atr: float = 0.2,
        entry_17_add_trigger_open_limit: bool = False,
        entry_17_limit_only_trigger_open: bool = False,
        entry_17_trigger_open_order_type: str = "Limit",
        allow_long: bool = False,
        allow_short: bool = True,
        execution: ExecutionOptions = ExecutionOptions(),
    ):
        self.active = active
        self.entry_17_break_lookback = entry_17_break_lookback
        self.entry_17_fail_close_buffer_atr = entry_17_fail_close_buffer_atr
        self.entry_17_wick_excess_atr = entry_17_wick_excess_atr
        self.entry_17_add_trigger_open_limit = entry_17_add_trigger_open_limit
        self.entry_17_limit_only_trigger_open = entry_17_limit_only_trigger_open
        self.entry_17_trigger_open_order_type = entry_17_trigger_open_order_type
        self.allow_long = allow_long
        self.allow_short = allow_short
        self.execution = execution

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        return bool(self.active) and self.allow_short and not ctx.shorted and ctx.strategy.shortsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        lookback = max(2, int(self.entry_17_break_lookback))
        return (
            _len_at_least(ctx.bars, lookback + 4)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.highs_trail_4h_vec, 3)
            and ctx.entry_context.atr is not None
            and ctx.entry_context.atr > 0
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        lookback = max(2, int(self.entry_17_break_lookback))
        atr = _as_float(ctx.entry_context.atr, 0.0)
        reference_high = max(bar.high for bar in ctx.bars[3 : 3 + lookback])
        breakout_level = max(reference_high, ctx.strategy.ta_data_trend_strat.highs_trail_4h_vec[-3])
        breakout_ok = ctx.bars[2].close > breakout_level and ctx.bars[2].high > breakout_level
        fail_close_level = breakout_level - self.entry_17_fail_close_buffer_atr * atr
        fail_close_ok = ctx.bars[1].close < fail_close_level and ctx.bars[1].close < ctx.bars[1].open
        wick_ok = ctx.bars[1].high > breakout_level + self.entry_17_wick_excess_atr * atr
        if not (breakout_ok and fail_close_ok and wick_ok):
            return

        ctx.strategy.logger.info("Shorting failed breakout trap.")
        if ctx.strategy.telegram is not None:
            ctx.strategy.telegram.send_log("Shorting failed breakout trap.")
        base_entry = ctx.bars[0].close
        base_stop = max(ctx.bars[1].high, ctx.bars[2].high)
        trigger_open_entry = ctx.bars[1].open
        trigger_order_type = _normalize_order_type(self.entry_17_trigger_open_order_type, "Limit")

        if self.entry_17_limit_only_trigger_open:
            limit_stop_mode = self.execution.stop_mode
            if str(limit_stop_mode or "legacy") in ("", "legacy"):
                limit_stop_mode = "atr_from_entry"
            limit_only_options = ExecutionOptions(
                order_type=trigger_order_type,
                entry_offset_atr=0.0,
                entry_offset_pct=0.0,
                sl_module_enabled=self.execution.sl_module_enabled,
                sl_module_atr_mult=self.execution.sl_module_atr_mult,
                stop_mode=limit_stop_mode,
                stop_atr_mult=self.execution.stop_atr_mult,
                stop_ref_bar_index=self.execution.stop_ref_bar_index,
                stop_buffer_atr=self.execution.stop_buffer_atr,
                stop_ref_profile_enabled=self.execution.stop_ref_profile_enabled,
                stop_ref_bar_1_source=self.execution.stop_ref_bar_1_source,
                stop_ref_bar_2_source=self.execution.stop_ref_bar_2_source,
                stop_ref_bar_3_source=self.execution.stop_ref_bar_3_source,
                stop_ref_bar_4_source=self.execution.stop_ref_bar_4_source,
                stop_ref_bar_5_source=self.execution.stop_ref_bar_5_source,
                secondary_enabled=False,
                secondary_entry_offset_atr=0.0,
                secondary_stop_atr_mult=1.0,
                fixed_stop_price=self.execution.fixed_stop_price,
            )
            _open_with_execution(
                ctx,
                direction=PositionDirection.SHORT,
                base_entry=trigger_open_entry,
                base_stop=base_stop,
                default_order_type=trigger_order_type,
                options=limit_only_options,
            )
            return

        _open_with_execution(
            ctx,
            direction=PositionDirection.SHORT,
            base_entry=base_entry,
            base_stop=base_stop,
            default_order_type="Market",
            options=self.execution,
        )

        if self.entry_17_add_trigger_open_limit:
            limit_stop_mode = self.execution.stop_mode
            if str(limit_stop_mode or "legacy") in ("", "legacy"):
                limit_stop_mode = "atr_from_entry"
            limit_options = ExecutionOptions(
                order_type=trigger_order_type,
                entry_offset_atr=0.0,
                entry_offset_pct=0.0,
                sl_module_enabled=self.execution.sl_module_enabled,
                sl_module_atr_mult=self.execution.sl_module_atr_mult,
                stop_mode=limit_stop_mode,
                stop_atr_mult=self.execution.stop_atr_mult,
                stop_ref_bar_index=self.execution.stop_ref_bar_index,
                stop_buffer_atr=self.execution.stop_buffer_atr,
                stop_ref_profile_enabled=self.execution.stop_ref_profile_enabled,
                stop_ref_bar_1_source=self.execution.stop_ref_bar_1_source,
                stop_ref_bar_2_source=self.execution.stop_ref_bar_2_source,
                stop_ref_bar_3_source=self.execution.stop_ref_bar_3_source,
                stop_ref_bar_4_source=self.execution.stop_ref_bar_4_source,
                stop_ref_bar_5_source=self.execution.stop_ref_bar_5_source,
                secondary_enabled=False,
                secondary_entry_offset_atr=0.0,
                secondary_stop_atr_mult=1.0,
                fixed_stop_price=self.execution.fixed_stop_price,
            )
            _open_with_execution(
                ctx,
                direction=PositionDirection.SHORT,
                base_entry=trigger_open_entry,
                base_stop=base_stop,
                default_order_type=trigger_order_type,
                options=limit_options,
                mark_opened=False,
            )


class Entry18Module(EntryModule):
    name = "entry_18"

    def __init__(
        self,
        active=None,
        entry_18_reject_lookback: int = 4,
        entry_18_reclaim_buffer_atr: float = 0.05,
        entry_18_tail_ratio_min: float = 1.2,
        allow_long: bool = True,
        allow_short: bool = False,
        execution: ExecutionOptions = ExecutionOptions(),
    ):
        self.active = active
        self.entry_18_reject_lookback = entry_18_reject_lookback
        self.entry_18_reclaim_buffer_atr = entry_18_reclaim_buffer_atr
        self.entry_18_tail_ratio_min = entry_18_tail_ratio_min
        self.allow_long = allow_long
        self.allow_short = allow_short
        self.execution = execution

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        return bool(self.active) and self.allow_long and not ctx.longed and ctx.strategy.longsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        lookback = max(2, int(self.entry_18_reject_lookback))
        return (
            _len_at_least(ctx.bars, lookback + 2)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.lows_trail_4h_vec, 2)
            and ctx.entry_context.atr is not None
            and ctx.entry_context.atr > 0
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        lookback = max(2, int(self.entry_18_reject_lookback))
        atr = _as_float(ctx.entry_context.atr, 0.0)
        reference_low = min(bar.low for bar in ctx.bars[2 : 2 + lookback])
        edge_level = min(reference_low, ctx.strategy.ta_data_trend_strat.lows_trail_4h_vec[-2])
        reclaim_level = edge_level + self.entry_18_reclaim_buffer_atr * atr
        lower_tail = min(ctx.bars[1].open, ctx.bars[1].close) - ctx.bars[1].low
        body = abs(ctx.bars[1].close - ctx.bars[1].open)
        tail_ratio = lower_tail / body if body > 0 else 99.0

        reject_ok = (
            ctx.bars[1].low < edge_level
            and ctx.bars[1].close > reclaim_level
            and ctx.bars[1].close > ctx.bars[1].open
            and tail_ratio >= self.entry_18_tail_ratio_min
        )
        if not reject_ok:
            return

        ctx.strategy.logger.info("Longing range-edge rejection.")
        if ctx.strategy.telegram is not None:
            ctx.strategy.telegram.send_log("Longing range-edge rejection.")
        base_entry = ctx.bars[0].close
        base_stop = ctx.bars[1].low
        _open_with_execution(
            ctx,
            direction=PositionDirection.LONG,
            base_entry=base_entry,
            base_stop=base_stop,
            default_order_type="Market",
            options=self.execution,
        )


class Entry19Module(EntryModule):
    name = "entry_19"

    def __init__(
        self,
        active=None,
        entry_19_body_atr_min: float = 1.0,
        entry_19_broad_core: bool = False,
        entry_19_breakout_lookback: int = 5,
        allow_long: bool = True,
        allow_short: bool = False,
        execution: ExecutionOptions = ExecutionOptions(),
    ):
        self.active = active
        self.entry_19_body_atr_min = entry_19_body_atr_min
        self.entry_19_broad_core = entry_19_broad_core
        self.entry_19_breakout_lookback = entry_19_breakout_lookback
        self.allow_long = allow_long
        self.allow_short = allow_short
        self.execution = execution

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        return bool(self.active) and self.allow_long and not ctx.longed and ctx.strategy.longsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        lookback = max(2, int(self.entry_19_breakout_lookback))
        return (
            _len_at_least(ctx.bars, lookback + 2)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.highs_trail_4h_vec, 2)
            and ctx.entry_context.atr is not None
            and ctx.entry_context.atr > 0
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        lookback = max(2, int(self.entry_19_breakout_lookback))
        atr = _as_float(ctx.entry_context.atr, 0.0)
        broad_core = bool(self.entry_19_broad_core)
        body = ctx.bars[1].close - ctx.bars[1].open
        reference_high = max(bar.high for bar in ctx.bars[2 : 2 + lookback])
        breakout_buffer = 0.0
        if broad_core:
            breakout_buffer = 0.40 * atr
        breakout_ok = (
            ctx.bars[1].close > reference_high + breakout_buffer
            and ctx.bars[1].high > ctx.strategy.ta_data_trend_strat.highs_trail_4h_vec[-2]
        )
        body_min = self.entry_19_body_atr_min
        if broad_core:
            body_min = body_min * 1.70
        body_ok = body > body_min * atr
        close_strength_ok = True
        follow_through_ok = True
        setup_reset_ok = True
        if broad_core:
            bar_range = max(ctx.bars[1].high - ctx.bars[1].low, atr * 0.10)
            close_strength_ok = ((ctx.bars[1].close - ctx.bars[1].low) / bar_range) >= 0.62
            follow_through_ok = ctx.bars[1].close > ctx.bars[2].high + 0.20 * atr
            setup_reset_ok = (
                ctx.bars[2].high <= reference_high + 0.05 * atr
                and ctx.bars[2].close <= reference_high
                and ctx.bars[3].close <= reference_high
            )
        if not (breakout_ok and body_ok and close_strength_ok and follow_through_ok and setup_reset_ok):
            return

        ctx.strategy.logger.info("Longing trend expansion continuation.")
        if ctx.strategy.telegram is not None:
            ctx.strategy.telegram.send_log("Longing trend expansion continuation.")
        base_entry = ctx.bars[0].close
        base_stop = ctx.bars[1].low
        _open_with_execution(
            ctx,
            direction=PositionDirection.LONG,
            base_entry=base_entry,
            base_stop=base_stop,
            default_order_type="Market",
            options=self.execution,
        )


class Entry20Module(EntryModule):
    name = "entry_20"

    def __init__(
        self,
        active=None,
        entry_20_break_lookback: int = 6,
        entry_20_broad_core: bool = False,
        entry_20_pullback_max_atr: float = 1.0,
        entry_20_reclaim_buffer_atr: float = 0.1,
        allow_long: bool = True,
        allow_short: bool = False,
        execution: ExecutionOptions = ExecutionOptions(),
    ):
        self.active = active
        self.entry_20_break_lookback = entry_20_break_lookback
        self.entry_20_broad_core = entry_20_broad_core
        self.entry_20_pullback_max_atr = entry_20_pullback_max_atr
        self.entry_20_reclaim_buffer_atr = entry_20_reclaim_buffer_atr
        self.allow_long = allow_long
        self.allow_short = allow_short
        self.execution = execution

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        return bool(self.active) and self.allow_long and not ctx.longed and ctx.strategy.longsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        lookback = max(2, int(self.entry_20_break_lookback))
        return (
            _len_at_least(ctx.bars, lookback + 4)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.highs_trail_4h_vec, 3)
            and ctx.entry_context.atr is not None
            and ctx.entry_context.atr > 0
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        lookback = max(2, int(self.entry_20_break_lookback))
        atr = _as_float(ctx.entry_context.atr, 0.0)
        broad_core = bool(self.entry_20_broad_core)
        if broad_core:
            lookback = max(2, int(lookback * 0.85))
        breakout_bar = ctx.bars[2]
        pullback_bar = ctx.bars[1]

        reference_high = max(bar.high for bar in ctx.bars[3 : 3 + lookback])
        breakout_level = max(reference_high, ctx.strategy.ta_data_trend_strat.highs_trail_4h_vec[-3])
        breakout_ok = breakout_bar.close > breakout_level
        pullback_max_atr = self.entry_20_pullback_max_atr
        reclaim_buffer_atr = self.entry_20_reclaim_buffer_atr
        pullback_depth_ok = pullback_bar.low >= breakout_bar.close - pullback_max_atr * atr
        pullback_reclaim_level = breakout_level - reclaim_buffer_atr * atr
        pullback_shape_ok = pullback_bar.open > pullback_bar.close and pullback_bar.close > pullback_reclaim_level
        resume_ok = ctx.bars[0].close > pullback_bar.close
        if broad_core:
            breakout_ok = (
                breakout_bar.high > breakout_level + 0.05 * atr
                and breakout_bar.close > breakout_level - 0.10 * atr
            )
            hold_level = breakout_level - 0.60 * atr
            pullback_depth_ok = pullback_bar.low > hold_level
            pullback_shape_ok = (
                pullback_bar.close > breakout_level - 0.40 * atr
            )
            resume_ok = (
                ctx.bars[0].close > breakout_level - 0.05 * atr
                and ctx.bars[0].close >= pullback_bar.close
            )
        if not (breakout_ok and pullback_depth_ok and pullback_shape_ok and resume_ok):
            return

        ctx.strategy.logger.info("Longing regime-flip pullback continuation.")
        if ctx.strategy.telegram is not None:
            ctx.strategy.telegram.send_log("Longing regime-flip pullback continuation.")
        base_entry = ctx.bars[0].close
        base_stop = min(breakout_bar.low, pullback_bar.low)
        _open_with_execution(
            ctx,
            direction=PositionDirection.LONG,
            base_entry=base_entry,
            base_stop=base_stop,
            default_order_type="Market",
            options=self.execution,
        )


class Entry21Module(EntryModule):
    name = "entry_21"

    def __init__(
        self,
        active=None,
        entry_21_crush_lookback: int = 8,
        entry_21_broad_core: bool = False,
        entry_21_crush_range_atr: float = 1.0,
        entry_21_crush_natr_max: float = 1.2,
        entry_21_fail_buffer_atr: float = 0.1,
        allow_long: bool = False,
        allow_short: bool = True,
        execution: ExecutionOptions = ExecutionOptions(),
    ):
        self.active = active
        self.entry_21_crush_lookback = entry_21_crush_lookback
        self.entry_21_broad_core = entry_21_broad_core
        self.entry_21_crush_range_atr = entry_21_crush_range_atr
        self.entry_21_crush_natr_max = entry_21_crush_natr_max
        self.entry_21_fail_buffer_atr = entry_21_fail_buffer_atr
        self.allow_long = allow_long
        self.allow_short = allow_short
        self.execution = execution

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        return bool(self.active) and self.allow_short and not ctx.shorted and ctx.strategy.shortsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        lookback = max(3, int(self.entry_21_crush_lookback))
        return (
            _len_at_least(ctx.bars, lookback + 4)
            and _len_at_least(ctx.strategy.ta_data_trend_strat.highs_trail_4h_vec, 3)
            and ctx.entry_context.natr_4h is not None
            and ctx.entry_context.atr is not None
            and ctx.entry_context.atr > 0
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        lookback = max(3, int(self.entry_21_crush_lookback))
        atr = _as_float(ctx.entry_context.atr, 0.0)
        broad_core = bool(self.entry_21_broad_core)
        crush_window = ctx.bars[3 : 3 + lookback]
        crush_ranges = [(bar.high - bar.low) / atr for bar in crush_window]
        crush_range_threshold = self.entry_21_crush_range_atr
        if broad_core:
            crush_sorted = sorted(crush_ranges)
            crush_core = crush_sorted[:-1] if len(crush_sorted) > 1 else crush_sorted
            crush_metric = sum(crush_core) / max(1, len(crush_core))
            crush_range_threshold = crush_range_threshold * 1.10
            crush_ok = (
                crush_metric <= crush_range_threshold
                and ctx.entry_context.natr_4h <= self.entry_21_crush_natr_max * 1.25
            )
        else:
            crush_metric = max(crush_ranges)
            crush_ok = crush_metric <= crush_range_threshold and ctx.entry_context.natr_4h <= self.entry_21_crush_natr_max
        local_high = max(bar.high for bar in crush_window)
        breakout_level = max(local_high, ctx.strategy.ta_data_trend_strat.highs_trail_4h_vec[-3])
        fail_close_level = breakout_level - self.entry_21_fail_buffer_atr * atr
        if broad_core:
            fail_close_level = breakout_level - 0.10 * atr
        false_break_ok = (
            ctx.bars[2].high > breakout_level + 0.10 * atr
            and ctx.bars[2].close < fail_close_level
        )
        if not (crush_ok and false_break_ok):
            return
        if broad_core:
            follow_through_ok = (
                ctx.bars[1].close < breakout_level
                and ctx.bars[1].close < ctx.bars[1].open
            )
            if not follow_through_ok:
                return

        ctx.strategy.logger.info("Shorting crush false-break trap.")
        if ctx.strategy.telegram is not None:
            ctx.strategy.telegram.send_log("Shorting crush false-break trap.")
        base_entry = ctx.bars[0].close
        base_stop = max(ctx.bars[1].high, ctx.bars[2].high)
        _open_with_execution(
            ctx,
            direction=PositionDirection.SHORT,
            base_entry=base_entry,
            base_stop=base_stop,
            default_order_type="Market",
            options=self.execution,
        )


class Entry22Module(EntryModule):
    name = "entry_22"

    def __init__(
        self,
        active=None,
        entry_22_impulse_body_atr: float = 1.5,
        entry_22_broad_core: bool = False,
        entry_22_absorption_reclaim_frac: float = 0.5,
        allow_long: bool = True,
        allow_short: bool = False,
        execution: ExecutionOptions = ExecutionOptions(),
    ):
        self.active = active
        self.entry_22_impulse_body_atr = entry_22_impulse_body_atr
        self.entry_22_broad_core = entry_22_broad_core
        self.entry_22_absorption_reclaim_frac = entry_22_absorption_reclaim_frac
        self.allow_long = allow_long
        self.allow_short = allow_short
        self.execution = execution

    def enabled(self, ctx: EntryExecutionContext) -> bool:
        return bool(self.active) and self.allow_long and not ctx.longed and ctx.strategy.longsAllowed

    def is_ready(self, ctx: EntryExecutionContext) -> bool:
        return (
            _len_at_least(ctx.bars, 3)
            and ctx.entry_context.atr is not None
            and ctx.entry_context.atr > 0
        )

    def run(self, ctx: EntryExecutionContext) -> None:
        atr = _as_float(ctx.entry_context.atr, 0.0)
        broad_core = bool(self.entry_22_broad_core)
        impulse_bar = ctx.bars[2]
        absorption_bar = ctx.bars[1]
        impulse_body = impulse_bar.open - impulse_bar.close
        impulse_body_mult = self.entry_22_impulse_body_atr
        reclaim_frac = self.entry_22_absorption_reclaim_frac
        if broad_core:
            impulse_body_mult = max(0.5, impulse_body_mult * 0.80)
            reclaim_frac = max(0.40, reclaim_frac * 0.90)
        impulse_ok = impulse_body > impulse_body_mult * atr and impulse_bar.close < impulse_bar.open
        reclaim_level = impulse_bar.close + impulse_body * reclaim_frac
        absorption_ok = absorption_bar.close > reclaim_level
        if broad_core:
            absorption_ok = absorption_ok and absorption_bar.close > impulse_bar.close
        if not (impulse_ok and absorption_ok):
            return

        ctx.strategy.logger.info("Longing volume-climax absorption.")
        if ctx.strategy.telegram is not None:
            ctx.strategy.telegram.send_log("Longing volume-climax absorption.")
        base_entry = ctx.bars[0].close
        base_stop = min(absorption_bar.low, impulse_bar.low)
        _open_with_execution(
            ctx,
            direction=PositionDirection.LONG,
            base_entry=base_entry,
            base_stop=base_stop,
            default_order_type="Market",
            options=self.execution,
        )


def default_entry_modules(config=None) -> List[EntryModule]:
    # Keep registry order stable to preserve historical behavior/parity outputs.
    def cfg(name, default):
        return _cfg_get(config, name, default)

    allow_flags = _allow_flags_by_module(config)

    def allow_long(module_id: str) -> bool:
        return allow_flags[module_id][0]

    def allow_short(module_id: str) -> bool:
        return allow_flags[module_id][1]

    modules = [
        Entry1Module(
            active=cfg("entry_1", False),
            entry_1_atr_fac=cfg("entry_1_atr_fac", 1),
            entry_1_vol_fac=cfg("entry_1_vol_fac", 2.0),
            entry_1_trail_lookback_1=cfg("entry_1_trail_lookback_1", 6),
            entry_1_trail_lookback_2=cfg("entry_1_trail_lookback_2", 7),
            entry_1_require_red_daily=cfg("entry_1_require_red_daily", True),
            entry_1_require_market_bearish=cfg("entry_1_require_market_bearish", True),
            allow_long=allow_long("entry_1"),
            allow_short=allow_short("entry_1"),
            execution=_build_execution_options(config, "entry_1"),
        ),
        Entry10Module(
            active=cfg("entry_10", False),
            entry_10_natr=cfg("entry_10_natr", 2),
            entry_10_natr_ath=cfg("entry_10_natr_ath", 2),
            entry_10_rsi_4h=cfg("entry_10_rsi_4h", 50),
            entry_10_rsi_d_min=cfg("entry_10_rsi_d_min", 50),
            entry_10_vol_cap_mult=cfg("entry_10_vol_cap_mult", 2.6),
            entry_10_sl_atr_mult=cfg("entry_10_sl_atr_mult", 0.2),
            entry_10_require_not_bearish=cfg("entry_10_require_not_bearish", True),
            entry_10_require_body_expansion=cfg("entry_10_require_body_expansion", True),
            entry_10_require_open_above_bar4_close=cfg("entry_10_require_open_above_bar4_close", True),
            entry_10_require_not_trending=cfg("entry_10_require_not_trending", True),
            allow_long=allow_long("entry_10"),
            allow_short=allow_short("entry_10"),
            execution=_build_execution_options(
                config,
                "entry_10",
                secondary_defaults={"enabled": True, "entry_offset_atr": 0.2, "stop_atr_mult": 1.0},
            ),
        ),
        Entry23Module(
            active=cfg("entry_23", False),
            allow_long=allow_long("entry_23"),
            allow_short=allow_short("entry_23"),
            execution=_build_execution_options(config, "entry_23"),
        ),
        Entry23SecondaryModule(
            active=cfg("entry_23_secondary", False),
            allow_long=allow_long("entry_23_secondary"),
            allow_short=allow_short("entry_23_secondary"),
            execution=_build_execution_options(config, "entry_23_secondary"),
        ),
        Entry24Module(
            active=cfg("entry_24", False),
            allow_long=allow_long("entry_24"),
            allow_short=allow_short("entry_24"),
            execution=_build_execution_options(
                config,
                "entry_24",
                secondary_defaults={"enabled": True, "entry_offset_atr": 0.2, "stop_atr_mult": 1.0},
            ),
        ),
        Entry2Module(
            active=cfg("entry_2", False),
            entry_2_swing_depth=cfg("entry_2_swing_depth", 40),
            entry_2_entry_buffer_atr=cfg("entry_2_entry_buffer_atr", 0.05),
            entry_2_max_natr=cfg("entry_2_max_natr", 1),
            entry_2_min_rsi_4h=cfg("entry_2_min_rsi_4h", 50),
            entry_2_min_rsi_d=cfg("entry_2_min_rsi_d", 80),
            entry_2_min_natr=cfg("entry_2_min_natr", 1),
            entry_2_min_rsi_4h_short=cfg("entry_2_min_rsi_4h_short", 50),
            entry_2_min_rsi_d_short=cfg("entry_2_min_rsi_d_short", 50),
            entry_2_use_min_natr=cfg("entry_2_use_min_natr", False),
            entry_2_enable_short=cfg("entry_2_enable_short", False),
            entry_2_require_not_bearish_long=cfg("entry_2_require_not_bearish_long", True),
            entry_2_require_not_trending_long=cfg("entry_2_require_not_trending_long", True),
            entry_2_require_not_bullish_short=cfg("entry_2_require_not_bullish_short", True),
            entry_2_require_not_trending_short=cfg("entry_2_require_not_trending_short", True),
            entry_2_expected_exit_slippage_pct=cfg("entry_2_expected_exit_slippage_pct", 0.0015),
            entry_2_expected_entry_slippage_pct=cfg("entry_2_expected_entry_slippage_pct", 0.0015),
            allow_long=allow_long("entry_2"),
            allow_short=allow_short("entry_2"),
            execution=_build_execution_options(config, "entry_2"),
        ),
        Entry3Module(
            active=cfg("entry_3", False),
            entry_3_max_natr=cfg("entry_3_max_natr", 2),
            entry_3_rsi_4h=cfg("entry_3_rsi_4h", 50),
            entry_3_atr_fac=cfg("entry_3_atr_fac", 1),
            entry_3_vol_fac=cfg("entry_3_vol_fac", 2.0),
            entry_3_use_vol_filter=cfg("entry_3_use_vol_filter", False),
            entry_3_rsi_d_min=cfg("entry_3_rsi_d_min", 50),
            entry_3_max_std_atr=cfg("entry_3_max_std_atr", 4.0),
            entry_3_stop_atr_mult=cfg("entry_3_stop_atr_mult", 1.0),
            entry_3_require_red_trigger_bar=cfg("entry_3_require_red_trigger_bar", True),
            entry_3_require_market_bullish=cfg("entry_3_require_market_bullish", True),
            entry_3_require_not_trending=cfg("entry_3_require_not_trending", True),
            allow_long=allow_long("entry_3"),
            allow_short=allow_short("entry_3"),
            execution=_build_execution_options(config, "entry_3"),
        ),
        Entry4Module(
            active=cfg("entry_4", False),
            entry_4_breakout_atr_mult=cfg("entry_4_breakout_atr_mult", 1.0),
            entry_4_rearm_lookback=cfg("entry_4_rearm_lookback", 300),
            allow_long=allow_long("entry_4"),
            allow_short=allow_short("entry_4"),
            execution=_build_execution_options(config, "entry_4"),
        ),
        Entry5Module(
            active=cfg("entry_5", False),
            entry_5_rsi_d=cfg("entry_5_rsi_d", 40),
            entry_5_rsi_4h=cfg("entry_5_rsi_4h", 80),
            entry_5_atr_fac=cfg("entry_5_atr_fac", 0.8),
            entry_5_trail_1_period=cfg("entry_5_trail_1_period", 10),
            entry_5_trail_2_period=cfg("entry_5_trail_2_period", 10),
            entry_5_vol_fac=cfg("entry_5_vol_fac", 2.0),
            allow_long=allow_long("entry_5"),
            allow_short=allow_short("entry_5"),
            execution=_build_execution_options(config, "entry_5"),
        ),
        Entry6Module(
            active=cfg("entry_6", False),
            entry_6_rsi_4h_max=cfg("entry_6_rsi_4h_max", 90),
            entry_6_rsi_4h_min=cfg("entry_6_rsi_4h_min", 75),
            entry_6_max_natr=cfg("entry_6_max_natr", 2),
            entry_6_atr_fac=cfg("entry_6_atr_fac", 5),
            entry_6_short_max_bar_range_atr=cfg("entry_6_short_max_bar_range_atr", 1.0),
            entry_6_swing_depth=cfg("entry_6_swing_depth", 40),
            entry_6_require_not_bearish_long=cfg("entry_6_require_not_bearish_long", True),
            entry_6_require_short_open_above_ema=cfg("entry_6_require_short_open_above_ema", True),
            allow_long=allow_long("entry_6"),
            allow_short=allow_short("entry_6"),
            execution=_build_execution_options(config, "entry_6"),
        ),
        Entry7Module(
            active=cfg("entry_7", False),
            entry_7_std_fac=cfg("entry_7_std_fac", 1),
            entry_7_4h_rsi=cfg("entry_7_4h_rsi", 2.5),
            entry_7_vol_fac=cfg("entry_7_vol_fac", 2),
            entry_7_use_std_filter=cfg("entry_7_use_std_filter", False),
            entry_7_use_rsi_filter=cfg("entry_7_use_rsi_filter", False),
            entry_7_use_vol_filter=cfg("entry_7_use_vol_filter", False),
            entry_7_require_prev_body_gt_lower_wick=cfg("entry_7_require_prev_body_gt_lower_wick", True),
            entry_7_require_sfp_upper_wick_gt_body=cfg("entry_7_require_sfp_upper_wick_gt_body", True),
            entry_7_require_not_trending=cfg("entry_7_require_not_trending", True),
            allow_long=allow_long("entry_7"),
            allow_short=allow_short("entry_7"),
            execution=_build_execution_options(config, "entry_7"),
        ),
        Entry8Module(
            active=cfg("entry_8", False),
            entry_8_vol_fac=cfg("entry_8_vol_fac", 2.0),
            entry_8_require_ranging_regime=cfg("entry_8_require_ranging_regime", True),
            allow_long=allow_long("entry_8"),
            allow_short=allow_short("entry_8"),
            execution=_build_execution_options(config, "entry_8"),
        ),
        Entry9Module(
            active=cfg("entry_9", False),
            entry_9_std=cfg("entry_9_std", 1),
            entry_9_4h_rsi=cfg("entry_9_4h_rsi", 50),
            entry_9_atr=cfg("entry_9_atr", 2),
            entry_9_require_lower_open=cfg("entry_9_require_lower_open", True),
            entry_9_require_ranging_regime=cfg("entry_9_require_ranging_regime", True),
            allow_long=allow_long("entry_9"),
            allow_short=allow_short("entry_9"),
            execution=_build_execution_options(config, "entry_9"),
        ),
        Entry11Module(
            active=cfg("entry_11", False),
            entry_11_vol=cfg("entry_11_vol", 3.0),
            entry_11_atr=cfg("entry_11_atr", 3.0),
            entry_11_natr=cfg("entry_11_natr", 3.0),
            allow_long=allow_long("entry_11"),
            allow_short=allow_short("entry_11"),
            execution=_build_execution_options(
                config,
                "entry_11",
                secondary_defaults={"enabled": True, "entry_offset_atr": 1.0, "stop_atr_mult": 2.0},
            ),
        ),
        Entry12Module(
            active=cfg("entry_12", False),
            entry_12_vol=cfg("entry_12_vol", 3.0),
            entry_12_rsi_4h=cfg("entry_12_rsi_4h", 3),
            entry_12_atr=cfg("entry_12_atr", 3.0),
            entry_12_max_rsi_4h=cfg("entry_12_max_rsi_4h", 90),
            entry_12_require_structure_1=cfg("entry_12_require_structure_1", True),
            entry_12_require_structure_2=cfg("entry_12_require_structure_2", True),
            entry_12_require_not_trending=cfg("entry_12_require_not_trending", True),
            allow_long=allow_long("entry_12"),
            allow_short=allow_short("entry_12"),
            execution=_build_execution_options(config, "entry_12"),
        ),
        Entry15Module(
            active=cfg("entry_15", False),
            entry_15_squeeze_lookback=cfg("entry_15_squeeze_lookback", 6),
            entry_15_broad_core=cfg("entry_15_broad_core", False),
            entry_15_squeeze_range_atr=cfg("entry_15_squeeze_range_atr", 1.0),
            entry_15_breakout_buffer_atr=cfg("entry_15_breakout_buffer_atr", 0.1),
            allow_long=allow_long("entry_15"),
            allow_short=allow_short("entry_15"),
            execution=_build_execution_options(config, "entry_15"),
        ),
        Entry16Module(
            active=cfg("entry_16", False),
            entry_16_dump_atr=cfg("entry_16_dump_atr", 2.0),
            entry_16_broad_core=cfg("entry_16_broad_core", False),
            entry_16_band_std=cfg("entry_16_band_std", 1.5),
            entry_16_reclaim_frac=cfg("entry_16_reclaim_frac", 0.5),
            allow_long=allow_long("entry_16"),
            allow_short=allow_short("entry_16"),
            execution=_build_execution_options(config, "entry_16"),
        ),
        Entry17Module(
            active=cfg("entry_17", False),
            entry_17_break_lookback=cfg("entry_17_break_lookback", 6),
            entry_17_fail_close_buffer_atr=cfg("entry_17_fail_close_buffer_atr", 0.1),
            entry_17_wick_excess_atr=cfg("entry_17_wick_excess_atr", 0.2),
            entry_17_add_trigger_open_limit=cfg("entry_17_add_trigger_open_limit", False),
            entry_17_limit_only_trigger_open=cfg("entry_17_limit_only_trigger_open", False),
            entry_17_trigger_open_order_type=cfg("entry_17_trigger_open_order_type", "Limit"),
            allow_long=allow_long("entry_17"),
            allow_short=allow_short("entry_17"),
            execution=_build_execution_options(config, "entry_17"),
        ),
        Entry18Module(
            active=cfg("entry_18", False),
            entry_18_reject_lookback=cfg("entry_18_reject_lookback", 4),
            entry_18_reclaim_buffer_atr=cfg("entry_18_reclaim_buffer_atr", 0.05),
            entry_18_tail_ratio_min=cfg("entry_18_tail_ratio_min", 1.2),
            allow_long=allow_long("entry_18"),
            allow_short=allow_short("entry_18"),
            execution=_build_execution_options(config, "entry_18"),
        ),
        Entry19Module(
            active=cfg("entry_19", False),
            entry_19_body_atr_min=cfg("entry_19_body_atr_min", 1.0),
            entry_19_broad_core=cfg("entry_19_broad_core", False),
            entry_19_breakout_lookback=cfg("entry_19_breakout_lookback", 5),
            allow_long=allow_long("entry_19"),
            allow_short=allow_short("entry_19"),
            execution=_build_execution_options(config, "entry_19"),
        ),
        Entry20Module(
            active=cfg("entry_20", False),
            entry_20_break_lookback=cfg("entry_20_break_lookback", 6),
            entry_20_broad_core=cfg("entry_20_broad_core", False),
            entry_20_pullback_max_atr=cfg("entry_20_pullback_max_atr", 1.0),
            entry_20_reclaim_buffer_atr=cfg("entry_20_reclaim_buffer_atr", 0.1),
            allow_long=allow_long("entry_20"),
            allow_short=allow_short("entry_20"),
            execution=_build_execution_options(config, "entry_20"),
        ),
        Entry21Module(
            active=cfg("entry_21", False),
            entry_21_crush_lookback=cfg("entry_21_crush_lookback", 8),
            entry_21_broad_core=cfg("entry_21_broad_core", False),
            entry_21_crush_range_atr=cfg("entry_21_crush_range_atr", 1.0),
            entry_21_crush_natr_max=cfg("entry_21_crush_natr_max", 1.2),
            entry_21_fail_buffer_atr=cfg("entry_21_fail_buffer_atr", 0.1),
            allow_long=allow_long("entry_21"),
            allow_short=allow_short("entry_21"),
            execution=_build_execution_options(config, "entry_21"),
        ),
        Entry22Module(
            active=cfg("entry_22", False),
            entry_22_impulse_body_atr=cfg("entry_22_impulse_body_atr", 1.5),
            entry_22_broad_core=cfg("entry_22_broad_core", False),
            entry_22_absorption_reclaim_frac=cfg("entry_22_absorption_reclaim_frac", 0.5),
            allow_long=allow_long("entry_22"),
            allow_short=allow_short("entry_22"),
            execution=_build_execution_options(config, "entry_22"),
        ),
    ]
    for entry_module in modules:
        _attach_common_rules(entry_module, config, module_name(entry_module))
    return modules
