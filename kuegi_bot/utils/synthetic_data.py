import random
from typing import List

from kuegi_bot.utils.trading_classes import Bar


def _make_bar(tstamp: int, o: float, h: float, l: float, c: float, v: float) -> Bar:
    sub = Bar(tstamp=tstamp + 30, open=o, high=h, low=l, close=c, volume=max(v, 1.0), subbars=[])
    return Bar(tstamp=tstamp, open=o, high=h, low=l, close=c, volume=max(v, 1.0), subbars=[sub])


def generate_synthetic_bars(
        n_bars: int = 5000,
        start_price: float = 20000.0,
        timeframe_seconds: int = 60 * 60,
        seed: int = 42,
        spike_probability: float = 0.02) -> List[Bar]:
    """Generate synthetic OHLCV bars in newest-first order used by the backtest engine.

    The generator alternates between ranging and trending blocks and injects random spikes so
    mean-reversion strategies can be validated without exchange history.
    """
    random.seed(seed)

    price = start_price
    t0 = 1_700_000_000
    bars_oldest_first: List[Bar] = []

    mode = "range"
    mode_left = 0

    for i in range(n_bars):
        if mode_left <= 0:
            mode = "trend" if random.random() < 0.45 else "range"
            mode_left = random.randint(40, 180)
            trend_dir = 1 if random.random() > 0.5 else -1
            trend_strength = random.uniform(0.0003, 0.0015) * trend_dir
        mode_left -= 1

        if mode == "range":
            drift = random.uniform(-0.0006, 0.0006)
            vol = random.uniform(0.0004, 0.0025)
        else:
            drift = trend_strength + random.uniform(-0.0005, 0.0005)
            vol = random.uniform(0.0003, 0.0018)

        spike = 0.0
        if random.random() < spike_probability:
            spike = random.choice([-1, 1]) * random.uniform(0.008, 0.03)

        ret = drift + random.gauss(0, vol) + spike
        ret = max(min(ret, 0.08), -0.08)

        o = price
        c = max(100.0, price * (1.0 + ret))

        wick = abs(c - o) * random.uniform(0.1, 0.7) + o * random.uniform(0.0001, 0.001)
        h = max(o, c) + wick
        l = min(o, c) - wick
        l = max(1.0, l)

        base_vol = 1000.0 if mode == "range" else 1400.0
        v = base_vol * (1.0 + abs(ret) * 80.0) * random.uniform(0.7, 1.4)

        bars_oldest_first.append(_make_bar(t0 + i * timeframe_seconds, o, h, l, c, v))
        price = c

    return list(reversed(bars_oldest_first))
