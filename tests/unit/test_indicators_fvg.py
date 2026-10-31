import numpy as np
import pandas as pd

from adamantem.indicators.ta import atr, ema
from adamantem.strategy.fvg import detect_fvgs


def test_atr_constant_range():
    n = 30
    high = pd.Series(np.full(n, 11.0))
    low = pd.Series(np.full(n, 10.0))
    close = pd.Series(np.full(n, 10.5))
    out = atr(high, low, close, 14)
    assert out.iloc[:13].isna().all()
    assert np.allclose(out.iloc[13:], 1.0)


def test_atr_has_no_lookahead():
    rng = np.random.default_rng(0)
    c = pd.Series(100 + rng.normal(0, 1, 200).cumsum())
    h, l = c + 1, c - 1
    full = atr(h, l, c, 14)
    cut = atr(h[:120], l[:120], c[:120], 14)
    assert np.allclose(full[:120], cut, equal_nan=True)


def test_ema_matches_pandas_span():
    s = pd.Series(np.arange(50, dtype=float))
    assert np.isclose(ema(s, 10).iloc[-1], s.ewm(span=10, adjust=False).mean().iloc[-1])


def test_fvg_detection():
    #            c1    c2    c3   (bearish: c3.high < c1.low)
    high = np.array([105.0, 104.0, 99.0, 99.5, 103.0])
    low = np.array([101.0, 98.0, 97.0, 96.0, 99.6])
    atr_ = np.full(5, 2.0)
    bear, bull = detect_fvgs(high, low, atr_, 0.15)
    assert bear[2] is not None and (bear[2].bottom, bear[2].top) == (99.0, 101.0)
    assert bear[3] is None or bear[3].index == 3
    # bullish at index 4: low[4]=99.6 > high[2]=99.0
    assert bull[4] is not None and (bull[4].bottom, bull[4].top) == (99.0, 99.6)


def test_fvg_min_size_filters_noise():
    high = np.array([105.0, 104.0, 100.95])
    low = np.array([101.0, 98.0, 97.0])
    bear, _ = detect_fvgs(high, low, np.full(3, 2.0), 0.15)  # gap 0.05 < 0.30
    assert bear[2] is None
