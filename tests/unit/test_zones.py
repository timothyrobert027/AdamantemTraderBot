import numpy as np
import pandas as pd

from adamantem.strategy.zones import detect_zones


def _bars(rows):
    idx = pd.date_range("2024-01-01", periods=len(rows), freq="1h", tz="UTC")
    o, h, l, c = zip(*rows)
    return pd.DataFrame({"bid_open": o, "bid_high": h, "bid_low": l, "bid_close": c}, index=idx)


def test_demand_zone_base_then_impulse(cfg):
    p = dict(cfg["strategy"])
    # 40 bars of range 2 (ATR ~2), then a 1-candle base, then a strong bullish impulse.
    rows = [(100, 101, 99, 100.2) if i % 2 else (100.2, 101, 99, 100) for i in range(40)]
    rows.append((100.0, 100.8, 99.4, 100.3))  # base: range 1.4 <= ATR, body 0.3 <= 0.5*range
    rows.append((100.3, 106.0, 100.2, 105.8))  # impulse: body 5.5 >= 0.6*range, move >= 2*ATR
    rows += [(105.8, 106.5, 105.0, 106.0)] * 5
    zones = detect_zones(_bars(rows), "H1", p)
    demand = [z for z in zones if z.side == "demand"]
    assert len(demand) == 1
    z = demand[0]
    assert z.proximal == 100.3 and z.distal == 99.4
    assert z.avail_time == _bars(rows).index[41] + pd.Timedelta("1h")
    assert z.invalid_time == pd.Timestamp.max.tz_localize("UTC")


def test_zone_invalidated_by_close_beyond_distal(cfg):
    p = dict(cfg["strategy"])
    rows = [(100, 101, 99, 100.2) if i % 2 else (100.2, 101, 99, 100) for i in range(40)]
    rows.append((100.0, 100.8, 99.4, 100.3))
    rows.append((100.3, 106.0, 100.2, 105.8))
    rows += [(105.8, 106.0, 99.0, 99.2)]  # closes below distal 99.4
    bars = _bars(rows)
    z = [z for z in detect_zones(bars, "H1", p) if z.side == "demand"][0]
    assert z.invalid_time == bars.index[42] + pd.Timedelta("1h")


def test_no_zone_without_impulse(cfg):
    rows = [(100, 101, 99, 100.2) if i % 2 else (100.2, 101, 99, 100) for i in range(40)]
    assert detect_zones(_bars(rows), "H1", dict(cfg["strategy"])) == []


def test_zone_detection_has_no_lookahead(cfg, m1):
    from adamantem.data.resample import resample

    h1 = resample(m1, "H1")
    p = dict(cfg["strategy"])
    full = detect_zones(h1, "H1", p)
    cut_at = h1.index[len(h1) // 2]
    part = detect_zones(h1[h1.index < cut_at], "H1", p)
    known = [(z.side, z.proximal, z.distal, z.avail_time) for z in full if z.avail_time <= cut_at]
    assert known == [(z.side, z.proximal, z.distal, z.avail_time) for z in part]
    assert np.isfinite([z.proximal for z in full]).all()
