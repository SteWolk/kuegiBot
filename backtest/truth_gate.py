import argparse
import json
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from backtest_result_tools import extract_metrics, trade_fingerprint
from mode_common import load_backtest_data, run_mode_backtest, setup_logger


def compare_metrics(expected: dict, actual: dict, tol: float):
    failures = []
    for key, expected_value in expected.items():
        actual_value = actual.get(key)
        if isinstance(expected_value, (int, float)) and isinstance(actual_value, (int, float)):
            delta = abs(float(expected_value) - float(actual_value))
            if delta > tol:
                failures.append((key, expected_value, actual_value, delta))
        elif expected_value != actual_value:
            failures.append((key, expected_value, actual_value, math.inf))
    return failures


def main():
    parser = argparse.ArgumentParser(description="Regression gate against frozen truth baseline.")
    parser.add_argument(
        "--baseline",
        default=str(Path(__file__).resolve().parent / "results" / "truth_baselines" / "strategy_one_truth_baseline.json"),
    )
    parser.add_argument("--tol", type=float, default=1e-9)
    parser.add_argument("--indicator-mode", choices=["incremental", "precomputed"], default="incremental")
    parser.add_argument("--scenario-id", action="append", default=None, help="Optional filter. Repeatable.")
    args = parser.parse_args()

    baseline_path = Path(args.baseline).resolve()
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    logger = setup_logger()

    scenario_filter = set(args.scenario_id) if args.scenario_id else None
    cache = {}
    has_failures = False

    for scenario in baseline.get("scenarios", []):
        scenario_id = scenario["scenario_id"]
        if scenario_filter and scenario_id not in scenario_filter:
            continue

        key = (scenario["exchange"], scenario["pair"], scenario["days"], scenario["timeframe"])
        if key not in cache:
            cache[key] = load_backtest_data(
                exchange=scenario["exchange"],
                pair=scenario["pair"],
                days=int(scenario["days"]),
                timeframe=int(scenario["timeframe"]),
            )
        bars, funding, symbol, open_interest = cache[key]
        backtest = run_mode_backtest(
            logger=logger,
            bars=bars,
            funding=funding,
            symbol=symbol,
            timeframe=int(scenario["timeframe"]),
            indicator_mode=args.indicator_mode,
            entry_module_overrides=scenario.get("entry_module_overrides"),
            open_interest_by_tstamp=open_interest,
            funding_by_tstamp=funding,
        )

        actual_metrics = extract_metrics(backtest)
        metric_failures = compare_metrics(scenario.get("metrics", {}), actual_metrics, args.tol)
        expected_fp_raw = scenario.get("trade_fingerprint", [])
        expected_fp = [tuple(item) for item in expected_fp_raw]
        actual_fp = trade_fingerprint(backtest)
        fp_match = expected_fp == actual_fp

        print(f"SCENARIO={scenario_id}")
        print(f"  metrics_failures={len(metric_failures)}")
        print(f"  trade_fingerprint_match={fp_match}")
        if metric_failures:
            has_failures = True
            for key_name, expected, actual, delta in metric_failures:
                print(f"  metric_delta[{key_name}] expected={expected} actual={actual} delta={delta}")
        if not fp_match:
            has_failures = True
            print(f"  expected_trades={len(expected_fp)} actual_trades={len(actual_fp)}")

    if has_failures:
        print("TRUTH_REGRESSION=FAIL")
        return 1
    print("TRUTH_REGRESSION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
