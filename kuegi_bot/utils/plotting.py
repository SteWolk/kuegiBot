# KuegiBot/kuegi_bot/utils/plotting.py

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

import plotly.graph_objects as go
from plotly.subplots import make_subplots


def plot_price_with_funding(
    bars: List,
    funding: Dict[int, float] | Dict[str, float],
    title: str = "Price + Funding",
) -> go.Figure:
    """
    Plot candlesticks (bars) with a funding-rate subplot.

    Key behavior:
    - Funding is clipped to the exact time window covered by `bars`.
    - Funding is plotted as a forward-filled line aligned to bar timestamps (easy to read).

    bars: list of bar objects (must have .tstamp, .open, .high, .low, .close)
    funding: dict {unix_seconds -> funding_rate}; keys may be int or str
    """

    if not bars:
        raise ValueError("bars is empty; cannot determine plotting range.")

    # Determine the backtest time window from the actual bars used
    start_ts = min(int(b.tstamp) for b in bars)
    end_ts = max(int(b.tstamp) for b in bars)

    # Normalize funding keys to int seconds and clip to the bar time range
    f: Dict[int, float] = {}
    for k, v in funding.items():
        try:
            ts = int(k)
            if start_ts <= ts <= end_ts:
                f[ts] = float(v)
        except Exception:
            continue

    # Build price series
    t = [datetime.fromtimestamp(int(b.tstamp)) for b in bars]
    o = [b.open for b in bars]
    h = [b.high for b in bars]
    l = [b.low for b in bars]
    c = [b.close for b in bars]

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.75, 0.25],
        specs=[[{"type": "candlestick"}], [{"type": "scatter"}]],
    )

    # Price (row 1)
    fig.add_trace(
        go.Candlestick(x=t, open=o, high=h, low=l, close=c, name="Price"),
        row=1,
        col=1,
    )

    # Funding as a forward-filled line aligned to bar timestamps (row 2)
    last: Optional[float] = None
    rates: List[float] = []
    for b in bars:
        ts = int(b.tstamp)
        if ts in f:
            last = f[ts]
        rates.append(last if last is not None else 0.0)

    fig.add_trace(
        go.Scatter(x=t, y=rates, mode="lines", name="Funding rate"),
        row=2,
        col=1,
    )

    fig.update_layout(
        title=title,
        xaxis_rangeslider_visible=False,
        legend_orientation="h",
        legend_y=1.02,
    )
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="Funding", row=2, col=1)

    return fig
