"""Scalping hypothesis S1: develop on 2021-11 -> 2025-11, select by a pre-registered rule,
validate on untouched 2016-2020. Everything here is frozen in docs/SCALPING.md.

The validated swing configuration (docs/HOLDOUT.md) is run on the same periods for
comparison; for it, 2016-2020 is also unseen data.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from adamantem.backtest.engine import run_backtest
from adamantem.backtest.market import build_market
from adamantem.backtest.metrics import breakdown, summarize, trades_frame
from adamantem.backtest.replay import build_replay, write_replay
from adamantem.data import histdata
from adamantem.data.quality import check_m1
from adamantem.risk.sizing import SymbolSpec

ENTRY_VARIANT = "FVG-D"  # midpoint retest + H1 trend filter, single exit (as validated)
COMMON = {
    "zone_model": "ob_fvg",
    "allow_no_zone_setups": False,
    "tp_default_r": 1.5,
    "tp_max_r": 1.5,
    "min_room_r": 1.5,
    "max_spread_stop_fraction": 0.20,
}
M1_BARS = {  # the M5 settings expressed for 1-minute bars, shorter for scalping
    "arm_window_bars": 60,
    "fvg_max_age_before_arm_bars": 30,
    "retest_window_bars": 15,
    "time_stop_bars": 120,
}
SCALP_VARIANTS = {
    "S-A": {**COMMON, **M1_BARS, "entry_timeframe": "M1", "zone_timeframes": ["H4", "H1", "M15"]},
    "S-B": {**COMMON, **M1_BARS, "entry_timeframe": "M1", "zone_timeframes": ["H4", "H1"]},
    "S-C": {**COMMON, "entry_timeframe": "M5", "zone_timeframes": ["H4", "H1", "M15"]},
}
SCANNER_M1 = {"max_spread_atr_fraction": 0.30}
RISK_SCALP = {"max_trades_per_day": 6}
SWING = {"zone_model": "ob_fvg", "allow_no_zone_setups": False}  # docs/HOLDOUT.md

SELECTION = {"min_trades": 200}  # dev, standard profile, base spread; then highest avg R
VALIDATION = {"min_trades": 250, "min_avg_r": 0.10, "min_profit_factor": 1.15,
              "min_stress_avg_r": 0.0}
PERIODS = {
    "dev": (date(2021, 11, 1), date(2025, 11, 1), date(2021, 11, 1)),
    "validation": (date(2015, 10, 1), date(2021, 1, 1), date(2016, 1, 1)),
}
SPREADS = {"base": 0.0, "stress_+0.20": 0.20}


def _fmt(x) -> str:
    return f"{x:.2f}" if isinstance(x, float) else str(x)


def _monthly(ret_pct: float, months: int) -> float:
    return ((1 + ret_pct / 100) ** (1 / months) - 1) * 100 if ret_pct > -100 else -100.0


def run(args: argparse.Namespace, load_m1, load_config) -> Path:
    cfg = load_config(Path(args.config))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    spec = SymbolSpec()
    configs = {name: (v, ENTRY_VARIANT) for name, v in SCALP_VARIANTS.items()}
    configs["SWING (validated)"] = (SWING, ENTRY_VARIANT)
    rows, details, data_info = [], {}, {}

    def run_period(period: str, names: list[str]) -> None:
        load_start, end, trade_from = PERIODS[period]
        try:
            m1 = load_m1(load_start, end, Path(args.cache), None, "histdata", args.assumed_spread)
        except histdata.HistDataError as exc:
            raise SystemExit(f"HistData download failed: {exc}") from None
        q = check_m1(m1)
        if not q.ok:
            raise SystemExit(f"Data quality check failed: {q}")
        data_info[period] = (q, trade_from)
        months = (end.year - trade_from.year) * 12 + end.month - trade_from.month
        for name in names:
            overrides, variant = configs[name]
            params = {**cfg["strategy"], **overrides}
            scanner = {**cfg["scanner"], **(SCANNER_M1 if params.get("entry_timeframe") == "M1" else {})}
            risk = {**cfg["risk"], **(RISK_SCALP if name.startswith("S-") else {})}
            mk = build_market(m1, params, scanner)
            for scen, extra in SPREADS.items():
                for prof_name, prof in cfg["risk"]["profiles"].items():
                    primary = scen == "base" and prof_name == "standard"
                    res = run_backtest(mk, params, scanner, risk, prof, variant, spec,
                                       start_equity=args.equity, extra_spread=extra,
                                       record_events=primary and period == "validation",
                                       trade_start=pd.Timestamp(trade_from, tz="UTC"))
                    df = trades_frame(res)
                    s = summarize(df, args.equity)
                    s["trades_per_month"] = s.get("trades", 0) / months
                    s["monthly_growth_pct"] = (_monthly(s["return_pct"], months)
                                               if s.get("trades") else 0.0)
                    rows.append({"period": period, "config": name, "spread": scen,
                                 "profile": prof_name, **s,
                                 "halted": str(res.halted_at.date()) if res.halted_at else "-"})
                    details[(period, name, scen, prof_name)] = (df, res)
            del mk

    run_period("dev", list(configs))
    table = pd.DataFrame(rows)

    def pick(period, name, scen="base", prof="standard"):
        sel = table[(table.period == period) & (table.config == name) & (table.spread == scen)
                    & (table.profile == prof)]
        return sel.iloc[0] if len(sel) else None

    candidates = [n for n in SCALP_VARIANTS
                  if pick("dev", n).get("trades", 0) >= SELECTION["min_trades"]]
    chosen = max(candidates, key=lambda n: pick("dev", n)["avg_r"]) if candidates else None

    verdict, checks = "NO CANDIDATE (no scalping variant reached the trade count in development)", []
    if chosen:
        run_period("validation", [chosen, "SWING (validated)"])
        table = pd.DataFrame(rows)
        v, vs = pick("validation", chosen), pick("validation", chosen, "stress_+0.20")
        _, vres = details[("validation", chosen, "base", "standard")]
        checks = [
            (f"Trades ≥ {VALIDATION['min_trades']}", v["trades"], v["trades"] >= VALIDATION["min_trades"]),
            (f"Average R ≥ +{VALIDATION['min_avg_r']:.2f}", v.get("avg_r"),
             v["trades"] > 0 and v["avg_r"] >= VALIDATION["min_avg_r"]),
            (f"Profit factor ≥ {VALIDATION['min_profit_factor']:.2f}", v.get("profit_factor"),
             v["trades"] > 0 and v["profit_factor"] >= VALIDATION["min_profit_factor"]),
            ("No kill switch", vres.halted_at or "none", vres.halted_at is None),
            (f"Stress-spread average R ≥ {VALIDATION['min_stress_avg_r']:.2f}", vs.get("avg_r"),
             vs["trades"] > 0 and vs["avg_r"] >= VALIDATION["min_stress_avg_r"]),
        ]
        verdict = "PASSED" if all(ok for *_, ok in checks) else "FAILED"

    cols = ["period", "config", "spread", "profile", "trades", "trades_per_month", "win_rate",
            "avg_r", "profit_factor", "return_pct", "monthly_growth_pct", "max_dd_pct",
            "longest_losing_streak", "halted"]
    lines = [
        "# Scalping hypothesis S1",
        "",
        f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC. Start equity ${args.equity:.0f}. "
        f"HistData M1 bid + assumed spread ${args.assumed_spread:.2f} (not Vantage data). "
        "Rules, selection and criteria: docs/SCALPING.md (committed before this run).",
        "",
        f"## Selected for validation: **{chosen or 'none'}**",
        f"## Verdict on untouched 2016-2020: **{verdict}**",
        "",
    ]
    if checks:
        lines += ["| Criterion | Value | Pass |", "|---|---|---|",
                  *[f"| {n} | {_fmt(x)} | {'yes' if ok else 'NO'} |" for n, x, ok in checks], ""]
    lines += ["## Data", *[f"- {p}: {q.rows:,} M1 rows, {q.first} → {q.last}; trading from {tf}"
                           for p, (q, tf) in data_info.items()], "", "## All runs", "",
              "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in table.reindex(columns=cols).iterrows():
        lines.append("| " + " | ".join(_fmt(r[c]) for c in cols) + " |")
    for (period, name, scen, prof), (df, _res) in details.items():
        if scen != "base" or prof != "standard" or df.empty:
            continue
        lines += ["", f"### {period} · {name} · standard · base", ""]
        lines += ["By zone type:", "", breakdown(df, "zone_kind").round(3).to_markdown(), ""]
        df = df.assign(year=pd.to_datetime(df.entry_time).dt.year)
        lines += ["By year:", "", breakdown(df, "year").round(3).to_markdown(), ""]
        lines += ["By exit:", "", breakdown(df, "exit_reason").round(3).to_markdown(), ""]

    key = ("validation", chosen, "base", "standard") if chosen else None
    if key and key in details:
        df, res = details[key]
        load_start, end, _ = PERIODS["validation"]
        m1 = load_m1(load_start, end, Path(args.cache), None, "histdata", args.assumed_spread)
        params = {**cfg["strategy"], **configs[chosen][0]}
        scanner = {**cfg["scanner"], **(SCANNER_M1 if params.get("entry_timeframe") == "M1" else {})}
        mk = build_market(m1, params, scanner)
        label = f"SCALPING {chosen} · validazione 2016-2020 · standard · dati HistData"
        meta = {"variant": chosen, "profile": "standard", "start": "2016-01-01",
                "end": "2021-01-01", "equity": args.equity, "in_sample": False,
                "generated": f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC"}
        write_replay(out / "replay.json", build_replay(mk, res, label, meta))
    report = out / "backtest_scalp.md"
    report.write_text("\n".join(lines))
    print("\n".join(lines[:25]))
    return report
