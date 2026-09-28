"""
Return (price-increment) distributions P(Delta p) for a lag Delta tau, as in
Figs. 2d, 3b/3d and 4b of Preis et al. (2006).

The paper works with price increments p(t + tau) - p(t) directly (not log
returns), so that is what is counted here. Counts, not normalised densities,
are returned so that results from many runs can be summed before normalising.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np


def return_counts(prices: Sequence[float], tau: int, bin_edges: Sequence[float],
                  absolute: bool = False) -> np.ndarray:
    """
    Histogram counts of price increments p(t+tau) - p(t) over all valid t.

    absolute=True counts |increment| instead (for log-log tail plots).
    Increments outside bin_edges are not counted.
    """
    p = np.asarray(prices, dtype=float)
    diffs = p[tau:] - p[:-tau]
    if absolute:
        diffs = np.abs(diffs)
    counts, _ = np.histogram(diffs, bins=bin_edges)
    return counts


def counts_to_density(counts: np.ndarray, bin_edges: Sequence[float]) -> np.ndarray:
    """Normalise histogram counts to a probability density (integrates to the
    fraction of increments that fell inside the bins)."""
    edges = np.asarray(bin_edges, dtype=float)
    return counts / (counts.sum() * np.diff(edges))
