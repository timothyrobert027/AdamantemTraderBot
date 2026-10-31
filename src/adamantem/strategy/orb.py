"""Opening-range breakout + retest signals (scalping family C). See docs/SCALPING_S2.md.

For each London (08:00 Europe/London) and New York (09:30 America/New_York) open, DST-aware:
- range = high/low of the first ``orb_range_minutes`` after the open (all entry bars present);
- the first entry-bar close above the range high (long) / below the range low (short) within
  ``orb_breakout_window_minutes`` after the range gives one signal per side per session;
- order: limit on the retest of the broken edge; stop beyond the range midpoint by
  ``sl_buffer_atr`` x ATR; the order is cancelled if price closes back through the midpoint.
Signals are known at the close of the breakout bar.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

SESSIONS = (("Europe/London", 8, 0, "LON"), ("America/New_York", 9, 30, "NY"))


@dataclass(frozen=True)
class OrbSignal:
    side: str
    index: int  # breakout bar
    range_index: int  # first bar of the range
    limit: float
    stop: float
    gap_bottom: float  # cancel band for the engine's "inversion failed" rule
    gap_top: float
    session: str


def orb_signals(t_open: pd.DatetimeIndex, bh, bl, bc, atr, params: dict) -> dict[int, list]:
    bar = t_open[1] - t_open[0] if len(t_open) > 1 else pd.Timedelta("5min")
    n_range = int(pd.Timedelta(minutes=params["orb_range_minutes"]) / bar)
    window = pd.Timedelta(minutes=params["orb_breakout_window_minutes"])
    buf = params["sl_buffer_atr"]
    out: dict[int, list] = {}
    if len(t_open) == 0:
        return out
    days = pd.date_range(t_open[0].normalize(), t_open[-1].normalize(), freq="D")
    for tz, hh, mm, name in SESSIONS:
        for day in days:
            local = pd.Timestamp(day.date(), tz=tz) + pd.Timedelta(hours=hh, minutes=mm)
            if local.day_of_week >= 5:
                continue
            start = local.tz_convert("UTC")
            s = int(t_open.searchsorted(start))
            e = s + n_range
            if e >= len(t_open) or t_open[s] != start or t_open[e - 1] != start + (n_range - 1) * bar:
                continue  # incomplete range (holiday or missing data)
            hi, lo = float(bh[s:e].max()), float(bl[s:e].min())
            mid = (hi + lo) / 2
            stop_i = int(t_open.searchsorted(start + n_range * bar + window))
            seen = set()
            for i in range(e, min(stop_i, len(t_open))):
                a = atr[i]
                if not np.isfinite(a):
                    continue
                if "long" not in seen and bc[i] > hi:
                    seen.add("long")
                    out.setdefault(i, []).append(
                        OrbSignal("long", i, s, hi, mid - buf * a, mid, hi, name))
                if "short" not in seen and bc[i] < lo:
                    seen.add("short")
                    out.setdefault(i, []).append(
                        OrbSignal("short", i, s, lo, mid + buf * a, lo, mid, name))
                if len(seen) == 2:
                    break
    return out
