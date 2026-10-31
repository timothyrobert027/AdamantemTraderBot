"""Fair value gap detection on M5 bid bars. See docs/STRATEGY.md §3.

The FVG whose third candle is bar ``i`` is known at the close of bar ``i``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class FVG:
    index: int  # index of the third candle
    side: str  # "bearish" | "bullish"
    bottom: float
    top: float

    @property
    def mid(self) -> float:
        return (self.top + self.bottom) / 2.0


def detect_fvgs(
    high: np.ndarray, low: np.ndarray, atr: np.ndarray, min_size_atr: float
) -> tuple[list[FVG | None], list[FVG | None]]:
    """Return per-bar lists (bearish, bullish) with the FVG completed at that bar, or None."""
    n = len(high)
    bear: list[FVG | None] = [None] * n
    bull: list[FVG | None] = [None] * n
    for i in range(2, n):
        if not np.isfinite(atr[i]):
            continue
        min_size = min_size_atr * atr[i]
        if high[i] < low[i - 2] and low[i - 2] - high[i] >= min_size:
            bear[i] = FVG(i, "bearish", bottom=float(high[i]), top=float(low[i - 2]))
        if low[i] > high[i - 2] and low[i] - high[i - 2] >= min_size:
            bull[i] = FVG(i, "bullish", bottom=float(high[i - 2]), top=float(low[i]))
    return bear, bull
