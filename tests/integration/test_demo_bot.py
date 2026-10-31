"""Demo runtime against a fake MT5: safety, time handling, orders and risk limits."""

from types import SimpleNamespace as NS

import pandas as pd
import pytest

from adamantem.backtest import engine as engine_mod
from adamantem.live import runner as runner_mod
from adamantem.live.doctor import run_doctor
from adamantem.live.mt5_client import MT5Client, NotDemoAccount
from adamantem.live.runner import DemoBot, load_demo_config
from tests.conftest import ROOT, synthetic_m1
from tests.fakes.fake_mt5 import FakeMT5


@pytest.fixture
def m1():
    # 30 days ending on a Wednesday 10:05 UTC (inside the entry window)
    df = synthetic_m1(days=30, start="2024-02-01")
    return df[df.index < pd.Timestamp("2024-02-28 10:05", tz="UTC")]


@pytest.fixture
def cfg():
    c = load_demo_config(ROOT)
    c["demo"]["history_m1_bars"] = 50_000
    return c


NOW = pd.Timestamp("2024-02-28 10:05:10", tz="UTC")


def _client(fake):
    return MT5Client(fake, clock=lambda: NOW.timestamp())


def _bot(m1, cfg, tmp_path, **kw):
    fake = FakeMT5(m1, **kw)
    bot = DemoBot(_client(fake), cfg, tmp_path)
    bot.setup()
    return bot, fake


def test_demo_config_is_the_validated_one(cfg):
    assert cfg["mode"] == "demo" and cfg["live_trading_enabled"] is False
    assert cfg["strategy"]["variant"] == "FVG-D" and cfg["strategy"]["zone_model"] == "ob_fvg"
    assert cfg["strategy"]["allow_no_zone_setups"] is False
    assert cfg["risk"]["profile"] == "standard"


def test_refuses_real_account(m1, cfg, tmp_path):
    with pytest.raises(NotDemoAccount):
        _bot(m1, cfg, tmp_path, trade_mode=FakeMT5.ACCOUNT_TRADE_MODE_REAL)


def test_server_time_converted_to_utc(m1, cfg, tmp_path):
    bot, _ = _bot(m1, cfg, tmp_path, server_offset_h=2)
    assert bot.c.server_offset == pd.Timedelta(hours=2)
    bars = bot.c.rates_m1(1000)
    assert bars.index[-1] == m1.index[-2]  # forming bar dropped, times back in UTC
    assert abs((bars.ask_close - bars.bid_close).median() - 0.15) < 0.06


def _fake_signal(monkeypatch, side="long"):
    real = engine_mod.run_backtest

    def fake_run(mk, *a, **kw):
        res = real(mk, *a, **kw)
        i = len(mk.t_open) - 1
        px = mk.bc[i]
        sign = 1 if side == "long" else -1
        res.planned.append(engine_mod.Pending(
            side=side, placed_i=i, expire_i=i + 12, limit=px - sign * 0.5, stop=px - sign * 3.5,
            target=px + sign * 4.0, risk_r=3.0, gap_bottom=px - 1.0, gap_top=px - 0.2,
            volume=0.01, risk_money=3.0, context="H1"))
        return res

    monkeypatch.setattr(runner_mod, "run_backtest", fake_run)


def test_signal_places_limit_order_with_sl_tp(m1, cfg, tmp_path, monkeypatch):
    _fake_signal(monkeypatch)
    bot, fake = _bot(m1, cfg, tmp_path)
    bot.step(NOW)
    pend = [r for r in fake.sent if r["action"] == FakeMT5.TRADE_ACTION_PENDING]
    assert len(pend) == 1
    r = pend[0]
    assert r["type"] == FakeMT5.ORDER_TYPE_BUY_LIMIT and r["sl"] < r["price"] < r["tp"]
    assert r["magic"] == cfg["broker"]["magic_number"] and r["volume"] >= 0.01
    assert bot.state.orders  # notes kept for cancel rules
    bot.step(NOW)  # same bar again: an order is already working, so no second one
    assert len([r for r in fake.sent if r["action"] == FakeMT5.TRADE_ACTION_PENDING]) == 1


def test_order_cancelled_when_inversion_fails(m1, cfg, tmp_path, monkeypatch):
    _fake_signal(monkeypatch)
    bot, fake = _bot(m1, cfg, tmp_path)
    bot.step(NOW)
    ticket = next(iter(bot.state.orders))
    bot.state.orders[ticket]["gap_bottom"] = 10**6  # any close is now below the gap
    monkeypatch.setattr(runner_mod, "run_backtest", engine_mod.run_backtest)
    bot.step(NOW)
    assert any(r["action"] == FakeMT5.TRADE_ACTION_REMOVE for r in fake.sent)
    assert not bot.state.orders


def test_kill_switch_flattens_and_blocks(m1, cfg, tmp_path, monkeypatch):
    _fake_signal(monkeypatch)
    bot, fake = _bot(m1, cfg, tmp_path)
    fake.open_positions = [NS(ticket=7, magic=cfg["broker"]["magic_number"], volume=0.01,
                              type=FakeMT5.POSITION_TYPE_BUY, profit=-80.0)]
    bot.state.peak_equity = 600.0
    fake.equity = 500.0  # 16.7% below peak > 15% kill switch
    bot.step(NOW)
    assert bot.state.kill_switch
    assert not fake.open_positions
    assert not [r for r in fake.sent if r["action"] == FakeMT5.TRADE_ACTION_PENDING]
    bot2 = DemoBot(_client(fake), cfg, tmp_path)  # persists across restarts
    assert bot2.state.kill_switch


def test_doctor_sends_no_orders(m1, cfg, tmp_path):
    fake = FakeMT5(m1)
    report = run_doctor(_client(fake), cfg, tmp_path, export=True)
    text = report.read_text()
    assert "**demo**: yes" in text and "XAUUSD" in text and "No order was sent." in text
    assert fake.sent == []
    assert (tmp_path / "vantage_xauusd_m1.csv.gz").exists()
