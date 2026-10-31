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
from adamantem.data import histdata
from adamantem.data.dukascopy import IncompleteDownload, download_m1
from adamantem.data.quality import check_m1
from adamantem.risk.sizing import SymbolSpec

ROOT = Path(__file__).resolve().parents[3]
SPREAD_SCENARIOS = {"base": 0.0, "stress_+0.20": 0.20}


def load_config(path: Path) -> dict:
    cfg = yaml.safe_load(path.read_text())
    assert cfg["mode"] != "live" and cfg["live_trading_enabled"] is False
    return cfg


def load_m1(
    start: date, end: date, cache: Path, budget_s: float | None = None,
    source: str = "histdata", assumed_spread: float = 0.25,
) -> pd.DataFrame:
    tag = f"{source}_s{assumed_spread:g}" if source == "histdata" else source
    key = cache / source / f"XAUUSD_M1_{tag}_{start:%Y%m%d}_{end:%Y%m%d}.parquet"
    if key.exists():
        return pd.read_parquet(key)
    if source == "histdata":
        m1 = histdata.download_m1("XAUUSD", start, end, cache / source / "zip", assumed_spread)
    else:
        m1 = download_m1("XAUUSD", start, end, cache / source / "bi5", budget_s=budget_s)
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
        m1 = load_m1(start, end, Path(args.cache), budget, args.source, args.assumed_spread)
    except histdata.HistDataError as exc:
        msg = f"# Backtest not run yet: HistData download failed\n\n{exc}\n"
        (out / "download_status.md").write_text(msg)
        print(msg)
        raise SystemExit(3) from None
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
        "**This is a single in-sample run on free historical data (see Assumptions). It is not the walk-forward "
        "validation in docs/STRATEGY.md and must not be read as expected future performance.**",
        "",
        "## Assumptions",
        *(
            [f"- Data: HistData.com M1 **bid** bars (not Vantage's feed), EST fixed UTC-5 "
             "converted to UTC. No ask data: ask = bid + an **assumed constant spread of "
             f"${args.assumed_spread:.2f}** (not measured; real spreads widen at news and "
             "rollover)."]
            if args.source == "histdata"
            else ["- Data: Dukascopy M1 bid/ask (not Vantage's feed). Real spreads per minute."]
        ),
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
        f"- Zones detected: {len(mk.zones)} (H4 {sum(z.tf == 'H4' for z in mk.zones)}, "
        f"H1 {sum(z.tf == 'H1' for z in mk.zones)}); order blocks "
        f"{sum(z.kind == 'OB' for z in mk.zones)}, FVG {sum(z.kind == 'FVG' for z in mk.zones)} "
        f"(FVGs dropped for a nearby OB or a stronger overlapping FVG: "
        f"{sum(z.kind == 'FVG' and z.dead_time < z.expire_time for z in mk.zones)})",
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
            lines += ["By zone type:", "", breakdown(df, "zone_kind").round(3).to_markdown(), ""]
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
    src = "HistData" if args.source == "histdata" else "Dukascopy"
    label = f"{var} · {prof_name} · dati {src} · {start} → {end}"
    meta = {"variant": var, "profile": prof_name, "start": str(start), "end": str(end),
            "equity": args.equity, "in_sample": True,
            "generated": f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC"}
    write_replay(out / "replay.json", build_replay(mk, res, label, meta))

    report = out / f"backtest_{stamp}.md"
    report.write_text("\n".join(lines))
    print("\n".join(lines[: lines.index("## Detail per run")]))
    return report


# Frozen before the holdout was looked at; see docs/HOLDOUT.md.
HOLDOUT_FROZEN = {
    "variant": "FVG-D",
    "strategy": {"allow_no_zone_setups": False, "zone_model": "ob_fvg"},
    "primary_profile": "standard",
    "criteria": {"min_trades": 30, "min_avg_r": 0.10, "min_profit_factor": 1.15},
}


def _load_or_exit(start: date, end: date, args: argparse.Namespace, out: Path) -> pd.DataFrame:
    try:
        return load_m1(start, end, Path(args.cache), None, "histdata", args.assumed_spread)
    except histdata.HistDataError as exc:
        msg = f"# Holdout not run: HistData download failed\n\n{exc}\n"
        (out / "download_status.md").write_text(msg)
        print(msg)
        raise SystemExit(3) from None


def holdout(args: argparse.Namespace) -> Path:
    """Run the single frozen configuration on the untouched holdout year (and, for
    comparison, on the in-sample period). Trading starts at the holdout start; earlier data
    only warms up indicators and zones."""
    cfg = load_config(Path(args.config))
    frozen = HOLDOUT_FROZEN
    params = {**cfg["strategy"], **frozen["strategy"], "variant": frozen["variant"]}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    spec = SymbolSpec()
    periods = {
        "in-sample": (date(2021, 11, 1), date(2025, 11, 1), date(2021, 11, 1)),
        "holdout": (date(2025, 8, 1), date.fromisoformat(args.end), date(2025, 11, 1)),
    }
    rows, details, replay_res = [], {}, None
    data_info = {}
    for period, (load_start, end, trade_from) in periods.items():
        m1 = _load_or_exit(load_start, end, args, out)
        q = check_m1(m1)
        if not q.ok:
            raise SystemExit(f"Data quality check failed: {q}")
        data_info[period] = (q, trade_from)
        mk = build_market(m1, params, cfg["scanner"])
        ts = pd.Timestamp(trade_from, tz="UTC")
        for scen, extra in SPREAD_SCENARIOS.items():
            for prof_name, prof in cfg["risk"]["profiles"].items():
                primary = scen == "base" and prof_name == frozen["primary_profile"]
                res = run_backtest(
                    mk, params, cfg["scanner"], cfg["risk"], prof, frozen["variant"], spec,
                    start_equity=args.equity, extra_spread=extra,
                    record_events=primary and period == "holdout", trade_start=ts,
                )
                df = trades_frame(res)
                s = summarize(df, args.equity)
                rows.append({"period": period, "spread": scen, "profile": prof_name, **s,
                             "halted": str(res.halted_at.date()) if res.halted_at else "-"})
                if primary:
                    details[period] = (df, res)
                    if period == "holdout":
                        replay_res = (mk, res)

    crit = frozen["criteria"]
    hd, hres = details["holdout"]
    hs = summarize(hd, args.equity)
    checks = [
        ("Trades ≥ %d" % crit["min_trades"], hs.get("trades", 0), hs.get("trades", 0) >= crit["min_trades"]),
        ("Average R ≥ +%.2f" % crit["min_avg_r"], hs.get("avg_r", float("nan")),
         hs.get("trades", 0) > 0 and hs["avg_r"] >= crit["min_avg_r"]),
        ("Profit factor ≥ %.2f" % crit["min_profit_factor"], hs.get("profit_factor", float("nan")),
         hs.get("trades", 0) > 0 and hs["profit_factor"] >= crit["min_profit_factor"]),
        ("No kill switch", hres.halted_at or "none", hres.halted_at is None),
    ]
    passed = all(ok for _, _, ok in checks)
    r = hd.r_multiple if len(hd) else pd.Series(dtype=float)
    t_stat = r.mean() / (r.std(ddof=1) / len(r) ** 0.5) if len(r) > 2 else float("nan")

    lines = [
        "# Holdout test - frozen configuration",
        "",
        f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC. Start equity ${args.equity:.0f}.",
        "",
        f"## Verdict: **{'PASSED' if passed else 'FAILED'}**",
        "",
        "Configuration and criteria were committed in docs/HOLDOUT.md before this run. "
        f"Variant {frozen['variant']}, zone setups only (order blocks + FVG H1/H4), single exit, "
        f"primary profile {frozen['primary_profile']}, assumed spread ${args.assumed_spread:.2f} "
        "(HistData bid + constant spread, not Vantage data).",
        "",
        "| Criterion | Holdout value | Pass |",
        "|---|---|---|",
        *[f"| {name} | {_fmt(v)} | {'yes' if ok else 'NO'} |" for name, v, ok in checks],
        "",
        f"t-statistic of mean R on the holdout: {t_stat:.2f} (informational).",
        "",
        "## Data",
        *[f"- {p}: {q.rows:,} M1 rows, {q.first} → {q.last}; trading from {tf}"
          for p, (q, tf) in data_info.items()],
        "",
        "## All runs of the frozen configuration",
        "",
    ]
    cols = ["period", "spread", "profile", "trades", "win_rate", "avg_r", "profit_factor",
            "return_pct", "max_dd_pct", "longest_losing_streak", "halted"]
    table = pd.DataFrame(rows).reindex(columns=cols)
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("|" + "---|" * len(cols))
    for _, row in table.iterrows():
        lines.append("| " + " | ".join(_fmt(row[c]) for c in cols) + " |")
    for period, (df, res) in details.items():
        lines += ["", f"## {period}: primary run detail", ""]
        if not df.empty:
            df = df.assign(month=pd.to_datetime(df.entry_time).dt.strftime("%Y-%m"))
            lines += ["By zone type:", "", breakdown(df, "zone_kind").round(3).to_markdown(), ""]
            lines += ["By side:", "", breakdown(df, "side").round(3).to_markdown(), ""]
            if period == "holdout":
                lines += ["By month:", "", breakdown(df, "month").round(3).to_markdown(), ""]
        lines += ["Pipeline counters:", "", "```"]
        lines += [f"{k}: {v}" for k, v in sorted(res.counters.items())]
        lines += ["```"]

    mk, res = replay_res
    label = f"HOLDOUT · {frozen['variant']} solo zone · {frozen['primary_profile']} · dati HistData"
    meta = {"variant": frozen["variant"], "profile": frozen["primary_profile"],
            "start": "2025-11-01", "end": args.end, "equity": args.equity, "in_sample": False,
            "generated": f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC"}
    write_replay(out / "replay.json", build_replay(mk, res, label, meta))
    report = out / "backtest_holdout.md"
    report.write_text("\n".join(lines))
    print("\n".join(lines[:30]))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(prog="adamantem")
    sub = parser.add_subparsers(dest="cmd", required=True)
    bt = sub.add_parser("backtest", help="exploratory in-sample backtest")
    bt.add_argument("--start", default="2021-11-01")
    bt.add_argument("--end", default="2025-11-01")
    bt.add_argument("--equity", type=float, default=500.0)
    bt.add_argument("--config", default=str(ROOT / "config" / "default.yaml"))
    bt.add_argument("--cache", default=str(ROOT / "data" / "raw"))
    bt.add_argument("--source", choices=["histdata", "dukascopy"], default="histdata")
    bt.add_argument("--assumed-spread", type=float, default=0.25,
                    help="HistData has no ask: constant spread in $ added to bid")
    bt.add_argument("--out", default=str(ROOT / "reports"))
    bt.add_argument("--download-budget-min", type=float, default=None)
    ho = sub.add_parser("holdout", help="frozen configuration on the untouched holdout year")
    ho.add_argument("--end", default="2026-11-01")
    ho.add_argument("--equity", type=float, default=500.0)
    ho.add_argument("--config", default=str(ROOT / "config" / "default.yaml"))
    ho.add_argument("--cache", default=str(ROOT / "data" / "raw"))
    ho.add_argument("--assumed-spread", type=float, default=0.25)
    ho.add_argument("--out", default=str(ROOT / "reports"))
    sc = sub.add_parser("scalp", help="scalping hypothesis S1: develop, select, validate 2016-20")
    sc.add_argument("--equity", type=float, default=500.0)
    sc.add_argument("--config", default=str(ROOT / "config" / "default.yaml"))
    sc.add_argument("--cache", default=str(ROOT / "data" / "raw"))
    sc.add_argument("--assumed-spread", type=float, default=0.25)
    sc.add_argument("--out", default=str(ROOT / "reports"))
    s2 = sub.add_parser("scalp2", help="scalping hypothesis S2 + third swing test (2016-2020)")
    s2.add_argument("--equity", type=float, default=500.0)
    s2.add_argument("--config", default=str(ROOT / "config" / "default.yaml"))
    s2.add_argument("--cache", default=str(ROOT / "data" / "raw"))
    s2.add_argument("--assumed-spread", type=float, default=0.25)
    s2.add_argument("--out", default=str(ROOT / "reports"))
    dr = sub.add_parser("doctor", help="read-only MT5 checks on the VPS (no orders)")
    dr.add_argument("--out", default=str(ROOT / "exports"))
    dr.add_argument("--no-export", action="store_true")
    sub.add_parser("demo", help="run the validated configuration on the MT5 DEMO account")
    args = parser.parse_args()
    if args.cmd in ("doctor", "demo"):
        import logging

        from adamantem.live.mt5_client import MT5Client, load_mt5
        from adamantem.live.runner import DemoBot, load_demo_config

        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
        cfg = load_demo_config(ROOT)
        client = MT5Client(load_mt5(), cfg["broker"].get("terminal_path"))
        if args.cmd == "doctor":
            from adamantem.live.doctor import run_doctor

            run_doctor(client, cfg, Path(args.out), export=not args.no_export)
        else:
            bot = DemoBot(client, cfg, ROOT / cfg["demo"]["state_dir"])
            bot.setup()
            bot.run_forever()
        return
    if args.cmd == "scalp2":
        from adamantem.app import scalp2

        scalp2.run(args, load_m1, load_config)
    if args.cmd == "scalp":
        from adamantem.app import scalp

        scalp.run(args, load_m1, load_config)
    if args.cmd == "backtest":
        backtest(args)
    elif args.cmd == "holdout":
        holdout(args)


if __name__ == "__main__":
    main()
