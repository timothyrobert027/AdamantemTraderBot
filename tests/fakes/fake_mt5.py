"""A small in-memory stand-in for the ``MetaTrader5`` package, for tests only."""

from __future__ import annotations

from types import SimpleNamespace as NS

import numpy as np
import pandas as pd


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO, ACCOUNT_TRADE_MODE_CONTEST, ACCOUNT_TRADE_MODE_REAL = 0, 1, 2
    TIMEFRAME_M1 = 1
    TRADE_ACTION_DEAL, TRADE_ACTION_PENDING, TRADE_ACTION_REMOVE = 1, 5, 8
    ORDER_TYPE_BUY, ORDER_TYPE_SELL, ORDER_TYPE_BUY_LIMIT, ORDER_TYPE_SELL_LIMIT = 0, 1, 2, 3
    ORDER_FILLING_FOK, ORDER_FILLING_IOC, ORDER_FILLING_RETURN = 0, 1, 2
    SYMBOL_FILLING_FOK, SYMBOL_FILLING_IOC = 1, 2
    ORDER_TIME_SPECIFIED = 2
    POSITION_TYPE_BUY, POSITION_TYPE_SELL = 0, 1
    DEAL_ENTRY_OUT = 1
    TRADE_RETCODE_PLACED, TRADE_RETCODE_DONE = 10008, 10009

    def __init__(self, m1: pd.DataFrame, trade_mode: int = 0, server_offset_h: int = 2,
                 equity: float = 500.0):
        self.m1 = m1  # bid/ask frame indexed by UTC, like adamantem's data
        self.offset = pd.Timedelta(hours=server_offset_h)
        self.trade_mode = trade_mode
        self.equity = equity
        self.sent: list[dict] = []
        self.pending: dict[int, NS] = {}
        self.open_positions: list[NS] = []
        self.deals: list[NS] = []
        self._ticket = 1000

    # connection
    def initialize(self, path=None):
        return True

    def shutdown(self):
        return None

    def last_error(self):
        return (0, "ok")

    def account_info(self):
        return NS(login=12345678, trade_mode=self.trade_mode, equity=self.equity,
                  balance=self.equity, leverage=500, currency="USD", server="Vantage-Demo")

    # symbols
    def symbols_get(self, group="*"):
        return [NS(name="XAUUSD"), NS(name="XAUUSD247")]

    def symbol_select(self, name, enable):
        return True

    def symbol_info(self, name):
        return NS(name=name, trade_contract_size=100.0, trade_tick_size=0.01, trade_tick_value=1.0,
                  volume_min=0.01, volume_step=0.01, volume_max=100.0, digits=2, point=0.01,
                  filling_mode=self.SYMBOL_FILLING_IOC, trade_stops_level=0,
                  trade_freeze_level=0, swap_long=-50.0, swap_short=10.0)

    def symbol_info_tick(self, name):
        last = self.m1.iloc[-1]
        t = int((self.m1.index[-1] + self.offset).timestamp()) + 59
        return NS(time=t, bid=float(last.bid_close), ask=float(last.ask_close))

    def copy_rates_from_pos(self, symbol, timeframe, start, count):
        df = self.m1.tail(count)
        epoch = pd.Timestamp("1970-01-01", tz="UTC")
        server = ((df.index + self.offset - epoch) // pd.Timedelta("1s")).to_numpy().astype(np.int64)
        spread_pts = np.round((df.ask_close - df.bid_close).to_numpy() / 0.01).astype(np.int32)
        arr = np.zeros(len(df), dtype=[("time", "i8"), ("open", "f8"), ("high", "f8"),
                                       ("low", "f8"), ("close", "f8"), ("tick_volume", "i8"),
                                       ("spread", "i4"), ("real_volume", "i8")])
        arr["time"], arr["open"], arr["high"] = server, df.bid_open, df.bid_high
        arr["low"], arr["close"], arr["spread"] = df.bid_low, df.bid_close, spread_pts
        arr["tick_volume"] = 1
        return arr

    # state
    def positions_get(self, symbol=None):
        return list(self.open_positions)

    def orders_get(self, symbol=None):
        return list(self.pending.values())

    def history_deals_get(self, start, end):
        return list(self.deals)

    # trading
    def order_check(self, request):
        return NS(retcode=0, comment="ok")

    def order_send(self, request):
        self.sent.append(request)
        self._ticket += 1
        if request["action"] == self.TRADE_ACTION_PENDING:
            self.pending[self._ticket] = NS(ticket=self._ticket, magic=request["magic"], **{
                k: request[k] for k in ("price", "sl", "tp", "volume", "type")})
            return NS(retcode=self.TRADE_RETCODE_PLACED, order=self._ticket, comment="placed")
        if request["action"] == self.TRADE_ACTION_REMOVE:
            self.pending.pop(request["order"], None)
        if request["action"] == self.TRADE_ACTION_DEAL and "position" in request:
            self.open_positions = [p for p in self.open_positions
                                   if p.ticket != request["position"]]
        return NS(retcode=self.TRADE_RETCODE_DONE, order=self._ticket, comment="done")
