"""Scalping S2 plumbing: trend-armed FVGs, multi-touch zones, opening-range signals."""

import argparse
import collections

import numpy as np
import pandas as pd
import pytest

from adamantem.app import cli, scalp2
from adamantem.backtest.engine import run_backtest
from adamantem.backtest.market import build_market
from adamantem.backtest.metrics import trades_frame
from adamantem.risk.sizing import SymbolSpec
from adamantem.strategy.orb import orb_signals
from tests.conftest import ROOT, synthetic_m1


def test_orb_signal_london_winter():
    # 2024-01-15 (winter): London 08:00 local = 08:00 UTC. Range 08:00-08:30, break at 08:40.
    idx = pd.date_range("2024-01-15 07:00", "2024-01-15 10:00", freq="5min", tz="UTC")
    n = len(idx)
    bh, bl, bc = np.full(n, 100.5), np.full(n, 99.5), np.full(n, 100.0)
    k = idx.get_loc(pd.Timestamp("2024-01-15 08:40", tz="UTC"))
    bh[k], bc[k] = 102.0, 101.5
    sig = orb_signals(idx, bh, bl, bc, np.full(n, 1.0), {
        "orb_range_minutes": 30, "orb_breakout_window_minutes": 120, "sl_buffer_atr": 0.2})
    longs = [s for v in sig.values() for s in v if s.side == "long"]
    assert len(longs) == 1 and longs[0].index == k and longs[0].session == "LON"
    assert longs[0].limit == 100.5 and abs(longs[0].stop - (100.0 - 0.2)) < 1e-9


def test_orb_signal_respects_dst():
    # 2024-07-15 (summer): London 08:00 local = 07:00 UTC.
    idx = pd.date_range("2024-07-15 06:00", "2024-07-15 09:00", freq="5min", tz="UTC")
    n = len(idx)
    bh, bl, bc = np.full(n, 100.5), np.full(n, 99.5), np.full(n, 100.0)
    k = idx.get_loc(pd.Timestamp("2024-07-15 07:35", tz="UTC"))
    bl[k], bc[k] = 98.0, 98.5
    sig = orb_signals(idx, bh, bl, bc, np.full(n, 1.0), {
        "orb_range_minutes": 30, "orb_breakout_window_minutes": 120, "sl_buffer_atr": 0.2})
    assert [s.side for s in sig.get(k, [])] == ["short"]


def test_multi_touch_zones_rearm(cfg):
    params = {**cfg["strategy"], **scalp2.S2_VARIANTS["S2-B"]}
    mk = build_market(synthetic_m1(days=60), params, {**cfg["scanner"], **scalp2.SCANNER_S2})
    per_zone = collections.Counter(z for zs in mk.zone_touch.values() for z in zs)
    assert per_zone and max(per_zone.values()) <= 3 and max(per_zone.values()) > 1


@pytest.mark.parametrize("name", list(scalp2.S2_VARIANTS))
def test_s2_no_edge_on_random_walk(cfg, name):
    params, scanner, risk = scalp2._setup(name, cfg)
    frames = []
    for seed in range(400, 406):
        mk = build_market(synthetic_m1(days=45, seed=seed), params, scanner)
        res = run_backtest(mk, params, scanner, risk, cfg["risk"]["profiles"]["standard"],
                           scalp2.ENTRY_VARIANT, SymbolSpec())
        frames.append(trades_frame(res))
    df = pd.concat(frames)
    assert len(df) > 20, f"{name}: too few trades to test"
    r = df.r_multiple
    t_stat = r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))
    assert t_stat < 2.0, f"{name} shows an edge on a random walk: t={t_stat:.2f}"


def _args(tmp_path):
    return argparse.Namespace(equity=500.0, config=str(ROOT / "config" / "default.yaml"),
                              cache=str(tmp_path), assumed_spread=0.25, out=str(tmp_path))


def _fake_load(start, end, cache, budget, source, spread):
    return synthetic_m1(days=40, seed=start.year, start=str(start))


def test_scalp2_no_candidate_still_tests_swing(tmp_path, monkeypatch):
    monkeypatch.setattr(scalp2, "SELECTION", {"min_trades_per_day": 99, "min_avg_r": 0})
    text = scalp2.run(_args(tmp_path), _fake_load, cli.load_config).read_text()
    assert "**NO CANDIDATE**" in text and "Validated swing configuration on 2016-2020" in text
    assert (tmp_path / "replay.json").exists()


def test_scalp2_selects_and_validates(tmp_path, monkeypatch):
    monkeypatch.setattr(scalp2, "SELECTION", {"min_trades_per_day": 0, "min_avg_r": -99})
    text = scalp2.run(_args(tmp_path), _fake_load, cli.load_config).read_text()
    assert "## S2 selected: **S2-" in text and "| validation | S2-" in text
