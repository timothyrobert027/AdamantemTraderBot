"""Scalping hypothesis plumbing: M1 entries, M15 zones, selection and validation flow."""

import argparse

import numpy as np
import pandas as pd

from adamantem.app import cli, scalp
from adamantem.backtest.engine import run_backtest
from adamantem.backtest.market import build_market
from adamantem.backtest.metrics import trades_frame
from adamantem.risk.sizing import SymbolSpec
from tests.conftest import ROOT, synthetic_m1


def _args(tmp_path):
    return argparse.Namespace(equity=500.0, config=str(ROOT / "config" / "default.yaml"),
                              cache=str(tmp_path), assumed_spread=0.25, out=str(tmp_path))


def _fake_load(start, end, cache, budget, source, spread):
    return synthetic_m1(days=45, seed=start.year, start=str(start))


def test_scalp_without_candidate(tmp_path, monkeypatch):
    monkeypatch.setattr(scalp, "SELECTION", {"min_trades": 10**6})
    report = scalp.run(_args(tmp_path), _fake_load, cli.load_config).read_text()
    assert "NO CANDIDATE" in report and "| validation |" not in report


def test_scalp_selects_and_validates(tmp_path, monkeypatch):
    monkeypatch.setattr(scalp, "SELECTION", {"min_trades": 0})
    report = scalp.run(_args(tmp_path), _fake_load, cli.load_config).read_text()
    assert "## Selected for validation: **S-" in report
    assert "| validation | SWING (validated) |" in report
    assert (tmp_path / "replay.json").exists()


def test_m1_entries_have_no_edge_on_random_walk(cfg):
    params = {**cfg["strategy"], **scalp.SCALP_VARIANTS["S-A"]}
    scanner = {**cfg["scanner"], **scalp.SCANNER_M1}
    risk = {**cfg["risk"], **scalp.RISK_SCALP}
    frames = []
    for seed in range(300, 306):
        mk = build_market(synthetic_m1(days=40, seed=seed), params, scanner)
        assert mk.bar == pd.Timedelta("1min")
        res = run_backtest(mk, params, scanner, risk, cfg["risk"]["profiles"]["standard"],
                           scalp.ENTRY_VARIANT, SymbolSpec())
        frames.append(trades_frame(res))
    r = pd.concat(frames).r_multiple
    assert len(r) > 30
    t_stat = r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))
    assert t_stat < 2.0, f"M1 entries show an edge on a random walk: t={t_stat:.2f}"
