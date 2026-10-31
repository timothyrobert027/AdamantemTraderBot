# Scalping hypothesis S2 + third test of the swing configuration

Generated 2026-10-31 15:43 UTC. Start equity $500. HistData M1 bid + assumed spread $0.25 (not Vantage data). Everything pre-registered in docs/SCALPING_S2.md.

## S2 selected: **none** — verdict on 2016-2020: **NO CANDIDATE**

## Validated swing configuration on 2016-2020: **FAILED**
| Criterion | Value | Pass |
|---|---|---|
| Trades ≥ 30 | 14 | NO |
| Average R ≥ +0.10 | -0.46 | NO |
| Profit factor ≥ 1.15 | 0.38 | NO |
| No kill switch | none | yes |

## Data
- dev: 1,375,942 M1 rows, 2021-11-01 00:00:00+00:00 → 2025-10-31 20:59:00+00:00; trading from 2021-11-01; 1040 trading days
- validation: 1,855,243 M1 rows, 2015-10-01 00:00:00+00:00 → 2020-12-31 21:58:00+00:00; trading from 2016-01-01; 1298 trading days

## Funnel (standard profile, base spread)

| period     | config            |   arms/day |   breaks/day |   orders/day |   fills/day | top rejections (per day)                                                        |
|:-----------|:------------------|-----------:|-------------:|-------------:|------------:|:--------------------------------------------------------------------------------|
| dev        | S2-A              |      41.68 |        18.9  |         0.57 |        0.32 | session 8.65, kill_switch 7.67, spread_vs_atr 0.58, trend_filter 0.53           |
| dev        | S2-B              |      16.98 |         8.82 |         0.31 |        0.18 | session 3.27, kill_switch 2.57, spread_vs_atr 0.87, trend_filter 0.67           |
| dev        | S2-C              |       0    |         2.19 |         0.17 |        0.11 | kill_switch 1.55, trend_filter 0.18, spread_vs_atr 0.14, volatility_regime 0.13 |
| dev        | S2-AC             |      41.68 |        21.09 |         0.59 |        0.34 | kill_switch 9.49, session 8.65, spread_vs_atr 0.67, trend_filter 0.60           |
| dev        | SWING (validated) |       2.39 |         1.86 |         0.1  |        0.06 | spread_vs_atr 0.75, session 0.64, volatility_regime 0.27, trend_filter 0.08     |
| validation | SWING (validated) |       2.5  |         1.99 |         0.02 |        0.01 | spread_vs_atr 0.94, session 0.73, volatility_regime 0.29, trend_filter 0.02     |

## All runs

| period | config | spread | profile | trades | trades_per_day | win_rate | avg_r | profit_factor | return_pct | monthly_growth_pct | max_dd_pct | longest_losing_streak | halted |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dev | S2-A | base | standard | 335 | 0.32 | 0.41 | -0.04 | 0.94 | -9.55 | -0.21 | 15.64 | 9.00 | 2022-10-21 |
| dev | S2-A | base | aggressive | 137 | 0.13 | 0.42 | -0.03 | 0.91 | -16.82 | -0.38 | 31.20 | 6.00 | 2022-05-02 |
| dev | S2-A | base | max | 85 | 0.08 | 0.42 | -0.02 | 0.92 | -20.02 | -0.46 | 40.57 | 6.00 | 2022-03-22 |
| dev | S2-A | stress_+0.20 | standard | 59 | 0.06 | 0.37 | -0.22 | 0.72 | -10.00 | -0.22 | 16.09 | 5.00 | 2024-04-19 |
| dev | S2-A | stress_+0.20 | aggressive | 46 | 0.04 | 0.37 | -0.20 | 0.66 | -22.32 | -0.52 | 30.80 | 5.00 | 2023-04-27 |
| dev | S2-A | stress_+0.20 | max | 37 | 0.04 | 0.35 | -0.19 | 0.66 | -30.43 | -0.75 | 40.60 | 4.00 | 2022-11-03 |
| dev | S2-B | base | standard | 185 | 0.18 | 0.42 | -0.07 | 0.88 | -10.20 | -0.22 | 15.30 | 9.00 | 2024-01-11 |
| dev | S2-B | base | aggressive | 169 | 0.16 | 0.44 | -0.03 | 0.92 | -17.24 | -0.39 | 31.10 | 9.00 | 2023-10-12 |
| dev | S2-B | base | max | 32 | 0.03 | 0.38 | -0.12 | 0.79 | -20.18 | -0.47 | 40.83 | 9.00 | 2022-04-22 |
| dev | S2-B | stress_+0.20 | standard | 70 | 0.07 | 0.41 | -0.11 | 0.71 | -11.55 | -0.26 | 15.78 | 6.00 | 2025-04-21 |
| dev | S2-B | stress_+0.20 | aggressive | 122 | 0.12 | 0.43 | -0.05 | 0.90 | -14.21 | -0.32 | 25.20 | 6.00 | - |
| dev | S2-B | stress_+0.20 | max | 92 | 0.09 | 0.42 | -0.07 | 0.83 | -33.70 | -0.85 | 41.58 | 6.00 | 2025-06-27 |
| dev | S2-C | base | standard | 112 | 0.11 | 0.37 | -0.12 | 0.80 | -10.19 | -0.22 | 15.09 | 13.00 | 2022-12-21 |
| dev | S2-C | base | aggressive | 99 | 0.10 | 0.37 | -0.10 | 0.86 | -20.92 | -0.49 | 30.79 | 13.00 | 2022-10-24 |
| dev | S2-C | base | max | 90 | 0.09 | 0.40 | -0.04 | 0.91 | -23.48 | -0.56 | 40.38 | 9.00 | 2022-10-06 |
| dev | S2-C | stress_+0.20 | standard | 29 | 0.03 | 0.17 | -0.57 | 0.34 | -15.12 | -0.34 | 15.12 | 7.00 | 2024-05-31 |
| dev | S2-C | stress_+0.20 | aggressive | 22 | 0.02 | 0.14 | -0.63 | 0.20 | -30.14 | -0.74 | 30.14 | 6.00 | 2024-04-19 |
| dev | S2-C | stress_+0.20 | max | 20 | 0.02 | 0.15 | -0.59 | 0.25 | -41.76 | -1.12 | 41.76 | 5.00 | 2024-04-12 |
| dev | S2-AC | base | standard | 355 | 0.34 | 0.41 | -0.03 | 0.96 | -5.58 | -0.12 | 15.11 | 10.00 | 2022-09-30 |
| dev | S2-AC | base | aggressive | 108 | 0.10 | 0.42 | -0.04 | 0.93 | -11.91 | -0.26 | 31.65 | 7.00 | 2022-03-28 |
| dev | S2-AC | base | max | 57 | 0.05 | 0.44 | -0.02 | 0.93 | -11.65 | -0.26 | 40.03 | 6.00 | 2022-02-02 |
| dev | S2-AC | stress_+0.20 | standard | 44 | 0.04 | 0.27 | -0.35 | 0.60 | -11.36 | -0.25 | 15.07 | 8.00 | 2022-11-03 |
| dev | S2-AC | stress_+0.20 | aggressive | 45 | 0.04 | 0.29 | -0.31 | 0.51 | -29.52 | -0.73 | 30.70 | 5.00 | 2022-11-03 |
| dev | S2-AC | stress_+0.20 | max | 28 | 0.03 | 0.29 | -0.36 | 0.46 | -38.78 | -1.02 | 41.77 | 5.00 | 2022-05-06 |
| dev | SWING (validated) | base | standard | 58 | 0.06 | 0.47 | 0.29 | 1.51 | 21.50 | 0.41 | 8.02 | 5.00 | - |
| dev | SWING (validated) | base | aggressive | 58 | 0.06 | 0.47 | 0.29 | 1.38 | 32.14 | 0.58 | 12.90 | 5.00 | - |
| dev | SWING (validated) | base | max | 58 | 0.06 | 0.47 | 0.29 | 1.51 | 93.10 | 1.38 | 18.31 | 5.00 | - |
| dev | SWING (validated) | stress_+0.20 | standard | 10 | 0.01 | 0.30 | 0.01 | 1.05 | 0.61 | 0.01 | 10.54 | 5.00 | - |
| dev | SWING (validated) | stress_+0.20 | aggressive | 10 | 0.01 | 0.30 | 0.01 | 0.81 | -3.18 | -0.07 | 13.32 | 5.00 | - |
| dev | SWING (validated) | stress_+0.20 | max | 10 | 0.01 | 0.30 | 0.01 | 0.98 | -0.46 | -0.01 | 14.69 | 5.00 | - |
| validation | SWING (validated) | base | standard | 14 | 0.01 | 0.29 | -0.46 | 0.38 | -6.26 | -0.11 | 6.26 | 4.00 | - |
| validation | SWING (validated) | base | aggressive | 14 | 0.01 | 0.29 | -0.46 | 0.35 | -14.47 | -0.26 | 14.47 | 4.00 | - |
| validation | SWING (validated) | base | max | 14 | 0.01 | 0.29 | -0.46 | 0.30 | -27.73 | -0.54 | 27.73 | 4.00 | - |
| validation | SWING (validated) | stress_+0.20 | standard | 0 | 0.00 | nan | nan | nan | nan | 0.00 | nan | nan | - |
| validation | SWING (validated) | stress_+0.20 | aggressive | 0 | 0.00 | nan | nan | nan | nan | 0.00 | nan | nan | - |
| validation | SWING (validated) | stress_+0.20 | max | 0 | 0.00 | nan | nan | nan | nan | 0.00 | nan | nan | - |

### dev · S2-A · standard · base

By setup context:

| context   |   trades |   win_rate |   avg_r |   net_pnl |
|:----------|---------:|-----------:|--------:|----------:|
| TREND     |      335 |      0.409 |  -0.038 |   -47.756 |

By year:

|   year |   trades |   win_rate |   avg_r |   net_pnl |
|-------:|---------:|-----------:|--------:|----------:|
|   2021 |       27 |      0.556 |   0.229 |    18.128 |
|   2022 |      308 |      0.396 |  -0.062 |   -65.884 |

By exit:

| exit_reason   |   trades |   win_rate |   avg_r |   net_pnl |
|:--------------|---------:|-----------:|--------:|----------:|
| session       |       33 |      0.667 |   0.304 |    54.368 |
| stop          |      187 |      0     |  -1     |  -738.135 |
| target        |      114 |      1     |   1.435 |   631.468 |
| time          |        1 |      1     |   0.575 |     4.543 |


### dev · S2-B · standard · base

By setup context:

| context   |   trades |   win_rate |   avg_r |   net_pnl |
|:----------|---------:|-----------:|--------:|----------:|
| H1        |       34 |      0.471 |   0.111 |    10.137 |
| H4        |        6 |      0.5   |   0.034 |     1.223 |
| H4+H1     |        5 |      0     |  -0.901 |   -15.917 |
| M15       |      140 |      0.414 |  -0.088 |   -46.428 |

By year:

|   year |   trades |   win_rate |   avg_r |   net_pnl |
|-------:|---------:|-----------:|--------:|----------:|
|   2021 |        6 |      0.5   |   0.129 |     3.056 |
|   2022 |      107 |      0.439 |   0.016 |    11.437 |
|   2023 |       69 |      0.391 |  -0.179 |   -51.66  |
|   2024 |        3 |      0     |  -1     |   -13.818 |

By exit:

| exit_reason   |   trades |   win_rate |   avg_r |   net_pnl |
|:--------------|---------:|-----------:|--------:|----------:|
| session       |       30 |        0.6 |   0.077 |     2.923 |
| stop          |       95 |        0   |  -1.034 |  -393.16  |
| target        |       58 |        1   |   1.433 |   338.391 |
| time          |        2 |        0.5 |  -0.021 |     0.861 |


### dev · S2-C · standard · base

By setup context:

| context   |   trades |   win_rate |   avg_r |   net_pnl |
|:----------|---------:|-----------:|--------:|----------:|
| ORB       |      112 |      0.366 |  -0.118 |   -50.927 |

By year:

|   year |   trades |   win_rate |   avg_r |   net_pnl |
|-------:|---------:|-----------:|--------:|----------:|
|   2021 |       10 |      0.6   |   0.121 |     7.771 |
|   2022 |      102 |      0.343 |  -0.142 |   -58.698 |

By exit:

| exit_reason   |   trades |   win_rate |   avg_r |   net_pnl |
|:--------------|---------:|-----------:|--------:|----------:|
| session       |        7 |      0.571 |   0.106 |     3.38  |
| stop          |       67 |      0     |  -1     |  -253.144 |
| target        |       37 |      1     |   1.434 |   198.957 |
| time          |        1 |      0     |  -0.027 |    -0.12  |


### dev · S2-AC · standard · base

By setup context:

| context   |   trades |   win_rate |   avg_r |   net_pnl |
|:----------|---------:|-----------:|--------:|----------:|
| ORB       |       58 |      0.397 |  -0.047 |   -14.872 |
| TREND     |      297 |      0.418 |  -0.022 |   -13.021 |

By year:

|   year |   trades |   win_rate |   avg_r |   net_pnl |
|-------:|---------:|-----------:|--------:|----------:|
|   2021 |       35 |      0.571 |   0.237 |    28.947 |
|   2022 |      320 |      0.397 |  -0.055 |   -56.84  |

By exit:

| exit_reason   |   trades |   win_rate |   avg_r |   net_pnl |
|:--------------|---------:|-----------:|--------:|----------:|
| session       |       39 |      0.641 |   0.273 |    57.458 |
| stop          |      194 |      0     |  -1     |  -775.591 |
| target        |      121 |      1     |   1.434 |   685.697 |
| time          |        1 |      1     |   0.575 |     4.543 |


### dev · SWING (validated) · standard · base

By setup context:

| context   |   trades |   win_rate |   avg_r |   net_pnl |
|:----------|---------:|-----------:|--------:|----------:|
| H1        |       39 |      0.513 |   0.367 |    77.928 |
| H4        |       10 |      0.2   |  -0.256 |    -1.65  |
| H4+H1     |        9 |      0.556 |   0.569 |    31.208 |

By year:

|   year |   trades |   win_rate |   avg_r |   net_pnl |
|-------:|---------:|-----------:|--------:|----------:|
|   2022 |        5 |      0.6   |   0.273 |     9.467 |
|   2024 |       16 |      0.438 |   0.234 |    39.956 |
|   2025 |       37 |      0.459 |   0.318 |    58.063 |

By exit:

| exit_reason   |   trades |   win_rate |   avg_r |   net_pnl |
|:--------------|---------:|-----------:|--------:|----------:|
| session       |       10 |        0.8 |   0.557 |    34.978 |
| stop          |       29 |        0   |  -1     |  -198.672 |
| target        |       15 |        1   |   2.483 |   247.416 |
| time          |        4 |        1   |   0.761 |    23.764 |


### validation · SWING (validated) · standard · base

By setup context:

| context   |   trades |   win_rate |   avg_r |   net_pnl |
|:----------|---------:|-----------:|--------:|----------:|
| H1        |       11 |      0.273 |  -0.528 |   -24.768 |
| H4        |        1 |      1     |   1.389 |     7.651 |
| H4+H1     |        2 |      0     |  -1     |   -14.202 |

By year:

|   year |   trades |   win_rate |   avg_r |   net_pnl |
|-------:|---------:|-----------:|--------:|----------:|
|   2020 |       14 |      0.286 |  -0.458 |   -31.319 |

By exit:

| exit_reason   |   trades |   win_rate |   avg_r |   net_pnl |
|:--------------|---------:|-----------:|--------:|----------:|
| session       |        4 |          1 |   0.896 |    19.137 |
| stop          |       10 |          0 |  -1     |   -50.455 |
