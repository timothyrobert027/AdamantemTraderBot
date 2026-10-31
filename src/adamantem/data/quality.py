"""Basic data quality checks for M1 bid/ask history."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class QualityReport:
    rows: int
    first: pd.Timestamp | None
    last: pd.Timestamp | None
    duplicates: int
    bad_ohlc: int
    negative_spread: int
    weekday_gaps_over_30m: int
    median_spread: float
    p95_spread: float

    @property
    def ok(self) -> bool:
        return self.rows > 0 and self.duplicates == 0 and self.bad_ohlc == 0


def check_m1(m1: pd.DataFrame) -> QualityReport:
    idx = m1.index
    bad = (
        (m1["bid_low"] > m1[["bid_open", "bid_close"]].min(axis=1))
        | (m1["bid_high"] < m1[["bid_open", "bid_close"]].max(axis=1))
        | (m1["bid_low"] <= 0)
    )
    spread = m1["ask_close"] - m1["bid_close"]
    prev, delta = idx[:-1], idx[1:] - idx[:-1]
    # Gaps starting Mon-Thu outside the daily break (~21:00-23:00 UTC) are unexpected.
    unexpected = (delta > pd.Timedelta("30min")) & (prev.day_of_week <= 3) & ~prev.hour.isin([20, 21, 22])
    return QualityReport(
        rows=len(m1),
        first=idx.min() if len(m1) else None,
        last=idx.max() if len(m1) else None,
        duplicates=int(idx.duplicated().sum()),
        bad_ohlc=int(bad.sum()),
        negative_spread=int((spread < 0).sum()),
        weekday_gaps_over_30m=int(unexpected.sum()),
        median_spread=float(spread.median()) if len(m1) else float("nan"),
        p95_spread=float(spread.quantile(0.95)) if len(m1) else float("nan"),
    )
