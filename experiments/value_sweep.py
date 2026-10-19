"""
Value trader sweep: which settings let the price recover after a shock without pinning it down in
normal times? (docs/validation.md, sections 10 and 11.)

Every combination of three settings is tried (docs/decisions.md, D28):

    share of the takers that are value traders   2%, 5%, 10%, 20%
    news: how much the true value moves a step   0.25, 0.5, 1, 2 ticks (standard deviation)
    mean error of a trader's own value (ticks)   50, 150, 500

That is 48 combinations, plus a control with no value traders: 49 in all, numbered 0 (the control)
to 48. Each one is two experiments:

    shock    experiments/shock.py: sell orders of 150 and 300 units; how fast does the price recover?
    normal   experiments/run.py, no shock, N_A = 500 only: Hurst exponent, return distribution and
             autocorrelations; does the price still behave like a market?

    python -m experiments.value_sweep list                 # the 49 combinations and their numbers
    python -m experiments.value_sweep run --index 7        # run combination 7 (both experiments)
    python -m experiments.value_sweep collect              # table + figure from whatever has finished

`run` is meant for a cluster job array, one combination per job (cluster/value_sweep.slurm).
`run --shock-only` redoes just the shock test, which takes about a minute instead of 15. Results
go to results/value_sweep/. Running the same index again picks up where it stopped. `collect` can be
run at any time; combinations that have not finished are listed as missing.
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

from analysis.recovery import time_to_recover, recovered_fraction
from experiments import run as runner
from experiments import shock
from experiments.plot import approximate_kurtosis, hurst_curves, hurst_near, mean_autocorrelation

FRACTIONS = (0.02, 0.05, 0.1, 0.2)
NEWS = (0.25, 0.5, 1.0, 2.0)
SPREADS = (50.0, 150.0, 500.0)
GRID = [(0.0, 1.0, 50.0)] + list(itertools.product(FRACTIONS, NEWS, SPREADS))   # entry 0: the control
SHOCK_SIZES = (150, 300)
NORMAL_AGENTS = 500              # the normal-times measures are read at this N_A
HURST_LAGS = (10, 100, 1000, 10_000, 100_000)
OUT_DIR = runner.RESULTS_DIR / "value_sweep"


def name_of(index: int) -> str:
    fraction, news, spread = GRID[index]
    return "control" if fraction == 0 else f"f{fraction:g}_news{news:g}_s{spread:g}"


def shock_traders(fraction: float) -> int:
    """Number of value traders in the shock test, which has 250 agents."""
    return round(fraction * shock.N_AGENTS)


def run_index(index: int, workers: int, n_steps: int, n_runs: int, shock_runs: int, shock_after: int,
              out_dir: Path, shock_only: bool = False) -> None:
    fraction, news, spread = GRID[index]
    name = name_of(index)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"combination {index}: {name}", flush=True)

    shock.main(["--sizes", "0", *map(str, SHOCK_SIZES), "--n-runs", str(shock_runs), "--after", str(shock_after),
                "--value-traders", str(shock_traders(fraction)), "--true-value-step", str(news),
                "--value-spread", str(spread), "--workers", str(workers),
                "--out", str(out_dir / f"shock_{name}.png")])
    if shock_only:
        return

    # --resume: an interrupted job carries on, and a finished one is only saved again.
    runner.main(["--value-fraction", str(fraction), "--true-value-step", str(news), "--value-spread", str(spread),
                 "--n-steps", str(n_steps), "--n-runs", str(n_runs), "--agent-counts", str(NORMAL_AGENTS),
                 "--workers", str(workers), "--resume", "--out", str(out_dir / f"normal_{name}.pkl")])


def summarise_index(index: int, out_dir: Path):
    """One row of the summary table, or None if this combination has not finished."""
    name = name_of(index)
    shock_file, normal_file = out_dir / f"shock_{name}.pkl", out_dir / f"normal_{name}.pkl"
    if not (shock_file.exists() and normal_file.exists()):
        return None
    fraction, news, spread = GRID[index]
    row = {"index": index, "name": name, "fraction": fraction,
           "news": news if fraction else None, "spread": spread if fraction else None}

    with open(shock_file, "rb") as f:
        shocked = pickle.load(f)
    for size in SHOCK_SIZES:
        means = shocked["means"][size]
        price = means.get("price_vs_value", means["price"])   # price relative to the true value
        row[f"half_life_{size}"] = time_to_recover(price, shock.BEFORE)
        row[f"recovered_{size}"] = recovered_fraction(price, shock.BEFORE, shock.TAIL)

    with open(normal_file, "rb") as f:
        normal = pickle.load(f)
    runs, config = normal["runs"], normal["config"]
    taus, h = hurst_curves(runs, NORMAL_AGENTS, "median")
    h_mean = h.mean(axis=0)
    for lag in HURST_LAGS:
        row[f"H({lag:g})"] = hurst_near(taus, h_mean, lag)
    row["kurtosis_800"] = approximate_kurtosis(runs, config["return_bin_edges"]["median"], "median", 800)
    for kind in ("signed", "absolute"):
        values = mean_autocorrelation(runs, NORMAL_AGENTS, "median", kind)
        row[f"autocorr_{kind}"] = None if values is None else float(values[0])
    return row


def plot_summary(rows, out: Path) -> None:
    """Recovery speed against the Hurst exponent, one point per combination."""
    done = [r for r in rows if r["fraction"] > 0]
    control = next((r for r in rows if r["fraction"] == 0), None)
    finite = [r["half_life_300"] for r in done if r["half_life_300"] is not None]
    never = 2 * max(finite) if finite else 1000          # where "never recovers" is drawn
    markers = dict(zip(FRACTIONS, ("o", "s", "^", "D")))
    colours = dict(zip(NEWS, ("C0", "C1", "C2", "C3")))
    sizes = dict(zip(SPREADS, (25, 60, 120)))

    fig, axes = plt.subplots(1, 2, figsize=(15, 5.5))
    for ax, lag in zip(axes, (1000, 10_000)):
        for r in done:
            y = r["half_life_300"] if r["half_life_300"] is not None else never
            x = r[f"H({lag:g})"]
            if x is not None:
                ax.scatter(x, max(y, 0.5), marker=markers[r["fraction"]], c=colours[r["news"]],
                           s=sizes[r["spread"]], alpha=0.8, edgecolors="k", linewidths=0.4)
        if control is not None and control[f"H({lag:g})"] is not None:
            ax.scatter(control[f"H({lag:g})"], never, marker="*", c="k", s=200, label="no value traders")
        ax.axhline(never, color="gray", ls=":", lw=0.8)
        ax.text(ax.get_xlim()[0], never, " never recovers", va="bottom", fontsize=7, color="gray")
        ax.axvline(0.5, color="k", ls="--", lw=0.8)
        ax.set(yscale="log", xlabel=f"H({lag:,}) without a shock (real markets: about 0.5)",
               ylabel="price half-life after a 300-unit sell [steps]",
               title=f"Recovery against H({lag:,})")
    # Legend: marker = share, colour = news, size = spread.
    handles = [plt.Line2D([], [], marker=markers[f], ls="", color="gray", label=f"{f:.0%} value traders") for f in FRACTIONS]
    handles += [plt.Line2D([], [], marker="o", ls="", color=colours[n], label=f"news {n:g}") for n in NEWS]
    handles += [plt.scatter([], [], s=sizes[s], c="white", edgecolors="k", label=f"mean error {s:g}") for s in SPREADS]
    handles += [plt.Line2D([], [], marker="*", ls="", color="k", markersize=12, label="no value traders")]
    axes[1].legend(handles=handles, fontsize=7, loc="upper left", bbox_to_anchor=(1.02, 1))
    fig.suptitle("Value trader sweep: lower is faster recovery, nearer the dashed line is more market-like")
    fig.tight_layout(rect=(0, 0, 0.87, 1))      # leave room on the right for the legend
    fig.savefig(out, dpi=130)
    plt.close(fig)


def collect(out_dir: Path) -> list:
    rows, missing = [], []
    for index in range(len(GRID)):
        row = summarise_index(index, out_dir)
        (rows.append(row) if row is not None else missing.append(name_of(index)))
    if missing:
        print(f"{len(missing)} of {len(GRID)} combinations have not finished: {', '.join(missing)}")
    if not rows:
        raise SystemExit(f"No finished combinations in {out_dir}.")

    def cell(value, fmt, width=7):
        if value is None:
            return f"{'never' if fmt == 'steps' else '-':>{width}}"
        return f"{value:>{width}}" if fmt == "steps" else f"{value:>{width}{fmt}}"
    print(f"\n{'combination':22} | {'half-life':>9} {'(150)':>6} | " + " ".join(f"{'H(' + format(l, 'g') + ')':>7}" for l in HURST_LAGS)
          + f" | {'kurt.':>6} {'ac(1)':>7} {'|ac|(1)':>7}")
    for r in rows:
        print(f"{r['name']:22} | {cell(r['half_life_300'], 'steps', 9)} {cell(r['half_life_150'], 'steps', 6)} | "
              + " ".join(cell(r[f'H({l:g})'], '.2f') for l in HURST_LAGS)
              + f" | {cell(r['kurtosis_800'], '.2f', 6)} {cell(r['autocorr_signed'], '.3f')} {cell(r['autocorr_absolute'], '.3f')}")
    print("\nhalf-life: steps until half of the price drop after a 300-unit (150-unit) sell is undone. "
          "H, kurtosis (800-step changes)\nand autocorrelations are from runs without a shock, N_A = 500, median price.")

    csv_out = out_dir / "summary.csv"
    with open(csv_out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    png_out = out_dir / "summary.png"
    plot_summary(rows, png_out)
    print(f"saved {csv_out} and {png_out}")
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
    run_cmd.add_argument("--shock-only", action="store_true",
                         help="run only the shock test (e.g. to redo it after a change to how recovery is measured)")
    for sub in (run_cmd, commands.add_parser("collect", help="summary table and figure")):
        sub.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)

    if args.command == "list":
        for index in range(len(GRID)):
            fraction, news, spread = GRID[index]
            what = "no value traders" if fraction == 0 else (
                f"{fraction:.0%} value traders ({shock_traders(fraction)} of 250 in the shock test), "
                f"news {news:g}, mean error {spread:g}")
            print(f"{index:3d}  {name_of(index):22}  {what}")
    elif args.command == "run":
        if not 0 <= args.index < len(GRID):
            parser.error(f"--index must be 0 to {len(GRID) - 1}")
        run_index(args.index, args.workers, args.n_steps, args.n_runs, args.shock_runs, args.shock_after, args.out_dir,
                  args.shock_only)
    else:
        collect(args.out_dir)


if __name__ == "__main__":
    main()
