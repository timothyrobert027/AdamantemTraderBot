"""The holdout command runs the frozen config and never trades before the holdout start."""

import argparse
import json

import pandas as pd

from adamantem.app import cli
from tests.conftest import ROOT, synthetic_m1


def test_holdout_command(tmp_path, monkeypatch):
    def fake_load(start, end, cache, budget, source, spread):
        days = (end - start).days
        return synthetic_m1(days=min(days, 150), seed=start.year, start=str(start))

    monkeypatch.setattr(cli, "load_m1", fake_load)
    args = argparse.Namespace(
        end="2025-12-20", equity=500.0, config=str(ROOT / "config" / "default.yaml"),
        cache=str(tmp_path), assumed_spread=0.25, out=str(tmp_path),
    )
    report = cli.holdout(args)
    text = report.read_text()
    assert "## Verdict:" in text and "FVG-D" in text
    replay = json.loads((tmp_path / "replay.json").read_text())
    start = pd.Timestamp("2025-11-01", tz="UTC")
    for t in replay["trades"]:
        assert pd.Timestamp(t["marks"]["fill"] * 60, unit="s", tz="UTC") >= start
        assert t["zone_kind"] in ("OB", "FVG")  # zone setups only
