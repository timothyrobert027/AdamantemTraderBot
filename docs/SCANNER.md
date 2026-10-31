# XAUUSD Market Scanner

The scanner answers one question on every closed M15 bar: **is the market fit to trade
right now, and if not, why not?** It never produces trade direction. That is the strategy's
job. The scanner is pure (no I/O) and fully unit-testable.

## Inputs
- Closed M15 and H1 bars (UTC), the current bid/ask, `SymbolSpec`, and a news calendar
  (optional).

## Filters (all must pass; each failure is logged as a reason)

| # | Filter | Rule (default, configurable) | Why |
|---|---|---|---|
| F1 | Data freshness | Last closed M15 bar ≤ 20 min old; no gap > 2 bars in the last 200 | Never trade on stale or broken data |
| F2 | Data sanity | No bar with range > 8 × ATR(14) and no zero-volume bar in the last 3 | Catch bad prints and feed glitches |
| F3 | Session | Entries only 07:00–20:00 UTC (London and NY overlap span) | Liquidity, tighter spreads |
| F4 | Rollover | No entries 20:45–22:15 UTC | Spreads widen sharply around daily rollover |
| F5 | Weekend | No entries Friday ≥ 18:00 UTC; flat before close | Weekend gap risk |
| F6 | Spread absolute | Spread ≤ `max_spread_points` (set from Vantage demo stats) | Cost control |
| F7 | Spread relative | Spread ≤ 10% of ATR(14, M15) | Cost relative to expected move |
| F8 | Volatility regime | ATR(14, M15) between its 10th and 95th percentile over the last 60 days | Skip dead markets and panic markets |
| F9 | Trend regime | H1 \|EMA50 − EMA200\| ≥ 0.5 × ATR(14, H1) | Pullback logic needs a trend to pull back within |
| F10 | News blackout | No entries from 30 min before to 30 min after high-impact USD events (CPI, NFP, FOMC, PCE, GDP) | Event slippage |
| F11 | Exposure | No open position on XAUUSD by this magic number | One position at a time |

## Output
```python
MarketState(
    time_utc, tradeable: bool, reasons: tuple[RejectReason, ...],
    trend: Literal["up", "down", "none"], atr_m15, atr_h1, spread, vol_percentile,
)
```

## Robustness notes
- Each filter is a separate function with its own tests: boundary times, DST change weeks,
  missing data.
- The news calendar is a pluggable source. A *historical* high-impact calendar is required
  to apply F10 honestly in backtests. If none is available, the backtest report states that
  F10 was not applied.
- Thresholds (F6, F8) are set from data observed **before** the test period, to avoid
  look-ahead bias.
