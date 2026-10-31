"""Performance metrics computed only from simulated trades."""

from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from adamantem.backtest.engine import Result


def trades_frame(result: Result) -> pd.DataFrame:
    return pd.DataFrame([asdict(t) for t in result.trades])


def summarize(df: pd.DataFrame, start_equity: float) -> dict:
    if df.empty:
        return {"trades": 0}
    wins = df[df.pnl > 0]
    losses = df[df.pnl <= 0]
    equity = pd.concat([pd.Series([start_equity]), df.equity_after], ignore_index=True)
    dd = (equity.cummax() - equity) / equity.cummax()
    streak = longest = 0
    for pnl in df.pnl:
        streak = streak + 1 if pnl <= 0 else 0
        longest = max(longest, streak)
    gross_loss = -losses.pnl.sum()
    return {
        "trades": len(df),
        "win_rate": len(wins) / len(df),
        "avg_r": df.r_multiple.mean(),
        "median_r": df.r_multiple.median(),
        "profit_factor": wins.pnl.sum() / gross_loss if gross_loss > 0 else float("inf"),
        "net_pnl": df.pnl.sum(),
        "return_pct": (equity.iloc[-1] / start_equity - 1) * 100,
        "max_dd_pct": dd.max() * 100,
        "longest_losing_streak": longest,
        "avg_volume": df.volume.mean(),
        "avg_risk_pct_of_start": (df.risk_money / start_equity).mean() * 100,
    }


def breakdown(df: pd.DataFrame, by: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    g = df.groupby(by)
    return pd.DataFrame(
        {
            "trades": g.size(),
            "win_rate": g.apply(lambda x: (x.pnl > 0).mean(), include_groups=False),
            "avg_r": g.r_multiple.mean(),
            "net_pnl": g.pnl.sum(),
        }
    )
