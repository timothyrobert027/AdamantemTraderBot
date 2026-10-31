"""Precomputed, look-ahead-safe market arrays used by the backtest loop.

Everything at entry-bar index ``i`` (M5, or M1 for scalping) is known at the close of bar ``i``:
higher-timeframe values come from the last H1/H4 bar that had closed by then.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from adamantem.data.resample import TIMEFRAMES, resample
from adamantem.indicators.ta import atr, ema, rolling_percentile_rank
from adamantem.strategy.fvg import FVG, detect_fvgs
from adamantem.strategy.htf_zones import detect_ob_fvg_zones
from adamantem.strategy.zones import Zone, detect_zones

MINUTES_PER_DAY = 1440


@dataclass
class Market:
    t_open: pd.DatetimeIndex
    bar: pd.Timedelta  # entry-bar length (M5 by default, M1 for scalping)
    bo: np.ndarray
    bh: np.ndarray
    bl: np.ndarray
    bc: np.ndarray
    ao: np.ndarray
    ah: np.ndarray
    al: np.ndarray
    ac: np.ndarray
    atr5: np.ndarray
    vol_pct: np.ndarray
    atr_h1: np.ndarray
    trend_up: np.ndarray
    trend_down: np.ndarray
    close_minute: np.ndarray  # minute of day (UTC) of each bar's close
    close_weekday: np.ndarray
    prev_low_min: np.ndarray  # min low of the previous N bars
    prev_high_max: np.ndarray
    bear: list[FVG | None]
    bull: list[FVG | None]
    zones: list[Zone]
    zone_start: dict[int, list[int]]  # M5 index -> zone ids becoming available
    zone_touch: dict[int, list[int]]  # M5 index -> zone ids touched for the first time
    zone_fresh_end: dict[int, list[int]]  # M5 index -> zone ids no longer fresh
    zone_valid_end: dict[int, list[int]]  # M5 index -> zone ids no longer valid


def _map_htf(htf: pd.DataFrame, step: str, values: dict[str, pd.Series], m5_close) -> dict:
    avail = htf.index + pd.Timedelta(step)
    frame = pd.DataFrame({k: v.to_numpy() for k, v in values.items()}, index=avail)
    left = pd.DataFrame(index=m5_close)
    merged = pd.merge_asof(left, frame, left_index=True, right_index=True, direction="backward")
    return {k: merged[k].to_numpy() for k in values}


def build_market(m1: pd.DataFrame, params: dict, scanner: dict) -> Market:
    entry_tf = params.get("entry_timeframe", "M5")
    m5 = m1 if entry_tf == "M1" else resample(m1, entry_tf)  # entry bars (named m5 for history)
    bar = pd.Timedelta(TIMEFRAMES[entry_tf])
    bars_per_day = int(MINUTES_PER_DAY / (bar / pd.Timedelta("1min")))
    h1 = resample(m1, "H1")
    h4 = resample(m1, "H4")
    t_open = m5.index
    m5_close = t_open + bar

    atr5 = atr(m5["bid_high"], m5["bid_low"], m5["bid_close"], params["atr_period"])
    lookback = scanner["vol_lookback_days"] * bars_per_day
    vol_pct = rolling_percentile_rank(atr5, lookback, min_periods=10 * bars_per_day)

    h1_atr = atr(h1["bid_high"], h1["bid_low"], h1["bid_close"], params["atr_period"])
    h1_ema = ema(h1["bid_close"], params["trend_ema"])
    mapped = _map_htf(
        h1, "1h", {"atr": h1_atr, "ema": h1_ema, "close": h1["bid_close"]}, m5_close
    )
    trend_up = mapped["close"] > mapped["ema"]
    trend_down = mapped["close"] < mapped["ema"]

    n_ext = params["no_zone_extreme_bars"]
    low = m5["bid_low"]
    high = m5["bid_high"]
    prev_low_min = low.rolling(n_ext).min().shift(1).to_numpy()
    prev_high_max = high.rolling(n_ext).max().shift(1).to_numpy()

    bear, bull = detect_fvgs(
        high.to_numpy(), low.to_numpy(), atr5.to_numpy(), params["fvg_min_size_atr"]
    )

    zones: list[Zone] = []
    htf = {"H4": h4, "H1": h1}
    if "M15" in params["zone_timeframes"]:
        htf["M15"] = resample(m1, "M15")
    tfs = {tf: bars for tf, bars in htf.items() if tf in params["zone_timeframes"]}
    if params.get("zone_model", "ob_fvg") == "ob_fvg":
        zones = detect_ob_fvg_zones(tfs, params)
    else:  # v1: base + impulse supply/demand
        for tf, bars in tfs.items():
            zones += detect_zones(bars, tf, params, start_id=len(zones))

    bl = low.to_numpy()
    bh = high.to_numpy()
    starts: dict[int, list[int]] = {}
    touches: dict[int, list[int]] = {}
    fresh_end: dict[int, list[int]] = {}
    valid_end: dict[int, list[int]] = {}
    for z in zones:
        s = int(t_open.searchsorted(z.avail_time, "left"))
        e = int(t_open.searchsorted(z.end_time(), "left"))
        if s >= e:
            continue
        seg = bl[s:e] <= z.proximal if z.side == "demand" else bh[s:e] >= z.proximal
        hit = np.flatnonzero(seg)
        starts.setdefault(s, []).append(z.zid)
        valid_end.setdefault(e, []).append(z.zid)
        if len(hit):
            z.touch_index = s + int(hit[0])
            touches.setdefault(z.touch_index, []).append(z.zid)
            fresh_end.setdefault(z.touch_index, []).append(z.zid)
        else:
            fresh_end.setdefault(e, []).append(z.zid)

    return Market(
        t_open=t_open,
        bar=bar,
        bo=m5["bid_open"].to_numpy(),
        bh=bh,
        bl=bl,
        bc=m5["bid_close"].to_numpy(),
        ao=m5["ask_open"].to_numpy(),
        ah=m5["ask_high"].to_numpy(),
        al=m5["ask_low"].to_numpy(),
        ac=m5["ask_close"].to_numpy(),
        atr5=atr5.to_numpy(),
        vol_pct=vol_pct.to_numpy(),
        atr_h1=mapped["atr"],
        trend_up=trend_up,
        trend_down=trend_down,
        close_minute=(m5_close.hour * 60 + m5_close.minute).to_numpy(),
        close_weekday=m5_close.day_of_week.to_numpy(),
        prev_low_min=prev_low_min,
        prev_high_max=prev_high_max,
        bear=bear,
        bull=bull,
        zones=zones,
        zone_start=starts,
        zone_touch=touches,
        zone_fresh_end=fresh_end,
        zone_valid_end=valid_end,
    )
