"""
Draw the four panels of Fig. 2 from the data saved by fig2.py.

    python plot_fig2.py [--data results/fig2_data.pkl] [--out results/fig2.png]
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

from fig2 import RESULTS_DIR, AGENT_COUNTS, PATH_AGENTS, DEPTH_AGENTS, RETURN_TAUS
from returns import counts_to_density


def load(path):
    with open(path, "rb") as f:
        return pickle.load(f)


def plot_price_path(ax, runs):
    run = next(r for r in runs if r["price_path"] is not None)
    path = run["price_path"]
    t = np.arange(len(path)) / 1e5
    ax.plot(t, path - path[0], lw=0.6)
    ax.set(xlabel="t [MCS / 10$^5$]", ylabel="p(t) - p(t$_0$) [ticks]",
           title=f"(a) price path, N$_A$={PATH_AGENTS}, seed {run['seed']}")


def plot_depth(ax, runs):
    """<N(p - p_m)>: mean number of resting orders per tick at each distance from the midpoint."""
    total = defaultdict(int)
    n_snapshots = 0
    for r in runs:
        if r["n_agents"] != DEPTH_AGENTS:
            continue
        n_snapshots += r["n_depth_snapshots"]
        for half_ticks, n in r["depth_sum"].items():
            total[half_ticks // 2] += n            # 1-tick bins (floor of half-tick offset / 2)
    ticks = np.array(sorted(total))
    mean_depth = np.array([total[k] for k in ticks]) / n_snapshots
    ax.plot(ticks, mean_depth, ".", ms=2)
    ax.set(xlim=(-600, 600), xlabel="p - p$_m$ [ticks]", ylabel="<N(p - p$_m$)>",
           title=f"(b) depth, N$_A$={DEPTH_AGENTS} (no lognormal fit yet)")


def plot_hurst(ax, runs):
    for n_agents in AGENT_COUNTS:
        curves = [r["h"] for r in runs if r["n_agents"] == n_agents]
        if not curves:
            continue
        taus = next(r["taus"] for r in runs if r["n_agents"] == n_agents)
        ax.plot(taus, np.mean(curves, axis=0), label=f"N$_A$={n_agents} ({len(curves)} runs)")
    ax.axhline(0.5, color="k", ls="--", lw=0.8, label="random walk (H = 0.5)")
    ax.set(xscale="log", xlabel="$\\Delta\\tau$ [MCS]", ylabel="H($\\Delta\\tau$)",
           title="(c) Hurst exponent")
    ax.legend(fontsize=7)


def plot_returns(ax, runs, bin_edges):
    centres = np.sqrt(bin_edges[:-1] * bin_edges[1:])   # geometric centre of log-spaced bins
    for tau in RETURN_TAUS:
        counts = sum(r["return_counts"][tau] for r in runs
                     if r["n_agents"] == DEPTH_AGENTS and tau in r["return_counts"])
        if np.isscalar(counts) or counts.sum() == 0:
            continue
        dens = counts_to_density(counts, bin_edges)
        keep = dens > 0
        ax.plot(centres[keep], dens[keep], "o-", ms=3, lw=0.8, label=f"$\\Delta\\tau$={tau}")
    ax.set(xscale="log", yscale="log", xlabel="|$\\Delta$p| [ticks]", ylabel="P(|$\\Delta$p|)",
           title=f"(d) |increments|, N$_A$={DEPTH_AGENTS}")
    ax.legend(fontsize=7)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=RESULTS_DIR / "fig2_data.pkl")
    parser.add_argument("--out", type=Path, default=RESULTS_DIR / "fig2.png")
    args = parser.parse_args()

    data = load(args.data)
    runs, config = data["runs"], data["config"]

    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    plot_price_path(axes[0, 0], runs)
    plot_depth(axes[0, 1], runs)
    plot_hurst(axes[1, 0], runs)
    plot_returns(axes[1, 1], runs, config["return_bin_edges"])
    fig.suptitle(f"Fig. 2 reproduction: {config['n_steps']:,} steps, {config['n_runs']} runs per N$_A$")
    fig.tight_layout()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=130)
    print(f"saved {args.out}")


if __name__ == "__main__":
    main()
