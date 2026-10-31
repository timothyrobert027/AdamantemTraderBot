# Development Roadmap (stage-gated)

Each stage ends with a **results review**. The next stage starts only after you approve it.

| Stage | Name | Deliverables | Gate (what you review) | Env |
|---|---|---|---|---|
| **0** | Architecture | This documentation, repo skeleton, CI, safety test | Approve architecture, strategy hypothesis, risk limits | Cloud |
| 1 | Foundation | `config`, `core`, `safety`, logging; full safety and unit tests | CI green; safety tests show live mode and real accounts are refused | Cloud |
| 2 | Data | Dukascopy downloader, resampler, quality checks, Parquet store; fake symbol spec; `export_symbol_spec.py` | Data quality report (gaps, spikes, coverage) for ≥ 4 years | Cloud |
| 3 | Indicators + scanner | `indicators`, `scanner` with per-filter tests | Scanner statistics: % of time tradeable and rejection-reason distribution | Cloud |
| 4 | Strategy + risk | `strategy`, `baselines`, `risk` with property tests | H4/H1 zones and M5 FVGs drawn on fixture charts for visual check; signal list; sizing tables for both risk profiles; % of signals rejected by min-lot | Cloud |
| 5 | Backtest engine | `backtest` engine, costs, fills, metrics, report | Determinism proof; a single in-sample run *clearly labelled* | Cloud |
| 6 | Validation | Walk-forward, Monte Carlo, baseline comparison, holdout | Pass/fail against the pre-registered criteria in `STRATEGY.md`. **Failure means no deployment.** | Cloud |
| 7 | MT5 adapter | `mt5_broker`, `mt5_provider`, contract tests with a fake MT5, `adamantem doctor` | Contract test suite green | Cloud |
| 8 | VPS demo | Windows VPS setup, service, monitoring, cost calibration on Vantage data | ≥ 3 months, ≥ 100 demo trades; live vs backtest comparison | Windows |
| 9 | Review | Written assessment | Your decision. Live trading is **not** part of this project's scope. | — |

## Decisions needed from you at the Stage 0 gate
1. ~~Strategy direction~~ → H4/H1 supply/demand zones + volatility, M5 FVG inversion + retest entry (chosen). Approve the exact rules and criteria in `STRATEGY.md`.
2. ~~Risk appetite~~ → aggressive profile (3% / 6% daily / 30% kill switch) chosen; standard profile reported alongside.
3. ~~Account type~~ → Vantage **Standard** (chosen).
4. Whether you can get temporary access to any Windows PC for an early read-only symbol spec
   export.
5. ~~Context~~ → H4 and H1 zones; setups without a zone allowed, tagged `NONE` (chosen).

## Change of order (requested)
An **exploratory in-sample backtest** was brought forward, ahead of Stages 1-5, at your
request. It is code that works but has not been reviewed stage by stage. Its results do NOT
replace Stage 6 validation (walk-forward, Monte Carlo, untouched holdout). Run it from the
GitHub app: Actions -> "Backtest (exploratory, in-sample)" -> Run workflow.
