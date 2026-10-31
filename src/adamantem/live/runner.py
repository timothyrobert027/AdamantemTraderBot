"""Demo trading loop: the validated configuration on a Vantage MT5 demo account.

Every closed M5 bar: read M1 history from MT5, run the same engine as the backtest in
decision mode (``simulate_fills=False``), manage pending orders and positions with the same
rules, apply the risk limits to the real demo account, and place at most one limit order.
Stops and targets are always attached server-side.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd
import yaml

from adamantem.backtest.engine import run_backtest
from adamantem.backtest.market import build_market
from adamantem.live.mt5_client import MT5Client
from adamantem.risk.sizing import size_position

log = logging.getLogger("adamantem.demo")
BAR = pd.Timedelta("5min")


def _hm(text: str) -> int:
    h, m = text.split(":")
    return int(h) * 60 + int(m)


def _merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in (b or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_demo_config(root: Path) -> dict:
    cfg = yaml.safe_load((root / "config" / "default.yaml").read_text())
    cfg = _merge(cfg, yaml.safe_load((root / "config" / "demo.yaml").read_text()))
    local = root / "config" / "local.yaml"
    if local.exists():
        cfg = _merge(cfg, yaml.safe_load(local.read_text()) or {})
    if cfg["mode"] != "demo" or cfg.get("live_trading_enabled"):
        raise SystemExit("demo config must have mode: demo and live_trading_enabled: false")
    return cfg


@dataclass
class BotState:
    kill_switch: bool = False
    kill_reason: str = ""
    peak_equity: float = 0.0
    orders: dict = field(default_factory=dict)  # ticket -> order notes (gap, R, placed time)
    positions: dict = field(default_factory=dict)  # position ticket -> opened (UTC iso)
    last_bar: str = ""

    @classmethod
    def load(cls, path: Path) -> BotState:
        if path.exists():
            return cls(**json.loads(path.read_text()))
        return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=1))
        tmp.replace(path)


class DemoBot:
    def __init__(self, client: MT5Client, cfg: dict, state_dir: Path):
        self.c = client
        self.cfg = cfg
        self.params = cfg["strategy"]
        self.scanner = cfg["scanner"]
        self.risk = cfg["risk"]
        self.profile = cfg["risk"]["profiles"][cfg["risk"]["profile"]]
        self.magic = int(cfg["broker"]["magic_number"])
        self.state_path = state_dir / "state.json"
        self.journal_path = state_dir / "journal.jsonl"
        self.state = BotState.load(self.state_path)
        self.spec = None

    # ---- setup -------------------------------------------------------------------------
    def setup(self) -> None:
        self.c.connect()  # refuses non-demo accounts
        acc = self.c.account()
        self.c.resolve_symbol(self.cfg["broker"]["symbol_pattern"], self.cfg["instrument"]["base_symbol"])
        self.c.detect_server_offset()
        self.spec, _ = self.c.symbol_spec()
        self.journal("start", login=self.c.masked_login(acc.login), symbol=self.c.symbol,
                     equity=acc.equity, server_offset_h=self.c.server_offset / pd.Timedelta("1h"))

    def journal(self, kind: str, **data) -> None:
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        row = {"utc": pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"), "event": kind, **data}
        with self.journal_path.open("a") as f:
            f.write(json.dumps(row, default=str) + "\n")
        log.info("%s %s", kind, data)

    # ---- one decision cycle ----------------------------------------------------------------
    def step(self, now: pd.Timestamp | None = None) -> None:
        self.c.ensure_demo()
        now = now or pd.Timestamp.now(tz="UTC")
        expected = now.floor("5min") - BAR  # last fully closed M5 bar
        m1 = self.c.rates_m1(int(self.cfg["demo"]["history_m1_bars"]))
        mk = build_market(m1, self.params, self.scanner)
        if len(mk.t_open) == 0 or mk.t_open[-1] != expected:
            self.journal("stale_data", last_bar=str(mk.t_open[-1]) if len(mk.t_open) else None,
                         expected=str(expected))
            return
        i = len(mk.t_open) - 1
        acc = self.c.account()
        self.state.peak_equity = max(self.state.peak_equity, acc.equity)
        self._manage_positions(mk, i, now)
        self._manage_orders(mk, i)
        blocked = self._risk_block(acc, now)
        if blocked:
            self._flatten(blocked)
        res = run_backtest(mk, self.params, self.scanner, self.risk, self.profile,
                           self.params["variant"], self.spec, start_equity=acc.equity,
                           simulate_fills=False)
        signals = [p for p in res.planned if p.placed_i == i]
        for p in signals:
            self.journal("signal", side=p.side, limit=p.limit, stop=p.stop, target=p.target,
                         context=p.context, bar=str(mk.t_open[i]))
            if blocked:
                self.journal("signal_skipped", reason=blocked)
            elif self.c.positions(self.magic) or self.c.orders(self.magic):
                self.journal("signal_skipped", reason="busy")
            else:
                self._place(p, mk, i, acc)
            break  # at most one order per bar
        self.state.last_bar = str(mk.t_open[i])
        self.state.save(self.state_path)

    # ---- order placement -------------------------------------------------------------------
    def _place(self, p, mk, i, acc) -> None:
        tick = self.c.tick()
        spread = tick.ask - tick.bid
        r = abs(p.limit - p.stop)
        if spread > self.params.get("max_spread_stop_fraction", 0.10) * r:
            return self.journal("signal_skipped", reason="live_spread_vs_stop", spread=spread)
        size = size_position(acc.equity, self.profile["risk_per_trade_pct"], p.limit, p.stop,
                             self.spec, 0.5 * spread, self.profile["max_effective_leverage"],
                             self.profile["min_free_margin_pct"],
                             self.risk.get("min_lot_risk_cap_pct"))
        if not size.ok:
            return self.journal("signal_skipped", reason=size.reason)
        expire = mk.t_open[i] + BAR + self.params["retest_window_bars"] * BAR
        res = self.c.place_limit(p.side, size.volume, p.limit, p.stop, p.target, expire,
                                 self.magic, f"ADM {p.context}")
        self.journal("order_sent" if res.ok else "order_failed", ticket=res.ticket,
                     retcode=res.retcode, comment=res.comment, volume=size.volume,
                     risk_money=round(size.risk_money, 2), spread=round(spread, 3))
        if res.ok:
            self.state.orders[str(res.ticket)] = {
                "side": p.side, "limit": p.limit, "stop": p.stop, "target": p.target,
                "r": r, "gap_bottom": p.gap_bottom, "gap_top": p.gap_top,
                "placed_bar": str(mk.t_open[i]),
            }

    # ---- management: same rules as the backtest --------------------------------------------
    def _in_entry_window(self, mk, i) -> bool:
        s_open, s_close = (_hm(x) for x in self.scanner["session_utc"])
        r_open, r_close = (_hm(x) for x in self.scanner["rollover_block_utc"])
        m, wd = mk.close_minute[i], mk.close_weekday[i]
        if not (s_open <= m < s_close) or (r_open <= m < r_close):
            return False
        return not (wd == 4 and m >= _hm(self.scanner["friday_cutoff_utc"])) and wd < 5

    def _manage_orders(self, mk, i) -> None:
        live = {str(o.ticket): o for o in self.c.orders(self.magic)}
        for ticket in list(self.state.orders):
            if ticket not in live:  # filled, expired or removed
                self.state.orders.pop(ticket)
        cancel_r = self.params["cancel_if_moved_r"]
        for ticket, o in list(self.state.orders.items()):
            reason = None
            if not self._in_entry_window(mk, i):
                reason = "session"
            elif o["side"] == "long" and mk.bc[i] < o["gap_bottom"]:
                reason = "inversion_failed"
            elif o["side"] == "short" and mk.bc[i] > o["gap_top"]:
                reason = "inversion_failed"
            elif o["side"] == "long" and mk.bh[i] >= o["limit"] + o["r"] * cancel_r:
                reason = "moved_away"
            elif o["side"] == "short" and mk.bl[i] <= o["limit"] - o["r"] * cancel_r:
                reason = "moved_away"
            if reason:
                res = self.c.cancel_order(int(ticket), self.magic)
                self.journal("order_cancelled", ticket=ticket, reason=reason, ok=res.ok)
                if res.ok:
                    self.state.orders.pop(ticket)

    def _manage_positions(self, mk, i, now) -> None:
        exit_min = _hm(self.params["session_exit_utc"])
        s_open = _hm(self.scanner["session_utc"][0])
        open_now = self.c.positions(self.magic)
        known = {str(p.ticket) for p in open_now}
        for t in list(self.state.positions):
            if t not in known:
                self.state.positions.pop(t)
        for pos in open_now:
            opened = self.state.positions.setdefault(str(pos.ticket), now.isoformat())
            bars_open = (now - pd.Timestamp(opened)) / BAR
            reason = None
            if bars_open >= self.params["time_stop_bars"]:
                reason = "time"
            elif mk.close_minute[i] >= exit_min or mk.close_minute[i] < s_open:
                reason = "session"
            if reason:
                res = self.c.close_position(pos, self.magic, f"ADM exit {reason}")
                self.journal("position_closed", ticket=pos.ticket, reason=reason, ok=res.ok,
                             retcode=res.retcode)

    # ---- risk limits on the real demo account ---------------------------------------------
    def _risk_block(self, acc, now) -> str | None:
        p = self.profile
        if self.state.kill_switch:
            return "kill_switch"
        if self.state.peak_equity - acc.equity >= self.state.peak_equity * p["max_drawdown_kill_pct"] / 100:
            self.state.kill_switch, self.state.kill_reason = True, f"drawdown at {now.isoformat()}"
            self.journal("kill_switch", equity=acc.equity, peak=self.state.peak_equity)
            return "kill_switch"
        day = now.normalize()
        week = day - pd.Timedelta(days=day.day_of_week)
        deals_week = self.c.closed_deals(week, self.magic)
        pnl = lambda ds: sum(d.profit + d.commission + d.swap for d in ds)  # noqa: E731
        deals_day = [d for d in deals_week if pd.Timestamp(d.time, unit="s", tz="UTC")
                     - self.c.server_offset >= day]
        floating = sum(pos.profit for pos in self.c.positions(self.magic))
        start_day = acc.equity - pnl(deals_day) - floating
        start_week = acc.equity - pnl(deals_week) - floating
        if -(pnl(deals_day) + floating) >= start_day * p["daily_loss_limit_pct"] / 100:
            return "daily_loss_limit"
        if -(pnl(deals_week) + floating) >= start_week * p["weekly_loss_limit_pct"] / 100:
            return "weekly_loss_limit"
        streak = 0
        for d in sorted(deals_day, key=lambda d: d.time):
            streak = streak + 1 if d.profit + d.commission + d.swap < 0 else 0
        if streak >= self.risk["max_consecutive_losses"]:
            return "consecutive_losses"
        if len(deals_day) + len(self.c.positions(self.magic)) >= self.risk["max_trades_per_day"]:
            return "max_trades_per_day"
        return None

    def _flatten(self, reason: str) -> None:
        """Daily/weekly/kill-switch breaches close everything; trade-count limits only block."""
        if reason not in ("kill_switch", "daily_loss_limit", "weekly_loss_limit"):
            return
        for o in self.c.orders(self.magic):
            self.c.cancel_order(o.ticket, self.magic)
        for pos in self.c.positions(self.magic):
            self.c.close_position(pos, self.magic, f"ADM {reason}")
        self.journal("flatten", reason=reason)

    # ---- loop ------------------------------------------------------------------------------
    def run_forever(self) -> None:  # pragma: no cover - real-time loop on the VPS
        delay = float(self.cfg["demo"]["poll_delay_seconds"])
        while True:
            now = pd.Timestamp.now(tz="UTC")
            nxt = now.floor("5min") + BAR + pd.Timedelta(seconds=delay)
            time.sleep(max((nxt - now).total_seconds(), 1))
            try:
                self.step()
                self._heartbeat("ok")
            except Exception as exc:  # keep running; server-side SL/TP protect positions
                self.journal("error", error=repr(exc))
                self._heartbeat(f"error: {exc!r}")
                try:
                    self.c.shutdown()
                    self.c.connect()
                except Exception as exc2:
                    self.journal("reconnect_failed", error=repr(exc2))

    def _heartbeat(self, status: str) -> None:
        hb = self.state_path.parent / "heartbeat.txt"
        hb.write_text(f"{pd.Timestamp.now(tz='UTC').isoformat(timespec='seconds')} {status}\n")
