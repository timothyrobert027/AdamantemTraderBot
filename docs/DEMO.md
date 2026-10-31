# Demo forward test - pre-registration

Committed before the bot runs on the demo account. Demo only: the bot refuses any account
whose `trade_mode` is not DEMO, and there is no live mode in the code.

## Configuration
Exactly the validated configuration of docs/HOLDOUT.md (`config/demo.yaml`): zones v2 (order
blocks + FVG on H1/H4, OB preferred), FVG-D entry on M5, zone setups only, single exit,
standard risk profile (1% target, 0.01 lot allowed up to 5%, kill switch at 15% from peak).
No parameter may change during the test.

## What the bot does every closed M5 bar
1. Reads ~70 trading days of M1 history from MT5 (bid + recorded spread).
2. Runs the backtest engine in decision mode on it; a new order is considered only if the
   strategy places one on the last closed bar.
3. Manages working orders (cancel outside the entry window, if the inversion fails, or if
   price moves 1R away) and positions (6-hour time stop, session exit 20:30 UTC). Expiry of the
   limit order (1 hour) is also set on the server.
4. Applies the risk limits to the real demo account: kill switch (persistent across restarts,
   reset only by a human editing `state/state.json`), daily and weekly loss limits (close
   everything), 3 consecutive losses and 3 trades a day (no new orders).
5. Places at most one limit order, with stop loss and take profit attached server-side.
Everything is written to `state/journal.jsonl`; `state/heartbeat.txt` shows the last cycle.

## Evaluation (decided now)
- Duration: at least **3 months** and at least **30 closed trades**, whichever is later.
- Compare with the backtest: average R, win rate, trades per month, real spread vs the $0.25
  assumption, slippage on stops, fills per order.
- **Stop early** if the kill switch fires, or if after 30 trades the average R is below 0.
- Continue past the minimum only while average R ≥ +0.10 and profit factor ≥ 1.15.
- Known limitation from research: the edge appeared only in high-volatility years
  (2024-2026); in quiet markets the bot is expected to trade rarely.

Real-money trading is outside this project's scope; it would need a separate written
decision by the account owner after this evaluation.
