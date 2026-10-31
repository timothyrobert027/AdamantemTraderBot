# ADAMANTEM AI TRADER

Autonomous XAUUSD trading system for Vantage MetaTrader 5.
**Scope: research, backtesting and demo trading only. No live trading.**

Current stage: **0 — Architecture** (no trading code yet, no performance results).

## Safety rules (enforced in code and tests)
- No live mode exists. Orders go only to accounts reporting `ACCOUNT_TRADE_MODE_DEMO`.
- The bot never handles a broker password. The MT5 terminal is logged in by hand.
- No secrets in the repository (`.env` and `config/local.yaml` are git-ignored).
- No ML unless it beats the rule-based baseline out of sample by a margin stated in advance.

## Documents
| Doc | Content |
|---|---|
| [ARCHITECTURE](docs/ARCHITECTURE.md) | System design, modules, data flow |
| [ROADMAP](docs/ROADMAP.md) | Stage-gated plan |
| [MT5_INTEGRATION](docs/MT5_INTEGRATION.md) | Vantage / MT5 technical requirements |
| [SCANNER](docs/SCANNER.md) | XAUUSD market scanner |
| [STRATEGY](docs/STRATEGY.md) | v1 strategy hypothesis and validation protocol |
| [RISK](docs/RISK.md) | Risk management for a $500 account |
| [TESTING](docs/TESTING.md) | Testing framework |
| [DEPLOYMENT](docs/DEPLOYMENT.md) | Windows VPS deployment |
| [CLOUD_VS_WINDOWS](docs/CLOUD_VS_WINDOWS.md) | What needs MT5 and what doesn't |
| [HOLDOUT](docs/HOLDOUT.md) | Validated configuration and its test |
| [DEMO](docs/DEMO.md) | Demo forward test plan |
| [GUIDA_VPS](docs/GUIDA_VPS.md) | Guida in italiano: VPS + MT5 demo dall'iPhone |

## Repository layout
```
config/            default.yaml (no secrets); local.yaml is git-ignored
docs/              design documents
src/adamantem/     config core safety data indicators scanner strategy
                   risk execution backtest journal monitoring app
tests/             unit/ integration/ fixtures/
data/ reports/     git-ignored outputs
scripts/           utility scripts (e.g. symbol-spec export, Stage 2)
.github/workflows/ CI (Linux tests + Windows MT5 wheel import check)
```

## Development (cloud)
```bash
pip install -e .[dev]
pytest
```
