# Risk Management — designed for a $500 account

## 1. The key constraint: minimum lot size versus a small account

On a standard XAUUSD contract (100 oz/lot, per Vantage's own announcement), **0.01 lot = 1 oz
⇒ $1 of P/L per $1 price move**. Assuming `volume_min = 0.01` (still to be checked on demo):

| Risk per trade | $ at risk on $500 | Max stop distance at 0.01 lot |
|---|---|---|
| 0.5% | $2.50 | $2.50 |
| 1.0% | $5.00 | $5.00 |
| 2.0% | $10.00 | $10.00 |

A v1 stop of 1.5 × ATR(14, M15) on gold is often **wider than $5** at current gold
volatility. On a standard account, many valid signals would need *more* risk than allowed.

**Rule: if the minimum volume puts more than the allowed amount at risk, the trade is REJECTED.
Size is never rounded up.** The backtest reports how many signals were rejected for this
reason, so the effect is visible rather than hidden.

### Options to check in Stage 1 (decision for the user after the data is in)
1. **Vantage MT5 Cent account.** Much finer granularity. Spec and spread to be checked.
2. **XAUUSD247 (1-oz contract).** 0.01 lot = 0.01 oz, so sizing becomes nearly continuous.
   Session and weekend behaviour differ, regional availability is to be checked.
3. **Standard account with a tighter-stop variant.** Accept a lower signal rate.

The sizing code is spec-driven, so all three options need no code change: only a different
`SymbolSpec`.

## 2. Sizing formula (`risk/sizing.py`)
```
risk_money   = equity × risk_pct
loss_per_lot = (|entry − stop| / tick_size) × tick_value + commission_per_lot + est_slippage
raw_volume   = risk_money / loss_per_lot
volume       = floor(raw_volume / volume_step) × volume_step
reject if volume < volume_min
reject if volume × loss_per_lot > risk_money × 1.0     (never exceed)
```

## 3. Hard limits (defaults; configurable only downward via the config validator)

| Limit | Value | Action on breach |
|---|---|---|
| Risk per trade | 1.0% of equity (absolute cap 2.0%) | Reject trade |
| Open positions | 1 | Reject trade |
| Trades per day | 3 | Reject until next UTC day |
| Consecutive losses | 3 | Pause until next UTC day |
| Daily loss | 3% of start-of-day equity (realised + floating) | Close all, pause until next day |
| Weekly loss | 6% of start-of-week equity | Close all, pause until next week |
| Max drawdown from peak | 15% | **Kill switch**: close all, halt; only a human can reset |
| Effective leverage | notional / equity ≤ 10× | Reject trade |
| Free margin after entry | ≥ 70% of equity | Reject trade |
| Stop required | Every order has a server-side SL at send | Reject if missing |
| Weekend | Flat before Friday close | Forced exit |

## 4. Failure-mode risks covered
- **Disconnect:** server-side SL/TP protect open positions. On reconnect, reconcile first.
- **Stale data:** the scanner blocks trading (F1).
- **Runaway loop:** a trades-per-day cap and an order-rate limiter (max 1 order per 60 s).
- **Unknown broker error:** halt and alert. No blind retries.
- **Clock drift:** a VPS time-sync check in `monitoring.health`.
