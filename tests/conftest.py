from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def cfg():
    return yaml.safe_load((ROOT / "config" / "default.yaml").read_text())


def synthetic_m1(days: int = 40, seed: int = 7, start: str = "2024-01-01") -> pd.DataFrame:
    """Random-walk M1 bid/ask bars on weekdays. For plumbing tests only, never for results."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=days * 1440, freq="1min", tz="UTC")
    idx = idx[(idx.day_of_week < 5) & ~idx.hour.isin([21])]
    steps = rng.standard_t(4, len(idx)) * 0.35
    mid = 2000 + np.cumsum(steps)
    noise = np.abs(rng.normal(0, 0.25, (len(idx), 2)))
    bo = np.r_[mid[0], mid[:-1]]
    bc = mid
    bh = np.maximum(bo, bc) + noise[:, 0]
    bl = np.minimum(bo, bc) - noise[:, 1]
    spr = 0.15 + np.abs(rng.normal(0, 0.03, len(idx)))
    return pd.DataFrame(
        {
            "bid_open": bo, "bid_high": bh, "bid_low": bl, "bid_close": bc,
            "ask_open": bo + spr, "ask_high": bh + spr, "ask_low": bl + spr, "ask_close": bc + spr,
            "volume": 1.0,
        },
        index=pd.DatetimeIndex(idx, name="time"),
    )


@pytest.fixture(scope="session")
def m1():
    return synthetic_m1()
