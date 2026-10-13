"""
How a quantity behaves around a shock: its level before, how far the shock moved it, and how much of
that move is undone afterwards.

Meant for the series recorded by run_simulation(shock=..., record_sides=True): the mid-price, the
spread, or the number of orders on one side of the book. A single run is noisy, so the usual order is

    window()            cut the same stretch around the shock out of every run
    mean_response()     average those stretches over runs
    recovered_fraction(), time_to_recover()    read numbers off the averaged curve

In a window, index `before` is the shock step itself; the `before` entries ahead of it are the
steps leading up to the shock.
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np


def window(series: Sequence[float], shock_step: int, before: int, after: int) -> np.ndarray:
    """The part of series from `before` steps ahead of the shock to `after` steps past it
    (before + 1 + after values). None entries (no midpoint) become NaN."""
    if shock_step - before < 0 or shock_step + after >= len(series):
        raise ValueError("the window runs off the end of the series")
    values = [np.nan if v is None else v for v in series[shock_step - before:shock_step + after + 1]]
    return np.asarray(values, dtype=float)


def mean_response(windows: Sequence[np.ndarray]) -> np.ndarray:
    """Average of many runs' windows, step by step. NaN entries are left out of the average."""
    return np.nanmean(np.asarray(windows, dtype=float), axis=0)


def pre_shock_level(response: np.ndarray, before: int) -> float:
    """Mean of the steps leading up to the shock: the level to recover to."""
    return float(np.mean(response[:before]))


def impact(response: np.ndarray, before: int) -> float:
    """How far the shock moved the quantity: its value at the shock step minus the level before.
    Negative for a fall."""
    return float(response[before] - pre_shock_level(response, before))


def recovered_fraction(response: np.ndarray, before: int, tail: int) -> float:
    """Share of the shock's move that has been undone by the end of the window.

    1 = back at the level before the shock, 0 = still where the shock left it, above 1 = overshot.
    The end level is the mean of the last `tail` steps. NaN if the shock did not move the quantity."""
    hit = impact(response, before)
    if hit == 0:
        return float("nan")
    still_displaced = float(np.mean(response[-tail:])) - pre_shock_level(response, before)
    return 1.0 - still_displaced / hit


def time_to_recover(response: np.ndarray, before: int, fraction: float = 0.5) -> Optional[int]:
    """Steps after the shock until `fraction` of its move has been undone for the first time
    (fraction = 0.5 gives a half-life). None if that never happens inside the window."""
    hit = impact(response, before)
    if hit == 0:
        return None
    displaced = np.abs(response[before:] - pre_shock_level(response, before))
    reached = np.nonzero(displaced <= (1.0 - fraction) * abs(hit))[0]
    return int(reached[0]) if len(reached) else None
