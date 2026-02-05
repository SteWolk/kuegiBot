import os
import json
import time
import requests

BYBIT_BASE_URL = "https://api.bybit.com"
MAX_LIMIT = 200

def exchange_to_category(exchange: str) -> str:
    if exchange == "bybit":
        return "inverse"
    if exchange == "bybit-linear":
        return "linear"
    raise ValueError("Only 'bybit' (inverse) and 'bybit-linear' (linear) are supported.")

def fetch_page(category: str, symbol: str, end_time_ms: int, limit: int = MAX_LIMIT):
    url = f"{BYBIT_BASE_URL}/v5/market/funding/history"
    params = {
        "category": category,
        "symbol": symbol,
        "endTime": end_time_ms,
        "limit": limit
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get("retCode") != 0:
        raise RuntimeError(f"Bybit error: {data}")
    return data["result"]["list"]

def pull_funding(exchange: str, symbol: str, out_path: str, earliest_ts_sec: int | None = None):
    category = exchange_to_category(exchange)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    funding = {}  # {unix_seconds: rate}
    end_ms = int(time.time() * 1000)

    while True:
        rows = fetch_page(category, symbol, end_ms, MAX_LIMIT)
        if not rows:
            break

        # rows are typically newest -> older; store and then page backwards
        min_seen_ms = None
        for row in rows:
            ts_ms = int(row["fundingRateTimestamp"])
            rate = float(row["fundingRate"])
            ts_sec = ts_ms // 1000
            funding[ts_sec] = rate
            min_seen_ms = ts_ms if (min_seen_ms is None or ts_ms < min_seen_ms) else min_seen_ms

        # stop if we reached requested earliest timestamp
        if earliest_ts_sec is not None and (min_seen_ms // 1000) <= earliest_ts_sec:
            break

        # page backwards: next endTime should be just before the earliest timestamp we saw
        end_ms = min_seen_ms - 1

        # be polite to rate limits
        time.sleep(0.05)

    # write as JSON with string keys (stable with your current loader)
    payload = {str(ts): funding[ts] for ts in sorted(funding.keys())}
    with open(out_path, "w") as f:
        json.dump(payload, f)

    print(f"Wrote {len(payload)} funding points to {out_path}")

if __name__ == "__main__":
    # Examples:
    # Inverse BTCUSD
    pull_funding(
        exchange="bybit",
        symbol="BTCUSD",
        out_path="history/bybit/BTCUSD_funding.json"
    )

    # Linear BTCUSDT
    pull_funding(
        exchange="bybit-linear",
        symbol="BTCUSDT",
        out_path="history/bybit-linear/BTCUSDT_funding.json"
    )
