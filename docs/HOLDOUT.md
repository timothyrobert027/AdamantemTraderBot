# Holdout test - pre-registration

Written and committed **before** any data from the holdout period was used. Nothing below may
be changed after the run; a different configuration would be a new hypothesis that needs new,
unseen data.

## Why
The in-sample run of zones v2 (order blocks + FVG on H1/H4, 2021-11 → 2025-11) showed one
promising configuration and a clear pattern: setups from order blocks averaged about +0.2R
while setups without a zone averaged about 0R. In-sample results are optimistic by
construction (12 variants × 3 profiles were compared on the same data), so the only honest
check is one frozen configuration on data that was never looked at.

## Data
- Holdout: **2025-11-01 → latest month HistData has published** (target 2026-10-31).
- Indicators, zones and volatility percentiles warm up from 2025-08-01; **no trade can be
  opened before 2025-11-01**.
- HistData M1 bid + assumed constant spread of $0.25 (stress $0.45 also reported).

## Frozen configuration
- Strategy v2 zones: order blocks + FVG on H1/H4, OB preferred (docs/STRATEGY.md §1).
- Variant **FVG-D**: retest limit at the gap midpoint, H1 EMA200 trend filter.
- **Zone setups only** (`allow_no_zone_setups: false`): chosen from the in-sample observation
  above, so it is part of what this test checks.
- **Single exit** (no break-even, no 3 take profits).
- Primary profile: **standard** (1% target risk, 0.01 lot allowed up to 5%, kill switch 15%).
  Aggressive and max profiles are reported for information only.
- All other parameters as in `config/default.yaml` at this commit.

## Pass criteria (primary run: standard profile, $0.25 spread), all required
| Criterion | Threshold |
|---|---|
| Trades | ≥ 30 |
| Average R per trade | ≥ +0.10R |
| Profit factor | ≥ 1.15 |
| Kill switch | not triggered |

## What follows
- **Pass:** the configuration may move to the MT5 demo on the Windows VPS, after re-running it
  on Vantage's own history and spreads. Passing on one year of HistData is evidence, not proof.
- **Fail:** the configuration does not go to demo. The result is reported as it is.

---

## Result (run 41205906028, 2026-10-31) — appended after the run, criteria unchanged

**Verdict: PASSED** on the primary run (standard profile, $0.25 spread). Data available:
2025-11-01 → 2026-10-23 (HistData had not yet published the last week of October).

| Criterion | Threshold | Holdout |
|---|---|---|
| Trades | ≥ 30 | 45 |
| Average R | ≥ +0.10 | +0.43 |
| Profit factor | ≥ 1.15 | 1.92 |
| Kill switch | not triggered | not triggered (max DD 9.7%) |

Caveats recorded with the result:
- t-statistic of mean R = 1.78 (one-sided p ≈ 0.04): positive, but 45 trades is a small sample.
- Concentration: order blocks +0.79R (23 trades) vs FVG +0.06R (22); shorts +0.84R vs longs
  +0.11R; March 2026 (3 trades) produced about 57% of the net profit.
- With the stress spread ($0.45) the holdout stayed positive (34 trades, +0.43R), unlike the
  in-sample period where it fell to ~0R: gold volatility in the holdout year was high.
- Data is HistData with an assumed constant spread, not Vantage's feed.

Next step per this document: re-run the frozen configuration on Vantage's own history and
spreads (Windows VPS), then MT5 demo.
