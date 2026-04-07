import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
BACKTEST_ROOT = PROJECT_ROOT / "backtest"
if str(BACKTEST_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKTEST_ROOT))
os.chdir(PROJECT_ROOT)

from result_tools import extract_metrics, trade_fingerprint
from kuegi_bot.backtest_engine import BackTest
from kuegi_bot.bots.MultiStrategyBot import MultiStrategyBot
from kuegi_bot.bots.strategies.entry_filters import DayOfWeekFilter
from kuegi_bot.bots.strategies.exit_modules import ATRrangeSL, FixedPercentage, TimedExit
from kuegi_bot.bots.strategies.strategy_one import StrategyOne
from kuegi_bot.bots.strategies.strategy_one_entry_schema import get_entry_parameter_catalog
from kuegi_bot.utils import log
from kuegi_bot.utils.helper import load_bars, load_funding, load_open_interest
from kuegi_bot.utils.trading_classes import Symbol

logger = log.setup_custom_logger()

ARTIFACT_DIR = PROJECT_ROOT / ".assistant_workspace" / "artifacts" / "modularization" / "schema_equivalence"
FLOAT_TOL = 1e-12
PAIR = "BTCUSD"
EXCHANGE = "bybit"
TIMEFRAME = 240
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


def get_symbol(pair: str):
    if pair == "BTCUSD":
        return Symbol(baseCoin="BTC", symbol="BTCUSD", isInverse=True, tickSize=0.1, lotSize=1.0, makerFee=0.0002, takerFee=0.00055, quantityPrecision=2, pricePrecision=2)
    if pair == "XRPUSD":
        return Symbol(baseCoin="XRP", symbol="XRPUSD", isInverse=True, tickSize=0.0001, lotSize=0.01, makerFee=0.0002, takerFee=0.00055, quantityPrecision=2, pricePrecision=4)
    if pair == "ETHUSD":
        return Symbol(baseCoin="ETH", symbol="ETHUSD", isInverse=True, tickSize=0.05, lotSize=1.0, makerFee=0.0002, takerFee=0.00055, quantityPrecision=2, pricePrecision=2)
    if pair == "BTCUSDT":
        return Symbol(baseCoin="USDT", symbol="BTCUSDT", isInverse=False, tickSize=0.1, lotSize=0.001, makerFee=0.0002, takerFee=0.00055, quantityPrecision=3, pricePrecision=2)
    raise ValueError("Unsupported pair: " + pair)


def _build_flat_config():
    cfg = {}
    for entry_id in get_entry_parameter_catalog().keys():
        cfg[entry_id] = True
    return cfg


def _flat_to_schema(flat_cfg: dict):
    catalog = get_entry_parameter_catalog()
    modules = {}
    for entry_id, classes in catalog.items():
        module_payload = {
            "activation": {
                "enabled": bool(flat_cfg.get(entry_id, False)),
                "allow_long": bool(flat_cfg.get(f"{entry_id}_allow_long", True)),
                "allow_short": bool(flat_cfg.get(f"{entry_id}_allow_short", True)),
            },
            "idea": {"params": {}},
            "confirmation": {"params": {}},
            "filters": {"params": {}},
            "execution": {"params": {}},
        }
        for class_name in ("idea", "confirmation", "filters", "execution"):
            for spec in classes.get(class_name, []):
                name = spec["name"]
                if name in flat_cfg:
                    module_payload[class_name]["params"][name] = flat_cfg[name]
        modules[entry_id] = module_payload
    return {"schema_version": 1, "modules": modules}


def build_strategy(entry_module_config, open_interest_by_tstamp=None, funding_by_tstamp=None):
    return (
        StrategyOne(
            var_1=0,
            var_2=0,
            risk_ref=1,
            reduceRisk=True,
            max_r=10,
            entry_module_config=entry_module_config,
            h_highs_trail_period=55,
            h_lows_trail_period=55,
            tp_fac_strat_one=20,
            plotStrategyOneData=False,
            plotTrailsStatOne=False,
            longsAllowed=True,
            shortsAllowed=True,
            timeframe=TIMEFRAME,
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
            indicator_mode="incremental",
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


def build_bot(entry_module_config, open_interest_by_tstamp=None, funding_by_tstamp=None):
    bot = MultiStrategyBot(logger=logger, directionFilter=0)
    bot.add_strategy(
        build_strategy(
            entry_module_config,
            open_interest_by_tstamp=open_interest_by_tstamp,
            funding_by_tstamp=funding_by_tstamp,
        )
    )
    return bot


def normalize_metrics(metrics):
    out = {}
    for key in METRIC_KEYS:
        out[key] = metrics.get(key)
    return out


def compare_metrics(left: dict, right: dict):
    diffs = []
    for key in METRIC_KEYS:
        a = left.get(key)
        b = right.get(key)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            if abs(float(a) - float(b)) > FLOAT_TOL:
                diffs.append({"metric": key, "left": a, "right": b, "delta": float(b) - float(a)})
        elif a != b:
            diffs.append({"metric": key, "left": a, "right": b})
    return diffs


def main():
    exchange = EXCHANGE
    if exchange == "bybit" and "USDT" in PAIR:
        exchange = "bybit-linear"

    bars = load_bars(days_in_history=3000 * 6, wanted_tf=TIMEFRAME, start_offset_minutes=0, exchange=exchange, symbol=PAIR)
    funding = load_funding(exchange, PAIR)
    open_interest = load_open_interest(exchange, PAIR)
    symbol = get_symbol(PAIR)

    flat_cfg = _build_flat_config()
    schema_cfg = _flat_to_schema(flat_cfg)

    legacy_bt = BackTest(
        build_bot(flat_cfg, open_interest_by_tstamp=open_interest, funding_by_tstamp=funding),
        bars=bars,
        funding=funding,
        symbol=symbol,
    ).run()
    schema_bt = BackTest(
        build_bot(schema_cfg, open_interest_by_tstamp=open_interest, funding_by_tstamp=funding),
        bars=bars,
        funding=funding,
        symbol=symbol,
    ).run()

    legacy_metrics = normalize_metrics(extract_metrics(legacy_bt))
    schema_metrics = normalize_metrics(extract_metrics(schema_bt))
    metric_diffs = compare_metrics(legacy_metrics, schema_metrics)
    fp_match = trade_fingerprint(legacy_bt) == trade_fingerprint(schema_bt)

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "legacy_metrics.json").write_text(json.dumps(legacy_metrics, indent=2, sort_keys=True), encoding="utf-8")
    (ARTIFACT_DIR / "schema_metrics.json").write_text(json.dumps(schema_metrics, indent=2, sort_keys=True), encoding="utf-8")
    report = {
        "float_tolerance": FLOAT_TOL,
        "metric_diff_count": len(metric_diffs),
        "trade_fingerprint_match": fp_match,
        "metric_diffs": metric_diffs,
    }
    (ARTIFACT_DIR / "equivalence_report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    if len(metric_diffs) > 0 or not fp_match:
        print("entry_module_schema_equivalence: FAIL")
        raise SystemExit(1)
    print("entry_module_schema_equivalence: PASS")


if __name__ == "__main__":
    main()
