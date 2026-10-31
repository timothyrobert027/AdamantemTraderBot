# Strategy v1 — "H1 Trend / M15 Pullback" (hypothesis, not yet validated)

This strategy is a **hypothesis to test**. It has **no** backtest results yet. Parameters
are reasonable starting values and are not optimised. Their effect is measured only within
the validation protocol below.

## Rationale
Gold tends to trend in sessions driven by USD and real-rate news. Buying a pullback inside
an established higher-timeframe trend gives a defined invalidation point, so the stop is
objective and sizing is clean. That property matters most for the risk engine.

## Rules (evaluated only on a CLOSED M15 bar when the scanner says `tradeable`)

**Trend (H1, last closed bar)**
- Up-trend: `EMA50 > EMA200` and `close > EMA50`.
- Down-trend: `EMA50 < EMA200` and `close < EMA50`.

**Long entry (M15)**
1. H1 up-trend.
2. Pullback: within the last 6 M15 bars, at least one `low ≤ EMA20(M15)`.
3. Momentum reset: `RSI14(M15)` was `< 40` within the last 6 bars and the current bar closes
   with `RSI14 ≥ 40` (crossing back up).
4. Trigger: current bar `close > open` and `close > EMA20(M15)`.
5. Enter at market on the next bar's open (in the backtest: the next bar's open plus the
   modelled spread and slippage).

**Short entry:** the exact mirror (down-trend, `high ≥ EMA20`, RSI `> 60` then `≤ 60`,
bearish close below EMA20).

**Exits (all set at entry; no discretionary changes)**
- Stop loss: `entry ∓ 1.5 × ATR14(M15)`, widened if needed to respect the broker stops level.
- Take profit: `entry ± 2.0 × (stop distance)`, i.e. 2R.
- Time stop: close at market after 16 M15 bars (4 h) if neither SL nor TP was hit.
- Session exit: close any open position at 20:30 UTC and before the Friday close.
- No trailing stop, no partial closes in v1. With 0.01-lot positions, a partial close is
  often impossible.

**Frequency:** at most 3 entries per day, 1 open position at a time.

## Validation protocol (fixed in advance, before any results are seen)

1. **Data:** at least 4 years of M1 XAUUSD history, resampled. The last 12 months are held
   out and untouched until the final test.
2. **Costs:** spread taken from the data or a session profile, plus slippage of 0.5 × spread
   on entries and stops, plus commission per account type. Swap is ignored because positions
   close intraday.
3. **Walk-forward:** 12-month in-sample / 3-month out-of-sample, rolling. Parameters may be
   chosen only from a small grid: EMA20 ∈ {15, 20, 30}, SL ATR ∈ {1.25, 1.5, 2.0}, TP R ∈
   {1.5, 2.0, 2.5}.
4. **Acceptance criteria (all required on stitched OOS and then on the holdout):**
   - ≥ 200 trades OOS.
   - Expectancy ≥ +0.10 R per trade after costs.
   - Profit factor ≥ 1.20.
   - 95th-percentile Monte Carlo max drawdown ≤ 20% at the chosen risk per trade.
   - Beats the random-entry baseline (same exits, same filters) at p < 0.05.
   - Parameter plateau: neighbouring grid values keep expectancy > 0.
5. **If the criteria fail,** the result is reported as a failure. The strategy is revised as
   a new, separately logged hypothesis. Tests on the holdout are counted and reported.

## When ML would be allowed
Only as a **filter** on v1 signals (meta-labelling), and only if, on walk-forward OOS, it
improves expectancy by ≥ 0.05 R without dropping the trade count below 200. The comparison
is made against the rule-only version on the same splits.
