# Risk Management — designed for a $500 account

There are two risk profiles: **standard** and **aggressive** ("high risk, high reward",
selected by the user). Every backtest reports **both**, so the trade-off is visible. Hard
ceilings apply on top of either profile: the config validator rejects anything above them.

## 1. What higher risk means (pure arithmetic, not a backtest)

Drawdown after a run of consecutive losses, compounding:

| Risk per trade | 10 losses in a row | 20 losses in a row |
|---|---|---|
| 1% | −9.6% | −18.2% |
| 3% | −26.3% | −45.6% |
| 5% | −40.1% | −64.2% |

Losing streaks happen more often than intuition says. *Illustration only:* with a 40% win
rate, the expected number of 10-loss streaks in 500 trades is about **1.2**. So one is more
likely than not. Recovering a 45% drawdown needs an **82%** gain.

Higher risk scales profits and losses alike. It does not create an edge.

## 2. The minimum-lot constraint

On standard XAUUSD (100 oz/lot), **0.01 lot ≈ $1 P/L per $1 move**. Assuming
`volume_min = 0.01` (still to be checked on demo), the widest stop the system can accept is:

| Risk per trade | $ at risk on $500 | Max stop at 0.01 lot |
|---|---|---|
| 1% | $5 | $5 |
| 3% | $15 | $15 |

**Chosen account: Vantage Standard.** The M5 FVG stops (below the M5 swing low plus
0.2 × ATR) are much tighter than zone stops, so signals are expected to fit the limit more often. The backtest
will measure the actual rejection rate.

**Coarse sizing on a Standard account:** the volume steps by 0.01 lot ($1 per $1). Rounding
down means the *actual* risk often sits below the target. Example at 3% ($15) with a $4 stop:
raw size 0.0375 → 0.03 lot → actual risk $12 (2.4%). The journal records target and actual
risk for every trade, and the backtest uses actual risk, so results aren't overstated.

**Rule: if the minimum volume would risk more than allowed, REJECT the trade. Size is never
rounded up.**

## 3. Sizing formula (`risk/sizing.py`)
```
risk_money   = equity × risk_pct
loss_per_lot = (|entry − stop| / tick_size) × tick_value + commission_per_lot + est_slippage
volume       = floor((risk_money / loss_per_lot) / volume_step) × volume_step
reject if volume < volume_min  or  volume × loss_per_lot > risk_money
```

## 4. Limits

| Limit | Standard | Aggressive | Hard ceiling | Action on breach |
|---|---|---|---|---|
| Risk per trade | 1% | 3% | 3% | Reject |
| Open positions | 1 | 1 | 2 | Reject |
| Trades per day | 3 | 3 | 5 | Reject until next day |
| Consecutive losses | 3 | 3 | 4 | Pause until next day |
| Daily loss | 3% | 6% | 8% | Close all, pause until next day |
| Weekly loss | 6% | 12% | 15% | Close all, pause until next week |
| Max drawdown from peak | 15% | 30% | 35% | **Kill switch**: halt; only a human can reset |
| Effective leverage (notional/equity) | 10× | 20× | 25× | Reject |
| Free margin after entry | ≥ 70% | ≥ 50% | ≥ 50% | Reject |
| Server-side stop on every order | required | required | — | Reject |
| Flat before weekend | yes | yes | — | Forced exit |

## 5. Failure modes covered
- **Disconnect:** server-side SL/TP protect open positions. On reconnect, reconcile first.
- **Stale data:** the scanner blocks trading.
- **Runaway loop:** a trades-per-day cap and at most 1 order per 60 s.
- **Unknown broker error:** halt and alert. No blind retries.
- **Clock drift:** a VPS time-sync check.
