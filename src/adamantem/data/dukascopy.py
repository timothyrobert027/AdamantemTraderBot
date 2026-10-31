"""Download free historical M1 candles (bid and ask) from the Dukascopy datafeed.

Day files: ``{BASE}/{SYMBOL}/{YYYY}/{MM-1:02d}/{DD:02d}/{BID|ASK}_candles_min_1.bi5``,
LZMA-compressed, big-endian records ``(sec_of_day, open, close, low, high, volume)``.
Prices are integers scaled by ``PRICE_DIVISOR``. Timestamps are UTC.

This is NOT Vantage's feed: spreads and prints differ. See docs/MT5_INTEGRATION.md.
"""

from __future__ import annotations

import lzma
import struct
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BASE_URL = "https://datafeed.dukascopy.com/datafeed"
PRICE_DIVISOR = {"XAUUSD": 1000.0}
RECORD = struct.Struct(">5if")


def day_url(symbol: str, day: date, side: str) -> str:
    return (
        f"{BASE_URL}/{symbol}/{day.year}/{day.month - 1:02d}/{day.day:02d}/"
        f"{side}_candles_min_1.bi5"
    )


def parse_day(raw: bytes, day: date, divisor: float) -> pd.DataFrame:
    """Decode one bi5 day file into an M1 frame indexed by UTC open time."""
    cols = ["open", "high", "low", "close", "volume"]
    if not raw:
        return pd.DataFrame(columns=cols, index=pd.DatetimeIndex([], tz="UTC", name="time"))
    data = lzma.decompress(raw)
    recs = np.array(list(RECORD.iter_unpack(data)), dtype=float)
    start = pd.Timestamp(day, tz="UTC")
    index = start + pd.to_timedelta(recs[:, 0], unit="s")
    frame = pd.DataFrame(
        {
            "open": recs[:, 1] / divisor,
            "high": recs[:, 4] / divisor,
            "low": recs[:, 3] / divisor,
            "close": recs[:, 2] / divisor,
            "volume": recs[:, 5],
        },
        index=pd.DatetimeIndex(index, name="time"),
    )
    # Dukascopy pads no-trade minutes with flat zero-volume candles.
    return frame[frame["volume"] > 0]


def _fetch(url: str, dest: Path, retries: int = 8) -> bytes:
    """Fetch one file with caching; backs off on rate limiting (HTTP 429/503) and timeouts."""
    if dest.exists():
        return dest.read_bytes()
    request = urllib.request.Request(url, headers={"User-Agent": "adamantem-research/0.1"})
    for attempt in range(retries):
        wait = min(2 ** (attempt + 1), 60)
        try:
            with urllib.request.urlopen(request, timeout=30) as resp:
                raw = resp.read()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
            return raw
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return b""
            if exc.code not in (429, 500, 502, 503, 504) or attempt == retries - 1:
                raise
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            if retry_after and retry_after.isdigit():
                wait = max(wait, int(retry_after))
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries - 1:
                raise
        time.sleep(wait)
    return b""


def download_m1(
    symbol: str, start: date, end: date, cache_dir: Path, workers: int = 3
) -> pd.DataFrame:
    """Return M1 bars with bid_* and ask_* OHLC columns for [start, end)."""
    divisor = PRICE_DIVISOR[symbol]
    days = [start + timedelta(d) for d in range((end - start).days)]
    days = [d for d in days if d.weekday() != 5]  # Saturday has no gold trading

    def load(args: tuple[date, str]) -> pd.DataFrame:
        day, side = args
        dest = cache_dir / symbol / f"{day:%Y%m%d}_{side}.bi5"
        return parse_day(_fetch(day_url(symbol, day, side), dest), day, divisor)

    jobs = [(d, s) for d in days for s in ("BID", "ASK")]
    with ThreadPoolExecutor(workers) as pool:
        frames = []
        for n, frame in enumerate(pool.map(load, jobs), 1):
            frames.append(frame)
            if n % 200 == 0:
                print(f"downloaded {n}/{len(jobs)} day files", flush=True)
    bid = pd.concat(frames[0::2])
    ask = pd.concat(frames[1::2])
    m1 = bid.add_prefix("bid_").join(ask.drop(columns="volume").add_prefix("ask_"), how="inner")
    return m1.rename(columns={"bid_volume": "volume"}).sort_index()
