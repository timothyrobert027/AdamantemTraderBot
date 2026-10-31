"""Read-only checks on the VPS before the demo bot is started. Never sends an order.

Writes ``exports/vantage_report.md`` and, with ``export``, the broker's M1 history and
symbol specification so backtests can be re-run on Vantage's own prices and spreads.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from adamantem.live.mt5_client import MT5Client, spread_stats


def run_doctor(client: MT5Client, cfg: dict, out_dir: Path, export: bool = True) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = ["# ADAMANTEM doctor - Vantage MT5 (read-only)", ""]
    client.connect()  # raises if the account is not a demo account
    acc = client.account()
    symbol = client.resolve_symbol(cfg["broker"]["symbol_pattern"], cfg["instrument"]["base_symbol"])
    offset = client.detect_server_offset()
    spec, info = client.symbol_spec()
    tick = client.tick()
    m1 = client.rates_m1(int(cfg["demo"]["history_m1_bars"]))
    stats = spread_stats(m1.tail(20 * 1380))
    lines += [
        "## Account",
        f"- Login: {client.masked_login(acc.login)} - **demo**: yes",
        f"- Server: {getattr(acc, 'server', '?')}; currency {acc.currency}; leverage 1:{acc.leverage}",
        f"- Equity {acc.equity:.2f}",
        "",
        "## Symbol",
        f"- Name: **{symbol}**; digits {info.digits}; point {info.point}",
        f"- Contract size {spec.contract_size}; tick size {spec.tick_size}; tick value {spec.tick_value}",
        f"- Volume min {spec.volume_min}, step {spec.volume_step}, max {spec.volume_max}",
        f"- Stops level {info.trade_stops_level} points; freeze level {info.trade_freeze_level}",
        f"- Filling modes flag {info.filling_mode}; swap long {info.swap_long}, short {info.swap_short}",
        f"- Server time offset vs UTC: {offset / pd.Timedelta('1h'):+.1f} h",
        f"- Current bid/ask {tick.bid} / {tick.ask} (spread {tick.ask - tick.bid:.2f})",
        "",
        "## Spread over the last ~20 trading days (from M1 bars)",
        f"- Median {stats.get('median', float('nan')):.3f}, 90th percentile "
        f"{stats.get('p90', float('nan')):.3f}, max {stats.get('max', float('nan')):.3f}",
        f"- Median by UTC hour: {stats.get('median_by_utc_hour', {})}",
        "",
        "## History",
        f"- {len(m1):,} M1 bars, {m1.index[0]} → {m1.index[-1]} (UTC)",
        "",
        "No order was sent.",
    ]
    report = out_dir / "vantage_report.md"
    report.write_text("\n".join(lines))
    if export:
        m1.to_csv(out_dir / "vantage_xauusd_m1.csv.gz", compression="gzip")
        (out_dir / "vantage_spec.json").write_text(json.dumps({
            "symbol": symbol, "contract_size": spec.contract_size, "tick_size": spec.tick_size,
            "tick_value": spec.tick_value, "volume_min": spec.volume_min,
            "volume_step": spec.volume_step, "volume_max": spec.volume_max,
            "stops_level_points": info.trade_stops_level, "digits": info.digits,
            "leverage": acc.leverage, "server_offset_hours": offset / pd.Timedelta("1h"),
            "spread": stats,
        }, indent=1, default=str))
    client.shutdown()
    print("\n".join(lines))
    return report
