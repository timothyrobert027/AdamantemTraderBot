"""Scalping hypothesis S2 (docs/SCALPING_S2.md): frequency-first setup families.

One run: development funnel on 2021-11 -> 2025-11, automatic selection, validation on
untouched 2016-2020, plus a third independent test of the validated swing configuration.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from adamantem.app.scalp import _fmt, _monthly
from adamantem.backtest.engine import run_backtest
from adamantem.backtest.market import build_market
from adamantem.backtest.metrics import breakdown, summarize, trades_frame
from adamantem.backtest.replay import build_replay, write_replay
from adamantem.data import histdata
from adamantem.data.quality import check_m1
from adamantem.risk.sizing import SymbolSpec

ENTRY_VARIANT = "FVG-D"  # midpoint retest + H1 trend filter, single exit
COMMON = {
    "zone_model": "ob_fvg",
    "entry_timeframe": "M5",
    "allow_no_zone_setups": False,
    "tp_default_r": 1.5,
    "tp_max_r": 1.5,
    "min_room_r": 1.5,
    "max_spread_stop_fraction": 0.20,
}
TREND = {"arm_mode": "trend", "zone_timeframes": []}
ORB = {"orb_enabled": True, "orb_range_minutes": 30, "orb_breakout_window_minutes": 120}
S2_VARIANTS = {
    "S2-A": {**COMMON, **TREND},
    "S2-B": {**COMMON, "zone_timeframes": ["H4", "H1", "M15"], "zone_max_touches": 3,
             "zone_max_age_bars": {"M15": 192, "H1": 240, "H4": 120}},
    "S2-C": {**COMMON, "zone_timeframes": [], **ORB},
    "S2-AC": {**COMMON, **TREND, **ORB},
}
SCANNER_S2 = {"max_spread_atr_fraction": 0.20}
RISK_S2 = {"max_trades_per_day": 6}
SWING = {"zone_model": "ob_fvg", "allow_no_zone_setups": False}  # docs/HOLDOUT.md

SELECTION = {"min_trades_per_day": 1.5, "min_avg_r": 0.05}
VALIDATION = {"min_trades_per_day": 1.5, "min_avg_r": 0.05, "min_profit_factor": 1.10,
              "min_stress_avg_r": 0.0}
SWING_VALIDATION = {"min_trades": 30, "min_avg_r": 0.10, "min_profit_factor": 1.15}
PERIODS = {
    "dev": (date(2021, 11, 1), date(2025, 11, 1), date(2021, 11, 1)),
    "validation": (date(2015, 10, 1), date(2021, 1, 1), date(2016, 1, 1)),
}
SPREADS = {"base": 0.0, "stress_+0.20": 0.20}
FUNNEL_KEYS = ("arm_", "break_", "orders_placed", "fills")


def _setup(name: str, cfg: dict):
    if name == "SWING (validated)":
        return {**cfg["strategy"], **SWING}, cfg["scanner"], cfg["risk"]
    return ({**cfg["strategy"], **S2_VARIANTS[name]}, {**cfg["scanner"], **SCANNER_S2},
            {**cfg["risk"], **RISK_S2})


def run(args: argparse.Namespace, load_m1, load_config) -> Path:
    cfg = load_config(Path(args.config))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    spec = SymbolSpec()
    rows, funnel, details, data_info, markets = [], [], {}, {}, {}

    def run_period(period: str, names: list[str]) -> None:
        load_start, end, trade_from = PERIODS[period]
        try:
            m1 = load_m1(load_start, end, Path(args.cache), None, "histdata", args.assumed_spread)
        except histdata.HistDataError as exc:
            raise SystemExit(f"HistData download failed: {exc}") from None
        q = check_m1(m1)
        if not q.ok:
            raise SystemExit(f"Data quality check failed: {q}")
        idx = m1.index[m1.index >= pd.Timestamp(trade_from, tz="UTC")]
        days = max(len(pd.unique(idx[idx.day_of_week < 5].date)), 1)
        months = (end.year - trade_from.year) * 12 + end.month - trade_from.month
        data_info[period] = (q, trade_from, days)
        for name in names:
            params, scanner, risk = _setup(name, cfg)
            mk = build_market(m1, params, scanner)
            for scen, extra in SPREADS.items():
                for prof_name, prof in cfg["risk"]["profiles"].items():
                    primary = scen == "base" and prof_name == "standard"
                    res = run_backtest(mk, params, scanner, risk, prof, ENTRY_VARIANT, spec,
                                       start_equity=args.equity, extra_spread=extra,
                                       record_events=primary and period == "validation",
                                       trade_start=pd.Timestamp(trade_from, tz="UTC"))
                    df = trades_frame(res)
                    s = summarize(df, args.equity)
                    s["trades_per_day"] = s.get("trades", 0) / days
                    s["monthly_growth_pct"] = (_monthly(s["return_pct"], months)
                                               if s.get("trades") else 0.0)
                    rows.append({"period": period, "config": name, "spread": scen,
                                 "profile": prof_name, **s,
                                 "halted": str(res.halted_at.date()) if res.halted_at else "-"})
                    details[(period, name, scen, prof_name)] = (df, res)
                    if primary:
                        c = res.counters
                        f = {"period": period, "config": name}
                        for key in ("arm", "break"):
                            f[f"{key}s/day"] = sum(v for k, v in c.items()
                                                   if k.startswith(key + "_")) / days
                        f["orders/day"] = c.get("orders_placed", 0) / days
                        f["fills/day"] = c.get("fills", 0) / days
                        rej = sorted(((v, k[7:]) for k, v in c.items() if k.startswith("reject_")),
                                     reverse=True)[:4]
                        f["top rejections (per day)"] = ", ".join(f"{k} {v / days:.2f}"
                                                                   for v, k in rej)
                        funnel.append(f)
                        if period == "validation":
                            markets[name] = mk
            if period != "validation":
                del mk

    run_period("dev", [*S2_VARIANTS, "SWING (validated)"])
    table = pd.DataFrame(rows)

    def pick(period, name, scen="base", prof="standard"):
        sel = table[(table.period == period) & (table.config == name) & (table.spread == scen)
                    & (table.profile == prof)]
        return sel.iloc[0] if len(sel) else None

    candidates = [n for n in S2_VARIANTS
                  if pick("dev", n)["trades_per_day"] >= SELECTION["min_trades_per_day"]
                  and pick("dev", n).get("avg_r", -9) >= SELECTION["min_avg_r"]]
    chosen = max(candidates, key=lambda n: pick("dev", n)["avg_r"]) if candidates else None

    run_period("validation", ([chosen] if chosen else []) + ["SWING (validated)"])
    table = pd.DataFrame(rows)

    def verdict_checks(name, crit, per_day: bool):
        v, vs = pick("validation", name), pick("validation", name, "stress_+0.20")
        _, vres = details[("validation", name, "base", "standard")]
        n = v["trades"]
        checks = []
        if per_day:
            checks.append((f"Trades/day ≥ {crit['min_trades_per_day']}", v["trades_per_day"],
                           v["trades_per_day"] >= crit["min_trades_per_day"]))
        else:
            checks.append((f"Trades ≥ {crit['min_trades']}", n, n >= crit["min_trades"]))
        checks += [
            (f"Average R ≥ +{crit['min_avg_r']:.2f}", v.get("avg_r"), n > 0 and v["avg_r"] >= crit["min_avg_r"]),
            (f"Profit factor ≥ {crit['min_profit_factor']:.2f}", v.get("profit_factor"),
             n > 0 and v["profit_factor"] >= crit["min_profit_factor"]),
            ("No kill switch", vres.halted_at or "none", vres.halted_at is None),
        ]
        if "min_stress_avg_r" in crit:
            checks.append((f"Stress-spread average R ≥ {crit['min_stress_avg_r']:.2f}", vs.get("avg_r"),
                           vs["trades"] > 0 and vs["avg_r"] >= crit["min_stress_avg_r"]))
        return ("PASSED" if all(ok for *_, ok in checks) else "FAILED"), checks

    s2_verdict, s2_checks = ("NO CANDIDATE", [])
    if chosen:
        s2_verdict, s2_checks = verdict_checks(chosen, VALIDATION, True)
    sw_verdict, sw_checks = verdict_checks("SWING (validated)", SWING_VALIDATION, False)

    def check_table(checks):
        return ["| Criterion | Value | Pass |", "|---|---|---|",
                *[f"| {n} | {_fmt(x)} | {'yes' if ok else 'NO'} |" for n, x, ok in checks], ""]

    lines = [
        "# Scalping hypothesis S2 + third test of the swing configuration",
        "",
        f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC. Start equity ${args.equity:.0f}. "
        f"HistData M1 bid + assumed spread ${args.assumed_spread:.2f} (not Vantage data). "
        "Everything pre-registered in docs/SCALPING_S2.md.",
        "",
        f"## S2 selected: **{chosen or 'none'}** — verdict on 2016-2020: **{s2_verdict}**",
        *(check_table(s2_checks) if s2_checks else [""]),
        f"## Validated swing configuration on 2016-2020: **{sw_verdict}**",
        *check_table(sw_checks),
        "## Data",
        *[f"- {p}: {q.rows:,} M1 rows, {q.first} → {q.last}; trading from {tf}; {d} trading days"
          for p, (q, tf, d) in data_info.items()],
        "",
        "## Funnel (standard profile, base spread)",
        "",
    ]
    fdf = pd.DataFrame(funnel)
    lines += [fdf.round(2).to_markdown(index=False), "", "## All runs", ""]
    cols = ["period", "config", "spread", "profile", "trades", "trades_per_day", "win_rate",
            "avg_r", "profit_factor", "return_pct", "monthly_growth_pct", "max_dd_pct",
            "longest_losing_streak", "halted"]
    lines += ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in table.reindex(columns=cols).iterrows():
        lines.append("| " + " | ".join(_fmt(r[c]) for c in cols) + " |")
    for (period, name, scen, prof), (df, _res) in details.items():
        if scen != "base" or prof != "standard" or df.empty:
            continue
        lines += ["", f"### {period} · {name} · standard · base", ""]
        lines += ["By setup context:", "", breakdown(df, "context").round(3).to_markdown(), ""]
        df = df.assign(year=pd.to_datetime(df.entry_time).dt.year)
        lines += ["By year:", "", breakdown(df, "year").round(3).to_markdown(), ""]
        lines += ["By exit:", "", breakdown(df, "exit_reason").round(3).to_markdown(), ""]

    replay_name = chosen or "SWING (validated)"
    _, res = details[("validation", replay_name, "base", "standard")]
    label = f"{replay_name} · validazione 2016-2020 · standard · dati HistData"
    meta = {"variant": replay_name, "profile": "standard", "start": "2016-01-01",
            "end": "2021-01-01", "equity": args.equity, "in_sample": False,
            "generated": f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC"}
    write_replay(out / "replay.json", build_replay(markets[replay_name], res, label, meta))
    report = out / "backtest_scalp2.md"
    report.write_text("\n".join(lines))
    print("\n".join(lines[:30]))
    return report
