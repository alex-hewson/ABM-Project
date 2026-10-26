"""
Draw the paper's figures from results files saved by experiments/run.py.

    python -m experiments.plot fig2 --data results/fig2.pkl --out results/fig2.png
    python -m experiments.plot fig3 --bounded results/fig3_bounded.pkl \
                                    --mean-reverting results/fig3_mean_reverting.pkl --out results/fig3.png
    python -m experiments.plot fig4 --data results/fig4.pkl --out results/fig4.png \
                                    [--compare results/fig3_mean_reverting.pkl]
    python -m experiments.plot compare --data results/a.pkl results/b.pkl --labels "none" "20%" \
                                       --out results/compare.png

All take --price mid|last|first|median|mean for the Hurst and return-distribution panels
(default: median, the definition adopted for reported results; docs/decisions.md, D11).

fig2   (a) mid-price path, (b) depth profile with lognormal fit, (c) H(delta tau), (d) |increment|
       distributions -- plus a second figure comparing H under every price definition, saved next to
       --out with "_price_definitions" added to the name.
fig3   (a)/(b) H(delta tau) and |increment| distributions for the bounded random walk,
       (c)/(d) the same for the mean-reverting walk. Each distribution panel has an inset showing the
       signed increments for every delta tau on linear axes, as in the paper (see plot_returns).
fig4   (a) H(delta tau) and (b) signed increment distributions on a semi-log plot (Delta p in
       ticks/10^3), for the mean-reverting walk with the Eq. 4 entry depth. On a semi-log plot,
       exponential tails are straight lines. --compare adds the same run without Eq. 4 (the Fig. 3c/3d
       file) to panel (b) as dashed lines, to show that the fat tails come from Eq. 4.

compare  puts any number of results files side by side, one curve per file, all at N_A = 500:
       (a) H(delta tau), (b) the |increment| distribution for one delta tau (--tau), (c) the
       autocorrelation of price changes, (d) the autocorrelation of their absolute size (volatility
       clustering). It also prints a table of the main numbers. Meant for seeing what a change to
       the model does, e.g. adding value traders. Files made before the autocorrelations were
       stored are left out of (c) and (d).

fig2, fig3 and fig4 check that the files they are given were made with the flow (and entry depth)
they expect, so e.g. a bounded-walk file can't be plotted as the mean-reverting one by mistake.
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
from experiments.run import RESULTS_DIR, RESULTS_FORMAT, AGENT_COUNTS, PATH_AGENTS, DEPTH_AGENTS, RETURN_TAUS
from experiments.provenance import describe


def load(path: Path, expected_flow: str, eq4: bool = False) -> dict:
    """Load a results file, refusing one made by an older version of run.py, or with a different
    order flow or entry depth than the figure needs (eq4: whether the Eq. 4 entry depth is expected)."""
    with open(path, "rb") as f:
        data = pickle.load(f)
    config = data["config"]
    if config.get("format") != RESULTS_FORMAT:
        raise SystemExit(f"{path} was made by an older version of the runner (results format "
                         f"{config.get('format')}, this plotter needs {RESULTS_FORMAT}). "
                         f"Re-run experiments.run to regenerate it.")
    flow = (config.get("flow") or {}).get("name", "symmetric")
    if flow != expected_flow:
        raise SystemExit(f"{path} was made with --flow {flow}, but this panel needs --flow {expected_flow}.")
    has_eq4 = config.get("entry_depth") is not None
    if has_eq4 != eq4:
        raise SystemExit(f"{path} was made {'with' if has_eq4 else 'without'} the Eq. 4 entry depth "
                         f"(--depth-coupling), but this panel needs it {'on' if eq4 else 'off'}.")
    return data


def warn_about_overflow(runs, price, label):
    """Increments too large for the last histogram bin are left out of the plotted distributions;
    say so if there are any. (Results files made before this was counted have no count to check.)"""
    lost = sum(n for r in runs for n in (r.get("return_overflow") or {}).get(price, {}).values())
    if lost:
        print(f"WARNING ({label}): {lost} increments were too large for the histogram bins and are missing "
              f"from the plotted distributions.")


def add_footer(fig, configs):
    """Code version(s) the results came from, bottom right."""
    versions = sorted({describe(c["git"]) for c in configs if "git" in c})
    if versions:
        fig.text(0.995, 0.005, "code version: " + "; ".join(versions), ha="right", va="bottom",
                 fontsize=7, color="gray")


def hurst_curves(runs, n_agents, price):
    """(lags, H per run) for one N_A: H derived per run from the stored RMS values, so the average
    over runs is an average of H (as in the paper), not an H of averaged RMS."""
    rs = [r for r in runs if r["n_agents"] == n_agents]
    if not rs:
        return None, None
    taus = rs[0]["taus"]
    return taus, np.array([local_slopes(taus, r["rms"][price]) for r in rs])


def plot_price_path(ax, runs, title):
    run = next(r for r in runs if r["price_path"] is not None)
    path = run["price_path"]
    t = np.arange(len(path)) / 1e5
    ax.plot(t, path - path[0], lw=0.6)
    ax.set(xlabel="t [MCS / 10$^5$]", ylabel="p(t) - p(t$_0$) [ticks]",
           title=f"{title}, N$_A$={PATH_AGENTS}, seed {run['seed']}")


def plot_depth(ax, runs, title):
    """<N(p - p_m)>: mean number of resting orders per tick at each distance from the midpoint,
    with a lognormal fit (see analysis/depth_profile.py and docs/decisions.md, D14) to the two
    sides combined."""
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
           title=f"{title}, N$_A$={DEPTH_AGENTS}")
    ax.legend(fontsize=7)
    return fit


def plot_hurst(ax, runs, price, title):
    for n_agents in AGENT_COUNTS:
        taus, h = hurst_curves(runs, n_agents, price)
        if h is None:
            continue
        ax.plot(taus, h.mean(axis=0), label=f"N$_A$={n_agents} ({len(h)} runs)")
    ax.axhline(0.5, color="k", ls="--", lw=0.8, label="random walk (H = 0.5)")
    ax.set(xscale="log", xlim=(1, None), xlabel="$\\Delta\\tau$ [MCS]", ylabel="H($\\Delta\\tau$)",
           title=f"{title}, price = {price}")
    ax.legend(fontsize=7)


def plot_returns(ax, runs, bin_edges_by_price, price, title, signed_inset=False):
    """|increment| distributions at N_A = DEPTH_AGENTS, one curve per delta tau, log-log.

    signed_inset adds a small linear-axes plot of the SIGNED increments for every delta tau, as in the
    paper's Fig. 3b inset: on linear axes a bimodal distribution shows up clearly, and so does its
    peak splitting and flattening as delta tau grows. Only |increment| is stored, so the signed
    density is reconstructed by mirroring: f(+x) = f(-x) = P(|dp| = x) / 2. This assumes the
    distribution is symmetric about zero, which holds by construction here, since every flow process
    is symmetric about q = 1/2 (docs/decisions.md, D20)."""
    bin_edges = bin_edges_by_price[price]
    centres = np.sqrt(bin_edges[:-1] * bin_edges[1:])   # geometric centre of log-spaced bins
    curves = []                                          # (tau, counts, density), for the inset
    for tau in RETURN_TAUS:
        counts = sum(r["return_counts"][price][tau] for r in runs
                     if r["n_agents"] == DEPTH_AGENTS and tau in r["return_counts"][price])
        if np.isscalar(counts) or counts.sum() == 0:
            continue
        dens = counts_to_density(counts, bin_edges)
        keep = dens > 0
        ax.plot(centres[keep], dens[keep], "o-", ms=3, lw=0.8, label=f"$\\Delta\\tau$={tau}")
        curves.append((tau, counts, dens))
    ax.set(xscale="log", yscale="log", xlabel="|$\\Delta$p| [ticks]", ylabel="P(|$\\Delta$p|)",
           title=f"{title}, N$_A$={DEPTH_AGENTS}, price = {price}")
    # The curves sit along the top and drop away on the right, so the lower left is empty: the inset
    # goes there, and the legend moves to the middle to make room.
    ax.legend(fontsize=7, loc="center" if signed_inset else "lower left")

    if signed_inset and curves:
        # x range: 99.9% of the widest (largest delta tau) distribution's increments.
        _, widest_counts, _ = curves[-1]
        cumulative = np.cumsum(widest_counts) / widest_counts.sum()
        x_max = bin_edges[1:][np.searchsorted(cumulative, 0.999)]
        keep = centres <= x_max
        inset = ax.inset_axes([0.07, 0.08, 0.36, 0.3])
        for colour, (tau, counts, dens) in enumerate(curves):       # same colours as the main curves
            x = np.concatenate([-centres[keep][::-1], centres[keep]])
            y = np.concatenate([dens[keep][::-1], dens[keep]]) / 2
            inset.plot(x, y, "-", lw=0.9, color=f"C{colour}")
        inset.set_title("signed $\\Delta$p, linear axes", fontsize=6)
        inset.tick_params(labelsize=5)


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
    add_footer(fig, [config])
    fig.savefig(out, dpi=130)
    plt.close(fig)


def figure2(args):
    data = load(args.data, "symmetric")
    runs, config = data["runs"], data["config"]

    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    plot_price_path(axes[0, 0], runs, "(a) mid-price path")
    plot_depth(axes[0, 1], runs, "(b) depth")
    plot_hurst(axes[1, 0], runs, args.price, "(c) Hurst exponent")
    plot_returns(axes[1, 1], runs, config["return_bin_edges"], args.price, "(d) |increments|")
    warn_about_overflow(runs, args.price, "fig2")
    fig.suptitle(f"Fig. 2 reproduction: {config['n_steps']:,} steps, {config['n_runs']} runs per N$_A$")
    fig.tight_layout()
    add_footer(fig, [config])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=130)
    plt.close(fig)
    print(f"saved {args.out}")

    comparison = args.out.with_name(args.out.stem + "_price_definitions" + args.out.suffix)
    plot_price_definition_comparison(runs, config, comparison)
    print(f"saved {comparison}")


def figure3(args):
    bounded = load(args.bounded, "bounded")
    reverting = load(args.mean_reverting, "mean-reverting", eq4=False)

    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    for row, (data, label, short, letters) in enumerate(((bounded, "bounded walk", "bounded", "ab"),
                                                         (reverting, "mean-reverting walk", "mean-rev.", "cd"))):
        runs, config = data["runs"], data["config"]
        plot_hurst(axes[row, 0], runs, args.price, f"({letters[0]}) H, {label}")
        plot_returns(axes[row, 1], runs, config["return_bin_edges"], args.price,
                     f"({letters[1]}) |$\\Delta$p|, {short}", signed_inset=True)
        warn_about_overflow(runs, args.price, label)

        # <(q - 1/2)^2> per N_A, averaged over runs: the quantity Eq. 4 needs (decisions D17).
        for n_agents in AGENT_COUNTS:
            values = [r["q_stats"]["mean_sq_dev"] for r in runs if r["n_agents"] == n_agents]
            if values:
                print(f"{label}, N_A={n_agents}: <(q - 1/2)^2> = {np.mean(values):.3e} "
                      f"(sqrt = {np.sqrt(np.mean(values)):.4f}, {len(values)} runs)")
    axes[0, 0].set_ylim(0, 1)
    axes[1, 0].set_ylim(0, 1)
    fig.suptitle(f"Fig. 3 reproduction: {bounded['config']['n_steps']:,} steps, "
                 f"{bounded['config']['n_runs']} / {reverting['config']['n_runs']} runs per N$_A$ "
                 f"(bounded / mean-reverting)")
    fig.tight_layout()
    add_footer(fig, [bounded["config"], reverting["config"]])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=130)
    plt.close(fig)
    print(f"saved {args.out}")


def plot_returns_semilog(ax, runs, bin_edges_by_price, price, title, compare=None):
    """Signed increment distributions at N_A = DEPTH_AGENTS on a semi-log plot, as in the paper's Fig. 4b:
    Delta p in ticks/10^3 on a linear axis, probability on a log axis, so an exponential tail is a straight
    line. The signed density is made by mirroring the stored |Delta p| histogram (see plot_returns).
    compare = (runs, bin edges by price) of the same model without Eq. 4, drawn as dashed lines."""
    def draw(these_runs, edges_by_price, style, label_suffix):
        bin_edges = edges_by_price[price]
        centres = np.sqrt(bin_edges[:-1] * bin_edges[1:])
        for colour, tau in enumerate(RETURN_TAUS):
            counts = sum(r["return_counts"][price][tau] for r in these_runs
                         if r["n_agents"] == DEPTH_AGENTS and tau in r["return_counts"][price])
            if np.isscalar(counts) or counts.sum() == 0:
                continue
            dens = counts_to_density(counts, bin_edges) / 2          # per tick, each sign
            keep = dens > 0
            x = np.concatenate([-centres[keep][::-1], centres[keep]]) / 1000
            y = np.concatenate([dens[keep][::-1], dens[keep]])
            ax.plot(x, y, style, color=f"C{colour}", ms=3, lw=0.8,
                    label=f"$\\Delta\\tau$={tau}{label_suffix}")

    draw(runs, bin_edges_by_price, "o-", "")
    if compare is not None:
        draw(*compare, "--", " (fixed depth)")
    ax.set(yscale="log", xlabel="$\\Delta$p [ticks / 10$^3$]", ylabel="P($\\Delta$p)",
           title=f"{title}, N$_A$={DEPTH_AGENTS}, price = {price}")
    ax.legend(fontsize=6, ncol=2 if compare is not None else 1)


def approximate_kurtosis(runs, bin_edges, price, tau, n_agents=DEPTH_AGENTS):
    """Kurtosis of the signed increments (3 for a Gaussian), from the binned |Delta p| counts, for the
    runs at n_agents (500 by default). Only approximate, since every increment is placed at its bin centre."""
    counts = sum(r["return_counts"][price][tau] for r in runs if r["n_agents"] == n_agents).astype(float)
    centres = np.sqrt(bin_edges[:-1] * bin_edges[1:])
    p = counts / counts.sum()
    return (p * centres ** 4).sum() / (p * centres ** 2).sum() ** 2


def figure4(args):
    data = load(args.data, "mean-reverting", eq4=True)
    runs, config = data["runs"], data["config"]
    compare = None
    if args.compare is not None:
        reference = load(args.compare, "mean-reverting", eq4=False)
        compare = (reference["runs"], reference["config"]["return_bin_edges"])

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    plot_hurst(axes[0], runs, args.price, "(a) H, mean-reverting walk + Eq. 4")
    axes[0].set_ylim(0, 1)
    plot_returns_semilog(axes[1], runs, config["return_bin_edges"], args.price, "(b) $\\Delta$p", compare)
    warn_about_overflow(runs, args.price, "fig4")

    depth = config["entry_depth"]
    lam_means = [r["lambda_stats"]["mean"] for r in runs]
    print(f"Eq. 4: lambda_0 = {depth['lambda_0']:g}, C_lambda = {depth['c_lambda']:g}, "
          f"sqrt(<(q - 1/2)^2>) = {depth['q_rms']:.4f}; lambda(t) averaged {np.mean(lam_means):.0f} ticks "
          f"(largest in any run: {max(r['lambda_stats']['max'] for r in runs):.0f})")
    edges = config["return_bin_edges"][args.price]
    for tau in RETURN_TAUS:
        line = f"N_A={DEPTH_AGENTS}, delta tau={tau}: kurtosis ~ {approximate_kurtosis(runs, edges, args.price, tau):.2f}"
        if compare is not None:
            ref_edges = compare[1][args.price]
            line += f" (fixed depth: {approximate_kurtosis(compare[0], ref_edges, args.price, tau):.2f})"
        print(line + "   [Gaussian: 3]")

    fig.suptitle(f"Fig. 4 reproduction: {config['n_steps']:,} steps, {config['n_runs']} runs per N$_A$, "
                 f"C$_\\lambda$ = {depth['c_lambda']:g}")
    fig.tight_layout()
    add_footer(fig, [config] + ([reference["config"]] if compare is not None else []))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=130)
    plt.close(fig)
    print(f"saved {args.out}")


def load_any(path: Path) -> dict:
    """Load a results file made with any flow, entry depth or agents (only the format is checked)."""
    with open(path, "rb") as f:
        data = pickle.load(f)
    if data["config"].get("format") != RESULTS_FORMAT:
        raise SystemExit(f"{path} was made by an older version of the runner (results format "
                         f"{data['config'].get('format')}, this plotter needs {RESULTS_FORMAT}).")
    return data


def describe_settings(config: dict) -> str:
    """Short text saying which model a results file is, e.g. 'mean-reverting + Eq. 4, 20% value traders'."""
    text = (config.get("flow") or {}).get("name", "symmetric")
    if config.get("entry_depth") is not None:
        text += " + Eq. 4"
    trend = config.get("momentum_traders")
    if trend is not None:
        text += f", {trend['fraction']:.0%} momentum (orders {trend['orders']}, window {trend['window']})"
    kinds = config.get("agent_types")
    if kinds is not None:
        text += f", provider types {kinds['providers']}, taker types {kinds['takers']}"
    traders = config.get("value_traders")
    text += ", no value traders" if traders is None else f", {traders['fraction']:.0%} value traders"
    news = config.get("news")
    if news is not None:
        text += f", news (chance {news['chance']:g}, jumps of {news['jump']:g})"
    big = config.get("poisson_trader")
    if big is not None:
        text += f", Poisson trader (chance {big['chance']:g}, mean order {big['rate'] / big['chance']:.0f})"
    return text


def mean_autocorrelation(runs, n_agents, price, kind):
    """Mean over runs of the stored autocorrelation ("signed" or "absolute") at one N_A, or None if
    the file has none (it was made before they were stored)."""
    rows = [r["autocorr"][price][kind] for r in runs
            if r["n_agents"] == n_agents and price in (r.get("autocorr") or {})]
    return np.nanmean(rows, axis=0) if rows else None


def hurst_near(taus, h_mean, target):
    """H at the stored lag closest to target (None if the lags do not reach that far)."""
    if target > taus[-1] * 1.5:
        return None
    return float(h_mean[int(np.argmin(np.abs(np.log(taus) - np.log(target))))])


def figure_compare(args):
    datasets = [load_any(path) for path in args.data]
    labels = args.labels or [describe_settings(d["config"]) for d in datasets]
    if len(labels) != len(datasets):
        raise SystemExit(f"--labels: {len(labels)} labels were given for {len(datasets)} files")
    n_agents, price, tau = DEPTH_AGENTS, args.price, args.tau

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    (ax_h, ax_r), (ax_signed, ax_abs) = axes
    rows = []
    for colour, (data, label) in enumerate(zip(datasets, labels)):
        runs, config, c = data["runs"], data["config"], f"C{colour}"
        row = {"label": label}

        taus, h = hurst_curves(runs, n_agents, price)
        if h is None:
            raise SystemExit(f"{label}: the file has no runs at N_A = {n_agents}")
        h_mean = h.mean(axis=0)
        ax_h.plot(taus, h_mean, color=c, label=label)
        row["hurst"] = [hurst_near(taus, h_mean, target) for target in (10, 100, 1000, 10_000)]

        edges = config["return_bin_edges"][price]
        counts = sum(r["return_counts"][price][tau] for r in runs
                     if r["n_agents"] == n_agents and tau in r["return_counts"][price])
        if np.isscalar(counts) or counts.sum() == 0:
            raise SystemExit(f"{label}: no return distribution stored for delta tau = {tau}")
        density = counts_to_density(counts, edges)
        centres = np.sqrt(edges[:-1] * edges[1:])
        keep = density > 0
        row["kurtosis"] = approximate_kurtosis(runs, edges, price, tau)
        p = counts / counts.sum()
        row["rms"] = float(np.sqrt((p * centres ** 2).sum()))
        ax_r.plot(centres[keep], density[keep], "o-", ms=3, lw=0.8, color=c,
                  label=f"{label} (kurtosis {row['kurtosis']:.2f})")
        warn_about_overflow(runs, price, label)

        interval = (config.get("autocorr") or {}).get("interval")
        for ax, kind in ((ax_signed, "signed"), (ax_abs, "absolute")):
            values = mean_autocorrelation(runs, n_agents, price, kind)
            row[kind] = None if values is None else float(values[0])
            if values is not None:
                ax.plot(np.arange(1, len(values) + 1) * interval, values, color=c, lw=0.9, label=label)
        row["book"] = float(np.mean([r["mean_orders"] for r in runs if r["n_agents"] == n_agents]))
        rows.append(row)

    ax_h.axhline(0.5, color="k", ls="--", lw=0.8)
    ax_h.set(xscale="log", xlim=(1, None), ylim=(0, None), xlabel="$\\Delta\\tau$ [MCS]", ylabel="H($\\Delta\\tau$)",
             title=f"(a) Hurst exponent, N$_A$={n_agents}, price = {price}")
    ax_r.set(xscale="log", yscale="log", xlabel="|$\\Delta$p| [ticks]", ylabel="P(|$\\Delta$p|)",
             title=f"(b) |$\\Delta$p| for $\\Delta\\tau$ = {tau}")
    ax_signed.set(xscale="log", xlabel="lag [MCS]", ylabel="autocorrelation",
                  title="(c) price changes: below 0 = turns back, above 0 = trends")
    ax_abs.set(xscale="log", xlabel="lag [MCS]", ylabel="autocorrelation",
               title="(d) size of price changes: above 0 = volatility clustering")
    for ax in (ax_signed, ax_abs):
        ax.axhline(0, color="k", ls="--", lw=0.8)
    for ax in axes.flat:
        if ax.get_legend_handles_labels()[0]:
            ax.legend(fontsize=7)

    def cell(value, fmt):
        return f"{'-':>7}" if value is None else f"{value:>7{fmt}}"
    width = max(len(row["label"]) for row in rows)
    print(f"\nN_A = {n_agents}, price = {price}")
    print(f"{'':{width}} | {'H(10)':>7} {'H(100)':>7} {'H(1e3)':>7} {'H(1e4)':>7} | {'RMS':>7} {'kurt.':>7} | "
          f"{'ac(1)':>7} {'|ac|(1)':>7} | {'orders':>7}")
    for row in rows:
        print(f"{row['label']:{width}} | " + " ".join(cell(h, ".2f") for h in row["hurst"])
              + f" | {cell(row['rms'], '.1f')} {cell(row['kurtosis'], '.2f')} | "
              f"{cell(row['signed'], '.3f')} {cell(row['absolute'], '.3f')} | {cell(row['book'], '.0f')}")
    print(f"\nRMS and kurtosis are of the price change over {tau} steps (a Gaussian has kurtosis 3). ac(1) and "
          f"|ac|(1) are the\nautocorrelations of the change over one interval and of its size, at a lag of one interval.")

    steps = sorted({d["config"]["n_steps"] for d in datasets})
    fig.suptitle("Comparison of results files: " + ", ".join(f"{s:,}" for s in steps) + " steps per run")
    fig.tight_layout()
    add_footer(fig, [d["config"] for d in datasets])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=130)
    plt.close(fig)
    print(f"saved {args.out}")
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    figures = parser.add_subparsers(dest="figure", required=True)

    fig2 = figures.add_parser("fig2", help="Fig. 2 (symmetric flow)")
    fig2.add_argument("--data", type=Path, default=RESULTS_DIR / "symmetric.pkl")
    fig2.add_argument("--out", type=Path, default=RESULTS_DIR / "fig2.png")

    fig3 = figures.add_parser("fig3", help="Fig. 3 (bounded and mean-reverting flows)")
    fig3.add_argument("--bounded", type=Path, default=RESULTS_DIR / "bounded.pkl")
    fig3.add_argument("--mean-reverting", type=Path, default=RESULTS_DIR / "mean-reverting.pkl")
    fig3.add_argument("--out", type=Path, default=RESULTS_DIR / "fig3.png")

    fig4 = figures.add_parser("fig4", help="Fig. 4 (mean-reverting flow with the Eq. 4 entry depth)")
    fig4.add_argument("--data", type=Path, default=RESULTS_DIR / "mean-reverting_c10.pkl")
    fig4.add_argument("--compare", type=Path, default=None,
                      help="the same model without Eq. 4 (the Fig. 3 mean-reverting file), drawn dashed in (b)")
    fig4.add_argument("--out", type=Path, default=RESULTS_DIR / "fig4.png")

    compare = figures.add_parser("compare", help="several results files side by side")
    compare.add_argument("--data", type=Path, nargs="+", required=True, help="results files, one curve each")
    compare.add_argument("--labels", nargs="+", default=None, help="one label per file (default: its settings)")
    compare.add_argument("--tau", type=int, default=800, choices=RETURN_TAUS,
                         help="delta tau for the return-distribution panel (default 800)")
    compare.add_argument("--out", type=Path, default=RESULTS_DIR / "compare.png")

    for sub in (fig2, fig3, fig4, compare):
        sub.add_argument("--price", choices=PRICE_DEFINITIONS, default="median",
                         help="price definition for the Hurst and distribution panels")
    args = parser.parse_args(argv)
    {"fig2": figure2, "fig3": figure3, "fig4": figure4, "compare": figure_compare}[args.figure](args)


if __name__ == "__main__":
    main()
