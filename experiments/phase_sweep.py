"""
Phase diagram sweep: value traders against momentum traders, at four system sizes (docs/decisions.md,
D36). Value traders pull the price back to the true value; momentum traders push it further the way
it is going. As the momentum share rises against the value share, the market should change from
recovering after a shock to running away. Near that change the time to recover (a relaxation time)
and the range of the correlation functions may grow, and the change should get sharper as the system
gets bigger.

Every combination of these settings is tried:

    N_A                                         125, 250, 500, 1000
    share of the takers that are value traders  0, 5, 10, 20, 40, 60%
    share that are momentum traders (order 1)   0, 10, 20, 30, 40, 50, 60, 80%

with value + momentum at most 100%: 44 points at each N_A, 176 in all, numbered 0 to 175 (see `list`;
the largest N_A first, as they take longest). Each one is three experiments:

    normal     experiments/run.py, no shocks: 16 runs of 10^6 steps. The order parameter (the
               correlation of consecutive 50-step price changes: negative = the price reverts,
               positive = it trends), H(delta tau), and the autocorrelation functions.
    pressure   experiments/pressure.py, twice: the Poisson trader with mean orders of a quarter and
               of half of one side of the book (0.6 and 1.2 units per agent; at N_A = 250, 150 and
               300 units). The time to recover, the lowest point, and impact against size.

Value traders have a mean error of 50 ticks and a true value step of 1; momentum traders a window of
50 steps.

    python -m experiments.phase_sweep list
    python -m experiments.phase_sweep run --index 7 --workers 16
    python -m experiments.phase_sweep collect

`run` is meant for a cluster job array (cluster/phase_sweep.slurm). Results go to
results/phase_sweep/. Running an index again picks up where it stopped. `collect` can be run at any
time; combinations that have not finished are listed as missing.
"""

from __future__ import annotations

import argparse
import csv
import pickle
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from experiments import pressure
from experiments import run as runner
from experiments.plot import approximate_kurtosis, hurst_curves, hurst_near, mean_autocorrelation

SIZES = (1000, 500, 250, 125)                          # N_A, largest first
VALUE_SHARES = (0.0, 0.05, 0.1, 0.2, 0.4, 0.6)
MOMENTUM_SHARES = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8)
POINTS = [(v, m) for v in VALUE_SHARES for m in MOMENTUM_SHARES if v + m <= 1 + 1e-9]
GRID = [(n, v, m) for n in SIZES for v, m in POINTS]
ORDER_SIZES = (0.6, 1.2)          # mean Poisson order, in units per agent: a quarter and half of one side
POISSON_CHANCE = 0.0002
VALUE = {"true_value_step": 1.0, "spread": 50.0}
MOMENTUM_WINDOW = 50
HURST_LAGS = (10, 100, 1000, 10_000)
OUT_DIR = runner.RESULTS_DIR / "phase_sweep"


def name_of(index: int) -> str:
    n, v, m = GRID[index]
    return f"n{n}_v{v:g}_m{m:g}"


def pressure_file(out_dir: Path, name: str, order_size: float) -> Path:
    return out_dir / f"pressure_o{order_size:g}_{name}.pkl"


def run_index(index: int, workers: int, n_steps: int, n_runs: int, pressure_runs: int, out_dir: Path) -> None:
    n, v, m = GRID[index]
    name = name_of(index)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"combination {index}: {name}", flush=True)
    n_value, n_momentum = round(v * n), round(m * n)

    for order_size in ORDER_SIZES:
        out = pressure_file(out_dir, name, order_size)
        if out.exists():
            print(f"{out.name} already done", flush=True)
            continue
        args = ["run", "--n-agents", str(n), "--n-runs", str(pressure_runs), "--workers", str(workers),
                "--poisson-chance", str(POISSON_CHANCE), "--poisson-rate", str(order_size * n * POISSON_CHANCE),
                "--out", str(out)]
        if n_value:
            args += ["--value-traders", str(n_value), "--true-value-step", str(VALUE["true_value_step"]),
                     "--value-spread", str(VALUE["spread"])]
        if n_momentum:
            args += ["--momentum-traders", str(n_momentum), "--momentum-orders", "1",
                     "--momentum-window", str(MOMENTUM_WINDOW)]
        pressure.main(args)

    run_args = ["--n-steps", str(n_steps), "--n-runs", str(n_runs), "--agent-counts", str(n),
                "--workers", str(workers), "--resume", "--out", str(out_dir / f"normal_{name}.pkl")]
    if v:
        run_args += ["--value-fraction", str(v), "--true-value-step", str(VALUE["true_value_step"]),
                     "--value-spread", str(VALUE["spread"])]
    if m:
        run_args += ["--momentum-fraction", str(m), "--momentum-orders", "1", "--momentum-window", str(MOMENTUM_WINDOW)]
    runner.main(run_args)


def summarise_index(index: int, out_dir: Path):
    """One row of the summary table and the mean autocorrelation functions, or None if unfinished."""
    name = name_of(index)
    normal_file = out_dir / f"normal_{name}.pkl"
    pressure_files = [pressure_file(out_dir, name, o) for o in ORDER_SIZES]
    if not (normal_file.exists() and all(f.exists() for f in pressure_files)):
        return None
    n, v, m = GRID[index]
    row = {"index": index, "name": name, "n_agents": n, "value": v, "momentum": m}

    with open(normal_file, "rb") as f:
        normal = pickle.load(f)
    runs, config = normal["runs"], normal["config"]
    taus, h = hurst_curves(runs, n, "median")
    h_mean = h.mean(axis=0)
    for lag in HURST_LAGS:
        row[f"H({lag:g})"] = hurst_near(taus, h_mean, lag)
    edges = config["return_bin_edges"]["median"]
    counts = sum(r["return_counts"]["median"][200] for r in runs if r["n_agents"] == n)
    centres = np.sqrt(edges[:-1] * edges[1:])
    row["rms_200"] = float(np.sqrt((counts / counts.sum() * centres ** 2).sum()))
    row["kurtosis_200"] = approximate_kurtosis(runs, edges, "median", 200, n)
    curves = {}
    for kind in ("signed", "absolute"):
        values = mean_autocorrelation(runs, n, "median", kind)
        curves[kind] = values
        row[f"autocorr_{kind}"] = None if values is None else float(values[0])
    row["mid_gaps"] = int(sum(r.get("mid_gaps", 0) for r in runs))

    for order_size, path in zip(ORDER_SIZES, pressure_files):
        with open(path, "rb") as f:
            data = pickle.load(f)
        s = pressure.band_summary(data["bands"]["all"]["mean"])
        tag = f"o{order_size:g}"
        row[f"impact_{tag}"] = s["impact"]
        row[f"lowest_{tag}"] = s["lowest"]
        row[f"half_life_{tag}"] = s["half-life"]
        row[f"recovered_{tag}"] = s["recovered"]
        row[f"emptied_{tag}"] = data["bands"]["all"]["emptied"] / data["n_used"]
        row[f"impact_power_{tag}"] = pressure.impact_power(data["sizes"], data["impacts"], n)[3]
    return row, curves


def plot_heatmaps(rows, key: str, title: str, out: Path, log: bool = False, centred: bool = False) -> None:
    """One panel per N_A: rows = value share, columns = momentum share, colour = the value of `key`."""
    values = [r[key] for r in rows if r[key] is not None and np.isfinite(r[key])]
    if not values:
        return
    if log:
        values = [x for x in values if x > 0]
    vmin, vmax = min(values), max(values)
    if centred:
        vmax = max(abs(vmin), abs(vmax))
        vmin = -vmax
    fig, axes = plt.subplots(1, len(SIZES), figsize=(5 * len(SIZES), 4.6), sharey=True)
    for ax, n in zip(axes, sorted(SIZES)):
        grid = np.full((len(VALUE_SHARES), len(MOMENTUM_SHARES)), np.nan)
        never = np.zeros_like(grid, dtype=bool)
        for r in rows:
            if r["n_agents"] == n:
                i, j = VALUE_SHARES.index(r["value"]), MOMENTUM_SHARES.index(r["momentum"])
                if r[key] is None:
                    never[i, j] = True
                else:
                    grid[i, j] = r[key]
        shown = np.log10(np.where(grid > 0, grid, np.nan)) if log else grid
        im = ax.imshow(shown, origin="lower", aspect="auto", cmap="RdBu_r" if centred else "viridis",
                       vmin=np.log10(vmin) if log else vmin, vmax=np.log10(vmax) if log else vmax)
        for i in range(grid.shape[0]):
            for j in range(grid.shape[1]):
                text = "never" if never[i, j] else ("" if np.isnan(grid[i, j]) else f"{grid[i, j]:.3g}")
                ax.text(j, i, text, ha="center", va="center", fontsize=6.5, color="k" if centred else "w")
        ax.set_xticks(range(len(MOMENTUM_SHARES)), [f"{s:.0%}" for s in MOMENTUM_SHARES], fontsize=8)
        ax.set_yticks(range(len(VALUE_SHARES)), [f"{s:.0%}" for s in VALUE_SHARES], fontsize=8)
        ax.set_title(f"N$_A$ = {n}")
        ax.set_xlabel("momentum traders (share of takers)")
    axes[0].set_ylabel("value traders (share of takers)")
    fig.colorbar(im, ax=axes, shrink=0.85, label=("log10 of " if log else "") + key)
    fig.suptitle(title)
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)


def collect(out_dir: Path) -> list:
    rows, curves, missing = [], {}, []
    for index in range(len(GRID)):
        result = summarise_index(index, out_dir)
        if result is None:
            missing.append(name_of(index))
            continue
        row, curve = result
        rows.append(row)
        curves[(row["n_agents"], row["value"], row["momentum"])] = curve
    print(f"{len(rows)} of {len(GRID)} combinations finished"
          + (f"; missing: {', '.join(missing)}" if 0 < len(missing) <= 20 else ""))
    if not rows:
        raise SystemExit(f"No finished combinations in {out_dir}.")

    def cell(value, fmt, width=7):
        if value is None:
            return f"{'never' if fmt == 'steps' else '-':>{width}}"
        return f"{value:>{width}}" if fmt == "steps" else f"{value:>{width}{fmt}}"
    print(f"\n{'combination':18} | {'ac(1)':>7} {'|ac|(1)':>7} {'H(100)':>6} {'H(1e3)':>6} {'RMS200':>7} {'kurt.':>6} | "
          f"{'impact':>7} {'lowest':>7} {'half-l.':>7} {'emptied':>7} || {'lowest':>7} {'half-l.':>7} {'emptied':>7}")
    for r in rows:
        print(f"{r['name']:18} | {cell(r['autocorr_signed'], '.3f')} {cell(r['autocorr_absolute'], '.3f')} "
              f"{cell(r['H(100)'], '.2f', 6)} {cell(r['H(1000)'], '.2f', 6)} {cell(r['rms_200'], '.1f')} "
              f"{cell(r['kurtosis_200'], '.2f', 6)} | {cell(r['impact_o0.6'], '.1f')} {cell(r['lowest_o0.6'], '.1f')} "
              f"{cell(r['half_life_o0.6'], 'steps')} {cell(r['emptied_o0.6'], '.2f')} || "
              f"{cell(r['lowest_o1.2'], '.1f')} {cell(r['half_life_o1.2'], 'steps')} {cell(r['emptied_o1.2'], '.2f')}")
    print("\nac(1) = correlation of consecutive 50-step price changes (negative = reverts, positive = trends); "
          "|ac|(1) the same for their size.\nPoisson orders (all sizes together, shown as sells, in ticks): left of || "
          "a mean order of a quarter of one side, right\nof it half of one side; 'emptied' = share of orders that "
          "emptied the other side of the book.")

    csv_out = out_dir / "summary.csv"
    with open(csv_out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with open(out_dir / "autocorrelations.pkl", "wb") as f:
        pickle.dump({"interval": runner.AUTOCORR_INTERVAL, "curves": curves}, f)
    figures = [("autocorr_signed", "Order parameter: correlation of consecutive 50-step price changes", "phase_order", False, True),
               ("autocorr_absolute", "Volatility clustering: correlation of the size of consecutive 50-step changes",
                "phase_volatility", False, False),
               ("half_life_o0.6", "Time to recover from an order of a quarter of one side (half-life, steps)",
                "phase_half_life_quarter", True, False),
               ("half_life_o1.2", "Time to recover from an order of half of one side (half-life, steps)",
                "phase_half_life_half", True, False),
               ("lowest_o0.6", "Lowest point after an order of a quarter of one side (ticks)", "phase_lowest_quarter", False, False),
               ("H(100)", "Hurst exponent at a lag of 100 steps", "phase_hurst100", False, False),
               ("rms_200", "Typical price move over 200 steps (ticks)", "phase_rms", True, False),
               ("kurtosis_200", "Kurtosis of the change over 200 steps (Gaussian = 3)", "phase_kurtosis", False, False)]
    for key, title, stem, log, centred in figures:
        plot_heatmaps(rows, key, title, out_dir / f"{stem}.png", log, centred)
    print(f"saved {csv_out}, autocorrelations.pkl and the phase_*.png figures in {out_dir}")
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="show the combinations and their numbers")
    run_cmd = commands.add_parser("run", help="run one combination (all three experiments)")
    run_cmd.add_argument("--index", type=int, required=True, help=f"0 to {len(GRID) - 1}")
    run_cmd.add_argument("--workers", type=int, required=True,
                         help="processes to use: the number of CPUs the job was given")
    run_cmd.add_argument("--n-steps", type=int, default=1_000_000, help="steps per normal-times run (default 10^6)")
    run_cmd.add_argument("--n-runs", type=int, default=16, help="normal-times runs (default 16)")
    run_cmd.add_argument("--pressure-runs", type=int, default=64,
                         help="runs of 50,000 steps per Poisson event study (default 64)")
    for sub in (run_cmd, commands.add_parser("collect", help="summary table and figures")):
        sub.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)

    if args.command == "list":
        for index in range(len(GRID)):
            n, v, m = GRID[index]
            print(f"{index:3d}  {name_of(index):18}  N_A = {n}: {round(v * n)} value traders, "
                  f"{round(m * n)} momentum traders, {n - round(v * n) - round(m * n)} ordinary takers")
    elif args.command == "run":
        if not 0 <= args.index < len(GRID):
            parser.error(f"--index must be 0 to {len(GRID) - 1}")
        run_index(args.index, args.workers, args.n_steps, args.n_runs, args.pressure_runs, args.out_dir)
    else:
        collect(args.out_dir)


if __name__ == "__main__":
    main()
