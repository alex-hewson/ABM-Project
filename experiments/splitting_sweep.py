"""
Order splitting trial (docs/takers/decisions.md, D42): random takers and splitters together, with
fixed-depth providers, over every combination of:

    lambda_0     100, 7 ticks (fixed-depth providers)
    alpha        1.4, 1.6, 1.8 (tail exponent of the hidden order sizes)
    N            1, 2, 3, 5, 10 (hidden orders active at once)
    f            0.5, 0.7, 0.85, 1.0 (share of takers that are splitters)
    q(t)         on, off for the random takers (once for f = 1, which has no random takers)

That is 2 x 3 x 5 x (3 x 2 + 1) = 210 jobs, numbered 0 to 209 (see `list`). Each is N_A = 500, 4 runs
of 120,000 steps, the first 20,000 left out, as in the earlier trials. Each is judged by the D38 check
on the mid-price and set beside the E-mini's per-order sign autocorrelation (D41).

    python -m experiments.splitting_sweep list
    python -m experiments.splitting_sweep run --index 7 --workers 4
    python -m experiments.splitting_sweep collect

`run` is meant for a cluster job array (cluster/splitting_sweep.slurm). Results go to
results/splitting_sweep/; running an index again skips it if it is done. `collect` writes
summary.csv, prints a table for each lambda_0 and alpha, and draws the sign autocorrelation and H
against lag beside the E-mini's (signs.png, hurst.png).
"""

from __future__ import annotations

import argparse
import csv
import itertools
import pickle
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from abm.order_splitting import SplittingSettings
from abm.simulation import run_simulation
from analysis.stylised import KURTOSIS_LAGS, LAGS, PRICE, SIGN_LAGS, stylised_facts
from experiments import run as runner
from experiments import volatility_sweep as first
from experiments.common import trade_segment
from experiments.provenance import describe, git_info

N_AGENTS = 500
LAMBDAS = (100, 7)
ALPHAS = (1.4, 1.6, 1.8)
NS = (1, 2, 3, 5, 10)
SHARES = (0.5, 0.7, 0.85, 1.0)
GRID = [(lam, alpha, n, f, q) for lam, alpha, n, f in itertools.product(LAMBDAS, ALPHAS, NS, SHARES)
        for q in ((True, False) if f < 1 else (False,))]
OUT_DIR = runner.RESULTS_DIR / "splitting_sweep"
EMINI = first.EMINI
SIGN_REPORT = (1, 10, 100, 1000)


def name_of(index: int) -> str:
    lam, alpha, n, f, q = GRID[index]
    taker = "" if f == 1 else ("_qon" if q else "_qoff")
    return f"lam{lam}_a{alpha:g}_N{n}_f{f:g}{taker}"


def run_one(task):
    """One run of one combination: its trade-time segment, and what the hidden orders did."""
    index, seed, n_steps, skip = task
    lam, alpha, n, f, q = GRID[index]
    r = run_simulation(n_agents=N_AGENTS, n_steps=n_steps, seed=seed, keep_trades=False, record_sides=True,
                       record_trades=True, taker_flow=runner.make_flow("mean-reverting") if q else None,
                       splitting=SplittingSettings(share=f, n_hidden=n, alpha=alpha),
                       **{**runner.PARAMS, "lambda_": lam})
    sizes = r.hidden_order_sizes
    return trade_segment(r, skip), {"n_hidden_orders": int(len(sizes)), "largest_hidden": int(sizes.max()),
                                    "mean_hidden": float(sizes.mean()), "hidden_1000_plus": int(np.sum(sizes >= 1000)),
                                    "mid_gaps": int(sum(m is None for m in r.mid_price_series)),
                                    "match_failures": int(r.n_match_failures)}


def run_index(index: int, workers: int, n_runs: int, n_steps: int, skip: int, out_dir: Path) -> None:
    out = out_dir / f"{name_of(index)}.pkl"
    if out.exists():
        print(f"{out.name} already done")
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"job {index}: {name_of(index)}", flush=True)
    start = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(run_one, [(index, seed, n_steps, skip) for seed in range(n_runs)]))
    facts = stylised_facts([seg for seg, _ in results])
    hidden = {"n_hidden_orders": sum(h["n_hidden_orders"] for _, h in results),
              "largest_hidden": max(h["largest_hidden"] for _, h in results),
              "largest_per_run": [h["largest_hidden"] for _, h in results],
              "mean_hidden": float(np.mean([h["mean_hidden"] for _, h in results])),
              "hidden_1000_plus": sum(h["hidden_1000_plus"] for _, h in results),
              "mid_gaps": sum(h["mid_gaps"] for _, h in results),
              "match_failures": sum(h["match_failures"] for _, h in results)}
    lam, alpha, n, f, q = GRID[index]
    data = {"index": index, "name": name_of(index), "lambda_0": lam, "alpha": alpha, "n_hidden": n, "share": f,
            "q_on": q, "facts": facts, "hidden": hidden, "check": first.check(facts),
            "n_runs": n_runs, "n_steps": n_steps, "skip": skip, "git": git_info()}
    with open(out, "wb") as fh:
        pickle.dump(data, fh)
    c, g = data["check"], facts["signs"]
    print(f"{facts['n_trades']:,} trades, {time.perf_counter() - start:.0f}s; sign autocorrelation at lag 1 "
          f"{g['autocorr'][0]:+.3f}, gamma {g['gamma']:.2f}; largest hidden order {hidden['largest_hidden']:,}; "
          f"(a) {c['a_fat_tails_fading']}, (b) {c['b_random_walk']}, (c) {c['c_bounce_only']}")


def sign_at(signs: dict, lag: int) -> float:
    return float(signs["autocorr"][list(signs["lags"]).index(lag)])


def row_of(data: dict) -> dict:
    f = data["facts"]
    t, g = f[PRICE], f["signs"]
    row = {k: data[k] for k in ("index", "name", "lambda_0", "alpha", "n_hidden", "share", "q_on")}
    row.update({f"kurtosis_{lag}": t["kurtosis"][lag] for lag in KURTOSIS_LAGS})
    row.update({"H_10": t["hurst"][first.nearest(10)], "H_1000": t["hurst"][first.nearest(1000)],
                "ac1": t["autocorr"][1]["signed"][0], "ac100_lag1": t["autocorr"][100]["signed"][0]})
    row.update({f"sign_{lag}": sign_at(g, lag) for lag in SIGN_REPORT})
    row.update({"sign_gamma": g["gamma"], "mid_moves": 1 - t["zero_steps"], "spread": f["spread"]["mean"],
                "spread_1_tick": f["spread"]["shares"][1], "best_size_median": f["best_size"]["quantiles"][50]})
    row.update({k: v for k, v in data["hidden"].items() if k != "largest_per_run"})
    row.update(first.check(f))      # redone from the saved statistics, as in the earlier trials
    return row


def collect(out_dir: Path, emini: Path) -> list:
    datas = []
    for index in range(len(GRID)):
        path = out_dir / f"{name_of(index)}.pkl"
        if path.exists():
            with open(path, "rb") as fh:
                datas.append(pickle.load(fh))
    print(f"{len(datas)} of {len(GRID)} jobs finished")
    if not datas:
        raise SystemExit(f"No finished jobs in {out_dir}.")
    rows = [row_of(d) for d in datas]
    with open(out_dir / "summary.csv", "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    e = None
    if emini.exists():
        with open(emini, "rb") as fh:
            e = pickle.load(fh)
    if e is not None and "signs" in e:
        o, t = e["signs"]["orders"], e[PRICE]
        per_order = {"lags": e["signs"]["lags"], "autocorr": o["autocorr"]}
        values = ", ".join(f"{sign_at(per_order, lag):+.3f}" for lag in SIGN_REPORT)
        print(f"\nE-mini (per order): signs {values} at lags {', '.join(map(str, SIGN_REPORT))}; gamma {o['gamma']:.2f}; "
              f"kurtosis 100/1000 {t['kurtosis'][100]:.2f}/{t['kurtosis'][1000]:.2f}; "
              f"H(1000) {t['hurst'][first.nearest(1000)]:.2f}; ac100 {t['autocorr'][100]['signed'][0]:+.2f}")
    for lam, alpha in itertools.product(LAMBDAS, ALPHAS):
        mine = [r for r in rows if r["lambda_0"] == lam and r["alpha"] == alpha]
        if not mine:
            continue
        print(f"\nlambda_0 = {lam}, alpha = {alpha:g}")
        print(f"  {'N':>3} {'f':>5} {'q':>4} | {'s(1)':>6} {'s(10)':>6} {'s(100)':>6} {'s(1e3)':>6} {'gamma':>5} | "
              f"{'k(100)':>6} {'k(1e3)':>6} {'H(1e3)':>6} {'ac100':>6} | {'moves':>6} {'spread':>6} {'largest':>9} | a b c")
        for r in sorted(mine, key=lambda r: (r["n_hidden"], r["share"], not r["q_on"])):
            q = "-" if r["share"] == 1 else ("on" if r["q_on"] else "off")
            print(f"  {r['n_hidden']:>3} {r['share']:>5g} {q:>4} | {r['sign_1']:+6.3f} {r['sign_10']:+6.3f} "
                  f"{r['sign_100']:+6.3f} {r['sign_1000']:+6.3f} {r['sign_gamma']:5.2f} | {r['kurtosis_100']:6.2f} "
                  f"{r['kurtosis_1000']:6.2f} {r['H_1000']:6.2f} {r['ac100_lag1']:+6.2f} | {r['mid_moves']:6.2%} "
                  f"{r['spread']:6.2f} {r['largest_hidden']:>9,} | "
                  + " ".join("y" if r[key] else "-" for key in ("a_fat_tails_fading", "b_random_walk", "c_bounce_only")))
    passes = [r["name"] for r in rows if r["passes"]]
    print(f"\npass all three D38 tests: {', '.join(passes) if passes else 'none'}")

    # Sign autocorrelation and H against lag: one panel per lambda_0 and alpha, one line per N, for
    # f = 0.85 with q off (the Tokyo-like share), beside the E-mini.
    by_key = {(d["lambda_0"], d["alpha"], d["n_hidden"], d["share"], d["q_on"]): d for d in datas}
    colours = {n: plt.cm.viridis(i / (len(NS) - 1)) for i, n in enumerate(NS)}
    for what, filename in (("signs", "signs.png"), ("hurst", "hurst.png")):
        fig, axes = plt.subplots(len(LAMBDAS), len(ALPHAS), figsize=(5 * len(ALPHAS), 4.2 * len(LAMBDAS)), squeeze=False)
        for (i, lam), (j, alpha) in itertools.product(enumerate(LAMBDAS), enumerate(ALPHAS)):
            ax = axes[i, j]
            for n in NS:
                d = by_key.get((lam, alpha, n, 0.85, False))
                if d is None:
                    continue
                if what == "signs":
                    ac = d["facts"]["signs"]["autocorr"]
                    ax.plot(SIGN_LAGS, np.where(ac > 0, ac, np.nan), "o-", ms=2, color=colours[n], lw=1, label=f"N = {n}")
                else:
                    ax.plot(LAGS, d["facts"][PRICE]["hurst"], color=colours[n], lw=1, label=f"N = {n}")
            if e is not None and what == "signs" and "signs" in e:
                ac = e["signs"]["orders"]["autocorr"]
                ax.plot(e["signs"]["lags"], np.where(ac > 0, ac, np.nan), "k-", lw=2, label="E-mini (per order)")
            elif e is not None and what == "hurst":
                ax.plot(LAGS, e[PRICE]["hurst"], "k-", lw=2, label="E-mini")
            if what == "signs":
                ax.set(xscale="log", yscale="log", ylim=(1e-3, 1.2), xlabel="lag [trades]", ylabel="sign autocorrelation")
            else:
                ax.axhline(0.5, color="gray", lw=0.6, ls=":")
                ax.set(xscale="log", xlabel="lag [trades]", ylabel="H (mid-price)")
            ax.set_title(f"λ₀ = {lam}, α = {alpha:g} (f = 0.85, q off)", fontsize=9)
        if axes[0, 0].get_legend_handles_labels()[0]:
            axes[0, 0].legend(fontsize=7)
        title = "sign autocorrelation" if what == "signs" else "Hurst exponent"
        fig.suptitle(f"Order splitting trial: {title} (N$_A$ = {N_AGENTS}, trade time)", fontsize=11)
        fig.text(0.995, 0.005, "code version: " + describe(datas[0]["git"]), ha="right", va="bottom", fontsize=7, color="gray")
        fig.tight_layout()
        fig.savefig(out_dir / filename, dpi=120)
        plt.close(fig)
    print(f"saved {out_dir / 'summary.csv'}, {out_dir / 'signs.png'} and {out_dir / 'hurst.png'}")
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
    collect_cmd = commands.add_parser("collect", help="summary tables and figures")
    collect_cmd.add_argument("--emini", type=Path, default=EMINI, help="E-mini statistics to draw alongside, if present")
    for sub in (run_cmd, collect_cmd):
        sub.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    if args.command == "list":
        for index in range(len(GRID)):
            print(f"{index:3d}  {name_of(index)}")
    elif args.command == "run":
        if not 0 <= args.index < len(GRID):
            parser.error(f"--index must be 0 to {len(GRID) - 1}")
        if args.skip >= args.n_steps:
            parser.error("--skip must be smaller than --n-steps")
        run_index(args.index, args.workers, args.n_runs, args.n_steps, args.skip, args.out_dir)
    else:
        collect(args.out_dir, args.emini)


if __name__ == "__main__":
    main()
