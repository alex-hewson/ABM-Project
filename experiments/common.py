"""
Helpers shared by several experiment scripts, so that no experiment script imports another one for
them. Statistics of trade-time segments are in analysis/stylised.py; these work on the results
files of experiments/run.py, on simulation results, or on command-line options.

    N_AGENTS, parse_mix, describe_mix    default N_A and agent mixes for the shock test and the
                                         event studies (shock, news, pressure)
    trade_segment                        one simulation run as a trade-time segment (D37)
    hurst_curves, hurst_near             H from the RMS values stored by experiments/run.py
    approximate_kurtosis                 kurtosis from the stored return histograms
    mean_stored_autocorrelation          mean of the autocorrelations stored by experiments/run.py
                                         (not the same as analysis.stylised.mean_autocorrelation,
                                         which works on trade-time segments)
"""

from __future__ import annotations

import numpy as np

from abm.agents import AgentType
from analysis.hurst import local_slopes
from experiments.run import DEPTH_AGENTS

N_AGENTS = 250        # default N_A of the shock test and the event studies


def parse_mix(items):
    """['1:100', '4:150'] -> {AgentType(1, 1): 100, AgentType(4, 4): 150}. K:COUNT gives agents that
    act every K steps with orders of K units; INTERVAL/SIZE:COUNT sets the two separately.
    None (option not given) stays None, which run_simulation reads as the paper's population."""
    if items is None:
        return None
    mix = {}
    for item in items:
        try:
            kind, count = item.split(":")
            interval, size = kind.split("/") if "/" in kind else (kind, kind)
            agent_type = AgentType(int(interval), int(size))
            mix[agent_type] = mix.get(agent_type, 0) + int(count)
        except ValueError as error:
            raise ValueError(f"cannot read mix item {item!r}: expected K:COUNT or INTERVAL/SIZE:COUNT") from error
    return mix


def describe_mix(mix, n_agents=N_AGENTS):
    """Short text for a mix, e.g. '100 x 1 unit every step, 150 x 4 units every 4 steps'.
    n_agents is how many agents there are when no mix was given."""
    if mix is None:
        mix = {AgentType(): n_agents}
    parts = []
    for agent_type, count in mix.items():
        units = "1 unit" if agent_type.size == 1 else f"{agent_type.size} units"
        every = "every step" if agent_type.interval == 1 else f"every {agent_type.interval} steps"
        parts.append(f"{count} x {units} {every}")
    return ", ".join(parts)


def trade_segment(r, skip_steps: int = 1) -> dict:
    """One run (run with record_sides=True and record_trades=True) as a segment for
    analysis/stylised.py: per trade, the trade price; the mid-price just before the trade, as the
    last quote before a trade in real data (D43); and the spread and units at the best prices at the
    end of the step before the trade's step. Trades in the first skip_steps steps are left out (at
    least step 0, which has no step before it)."""
    keep = r.trade_steps >= max(skip_steps, 1)
    before = r.trade_steps[keep] - 1                       # the state at the end of the step before
    bid, ask = r.best_bid_series, r.best_ask_series
    step_mid = (bid + ask) / 2
    step_mid = np.where(np.isfinite(step_mid), step_mid, np.nan)
    filled = np.copy(step_mid)                             # a step with one side empty keeps the last mid
    for i in range(1, len(filled)):
        if not np.isfinite(filled[i]):
            filled[i] = filled[i - 1]
    if len(r.trade_mids) == len(r.trade_steps):
        # The mid-price in the book just before each trade (D43). A trade with one side of the book
        # empty has none; it keeps the last one before it (or the end-of-step mid, for a first trade).
        mid = np.asarray(r.trade_mids, dtype=float)[keep]
        for i in range(len(mid)):
            if not np.isfinite(mid[i]):
                mid[i] = mid[i - 1] if i > 0 else filled[before][0]
    else:
        mid = filled[before]                               # runs made before trade_mids was recorded
    return {"trade": r.trade_prices[keep].astype(float), "mid": mid, "spread": (ask - bid)[before],
            "bid_size": r.best_bid_size_series[before].astype(float),
            "ask_size": r.best_ask_size_series[before].astype(float),
            "size": np.ones(int(keep.sum()))}             # every order of these agents is one unit


def hurst_curves(runs, n_agents, price):
    """(lags, H per run) for one N_A: H derived per run from the stored RMS values, so the average
    over runs is an average of H (as in the paper), not an H of averaged RMS."""
    rs = [r for r in runs if r["n_agents"] == n_agents]
    if not rs:
        return None, None
    taus = rs[0]["taus"]
    return taus, np.array([local_slopes(taus, r["rms"][price]) for r in rs])


def hurst_near(taus, h_mean, target):
    """H at the stored lag closest to target (None if the lags do not reach that far)."""
    if target > taus[-1] * 1.5:
        return None
    return float(h_mean[int(np.argmin(np.abs(np.log(taus) - np.log(target))))])


def approximate_kurtosis(runs, bin_edges, price, tau, n_agents=DEPTH_AGENTS):
    """Kurtosis of the signed increments (3 for a Gaussian), from the binned |Delta p| counts, for the
    runs at n_agents (500 by default). Only approximate, since every increment is placed at its bin centre."""
    counts = sum(r["return_counts"][price][tau] for r in runs if r["n_agents"] == n_agents).astype(float)
    centres = np.sqrt(bin_edges[:-1] * bin_edges[1:])
    p = counts / counts.sum()
    return (p * centres ** 4).sum() / (p * centres ** 2).sum() ** 2


def mean_stored_autocorrelation(runs, n_agents, price, kind):
    """Mean over runs of the stored autocorrelation ("signed" or "absolute") at one N_A, or None if
    the file has none (it was made before they were stored)."""
    rows = [r["autocorr"][price][kind] for r in runs
            if r["n_agents"] == n_agents and price in (r.get("autocorr") or {})]
    return np.nanmean(rows, axis=0) if rows else None
