"""Download free XAUUSD M1 bars from HistData.com (one ZIP per year, or per month for the
current year).

HistData ASCII M1 files are bid quotes with timestamps in EST *without* daylight saving
(fixed UTC-5). There is no ask, so the ask side is built from an assumed constant spread
that the backtest report states. This is NOT Vantage's feed.

Download flow: the page for a year/month carries a hidden form (``id="file_down"``) with a
one-time token; posting that form to ``get.php`` (with the page as Referer) returns the ZIP.
"""

from __future__ import annotations

import io
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

BASE = "https://www.histdata.com"
PAGE = BASE + "/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/{pair}/{period}"
POST = BASE + "/get.php"
UA = "Mozilla/5.0 (adamantem-research)"
SOURCE_TZ_OFFSET = pd.Timedelta(hours=5)  # EST without DST -> UTC


class HistDataError(RuntimeError):
    pass


def _request(url: str, data: bytes | None = None, referer: str | None = None) -> bytes:
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, data=data, headers=headers)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3:
                raise
            time.sleep(2 ** (attempt + 2))
    raise HistDataError(f"unreachable: {url}")


def form_fields(page_html: str) -> dict[str, str]:
    """Extract the hidden inputs of the download form from a HistData page."""
    form = re.search(r'<form[^>]*id="file_down".*?</form>', page_html, re.S | re.I)
    if not form:
        raise HistDataError("download form not found on the page")
    fields = {}
    for tag in re.findall(r"<input[^>]*>", form.group(0), re.I):
        name = re.search(r'name="([^"]+)"', tag)
        value = re.search(r'value="([^"]*)"', tag)
        if name:
            fields[name.group(1)] = value.group(1) if value else ""
    if not fields.get("tk"):
        raise HistDataError("download token missing from the form")
    return fields


def fetch_zip(pair: str, period: str, cache_dir: Path) -> bytes | None:
    """Return the ZIP for ``period`` ('2023' or '2025/7'), cached; None if not offered."""
    dest = cache_dir / f"{pair}_{period.replace('/', '_')}.zip"
    if dest.exists():
        return dest.read_bytes()
    page_url = PAGE.format(pair=pair.lower(), period=period)
    html = _request(page_url).decode("utf-8", "replace")
    try:
        fields = form_fields(html)
    except HistDataError:
        return None
    raw = _request(POST, urllib.parse.urlencode(fields).encode(), referer=page_url)
    if not raw.startswith(b"PK"):
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    time.sleep(2)  # be polite between files
    return raw


def parse_zip(raw: bytes) -> pd.DataFrame:
    """Parse a HistData ASCII M1 ZIP into bid OHLC indexed by UTC open time."""
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        text = zf.read(name).decode("utf-8", "replace")
    df = pd.read_csv(
        io.StringIO(text), sep=";", header=None,
        names=["dt", "open", "high", "low", "close", "volume"],
    )
    ts = pd.to_datetime(df["dt"], format="%Y%m%d %H%M%S") + SOURCE_TZ_OFFSET
    out = df[["open", "high", "low", "close"]].astype(float)
    out.index = pd.DatetimeIndex(ts.dt.tz_localize("UTC"), name="time")
    return out[~out.index.duplicated()].sort_index()


def download_m1(
    pair: str, start: date, end: date, cache_dir: Path, assumed_spread: float
) -> pd.DataFrame:
    """Return M1 bars with bid_* and synthetic ask_* columns (bid + assumed spread)."""
    frames = []
    for year in range(start.year, end.year + 1):
        raw = fetch_zip(pair, str(year), cache_dir)
        if raw is not None:
            frames.append(parse_zip(raw))
            continue
        for month in range(1, 13):  # current year: offered month by month
            if date(year, month, 1) >= end:
                break
            raw = fetch_zip(pair, f"{year}/{month}", cache_dir)
            if raw is None:
                raise HistDataError(f"no HistData file for {pair} {year}-{month:02d}")
            frames.append(parse_zip(raw))
    if not frames:
        raise HistDataError("no data downloaded")
    bid = pd.concat(frames).sort_index()
    bid = bid[~bid.index.duplicated()]
    lo = pd.Timestamp(start, tz="UTC")
    hi = pd.Timestamp(end, tz="UTC")
    bid = bid[(bid.index >= lo) & (bid.index < hi)]
    m1 = bid.add_prefix("bid_")
    for col in ("open", "high", "low", "close"):
        m1[f"ask_{col}"] = m1[f"bid_{col}"] + assumed_spread
    m1["volume"] = 1.0
    return m1
