"""Vectorised indicators. All values at row i use only rows <= i."""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder ATR, seeded with the simple mean of the first ``period`` true ranges."""
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1)
    tr = tr.max(axis=1)
    tr.iloc[0] = high.iloc[0] - low.iloc[0]
    values = np.full(len(tr), np.nan)
    if len(tr) < period:
        return pd.Series(values, index=tr.index)
    trv = tr.to_numpy(dtype=float)
    values[period - 1] = trv[:period].mean()
    for i in range(period, len(trv)):
        values[i] = (values[i - 1] * (period - 1) + trv[i]) / period
    return pd.Series(values, index=tr.index)


def rolling_percentile_rank(series: pd.Series, window: int, min_periods: int) -> pd.Series:
    """Percentile (0-100) of each value within its trailing window, current value included."""
    return series.rolling(window, min_periods=min_periods).rank(pct=True) * 100.0
