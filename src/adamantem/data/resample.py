"""Resample M1 bid/ask bars to higher timeframes.

Bars are labelled by their UTC open time and cover ``[open, open + tf)``. A bar is only
usable by the strategy after ``open + tf`` (its close time).
"""

from __future__ import annotations

import pandas as pd

TIMEFRAMES = {"M5": "5min", "H1": "1h", "H4": "4h"}

_AGG = {
    "bid_open": "first",
    "bid_high": "max",
    "bid_low": "min",
    "bid_close": "last",
    "ask_open": "first",
    "ask_high": "max",
    "ask_low": "min",
    "ask_close": "last",
    "volume": "sum",
}


def resample(m1: pd.DataFrame, tf: str) -> pd.DataFrame:
    rule = TIMEFRAMES[tf]
    cols = {k: v for k, v in _AGG.items() if k in m1.columns}
    out = m1.resample(rule, label="left", closed="left").agg(cols)
    return out.dropna(subset=["bid_close"])


def timeframe_delta(tf: str) -> pd.Timedelta:
    return pd.Timedelta(TIMEFRAMES[tf])
