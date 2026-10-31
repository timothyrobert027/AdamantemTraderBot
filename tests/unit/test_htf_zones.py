import pandas as pd

from adamantem.strategy.htf_zones import (
    detect_htf_fvgs,
    detect_ob_fvg_zones,
    detect_order_blocks,
)
from adamantem.strategy.zones import NEVER


def _bars(rows):
    idx = pd.date_range("2024-01-01", periods=len(rows), freq="1h", tz="UTC")
    o, h, l, c = zip(*rows)
    return pd.DataFrame({"bid_open": o, "bid_high": h, "bid_low": l, "bid_close": c}, index=idx)


def _flat(n=40):  # ATR ~2
    return [(100, 101, 99, 100.2) if i % 2 else (100.2, 101, 99, 100) for i in range(n)]


def _bullish_ob_rows():
    rows = _flat()
    rows.append((100.4, 100.6, 99.0, 99.3))    # 40: OB, last bearish candle (range 1.6)
    rows.append((99.3, 102.5, 99.2, 102.3))    # 41: impulse, closes above OB high 100.6
    rows.append((102.3, 104.8, 101.8, 104.6))  # 42: low 101.8 > high[40] 100.6 -> FVG; +5.6 from OB low
    rows += [(104.6, 105.2, 104.0, 104.8)] * 4
    return rows


def test_bullish_order_block(cfg):
    bars = _bars(_bullish_ob_rows())
    obs = [z for z in detect_order_blocks(bars, "H1", cfg["strategy"]) if z.side == "demand"]
    assert len(obs) == 1
    z = obs[0]
    assert z.kind == "OB" and (z.proximal, z.distal) == (100.6, 99.0)
    assert z.avail_time == bars.index[42] + pd.Timedelta("1h")  # confirmed by the FVG candle
    assert z.invalid_time == NEVER


def test_no_order_block_without_displacement_gap(cfg):
    rows = _flat()
    rows.append((100.4, 100.6, 99.0, 99.3))
    rows.append((99.3, 100.9, 99.2, 100.8))   # closes above OB high but weak, no FVG
    rows += [(100.8, 101.0, 100.4, 100.6)] * 4
    obs = detect_order_blocks(_bars(rows), "H1", cfg["strategy"])
    assert [z for z in obs if z.side == "demand"] == []


def test_htf_fvg_zone(cfg):
    fvgs = detect_htf_fvgs(_bars(_bullish_ob_rows()), "H1", cfg["strategy"])
    demand = [z for z in fvgs if z.side == "demand"]
    assert any((z.proximal, z.distal) == (101.8, 100.6) for z in demand)


def test_order_block_wins_over_nearby_fvg(cfg):
    bars = _bars(_bullish_ob_rows())
    zones = detect_ob_fvg_zones({"H1": bars}, cfg["strategy"])
    ob = next(z for z in zones if z.kind == "OB" and z.side == "demand")
    fvg = next(z for z in zones if z.kind == "FVG" and z.side == "demand" and z.distal == 100.6)
    assert ob.dead_time == NEVER
    assert fvg.dead_time == ob.avail_time  # dropped when the OB became known, not before
    assert len({z.zid for z in zones}) == len(zones)


def test_ob_fvg_detection_has_no_lookahead(cfg, m1):
    from adamantem.data.resample import resample

    h1 = resample(m1, "H1")
    cut = h1.index[len(h1) // 2]
    full = detect_ob_fvg_zones({"H1": h1}, cfg["strategy"])
    part = detect_ob_fvg_zones({"H1": h1[h1.index < cut]}, cfg["strategy"])
    key = lambda z: (z.kind, z.side, z.proximal, z.distal, z.avail_time)  # noqa: E731
    assert sorted(map(key, (z for z in full if z.avail_time <= cut))) == sorted(map(key, part))
