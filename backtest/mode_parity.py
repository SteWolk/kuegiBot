import argparse
import math
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from mode_common import load_backtest_data, run_mode_backtest, setup_logger
from kuegi_bot.utils.trading_classes import PositionStatus


def _trade_fingerprint(backtest):
    closed = []
    for pos in backtest.bot.position_history:
        if pos.status != PositionStatus.CLOSED:
            continue
        closed.append(
            (
                int(pos.entry_tstamp),
                int(pos.exit_tstamp),
                round(float(pos.filled_entry or 0.0), 8),
                round(float(pos.filled_exit or 0.0), 8),
                round(float(pos.max_filled_amount or 0.0), 8),
            )
        )
    return closed


def _metrics_diff(m1, m2):
    keys = [
        "trades_closed",
        "final_equity",
        "profit_pct",
        "max_drawdown_pct",
        "max_exposure_pct",
        "relY_final",
        "relY_final_trades",
        "cagr",
        "mar",
        "winrate",
        "avg_R",
        "profit_factor",
        "sqn_trades",
    ]
    deltas = {}
    for key in keys:
        v1 = m1.get(key)
        v2 = m2.get(key)
        if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
            deltas[key] = abs(float(v1) - float(v2))
        else:
            deltas[key] = 0.0 if v1 == v2 else math.inf
    return deltas


def main():
    parser = argparse.ArgumentParser(description="Check incremental vs precomputed indicator parity.")
    parser.add_argument("--pair", default="BTCUSD")
    parser.add_argument("--exchange", default="bybit")
    parser.add_argument("--days", type=int, default=600 * 6)
    parser.add_argument("--timeframe", type=int, default=240)
    parser.add_argument("--tol", type=float, default=1e-9)
    args = parser.parse_args()

    logger = setup_logger()
    bars, funding, symbol, open_interest = load_backtest_data(
        exchange=args.exchange,
        pair=args.pair,
        days=args.days,
        timeframe=args.timeframe,
    )

    bt_incremental = run_mode_backtest(
        logger=logger,
        bars=bars,
        funding=funding,
        symbol=symbol,
        timeframe=args.timeframe,
        indicator_mode="incremental",
        open_interest_by_tstamp=open_interest,
        funding_by_tstamp=funding,
    )
    bt_precomputed = run_mode_backtest(
        logger=logger,
        bars=bars,
        funding=funding,
        symbol=symbol,
        timeframe=args.timeframe,
        indicator_mode="precomputed",
        open_interest_by_tstamp=open_interest,
        funding_by_tstamp=funding,
    )

    metrics_inc = bt_incremental.metrics or {}
    metrics_pre = bt_precomputed.metrics or {}
    metric_deltas = _metrics_diff(metrics_inc, metrics_pre)
    max_delta = max(metric_deltas.values()) if metric_deltas else 0.0

    trades_inc = _trade_fingerprint(bt_incremental)
    trades_pre = _trade_fingerprint(bt_precomputed)
    trades_match = trades_inc == trades_pre

    print("PARITY SUMMARY")
    print(f"bars={len(bars)} pair={args.pair} exchange={args.exchange} timeframe={args.timeframe}")
    print(f"max_metric_delta={max_delta:.12f} tol={args.tol}")
    print(f"trades_incremental={len(trades_inc)} trades_precomputed={len(trades_pre)}")
    print(f"trades_match={trades_match}")

    if max_delta <= args.tol and trades_match:
        print("PARITY_RESULT=PASS")
        return 0

    print("PARITY_RESULT=FAIL")
    if not trades_match:
        print("reason=trade_fingerprint_mismatch")
    for key, delta in metric_deltas.items():
        if delta > args.tol:
            print(f"delta[{key}]={delta}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
