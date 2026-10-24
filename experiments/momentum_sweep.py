"""
Momentum trader sweep: how do trend followers change the market, and its recovery after a shock?
(docs/decisions.md, D31.)

Every combination of these settings is tried:

    share of the takers that are momentum traders   10%, 25%, 50%
    mix of orders (derivatives they see)            only 1, only 2, only 3, a third of each, and
                                                    every two-to-one pair (e.g. 2/3 order 1, 1/3 order 2)
    window (steps of past prices they read)         50, 100, 200, 500
    value traders                                   none, or 20% of takers (mean error 50, news 1)

That is 3 x 10 x 4 x 2 = 240 combinations, plus two controls with no momentum traders (with and
without value traders): 242 in all, numbered 0 to 241 (see `list`). Each one is two experiments, as
in experiments/value_sweep.py:

    shock    experiments/shock.py: sell orders of 150 and 300 units. With value traders: how fast does
             the price recover? Without: how much further does it fall after the order?
    normal   experiments/run.py, no shock, N_A = 500 only: Hurst exponent, size of price moves, return
             distribution and autocorrelations

    python -m experiments.momentum_sweep list
    python -m experiments.momentum_sweep run --index 7 --workers 16
    python -m experiments.momentum_sweep collect

`run` is meant for a cluster job array (cluster/momentum_sweep.slurm). Results go to
results/momentum_sweep/. Running an index again picks up where it stopped. `collect` can be run at
any time; combinations that have not finished are listed as missing.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import pickle
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from analysis.recovery import impact, recovered_fraction, time_to_recover
from experiments import run as runner
from experiments import shock
from experiments.plot import approximate_kurtosis, hurst_curves, hurst_near, mean_autocorrelation

SHARES = (0.1, 0.25, 0.5)
MIXES = ((1,), (2,), (3,), (1, 2, 3), (1, 1, 2), (2, 2, 1), (1, 1, 3), (3, 3, 1), (2, 2, 3), (3, 3, 2))
WINDOWS = (50, 100, 200, 500)
VALUE = {"fraction": 0.2, "true_value_step": 1.0, "spread": 50.0}     # when value traders are present
CONTROLS = [(False, 0.0, (), 50), (True, 0.0, (), 50)]
GRID = CONTROLS + [(with_value, share, mix, window)
                   for with_value in (False, True)
                   for share, mix, window in itertools.product(SHARES, MIXES, WINDOWS)]
SHOCK_SIZES = (150, 300)
NORMAL_AGENTS = 500
HURST_LAGS = (10, 100, 1000, 10_000, 100_000)
OUT_DIR = runner.RESULTS_DIR / "momentum_sweep"


def mix_name(mix) -> str:
    """(1, 1, 2) -> '112'."""
    return "".join(map(str, mix))


def describe_mix(mix) -> str:
    """(1, 1, 2) -> '2/3 order 1, 1/3 order 2'."""
    counts = {order: mix.count(order) for order in dict.fromkeys(mix)}
    if len(counts) == 1:
        return f"only order {mix[0]}"
    if len(set(counts.values())) == 1:
        return "equal shares of orders " + ", ".join(map(str, counts))
    return ", ".join(f"{c}/{len(mix)} order {o}" for o, c in counts.items())


def name_of(index: int) -> str:
    with_value, share, mix, window = GRID[index]
    prefix = "val" if with_value else "noval"
    if share == 0:
        return f"control_{prefix}"
    return f"{prefix}_s{share:g}_m{mix_name(mix)}_w{window}"


def shock_traders(share: float) -> int:
    """Number of traders of a given share in the shock test, which has 250 agents."""
    return round(share * shock.N_AGENTS)


def run_index(index: int, workers: int, n_steps: int, n_runs: int, shock_runs: int, shock_after: int,
              out_dir: Path, shock_only: bool = False) -> None:
    with_value, share, mix, window = GRID[index]
    name = name_of(index)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"combination {index}: {name}", flush=True)

    shock_args = ["--sizes", "0", *map(str, SHOCK_SIZES), "--n-runs", str(shock_runs), "--after", str(shock_after),
                  "--workers", str(workers), "--out", str(out_dir / f"shock_{name}.png")]
    run_args = ["--n-steps", str(n_steps), "--n-runs", str(n_runs), "--agent-counts", str(NORMAL_AGENTS),
                "--workers", str(workers), "--resume", "--out", str(out_dir / f"normal_{name}.pkl")]
    if with_value:
        shock_args += ["--value-traders", str(shock_traders(VALUE["fraction"])),
                       "--true-value-step", str(VALUE["true_value_step"]), "--value-spread", str(VALUE["spread"])]
        run_args += ["--value-fraction", str(VALUE["fraction"]),
                     "--true-value-step", str(VALUE["true_value_step"]), "--value-spread", str(VALUE["spread"])]
    if share > 0:
        orders = list(map(str, mix))
        shock_args += ["--momentum-traders", str(shock_traders(share)), "--momentum-orders", *orders,
                       "--momentum-window", str(window)]
        run_args += ["--momentum-fraction", str(share), "--momentum-orders", *orders, "--momentum-window", str(window)]

    shock.main(shock_args)
    if not shock_only:
        runner.main(run_args)


def summarise_index(index: int, out_dir: Path):
    """One row of the summary table, or None if this combination has not finished."""
    name = name_of(index)
    shock_file, normal_file = out_dir / f"shock_{name}.pkl", out_dir / f"normal_{name}.pkl"
    if not (shock_file.exists() and normal_file.exists()):
        return None
    with_value, share, mix, window = GRID[index]
    row = {"index": index, "name": name, "value_traders": with_value, "share": share,
           "mix": mix_name(mix) if share else "", "window": window if share else None}

    with open(shock_file, "rb") as f:
        shocked = pickle.load(f)
    for size in SHOCK_SIZES:
        means = shocked["means"][size]
        price = means.get("price_vs_value", means["price"])
        row[f"impact_{size}"] = impact(price, shock.BEFORE)
        # How far the price went after the order: below the impact = momentum pushed it further down.
        row[f"lowest_{size}"] = float(np.min(price[shock.BEFORE:shock.BEFORE + 500]))
        # Highest point once it has had time to come back: above 0 = it overshot the old level.
        row[f"highest_{size}"] = float(np.max(price[shock.BEFORE + 50:]))
        row[f"half_life_{size}"] = time_to_recover(price, shock.BEFORE)
        row[f"recovered_{size}"] = recovered_fraction(price, shock.BEFORE, shock.TAIL)

    with open(normal_file, "rb") as f:
        normal = pickle.load(f)
    runs, config = normal["runs"], normal["config"]
    taus, h = hurst_curves(runs, NORMAL_AGENTS, "median")
    h_mean = h.mean(axis=0)
    for lag in HURST_LAGS:
        row[f"H({lag:g})"] = hurst_near(taus, h_mean, lag)
    edges = config["return_bin_edges"]["median"]
    counts = sum(r["return_counts"]["median"][200] for r in runs if r["n_agents"] == NORMAL_AGENTS)
    centres = np.sqrt(edges[:-1] * edges[1:])
    row["rms_200"] = float(np.sqrt((counts / counts.sum() * centres ** 2).sum()))
    for tau in (200, 800):
        row[f"kurtosis_{tau}"] = approximate_kurtosis(runs, edges, "median", tau)
    for kind in ("signed", "absolute"):
        values = mean_autocorrelation(runs, NORMAL_AGENTS, "median", kind)
        row[f"autocorr_{kind}"] = None if values is None else float(values[0])
    return row


def plot_heatmaps(rows, key: str, with_value: bool, title: str, out: Path, log: bool = False) -> None:
    """One panel per window: rows = mixes, columns = shares, colour = the value of `key`."""
    fig, axes = plt.subplots(1, len(WINDOWS), figsize=(17, 6), sharey=True)
    lookup = {(r["share"], r["mix"], r["window"]): r[key] for r in rows if r["value_traders"] == with_value and r["share"]}
    values = [v for v in lookup.values() if v is not None]
    if not values:
        plt.close(fig)
        return
    vmin, vmax = min(values), max(values)
    for ax, window in zip(axes, WINDOWS):
        grid = np.full((len(MIXES), len(SHARES)), np.nan)
        for i, mix in enumerate(MIXES):
            for j, share in enumerate(SHARES):
                value = lookup.get((share, mix_name(mix), window))
                if value is not None:
                    grid[i, j] = value
        shown = np.log10(grid) if log else grid
        im = ax.imshow(shown, cmap="viridis", aspect="auto",
                       vmin=np.log10(vmin) if log else vmin, vmax=np.log10(vmax) if log else vmax)
        for i in range(grid.shape[0]):
            for j in range(grid.shape[1]):
                text = "-" if np.isnan(grid[i, j]) else f"{grid[i, j]:.3g}"
                ax.text(j, i, text, ha="center", va="center", fontsize=7, color="w")
        ax.set_xticks(range(len(SHARES)), [f"{s:.0%}" for s in SHARES])
        ax.set_yticks(range(len(MIXES)), [describe_mix(m) for m in MIXES])
        ax.set_title(f"window {window} steps")
    fig.supxlabel("share of takers that are momentum traders")
    fig.colorbar(im, ax=axes, shrink=0.8, label=("log10 of " if log else "") + key)
    fig.suptitle(title + ("  (with 20% value traders)" if with_value else "  (no value traders)"))
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)


def collect(out_dir: Path) -> list:
    rows, missing = [], []
    for index in range(len(GRID)):
        row = summarise_index(index, out_dir)
        (rows.append(row) if row is not None else missing.append(name_of(index)))
    if missing:
        print(f"{len(missing)} of {len(GRID)} combinations have not finished"
              + (f": {', '.join(missing)}" if len(missing) <= 20 else ""))
    if not rows:
        raise SystemExit(f"No finished combinations in {out_dir}.")

    def cell(value, fmt, width=7):
        if value is None:
            return f"{'never' if fmt == 'steps' else '-':>{width}}"
        return f"{value:>{width}}" if fmt == "steps" else f"{value:>{width}{fmt}}"
    print(f"\n{'combination':24} | {'impact':>7} {'lowest':>7} {'highest':>7} {'half-l.':>7} | "
          f"{'H(10)':>6} {'H(100)':>6} {'H(1e3)':>6} {'H(1e4)':>6} | {'RMS200':>7} {'kurt.':>6} {'ac(1)':>7} {'|ac|':>6}")
    for r in rows:
        print(f"{r['name']:24} | {cell(r['impact_300'], '.1f')} {cell(r['lowest_300'], '.1f')} "
              f"{cell(r['highest_300'], '.1f')} {cell(r['half_life_300'], 'steps')} | "
              + " ".join(cell(r[f'H({l:g})'], '.2f', 6) for l in HURST_LAGS[:4])
              + f" | {cell(r['rms_200'], '.1f')} {cell(r['kurtosis_200'], '.2f', 6)} "
              f"{cell(r['autocorr_signed'], '.3f')} {cell(r['autocorr_absolute'], '.3f', 6)}")
    print("\nShock columns are for the 300-unit sell, in ticks relative to the step before (relative to the true "
          "value when there are\nvalue traders): impact at the order, lowest point in the next 500 steps, highest "
          "point after 50 steps, half-life in steps.\nThe rest are from runs without a shock (N_A = 500, median "
          "price): RMS and kurtosis of the change over 200 steps.")

    csv_out = out_dir / "summary.csv"
    with open(csv_out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    figures = [("rms_200", False, "Typical price move over 200 steps (ticks)", "summary_rms", True),
               ("H(100)", False, "Hurst exponent at a lag of 100 steps", "summary_hurst", False),
               ("lowest_300", False, "Lowest price after a 300-unit sell (ticks)", "summary_lowest", False),
               ("half_life_300", True, "Recovery half-life after a 300-unit sell (steps)", "summary_half_life", True),
               ("lowest_300", True, "Lowest price after a 300-unit sell (ticks)", "summary_lowest", False),
               ("kurtosis_200", False, "Kurtosis of the change over 200 steps (Gaussian = 3)", "summary_kurtosis", False)]
    for key, with_value, title, stem, log in figures:
        out = out_dir / f"{stem}_{'val' if with_value else 'noval'}.png"
        plot_heatmaps(rows, key, with_value, title, out, log)
    print(f"saved {csv_out} and the summary_*.png figures in {out_dir}")
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="show the combinations and their numbers")
    run_cmd = commands.add_parser("run", help="run one combination (both experiments)")
    run_cmd.add_argument("--index", type=int, required=True, help=f"0 to {len(GRID) - 1}")
    run_cmd.add_argument("--workers", type=int, required=True,
                         help="processes to use: the number of CPUs the job was given")
    run_cmd.add_argument("--n-steps", type=int, default=1_000_000, help="steps per normal-times run (default 10^6)")
    run_cmd.add_argument("--n-runs", type=int, default=16, help="normal-times runs (default 16)")
    run_cmd.add_argument("--shock-runs", type=int, default=200, help="shock runs per size (default 200)")
    run_cmd.add_argument("--shock-after", type=int, default=2000, help="steps recorded after each shock (default 2000)")
    run_cmd.add_argument("--shock-only", action="store_true", help="run only the shock test")
    for sub in (run_cmd, commands.add_parser("collect", help="summary table and figures")):
        sub.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)

    if args.command == "list":
        for index in range(len(GRID)):
            with_value, share, mix, window = GRID[index]
            what = "no momentum traders" if share == 0 else (
                f"{share:.0%} momentum ({shock_traders(share)} of 250 in the shock test), {describe_mix(mix)}, "
                f"window {window}")
            print(f"{index:3d}  {name_of(index):24}  {what}; " + ("with value traders" if with_value else "no value traders"))
    elif args.command == "run":
        if not 0 <= args.index < len(GRID):
            parser.error(f"--index must be 0 to {len(GRID) - 1}")
        run_index(args.index, args.workers, args.n_steps, args.n_runs, args.shock_runs, args.shock_after,
                  args.out_dir, args.shock_only)
    else:
        collect(args.out_dir)


if __name__ == "__main__":
    main()
