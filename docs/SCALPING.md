# Scalping hypothesis S1 - pre-registration

Committed **before** the run. The whole experiment runs in one go: development, selection by
the rule below, validation on unseen data. No step needs a human decision, so nothing can be
adjusted after looking at results. A different design afterwards would be hypothesis S2 and
would need other unseen data.

## Goal
More trades than the validated swing configuration (docs/HOLDOUT.md, about 4 trades a month),
without losing the net edge per trade.

## Shared rules (all S variants)
- Zones v2 (order blocks + FVG, OB preferred), **zone setups only**.
- Entry as the validated FVG-D: inversion of the latest opposing FVG on the entry timeframe,
  limit order at the gap midpoint on the retest, H1 EMA200 trend filter.
- **Single exit at 1.5R** (target = opposing zone capped at 1.5R; room to it ≥ 1.5R).
- Spread must be ≤ 20% of the stop distance (validated swing: 10%).
- Up to **6 trades a day** (swing: 3). All other risk limits unchanged.

## Variants (3)
| ID | Entry timeframe | Zone timeframes | Bar settings |
|---|---|---|---|
| S-A | **M1** | M15 + H1 + H4 | arm 60 min, FVG age ≤ 30 min before arm, retest 15 min, time stop 2 h, spread ≤ 30% of ATR(M1) |
| S-B | **M1** | H1 + H4 | as S-A |
| S-C | M5 | **M15** + H1 + H4 | as the validated M5 settings |

M15 zones: same OB/FVG rules, maximum age 96 bars (1 day).

## Periods
- **Development:** 2021-11-01 → 2025-11-01 (already seen during earlier work).
- **Validation:** 2016-01-01 → 2020-12-31, never used before. Warm-up from 2015-10-01, no trade
  before 2016-01-01. The validated swing configuration is also run here, as an extra
  out-of-sample check for it (no change to it).
- The 2025-11 → 2026-10 holdout is **not** used: it has already been looked at.

## Selection rule (development, standard profile, $0.25 spread)
Among S-A, S-B, S-C with **≥ 200 trades**, pick the one with the **highest average R**.
If none has 200 trades, the experiment stops: no candidate.

## Validation criteria (2016-2020, standard profile), all required
| Criterion | Threshold |
|---|---|
| Trades | ≥ 250 (about 4 a month or more) |
| Average R ($0.25 spread) | ≥ +0.10R |
| Profit factor ($0.25 spread) | ≥ 1.15 |
| Kill switch | not triggered |
| Average R with $0.45 spread | ≥ 0 |

## Reported for comparison
Trades per month, monthly growth, drawdown, for every S variant and the swing configuration,
all three risk profiles and both spreads. Data: HistData M1 bid + assumed constant spread,
not Vantage's feed. Scalping is the most spread-sensitive part of this project, so a pass
must be re-checked on Vantage's real spreads before any demo.
