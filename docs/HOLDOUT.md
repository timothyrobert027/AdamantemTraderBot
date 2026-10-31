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
