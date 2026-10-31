# ADAMANTEM AI TRADER — System Architecture

Status: **Stage 0 (design)**. Nothing here has been backtested yet, and the
document makes no claims about performance.

## 1. Design principles

1. **Safety comes before features.** The system runs in `research`, `backtest`, `paper` or
   `demo` mode. It has no `live` mode. The MT5 adapter refuses to send any order unless the
   connected account reports `trade_mode == ACCOUNT_TRADE_MODE_DEMO`.
2. **No credentials in code, config or git.** The MT5 terminal is logged in by hand on the
   VPS. Python attaches to the running terminal with `mt5.initialize()` and never passes a
   password. Optional notifier tokens (e.g. Telegram) come only from environment variables.
3. **One core, many adapters (ports and adapters).** Strategy, scanner and risk are pure
   Python with no I/O. They run the same way in a backtest, in the cloud paper simulator and
   against MT5 demo. Only the data provider and the broker adapter change.
4. **Deterministic and testable.** Given the same bars and config, the system produces the
   same signals. All time handling is in UTC internally.
5. **Rules before ML.** Any ML component has to beat the rule-based baseline out of sample,
   by a margin stated in advance, before it is added.
6. **Each stage has a gate.** Each roadmap stage ends with a results review (see `ROADMAP.md`).

## 2. High-level view

```
                    ┌──────────────────────────────────────────────┐
                    │                 app / orchestrator            │
                    │  (mode: research | backtest | paper | demo)   │
                    └──────┬───────────────┬───────────────┬────────┘
                           │               │               │
          ┌────────────────▼──┐   ┌────────▼────────┐  ┌───▼─────────────┐
          │   data (port)     │   │  decision core  │  │ execution (port)│
          │ ───────────────── │   │ (pure, no I/O)  │  │ ─────────────── │
          │ CsvProvider       │──▶│ indicators      │─▶│ SimBroker       │
          │ DukascopyProvider │   │ scanner         │  │ MT5Broker(demo) │
          │ MT5Provider (Win) │   │ strategy        │  └───┬─────────────┘
          └───────────────────┘   │ risk            │      │
                                  └────────┬────────┘      │
                                           │               │
                ┌──────────────────────────▼───────────────▼──────────┐
                │ safety (mode guard, kill switch) · journal (SQLite) │
                │ monitoring (structured logs, health, notifier)      │
                └─────────────────────────────────────────────────────┘
```

### Data flow (one decision cycle, every closed M15 bar)

1. `data` delivers closed bars (M15 and H1) plus the current tick/spread.
2. `indicators` computes ATR, EMA and percentiles; `strategy.zones` maintains the live set of supply/demand zones.
3. `scanner` scores the market state: session, spread, volatility regime, trend regime,
   news blackout and data freshness. It returns `TRADEABLE` or a list of blocking reasons.
4. `strategy` turns a tradeable state into a `Signal` (side, entry, SL, TP, time stop),
   or nothing.
5. `risk` checks the signal against account state and the symbol spec. It returns a sized
   `OrderIntent` or a `Rejection(reason)`.
6. `safety.mode_guard` makes the final pre-send check (mode, demo account, kill switch).
7. `execution` sends the order: simulated, or MT5 demo.
8. `journal` records every scan, signal, rejection, order and fill, so every decision can
   be audited.

## 3. Python modules and responsibilities

Package root: `src/adamantem/`

| Package | Module | Responsibility |
|---|---|---|
| `config` | `settings.py` | Typed settings (pydantic) loaded from `config/*.yaml` plus env overrides. Validates that the mode is not live. |
| `core` | `models.py` | Immutable domain types: `Bar`, `Tick`, `SymbolSpec`, `Signal`, `OrderIntent`, `Order`, `Fill`, `Position`, `AccountState`. |
| | `enums.py` | `Mode`, `Side`, `Timeframe`, `RejectReason`, `ExitReason`. |
| | `clock.py` | Injected clock (real or simulated). Converts broker server time to UTC. |
| | `errors.py` | Exception hierarchy (`SafetyViolation`, `DataQualityError`, `BrokerError`). |
| `safety` | `mode_guard.py` | Final pre-trade gate: allowed mode, demo-only account, symbol whitelist, kill switch not set. |
| | `kill_switch.py` | Persistent halt flag, set on drawdown/limit breach. Only a human can clear it. |
| `data` | `providers/base.py` | `DataProvider` protocol: `get_bars(symbol, tf, start, end)`, `get_tick(symbol)`. |
| | `providers/csv_provider.py` | Reads normalized CSV/Parquet history. Runs in the cloud. |
| | `providers/dukascopy.py` | Downloads and normalizes free historical XAUUSD ticks/bars for research. |
| | `providers/mt5_provider.py` | `copy_rates_range`, `symbol_info_tick`. Windows only, lazy import. |
| | `quality.py` | Gap, duplicate, outlier, weekend and stale-bar checks; returns a quality report. |
| | `resample.py` | Tick → M1 → M15/H1 resampling with explicit bar-close semantics. |
| | `store.py` | Local Parquet cache keyed by source/symbol/timeframe. |
| `indicators` | `ta.py` | Vectorised EMA, ATR (Wilder), rolling percentile, rolling high/low. Tested against reference values. |
| `scanner` | `filters.py` | Independent filters: session, spread, volatility regime, trend regime, news blackout, rollover window, data freshness. |
| | `scanner.py` | Combines the filters into a `MarketState` with reasons. Has no trading logic. |
| `strategy` | `base.py` | `Strategy` protocol: `on_bar(state, history) -> Signal | None`. |
| | `zones.py` | Supply/demand zone detection (base + impulse), validity, freshness, invalidation and scoring. Pure functions over H1 bars. |
| | `supply_demand.py` | The v1 strategy: entry at a fresh zone with volatility gating, ATR stops, opposing-zone targets (see `STRATEGY.md`). |
| | `baselines.py` | Random-entry and buy-and-hold baselines that use the same exits, as controls. |
| `risk` | `sizing.py` | Fixed-fractional sizing from `SymbolSpec` (tick value, tick size, volume min/step). Rounds **down** and never up. |
| | `limits.py` | Daily, weekly and max-drawdown limits, max positions, max trades/day, loss streak, effective leverage cap. |
| | `profiles.py` | `standard` / `aggressive` profiles and the hard ceilings no config can exceed. |
| | `engine.py` | `RiskEngine.evaluate(signal, account, spec) -> OrderIntent | Rejection`. |
| `execution` | `broker.py` | `Broker` protocol: `account()`, `positions()`, `submit(intent)`, `modify()`, `close()`. |
| | `sim_broker.py` | Simulated fills with spread, slippage and commission. Used by the backtest and cloud paper mode. |
| | `mt5_broker.py` | MT5 demo adapter: `order_check` → `order_send`, retcode handling, filling-mode detection, magic number. |
| | `order_manager.py` | Position lifecycle: time stops, reconciliation with the broker after restarts. |
| `backtest` | `engine.py` | Event-driven bar replay that uses the exact same strategy, risk and SimBroker code as live. |
| | `costs.py` | Spread model (from data or a session profile), commission, slippage, swap. |
| | `fills.py` | Conservative intrabar rules: if a bar touches both SL and TP, count it as SL. Gap-through stops fill at the open. |
| | `metrics.py` | Expectancy (R), profit factor, win rate, max DD, Sharpe/Sortino, trade count, exposure. |
| | `walk_forward.py` | Rolling in-sample/out-of-sample splits, plus a final untouched holdout. |
| | `monte_carlo.py` | Trade-order resampling to get drawdown and risk-of-ruin distributions. |
| | `report.py` | Markdown/HTML report with equity curve and all assumptions stated. |
| `journal` | `store.py` | SQLite tables: scans, signals, rejections, orders, fills, equity snapshots. |
| `monitoring` | `logging.py` | Structured JSON logs that redact secrets. |
| | `notifier.py` | Optional Telegram/email alerts. The token comes from env, never from config files. |
| | `health.py` | Heartbeat, terminal-connected check, data-staleness alarm. |
| `app` | `orchestrator.py` | Main loop: wait for a bar to close, then run the decision cycle. |
| | `cli.py` | `adamantem backtest|scan|paper|demo|report`. |

## 4. Cross-cutting rules

- **Time:** MT5 returns bar times in *broker server time* encoded as epoch seconds. For many
  brokers that is GMT+2 or GMT+3 with DST; Vantage's offset still has to be checked on demo.
  `core.clock` converts these times to UTC once, at the provider boundary.
- **Symbol resolution:** the broker symbol may carry a suffix that depends on account type.
  The system resolves it at startup through `symbols_get("*XAU*")` and config, never by
  hard-coding.
- **Symbol spec drives the math:** contract size, tick value, tick size, digits, stops level,
  volume min/step/max and filling mode are read from the broker (`symbol_info`). The
  backtest gets them from a fixture snapshot of the same fields.
- **Idempotency:** every order carries a magic number and a client id. After a restart,
  `order_manager` reconciles open positions before it trades again.
