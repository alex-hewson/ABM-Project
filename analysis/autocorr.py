"""
Autocorrelation of price changes: does one change tell anything about the next?

Two versions are measured, on the price change over a fixed interval (e.g. every 50 steps):

    signed changes      Real markets: close to zero at every lag (a rise says nothing about whether
                        the next change is a rise or a fall). Negative values mean the price tends to
                        turn back (anti-persistent); positive values mean it tends to carry on (a trend).
    absolute changes    Real markets: positive, and slow to die away. Large changes tend to follow
                        large changes, of either sign. This is "volatility clustering".

The intervals do not overlap, so neighbouring changes share no steps.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np


def interval_changes(prices: Sequence[float], interval: int) -> np.ndarray:
    """Price change over each block of `interval` steps: p(interval) - p(0), p(2*interval) - p(interval), ..."""
    if interval < 1:
        raise ValueError("interval must be at least 1")
    p = np.asarray(prices, dtype=float)[::interval]
    return np.diff(p)


def autocorrelation(x: Sequence[float], max_lag: int) -> np.ndarray:
    """Sample autocorrelation of x at lags 1 to max_lag: how alike x(t) and x(t + lag) are, from
    -1 (opposite) through 0 (unrelated) to 1 (the same). The mean of x is removed first.
    Returns NaN at every lag if x never varies."""
    x = np.asarray(x, dtype=float)
    if max_lag < 1 or max_lag >= len(x):
        raise ValueError(f"max_lag must be between 1 and {len(x) - 1} for a series of {len(x)} values")
    d = x - x.mean()
    variance = float(np.dot(d, d))
    if variance == 0:
        return np.full(max_lag, np.nan)
    return np.array([np.dot(d[:-lag], d[lag:]) / variance for lag in range(1, max_lag + 1)])


def change_autocorrelations(prices: Sequence[float], interval: int, max_lag: int) -> dict:
    """Both autocorrelations for one price series: {"signed": ..., "absolute": ...}, each an array
    over lags 1 to max_lag, measured in intervals (lag 3 = 3 * interval steps apart)."""
    changes = interval_changes(prices, interval)
    return {"signed": autocorrelation(changes, max_lag),
            "absolute": autocorrelation(np.abs(changes), max_lag)}
