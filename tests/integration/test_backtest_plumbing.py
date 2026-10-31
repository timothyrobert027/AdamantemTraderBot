"""End-to-end plumbing tests on synthetic random-walk data (no performance meaning)."""

import lzma
from datetime import date

import numpy as np
import pandas as pd
import pytest

from adamantem.backtest.engine import VARIANTS, run_backtest
from adamantem.backtest.market import build_market
from adamantem.backtest.metrics import trades_frame
from adamantem.data.dukascopy import RECORD, parse_day
from adamantem.data.quality import check_m1
from adamantem.risk.sizing import SymbolSpec


@pytest.fixture(scope="module")
def market(cfg, m1):
    return build_market(m1, cfg["strategy"], cfg["scanner"])


def _run(cfg, mk, variant="FVG-A", profile="aggressive", extra=0.0):
    prof = cfg["risk"]["profiles"][profile]
    return run_backtest(mk, cfg["strategy"], cfg["scanner"], cfg["risk"], prof, variant,
                        SymbolSpec(), 500.0, extra)


def test_synthetic_data_passes_quality(m1):
    assert check_m1(m1).ok


def test_pipeline_produces_activity(cfg, market):
    res = _run(cfg, market)
    assert sum(v for k, v in res.counters.items() if k.startswith("arm_")) > 0
    assert sum(v for k, v in res.counters.items() if k.startswith("break_")) > 0


def test_deterministic(cfg, market):
    a = trades_frame(_run(cfg, market))
    b = trades_frame(_run(cfg, market))
    pd.testing.assert_frame_equal(a, b)


@pytest.mark.parametrize("variant", list(VARIANTS))
def test_trade_invariants(cfg, market, variant):
    res = _run(cfg, market, variant)
    for t in res.trades:
        if t.side == "long":
            assert t.stop < t.entry < t.target
        else:
            assert t.target < t.entry < t.stop
        assert t.exit_time > t.entry_time
        assert t.entry_time.day_of_week < 5
        if t.exit_reason == "target":
            assert t.pnl > 0
        if t.exit_reason == "stop":
            assert t.r_multiple < 0
        if t.exit_reason == "breakeven" and len(t.legs) == 1:
            assert -0.5 < t.r_multiple < 0.5
        if any(leg[4] == "tp1" for leg in t.legs):
            assert t.r_multiple > -0.1  # TP1 banked, rest protected at break-even or better
        assert abs(sum(leg[1] for leg in t.legs) - t.volume) < 1e-9
        assert t.volume >= 0.01


def test_parse_dukascopy_day():
    recs = [(60, 2000_000, 2001_000, 1999_500, 2001_500, 3.0), (120, 2001_000, 2001_000, 2001_000, 2001_000, 0.0)]
    raw = lzma.compress(b"".join(RECORD.pack(*r) for r in recs), format=lzma.FORMAT_ALONE)
    df = parse_day(raw, date(2024, 1, 2), 1000.0)
    assert len(df) == 1  # zero-volume padding dropped
    row = df.iloc[0]
    assert (row.open, row.high, row.low, row.close) == (2000.0, 2001.5, 1999.5, 2001.0)
    assert df.index[0] == pd.Timestamp("2024-01-02 00:01", tz="UTC")
    assert np.isfinite(df.to_numpy()).all()


def test_no_edge_on_random_walk(cfg):
    """Null test: with costs, a random walk must not show a positive edge (detects look-ahead)."""
    from tests.conftest import synthetic_m1

    prof = cfg["risk"]["profiles"]["standard"]
    frames = []
    for seed in range(100, 120):
        mk = build_market(synthetic_m1(days=60, seed=seed), cfg["strategy"], cfg["scanner"])
        res = run_backtest(mk, cfg["strategy"], cfg["scanner"], cfg["risk"], prof, "FVG-A",
                           SymbolSpec(), 500.0, 0.0)
        frames.append(trades_frame(res))
    r = pd.concat(frames).r_multiple
    assert len(r) > 400
    t_stat = r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))
    assert t_stat < 2.0, f"random walk shows a significant edge: mean {r.mean():.3f}R, t={t_stat:.2f}"


def test_replay_export_matches_trades(cfg, market):
    from adamantem.backtest.replay import build_replay

    prof = cfg["risk"]["profiles"]["aggressive"]
    res = run_backtest(market, cfg["strategy"], cfg["scanner"], cfg["risk"], prof, "FVG-A",
                       SymbolSpec(), 500.0, 0.0, record_events=True)
    rep = build_replay(market, res, "test", {})
    assert len(rep["trades"]) == len(res.trades)
    for t in rep["trades"]:
        m = t["marks"]
        assert m["arm"] <= m["break"] <= m["fill"] <= m["exit"]
        times = [b[0] for b in t["bars"]]
        assert times == sorted(times) and times[0] <= m["fill"] <= times[-1]
        assert t["day"] in rep["days"]  # every trade day has its bot events
    for events in rep["days"].values():
        assert [e[0] for e in events] == sorted(e[0] for e in events)
        assert {e[1] for e in events} <= {"scanner", "hunter", "sniper", "risk", "exec",
                                          "ledger", "boss"}


def test_breakeven_changes_only_be_variants(cfg, market):
    prof = cfg["risk"]["profiles"]["standard"]
    plain = _run(cfg, market, "FVG-A", "standard")
    be = _run(cfg, market, "FVG-A+BE", "standard")
    assert "breakeven_moves" not in plain.counters
    assert all(t.exit_reason != "breakeven" for t in plain.trades)
    if be.counters.get("breakeven_moves"):
        assert any(t.exit_reason in ("breakeven", "target", "time", "session") for t in be.trades)
    assert prof["risk_per_trade_pct"] == 1.0


def test_three_take_profits_split_and_order(cfg, market):
    res = _run(cfg, market, "FVG-A+3TP", "max")
    multi = [t for t in res.trades if round(t.volume / 0.01) >= 4]
    for t in res.trades:
        sign = 1 if t.side == "long" else -1
        tp1, tp2, tp3 = t.tps
        assert sign * (tp1 - t.entry) > 0 and sign * (tp2 - tp1) > 0 and sign * (tp3 - tp2) >= 0
    for t in multi:  # with 0.04 lot or more, a runner leg exists
        names = {leg[0] for leg in t.legs}
        assert names == {"tp1", "tp2", "tp3", "runner"}
