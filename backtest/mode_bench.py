import argparse
import statistics
import sys
import time
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from mode_common import load_backtest_data, run_mode_backtest, setup_logger


def _run_once(logger, bars, funding, symbol, open_interest, timeframe, mode):
    t0 = time.perf_counter()
    bt = run_mode_backtest(
        logger=logger,
        bars=bars,
        funding=funding,
        symbol=symbol,
        timeframe=timeframe,
        indicator_mode=mode,
        open_interest_by_tstamp=open_interest,
        funding_by_tstamp=funding,
    )
    dt = time.perf_counter() - t0
    trades = 0 if bt.metrics is None else bt.metrics.get("trades_closed", 0)
    return dt, trades, bt.metrics


def main():
    parser = argparse.ArgumentParser(description="Benchmark incremental vs precomputed indicator modes.")
    parser.add_argument("--pair", default="BTCUSD")
    parser.add_argument("--exchange", default="bybit")
    parser.add_argument("--days", type=int, default=1000 * 6)
    parser.add_argument("--timeframe", type=int, default=240)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()

    logger = setup_logger()
    bars, funding, symbol, open_interest = load_backtest_data(
        exchange=args.exchange,
        pair=args.pair,
        days=args.days,
        timeframe=args.timeframe,
    )

    times_inc = []
    times_pre = []
    metrics_inc = None
    metrics_pre = None

    for _ in range(args.repeats):
        dt_inc, _trades_inc, metrics_inc = _run_once(
            logger=logger,
            bars=bars,
            funding=funding,
            symbol=symbol,
            open_interest=open_interest,
            timeframe=args.timeframe,
            mode="incremental",
        )
        times_inc.append(dt_inc)

        dt_pre, _trades_pre, metrics_pre = _run_once(
            logger=logger,
            bars=bars,
            funding=funding,
            symbol=symbol,
            open_interest=open_interest,
            timeframe=args.timeframe,
            mode="precomputed",
        )
        times_pre.append(dt_pre)

    avg_inc = statistics.mean(times_inc)
    avg_pre = statistics.mean(times_pre)
    speedup = (avg_inc / avg_pre) if avg_pre > 0 else 0.0

    print("BENCHMARK SUMMARY")
    print(f"bars={len(bars)} pair={args.pair} exchange={args.exchange} timeframe={args.timeframe}")
    print(f"runs={args.repeats}")
    print(f"incremental_seconds={avg_inc:.4f}")
    print(f"precomputed_seconds={avg_pre:.4f}")
    print(f"speedup_x={speedup:.4f}")
    if metrics_inc is not None and metrics_pre is not None:
        print(f"incremental_profit_pct={metrics_inc.get('profit_pct'):.6f}")
        print(f"precomputed_profit_pct={metrics_pre.get('profit_pct'):.6f}")
        print(f"incremental_max_dd_pct={metrics_inc.get('max_drawdown_pct'):.6f}")
        print(f"precomputed_max_dd_pct={metrics_pre.get('max_drawdown_pct'):.6f}")


if __name__ == "__main__":
    main()
