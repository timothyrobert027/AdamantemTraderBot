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

## Evaluation (decided now; the owner set the demo to at most 2 weeks)
Two weeks is about 10 trading days. The validated configuration averaged roughly 4 trades a
month in the holdout year, so the demo will produce only a handful of trades: far too few to
judge profitability. The 2-week demo is therefore a **technical acceptance test**:

- [ ] The bot runs 10 trading days without unhandled errors (`state/journal.jsonl`).
- [ ] Data is never stale for more than one cycle during market hours.
- [ ] Every order sent has stop loss and take profit on the server, the correct volume and the
      magic number; expired, cancelled and filled orders are handled as in the backtest.
- [ ] Positions are closed by the 6-hour time stop and the session exit when due.
- [ ] After a restart the bot reconciles open orders/positions and keeps the kill switch.
- [ ] Measured Vantage spread and stop slippage are recorded and compared with the $0.25
      assumption; the backtest is re-run on the exported Vantage history.
- [ ] If any trade happens: its entry, stop and target match what the backtest engine would
      have done on the same bars.

Performance can only be judged over many more trades (at least 30). That evidence will come
slowly whichever account the bot runs on.

Real-money trading is outside this project's scope; it would need a separate written
decision by the account owner after this evaluation.
