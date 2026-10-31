"""Export one backtest run as compact JSON for the ADAMANTEM Floor replay and trade charts."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from adamantem.backtest.engine import Result
from adamantem.backtest.market import Market

BARS_BEFORE = 24
BARS_AFTER = 12
MAX_BARS = 220
MAX_EVENTS_PER_DAY = 250


def _r(x: float) -> float | None:
    return None if x is None or not np.isfinite(x) else round(float(x), 2)


def build_replay(mk: Market, res: Result, label: str, meta: dict) -> dict:
    epoch = pd.Timestamp("1970-01-01", tz="UTC")
    t_min = ((mk.t_open - epoch) // pd.Timedelta("1min")).to_numpy().astype(np.int64)  # UTC
    zones = {z.zid: z for z in mk.zones}

    trades = []
    for n, t in enumerate(res.trades):
        start = max(min(t.arm_i, t.fvg_i) - BARS_BEFORE, 0)
        end = min(t.exit_i + BARS_AFTER, len(mk.t_open) - 1)
        start = max(start, end - MAX_BARS + 1)
        sl = slice(start, end + 1)
        bars = np.column_stack(
            [t_min[sl], mk.bo[sl].round(2), mk.bh[sl].round(2), mk.bl[sl].round(2), mk.bc[sl].round(2)]
        ).tolist()
        trades.append(
            {
                "id": n,
                "day": str(mk.t_open[t.fill_i].date()),
                "side": t.side,
                "context": t.context,
                "zone_kind": t.zone_kind,
                "entry": _r(t.entry),
                "exit": _r(t.exit),
                "stop": _r(t.stop),
                "target": _r(t.target),
                "volume": t.volume,
                "pnl": _r(t.pnl),
                "r": _r(t.r_multiple),
                "reason": t.exit_reason,
                "equity": _r(t.equity_after),
                "fvg": [_r(t.fvg_bottom), _r(t.fvg_top)],
                "tps": [_r(x) for x in t.tps if x is not None],
                "legs": [[name, lots, _r(price), int(t_min[i]), reason]
                         for name, lots, price, i, reason in t.legs],
                "marks": {
                    k: int(t_min[i])
                    for k, i in (("arm", t.arm_i), ("fvg", t.fvg_i), ("break", t.break_i),
                                 ("fill", t.fill_i), ("exit", t.exit_i))
                    if i >= 0
                },
                "zones": [
                    {"tf": zones[z].tf, "side": zones[z].side, "kind": zones[z].kind,
                     "low": _r(zones[z].low), "high": _r(zones[z].high)}
                    for z in t.zone_ids
                ],
                "bars": [[int(b[0])] + b[1:] for b in bars],
            }
        )

    # Keep events only for days with an order or a trade, so the file stays small.
    day_of = mk.t_open.date
    active_days = {str(day_of[i]) for i, bot, _, text in res.events if bot == "exec"}
    days: dict[str, list] = {}
    for i, bot, state, text in res.events:
        d = str(day_of[i])
        if d in active_days and len(days.setdefault(d, [])) < MAX_EVENTS_PER_DAY:
            days[d].append([int(t_min[i]) + 5, bot, state, text])  # stamp at bar close

    return {"label": label, "meta": meta, "days": days, "trades": trades}


def write_replay(path: Path, replay: dict) -> None:
    path.write_text(json.dumps(replay, separators=(",", ":"), ensure_ascii=False))
