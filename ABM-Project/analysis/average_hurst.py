"""
Average H(Delta_tau) over multiple simulation runs.

Necessary because a single run's Hurst curve gets extremely noisy at
large lags (see hurst.py's validation against a synthetic random walk --
per-run H at large tau can vary by +-0.2 or more purely from seed choice).
The paper handles this by averaging over 50 runs; this is that averaging
step, applied to actual simulation output rather than a synthetic walk.

Assumes every run uses the same n_steps, so every run's hurst_curve()
call produces the identical set of tau values -- that's what makes the
averaging here a simple elementwise mean rather than requiring alignment
by tau value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from abm.simulation import run_simulation
from analysis.hurst import hurst_curve


@dataclass
class AveragedHurstResult:
    taus: List[int]
    mean_h: List[float]
    min_h: List[float]
    max_h: List[float]
    n_runs: int


def average_hurst_over_runs(
    n_agents: int,
    alpha: float,
    mu: float,
    delta: float,
    lambda_: float,
    q_provider: float = 0.5,
    q_taker: float = 0.5,
    n_steps: int = 100_000,
    pre_opening_steps: int = 10,
    p0: int = 1_000_000,
    n_runs: int = 10,
    base_seed: int = 0,
    min_tau: int = 10,
    max_tau: int = 10_000,
    n_points: int = 30,
) -> AveragedHurstResult:
    """
    Run the simulation n_runs times (seeds base_seed, base_seed+1, ...,
    each run fully independent), compute the Hurst curve for each run's
    mid-price series, and average across runs at each tau.
    """
    per_run_curves: List[List[float]] = []
    taus_reference: List[int] = None  # type: ignore

    for i in range(n_runs):
        seed = base_seed + i
        result = run_simulation(
            n_agents=n_agents, alpha=alpha, mu=mu, delta=delta, lambda_=lambda_,
            q_provider=q_provider, q_taker=q_taker,
            n_steps=n_steps, pre_opening_steps=pre_opening_steps, p0=p0,
            seed=seed,
        )

        prices = result.mid_price_series
        if any(p is None for p in prices):
            # mid_price() returns None if either side of the book is
            # empty -- surfacing this as an error rather than silently
            # dropping/interpolating those points, since for an
            # instability study, "the book went one-sided" is itself an
            # important event you'd want to know about, not paper over.
            raise ValueError(
                f"Run with seed={seed} produced a None mid-price (book went "
                f"empty on one side at some point) -- Hurst calculation "
                f"assumes a complete, gap-free price series. Investigate "
                f"before averaging over this run."
            )

        taus, hs = hurst_curve(prices, min_tau=min_tau, max_tau=max_tau, n_points=n_points)

        if taus_reference is None:
            taus_reference = taus
        elif taus != taus_reference:
            # Should only happen if something about run length/parameters
            # varies between runs -- flagged rather than silently
            # misaligning tau values across runs.
            raise ValueError(
                f"Run with seed={seed} produced a different set of tau "
                f"values than earlier runs -- are all runs using the same "
                f"n_steps? Cannot average misaligned tau values."
            )

        per_run_curves.append(hs)

    n_taus = len(taus_reference)
    mean_h = []
    min_h = []
    max_h = []
    for j in range(n_taus):
        values_at_this_tau = [curve[j] for curve in per_run_curves]
        mean_h.append(sum(values_at_this_tau) / n_runs)
        min_h.append(min(values_at_this_tau))
        max_h.append(max(values_at_this_tau))

    return AveragedHurstResult(
        taus=taus_reference, mean_h=mean_h, min_h=min_h, max_h=max_h, n_runs=n_runs,
    )


if __name__ == "__main__":
    # Paper's representative parameter set, scaled down from n_steps=1e6
    # for a quick check -- bump this up once you're ready for a real run.
    result = average_hurst_over_runs(
        n_agents=250, alpha=0.15, mu=0.025, delta=0.025, lambda_=100,
        q_provider=0.5, q_taker=0.5,
        n_steps=20_000, n_runs=5, base_seed=0,
        min_tau=10, max_tau=5_000, n_points=25,
    )
    print(f"Averaged over {result.n_runs} runs:")
    for tau, h, lo, hi in zip(result.taus, result.mean_h, result.min_h, result.max_h):
        print(f"  tau={tau:>6}  mean H={h:.3f}  (range {lo:.3f}-{hi:.3f})")
