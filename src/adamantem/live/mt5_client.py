"""Thin wrapper around the official ``MetaTrader5`` package (Windows only).

The module object is injected, so tests use a fake. The terminal must already be logged in:
``connect`` never receives a password. Every trading call is refused unless the account
reports ``ACCOUNT_TRADE_MODE_DEMO``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import pandas as pd

from adamantem.risk.sizing import SymbolSpec


class MT5Error(RuntimeError):
    pass


class NotDemoAccount(MT5Error):
    pass


@dataclass(frozen=True)
class OrderResult:
    ok: bool
    retcode: int
    ticket: int
    comment: str


class MT5Client:
    def __init__(self, mt5, terminal_path: str | None = None, clock=time.time):
        self.mt5 = mt5
        self.clock = clock  # UTC epoch seconds; injectable for tests
        self.terminal_path = terminal_path
        self.symbol: str | None = None
        self.server_offset = pd.Timedelta(0)  # server time - UTC

    # ---- connection and safety -------------------------------------------------------
    def connect(self) -> None:
        ok = self.mt5.initialize(path=self.terminal_path) if self.terminal_path else self.mt5.initialize()
        if not ok:
            raise MT5Error(f"cannot attach to the MT5 terminal: {self.mt5.last_error()}")
        self.ensure_demo()

    def shutdown(self) -> None:
        self.mt5.shutdown()

    def account(self):
        info = self.mt5.account_info()
        if info is None:
            raise MT5Error(f"no account info: {self.mt5.last_error()}")
        return info

    def ensure_demo(self) -> None:
        if self.account().trade_mode != self.mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise NotDemoAccount("the terminal is logged in to a NON-demo account: refusing to run")

    @staticmethod
    def masked_login(login: int) -> str:
        s = str(login)
        return "****" + s[-4:]

    # ---- symbol and time ----------------------------------------------------------------
    def resolve_symbol(self, pattern: str, base: str = "XAUUSD") -> str:
        symbols = self.mt5.symbols_get(group=pattern) or []
        names = sorted(s.name for s in symbols if s.name.upper().startswith(base))
        if not names:
            raise MT5Error(f"no symbol matching {pattern} / {base}")
        exact = [n for n in names if n.upper() == base]
        self.symbol = exact[0] if exact else names[0]
        self.mt5.symbol_select(self.symbol, True)
        return self.symbol

    def symbol_spec(self) -> tuple[SymbolSpec, object]:
        info = self.mt5.symbol_info(self.symbol)
        if info is None:
            raise MT5Error(f"no symbol info for {self.symbol}")
        spec = SymbolSpec(
            name=info.name,
            contract_size=float(info.trade_contract_size),
            tick_size=float(info.trade_tick_size),
            tick_value=float(info.trade_tick_value),
            volume_min=float(info.volume_min),
            volume_step=float(info.volume_step),
            volume_max=float(info.volume_max),
            commission_per_lot=0.0,
            account_leverage=float(self.account().leverage or 1),
        )
        return spec, info

    def tick(self):
        t = self.mt5.symbol_info_tick(self.symbol)
        if t is None:
            raise MT5Error(f"no tick for {self.symbol}")
        return t

    def detect_server_offset(self, now_utc: float | None = None) -> pd.Timedelta:
        """Server time minus UTC, rounded to 30 minutes, from the last tick time."""
        now = self.clock() if now_utc is None else now_utc
        diff = self.tick().time - now
        self.server_offset = pd.Timedelta(minutes=30 * round(diff / 1800))
        return self.server_offset

    def rates_m1(self, count: int) -> pd.DataFrame:
        """Last ``count`` M1 bars as a bid/ask frame indexed by UTC open time.

        MT5 bars are bid prices; the ask side uses each bar's recorded spread (in points).
        The newest bar is still forming and is dropped.
        """
        raw = self.mt5.copy_rates_from_pos(self.symbol, self.mt5.TIMEFRAME_M1, 0, count)
        if raw is None or len(raw) == 0:
            raise MT5Error(f"no M1 history: {self.mt5.last_error()}")
        df = pd.DataFrame(raw)
        point = float(self.mt5.symbol_info(self.symbol).point)
        idx = pd.to_datetime(df["time"], unit="s", utc=True) - self.server_offset
        spread = df["spread"].to_numpy(dtype=float) * point
        out = pd.DataFrame(
            {
                "bid_open": df["open"].to_numpy(float),
                "bid_high": df["high"].to_numpy(float),
                "bid_low": df["low"].to_numpy(float),
                "bid_close": df["close"].to_numpy(float),
            },
            index=pd.DatetimeIndex(idx, name="time"),
        )
        for col in ("open", "high", "low", "close"):
            out[f"ask_{col}"] = out[f"bid_{col}"] + spread
        out["volume"] = df["tick_volume"].to_numpy(float)
        return out.iloc[:-1]

    # ---- account state --------------------------------------------------------------------
    def positions(self, magic: int) -> list:
        return [p for p in (self.mt5.positions_get(symbol=self.symbol) or []) if p.magic == magic]

    def orders(self, magic: int) -> list:
        return [o for o in (self.mt5.orders_get(symbol=self.symbol) or []) if o.magic == magic]

    def closed_deals(self, since_utc: pd.Timestamp, magic: int) -> list:
        start = (since_utc + self.server_offset).to_pydatetime()
        end = (pd.Timestamp.now(tz="UTC") + self.server_offset + pd.Timedelta(days=1)).to_pydatetime()
        deals = self.mt5.history_deals_get(start, end) or []
        return [d for d in deals if d.magic == magic and d.entry == self.mt5.DEAL_ENTRY_OUT]

    # ---- trading (demo only) ---------------------------------------------------------------
    def _send(self, request: dict) -> OrderResult:
        self.ensure_demo()
        check = self.mt5.order_check(request)
        if check is None or check.retcode not in (0, self.mt5.TRADE_RETCODE_DONE):
            code = getattr(check, "retcode", -1)
            return OrderResult(False, code, 0, f"order_check refused: {getattr(check, 'comment', '')}")
        res = self.mt5.order_send(request)
        if res is None:
            return OrderResult(False, -1, 0, str(self.mt5.last_error()))
        ok = res.retcode in (self.mt5.TRADE_RETCODE_DONE, self.mt5.TRADE_RETCODE_PLACED)
        return OrderResult(ok, res.retcode, int(getattr(res, "order", 0)), res.comment)

    def _filling(self, info) -> int:
        mode = int(info.filling_mode)
        if mode & self.mt5.SYMBOL_FILLING_FOK:
            return self.mt5.ORDER_FILLING_FOK
        if mode & self.mt5.SYMBOL_FILLING_IOC:
            return self.mt5.ORDER_FILLING_IOC
        return self.mt5.ORDER_FILLING_RETURN

    def place_limit(self, side: str, volume: float, price: float, sl: float, tp: float,
                    expire_utc: pd.Timestamp, magic: int, comment: str) -> OrderResult:
        info = self.mt5.symbol_info(self.symbol)
        digits = int(info.digits)
        request = {
            "action": self.mt5.TRADE_ACTION_PENDING,
            "symbol": self.symbol,
            "volume": float(volume),
            "type": self.mt5.ORDER_TYPE_BUY_LIMIT if side == "long" else self.mt5.ORDER_TYPE_SELL_LIMIT,
            "price": round(price, digits),
            "sl": round(sl, digits),
            "tp": round(tp, digits),
            "type_time": self.mt5.ORDER_TIME_SPECIFIED,
            "expiration": int((expire_utc + self.server_offset).timestamp()),
            "type_filling": self.mt5.ORDER_FILLING_RETURN,
            "magic": int(magic),
            "comment": comment[:31],
        }
        return self._send(request)

    def cancel_order(self, ticket: int, magic: int) -> OrderResult:
        return self._send({"action": self.mt5.TRADE_ACTION_REMOVE, "order": int(ticket),
                           "magic": int(magic)})

    def close_position(self, position, magic: int, comment: str) -> OrderResult:
        info = self.mt5.symbol_info(self.symbol)
        tick = self.tick()
        is_buy = position.type == self.mt5.POSITION_TYPE_BUY
        request = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "position": int(position.ticket),
            "volume": float(position.volume),
            "type": self.mt5.ORDER_TYPE_SELL if is_buy else self.mt5.ORDER_TYPE_BUY,
            "price": tick.bid if is_buy else tick.ask,
            "deviation": 30,
            "type_filling": self._filling(info),
            "magic": int(magic),
            "comment": comment[:31],
        }
        return self._send(request)


def load_mt5():
    """Import the official package; only available on Windows with a terminal installed."""
    try:
        import MetaTrader5 as mt5  # noqa: N813
    except ImportError as exc:  # pragma: no cover - Windows only
        raise MT5Error("the MetaTrader5 package is not installed (Windows only)") from exc
    return mt5


def spread_stats(m1: pd.DataFrame) -> dict:
    s = (m1["ask_close"] - m1["bid_close"]).to_numpy()
    if len(s) == 0:
        return {}
    hours = m1.index.hour
    by_hour = pd.Series(s, index=hours).groupby(level=0).median().round(3).to_dict()
    return {"median": float(np.median(s)), "p90": float(np.percentile(s, 90)),
            "max": float(s.max()), "median_by_utc_hour": by_hour}
