"""
Data generation for Fig. 2 of Preis et al. (2006): the symmetric model
(q_provider = q_taker = 0.5, alpha=0.15, mu=0.025, delta=0.025, lambda_0=100).

    (a) price path of one run, N_A = 250
    (b) order book depth around the midpoint, averaged over the last 10^4 MCS, N_A = 500
    (c) Hurst exponent H(delta tau) for N_A = 125, 250, 500, averaged over runs
    (d) distributions of price increments for delta tau = 200, 400, 800, 1600, N_A = 500

The paper doesn't say which "price" it uses, and the choice changes (c) at short lags, so every
run stores results for ALL the definitions in analysis/prices.py (mid, last, first, median, mean).
For (c) it stores the RMS price change at ~80 lags from 1 to n_steps/10, not finished H values;
plot_fig2.py derives H from those (see analysis/hurst.py), so lag spacing and price definition
can be changed later without re-simulating.

Runs are independent (one seed each), so they are spread over CPU cores. Only small derived
quantities are kept per run, and everything is saved to one pickle so that plot_fig2.py can
redraw figures without re-simulating.

Each run is also saved the moment it finishes (see checkpoint.py), so an interrupted
experiment can be continued with --resume. Resuming with a larger --n-runs extends it.

Usage (paper scale is the default; expect hours):
    python -m experiments.fig2 --n-steps 100000 --n-runs 4    # quick check
    python -m experiments.fig2                                 # 10^6 steps, 50 runs per N_A
    python -m experiments.fig2 --resume                        # continue after an interruption
"""

from __future__ import annotations

import argparse
import os
import pickle
import shutil
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from abm.simulation import run_simulation
from analysis.hurst import log_spaced_taus, rms_at_lags
from analysis.prices import PRICE_DEFINITIONS, price_series
from analysis.returns import return_counts
from experiments.provenance import git_info, describe
from experiments.checkpoint import (atomic_pickle, parts_dir_for, has_parts, save_meta, load_meta,
                                    save_part, load_parts, check_compatible)

RESULTS_FORMAT = 2           # bump when what each run stores changes, so old files aren't mixed in
PARAMS = dict(alpha=0.15, mu=0.025, delta=0.025, lambda_=100, q_provider=0.5, q_taker=0.5)
AGENT_COUNTS = (125, 250, 500)
PATH_AGENTS = 250            # panel (a)
DEPTH_AGENTS = 500           # panel (b) and (d)
DEPTH_WINDOW = 10_000        # panel (b): average depth over this many final steps
RETURN_TAUS = (200, 400, 800, 1600)
LAG_POINTS = 80              # number of log-spaced lags (from 1 to n_steps/10) at which RMS is stored
# |increment| bins in ticks, log-spaced. Mid-prices live on a half-tick grid, so edges are placed
# 0.25 tick off the grid: every bin then holds a whole number of grid values, and there are no
# spurious bumps from bins that happen to catch more or fewer grid points.
_half_ticks = np.unique(np.round(np.logspace(np.log10(2), np.log10(10_000), 41)))
RETURN_BIN_EDGES = (_half_ticks - 0.5) / 2
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"


def run_one(job):
    """One independent simulation, reduced to the quantities the figure needs."""
    n_agents, seed, n_steps = job
    record_depth = n_agents == DEPTH_AGENTS
    result = run_simulation(
        n_agents=n_agents, n_steps=n_steps, seed=seed,
        depth_record_from=max(0, n_steps - DEPTH_WINDOW) if record_depth else None,
        keep_trades=False,            # millions of Trade objects per run otherwise
        record_trade_prices=True,
        **PARAMS,
    )

    taus = np.array(log_spaced_taus(1, n_steps // 10, LAG_POINTS))
    rms, counts, mid_path = {}, {}, None
    for name in PRICE_DEFINITIONS:
        try:
            prices = price_series(result, name)
        except ValueError as error:
            raise ValueError(f"N_A={n_agents}, seed={seed}, price={name}: {error}") from error
        rms[name] = rms_at_lags(prices, taus)
        counts[name] = {tau: return_counts(prices, tau, RETURN_BIN_EDGES, absolute=True)
                        for tau in RETURN_TAUS if tau < n_steps}
        if name == "mid":
            mid_path = prices

    return {
        "n_agents": n_agents,
        "seed": seed,
        "taus": taus,
        "rms": rms,                    # {price definition: RMS price change at each lag in taus}
        "return_counts": counts,       # {price definition: {delta tau: histogram counts of |increment|}}
        "depth_sum": result.depth_profile_sum,
        "n_depth_snapshots": result.n_depth_snapshots,
        "mean_orders": float(np.mean(result.total_orders_series)),
        "n_trades": result.n_trades,
        "n_match_failures": result.n_match_failures,
        "price_path": mid_path if (n_agents == PATH_AGENTS and seed == 0) else None,   # mid-price
    }


# Settings that must match for saved runs to be combined with new ones.
CHECKED_SETTINGS = ("format", "n_steps", "params", "return_bin_edges", "depth_window",
                    "price_definitions", "lag_points")


def make_config(n_steps: int, git: dict) -> dict:
    """The settings that define an experiment; saved with the results and checked on --resume."""
    return {"format": RESULTS_FORMAT, "n_steps": n_steps, "params": PARAMS,
            "return_bin_edges": RETURN_BIN_EDGES, "depth_window": DEPTH_WINDOW,
            "price_definitions": PRICE_DEFINITIONS, "lag_points": LAG_POINTS, "git": git}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n-steps", type=int, default=1_000_000)
    parser.add_argument("--n-runs", type=int, default=50, help="runs per N_A")
    parser.add_argument("--workers", type=int, default=os.cpu_count())
    parser.add_argument("--out", type=Path, default=RESULTS_DIR / "fig2_data.pkl")
    parser.add_argument("--resume", action="store_true",
                        help="continue an interrupted experiment, skipping runs already saved")
    parser.add_argument("--allow-code-change", action="store_true",
                        help="with --resume: accept saved runs made at a different git commit")
    args = parser.parse_args(argv)

    # Captured before the runs start, so it describes the code the workers actually load.
    git = git_info()
    config = make_config(args.n_steps, git)

    parts_dir = parts_dir_for(args.out)
    if has_parts(parts_dir) and not args.resume:
        raise SystemExit(f"Partial results from an earlier, unfinished run exist in {parts_dir}.\n"
                         f"  To continue that run, add --resume.\n"
                         f"  To start over, delete that folder or choose a different --out.")

    # With --resume, runs come from two places: the parts of an interrupted run, and the final
    # results file of an earlier completed run (so an experiment can be extended with more seeds).
    finished = {}
    saved_configs = []
    if args.resume and args.out.exists():
        with open(args.out, "rb") as f:
            previous = pickle.load(f)
        saved_configs.append(previous["config"])
        finished.update({(r["n_agents"], r["seed"]): r for r in previous["runs"]})
    if args.resume and has_parts(parts_dir):
        saved_configs.append(load_meta(parts_dir))
        finished.update(load_parts(parts_dir))

    for saved in saved_configs:
        try:
            check_compatible(saved, config, CHECKED_SETTINGS, allow_code_change=args.allow_code_change)
        except ValueError as error:
            raise SystemExit(str(error))
    if saved_configs:
        # Keep describing the code that made the saved runs; note the current one if it differs.
        config["git"] = saved_configs[0].get("git")
        if (config["git"] or {}).get("commit") != git["commit"]:
            config["resumed_with_git"] = git

    all_keys = [(n, seed) for n in AGENT_COUNTS for seed in range(args.n_runs)]
    extra = sorted(set(finished) - set(all_keys))
    if extra:
        raise SystemExit(f"The saved runs include {len(extra)} beyond --n-runs={args.n_runs} (e.g. N_A={extra[0][0]}, "
                         f"seed={extra[0][1]}). Writing the results file would drop them; raise --n-runs.")
    if not has_parts(parts_dir):
        save_meta(parts_dir, config)

    # Slowest jobs (largest N_A) first so the pool doesn't end waiting on one long run.
    todo = sorted((k for k in all_keys if k not in finished), key=lambda k: -k[0])

    print(f"{len(all_keys)} runs ({args.n_runs} per N_A in {AGENT_COUNTS}), {args.n_steps:,} steps each, "
          f"{args.workers} workers")
    print(f"code version: {describe(config['git'])}")
    if git["dirty"]:
        print("WARNING: uncommitted changes -- these results won't match any single commit. "
              "Commit first if you want them reproducible.")
    n_already = len(all_keys) - len(todo)
    if n_already:
        print(f"resuming: {n_already} of {len(all_keys)} runs already saved, {len(todo)} to go")

    start = time.perf_counter()
    if todo:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(run_one, (n, seed, args.n_steps)) for n, seed in todo]
            for count, future in enumerate(as_completed(futures), n_already + 1):
                r = future.result()   # re-raises any worker exception here
                key = (r["n_agents"], r["seed"])
                save_part(parts_dir, key, r)     # saved immediately, so an interruption loses at most the runs in flight
                finished[key] = r
                print(f"[{count}/{len(all_keys)}] N_A={r['n_agents']} seed={r['seed']} done "
                      f"({time.perf_counter() - start:.0f}s elapsed, mean book {r['mean_orders']:.0f} orders)",
                      flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    atomic_pickle({"config": {**config, "n_runs": args.n_runs}, "runs": [finished[k] for k in all_keys]}, args.out)
    print(f"saved {args.out} ({time.perf_counter() - start:.0f}s this session)")
    shutil.rmtree(parts_dir)   # everything in it is now in the results file


if __name__ == "__main__":
    main()
