# Vantage MT5 Integration — Technical Requirements

Verified facts are marked **[verified]**. Items still to be confirmed on a Vantage demo
account are marked **[verify on demo]**. Nothing below has been fabricated. Where I am unsure,
the item is marked for verification.

## 1. The official `MetaTrader5` Python package

- **[verified]** The PyPI package `MetaTrader5` (latest 5.0.6231, Sep 2026) ships wheels for
  **Windows x86-64 only**, for CPython 3.6–3.14.
- It talks over IPC to a **locally running MT5 terminal**. It is not a network API. Without a
  terminal on the same Windows machine, it cannot connect.
- Typical flow:
  `mt5.initialize(path=...)` → `account_info()` → `symbol_info()` / `copy_rates_range()` →
  `order_check()` → `order_send()` → `mt5.shutdown()`.
- Each Python process holds **one terminal connection**. Run one bot process per terminal.
- Third-party bridges exist (`mt5-remote` runs the package under Wine or a VM and serves it
  over RPC). They are **not** part of the plan: they add a fragile layer. The plan is native
  Windows on a VPS.

## 2. Credentials policy (no password ever handled by the bot)

- The user logs in to the Vantage **demo** account **by hand in the MT5 terminal** on the
  VPS and ticks "save password" *in the terminal*.
- The bot calls `mt5.initialize(path=TERMINAL_PATH)` **without** `login`, `password` or
  `server`. It attaches to the session that is already authenticated.
- At startup the bot reads `account_info().trade_mode` and **aborts** unless it equals
  `ACCOUNT_TRADE_MODE_DEMO`. The account number appears in logs only in masked form (`****1234`).

## 3. Vantage-specific items

| Item | Status | Notes |
|---|---|---|
| Demo server name | **[verify on demo]** | A third-party list shows `VantageInternational-Demo`. Use the name shown in the Vantage client portal or MT5. |
| Gold symbol name and suffix | **[verify on demo]** | Resolve at runtime via `symbols_get("*XAU*")`. Suffixes can differ by account type. |
| Standard XAUUSD contract size | **[verified, press]** | 100 oz per lot, per Vantage's XAUUSD247 announcement. So 0.01 lot = 1 oz, and a $1 move ≈ $1 P/L. |
| XAUUSD247 | **[verified, press]** | 1-oz contract, 24/7 trading, launched Jul 2026, availability varies by region. Finer sizing granularity, but weekend liquidity and spreads differ. It would be studied separately. |
| MT5 Cent account | **[verified, help-centre search snippet]** | Can be opened from the client portal or app. P/L is in cents, which gives far finer risk granularity on a small account. Spec and spread still to be checked. |
| `volume_min`, `volume_step` | **[verify on demo]** | 0.01 is common but not confirmed for Vantage. |
| Stops level, freeze level | **[verify on demo]** | `trade_stops_level`, `trade_freeze_level`. |
| Filling mode | **[verify on demo]** | Read `symbol_info().filling_mode` and pick FOK or IOC accordingly. |
| Commission per lot (Raw/ECN) | **[verify on demo]** | Depends on account type. |
| Server time zone | **[verify on demo]** | Compare the last bar's timestamp with UTC. |
| Swap long/short | **[verify on demo]** | `swap_long`, `swap_short`. The v1 strategy closes positions intraday. |

## 4. Order handling requirements (`mt5_broker.py`)

- Always call `order_check(request)` before `order_send(request)`.
- Market orders use `TRADE_ACTION_DEAL`, with SL/TP attached at send time and an explicit
  `deviation`, `magic`, `comment`, and a filling type taken from the symbol.
- Retcodes must be handled explicitly: `10009` DONE, `10004` REQUOTE (bounded retry),
  `10006` REJECT, `10016` INVALID_STOPS, `10018` MARKET_CLOSED, `10019` NO_MONEY,
  `10027` AUTOTRADING_DISABLED (alert, no retry). Any unknown retcode halts trading.
- Before sending, enforce `trade_stops_level` and round prices to `digits`.
- After a restart, reconcile `positions_get(magic=...)` with the journal before acting.

## 5. Data notes

- Research data from Dukascopy is **not** Vantage's price feed. Spreads and occasional
  spikes differ. Once the demo is running, the system exports Vantage M1/M5 history with
  `copy_rates_range` and re-runs the backtest on it to calibrate the cost model.

## 6. Open item

`vantagehelpcenter.com` is blocked by this cloud session's network policy. The Vantage help
pages could not be read directly, which is why the items above are marked for demo
verification.
