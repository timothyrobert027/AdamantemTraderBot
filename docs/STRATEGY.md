# Strategy v1 — "H1 Supply/Demand Zones + M5 FVG Inversion Retest" (hypothesis, not yet validated)

This strategy is a **hypothesis to test**. It has **no** backtest results yet. Every rule
below is mechanical: two people (or two runs of the code) given the same bars will draw the
same zones and take the same trades.

## Idea
Institutional order flow leaves footprints: a short **base** (price pauses), then a strong
**impulse** away from it. The base marks unfilled orders. On the **first return** to the
base, price often reacts again. A demand zone acts as support and a supply zone as
resistance. Volatility (ATR) normalises every size and distance, so the rules adapt
automatically when gold gets quiet or wild.

**H1 zone = *where* to trade. M5 fair value gap (FVG) = *when* to enter.** The hypothesis: as
price falls into a demand zone it leaves bearish FVGs behind. When an M5 candle *closes
above* the most recent bearish FVG, sellers have failed (the FVG is "inverted"). The entry
comes on the **retest** of that gap, which should now act as support. Supply is the mirror.

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
- **Regime gate:** trade only when ATR14(M5) is between its 30th and 95th percentile over the
  last 60 days.
- **Every distance is in ATR units:** zone size, FVG minimum size, stop buffer, spread limit.
- **Expansion check:** the impulse that created the zone must have ATR14(H1) at or above its
  20-bar median.
- **Cost check:** spread ≤ 10% of the stop distance. M5 stops are tight, so the spread is a
  larger share of each trade than it was on M15.

## 3. Fair value gap definition (M5, 3-candle pattern on closed bars)
Candles `c1, c2, c3` (c3 is the newest):
- **Bearish FVG:** `c3.high < c1.low`. Gap = `[c3.high, c1.low]`.
- **Bullish FVG:** `c3.low > c1.high`. Gap = `[c1.high, c3.low]`.
- Minimum size: gap height ≥ `0.15 × ATR14(M5)`. Smaller gaps are noise.
- An FVG exists from the close of `c3` onward. Detection never looks at later candles.

## 4. Entry (M5; long described, short is the exact mirror)

1. **Arm:** an M5 candle trades into a fresh H1 **demand** zone (`low ≤ proximal`) without an
   H1 close below distal. The setup stays armed for 36 M5 bars (3 h).
2. **Track the last bearish FVG:** while armed, the reference gap is the **most recently
   created** bearish FVG, formed after the arm or at most 24 bars before it.
3. **Break (inversion):** an M5 candle **closes above the top** of that gap (`close > c1.low`).
   The FVG is now inverted.
4. **Room to run:** the target (below) must be ≥ 2.0R away. Otherwise cancel.
5. **Retest entry:** place a **buy limit at the top edge of the inverted FVG**. It is valid for
   12 M5 bars (1 h). Cancel if:
   - it isn't filled in time;
   - an M5 candle closes **below the bottom** of the gap before the fill (the inversion failed);
   - price reaches 1R of the planned trade before the fill (the move left without us).
6. **Backtest fill rule:** a buy limit fills only when the **ask** reaches the price. Bars are
   bid-based, so this means `bid low ≤ limit − spread`. Touching the price is not enough.

## 5. Exits (fixed at entry)
- **Stop loss:** below the lowest low between arming and the break, minus `0.2 × ATR14(M5)`.
  Widened if needed to the broker stops level.
- **Take profit:** the nearest opposing H1 supply zone's proximal, capped at `3.0R`. If there
  is none, use `2.5R`.
- **Time stop:** 72 M5 bars (6 h).
- **Session/weekend exit:** flat at 20:30 UTC and before the Friday close.
- One trade per zone, ever. At most one pending limit order at a time.

## 6. Variants tested (pre-registered; at most 4)
| ID | Retest limit price | Trend filter (H1 EMA200) |
|---|---|---|
| FVG-A | Top edge of the inverted gap | Off |
| FVG-B | Top edge | On |
| FVG-C | Midpoint of the gap (50%) | Off |
| FVG-D | Midpoint | On |

The edge fills more often. The midpoint gives a better price and a smaller stop, but misses
more trades. The test measures this trade-off instead of guessing. Because 4 variants are
tested, the best one must beat random entry at p < 0.0125 (Bonferroni).

## 7. Validation protocol (fixed before any results are seen)
1. **Data:** ≥ 4 years of M1 XAUUSD resampled to M5/H1. The last 12 months are a holdout,
   untouched until the end.
2. **Costs:** spread from the data or a session profile, plus slippage of 0.5 × spread on
   entries and stops, plus commission per account type.
3. **Walk-forward:** 12-month in-sample / 3-month out-of-sample, rolling. A small parameter grid
   only: impulse ∈ {1.5, 2.0, 2.5} ATR(H1), FVG min size ∈ {0.1, 0.15, 0.25} ATR(M5), retest window
   ∈ {6, 12, 24} bars.
4. **Acceptance (stitched out-of-sample, then holdout):** ≥ 150 trades; expectancy ≥ +0.15R after
   costs; profit factor ≥ 1.25; the 95th-percentile Monte Carlo max drawdown fits the chosen
   risk profile's kill switch; beats random entry (same exits) at the adjusted p-value; the
   parameter neighbourhood stays profitable.
5. **A failure is reported as a failure.** No deployment follows from it.

Higher risk per trade does **not** make the strategy's edge any larger. It only makes gains
*and* drawdowns bigger. The strategy has to show an edge at 1R first, before any risk profile
matters.

## 8. When ML would be allowed
Only as a ranking/filter on zones (e.g. which zones to take), and only if it lifts walk-forward
out-of-sample expectancy by ≥ 0.05R versus the score-based rules on the same splits.
