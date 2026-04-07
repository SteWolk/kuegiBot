from typing import Dict, List, Tuple

from kuegi_bot.utils.trading_classes import PositionStatus

DEFAULT_METRIC_KEYS = [
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


def trade_fingerprint(backtest) -> List[Tuple[int, int, float, float, float]]:
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


def extract_metrics(backtest, metric_keys=None) -> Dict[str, float]:
    keys = DEFAULT_METRIC_KEYS if metric_keys is None else metric_keys
    metrics = backtest.metrics or {}
    out = {}
    for key in keys:
        value = metrics.get(key)
        if isinstance(value, (int, float)):
            out[key] = float(value)
        else:
            out[key] = value
    return out
