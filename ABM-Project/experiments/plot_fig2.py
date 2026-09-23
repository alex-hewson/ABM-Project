"""
Draw the four panels of Fig. 2 from the data saved by fig2.py, plus a second figure comparing
the Hurst exponent under every price definition (the paper doesn't say which it used).

    python -m experiments.plot_fig2 [--data results/fig2_data.pkl] [--out results/fig2.png]
                                    [--price mid|last|first|median|mean]

--price chooses the price definition for panels (c) and (d). The comparison figure is saved
next to --out with "_price_definitions" added to the name.
"""

from __future__ import annotations

import argparse
import pickle
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from analysis.depth_profile import profile_from_depth_sum, combine_sides, fit_lognormal
from analysis.hurst import local_slopes
from analysis.prices import PRICE_DEFINITIONS
from analysis.returns import counts_to_density
from experiments.fig2 import RESULTS_DIR, RESULTS_FORMAT, AGENT_COUNTS, PATH_AGENTS, DEPTH_AGENTS, RETURN_TAUS
from experiments.provenance import describe


def load(path):
    with open(path, "rb") as f:
        data = pickle.load(f)
    if data["config"].get("format") != RESULTS_FORMAT:
        raise SystemExit(f"{path} was made by an older version of fig2.py (results format "
                         f"{data['config'].get('format')}, this plotter needs {RESULTS_FORMAT}). "
                         f"Re-run fig2.py to regenerate it.")
    return data


def hurst_curves(runs, n_agents, price):
    """(lags, H per run) for one N_A: H derived per run from the stored RMS values, so the average
    over runs is an average of H (as in the paper), not an H of averaged RMS."""
    rs = [r for r in runs if r["n_agents"] == n_agents]
    if not rs:
        return None, None
    taus = rs[0]["taus"]
    return taus, np.array([local_slopes(taus, r["rms"][price]) for r in rs])


def plot_price_path(ax, runs):
    run = next(r for r in runs if r["price_path"] is not None)
    path = run["price_path"]
    t = np.arange(len(path)) / 1e5
    ax.plot(t, path - path[0], lw=0.6)
    ax.set(xlabel="t [MCS / 10$^5$]", ylabel="p(t) - p(t$_0$) [ticks]",
           title=f"(a) mid-price path, N$_A$={PATH_AGENTS}, seed {run['seed']}")


def plot_depth(ax, runs):
    """<N(p - p_m)>: mean number of resting orders per tick at each distance from the midpoint,
    with a lognormal fit (method of moments; see analysis/depth_profile.py and docs/decisions.md,
    D14) to the two sides combined."""
    total_depth_sum = defaultdict(int)
    n_snapshots = 0
    for r in runs:
        if r["n_agents"] != DEPTH_AGENTS:
            continue
        n_snapshots += r["n_depth_snapshots"]
        for half_ticks, n in r["depth_sum"].items():
            total_depth_sum[half_ticks] += n
    profile = profile_from_depth_sum(total_depth_sum, n_snapshots)
    ticks = np.array(sorted(profile))
    mean_depth = np.array([profile[k] for k in ticks])
    ax.plot(ticks, mean_depth, ".", ms=2, label="simulation data")

    # combine_sides sums bid + ask counts at each |x|, so a fit to it describes the COMBINED
    # (both-sides) mass at each distance. Plotting that curve on both sides of the midpoint would
    # double-count -- each side gets half the fitted mass back, matching the fact that each side's
    # raw data (plotted above) is itself about half of the combined total.
    fit = fit_lognormal(combine_sides(profile))
    x = np.linspace(1, 600, 400)
    one_side = fit.total_weight / 2 * fit.density(x)
    ax.plot(x, one_side, "k--", lw=1, label="lognormal fit")
    ax.plot(-x, one_side, "k--", lw=1)

    ax.set(xlim=(-600, 600), xlabel="p - p$_m$ [ticks]", ylabel="<N(p - p$_m$)>",
           title=f"(b) depth, N$_A$={DEPTH_AGENTS}")
    ax.legend(fontsize=7)
    return fit


def plot_hurst(ax, runs, price):
    for n_agents in AGENT_COUNTS:
        taus, h = hurst_curves(runs, n_agents, price)
        if h is None:
            continue
        ax.plot(taus, h.mean(axis=0), label=f"N$_A$={n_agents} ({len(h)} runs)")
    ax.axhline(0.5, color="k", ls="--", lw=0.8, label="random walk (H = 0.5)")
    ax.set(xscale="log", xlim=(1, None), xlabel="$\\Delta\\tau$ [MCS]", ylabel="H($\\Delta\\tau$)",
           title=f"(c) Hurst exponent, price = {price}")
    ax.legend(fontsize=7)


def plot_returns(ax, runs, bin_edges_by_price, price):
    bin_edges = bin_edges_by_price[price]
    centres = np.sqrt(bin_edges[:-1] * bin_edges[1:])   # geometric centre of log-spaced bins
    for tau in RETURN_TAUS:
        counts = sum(r["return_counts"][price][tau] for r in runs
                     if r["n_agents"] == DEPTH_AGENTS and tau in r["return_counts"][price])
        if np.isscalar(counts) or counts.sum() == 0:
            continue
        dens = counts_to_density(counts, bin_edges)
        keep = dens > 0
        ax.plot(centres[keep], dens[keep], "o-", ms=3, lw=0.8, label=f"$\\Delta\\tau$={tau}")
    ax.set(xscale="log", yscale="log", xlabel="|$\\Delta$p| [ticks]", ylabel="P(|$\\Delta$p|)",
           title=f"(d) |increments|, N$_A$={DEPTH_AGENTS}, price = {price}")
    ax.legend(fontsize=7)


def plot_price_definition_comparison(runs, config, out):
    """H(delta tau) for every price definition, one panel per N_A."""
    fig, axes = plt.subplots(1, len(AGENT_COUNTS), figsize=(15, 4.6), sharey=True)
    for ax, n_agents in zip(axes, AGENT_COUNTS):
        for price in PRICE_DEFINITIONS:
            taus, h = hurst_curves(runs, n_agents, price)
            if h is not None:
                ax.plot(taus, h.mean(axis=0), label=price)
        ax.axhline(0.5, color="k", ls="--", lw=0.8)
        ax.set(xscale="log", xlim=(1, None), xlabel="$\\Delta\\tau$ [MCS]", title=f"N$_A$={n_agents}")
    axes[0].set_ylabel("H($\\Delta\\tau$)")
    axes[0].legend(title="price definition", fontsize=8)
    fig.suptitle(f"Hurst exponent under each price definition ({config['n_steps']:,} steps, "
                 f"{config['n_runs']} runs per N$_A$)")
    fig.tight_layout()
    if "git" in config:
        fig.text(0.995, 0.005, f"code version: {describe(config['git'])}", ha="right", va="bottom",
                 fontsize=7, color="gray")
    fig.savefig(out, dpi=130)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=RESULTS_DIR / "fig2_data.pkl")
    parser.add_argument("--out", type=Path, default=RESULTS_DIR / "fig2.png")
    parser.add_argument("--price", choices=PRICE_DEFINITIONS, default="mid",
                        help="price definition for panels (c) and (d)")
    args = parser.parse_args()

    data = load(args.data)
    runs, config = data["runs"], data["config"]

    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    plot_price_path(axes[0, 0], runs)
    plot_depth(axes[0, 1], runs)
    plot_hurst(axes[1, 0], runs, args.price)
    plot_returns(axes[1, 1], runs, config["return_bin_edges"], args.price)
    fig.suptitle(f"Fig. 2 reproduction: {config['n_steps']:,} steps, {config['n_runs']} runs per N$_A$")
    fig.tight_layout()
    if "git" in config:    # results saved before commit IDs were recorded won't have it
        fig.text(0.995, 0.005, f"code version: {describe(config['git'])}", ha="right", va="bottom",
                 fontsize=7, color="gray")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=130)
    print(f"saved {args.out}")

    comparison = args.out.with_name(args.out.stem + "_price_definitions" + args.out.suffix)
    plot_price_definition_comparison(runs, config, comparison)
    print(f"saved {comparison}")


if __name__ == "__main__":
    main()
