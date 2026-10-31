"""Bar-by-bar backtest of the H4/H1 zone + M5 FVG-inversion retest strategy.

Conservative execution rules (docs/STRATEGY.md §4-5):
- a buy limit fills only when the ASK low reaches it; a sell limit when the BID high does;
- long positions exit on BID, short positions on ASK;
- if a bar touches both stop and target, the stop is assumed first;
- on the fill bar only the stop is checked, never the target;
- stops gapped through fill at the bar open, plus slippage of 0.5 x spread.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from adamantem.backtest.market import Market
from adamantem.risk.sizing import SymbolSpec, size_position

PRIORITY = {"H4+H1": 3, "H4": 2, "H1": 1, "NONE": 0}
VARIANTS = {
    "FVG-A": {"retest_price": "edge", "trend_filter": False},
    "FVG-B": {"retest_price": "edge", "trend_filter": True},
    "FVG-C": {"retest_price": "midpoint", "trend_filter": False},
    "FVG-D": {"retest_price": "midpoint", "trend_filter": True},
}


def _hm(text: str) -> int:
    h, m = text.split(":")
    return int(h) * 60 + int(m)


@dataclass
class Armed:
    arm_i: int
    expire_i: int
    context: str
    extreme: float  # lowest low (long) / highest high (short) since arming
    ref: object = None  # FVG


@dataclass
class Pending:
    side: str
    placed_i: int
    expire_i: int
    limit: float
    stop: float
    target: float
    risk_r: float  # price distance limit -> stop
    gap_bottom: float
    gap_top: float
    volume: float
    risk_money: float
    context: str


@dataclass
class Trade:
    side: str
    context: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry: float
    exit: float
    stop: float
    target: float
    volume: float
    risk_money: float
    pnl: float
    r_multiple: float
    exit_reason: str
    equity_after: float


@dataclass
class Result:
    trades: list[Trade]
    counters: dict[str, int] = field(default_factory=dict)
    halted_at: pd.Timestamp | None = None
    start_equity: float = 0.0


class RiskState:
    def __init__(self, equity: float, profile: dict, risk: dict):
        self.equity = equity
        self.peak = equity
        self.p = profile
        self.r = risk
        self.day = None
        self.week = None
        self.day_start = equity
        self.week_start = equity
        self.trades_today = 0
        self.losses_in_row = 0
        self.paused_day = False
        self.paused_week = False
        self.halted = False

    def roll(self, t: pd.Timestamp) -> None:
        day = t.date()
        week = t.isocalendar()[:2]
        if day != self.day:
            self.day, self.day_start = day, self.equity
            self.trades_today = 0
            self.losses_in_row = 0
            self.paused_day = False
        if week != self.week:
            self.week, self.week_start = week, self.equity
            self.paused_week = False

    def can_trade(self) -> str | None:
        if self.halted:
            return "kill_switch"
        if self.paused_week:
            return "weekly_loss_limit"
        if self.paused_day:
            return "daily_pause"
        if self.trades_today >= self.r["max_trades_per_day"]:
            return "max_trades_per_day"
        return None

    def on_close(self, pnl: float) -> None:
        self.equity += pnl
        self.peak = max(self.peak, self.equity)
        self.losses_in_row = self.losses_in_row + 1 if pnl < 0 else 0
        if self.losses_in_row >= self.r["max_consecutive_losses"]:
            self.paused_day = True
        if self.day_start - self.equity >= self.day_start * self.p["daily_loss_limit_pct"] / 100:
            self.paused_day = True
        if self.week_start - self.equity >= self.week_start * self.p["weekly_loss_limit_pct"] / 100:
            self.paused_week = True
        if self.peak - self.equity >= self.peak * self.p["max_drawdown_kill_pct"] / 100:
            self.halted = True


def run_backtest(
    mk: Market,
    params: dict,
    scanner: dict,
    risk: dict,
    profile: dict,
    variant: str,
    spec: SymbolSpec,
    start_equity: float = 500.0,
    extra_spread: float = 0.0,
) -> Result:
    var = VARIANTS[variant]
    n = len(mk.t_open)
    ah, al, ac, ao = mk.ah + extra_spread, mk.al + extra_spread, mk.ac + extra_spread, mk.ao + extra_spread
    spread = ac - mk.bc
    s_open, s_close = (_hm(x) for x in scanner["session_utc"])
    r_open, r_close = (_hm(x) for x in scanner["rollover_block_utc"])
    fri_cut = _hm(scanner["friday_cutoff_utc"])
    exit_min = _hm(params["session_exit_utc"])
    vlo, vhi = scanner["vol_percentile_range"]

    zones = {z.zid: z for z in mk.zones}
    fresh: dict[int, object] = {}
    valid: dict[int, object] = {}
    armed: dict[str, Armed | None] = {"long": None, "short": None}
    last_fvg = {"long": None, "short": None}  # latest unbroken opposing FVG per trade side
    pending: Pending | None = None
    pos: Pending | None = None
    pos_fill_i = -1
    rs = RiskState(start_equity, profile, risk)
    trades: list[Trade] = []
    c: dict[str, int] = {}
    halted_at = None

    def bump(key: str) -> None:
        c[key] = c.get(key, 0) + 1

    def in_entry_window(i: int) -> bool:
        m, wd = mk.close_minute[i], mk.close_weekday[i]
        if not (s_open <= m < s_close) or (r_open <= m < r_close):
            return False
        return not (wd == 4 and m >= fri_cut) and wd < 5

    def close_position(k: int, price: float, reason: str) -> None:
        nonlocal pos, halted_at
        sign = 1.0 if pos.side == "long" else -1.0
        pnl = sign * (price - pos.limit) * pos.volume * spec.contract_size
        pnl -= spec.commission_per_lot * pos.volume
        rs.on_close(pnl)
        trades.append(
            Trade(
                side=pos.side,
                context=pos.context,
                entry_time=mk.t_open[pos_fill_i],
                exit_time=mk.t_open[k] + pd.Timedelta("5min"),
                entry=pos.limit,
                exit=price,
                stop=pos.stop,
                target=pos.target,
                volume=pos.volume,
                risk_money=pos.risk_money,
                pnl=pnl,
                r_multiple=pnl / pos.risk_money,
                exit_reason=reason,
                equity_after=rs.equity,
            )
        )
        bump(f"exit_{reason}")
        if rs.halted and halted_at is None:
            halted_at = mk.t_open[k]
        pos = None

    def stop_hit(k: int) -> float | None:
        slip = 0.5 * spread[k]
        if pos.side == "long" and mk.bl[k] <= pos.stop:
            return min(mk.bo[k], pos.stop) - slip
        if pos.side == "short" and ah[k] >= pos.stop:
            return max(ao[k], pos.stop) + slip
        return None

    def _plan(side: str, i: int, a: Armed, f) -> None:
        """A close through the reference FVG: try to place the retest limit order."""
        nonlocal pending
        bump(f"break_{a.context}")

        def reject(reason: str) -> None:
            bump(f"reject_{reason}")

        if not in_entry_window(i):
            return reject("session")
        why = rs.can_trade()
        if why:
            return reject(why)
        if pos is not None or pending is not None:
            return reject("busy")
        atr5 = mk.atr5[i]
        if not (np.isfinite(atr5) and np.isfinite(mk.vol_pct[i])):
            return reject("warmup")
        if not (vlo <= mk.vol_pct[i] <= vhi):
            return reject("volatility_regime")
        if spread[i] > scanner["max_spread_atr_fraction"] * atr5:
            return reject("spread_vs_atr")
        if var["trend_filter"] and not (mk.trend_up[i] if side == "long" else mk.trend_down[i]):
            return reject("trend_filter")
        edge = var["retest_price"] == "edge"
        buf = params["sl_buffer_atr"] * atr5
        if side == "long":
            limit = f.top if edge else f.mid
            stop = min(a.extreme, mk.bl[i]) - buf
        else:
            limit = f.bottom if edge else f.mid
            stop = max(a.extreme, mk.bh[i]) + buf
        r = abs(limit - stop)
        if r <= 0:
            return reject("invalid_stop")
        if spread[i] > 0.10 * r:
            return reject("spread_vs_stop")
        sign = 1.0 if side == "long" else -1.0
        opp = "supply" if side == "long" else "demand"
        dists = [
            sign * (z.proximal - limit)
            for z in fresh.values()
            if z.side == opp and sign * (z.proximal - limit) > 0
        ]
        if dists:
            d = min(dists)
            if d < params["min_room_r"] * r:
                return reject("no_room")
            target = limit + sign * min(d, params["tp_max_r"] * r)
        else:
            target = limit + sign * params["tp_default_r"] * r
        size = size_position(
            rs.equity, profile["risk_per_trade_pct"], limit, stop, spec,
            est_slippage=0.5 * spread[i],
            max_effective_leverage=profile["max_effective_leverage"],
            min_free_margin_pct=profile["min_free_margin_pct"],
        )
        if not size.ok:
            return reject(size.reason)
        pending = Pending(
            side=side, placed_i=i, expire_i=i + params["retest_window_bars"], limit=limit,
            stop=stop, target=target, risk_r=r, gap_bottom=f.bottom, gap_top=f.top,
            volume=size.volume, risk_money=size.risk_money, context=a.context,
        )
        bump("orders_placed")

    for i in range(n):
        rs.roll(mk.t_open[i])

        # 1. Manage an open position.
        if pos is not None:
            px = stop_hit(i)
            if px is not None:
                close_position(i, px, "stop")
            elif (mk.bh[i] >= pos.target) if pos.side == "long" else (al[i] <= pos.target):
                close_position(i, pos.target, "target")
            elif i - pos_fill_i >= params["time_stop_bars"]:
                close_position(i, mk.bc[i] if pos.side == "long" else ac[i], "time")
            elif mk.close_minute[i] >= exit_min or mk.close_minute[i] < s_open:
                close_position(i, mk.bc[i] if pos.side == "long" else ac[i], "session")

        # 2. Pending limit order: fill or cancel.
        if pending is not None and i > pending.placed_i:
            p = pending
            filled = (al[i] <= p.limit) if p.side == "long" else (mk.bh[i] >= p.limit)
            if filled and in_entry_window(i) and pos is None:
                pending, pos, pos_fill_i = None, p, i
                rs.trades_today += 1
                bump("fills")
                px = stop_hit(i)
                if px is not None:
                    close_position(i, px, "stop")
            elif not in_entry_window(i):
                pending = None
                bump("cancel_session")
            elif (p.side == "long" and mk.bc[i] < p.gap_bottom) or (
                p.side == "short" and mk.bc[i] > p.gap_top
            ):
                pending = None
                bump("cancel_inversion_failed")
            elif (p.side == "long" and mk.bh[i] >= p.limit + p.risk_r * params["cancel_if_moved_r"]) or (
                p.side == "short" and mk.bl[i] <= p.limit - p.risk_r * params["cancel_if_moved_r"]
            ):
                pending = None
                bump("cancel_moved_away")
            elif i >= p.expire_i:
                pending = None
                bump("cancel_expired")

        # 3. Zone bookkeeping.
        for zid in mk.zone_valid_end.get(i, ()):
            valid.pop(zid, None)
            fresh.pop(zid, None)
        for zid in mk.zone_start.get(i, ()):
            valid[zid] = zones[zid]
            fresh[zid] = zones[zid]
        touched = mk.zone_touch.get(i, ())
        for zid in mk.zone_fresh_end.get(i, ()):
            fresh.pop(zid, None)

        # 4. Track FVGs: a new opposing FVG becomes the latest; a close through it breaks it.
        for side in ("long", "short"):
            f = last_fvg[side]
            if f is not None and f.index < i:
                broke = mk.bc[i] > f.top if side == "long" else mk.bc[i] < f.bottom
                if broke:
                    last_fvg[side] = None
                    a = armed[side]
                    if a is not None and a.ref is f:
                        _plan(side, i, a, f)
                        armed[side] = None

        # 5. Arming.
        for side, zside in (("long", "demand"), ("short", "supply")):
            a = armed[side]
            if a is not None:
                a.extreme = min(a.extreme, mk.bl[i]) if side == "long" else max(a.extreme, mk.bh[i])
                if i > a.expire_i:
                    armed[side] = None
                    bump("arm_expired")
            hits = [zones[z] for z in touched if zones[z].side == zside]
            context = None
            if hits:
                tfs = {z.tf for z in hits}
                if "H1" in tfs and "H4" not in tfs:
                    h1s = [z for z in hits if z.tf == "H1"]
                    if any(
                        v.side == zside and v.tf == "H4" and v.low <= h.high and h.low <= v.high
                        for v in valid.values()
                        for h in h1s
                    ):
                        tfs.add("H4")
                context = "H4+H1" if tfs == {"H1", "H4"} else tfs.pop()
            elif params["allow_no_zone_setups"] and np.isfinite(mk.atr_h1[i]):
                extreme = (
                    mk.bl[i] < mk.prev_low_min[i] if side == "long" else mk.bh[i] > mk.prev_high_max[i]
                )
                if extreme:
                    px, dist = mk.bc[i], mk.atr_h1[i]
                    near = any(z.low - dist <= px <= z.high + dist for z in fresh.values())
                    if not near:
                        context = "NONE"
            if context is None:
                continue
            cur = armed[side]
            if cur is not None and PRIORITY[context] < PRIORITY[cur.context]:
                continue
            ext = mk.bl[i] if side == "long" else mk.bh[i]
            if cur is not None and PRIORITY[context] == PRIORITY[cur.context]:
                ext = min(ext, cur.extreme) if side == "long" else max(ext, cur.extreme)
            ref = last_fvg[side]
            if ref is not None and ref.index < i - params["fvg_max_age_before_arm_bars"]:
                ref = None
            armed[side] = Armed(i, i + params["arm_window_bars"], context, ext, ref)
            bump(f"arm_{context}")

        # 6. New FVG at this bar (known at its close).
        for side, fv in (("long", mk.bear[i]), ("short", mk.bull[i])):
            if fv is not None:
                last_fvg[side] = fv
                if armed[side] is not None:
                    armed[side].ref = fv

    return Result(trades=trades, counters=c, halted_at=halted_at, start_equity=start_equity)
