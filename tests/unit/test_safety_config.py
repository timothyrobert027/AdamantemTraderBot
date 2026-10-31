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


def test_risk_limits_within_caps():
    risk = load_default()["risk"]
    assert 0 < risk["risk_per_trade_pct"] <= risk["risk_per_trade_cap_pct"] <= 2.0
    assert risk["max_open_positions"] == 1
    assert risk["daily_loss_limit_pct"] <= 3.0
    assert risk["max_drawdown_kill_pct"] <= 15.0


def test_secrets_are_gitignored():
    ignored = (ROOT / ".gitignore").read_text().splitlines()
    for pattern in (".env", "config/local.yaml"):
        assert pattern in ignored
