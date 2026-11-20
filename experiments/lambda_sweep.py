"""
Mean entry depth trial (docs/volatility_provider/decisions.md, D40): the four strongest volatility
provider setups of the first trial (D39), and ordinary fixed-depth providers as a control, each run
with a smaller mean entry depth lambda_0, to see whether a narrower book brings tests (b) and (c) of
D38 closer to the E-mini.

    lambda_0     30, 10, 8, 7, 6, 5 ticks (100 is the first trial)
    setups       fixed-depth control, and volatility provider setups 105, 21, 35, 84 of the first
                 trial (`python -m experiments.volatility_sweep list`)

That is 6 x 5 = 30 jobs, numbered 0 to 29 (see `list`); 0 to 5 are the controls. Everything else is
as in the first trial: mean-reverting takers, N_A = 500, 4 runs of 120,000 steps, the first 20,000
left out, judged by the D38 check on the mid-price.

    python -m experiments.lambda_sweep list
    python -m experiments.lambda_sweep run --index 7 --workers 4
    python -m experiments.lambda_sweep collect

`run` is meant for a cluster job array (cluster/lambda_sweep.slurm). Results go to
results/lambda_sweep/; running an index again skips it if it is done. `collect` prints a table per
setup (with the first trial's lambda_0 = 100 alongside, if results/volatility_sweep/ is there), writes
summary.csv and draws H and kurtosis against lag for every setup and lambda_0.
"""

from __future__ import annotations

import argparse
import csv
import pickle
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from analysis.stylised import KURTOSIS_LAGS, LAGS, PRICE, stylised_facts
from experiments import run as runner
from experiments import volatility_sweep as first
from experiments.provenance import describe, git_info

LAMBDAS = (30, 10, 8, 7, 6, 5)
SETUPS = (1, 105, 21, 35, 84)          # indices in the first trial's grid; 1 is the fixed-depth control
GRID = [(setup, lam) for setup in SETUPS for lam in LAMBDAS]
OUT_DIR = runner.RESULTS_DIR / "lambda_sweep"
FIRST_DIR = first.OUT_DIR
EMINI = first.EMINI


def name_of(index: int) -> str:
    setup, lam = GRID[index]
    return f"lam{lam}_{first.name_of(setup)}"


def run_one(task):
    index, seed, n_steps, skip = task
    setup, lam = GRID[index]
    return first.simulate(first.GRID[setup], seed, n_steps, skip, lambda_0=lam)


def run_index(index: int, workers: int, n_runs: int, n_steps: int, skip: int, out_dir: Path) -> None:
    out = out_dir / f"{name_of(index)}.pkl"
    if out.exists():
        print(f"{out.name} already done")
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    setup, lam = GRID[index]
    print(f"job {index}: {name_of(index)} (lambda_0 = {lam})", flush=True)
    start = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(run_one, [(index, seed, n_steps, skip) for seed in range(n_runs)]))
    facts = stylised_facts([seg for seg, _ in results])
    depth = {key: float(np.mean([d[key] for _, d in results])) for key in results[0][1]}
    depth["lambda_max"] = max(d["lambda_max"] for _, d in results)
    depth["lambda_min"] = min(d["lambda_min"] for _, d in results)
    data = {"index": index, "name": name_of(index), "setup": setup, "setup_name": first.name_of(setup),
            "lambda_0": lam, "facts": facts, "depth": depth, "check": first.check(facts),
            "n_runs": n_runs, "n_steps": n_steps, "skip": skip, "git": git_info()}
    with open(out, "wb") as f:
        pickle.dump(data, f)
    c = data["check"]
    print(f"{facts['n_trades']:,} trades, {time.perf_counter() - start:.0f}s; spread {facts['spread']['mean']:.2f}; "
          f"mid moves on {1 - facts[PRICE]['zero_steps']:.2%} of trades; "
          f"(a) {c['a_fat_tails_fading']}, (b) {c['b_random_walk']}, (c) {c['c_bounce_only']}")


def row_of(data: dict) -> dict:
    f = data["facts"]
    t = f[PRICE]
    row = {"name": data["name"], "setup": data["setup"], "setup_name": data["setup_name"], "lambda_0": data["lambda_0"]}
    row.update({f"kurtosis_{lag}": t["kurtosis"][lag] for lag in KURTOSIS_LAGS})
    row.update({"H_10": t["hurst"][first.nearest(10)], "H_1000": t["hurst"][first.nearest(1000)],
                "ac1": t["autocorr"][1]["signed"][0], "ac100_lag1": t["autocorr"][100]["signed"][0],
                "mid_moves": 1 - t["zero_steps"], "spread": f["spread"]["mean"], "spread_1_tick": f["spread"]["shares"][1],
                "best_size_median": f["best_size"]["quantiles"][50],
                "trade_per_best": f.get("trade_size", {}).get("per_best_size", float("nan"))})
    row.update(data["depth"])
    row.update(first.check(f))      # redone from the saved statistics, as in the first trial
    return row


def load(out_dir: Path, first_dir: Path) -> list:
    """Every finished job, plus the first trial's lambda_0 = 100 result for each setup, if there."""
    datas = []
    for index in range(len(GRID)):
        path = out_dir / f"{name_of(index)}.pkl"
        if path.exists():
            with open(path, "rb") as f:
                datas.append(pickle.load(f))
    print(f"{len(datas)} of {len(GRID)} jobs finished")
    for setup in SETUPS:
        path = first_dir / f"{first.name_of(setup)}.pkl"
        if path.exists():
            with open(path, "rb") as f:
                d = pickle.load(f)
            d.update(name=f"lam100_{d['name']}", setup=setup, setup_name=first.name_of(setup),
                     lambda_0=runner.PARAMS["lambda_"])
            datas.append(d)
    return datas


def collect(out_dir: Path, first_dir: Path, emini: Path) -> list:
    datas = load(out_dir, first_dir)
    if not datas:
        raise SystemExit(f"No finished jobs in {out_dir}.")
    rows = sorted((row_of(d) for d in datas), key=lambda r: (SETUPS.index(r["setup"]), -r["lambda_0"]))
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "summary.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    for setup in SETUPS:
        mine = [r for r in rows if r["setup"] == setup]
        if not mine:
            continue
        print(f"\n{first.name_of(setup)}")
        print(f"  {'lambda_0':>8} | {'k(1)':>6} {'k(10)':>6} {'k(100)':>6} {'k(1e3)':>6} | {'H(10)':>5} {'H(1e3)':>6} | "
              f"{'ac1':>6} {'ac100':>6} | {'moves':>6} {'spread':>6} {'1 tick':>6} {'queue':>6} | a b c")
        for r in mine:
            print(f"  {r['lambda_0']:>8g} | {r['kurtosis_1']:6.1f} {r['kurtosis_10']:6.1f} {r['kurtosis_100']:6.2f} "
                  f"{r['kurtosis_1000']:6.2f} | {r['H_10']:5.2f} {r['H_1000']:6.2f} | {r['ac1']:+6.2f} {r['ac100_lag1']:+6.2f} | "
                  f"{r['mid_moves']:6.2%} {r['spread']:6.2f} {r['spread_1_tick']:6.0%} {r['best_size_median']:6g} | "
                  + " ".join("y" if r[key] else "-" for key in ("a_fat_tails_fading", "b_random_walk", "c_bounce_only")))
    if emini.exists():
        with open(emini, "rb") as f:
            e = pickle.load(f)
        t = e[PRICE]
        kurt = ", ".join(f"{t['kurtosis'][lag]:.1f}" for lag in KURTOSIS_LAGS)
        print(f"\nE-mini: kurtosis {kurt}; "
              f"H {t['hurst'][first.nearest(10)]:.2f} / {t['hurst'][first.nearest(1000)]:.2f}; "
              f"ac1 {t['autocorr'][1]['signed'][0]:+.2f}, ac100 {t['autocorr'][100]['signed'][0]:+.2f}; "
              f"mid moves on {1 - t['zero_steps']:.2%} of trades; spread {e['spread']['mean']:.2f}, "
              f"1 tick {e['spread']['shares'][1]:.0%}, queue {e['best_size']['quantiles'][50]:g}")
    else:
        e = None
    passes = [r["name"] for r in rows if r["passes"]]
    print(f"\npass all three: {', '.join(passes) if passes else 'none'}")

    # H (top) and kurtosis (bottom) against lag, one column per setup, one line per lambda_0.
    fig, axes = plt.subplots(2, len(SETUPS), figsize=(4 * len(SETUPS), 8), squeeze=False)
    lambdas = sorted({r["lambda_0"] for r in rows}, reverse=True)
    colours = {lam: plt.cm.viridis(i / max(len(lambdas) - 1, 1)) for i, lam in enumerate(lambdas)}
    for col, setup in enumerate(SETUPS):
        top, bottom = axes[0, col], axes[1, col]
        for d in sorted((d for d in datas if d["setup"] == setup), key=lambda d: -d["lambda_0"]):
            t = d["facts"][PRICE]
            label = f"λ₀ = {d['lambda_0']:g}"
            top.plot(LAGS, t["hurst"], color=colours[d["lambda_0"]], lw=1.2, label=label)
            bottom.plot(KURTOSIS_LAGS, [t["kurtosis"][lag] for lag in KURTOSIS_LAGS], "o-", ms=3,
                        color=colours[d["lambda_0"]], lw=1.2, label=label)
        if e is not None:
            top.plot(LAGS, e[PRICE]["hurst"], "k", lw=2, label="E-mini")
            bottom.plot(KURTOSIS_LAGS, [e[PRICE]["kurtosis"][lag] for lag in KURTOSIS_LAGS], "ko-", ms=3, lw=2, label="E-mini")
        top.axhline(0.5, color="gray", lw=0.6, ls=":")
        bottom.axhline(3, color="gray", lw=0.6, ls=":")
        title = "fixed depth (control)" if setup == 1 else f"setup {setup}: {first.name_of(setup)}"
        top.set(xscale="log", title=title, xlabel="lag [trades]", ylabel="H (mid-price)")
        bottom.set(xscale="log", yscale="log", xlabel="lag [trades]", ylabel="kurtosis of mid-price changes")
        top.title.set_fontsize(8)
    axes[0, 0].legend(fontsize=7)
    fig.suptitle(f"Mean entry depth trial (N$_A$ = {first.N_AGENTS}, trade time, mid-price)", fontsize=11)
    fig.text(0.995, 0.005, "code version: " + describe(datas[0]["git"]), ha="right", va="bottom", fontsize=7, color="gray")
    fig.tight_layout()
    fig.savefig(out_dir / "summary.png", dpi=120)
    plt.close(fig)
    print(f"saved {out_dir / 'summary.csv'} and {out_dir / 'summary.png'}")
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="show the jobs and their numbers")
    run_cmd = commands.add_parser("run", help="run one job")
    run_cmd.add_argument("--index", type=int, required=True, help=f"0 to {len(GRID) - 1}")
    run_cmd.add_argument("--workers", type=int, required=True, help="processes to use: the CPUs the job was given")
    run_cmd.add_argument("--n-runs", type=int, default=4, help="runs per job (default 4)")
    run_cmd.add_argument("--n-steps", type=int, default=120_000, help="steps per run (default 120,000)")
    run_cmd.add_argument("--skip", type=int, default=20_000, help="steps left out at the start of each run (default 20,000)")
    collect_cmd = commands.add_parser("collect", help="summary tables and figure")
    collect_cmd.add_argument("--first-dir", type=Path, default=FIRST_DIR, help="first trial's results, for lambda_0 = 100")
    collect_cmd.add_argument("--emini", type=Path, default=EMINI, help="E-mini statistics to draw alongside, if present")
    for sub in (run_cmd, collect_cmd):
        sub.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    if args.command == "list":
        for index, (setup, lam) in enumerate(GRID):
            g = first.GRID[setup]
            print(f"{index:3d}  {name_of(index):44}  lambda_0 = {lam:>3}  " + (g if isinstance(g, str) else g.describe()))
    elif args.command == "run":
        if not 0 <= args.index < len(GRID):
            parser.error(f"--index must be 0 to {len(GRID) - 1}")
        if args.skip >= args.n_steps:
            parser.error("--skip must be smaller than --n-steps")
        run_index(args.index, args.workers, args.n_runs, args.n_steps, args.skip, args.out_dir)
    else:
        collect(args.out_dir, args.first_dir, args.emini)


if __name__ == "__main__":
    main()
