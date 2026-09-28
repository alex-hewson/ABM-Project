"""
Order book depth profile <N(p - p_m)> and its lognormal fit (Preis et al. 2006, Fig. 2b).

No scipy is available in this environment, so the fit avoids nonlinear least squares. Instead it
uses a fact specific to the lognormal density f: ln(f(x)) + ln(x) is an exact quadratic in ln(x),
so (mu, sigma) can be read off a quadratic regression of ln(N(x)) + ln(x) against ln(x), which
numpy can do directly (no iteration). An earlier method-of-moments version (matching the
weighted mean/variance of the profile) put the fitted peak 25-50% further out than the data's
actual peak, because moments are dominated by the far tail; this regression is weighted to follow
the bulk of the distribution instead -- see docs/decisions.md, D14 for the comparison.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np


def profile_from_depth_sum(depth_sum: Dict[int, int], n_snapshots: int) -> Dict[int, float]:
    """depth_sum (as stored by run_simulation: keys are HALF-ticks from the midpoint, bids
    negative) -> {tick offset: mean resting orders at that tick}, one entry per occupied tick."""
    if n_snapshots == 0:
        return {}
    total: Dict[int, float] = {}
    for half_ticks, n in depth_sum.items():
        total[half_ticks // 2] = total.get(half_ticks // 2, 0) + n
    return {tick: n / n_snapshots for tick, n in total.items()}


def combine_sides(profile: Dict[int, float]) -> Dict[int, float]:
    """Fold the bid (negative) and ask (positive) sides onto one distance-from-midpoint axis,
    by summing the weight at +x and -x. Assumes q_provider = 0.5, so the two sides are expected
    to be symmetric (checked, not assumed blindly, by the caller comparing the two sides if it
    matters)."""
    combined: Dict[int, float] = {}
    for tick, weight in profile.items():
        x = abs(tick)
        if x == 0:
            continue
        combined[x] = combined.get(x, 0) + weight
    return combined


@dataclass
class LognormalFit:
    mu: float
    sigma: float
    total_weight: float      # sum of the weights the fit was made from (e.g. total resting orders
                             # on the side(s) fitted); used to scale the curve back up to raw counts

    def density(self, x: np.ndarray) -> np.ndarray:
        """Lognormal PDF at x (0 or negative x -> 0, not an error, since distance is positive)."""
        x = np.asarray(x, dtype=float)
        out = np.zeros_like(x)
        pos = x > 0
        out[pos] = np.exp(-((np.log(x[pos]) - self.mu) ** 2) / (2 * self.sigma ** 2)) \
            / (x[pos] * self.sigma * np.sqrt(2 * np.pi))
        return out

    def scaled_curve(self, x: np.ndarray) -> np.ndarray:
        """The fitted curve on the same scale as the original counts (1-tick bins): total_weight
        times the density, so it can be overlaid directly on a plot of the raw profile."""
        return self.total_weight * self.density(x)


def fit_lognormal(one_sided_profile: Dict[int, float]) -> LognormalFit:
    """
    Fit a lognormal distribution to a one-sided profile {distance: weight}, by weighted quadratic
    regression in log space rather than by iterative nonlinear least squares (no scipy here).

    For a lognormal density f(x; mu, sigma), ln(f(x)) + ln(x) = -(ln(x) - mu)^2 / (2 sigma^2) +
    constant -- an exact quadratic in ln(x). So fitting y = ln(N(x)) + ln(x) against z = ln(x)
    with numpy's ordinary quadratic regression recovers mu and sigma from the coefficients (the
    constant term is not needed: total_weight, the empirical sum, sets the amplitude instead).

    Weighted by weight(x)^2 (passed as weight(x)**2 to numpy, whose own `w` already weights the
    squared residual once, for an effective weight(x)^4 on the squared error): the paper specifies
    no fitting procedure, and weighting less aggressively (uniform, or by count, or matching
    moments instead of regressing) lets the noisy, low-count far tail pull the fitted peak well
    away from the data's actual peak (checked: 25-50% too far out). This heavy weighting keeps the
    fit close to the bulk of the distribution, which is what "phenomenologically described by a
    lognormal" is really claiming to match.
    """
    if not one_sided_profile:
        raise ValueError("empty profile: nothing to fit")
    x = np.array(sorted(one_sided_profile))
    w = np.array([one_sided_profile[k] for k in x], dtype=float)
    if (x <= 0).any():
        raise ValueError("profile must only contain positive distances")
    keep = w > 0                        # can't take log(0); a handful of empty far-tick bins is normal
    x, w = x[keep], w[keep]
    if len(x) < 3:
        raise ValueError("need at least 3 distinct positive-weight points to fit a quadratic")
    total = w.sum()
    if total <= 0:
        raise ValueError("total weight must be positive")

    z, y = np.log(x), np.log(w) + np.log(x)
    a, b, _ = np.polyfit(z, y, deg=2, w=w ** 2)
    if a >= 0:
        raise ValueError("fit is not peaked (quadratic coefficient >= 0); "
                         "the profile may not be unimodal enough to fit a lognormal to")

    sigma2 = -1 / (2 * a)
    mu = -b / (2 * a)
    return LognormalFit(mu=float(mu), sigma=float(np.sqrt(sigma2)), total_weight=float(total))
