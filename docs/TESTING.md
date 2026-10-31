# Automated Testing Framework

Tooling: `pytest`, `pytest-cov`, `hypothesis` (property tests), `ruff` (lint), `mypy`
(types). CI runs on GitHub Actions on every push and PR (`.github/workflows/ci.yml`).

## Test layers

| Layer | Location | What it proves | Runs in cloud |
|---|---|---|---|
| Unit | `tests/unit/` | Each indicator, filter, rule, and sizing function is correct, including boundaries | Yes |
| Property | `tests/unit/test_*_props.py` | Invariants: size never exceeds risk, SL is always on the correct side, no look-ahead | Yes |
| Golden | `tests/fixtures/` | Indicator values match published reference values; a known bar series gives a known signal list | Yes |
| Integration | `tests/integration/` | Full backtest on a small fixture dataset is deterministic (same hash twice) | Yes |
| Contract | `tests/integration/test_mt5_contract.py` | `MT5Broker` against a **fake `MetaTrader5` module** that mimics the real API and retcodes | Yes |
| Safety | `tests/unit/test_safety.py` | Live mode impossible; real account refused; kill switch persists; no secrets in config | Yes |
| Windows smoke | `tests/windows/` (`@pytest.mark.mt5`) | Real terminal: connect, read spec, `order_check` only | VPS only, demo |

## Mandatory invariants (property-based)
1. `volume × loss_per_lot ≤ equity × risk_pct` for every generated input.
2. Long: `SL < entry < TP`; short: the mirror.
3. A signal at bar *t* depends only on bars ≤ *t* (checked by truncating future bars and
   asserting the same output).
4. A backtest with zero costs is never worse than the same backtest with costs.
5. No order is ever produced while the kill switch is set.

## Coverage gate
≥ 90% line coverage on `risk`, `safety`, `strategy`, `scanner`; ≥ 80% overall.
