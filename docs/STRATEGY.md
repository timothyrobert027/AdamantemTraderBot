# Strategy v1 — "Supply/Demand Zones + Volatility" (hypothesis, not yet validated)

This strategy is a **hypothesis to test**. It has **no** backtest results yet. Every rule
below is mechanical: two people (or two runs of the code) given the same bars will draw the
same zones and take the same trades.

## Idea
Institutional order flow leaves footprints: a short **base** (price pauses), then a strong
**impulse** away from it. The base marks unfilled orders. On the **first return** to the
base, price often reacts again. A demand zone acts as support and a supply zone as
resistance. Volatility (ATR) normalises every size and distance, so the rules adapt
automatically when gold gets quiet or wild.

## 1. Zone detection (H1, closed bars only)

Let `ATR = ATR14(H1)` measured at the base.

**Base:** 1–3 consecutive candles, each with `range ≤ 1.0 × ATR` and `body ≤ 0.5 × range`.

**Impulse (leg-out):** the 1–2 candles right after the base, together satisfying:
- Move from the base edge to the impulse close `≥ 2.0 × ATR`.
- Each impulse candle has `body ≥ 0.6 × range`, in the same direction.
- The close is beyond the base: above the base high (demand) or below the base low (supply).

**Zone boundaries:**
- Demand: proximal = highest *body top* in the base; distal = lowest *low* in the base.
- Supply: proximal = lowest *body bottom* in the base; distal = highest *high* in the base.

**Zone validity (all required):**
- Width `(proximal − distal) ≤ 1.0 × ATR`. A wider zone means the stop is too wide.
- **Fresh:** price has not traded into the zone since it formed. Only the first retest is
  traded.
- Age ≤ 120 H1 bars (≈ 5 trading days).
- Invalidated permanently once an H1 candle **closes** beyond the distal line.

**Zone score (logged, used for ranking):**
`score = impulse_size_in_ATR + (1 if base has 1 candle) − 0.01 × age_bars`.
When two zones overlap, keep the higher-scoring one.

## 2. Volatility rules
- **Regime gate:** trade only when ATR14(M15) is between its 30th and 95th percentile over the
  last 60 days. Below that, moves are too small to pay the spread. Above it is news chaos.
- **Every distance is in ATR units:** zone size, impulse size, stop buffer, spread limit.
- **Expansion check:** the impulse that created the zone must have ATR14(H1) at or above its
  20-bar median. A zone born in a dead market is ignored.

## 3. Entry (M15, evaluated on a closed bar, scanner must say `tradeable`)

**Long at a fresh demand zone:**
1. The M15 bar trades into the zone: `low ≤ proximal`, and it doesn't close below distal.
2. **Rejection:** the same bar or the next one closes **back above proximal** with
   `close > open` and lower wick `≥ 40%` of the bar range.
3. **Room to run:** the distance to the nearest opposing **supply** zone (proximal) is
   `≥ 2.0R`. If that zone is closer, skip the trade.
4. Enter at market on the next bar's open.

**Short at a fresh supply zone:** the exact mirror.

Optional trend filter (tested both **with** and **without**): trade demand only when H1 close
> EMA200(H1), and supply only when it is below.

## 4. Exits (fixed at entry)
- **Stop loss:** `distal ∓ 0.25 × ATR14(M15)` (beyond the zone plus a volatility buffer),
  widened if needed to the broker stops level.
- **Take profit:** the nearest opposing zone's proximal, capped at `3.0R`. If no opposing
  zone exists, use `2.5R`.
- **Time stop:** 24 M15 bars (6 h).
- **Session/weekend exit:** flat at 20:30 UTC and before the Friday close.
- One trade per zone, ever.

## 5. Variants tested (pre-registered; at most 4 so the result stays honest)
| ID | Entry | Trend filter |
|---|---|---|
| SD-A | Rejection close (above) | Off |
| SD-B | Rejection close | On |
| SD-C | Limit order at proximal (no confirmation) | Off |
| SD-D | Limit order at proximal | On |

Because 4 variants are tested, the acceptance bar applies to the best variant *after* a
multiple-testing adjustment (Bonferroni: p < 0.0125 against the random baseline).

## 6. Validation protocol (fixed before any results are seen)
1. **Data:** ≥ 4 years of M1 XAUUSD resampled to M15/H1. The last 12 months are a holdout,
   untouched until the end.
2. **Costs:** spread from the data or a session profile, plus slippage of 0.5 × spread on
   entries and stops, plus commission per account type.
3. **Walk-forward:** 12-month in-sample / 3-month out-of-sample, rolling. A small parameter grid
   only: base-range ∈ {0.8, 1.0, 1.2} ATR, impulse ∈ {1.5, 2.0, 2.5} ATR, SL buffer ∈ {0.1,
   0.25, 0.5} ATR.
4. **Acceptance (stitched out-of-sample, then holdout):** ≥ 150 trades; expectancy ≥ +0.15R after
   costs; profit factor ≥ 1.25; the 95th-percentile Monte Carlo max drawdown fits the chosen
   risk profile's kill switch; beats random entry (same exits) at the adjusted p-value; the
   parameter neighbourhood stays profitable.
5. **A failure is reported as a failure.** No deployment follows from it.

Higher risk per trade does **not** make the strategy's edge any larger. It only makes gains
*and* drawdowns bigger. The strategy has to show an edge at 1R first, before any risk profile
matters.

## 7. When ML would be allowed
Only as a ranking/filter on zones (e.g. which zones to take), and only if it lifts walk-forward
out-of-sample expectancy by ≥ 0.05R versus the score-based rules on the same splits.
