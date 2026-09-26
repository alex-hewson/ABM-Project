"""
Experiment runner for the Preis et al. (2006) figures: runs many independent simulations and saves
the quantities the figures need to one results file. experiments/plot.py draws the figures from it.

Parameters are the paper's (alpha=0.15, mu=0.025, delta=0.025, lambda_0=100, q_provider = 0.5).
--flow chooses how the takers' buy probability q_taker behaves (docs/decisions.md, D16-D19):

    symmetric        constant 1/2                           Fig. 2
    bounded          bounded random walk (Fig. 3a)          Fig. 3a/3b
    mean-reverting   mean-reverting random walk (Fig. 3c)   Fig. 3c/3d

Each flow is a separate experiment with its own results file. Every run stores:
    - RMS price change at ~80 lags from 1 to n_steps/10, for all five price definitions in
      analysis/prices.py (H(delta tau) is derived from these at plot time; see analysis/hurst.py)
    - |price increment| histograms for delta tau = 200, 400, 800, 1600, for all five definitions
    - order book depth around the midpoint over the last 10^4 steps (N_A = 500 only)
    - the mid-price path (N_A = 250, seed 0 only)
    - with a random-walk flow: summary statistics of q_taker, including <(q - 1/2)^2> (Eq. 4)

Runs are independent (one seed each), so they are spread over CPU cores. Each run is also saved
the moment it finishes (see checkpoint.py), so an interrupted experiment can be continued with
--resume. Resuming with a larger --n-runs extends it.

Usage (paper scale is the default: 10^6 steps, 50 runs per N_A; expect hours per flow):
    python -m experiments.run --n-steps 100000 --n-runs 4        # quick check (symmetric)
    python -m experiments.run --out results/fig2.pkl             # Fig. 2 data
    python -m experiments.run --flow bounded --out results/fig3_bounded.pkl
    python -m experiments.run --flow mean-reverting --out results/fig3_mean_reverting.pkl
    ... add --resume to continue after an interruption
"""

from __future__ import annotations

import argparse
import os
import pickle
import shutil
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import numpy as np

from abm.agents import BoundedRandomWalk, MeanRevertingWalk
from abm.simulation import run_simulation
from analysis.hurst import log_spaced_taus, rms_at_lags
from analysis.prices import PRICE_DEFINITIONS, price_series
from analysis.returns import return_counts
from experiments.provenance import git_info, describe
from experiments.checkpoint import (atomic_pickle, parts_dir_for, has_parts, save_meta, load_meta,
                                    save_part, load_parts, check_compatible)

RESULTS_FORMAT = 3           # bump when what each run stores changes, so old files aren't mixed in
PARAMS = dict(alpha=0.15, mu=0.025, delta=0.025, lambda_=100, q_provider=0.5, q_taker=0.5)
AGENT_COUNTS = (125, 250, 500)
PATH_AGENTS = 250            # price path is kept for this N_A (seed 0)
DEPTH_AGENTS = 500           # depth profile and return distributions are plotted for this N_A
DEPTH_WINDOW = 10_000        # depth profile: averaged over this many final steps
RETURN_TAUS = (200, 400, 800, 1600)
LAG_POINTS = 80              # number of log-spaced lags (from 1 to n_steps/10) at which RMS is stored

# Order-flow processes for the takers' buy probability (decisions D16-D19). "symmetric" means no
# process: every taker keeps q_taker = 1/2, exactly the Fig. 2 model.
FLOWS = {
    "symmetric": None,
    "bounded": BoundedRandomWalk,
    "mean-reverting": MeanRevertingWalk,
}


def make_flow(name: str):
    """A NEW flow process for one run (None for "symmetric"). A process carries its position from
    step to step, so reusing one across runs would start later runs where the previous one stopped;
    building it here, inside each job, guarantees every run starts from q = 1/2."""
    if name not in FLOWS:
        raise ValueError(f"unknown flow {name!r}; choose from {tuple(FLOWS)}")
    process_class = FLOWS[name]
    return None if process_class is None else process_class()


def describe_flow(name: str) -> Optional[dict]:
    """The flow's settings, as saved in the results file (None for "symmetric", which keeps
    symmetric files identical in format to those made before flows existed)."""
    flow = make_flow(name)
    if flow is None:
        return None
    return {"name": name, "step": flow.step, "half_width": flow.K * flow.step, "centre": flow.centre}


def make_bin_edges(grid_step: float, min_ticks: float = 1.0, max_ticks: float = 5_000.0,
                   n_points: int = 41) -> np.ndarray:
    """Log-spaced |increment| bin edges for a price series that only takes multiples of
    grid_step (0.5 for the mid-price -- the average of two integer prices; 1.0 for a trade
    price -- an actual traded, integer, price). Edges sit half a grid step off every multiple of
    grid_step, so every bin holds exactly one grid value at the low end (and more at the high end,
    where consecutive log-spaced points are more than one grid step apart). Using edges built for
    the wrong grid spacing leaves alternating bins empty -- e.g. edges for the 0.5 grid, applied to
    an integer series, catch an integer in one bin and nothing in the next -- which shows up as a
    zigzag in the plotted distribution (this happened for the trade-price definitions in an earlier
    version; see docs/decisions.md, D15)."""
    min_i = max(1, round(min_ticks / grid_step))
    max_i = round(max_ticks / grid_step)
    idx = np.unique(np.round(np.logspace(np.log10(min_i), np.log10(max_i), n_points)))
    return (idx - 0.5) * grid_step


# One edge set per price definition: 0.5-tick grid for the mid-price, 1-tick grid for the trade
# prices ("mean" isn't exactly on the 1-tick grid, since it averages several trade prices, but
# it's not concentrated on a sparser grid either, so the 1-tick edges are a reasonable fit).
RETURN_BIN_EDGES = {"mid": make_bin_edges(0.5),
                    **{name: make_bin_edges(1.0) for name in ("last", "first", "median", "mean")}}
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"


def run_one(job):
    """One independent simulation, reduced to the quantities the figures need.
    job = (n_agents, seed, n_steps, flow name)."""
    n_agents, seed, n_steps, flow_name = job
    flow = make_flow(flow_name)                 # fresh for this run
    record_depth = n_agents == DEPTH_AGENTS
    result = run_simulation(
        n_agents=n_agents, n_steps=n_steps, seed=seed,
        depth_record_from=max(0, n_steps - DEPTH_WINDOW) if record_depth else None,
        keep_trades=False,            # millions of Trade objects per run otherwise
        record_trade_prices=True,
        taker_flow=flow,
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
        counts[name] = {tau: return_counts(prices, tau, RETURN_BIN_EDGES[name], absolute=True)
                        for tau in RETURN_TAUS if tau < n_steps}
        if name == "mid":
            mid_path = prices

    q_stats = None
    if flow is not None:
        q = result.q_taker_series
        q_stats = {"mean_sq_dev": float(np.mean((q - flow.centre) ** 2)),   # <(q - 1/2)^2>, for Eq. 4
                   "std": float(q.std()), "min": float(q.min()), "max": float(q.max())}

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
        "q_stats": q_stats,            # None for the symmetric flow
    }


# Settings that must match for saved runs to be combined with new ones.
CHECKED_SETTINGS = ("format", "n_steps", "params", "return_bin_edges", "depth_window",
                    "price_definitions", "lag_points", "flow")


def make_config(n_steps: int, git: dict, flow_name: str = "symmetric") -> dict:
    """The settings that define an experiment; saved with the results and checked on --resume."""
    return {"format": RESULTS_FORMAT, "n_steps": n_steps, "params": PARAMS,
            "return_bin_edges": RETURN_BIN_EDGES, "depth_window": DEPTH_WINDOW,
            "price_definitions": PRICE_DEFINITIONS, "lag_points": LAG_POINTS,
            "flow": describe_flow(flow_name), "git": git}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--flow", choices=tuple(FLOWS), default="symmetric",
                        help="how the takers' buy probability behaves (default: symmetric, Fig. 2)")
    parser.add_argument("--n-steps", type=int, default=1_000_000)
    parser.add_argument("--n-runs", type=int, default=50, help="runs per N_A")
    parser.add_argument("--workers", type=int, default=os.cpu_count())
    parser.add_argument("--out", type=Path, default=None,
                        help="results file (default: results/<flow>.pkl)")
    parser.add_argument("--resume", action="store_true",
                        help="continue an interrupted experiment, skipping runs already saved")
    parser.add_argument("--allow-code-change", action="store_true",
                        help="with --resume: accept saved runs made at a different git commit")
    args = parser.parse_args(argv)
    if args.out is None:
        args.out = RESULTS_DIR / f"{args.flow}.pkl"

    # Captured before the runs start, so it describes the code the workers actually load.
    git = git_info()
    config = make_config(args.n_steps, git, args.flow)

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

    flow = config["flow"]
    print(f"order flow: {args.flow}" + ("" if flow is None else
          f" (step {flow['step']}, half-width {flow['half_width']:g} around {flow['centre']})"))
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
            futures = [pool.submit(run_one, (n, seed, args.n_steps, args.flow)) for n, seed in todo]
            try:
                for count, future in enumerate(as_completed(futures), n_already + 1):
                    r = future.result()   # re-raises any worker exception here
                    key = (r["n_agents"], r["seed"])
                    save_part(parts_dir, key, r)     # saved immediately, so an interruption loses at most the runs in flight
                    finished[key] = r
                    print(f"[{count}/{len(all_keys)}] N_A={r['n_agents']} seed={r['seed']} done "
                          f"({time.perf_counter() - start:.0f}s elapsed, mean book {r['mean_orders']:.0f} orders)",
                          flush=True)
            except BaseException:
                # On any error (a failed run, Ctrl+C, output that can't be written), cancel the runs
                # still queued. Otherwise leaving this block waits for ALL of them to finish -- hours at
                # paper scale -- before the error is shown, and their results are discarded anyway.
                # Runs already in progress still finish; runs saved so far are kept for --resume.
                # wait=True matters: leaving the with-block calls shutdown() again without
                # cancel_futures, which would undo the cancellation if it hadn't taken effect yet.
                pool.shutdown(wait=True, cancel_futures=True)
                raise

    args.out.parent.mkdir(parents=True, exist_ok=True)
    atomic_pickle({"config": {**config, "n_runs": args.n_runs}, "runs": [finished[k] for k in all_keys]}, args.out)
    print(f"saved {args.out} ({time.perf_counter() - start:.0f}s this session)")
    shutil.rmtree(parts_dir)   # everything in it is now in the results file


if __name__ == "__main__":
    main()
