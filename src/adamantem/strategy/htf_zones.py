"""Order blocks and fair value gaps on M15/H1/H4 as zones (strategy v2). See docs/STRATEGY.md §1.

Bullish order block: the last bearish candle before a bullish displacement. Within
``ob_max_impulse_bars`` candles after it, the move must close above the OB high, travel at
least ``ob_min_displacement_atr`` x ATR from the OB low, and leave a bullish FVG. The zone is
the OB candle's range (proximal = high, distal = low). Bearish order blocks mirror this.

HTF FVG zone: a 3-candle gap of at least ``htf_fvg_min_size_atr`` x ATR. A bullish gap is a
demand zone (proximal = top, distal = bottom); a bearish gap is a supply zone.

When an OB and an FVG of the same side are within ``ob_fvg_near_atr`` x ATR of each other
(any timeframe), the FVG is dropped and the OB kept.

Every zone becomes known at the close of the candle that confirms it, and is invalidated by
the first later close beyond its distal edge, as in ``zones.py``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from adamantem.indicators.ta import atr as atr_fn
from adamantem.strategy.zones import NEVER, Zone, _resolve_overlaps

STEP = {"M15": pd.Timedelta("15min"), "H1": pd.Timedelta("1h"), "H4": pd.Timedelta("4h")}


def _arrays(bars: pd.DataFrame, period: int):
    o = bars["bid_open"].to_numpy()
    h = bars["bid_high"].to_numpy()
    l = bars["bid_low"].to_numpy()
    c = bars["bid_close"].to_numpy()
    a = atr_fn(bars["bid_high"], bars["bid_low"], bars["bid_close"], period).to_numpy()
    return o, h, l, c, a


def _invalid_time(c: np.ndarray, close_times, j: int, side: str, distal: float):
    later = c[j + 1 :]
    beyond = np.nonzero(later < distal if side == "demand" else later > distal)[0]
    return close_times[j + 1 + beyond[0]] if len(beyond) else NEVER


def _zone(tf, kind, side, proximal, distal, score, j, close_times, c, max_age, atr_ref):
    avail = close_times[j]
    z = Zone(
        zid=-1, tf=tf, side=side, proximal=float(proximal), distal=float(distal),
        score=float(score), base_candles=1, impulse_atr=float(score),
        avail_time=avail, expire_time=avail + max_age * STEP[tf],
        invalid_time=_invalid_time(c, close_times, j, side, distal), kind=kind,
    )
    z.atr = float(atr_ref)
    return z


def detect_order_blocks(bars: pd.DataFrame, tf: str, p: dict) -> list[Zone]:
    o, h, l, c, a = _arrays(bars, p["atr_period"])
    close_times = bars.index + STEP[tf]
    k_max = p["ob_max_impulse_bars"]
    zones = []
    for j in range(len(bars) - 1):
        ref = a[j]
        if not np.isfinite(ref) or ref <= 0:
            continue
        for side, ob_dir in (("demand", -1), ("supply", 1)):
            if np.sign(c[j] - o[j]) != ob_dir or np.sign(c[j + 1] - o[j + 1]) != -ob_dir:
                continue  # OB is the last opposite candle: the next one starts the impulse
            if h[j] - l[j] > p["ob_max_width_atr"] * ref:
                continue
            broke = moved = gap = None
            for i in range(j + 1, min(j + 1 + k_max, len(bars))):
                if side == "demand":
                    if broke is None and c[i] > h[j]:
                        broke = i
                    if moved is None and c[i] - l[j] >= p["ob_min_displacement_atr"] * ref:
                        moved = i
                    if gap is None and i >= j + 2 and l[i] > h[i - 2]:
                        gap = i
                else:
                    if broke is None and c[i] < l[j]:
                        broke = i
                    if moved is None and h[j] - c[i] >= p["ob_min_displacement_atr"] * ref:
                        moved = i
                    if gap is None and i >= j + 2 and h[i] < l[i - 2]:
                        gap = i
            if broke is None or moved is None or gap is None:
                continue
            confirm = max(broke, moved, gap)
            disp = (c[confirm] - l[j]) if side == "demand" else (h[j] - c[confirm])
            proximal, distal = (h[j], l[j]) if side == "demand" else (l[j], h[j])
            zones.append(_zone(tf, "OB", side, proximal, distal, disp / ref, confirm,
                               close_times, c, p["zone_max_age_bars"][tf], ref))
    return zones


def detect_htf_fvgs(bars: pd.DataFrame, tf: str, p: dict) -> list[Zone]:
    o, h, l, c, a = _arrays(bars, p["atr_period"])
    close_times = bars.index + STEP[tf]
    zones = []
    for i in range(2, len(bars)):
        ref = a[i]
        if not np.isfinite(ref) or ref <= 0:
            continue
        min_size = p["htf_fvg_min_size_atr"] * ref
        if l[i] > h[i - 2] and l[i] - h[i - 2] >= min_size:
            size = l[i] - h[i - 2]
            zones.append(_zone(tf, "FVG", "demand", l[i], h[i - 2], size / ref, i,
                               close_times, c, p["zone_max_age_bars"][tf], ref))
        if h[i] < l[i - 2] and l[i - 2] - h[i] >= min_size:
            size = l[i - 2] - h[i]
            zones.append(_zone(tf, "FVG", "supply", h[i], l[i - 2], size / ref, i,
                               close_times, c, p["zone_max_age_bars"][tf], ref))
    return zones


def prefer_order_blocks(zones: list[Zone], near_atr: float) -> None:
    """Drop an FVG zone when an order block of the same side is near it (any timeframe).

    Decided in time order: when the later of the pair appears, the FVG dies at that moment,
    so nothing is known before it could have been.
    """
    zones.sort(key=lambda z: z.avail_time)
    for i, new in enumerate(zones):
        t = new.avail_time
        for old in zones[:i]:
            if old.side != new.side or old.kind == new.kind or not old.valid_at(t):
                continue
            if new.dead_time != NEVER:
                break
            gap = max(old.low - new.high, new.low - old.high, 0.0)
            if gap > near_atr * max(old.atr, new.atr):
                continue
            fvg = old if old.kind == "FVG" else new
            fvg.dead_time = t


def detect_ob_fvg_zones(bars_by_tf: dict[str, pd.DataFrame], p: dict) -> list[Zone]:
    zones: list[Zone] = []
    for tf, bars in bars_by_tf.items():
        for kind_zones in (detect_order_blocks(bars, tf, p), detect_htf_fvgs(bars, tf, p)):
            kind_zones.sort(key=lambda z: z.avail_time)
            _resolve_overlaps(kind_zones)  # same kind + timeframe: higher score wins
            zones += kind_zones
    prefer_order_blocks(zones, p["ob_fvg_near_atr"])
    for n, z in enumerate(zones):
        z.zid = n
    return zones
