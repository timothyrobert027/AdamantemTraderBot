"""Supply/demand zone detection (base + impulse) on a higher timeframe. See docs/STRATEGY.md §1.

Each zone carries the times between which it is valid, all derived only from bars that
had closed by then:
- ``avail_time``: close of the last impulse candle (zone becomes known);
- ``expire_time``: ``avail_time + max_age_bars * tf``;
- ``invalid_time``: close of the first later bar of this timeframe that closes beyond distal;
- ``dead_time``: set when a higher-scoring overlapping zone of the same side/timeframe appears.
Freshness (first touch) is resolved by the backtest on M5 bars.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from adamantem.indicators.ta import atr as atr_fn

NEVER = pd.Timestamp.max.tz_localize("UTC")


@dataclass
class Zone:
    zid: int
    tf: str
    side: str  # "demand" | "supply"
    proximal: float
    distal: float
    score: float
    base_candles: int
    impulse_atr: float
    avail_time: pd.Timestamp
    expire_time: pd.Timestamp
    invalid_time: pd.Timestamp = NEVER
    dead_time: pd.Timestamp = NEVER
    touch_index: int | None = field(default=None, compare=False)

    @property
    def low(self) -> float:
        return min(self.proximal, self.distal)

    @property
    def high(self) -> float:
        return max(self.proximal, self.distal)

    def end_time(self) -> pd.Timestamp:
        return min(self.expire_time, self.invalid_time, self.dead_time)

    def valid_at(self, t: pd.Timestamp) -> bool:
        return self.avail_time <= t < self.end_time()


def _candidate(o, h, l, c, a, med_atr, j, b, k, p) -> tuple[str, float, float, float] | None:
    """Return (side, proximal, distal, impulse_atr) if bars form a zone ending at j."""
    base = range(j - k - b + 1, j - k + 1)
    imp = range(j - k + 1, j + 1)
    ref = a[j - k]  # ATR measured at the last base candle
    if not np.isfinite(ref) or ref <= 0 or not np.isfinite(med_atr[j]):
        return None
    for i in base:
        rng = h[i] - l[i]
        if rng > p["base_max_range_atr"] * ref or abs(c[i] - o[i]) > p["base_max_body_frac"] * rng:
            return None
    if a[j] < med_atr[j]:  # expansion check
        return None
    dirs = {np.sign(c[i] - o[i]) for i in imp}
    if len(dirs) != 1 or 0 in dirs:
        return None
    for i in imp:
        rng = h[i] - l[i]
        if rng <= 0 or abs(c[i] - o[i]) < p["impulse_min_body_frac"] * rng:
            return None
    base_hi = max(h[i] for i in base)
    base_lo = min(l[i] for i in base)
    if dirs == {1.0}:
        move = c[j] - base_hi
        side, proximal, distal = "demand", max(max(o[i], c[i]) for i in base), base_lo
    else:
        move = base_lo - c[j]
        side, proximal, distal = "supply", min(min(o[i], c[i]) for i in base), base_hi
    if move < p["impulse_min_move_atr"] * ref:
        return None
    if abs(proximal - distal) > p["zone_max_width_atr"] * ref:
        return None
    return side, proximal, distal, move / ref


def detect_zones(bars: pd.DataFrame, tf: str, params: dict, start_id: int = 0) -> list[Zone]:
    """Detect zones on bid bars of timeframe ``tf`` (index = UTC open time)."""
    o = bars["bid_open"].to_numpy()
    h = bars["bid_high"].to_numpy()
    l = bars["bid_low"].to_numpy()
    c = bars["bid_close"].to_numpy()
    a = atr_fn(bars["bid_high"], bars["bid_low"], bars["bid_close"], params["atr_period"]).to_numpy()
    med = pd.Series(a).rolling(20, min_periods=20).median().to_numpy()
    step = pd.Timedelta({"H1": "1h", "H4": "4h"}[tf])
    close_times = bars.index + step
    max_age = params["zone_max_age_bars"][tf]

    zones: list[Zone] = []
    for j in range(len(bars)):
        found = None
        for b in range(1, params["base_max_candles"] + 1):
            for k in range(1, params["impulse_max_candles"] + 1):
                if j - k - b + 1 < 0:
                    continue
                found = _candidate(o, h, l, c, a, med, j, b, k, params)
                if found:
                    break
            if found:
                break
        if not found:
            continue
        side, proximal, distal, imp_atr = found
        avail = close_times[j]
        # Invalidation: first later close beyond distal.
        later = c[j + 1 :]
        beyond = np.nonzero(later < distal if side == "demand" else later > distal)[0]
        invalid = close_times[j + 1 + beyond[0]] if len(beyond) else NEVER
        zones.append(
            Zone(
                zid=start_id + len(zones),
                tf=tf,
                side=side,
                proximal=float(proximal),
                distal=float(distal),
                score=imp_atr + (1.0 if b == 1 else 0.0),
                base_candles=b,
                impulse_atr=float(imp_atr),
                avail_time=avail,
                expire_time=avail + max_age * step,
                invalid_time=invalid,
            )
        )
    _resolve_overlaps(zones)
    return zones


def _resolve_overlaps(zones: list[Zone]) -> None:
    """Between overlapping live zones of the same side, keep the higher score.

    The age penalty in the score (``-0.01 * age_bars``) is applied at comparison time.
    """
    for i, new in enumerate(zones):
        t = new.avail_time
        for old in zones[:i]:
            if old.side != new.side or not old.valid_at(t) or new.dead_time != NEVER:
                continue
            if old.low > new.high or new.low > old.high:
                continue
            step = pd.Timedelta({"H1": "1h", "H4": "4h"}[old.tf])
            old_score = old.score - 0.01 * ((t - old.avail_time) / step)
            if new.score > old_score:
                old.dead_time = t
            else:
                new.dead_time = t
