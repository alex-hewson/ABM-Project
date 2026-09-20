"""
Data generation for Fig. 2 of Preis et al. (2006): the symmetric model
(q_provider = q_taker = 0.5, alpha=0.15, mu=0.025, delta=0.025, lambda_0=100).

    (a) price path of one run, N_A = 250
    (b) order book depth around the midpoint, averaged over the last 10^4 MCS, N_A = 500
    (c) Hurst exponent H(delta tau) for N_A = 125, 250, 500, averaged over runs
    (d) distributions of price increments for delta tau = 200, 400, 800, 1600, N_A = 500

Runs are independent (one seed each), so they are spread over CPU cores. Only
small derived quantities are kept per run, and everything is saved to one
pickle so that plot_fig2.py can redraw figures without re-simulating.

Usage (paper scale is the default; expect hours):
    python fig2.py --n-steps 100000 --n-runs 4          # quick check
    python fig2.py                                       # 10^6 steps, 50 runs per N_A
"""

from __future__ import annotations

import argparse
import os
import pickle
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from simulation import run_simulation
from hurst import hurst_curve
from returns import return_counts

PARAMS = dict(alpha=0.15, mu=0.025, delta=0.025, lambda_=100, q_provider=0.5, q_taker=0.5)
AGENT_COUNTS = (125, 250, 500)
PATH_AGENTS = 250            # panel (a)
DEPTH_AGENTS = 500           # panel (b) and (d)
DEPTH_WINDOW = 10_000        # panel (b): average depth over this many final steps
RETURN_TAUS = (200, 400, 800, 1600)
# |increment| bins in ticks, log-spaced. Mid-prices live on a half-tick grid, so edges are placed
# 0.25 tick off the grid: every bin then holds a whole number of grid values, and there are no
# spurious bumps from bins that happen to catch more or fewer grid points.
_half_ticks = np.unique(np.round(np.logspace(np.log10(2), np.log10(10_000), 41)))
RETURN_BIN_EDGES = (_half_ticks - 0.5) / 2
RESULTS_DIR = Path(__file__).parent / "results"


def run_one(job):
    """One independent simulation, reduced to the quantities the figure needs."""
    n_agents, seed, n_steps = job
    record_depth = n_agents == DEPTH_AGENTS
    result = run_simulation(
        n_agents=n_agents, n_steps=n_steps, seed=seed,
        depth_record_from=max(0, n_steps - DEPTH_WINDOW) if record_depth else None,
        **PARAMS,
    )
    prices = result.mid_price_series
    if any(p is None for p in prices):
        raise ValueError(f"N_A={n_agents}, seed={seed}: book went one-sided (mid-price None); "
                         f"the Hurst calculation needs a gap-free series.")

    taus, h = hurst_curve(prices, min_tau=10, max_tau=n_steps // 10, n_points=30)
    return {
        "n_agents": n_agents,
        "seed": seed,
        "taus": taus,
        "h": h,
        "return_counts": {tau: return_counts(prices, tau, RETURN_BIN_EDGES, absolute=True)
                          for tau in RETURN_TAUS if tau < n_steps},
        "depth_sum": result.depth_profile_sum,
        "n_depth_snapshots": result.n_depth_snapshots,
        "mean_orders": float(np.mean(result.total_orders_series)),
        "n_trades": result.n_trades,
        "n_match_failures": result.n_match_failures,
        "price_path": np.array(prices) if (n_agents == PATH_AGENTS and seed == 0) else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n-steps", type=int, default=1_000_000)
    parser.add_argument("--n-runs", type=int, default=50, help="runs per N_A")
    parser.add_argument("--workers", type=int, default=os.cpu_count())
    parser.add_argument("--out", type=Path, default=RESULTS_DIR / "fig2_data.pkl")
    args = parser.parse_args()

    jobs = [(n, seed, args.n_steps) for n in AGENT_COUNTS for seed in range(args.n_runs)]
    # Slowest jobs (largest N_A) first so the pool doesn't end waiting on one long run.
    jobs.sort(key=lambda j: -j[0])
    print(f"{len(jobs)} runs ({args.n_runs} per N_A in {AGENT_COUNTS}), {args.n_steps:,} steps each, "
          f"{args.workers} workers")

    start = time.perf_counter()
    runs = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_one, job) for job in jobs]
        for done, future in enumerate(as_completed(futures), 1):
            runs.append(future.result())   # re-raises any worker exception here
            r = runs[-1]
            print(f"[{done}/{len(jobs)}] N_A={r['n_agents']} seed={r['seed']} done "
                  f"({time.perf_counter() - start:.0f}s elapsed, mean book {r['mean_orders']:.0f} orders)",
                  flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "wb") as f:
        pickle.dump({"config": {"n_steps": args.n_steps, "n_runs": args.n_runs, "params": PARAMS,
                                "return_bin_edges": RETURN_BIN_EDGES, "depth_window": DEPTH_WINDOW},
                     "runs": runs}, f)
    print(f"saved {args.out} ({time.perf_counter() - start:.0f}s total)")


if __name__ == "__main__":
    main()
