import json
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
from kuegi_bot.bots.strategies.strategy_one_entry_modules import default_entry_modules
from kuegi_bot.utils import log
from kuegi_bot.utils.helper import load_bars, load_funding, load_open_interest
from kuegi_bot.utils.trading_classes import Symbol

logger = log.setup_custom_logger()

PAIR = "BTCUSD"
EXCHANGE = "bybit"
TIMEFRAME = 240
DAYS = 3000 * 6
FLOAT_TOL = 1e-12

ARTIFACT_DIR = PROJECT_ROOT / ".assistant_workspace" / "artifacts" / "modularization" / "pass19"
METRIC_KEYS = [
    "trades_closed",
    "open_positions",
    "final_equity",
    "profit_pct",
    "max_drawdown_pct",
    "relY_final",
    "relY_final_trades",
    "cagr",
    "mar",
    "winrate",
    "avg_R",
    "profit_factor",
    "sqn_trades",
]

ENTRY_MODULE_CONFIG = {
    "entry_1_atr_fac": 0.3,
    "entry_1_vol_fac": 1.05,
    "entry_1_trail_lookback_1": 6,
    "entry_1_trail_lookback_2": 7,
    "entry_2_max_natr": 1.1,
    "entry_2_min_rsi_4h": 100,
    "entry_2_min_rsi_d": 0,
    "entry_2_min_natr": 1.5,
    "entry_2_min_rsi_4h_short": 30,
    "entry_2_min_rsi_d_short": 70,
    "entry_2_expected_exit_slippage_pct": 0.0015,
    "entry_2_expected_entry_slippage_pct": 0.0015,
    "entry_3_max_natr": 2,
    "entry_3_atr_fac": 0.2,
    "entry_3_rsi_4h": 70,
    "entry_3_rsi_d_min": 50,
    "entry_3_max_std_atr": 4.0,
    "entry_3_stop_atr_mult": 1.0,
    "entry_5_rsi_d": 45,
    "entry_5_rsi_4h": 20,
    "entry_5_atr_fac": 0.8,
    "entry_5_trail_1_period": 3,
    "entry_5_trail_2_period": 15,
    "entry_5_vol_fac": 2.9,
    "entry_6_max_natr": 1,
    "entry_6_rsi_4h_max": 90,
    "entry_6_rsi_4h_min": 75,
    "entry_6_atr_fac": 2,
    "entry_6_short_max_bar_range_atr": 1.0,
    "entry_6_swing_depth": 40,
    "entry_7_std_fac": 1,
    "entry_7_4h_rsi": 100,
    "entry_7_vol_fac": 1.2,
    "entry_8_vol_fac": 1.8,
    "entry_9_std": 2.0,
    "entry_9_4h_rsi": 25,
    "entry_9_atr": 0.6,
    "entry_10_natr": 1.3,
    "entry_10_natr_ath": 1.8,
    "entry_10_rsi_4h": 85,
    "entry_10_rsi_d_min": 50,
    "entry_10_vol_cap_mult": 2.6,
    "entry_10_sl_atr_mult": 0.2,
    "entry_11_vol": 2.7,
    "entry_11_atr": 2,
    "entry_11_natr": 1.2,
    "entry_12_vol": 1.3,
    "entry_12_rsi_4h": 70,
    "entry_12_atr": 0.9,
    "entry_12_max_rsi_4h": 70,
    "entry_1": False,
    "entry_2": True,
    "entry_3": False,
    "entry_5": False,
    "entry_6": False,
    "entry_7": False,
    "entry_8": False,
    "entry_9": False,
    "entry_10": False,
    "entry_11": False,
    "entry_12": False,
}


def get_symbol(pair: str):
    if pair == "BTCUSD":
        return Symbol(baseCoin="BTC", symbol="BTCUSD", isInverse=True, tickSize=0.1, lotSize=1.0, makerFee=0.0002, takerFee=0.00055, quantityPrecision=2, pricePrecision=2)
    if pair == "ETHUSD":
        return Symbol(baseCoin="ETH", symbol="ETHUSD", isInverse=True, tickSize=0.05, lotSize=1.0, makerFee=0.0002, takerFee=0.00055, quantityPrecision=2, pricePrecision=2)
    if pair == "XRPUSD":
        return Symbol(baseCoin="XRP", symbol="XRPUSD", isInverse=True, tickSize=0.0001, lotSize=0.01, makerFee=0.0002, takerFee=0.00055, quantityPrecision=2, pricePrecision=4)
    if pair == "BTCUSDT":
        return Symbol(baseCoin="USDT", symbol="BTCUSDT", isInverse=False, tickSize=0.1, lotSize=0.001, makerFee=0.0002, takerFee=0.00055, quantityPrecision=3, pricePrecision=2)
    raise ValueError("Unsupported pair: " + pair)


def build_strategy(timeframe: int, explicit_registry: bool, open_interest_by_tstamp=None, funding_by_tstamp=None):
    strategy = (
        StrategyOne(
            var_1=0,
            var_2=0,
            risk_ref=1,
            reduceRisk=True,
            max_r=10,
            entry_module_config=ENTRY_MODULE_CONFIG if not explicit_registry else None,
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
        .withEntryFilter(DayOfWeekFilter(allowedDaysMask=63))
        .withRM(risk_factor=5, max_risk_mul=1, risk_type=3, atr_factor=0)
        .withExitModule(ATRrangeSL(rangeFacTrigger=0.15, longRangefacSL=-1.3, shortRangefacSL=-0.7, rangeATRfactor=1, atrPeriod=20))
        .withExitModule(ATRrangeSL(rangeFacTrigger=0.8, longRangefacSL=0.1, shortRangefacSL=-0.3, rangeATRfactor=1, atrPeriod=20))
        .withExitModule(ATRrangeSL(rangeFacTrigger=1.5, longRangefacSL=0.1, shortRangefacSL=-0.2, rangeATRfactor=1, atrPeriod=20))
        .withExitModule(ATRrangeSL(rangeFacTrigger=6.3, longRangefacSL=3.2, shortRangefacSL=0, rangeATRfactor=1, atrPeriod=20))
        .withExitModule(TimedExit(longs_min_to_exit=12 * 240, shorts_min_to_exit=0, longs_min_to_breakeven=6 * 240, shorts_min_to_breakeven=0, atrPeriod=20))
        .withExitModule(FixedPercentage(slPercentage=0.5, useInitialSLRange=False, rangeFactor=0))
    )

    if explicit_registry:
        strategy.clearEntryModules()
        for module in default_entry_modules(ENTRY_MODULE_CONFIG):
            strategy.withEntryModule(module)

    return strategy


def build_bot(timeframe: int, explicit_registry: bool, open_interest_by_tstamp=None, funding_by_tstamp=None):
    bot = MultiStrategyBot(logger=logger, directionFilter=0)
    bot.add_strategy(
        build_strategy(
            timeframe=timeframe,
            explicit_registry=explicit_registry,
            open_interest_by_tstamp=open_interest_by_tstamp,
            funding_by_tstamp=funding_by_tstamp,
        )
    )
    return bot


def normalize_metrics(bt):
    metrics = bt.metrics or {}
    result = {}
    for key in METRIC_KEYS:
        result[key] = metrics.get(key)
    return result


def compare_metrics(reference: dict, candidate: dict):
    diffs = []
    for key in METRIC_KEYS:
        left = reference.get(key)
        right = candidate.get(key)
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            if abs(float(left) - float(right)) > FLOAT_TOL:
                diffs.append({"metric": key, "left": left, "right": right, "delta": float(right) - float(left)})
        elif left != right:
            diffs.append({"metric": key, "left": left, "right": right})
    return diffs


def main():
    exchange = EXCHANGE
    if exchange == "bybit" and "USDT" in PAIR:
        exchange = "bybit-linear"

    bars = load_bars(days_in_history=DAYS, wanted_tf=TIMEFRAME, start_offset_minutes=0, exchange=exchange, symbol=PAIR)
    funding = load_funding(exchange, PAIR)
    open_interest = load_open_interest(exchange, PAIR)
    symbol = get_symbol(PAIR)

    baseline_bt = BackTest(
        build_bot(TIMEFRAME, explicit_registry=False, open_interest_by_tstamp=open_interest, funding_by_tstamp=funding),
        bars=bars,
        funding=funding,
        symbol=symbol,
    ).run()
    explicit_bt = BackTest(
        build_bot(TIMEFRAME, explicit_registry=True, open_interest_by_tstamp=open_interest, funding_by_tstamp=funding),
        bars=bars,
        funding=funding,
        symbol=symbol,
    ).run()

    baseline_metrics = normalize_metrics(baseline_bt)
    explicit_metrics = normalize_metrics(explicit_bt)
    diffs = compare_metrics(baseline_metrics, explicit_metrics)

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    baseline_path = ARTIFACT_DIR / "baseline_default_registry.json"
    explicit_path = ARTIFACT_DIR / "baseline_explicit_registry.json"
    report_path = ARTIFACT_DIR / "parity_report.md"

    baseline_path.write_text(json.dumps(baseline_metrics, indent=2, sort_keys=True), encoding="utf-8")
    explicit_path.write_text(json.dumps(explicit_metrics, indent=2, sort_keys=True), encoding="utf-8")

    lines = []
    lines.append("# Entry Module Pipeline Parity (Pass 19)")
    lines.append("")
    lines.append(f"- pair: `{PAIR}`")
    lines.append(f"- exchange: `{exchange}`")
    lines.append(f"- timeframe: `{TIMEFRAME}`")
    lines.append(f"- bars: `{len(bars)}`")
    lines.append(f"- float_tolerance: `{FLOAT_TOL}`")
    lines.append("")
    lines.append(f"- diff_count: `{len(diffs)}`")
    lines.append("")
    if diffs:
        lines.append("## Diffs")
        lines.append("")
        for diff in diffs:
            lines.append("- " + json.dumps(diff, sort_keys=True))
    else:
        lines.append("No metric diffs found.")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if diffs:
        print("entry_module_pipeline_parity: FAIL")
        print(json.dumps(diffs, indent=2, sort_keys=True))
        raise SystemExit(1)

    print("entry_module_pipeline_parity: OK")
    print("diff_count=0")


if __name__ == "__main__":
    main()
