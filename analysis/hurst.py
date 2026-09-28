"""
Hurst exponent estimation, following Preis et al. (2006):

    <(Delta p)^2>^(1/2) (Delta_tau) ~ Delta_tau ^ H

i.e. the RMS of price changes over lag Delta_tau scales as Delta_tau^H.
H(Delta_tau) is reported as a curve (local slope in log-log space at each
lag), not a single global fit -- that's what produces the characteristic
shape in the paper's Fig 2c (anti-persistent at short lags, rising to 0.5
at long lags).
"""

from __future__ import annotations

import math
import random
from typing import List, Sequence, Tuple

import numpy as np


def rms_price_change(prices: Sequence[float], tau: int) -> float:
    """
    RMS of price changes p(t+tau) - p(t), averaged over all valid t in
    the series. This is <(Delta p)^2>^(1/2) at a single lag tau.
    """
    diffs = [prices[t + tau] - prices[t] for t in range(len(prices) - tau)]
    mean_sq = sum(d * d for d in diffs) / len(diffs)
    return math.sqrt(mean_sq)


def log_spaced_taus(min_tau: int, max_tau: int, n_points: int) -> List[int]:
    """
    Lags spaced evenly in log-space rather than linear space. This matters
    because H(Delta_tau) is plotted on a log-x axis (paper's Fig 2c uses
    the range 10^1 to 10^5) -- linearly spaced taus would crowd all your
    points at the low end and waste most of them past tau=10000.
    Deduplicated and sorted, since rounding can collide at the low end.
    """
    log_min, log_max = math.log10(min_tau), math.log10(max_tau)
    raw = [10 ** (log_min + i * (log_max - log_min) / (n_points - 1)) for i in range(n_points)]
    taus = sorted(set(int(round(t)) for t in raw if t >= 1))
    return taus


def hurst_curve(prices: Sequence[float], min_tau: int, max_tau: int, n_points: int = 30) -> Tuple[List[int], List[float]]:
    """
    Compute H(Delta_tau) as a curve: for each lag tau in a log-spaced
    range, estimate the LOCAL slope of log(RMS) vs log(tau) using the
    neighboring points (centered finite difference), rather than fitting
    one global H across the whole range. This is what lets H vary with
    tau the way it does in the paper's Fig 2c, instead of collapsing to
    one number.

    Returns (taus_used, H_values) -- one fewer point than the input tau
    list at each end, since the centered difference needs a neighbor on
    both sides.
    """
    taus = log_spaced_taus(min_tau, max_tau, n_points)
    max_valid_tau = len(prices) - 2   # need at least 2 points left for a diff
    taus = [t for t in taus if t <= max_valid_tau]

    log_tau = [math.log10(t) for t in taus]
    log_rms = [math.log10(rms_price_change(prices, t)) for t in taus]

    taus_out: List[int] = []
    h_out: List[float] = []
    for i in range(1, len(taus) - 1):
        slope = (log_rms[i + 1] - log_rms[i - 1]) / (log_tau[i + 1] - log_tau[i - 1])
        taus_out.append(taus[i])
        h_out.append(slope)

    return taus_out, h_out


# ---------------------------------------------------------------------- #
# Two-stage version: store RMS per lag, derive H later
#
# Storing the RMS price change at a dense set of lags (instead of finished H
# values) lets H be recomputed at plot time -- with different lag spacing, or
# for a different price definition -- without re-simulating.
# ---------------------------------------------------------------------- #

def rms_at_lags(prices: Sequence[float], taus: Sequence[int]) -> np.ndarray:
    """RMS of p(t+tau) - p(t) over all valid t, for each lag in taus (numpy; same values as
    rms_price_change, but fast enough for 10^6-step series)."""
    p = np.asarray(prices, dtype=float)
    return np.array([np.sqrt(np.mean((p[tau:] - p[:-tau]) ** 2)) for tau in taus])


def local_slopes(taus: Sequence[float], values: Sequence[float]) -> np.ndarray:
    """d ln(values) / d ln(taus) at every lag: the centred difference between neighbouring lags
    inside the range (as hurst_curve does), and a one-sided difference at the first and last lag,
    so H is defined over the whole range instead of losing an end point on each side."""
    x = np.log(np.asarray(taus, dtype=float))
    y = np.log(np.asarray(values, dtype=float))
    slopes = np.empty_like(y)
    slopes[1:-1] = (y[2:] - y[:-2]) / (x[2:] - x[:-2])
    slopes[0] = (y[1] - y[0]) / (x[1] - x[0])
    slopes[-1] = (y[-1] - y[-2]) / (x[-1] - x[-2])
    return slopes


# ---------------------------------------------------------------------- #
# Validation against a synthetic random walk (known H = 0.5)
# ---------------------------------------------------------------------- #

def synthetic_random_walk(n_steps: int, seed: int = 0) -> List[float]:
    """A plain random walk: cumulative sum of IID +-1 steps. This has a
    known, exact Hurst exponent of 0.5 at every lag -- the one case where
    we know the right answer in advance, so it's the natural thing to
    validate the estimator against before trusting it on simulated data."""
    rng = random.Random(seed)
    price = 0.0
    series = [price]
    for _ in range(n_steps):
        price += 1.0 if rng.random() < 0.5 else -1.0
        series.append(price)
    return series


if __name__ == "__main__":
    print("Validating Hurst estimator against a synthetic random walk (expect H ~ 0.5)...")
    walk = synthetic_random_walk(n_steps=200_000, seed=1)
    taus, hs = hurst_curve(walk, min_tau=10, max_tau=20_000, n_points=25)
    for t, h in zip(taus, hs):
        print(f"  tau={t:>6}  H={h:.3f}")

    mean_h = sum(hs) / len(hs)
    print(f"\nmean H across all lags: {mean_h:.3f} (expect close to 0.500)")
