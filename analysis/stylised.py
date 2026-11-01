"""
Statistics of a market in trade time, computed the same way for the model and for real data
(docs/decisions.md, D37), so that any difference between them comes from the markets, not the code.

The input is a list of segments: stretches with no gap inside them (one model run, or one trading
session of real data). Changes and autocorrelations are taken within a segment, never across a gap.
Each segment is a dict of arrays with one entry per trade, in order:

    trade       the trade price, in ticks
    mid         the mid-price just before the trade, in ticks
    spread      the spread just before the trade, in ticks
    bid_size    units resting at the best bid just before the trade
    ask_size    units resting at the best ask just before the trade
    size        the trade's size in units (optional)

Time is counted in trades: a lag of 10 is ten trades later.
"""

from __future__ import annotations

from typing import Dict, List, Sequence

import numpy as np

from analysis.autocorr import change_autocorrelations
from analysis.hurst import local_slopes, log_spaced_taus

LAGS = np.array(log_spaced_taus(1, 20_000, 40))        # lags for the RMS change and H, in trades
KURTOSIS_LAGS = (1, 10, 100, 1000)
TAIL_LAGS = (10, 100, 1000)
TAIL_LEVELS = np.logspace(-1, np.log10(30), 40)        # |change| in units of its standard deviation
AUTOCORR = {1: 20, 100: 50}                            # interval in trades: number of lags
PRICES = ("trade", "mid")


def changes(segments: Sequence[Dict[str, np.ndarray]], kind: str, lag: int) -> np.ndarray:
    """Every change over `lag` trades, from every segment long enough (overlapping, as for H)."""
    parts = [s[kind][lag:] - s[kind][:-lag] for s in segments if len(s[kind]) > lag]
    return np.concatenate(parts) if parts else np.empty(0)


def kurtosis(x: np.ndarray) -> float:
    """Fourth moment over the squared second, about the mean: 3 for a normal distribution."""
    if len(x) < 4:
        return float("nan")
    d = x - x.mean()
    m2 = np.mean(d ** 2)
    return float(np.mean(d ** 4) / m2 ** 2) if m2 > 0 else float("nan")


def tail(x: np.ndarray) -> np.ndarray:
    """Share of |change| at or above each of TAIL_LEVELS standard deviations."""
    if len(x) == 0 or x.std() == 0:
        return np.full(len(TAIL_LEVELS), np.nan)
    sd = x.std()
    a = np.sort(np.abs(x - x.mean()) / sd)
    return 1.0 - np.searchsorted(a, TAIL_LEVELS, side="left") / len(a)


def mean_autocorrelation(segments, kind: str, interval: int, n_lags: int) -> Dict[str, np.ndarray]:
    """Autocorrelation of the signed and absolute changes over `interval` trades at lags 1 to n_lags,
    computed in each segment and averaged, weighted by the number of changes in it."""
    sums = {"signed": np.zeros(n_lags), "absolute": np.zeros(n_lags)}
    weight = 0
    for s in segments:
        n_changes = len(s[kind]) // interval - 1
        if n_changes <= 4 * n_lags:                  # too short for this many lags
            continue
        ac = change_autocorrelations(s[kind], interval, n_lags)
        for name in sums:
            sums[name] += np.nan_to_num(ac[name]) * n_changes
        weight += n_changes
    return {name: (total / weight if weight else np.full(n_lags, np.nan)) for name, total in sums.items()}


def stylised_facts(segments: Sequence[Dict[str, np.ndarray]]) -> dict:
    """All the statistics, as a dict of numbers and small arrays (never the series themselves)."""
    out: dict = {"n_trades": int(sum(len(s["trade"]) for s in segments)), "n_segments": len(segments),
                 "lags": LAGS, "tail_levels": TAIL_LEVELS}
    for kind in PRICES:
        rms = np.array([np.sqrt(np.mean(c ** 2)) if len(c := changes(segments, kind, lag)) else np.nan
                        for lag in LAGS])
        ok = np.isfinite(rms) & (rms > 0)
        hurst = np.full(len(LAGS), np.nan)
        if ok.sum() >= 2:
            hurst[ok] = local_slopes(LAGS[ok], rms[ok])
        out[kind] = {
            "rms": rms,
            "hurst": hurst,
            "kurtosis": {lag: kurtosis(changes(segments, kind, lag)) for lag in KURTOSIS_LAGS},
            "tail": {lag: tail(changes(segments, kind, lag)) for lag in TAIL_LAGS},
            "autocorr": {interval: mean_autocorrelation(segments, kind, interval, n)
                         for interval, n in AUTOCORR.items()},
            "zero_steps": float(np.mean(changes(segments, kind, 1) == 0)),     # share of trades with no price change
        }
    spread = np.concatenate([s["spread"] for s in segments])
    spread = spread[np.isfinite(spread)]
    ticks = np.clip(np.round(spread).astype(int), 0, 4)
    out["spread"] = {"mean": float(spread.mean()), "shares": [float(np.mean(ticks == k)) for k in range(5)]}
    best = np.concatenate([np.concatenate([s["bid_size"], s["ask_size"]]) for s in segments])
    best = best[np.isfinite(best)]
    out["best_size"] = {"mean": float(best.mean()),
                        "quantiles": {q: float(np.percentile(best, q)) for q in (10, 50, 90, 99)}}
    if all("size" in s for s in segments):
        sizes = np.concatenate([s["size"] for s in segments])
        sizes = sizes[np.isfinite(sizes)]
        out["trade_size"] = {"mean": float(sizes.mean()), "median": float(np.median(sizes)),
                             "per_best_size": float(np.median(sizes) / np.median(best))}
    return out


def summary_rows(facts: dict) -> List[tuple]:
    """(label, value) pairs for a side-by-side table."""
    t = facts["trade"]
    rows = [("trades", f"{facts['n_trades']:,}"),
            ("trades with no price change", f"{t['zero_steps']:.0%}"),
            ("mean spread (ticks)", f"{facts['spread']['mean']:.2f}"),
            ("spread of 1 tick", f"{facts['spread']['shares'][1]:.0%}"),
            ("median units at best price", f"{facts['best_size']['quantiles'][50]:g}")]
    if "trade_size" in facts:
        rows.append(("median trade / median best size", f"{facts['trade_size']['per_best_size']:.3f}"))
    for lag in KURTOSIS_LAGS:
        rows.append((f"kurtosis, {lag}-trade changes", f"{t['kurtosis'][lag]:.1f}"))
    i = list(LAGS).index(min(LAGS, key=lambda x: abs(x - 1000)))
    j = list(LAGS).index(min(LAGS, key=lambda x: abs(x - 10)))
    rows += [("H at 10 trades", f"{t['hurst'][j]:.2f}"), ("H at 1000 trades", f"{t['hurst'][i]:.2f}"),
             ("autocorr. of trade-to-trade changes, lag 1", f"{t['autocorr'][1]['signed'][0]:+.2f}"),
             ("autocorr. of |100-trade changes|, lag 1", f"{t['autocorr'][100]['absolute'][0]:+.2f}"),
             ("autocorr. of |100-trade changes|, lag 10", f"{t['autocorr'][100]['absolute'][9]:+.2f}")]
    return rows
