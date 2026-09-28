"""
Turn a simulation result into a per-step price series, under several definitions of "price".

Preis et al. (2006) don't say whether their price is the mid-price or a trade price, and (with
our discrete steps) the choice noticeably changes H(delta tau) at short lags. So the analysis
keeps every candidate and the choice is made explicitly later. See docs/decisions.md.

    mid     (best bid + best ask) / 2 at the end of the step
    last    price of the last trade in the step
    first   price of the first trade in the step
    median  median trade price in the step (upper median if the count is even)
    mean    mean trade price in the step

Steps with no trade carry the previous trade price forward; any steps before the very first
trade take that first trade's price.
"""

from __future__ import annotations

import numpy as np

from abm.simulation import SimulationResult

PRICE_DEFINITIONS = ("mid", "last", "first", "median", "mean")


def forward_fill(values: np.ndarray) -> np.ndarray:
    """Replace each NaN by the most recent earlier real value (leading NaNs take the first real value)."""
    values = np.asarray(values, dtype=float)
    real = ~np.isnan(values)
    if not real.any():
        raise ValueError("no trades at all, so no trade-price series can be built")
    idx = np.where(real, np.arange(len(values)), 0)
    np.maximum.accumulate(idx, out=idx)
    filled = values[idx]
    first_real = int(np.argmax(real))
    filled[:first_real] = values[first_real]
    return filled


def price_series(result: SimulationResult, kind: str) -> np.ndarray:
    """One price per step, as a float array, under the named definition."""
    if kind == "mid":
        if any(p is None for p in result.mid_price_series):
            raise ValueError("the book went one-sided (mid-price undefined) at some step; "
                             "a gap-free series is needed")
        return np.array(result.mid_price_series, dtype=float)
    if kind not in PRICE_DEFINITIONS:
        raise ValueError(f"unknown price definition {kind!r}; choose from {PRICE_DEFINITIONS}")
    if kind not in result.trade_price_steps:
        raise ValueError("this result has no trade prices; run_simulation needs record_trade_prices=True")
    return forward_fill(result.trade_price_steps[kind])
