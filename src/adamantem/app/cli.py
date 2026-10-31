"""Command line entry point: ``python -m adamantem.app.cli backtest ...``."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from adamantem.backtest.engine import VARIANTS, run_backtest
from adamantem.backtest.market import build_market
from adamantem.backtest.metrics import breakdown, summarize, trades_frame
from adamantem.backtest.replay import build_replay, write_replay
from adamantem.data.dukascopy import IncompleteDownload, download_m1
from adamantem.data.quality import check_m1
from adamantem.risk.sizing import SymbolSpec

ROOT = Path(__file__).resolve().parents[3]
SPREAD_SCENARIOS = {"dukascopy": 0.0, "stress_+0.20": 0.20}


def load_config(path: Path) -> dict:
    cfg = yaml.safe_load(path.read_text())
    assert cfg["mode"] != "live" and cfg["live_trading_enabled"] is False
    return cfg


def load_m1(start: date, end: date, cache: Path, budget_s: float | None = None) -> pd.DataFrame:
    key = cache / f"XAUUSD_M1_{start:%Y%m%d}_{end:%Y%m%d}.parquet"
    if key.exists():
        return pd.read_parquet(key)
    m1 = download_m1("XAUUSD", start, end, cache / "bi5", budget_s=budget_s)
    key.parent.mkdir(parents=True, exist_ok=True)
    m1.to_parquet(key)
    return m1


def _fmt(x) -> str:
    return f"{x:.2f}" if isinstance(x, float) else str(x)


def backtest(args: argparse.Namespace) -> Path:
    cfg = load_config(Path(args.config))
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    budget = args.download_budget_min * 60 if args.download_budget_min else None
    try:
        m1 = load_m1(start, end, Path(args.cache), budget)
    except IncompleteDownload as exc:
        pct = 100 * exc.done / exc.total
        msg = (
            "# Backtest not run yet: data download incomplete\n\n"
            f"Downloaded {exc.done} of {exc.total} day files ({pct:.0f}%). Reason: {exc.reason}.\n\n"
            "The files downloaded so far are cached. Run the workflow again to continue.\n"
        )
        (out / "download_status.md").write_text(msg)
        print(msg)
        raise SystemExit(3) from None
    q = check_m1(m1)
    if not q.ok:
        raise SystemExit(f"Data quality check failed: {q}")
    mk = build_market(m1, cfg["strategy"], cfg["scanner"])
    spec = SymbolSpec()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")

    rows, details = [], []
    for scen, extra in SPREAD_SCENARIOS.items():
        for prof_name, prof in cfg["risk"]["profiles"].items():
            for var in VARIANTS:
                res = run_backtest(
                    mk, cfg["strategy"], cfg["scanner"], cfg["risk"], prof, var, spec,
                    start_equity=args.equity, extra_spread=extra,
                )
                df = trades_frame(res)
                df.to_csv(out / f"trades_{stamp}_{var}_{prof_name}_{scen}.csv", index=False)
                s = summarize(df, args.equity)
                rows.append({"spread": scen, "profile": prof_name, "variant": var, **s,
                             "halted": str(res.halted_at.date()) if res.halted_at else "-"})
                details.append((scen, prof_name, var, df, res.counters))

    lines = [
        "# Exploratory backtest - IN-SAMPLE, NOT VALIDATED",
        "",
        f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC. Period {start} to {end} "
        f"(the holdout after {end} was NOT used). Start equity ${args.equity:.0f}.",
        "",
        "**This is a single in-sample run on Dukascopy data. It is not the walk-forward "
        "validation in docs/STRATEGY.md and must not be read as expected future performance.**",
        "",
        "## Assumptions",
        "- Data: Dukascopy M1 bid/ask (not Vantage's feed). Real bid/ask spreads per minute.",
        "- `stress_+0.20`: $0.20 added to every ask price to approximate a wider retail spread.",
        "- Symbol spec (unverified for Vantage): 100 oz/lot, min lot 0.01, step 0.01, "
        "no commission, account leverage 1:500.",
        "- News blackout (F10) NOT applied: no historical calendar available.",
        "- Daily/weekly loss limits use realised P/L only.",
        "- Limit fills need the ask (long) / bid (short) to reach the price; stop first when "
        "a bar touches stop and target; stops slip 0.5 x spread.",
        "",
        "## Data quality",
        f"- M1 rows: {q.rows:,}; first {q.first}; last {q.last}",
        f"- Duplicates {q.duplicates}; bad OHLC {q.bad_ohlc}; negative spreads "
        f"{q.negative_spread}; unexpected weekday gaps > 30 min: {q.weekday_gaps_over_30m}",
        f"- Spread median ${q.median_spread:.3f}, 95th percentile ${q.p95_spread:.3f}",
        f"- Zones detected: {len(mk.zones)} "
        f"(H4 {sum(z.tf == 'H4' for z in mk.zones)}, H1 {sum(z.tf == 'H1' for z in mk.zones)})",
        "",
        "## Summary",
        "",
    ]
    table = pd.DataFrame(rows)
    cols = ["spread", "profile", "variant", "trades", "win_rate", "avg_r", "profit_factor",
            "return_pct", "max_dd_pct", "longest_losing_streak", "halted"]
    table = table.reindex(columns=cols)
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("|" + "---|" * len(cols))
    for _, r in table.iterrows():
        lines.append("| " + " | ".join(_fmt(r[c]) for c in cols) + " |")

    lines += ["", "## Detail per run", ""]
    for scen, prof_name, var, df, counters in details:
        lines += [f"### {var} / {prof_name} / {scen}", ""]
        if not df.empty:
            lines += ["By context:", "", breakdown(df, "context").round(3).to_markdown(), ""]
            lines += ["By side:", "", breakdown(df, "side").round(3).to_markdown(), ""]
            df = df.assign(year=pd.to_datetime(df.entry_time).dt.year)
            lines += ["By year:", "", breakdown(df, "year").round(3).to_markdown(), ""]
        lines += ["Pipeline counters:", "", "```"]
        lines += [f"{k}: {v}" for k, v in sorted(counters.items())]
        lines += ["```", ""]
    # Replay of the configured variant/profile with every bot action recorded.
    var, prof_name = cfg["strategy"]["variant"], cfg["risk"]["profile"]
    res = run_backtest(
        mk, cfg["strategy"], cfg["scanner"], cfg["risk"], cfg["risk"]["profiles"][prof_name],
        var, spec, start_equity=args.equity, extra_spread=0.0, record_events=True,
    )
    label = f"{var} · {prof_name} · spread Dukascopy · {start} → {end}"
    meta = {"variant": var, "profile": prof_name, "start": str(start), "end": str(end),
            "equity": args.equity, "in_sample": True,
            "generated": f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC"}
    write_replay(out / "replay.json", build_replay(mk, res, label, meta))

    report = out / f"backtest_{stamp}.md"
    report.write_text("\n".join(lines))
    print("\n".join(lines[: lines.index("## Detail per run")]))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(prog="adamantem")
    sub = parser.add_subparsers(dest="cmd", required=True)
    bt = sub.add_parser("backtest", help="exploratory in-sample backtest")
    bt.add_argument("--start", default="2021-11-01")
    bt.add_argument("--end", default="2025-11-01")
    bt.add_argument("--equity", type=float, default=500.0)
    bt.add_argument("--config", default=str(ROOT / "config" / "default.yaml"))
    bt.add_argument("--cache", default=str(ROOT / "data" / "raw" / "dukascopy"))
    bt.add_argument("--out", default=str(ROOT / "reports"))
    bt.add_argument("--download-budget-min", type=float, default=None)
    args = parser.parse_args()
    if args.cmd == "backtest":
        backtest(args)


if __name__ == "__main__":
    main()
