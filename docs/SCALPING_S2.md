# Scalping hypothesis S2 + third test of the swing configuration - pre-registration

Committed **before** the run; everything below runs in one go with no human decision.

## Why S2
S1 (docs/SCALPING.md) produced too few trades and M1 entries lost money. The user wants at
least two good trades a day. A minimum cannot be forced without taking bad trades, so S2
tests setup families designed to occur about twice a day, and keeps them only if each
trade stays profitable after costs.

## Shared rules (all S2 families)
- Entry timeframe **M5**. Entry as FVG-D: retest limit at the gap midpoint (ORB: at the
  broken range edge), **H1 EMA200 trend filter**.
- Single exit at **1.5R** (opposing zone capped at 1.5R; room ≥ 1.5R).
- Spread ≤ 20% of the stop and ≤ 20% of ATR(M5). Up to **6 trades a day**, one position at a
  time. Standard risk profile and kill switches unchanged.

## Families (4 variants)
| ID | Setup |
|---|---|
| S2-A | **Trend FVG**: every new opposing M5 FVG is a setup (no zone needed); entry on its inversion + retest; stop beyond the FVG's three candles + 0.2 ATR; setup valid 3 h |
| S2-B | **Re-tested zones**: order blocks + FVG on M15/H1/H4, each zone re-armable up to **3 touches**, maximum age doubled (M15 2 days, H1 10 days, H4 20 days) |
| S2-C | **Opening range**: London 08:00 and New York 09:30 local time (DST-aware); range of the first 30 min; first M5 close beyond it within 2 h; limit on the retest of the broken edge; stop beyond the range midpoint + 0.2 ATR; cancelled if price closes back through the midpoint |
| S2-AC | S2-A and S2-C together |

## Periods
- Development / diagnosis: 2021-11-01 → 2025-11-01 (already seen).
- Validation: **2016-01-01 → 2020-12-31**, never used (warm-up from 2015-10-01).

## Selection rule (development, standard profile, $0.25 spread)
Among the four, those with **≥ 1.5 trades per trading day** and **average R ≥ +0.05**; pick
the highest average R. If none qualifies: no candidate, nothing from S2 is validated.

## S2 validation criteria (2016-2020, standard profile), all required
| Criterion | Threshold |
|---|---|
| Trades per trading day | ≥ 1.5 |
| Average R ($0.25 spread) | ≥ +0.05R |
| Profit factor | ≥ 1.10 |
| Kill switch | not triggered |
| Average R with $0.45 spread | ≥ 0 |

## Third test of the validated swing configuration (always run)
Configuration exactly as docs/HOLDOUT.md, on 2016-2020. Criteria, all required: trades ≥ 30,
average R ≥ +0.10, profit factor ≥ 1.15, kill switch not triggered.

## Reported
A funnel per family (setups, breaks, orders and fills per day; main rejection reasons),
trades per day, monthly growth, drawdown, all profiles and both spreads. Data: HistData bid
+ assumed constant $0.25 spread (gold traded at $1,050-2,070 in 2016-2020, so the same
dollar spread is relatively larger than in 2025).

---

## Result (run 41216032793, 2026-10-31) — appended after the run, rules unchanged

**S2: NO CANDIDATE.** In development every family lost money per trade and none reached
1.5 trades per day; S2 was not validated.

| Family (dev, standard, $0.25) | Setups/day | Orders/day | Trades/day | Avg R | PF | Kill switch |
|---|---|---|---|---|---|---|
| S2-A trend FVG | 18.9 | 0.57 | 0.32 | −0.04 | 0.94 | 2022-10-21 |
| S2-B re-tested zones | 8.8 | 0.31 | 0.18 | −0.07 | 0.88 | 2024-01-11 |
| S2-C opening range | 2.2 | 0.17 | 0.11 | −0.12 | 0.80 | 2022-12-21 |
| S2-AC | 21.1 | 0.59 | 0.34 | −0.03 | 0.96 | 2022-09-30 |
| Swing (validated) | 1.9 | 0.10 | 0.06 | +0.29 | 1.51 | — |

Most setups were filtered out by the session window; after the kill switch fired, every later
setup was rejected, which is why trades per day stayed low. Before that, the per-trade result
was already slightly negative. With the $0.45 spread all families lost clearly.

**Swing configuration on 2016-2020: FAILED.** 14 trades (criterion ≥ 30), average R −0.46,
profit factor 0.38, no kill switch. All 14 trades are from 2020; in 2016-2019 the spread
filter (spread ≤ 10% of ATR(M5), with a constant $0.25 spread) rejected almost every setup
because gold's 5-minute ranges were small. Combined with the earlier results, the swing
configuration has only shown an edge in the high-volatility years 2024-2026.
