# What can be built in the cloud vs. what needs Windows MT5

You can drive everything in the "Cloud" column from an iPhone: Claude Code on the web, the
GitHub mobile app, and CI reports.

| Component | Cloud (Linux, no MT5) | Needs Windows + MT5 terminal |
|---|---|---|
| Config, domain models, safety guards | ✅ fully | — |
| Indicators, scanner, strategy, risk engine | ✅ fully | — |
| Historical data download (Dukascopy) and quality checks | ✅ fully | — |
| Backtest engine, cost model, walk-forward, Monte Carlo, reports | ✅ fully | — |
| Paper trading on replayed data (SimBroker) | ✅ fully | — |
| `MT5Broker` / `MT5Provider` logic | ✅ against a **fake MetaTrader5 module** | Real-API confirmation |
| CI (lint, types, tests, coverage, backtest reports as artifacts) | ✅ GitHub Actions | — |
| Install check of the `MetaTrader5` wheel | ✅ GitHub `windows-latest` runner (import only) | — |
| Vantage symbol spec, server time, spreads, filling mode | ❌ | ✅ demo terminal |
| Vantage historical bars for cost calibration | ❌ | ✅ `copy_rates_range` export |
| Order placement on demo | ❌ | ✅ |
| Unattended operation, restarts, reconciliation in practice | ❌ | ✅ VPS |

Roughly **85–90% of the codebase** can be written and tested before Windows is needed. The
Windows phase is mostly verification and calibration.

**Useful early step that needs no VPS:** if you can open a Vantage MT5 demo on any Windows PC
(a friend's, or a short-lived cheap VPS), run the read-only `scripts/export_symbol_spec.py`
(added in Stage 2). It dumps the XAUUSD spec and recent bars to a file you can commit. That
answers the open questions in `MT5_INTEGRATION.md` early.
