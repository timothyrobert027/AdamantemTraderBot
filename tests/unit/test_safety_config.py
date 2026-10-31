"""Stage 0 safety checks on the committed configuration and repository."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ALLOWED_MODES = {"research", "backtest", "paper", "demo"}
SECRET_KEY = re.compile(r"(password|passwd|secret|api_key|token|login)", re.IGNORECASE)


def load_default():
    return yaml.safe_load((ROOT / "config" / "default.yaml").read_text())


def test_mode_is_not_live():
    cfg = load_default()
    assert cfg["mode"] in ALLOWED_MODES
    assert cfg["live_trading_enabled"] is False


def test_demo_account_required():
    assert load_default()["broker"]["require_demo_account"] is True


def test_no_credential_keys_in_config():
    def walk(node, path=""):
        if isinstance(node, dict):
            for k, v in node.items():
                assert not SECRET_KEY.search(str(k)), f"credential-like key: {path}{k}"
                walk(v, f"{path}{k}.")

    walk(load_default())


HARD_CEILINGS = {
    "risk_per_trade_pct": 5.0,
    "daily_loss_limit_pct": 10.0,
    "weekly_loss_limit_pct": 20.0,
    "max_drawdown_kill_pct": 40.0,
    "max_effective_leverage": 50.0,
}


def test_risk_profiles_within_hard_ceilings():
    risk = load_default()["risk"]
    assert risk["profile"] in risk["profiles"]
    for name, profile in risk["profiles"].items():
        for key, ceiling in HARD_CEILINGS.items():
            assert 0 < profile[key] <= ceiling, f"{name}.{key}"
        assert profile["min_free_margin_pct"] >= 50.0
    assert risk["min_lot_risk_cap_pct"] <= HARD_CEILINGS["risk_per_trade_pct"]
    assert risk["max_open_positions"] <= 2
    assert risk["max_trades_per_day"] <= 5


def test_secrets_are_gitignored():
    ignored = (ROOT / ".gitignore").read_text().splitlines()
    for pattern in (".env", "config/local.yaml"):
        assert pattern in ignored
