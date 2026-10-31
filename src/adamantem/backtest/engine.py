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
_BASE_VARIANTS = {
    "FVG-A": {"retest_price": "edge", "trend_filter": False},
    "FVG-B": {"retest_price": "edge", "trend_filter": True},
    "FVG-C": {"retest_price": "midpoint", "trend_filter": False},
    "FVG-D": {"retest_price": "midpoint", "trend_filter": True},
}
# Each base variant is tested without and with the break-even stop (docs/STRATEGY.md §5).
VARIANTS = {
    **{k: {**v, "breakeven": False} for k, v in _BASE_VARIANTS.items()},
    **{f"{k}+BE": {**v, "breakeven": True} for k, v in _BASE_VARIANTS.items()},
}


EXIT_TEXT = {
    "stop": "stop loss",
    "breakeven": "stop a break-even",
    "target": "target",
    "time": "limite di 6 ore",
    "session": "fine sessione",
}
REJECT_TEXT = {
    "session": ("scanner", "Rottura fuori dalla finestra di entrata: scartata."),
    "warmup": ("scanner", "Dati insufficienti per gli indicatori: scartata."),
    "volatility_regime": ("scanner", "Volatilità fuori dal range 30°–95° percentile: scartata."),
    "spread_vs_atr": ("scanner", "Spread oltre il 10% dell'ATR M5: scartata."),
    "trend_filter": ("scanner", "Contro il trend H1 (EMA200): scartata."),
    "busy": ("boss", "C'è già un ordine o una posizione: setup ignorato."),
    "kill_switch": ("risk", "NO: blocco automatico attivo."),
    "daily_pause": ("risk", "NO: pausa giornaliera attiva."),
    "weekly_loss_limit": ("risk", "NO: limite settimanale raggiunto."),
    "max_trades_per_day": ("risk", "NO: già 3 trade oggi."),
    "invalid_stop": ("risk", "NO: stop non valido."),
    "spread_vs_stop": ("risk", "NO: lo spread supera il 10% dello stop."),
    "no_room": ("risk", "NO: la zona opposta è a meno di 2R."),
    "min_lot_exceeds_risk": ("risk", "NO: anche 0,01 lotti rischierebbe troppo."),
    "leverage_cap": ("risk", "NO: supererebbe il tetto di leva."),
    "free_margin": ("risk", "NO: margine libero insufficiente."),
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
    zone_ids: tuple = ()


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
    arm_i: int = -1
    fvg_i: int = -1
    zone_ids: tuple = ()
    orig_stop: float = float("nan")
    be_active: bool = False


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
    # bar indices and setup geometry, for charts and replay
    arm_i: int = -1
    fvg_i: int = -1
    break_i: int = -1
    fill_i: int = -1
    exit_i: int = -1
    fvg_bottom: float = float("nan")
    fvg_top: float = float("nan")
    zone_ids: tuple = ()


@dataclass
class Result:
    trades: list[Trade]
    counters: dict[str, int] = field(default_factory=dict)
    halted_at: pd.Timestamp | None = None
    start_equity: float = 0.0
    # (bar index, bot, state, text) - filled only when record_events=True
    events: list[tuple[int, str, str, str]] = field(default_factory=list)


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
    record_events: bool = False,
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
    be_trigger = params["breakeven_trigger_r"]
    be_offset = params["breakeven_offset_r"]

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

    events: list[tuple[int, str, str, str]] = []

    def bump(key: str) -> None:
        c[key] = c.get(key, 0) + 1

    def ev(i: int, bot: str, state: str, text: str) -> None:
        if record_events:
            events.append((int(i), bot, state, text))

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
        before = (rs.paused_day, rs.paused_week, rs.halted)
        rs.on_close(pnl)
        trades.append(
            Trade(
                side=pos.side,
                context=pos.context,
                entry_time=mk.t_open[pos_fill_i],
                exit_time=mk.t_open[k] + pd.Timedelta("5min"),
                entry=pos.limit,
                exit=price,
                stop=pos.orig_stop,
                target=pos.target,
                volume=pos.volume,
                risk_money=pos.risk_money,
                pnl=pnl,
                r_multiple=pnl / pos.risk_money,
                exit_reason=reason,
                equity_after=rs.equity,
                arm_i=pos.arm_i,
                fvg_i=pos.fvg_i,
                break_i=pos.placed_i,
                fill_i=pos_fill_i,
                exit_i=k,
                fvg_bottom=pos.gap_bottom,
                fvg_top=pos.gap_top,
                zone_ids=pos.zone_ids,
            )
        )
        bump(f"exit_{reason}")
        r_mult = pnl / pos.risk_money
        ev(k, "exec", "ok" if pnl > 0 else "bad",
           f"Uscita ({EXIT_TEXT[reason]}) a {price:.2f}.")
        ev(k, "ledger", "ok", f"Trade registrato: {r_mult:+.2f}R, ${pnl:+.2f}. Conto ${rs.equity:.2f}.")
        ev(k, "boss", "work", "Nessuna posizione aperta: torno a cercare setup.")
        after = (rs.paused_day, rs.paused_week, rs.halted)
        if after[2] and not before[2]:
            ev(k, "risk", "bad", "BLOCCO AUTOMATICO: drawdown massimo raggiunto. Stop a tutto.")
        elif after[1] and not before[1]:
            ev(k, "risk", "bad", "Limite di perdita settimanale: pausa fino a lunedì.")
        elif after[0] and not before[0]:
            ev(k, "risk", "bad", "Pausa per oggi: limite giornaliero o 3 perdite di fila.")
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
        word = "sopra" if side == "long" else "sotto"
        ev(i, "sniper", "work",
           f"Chiusura M5 {word} l'FVG {f.bottom:.2f}–{f.top:.2f}: inversione. Chiedo l'ok sul rischio.")

        def reject(reason: str) -> None:
            bump(f"reject_{reason}")
            bot, text = REJECT_TEXT.get(reason, ("risk", reason))
            ev(i, bot, "bad", text)

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
            arm_i=a.arm_i, fvg_i=f.index, zone_ids=a.zone_ids, orig_stop=stop,
        )
        bump("orders_placed")
        pct = 100 * size.risk_money / rs.equity
        ev(i, "risk", "ok", f"Approvato: {size.volume:.2f} lotti, rischio ${size.risk_money:.2f} ({pct:.1f}%).")
        kind = "Buy" if side == "long" else "Sell"
        ev(i, "exec", "work",
           f"{kind} limit sul retest a {limit:.2f}, stop {stop:.2f}, target {target:.2f}.")

    for i in range(n):
        rs.roll(mk.t_open[i])

        # 1. Manage an open position.
        if pos is not None:
            px = stop_hit(i)
            if px is not None:
                close_position(i, px, "breakeven" if pos.be_active else "stop")
            elif (mk.bh[i] >= pos.target) if pos.side == "long" else (al[i] <= pos.target):
                close_position(i, pos.target, "target")
            elif i - pos_fill_i >= params["time_stop_bars"]:
                close_position(i, mk.bc[i] if pos.side == "long" else ac[i], "time")
            elif mk.close_minute[i] >= exit_min or mk.close_minute[i] < s_open:
                close_position(i, mk.bc[i] if pos.side == "long" else ac[i], "session")
            # Break-even: once price has run +trigger R, move the stop to entry (+ small offset).
            # It takes effect from the next bar, never inside the bar that triggered it.
            if pos is not None and var["breakeven"] and not pos.be_active:
                sign = 1.0 if pos.side == "long" else -1.0
                trigger = pos.limit + sign * be_trigger * pos.risk_r
                if (mk.bh[i] >= trigger) if pos.side == "long" else (al[i] <= trigger):
                    pos.stop = pos.limit + sign * be_offset * pos.risk_r
                    pos.be_active = True
                    bump("breakeven_moves")
                    ev(i, "risk", "ok", f"Trade a +{be_trigger:g}R: stop spostato a break-even "
                                        f"({pos.stop:.2f}).")

        # 2. Pending limit order: fill or cancel.
        if pending is not None and i > pending.placed_i:
            p = pending
            filled = (al[i] <= p.limit) if p.side == "long" else (mk.bh[i] >= p.limit)
            if filled and in_entry_window(i) and pos is None:
                pending, pos, pos_fill_i = None, p, i
                rs.trades_today += 1
                bump("fills")
                ev(i, "exec", "ok", f"Limit eseguito a {p.limit:.2f}. Stop e target sul server.")
                ev(i, "boss", "wait", "Posizione aperta: nuove entrate in pausa.")
                px = stop_hit(i)
                if px is not None:
                    close_position(i, px, "stop")
            elif not in_entry_window(i):
                pending = None
                bump("cancel_session")
                ev(i, "exec", "wait", "Ordine annullato: fine della finestra di entrata.")
            elif (p.side == "long" and mk.bc[i] < p.gap_bottom) or (
                p.side == "short" and mk.bc[i] > p.gap_top
            ):
                pending = None
                bump("cancel_inversion_failed")
                ev(i, "exec", "wait", "Ordine annullato: chiusura oltre il gap, inversione fallita.")
            elif (p.side == "long" and mk.bh[i] >= p.limit + p.risk_r * params["cancel_if_moved_r"]) or (
                p.side == "short" and mk.bl[i] <= p.limit - p.risk_r * params["cancel_if_moved_r"]
            ):
                pending = None
                bump("cancel_moved_away")
                ev(i, "exec", "wait", "Ordine annullato: il prezzo è partito senza retest.")
            elif i >= p.expire_i:
                pending = None
                bump("cancel_expired")
                ev(i, "exec", "wait", "Ordine annullato: nessun retest entro 1 ora.")

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
                    ev(i, "sniper", "idle", "Setup scaduto: nessuna rottura dell'FVG in 3 ore.")
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
            zone_ids = tuple(z.zid for z in hits)
            armed[side] = Armed(i, i + params["arm_window_bars"], context, ext, ref, zone_ids)
            bump(f"arm_{context}")
            if not hits and cur is not None and cur.context == "NONE":
                continue  # a deeper extreme only refreshes the no-zone setup; don't log it
            if hits:
                z = max(hits, key=lambda h: h.tf == "H4")
                kind = "domanda" if zside == "demand" else "offerta"
                ev(i, "hunter", "work",
                   f"Zona di {kind} {z.tf} toccata ({z.low:.2f}–{z.high:.2f}). Contesto {context}.")
            else:
                word = "minimo" if side == "long" else "massimo"
                ev(i, "hunter", "idle", f"Nessuna zona vicina: nuovo {word} a 36 candele.")
            target = "ribassista" if side == "long" else "rialzista"
            ev(i, "sniper", "work", f"Setup {side} armato ({context}). Seguo l'ultimo FVG {target}.")

        # 6. New FVG at this bar (known at its close).
        for side, fv in (("long", mk.bear[i]), ("short", mk.bull[i])):
            if fv is not None:
                last_fvg[side] = fv
                if armed[side] is not None:
                    armed[side].ref = fv
                    ev(i, "sniper", "work", f"Nuovo FVG di riferimento {fv.bottom:.2f}–{fv.top:.2f}.")

    return Result(trades=trades, counters=c, halted_at=halted_at, start_equity=start_equity,
                  events=events)
