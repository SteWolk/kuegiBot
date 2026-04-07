import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from kuegi_bot.backtest_engine import BackTest
from kuegi_bot.bots.MultiStrategyBot import MultiStrategyBot
from kuegi_bot.bots.strategies.entry_filters import DayOfWeekFilter
from kuegi_bot.bots.strategies.exit_modules import ATRrangeSL, FixedPercentage, TimedExit
from kuegi_bot.bots.strategies.strategy_one import StrategyOne
from kuegi_bot.bots.strategies.strategy_one_entry_modules import (
    Entry10Module,
    Entry11Module,
    Entry12Module,
    Entry1Module,
    Entry2Module,
    Entry3Module,
    Entry5Module,
    Entry6Module,
    Entry7Module,
    Entry8Module,
    Entry9Module,
)
from kuegi_bot.utils.helper import load_bars, load_funding, load_open_interest
from kuegi_bot.utils.trading_classes import Symbol
from private_config import load_private_section

_MODE_COMMON_PRIVATE = load_private_section("mode_common")
DEFAULT_ENTRY_MODULE_OVERRIDES = dict(_MODE_COMMON_PRIVATE["default_entry_module_overrides"])


def setup_logger(log_level=logging.INFO):
    import kuegi_bot.utils.log as log

    return log.setup_custom_logger(log_level=log_level)


def build_symbol(pair: str):
    if pair == "BTCUSD":
        return Symbol(
            baseCoin="BTC",
            symbol="BTCUSD",
            isInverse=True,
            tickSize=0.1,
            lotSize=1.0,
            makerFee=0.0002,
            takerFee=0.00055,
            quantityPrecision=2,
            pricePrecision=2,
        )
    if pair == "XRPUSD":
        return Symbol(
            baseCoin="XRP",
            symbol="XRPUSD",
            isInverse=True,
            tickSize=0.0001,
            lotSize=0.01,
            makerFee=0.0002,
            takerFee=0.00055,
            quantityPrecision=2,
            pricePrecision=4,
        )
    if pair == "ETHUSD":
        return Symbol(
            baseCoin="ETH",
            symbol="ETHUSD",
            isInverse=True,
            tickSize=0.05,
            lotSize=1.0,
            makerFee=0.0002,
            takerFee=0.00055,
            quantityPrecision=2,
            pricePrecision=2,
        )
    if pair == "BTCUSDT":
        return Symbol(
            baseCoin="USDT",
            symbol="BTCUSDT",
            isInverse=False,
            tickSize=0.1,
            lotSize=0.001,
            makerFee=0.0002,
            takerFee=0.00055,
            quantityPrecision=3,
            pricePrecision=2,
        )
    raise ValueError("Unsupported pair: " + str(pair))


def normalize_exchange(exchange: str, pair: str) -> str:
    if exchange == "bybit" and "USDT" in pair:
        return "bybit-linear"
    return exchange


def _entry_value(overrides: dict, key: str):
    return overrides.get(key, DEFAULT_ENTRY_MODULE_OVERRIDES[key])


def with_explicit_entry_modules(strategy: StrategyOne, entry_module_overrides: dict = None) -> StrategyOne:
    overrides = dict(DEFAULT_ENTRY_MODULE_OVERRIDES)
    if entry_module_overrides:
        overrides.update(entry_module_overrides)
    return (
        strategy.clearEntryModules()
        .withEntryModule(
            Entry1Module(
                active=_entry_value(overrides, "entry_1"),
                entry_1_atr_fac=_entry_value(overrides, "entry_1_atr_fac"),
                entry_1_vol_fac=_entry_value(overrides, "entry_1_vol_fac"),
                entry_1_trail_lookback_1=_entry_value(overrides, "entry_1_trail_lookback_1"),
                entry_1_trail_lookback_2=_entry_value(overrides, "entry_1_trail_lookback_2"),
            )
        )
        .withEntryModule(
            Entry10Module(
                active=_entry_value(overrides, "entry_10"),
                entry_10_natr=_entry_value(overrides, "entry_10_natr"),
                entry_10_natr_ath=_entry_value(overrides, "entry_10_natr_ath"),
                entry_10_rsi_4h=_entry_value(overrides, "entry_10_rsi_4h"),
                entry_10_rsi_d_min=_entry_value(overrides, "entry_10_rsi_d_min"),
                entry_10_vol_cap_mult=_entry_value(overrides, "entry_10_vol_cap_mult"),
                entry_10_sl_atr_mult=_entry_value(overrides, "entry_10_sl_atr_mult"),
            )
        )
        .withEntryModule(
            Entry2Module(
                active=_entry_value(overrides, "entry_2"),
                entry_2_max_natr=_entry_value(overrides, "entry_2_max_natr"),
                entry_2_min_rsi_4h=_entry_value(overrides, "entry_2_min_rsi_4h"),
                entry_2_min_rsi_d=_entry_value(overrides, "entry_2_min_rsi_d"),
                entry_2_min_natr=_entry_value(overrides, "entry_2_min_natr"),
                entry_2_min_rsi_4h_short=_entry_value(overrides, "entry_2_min_rsi_4h_short"),
                entry_2_min_rsi_d_short=_entry_value(overrides, "entry_2_min_rsi_d_short"),
                entry_2_expected_exit_slippage_pct=_entry_value(overrides, "entry_2_expected_exit_slippage_pct"),
                entry_2_expected_entry_slippage_pct=_entry_value(overrides, "entry_2_expected_entry_slippage_pct"),
            )
        )
        .withEntryModule(
            Entry3Module(
                active=_entry_value(overrides, "entry_3"),
                entry_3_max_natr=_entry_value(overrides, "entry_3_max_natr"),
                entry_3_rsi_4h=_entry_value(overrides, "entry_3_rsi_4h"),
                entry_3_atr_fac=_entry_value(overrides, "entry_3_atr_fac"),
                entry_3_rsi_d_min=_entry_value(overrides, "entry_3_rsi_d_min"),
                entry_3_max_std_atr=_entry_value(overrides, "entry_3_max_std_atr"),
                entry_3_stop_atr_mult=_entry_value(overrides, "entry_3_stop_atr_mult"),
            )
        )
        .withEntryModule(
            Entry5Module(
                active=_entry_value(overrides, "entry_5"),
                entry_5_rsi_d=_entry_value(overrides, "entry_5_rsi_d"),
                entry_5_rsi_4h=_entry_value(overrides, "entry_5_rsi_4h"),
                entry_5_atr_fac=_entry_value(overrides, "entry_5_atr_fac"),
                entry_5_trail_1_period=_entry_value(overrides, "entry_5_trail_1_period"),
                entry_5_trail_2_period=_entry_value(overrides, "entry_5_trail_2_period"),
                entry_5_vol_fac=_entry_value(overrides, "entry_5_vol_fac"),
            )
        )
        .withEntryModule(
            Entry6Module(
                active=_entry_value(overrides, "entry_6"),
                entry_6_rsi_4h_max=_entry_value(overrides, "entry_6_rsi_4h_max"),
                entry_6_rsi_4h_min=_entry_value(overrides, "entry_6_rsi_4h_min"),
                entry_6_max_natr=_entry_value(overrides, "entry_6_max_natr"),
                entry_6_atr_fac=_entry_value(overrides, "entry_6_atr_fac"),
                entry_6_short_max_bar_range_atr=_entry_value(overrides, "entry_6_short_max_bar_range_atr"),
                entry_6_swing_depth=_entry_value(overrides, "entry_6_swing_depth"),
            )
        )
        .withEntryModule(
            Entry7Module(
                active=_entry_value(overrides, "entry_7"),
                entry_7_std_fac=_entry_value(overrides, "entry_7_std_fac"),
                entry_7_4h_rsi=_entry_value(overrides, "entry_7_4h_rsi"),
                entry_7_vol_fac=_entry_value(overrides, "entry_7_vol_fac"),
            )
        )
        .withEntryModule(
            Entry8Module(
                active=_entry_value(overrides, "entry_8"),
                entry_8_vol_fac=_entry_value(overrides, "entry_8_vol_fac"),
            )
        )
        .withEntryModule(
            Entry9Module(
                active=_entry_value(overrides, "entry_9"),
                entry_9_std=_entry_value(overrides, "entry_9_std"),
                entry_9_4h_rsi=_entry_value(overrides, "entry_9_4h_rsi"),
                entry_9_atr=_entry_value(overrides, "entry_9_atr"),
            )
        )
        .withEntryModule(
            Entry11Module(
                active=_entry_value(overrides, "entry_11"),
                entry_11_vol=_entry_value(overrides, "entry_11_vol"),
                entry_11_atr=_entry_value(overrides, "entry_11_atr"),
                entry_11_natr=_entry_value(overrides, "entry_11_natr"),
            )
        )
        .withEntryModule(
            Entry12Module(
                active=_entry_value(overrides, "entry_12"),
                entry_12_vol=_entry_value(overrides, "entry_12_vol"),
                entry_12_rsi_4h=_entry_value(overrides, "entry_12_rsi_4h"),
                entry_12_atr=_entry_value(overrides, "entry_12_atr"),
                entry_12_max_rsi_4h=_entry_value(overrides, "entry_12_max_rsi_4h"),
            )
        )
    )


def build_strategy_one(
    timeframe: int,
    indicator_mode: str,
    entry_module_overrides: dict = None,
    open_interest_by_tstamp: dict = None,
    funding_by_tstamp: dict = None,
):
    strategy = StrategyOne(
        var_1=0,
        var_2=0,
        risk_ref=1,
        reduceRisk=True,
        max_r=10,
        h_highs_trail_period=55,
        h_lows_trail_period=55,
        tp_fac_strat_one=20,
        plotStrategyOneData=False,
        plotTrailsStatOne=False,
        longsAllowed=True,
        shortsAllowed=True,
        timeframe=timeframe,
        ema_w_period=3,
        highs_trail_4h_period=20 * 6,
        lows_trail_4h_period=20 * 6,
        days_buffer_bear=25,
        days_buffer_bull=10,
        trend_atr_fac=0.8,
        atr_4h_period=28,
        natr_4h_period_slow=200,
        bbands_4h_period=200,
        plotIndicators=True,
        plot_RSI=False,
        rsi_4h_period=6,
        volume_sma_4h_period=22,
        trend_var_1=0,
        indicator_mode=indicator_mode,
        open_interest_by_tstamp=open_interest_by_tstamp,
        funding_by_tstamp=funding_by_tstamp,
        risk_with_trend=3.5,
        risk_ranging=2.5,
        risk_counter_trend=3.5,
        risk_fac_shorts=1,
        sl_atr_fac=0.8,
        be_by_middleband=False,
        be_by_opposite=False,
        stop_at_middleband=False,
        tp_at_middleband=False,
        atr_buffer_fac=0,
        tp_on_opposite=False,
        stop_at_new_entry=False,
        trail_sl_with_bband=False,
        stop_short_at_middleband=False,
        stop_at_trail=True,
        stop_at_lowerband=False,
        moving_sl_atr_fac=0,
        sl_upper_bb_std_fac=3,
        sl_lower_bb_std_fac=3,
        ema_multiple_4_tp=1.4,
        use_shapes=True,
        plotBackgroundColor4Trend=False,
        plotTrailsAndEMAs=False,
        plotBBands=True,
        plotATR=False,
        maxPositions=140,
        consolidate=False,
        close_on_opposite=False,
        bars_till_cancel_triggered=20,
        limit_entry_offset_perc=0.15,
        tp_fac=0,
        delayed_cancel=False,
        cancel_on_filter=True,
    )
    strategy = with_explicit_entry_modules(strategy, entry_module_overrides=entry_module_overrides)
    return (
        strategy.withEntryFilter(DayOfWeekFilter(allowedDaysMask=63))
        .withRM(risk_factor=5, max_risk_mul=1, risk_type=3, atr_factor=0)
        .withExitModule(
            ATRrangeSL(
                rangeFacTrigger=0.15,
                longRangefacSL=-1.3,
                shortRangefacSL=-0.7,
                rangeATRfactor=1,
                atrPeriod=20,
            )
        )
        .withExitModule(
            ATRrangeSL(
                rangeFacTrigger=0.8,
                longRangefacSL=0.1,
                shortRangefacSL=-0.3,
                rangeATRfactor=1,
                atrPeriod=20,
            )
        )
        .withExitModule(
            ATRrangeSL(
                rangeFacTrigger=1.5,
                longRangefacSL=0.1,
                shortRangefacSL=-0.2,
                rangeATRfactor=1,
                atrPeriod=20,
            )
        )
        .withExitModule(
            ATRrangeSL(
                rangeFacTrigger=6.3,
                longRangefacSL=3.2,
                shortRangefacSL=0,
                rangeATRfactor=1,
                atrPeriod=20,
            )
        )
        .withExitModule(
            TimedExit(
                longs_min_to_exit=12 * 240,
                shorts_min_to_exit=0,
                longs_min_to_breakeven=6 * 240,
                shorts_min_to_breakeven=0,
                atrPeriod=20,
            )
        )
        .withExitModule(FixedPercentage(slPercentage=0.5, useInitialSLRange=False, rangeFactor=0))
    )


def build_bot(
    logger,
    timeframe: int,
    indicator_mode: str,
    entry_module_overrides: dict = None,
    open_interest_by_tstamp: dict = None,
    funding_by_tstamp: dict = None,
):
    bot = MultiStrategyBot(logger=logger, directionFilter=0)
    bot.add_strategy(
        build_strategy_one(
            timeframe=timeframe,
            indicator_mode=indicator_mode,
            entry_module_overrides=entry_module_overrides,
            open_interest_by_tstamp=open_interest_by_tstamp,
            funding_by_tstamp=funding_by_tstamp,
        )
    )
    return bot


def load_backtest_data(exchange: str, pair: str, days: int, timeframe: int):
    normalized_exchange = normalize_exchange(exchange, pair)
    bars = load_bars(
        days_in_history=days,
        wanted_tf=timeframe,
        start_offset_minutes=0,
        exchange=normalized_exchange,
        symbol=pair,
    )
    funding = load_funding(normalized_exchange, pair)
    open_interest = load_open_interest(normalized_exchange, pair)
    symbol = build_symbol(pair)
    return bars, funding, symbol, open_interest


def run_mode_backtest(
    logger,
    bars,
    funding,
    symbol,
    timeframe: int,
    indicator_mode: str,
    entry_module_overrides: dict = None,
    open_interest_by_tstamp: dict = None,
    funding_by_tstamp: dict = None,
):
    bot = build_bot(
        logger=logger,
        timeframe=timeframe,
        indicator_mode=indicator_mode,
        entry_module_overrides=entry_module_overrides,
        open_interest_by_tstamp=open_interest_by_tstamp,
        funding_by_tstamp=funding_by_tstamp,
    )
    return BackTest(bot, bars=bars, funding=funding, symbol=symbol).run()
