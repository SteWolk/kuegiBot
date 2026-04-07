import argparse
import json
import math
import os
import re
import sys
from datetime import datetime
from time import sleep
from typing import Dict, Optional, Tuple

import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download and persist historical price data.")
    parser.add_argument("exchange", nargs="?", default="bybit")
    parser.add_argument("symbol", nargs="?", default="BTCUSD")
    parser.add_argument(
        "--with-open-interest",
        action="store_true",
        help="Also fetch and persist Bybit open-interest history for the same symbol window.",
    )
    parser.add_argument(
        "--oi-interval",
        default="5min",
        help="Bybit OI intervalTime (e.g. 5min, 15min, 30min, 1h, 4h, 1d).",
    )
    parser.add_argument(
        "--oi-limit",
        type=int,
        default=200,
        help="Bybit OI page size (max 200).",
    )
    parser.add_argument(
        "--oi-max-pages",
        type=int,
        default=1000,
        help="Safety guard to stop OI pagination loops.",
    )
    return parser.parse_args()


def open_interest_file_name(exchange: str, symbol: str) -> str:
    return f"./history/{exchange}/{symbol}_open_interest.json"


def history_file_name(index: int, exchange: str, symbol: str) -> str:
    return f"./history/{exchange}/{symbol}_M1_{index}.json"


def is_future_time(start_time: int, milli: bool) -> bool:
    now = int(datetime.now().timestamp() * 1000) - 120000 if milli else int(datetime.now().timestamp()) - 120
    return int(start_time) > int(now)


def load_existing_history(exchange: str, symbol: str):
    loaded_data = []
    directory = f"./history/{exchange}/"
    try:
        file_list = os.listdir(directory)
    except FileNotFoundError:
        print(f"Directory {directory} not found.")
        return [loaded_data, 0]

    def _numerical_sort(value: str):
        parts = re.split(r"(\d+)", value)
        parts[1::2] = map(int, parts[1::2])
        return parts

    sorted_files = sorted(file_list, key=_numerical_sort)
    count = 0
    for filename in sorted_files:
        if not (filename.startswith(f"{symbol}_M1_") and filename.endswith(".json")):
            continue
        try:
            with open(os.path.join(directory, filename), "r", encoding="utf-8") as file:
                file_data = json.load(file)
        except Exception:
            continue
        if len(file_data) > 0:
            loaded_data += file_data
            count += 1

    if not loaded_data:
        print(f"No history files found for {exchange} - {symbol}. Starting fresh.")
    return [loaded_data, count]


def _load_existing_open_interest(file_path: str) -> Dict[int, float]:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return {}

    series = raw.get("series") if isinstance(raw, dict) and isinstance(raw.get("series"), dict) else raw
    if not isinstance(series, dict):
        return {}

    out: Dict[int, float] = {}
    for ts_raw, oi_raw in series.items():
        try:
            ts_int = int(ts_raw)
            oi_val = float(oi_raw)
        except Exception:
            continue
        if math.isfinite(oi_val):
            out[ts_int] = oi_val
    return out


def _write_open_interest(
    file_path: str,
    exchange: str,
    symbol: str,
    category: str,
    interval: str,
    series: Dict[int, float],
):
    ordered = {str(k): series[k] for k in sorted(series.keys())}
    payload = {
        "exchange": exchange,
        "symbol": symbol,
        "category": category,
        "interval": interval,
        "unit": "exchange_native",
        "updated_at": int(datetime.utcnow().timestamp()),
        "series": ordered,
    }
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def _to_millis(exchange: str, row) -> Optional[int]:
    try:
        if exchange in ("bybit", "bybit-linear", "okx", "bitfinex"):
            return int(row[0])
        if exchange == "bitstamp":
            return int(row["timestamp"]) * 1000
        if exchange in ("kucoin-spot", "kucoin-futures"):
            return int(row[0]) * 1000
    except Exception:
        return None
    return None


def _price_history_bounds_ms(exchange: str, data) -> Tuple[Optional[int], Optional[int]]:
    if not data:
        return None, None
    first_ms = _to_millis(exchange, data[0])
    last_ms = _to_millis(exchange, data[-1])
    return first_ms, last_ms


def _fetch_bybit_open_interest_history(
    exchange: str,
    symbol: str,
    start_ms: int,
    end_ms: int,
    interval: str,
    limit: int,
    max_pages: int,
) -> Dict[int, float]:
    if start_ms > end_ms:
        start_ms, end_ms = end_ms, start_ms

    category = "linear" if exchange == "bybit-linear" else "inverse"
    url = "https://api.bybit.com/v5/market/open-interest"
    page_end = int(end_ms)
    page_limit = max(1, min(int(limit), 200))
    out: Dict[int, float] = {}
    pages = 0

    while pages < max_pages and page_end >= start_ms:
        params = {
            "category": category,
            "symbol": symbol,
            "intervalTime": interval,
            "startTime": int(start_ms),
            "endTime": int(page_end),
            "limit": page_limit,
        }

        try:
            response = requests.get(url=url, params=params, timeout=15)
        except Exception as exc:
            print(f"Failed to fetch OI page: {exc}")
            break

        if response.status_code == 429:
            print("Bybit OI rate limit reached. Retrying in 2 seconds.")
            sleep(2)
            continue
        if response.status_code != 200:
            print(f"Bybit OI request failed with HTTP {response.status_code}.")
            break

        try:
            payload = response.json()
        except Exception:
            print("Bybit OI response is not valid JSON.")
            break

        ret_code = payload.get("retCode")
        if str(ret_code) not in ("0", "None"):
            ret_msg = payload.get("retMsg")
            print(f"Bybit OI API error: retCode={ret_code}, retMsg={ret_msg}")
            if str(ret_code) in ("10006", "429"):
                sleep(2)
                continue
            break

        result = payload.get("result") or {}
        rows = result.get("list") or []
        if len(rows) == 0:
            break

        min_seen_ms = None
        for row in rows:
            try:
                ts_ms = int(row.get("timestamp"))
                oi_value = float(row.get("openInterest"))
            except Exception:
                continue
            if ts_ms < start_ms or ts_ms > end_ms:
                continue
            if not math.isfinite(oi_value):
                continue
            out[int(ts_ms // 1000)] = oi_value
            if min_seen_ms is None or ts_ms < min_seen_ms:
                min_seen_ms = ts_ms

        if min_seen_ms is None or min_seen_ms <= start_ms:
            break

        page_end = int(min_seen_ms) - 1
        pages += 1
        sleep(0.05)

    return out


def _default_start(exchange: str, symbol: str) -> int:
    starts = {
        ("bybit", "ETHUSD"): 1548633600000,
        ("bybit", "BTCUSD"): 1542502800000,
        ("bybit-linear", "BTCUSDT"): 1585526400000,
        ("bybit-linear", "MNTUSDT"): 1698062401000,
        ("bybit-linear", "HBARUSDT"): 1635595201000,
        ("bitstamp", "btcusd"): 1322312400,
        ("kucoin-spot", "BTC-USDT"): 1508720400,
        ("okx", "BTC-USDT"): 1534294800000,
        ("bitfinex", "BTCUSD"): 1372467600000,
    }
    key = (exchange, symbol)
    if key not in starts:
        raise ValueError(f"symbol not found for exchange: {exchange} {symbol}")
    return int(starts[key])


def main():
    args = parse_args()
    exchange = str(args.exchange)
    symbol = str(args.symbol)
    print("Pulling " + symbol + " price data from " + exchange)

    os.makedirs("history/" + exchange, exist_ok=True)

    exclude_current_candle = True
    batch_size = 50000
    acc_data = []
    milli = exchange in ("bybit", "bybit-linear", "okx", "bitfinex")
    jump = False

    limits = {
        "bybit": 1000,
        "bybit-linear": 1000,
        "bitstamp": 1000,
        "kucoin-spot": 1500,
        "kucoin-futures": 1500,
        "okx": 100,
        "bitfinex": 1000,
    }
    if exchange not in limits:
        sys.exit("exchange not found")
    limit = limits[exchange]

    urls = {
        "bybit": f"https://api.bybit.com/v5/market/kline?category=inverse&symbol={symbol}&interval=1&limit={limit}",
        "bybit-linear": f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval=1&limit={limit}",
        "bitstamp": f"https://www.bitstamp.net/api/v2/ohlc/{symbol}/?step=60&limit={limit}&exclude_current_candle={exclude_current_candle}",
        "kucoin-spot": f"https://api.kucoin.com/api/v1/market/candles?type=1min&symbol={symbol}",
        "kucoin-futures": f"https://api-futures.kucoin.com/api/v1/market/candles?type=1min&symbol={symbol}",
        "okx": f"https://www.okx.com/api/v5/market/history-candles?instId={symbol}&limit={limit}",
        "bitfinex": f"https://api-pub.bitfinex.com/v2/candles/trade:1m:t{symbol}/hist?sort=1&limit={limit}",
    }

    try:
        start = _default_start(exchange=exchange, symbol=symbol)
    except Exception as exc:
        sys.exit(str(exc))

    acc_data, nmb_files = load_existing_history(exchange, symbol)

    while True:
        if len(acc_data) > 0 and not jump:
            if exchange in ("bybit", "bybit-linear", "okx", "bitfinex"):
                latest_timestamp = int(acc_data[-1][0])
                start = latest_timestamp
                print(datetime.fromtimestamp(latest_timestamp / 1000))
            elif exchange == "bitstamp":
                latest_timestamp = int(acc_data[-1]["timestamp"])
                start = latest_timestamp
                print(datetime.fromtimestamp(latest_timestamp))
            elif exchange in ("kucoin-spot", "kucoin-futures"):
                latest_timestamp = int(acc_data[-1][0])
                start = latest_timestamp
                print(datetime.fromtimestamp(latest_timestamp))
            else:
                print("Could not update the latest timestamp.")
                break

        if is_future_time(start, milli):
            print("All price data pulled. Good luck!")
            break

        end = start + limit * 60 * 1000 if milli else start + limit * 60
        if jump:
            print("Seems like there is no data available for this period. Trying to jump.")
            start = end
            end = start + limit * 60 * 1000 if milli else start + limit * 60
            jump = False

        if exchange in ("kucoin-spot", "kucoin-futures"):
            url = urls[exchange] + "&startAt=" + str(start) + "&endAt=" + str(end)
        elif exchange == "okx":
            url = urls[exchange] + "&after=" + str(end)
        else:
            url = urls[exchange] + "&start=" + str(start) + "&end=" + str(end)
        print(url + " __ " + str(len(acc_data)))

        response = requests.get(url=url)
        if response.status_code != 200:
            if response.status_code == 429:
                print("Too many requests. Stopping for now.")
            else:
                print("Something went wrong. I am done.")
            break

        try:
            payload = response.json()
        except ValueError:
            print("Could not parse JSON response. I am done.")
            break

        if exchange in ("bybit", "bybit-linear"):
            ret_code = payload.get("retCode")
            if str(ret_code) not in ("0", "None"):
                ret_msg = payload.get("retMsg")
                print(f"Bybit API error: retCode={ret_code}, retMsg={ret_msg}")
                if str(ret_code) in ("10006", "429"):
                    print("Rate limited by Bybit. Waiting 2 seconds and retrying.")
                    sleep(2)
                    continue
                break
            result = payload.get("result") or {}
            data = result.get("list")
            if data is None:
                print(f"Unexpected Bybit payload (missing result.list): {payload}")
                break
            data.reverse()
            package_complete = len(data) >= limit - 1
            if len(acc_data) > 0 and len(data) > 0 and data[0][0] == acc_data[-1][0]:
                print("removed duplicate timestamp: " + str(data[0][0]))
                data = data[1:]
        elif exchange == "bitstamp":
            data = payload["data"]["ohlc"]
            package_complete = len(data) >= limit
            if len(acc_data) > 0 and len(data) > 0 and data[0]["timestamp"] == acc_data[-1]["timestamp"]:
                print("removed duplicate timestamp: " + str(data[0]["timestamp"]))
                data = data[1:]
        elif exchange in ("kucoin-spot", "kucoin-futures", "okx"):
            data = payload["data"]
            data.reverse()
            package_complete = len(data) >= limit - 1
            if len(acc_data) > 0 and len(data) > 0 and data[0][0] == acc_data[-1][0]:
                print("removed duplicate timestamp: " + str(data[0][0]))
                data = data[1:]
        elif exchange in ("bitfinex",):
            data = payload
            package_complete = len(data) >= limit - 1
            if len(acc_data) > 0 and len(data) > 0 and data[0][0] == acc_data[-1][0]:
                print("removed duplicate timestamp: " + str(data[0][0]))
                data = data[1:]
        else:
            break

        if len(data) == 0:
            jump = True
        else:
            acc_data += data

        next_file = (len(acc_data) > batch_size and nmb_files == 0) or (
            len(acc_data) > batch_size * nmb_files and nmb_files > 0
        )
        if next_file or not package_complete:
            idx = nmb_files - 1
            while idx < nmb_files + 1:
                if idx >= 0:
                    file_path = history_file_name(idx, exchange, symbol)
                    with open(file_path, "w") as file:
                        content = acc_data[idx * batch_size : (idx + 1) * batch_size]
                        json.dump(content, file)
                        print("wrote to file " + str(idx))
                idx += 1

        if next_file:
            nmb_files += 1

        if not package_complete:
            print("Received less data than expected: " + str(len(data)) + " entries")
            print("Short break. Will continue shortly after.")
            sleep(1)

    if not args.with_open_interest:
        return

    if exchange not in ("bybit", "bybit-linear"):
        print("Open-interest fetch currently supports bybit and bybit-linear only. Skipping.")
        return

    start_ms, end_ms = _price_history_bounds_ms(exchange=exchange, data=acc_data)
    if start_ms is None or end_ms is None:
        print("No price history available to determine OI window. Skipping open-interest fetch.")
        return

    oi_file = open_interest_file_name(exchange=exchange, symbol=symbol)
    existing_oi = _load_existing_open_interest(oi_file)
    if len(existing_oi) > 0:
        latest_existing_ms = int(max(existing_oi.keys()) * 1000)
        fetch_start_ms = max(int(start_ms), latest_existing_ms + 1)
    else:
        fetch_start_ms = int(start_ms)

    if fetch_start_ms > int(end_ms):
        print("Open-interest history already up to date.")
        return

    print(
        "Pulling open interest from %s (%s) [%s..%s]"
        % (
            exchange,
            symbol,
            datetime.fromtimestamp(fetch_start_ms / 1000),
            datetime.fromtimestamp(int(end_ms) / 1000),
        )
    )
    fetched_oi = _fetch_bybit_open_interest_history(
        exchange=exchange,
        symbol=symbol,
        start_ms=fetch_start_ms,
        end_ms=int(end_ms),
        interval=str(args.oi_interval),
        limit=int(args.oi_limit),
        max_pages=int(args.oi_max_pages),
    )
    if len(fetched_oi) == 0:
        print("No new open-interest points fetched.")
        return

    merged = dict(existing_oi)
    merged.update(fetched_oi)
    category = "linear" if exchange == "bybit-linear" else "inverse"
    _write_open_interest(
        file_path=oi_file,
        exchange=exchange,
        symbol=symbol,
        category=category,
        interval=str(args.oi_interval),
        series=merged,
    )
    print("Wrote open-interest file: %s (%d points)" % (oi_file, len(merged)))


if __name__ == "__main__":
    main()
