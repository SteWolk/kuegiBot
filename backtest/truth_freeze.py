import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from result_tools import extract_metrics, trade_fingerprint
from mode_common import load_backtest_data, run_mode_backtest, setup_logger
from truth_scenarios import DEFAULT_TRUTH_SCENARIOS


def atomic_write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)


def main():
    parser = argparse.ArgumentParser(description="Freeze truth baseline for regression gating.")
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parent / "results" / "truth_baselines" / "strategy_one_truth_baseline.json"),
    )
    parser.add_argument("--indicator-mode", choices=["incremental", "precomputed"], default="incremental")
    args = parser.parse_args()

    logger = setup_logger()
    cache = {}
    baseline = {"indicator_mode": args.indicator_mode, "scenarios": []}

    for scenario in DEFAULT_TRUTH_SCENARIOS:
        key = (scenario.exchange, scenario.pair, scenario.days, scenario.timeframe)
        if key not in cache:
            cache[key] = load_backtest_data(
                exchange=scenario.exchange,
                pair=scenario.pair,
                days=scenario.days,
                timeframe=scenario.timeframe,
            )
        bars, funding, symbol, open_interest = cache[key]
        backtest = run_mode_backtest(
            logger=logger,
            bars=bars,
            funding=funding,
            symbol=symbol,
            timeframe=scenario.timeframe,
            indicator_mode=args.indicator_mode,
            entry_module_overrides=scenario.entry_module_overrides,
            open_interest_by_tstamp=open_interest,
            funding_by_tstamp=funding,
        )

        baseline["scenarios"].append(
            {
                "scenario_id": scenario.scenario_id,
                "pair": scenario.pair,
                "exchange": scenario.exchange,
                "timeframe": scenario.timeframe,
                "days": scenario.days,
                "entry_module_overrides": scenario.entry_module_overrides,
                "metrics": extract_metrics(backtest),
                "trade_fingerprint": trade_fingerprint(backtest),
            }
        )

    out_path = Path(args.out).resolve()
    atomic_write_text(out_path, json.dumps(baseline, indent=2, sort_keys=True))
    print(f"BASELINE_WRITTEN={out_path}")


if __name__ == "__main__":
    main()
