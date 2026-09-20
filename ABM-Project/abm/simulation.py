"""
Simulation loop for the Preis et al. (2006) order book model.

Wires together LiquidityProvider and LiquidityTaker agents (agents.py)
around the OrderBook matching engine (orderbook.py), plus the one piece
neither agent type owns: order cancellation. Cancellation isn't agent
behavior -- no single agent decides to cancel someone else's resting
order -- so it's implemented here as a book-level sweep, following the
paper's Eq. 1: each resting order is removed with probability delta,
once per step.

Per-step order, following the paper's Eq. 1,
N(t+1) = (N(t) + alpha*N_A) - (N(t) + alpha*N_A)*delta - mu*N_A:
  1. Providers act (submit limit orders)
  2. Cancellation sweep over all resting orders (including this step's new ones)
  3. Takers act (submit market orders)

This ordering is what makes the equilibrium depth match the paper's Eq. 2-3.
A freshly-placed order can be cancelled in the step it was created, and takers
only see the book after cancellation.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from abm.orderbook import OrderBook, Side, OrderResult
from abm.agents import LiquidityProvider, LiquidityTaker


@dataclass
class SimulationResult:
    """Everything you'd want to inspect or plot after a run."""
    mid_price_series: List[Optional[float]]   # one entry per step (post pre-opening)
    total_orders_series: List[int]             # book depth over time -- your instability signal
    n_match_failures: int                       # count of taker orders that hit an empty book
    n_trades: int
    book: OrderBook                              # final book state, for further inspection
    # Summed resting-order counts by distance from the midpoint, over the snapshots taken
    # (see run_simulation's depth_record_from). Keys are in HALF-ticks: 2*price - (best_bid + best_ask),
    # so they are exact integers even though the midpoint can sit on a half-tick. Bids are negative,
    # asks positive. Divide a bin's sum by n_depth_snapshots for the paper's <N(p - p_m)> (Fig. 2b).
    depth_profile_sum: Dict[int, int] = field(default_factory=dict)
    n_depth_snapshots: int = 0


def _accumulate_depth(book: OrderBook, depth_sum: Dict[int, int]) -> int:
    """Add the book's current depth, keyed by half-tick offset from the midpoint,
    into depth_sum. Returns 1 if a snapshot was taken, 0 if there is no midpoint
    (one side of the book empty)."""
    best_bid, best_ask = book.best_bid(), book.best_ask()
    if best_bid is None or best_ask is None:
        return 0
    mid2 = best_bid + best_ask   # twice the midpoint
    for side in (Side.BID, Side.ASK):
        for price, n_orders in book.depth_profile(side).items():
            key = 2 * price - mid2
            depth_sum[key] = depth_sum.get(key, 0) + n_orders
    return 1


def check_stability_condition(alpha: float, mu: float, delta: float) -> None:
    """
    Paper's Eq. 1-3: the book only stays populated in equilibrium if
    alpha* = alpha * (1 - delta) > mu. If this doesn't hold, the book
    empties out over time regardless of what the agents do -- that's a
    parameter problem, not a finding, so we fail loudly here rather than
    let you spend an hour debugging a simulation that was never going to
    stabilize.
    """
    alpha_star = alpha * (1 - delta)
    if not (alpha_star > mu):
        raise ValueError(
            f"Stability condition alpha*(1-delta) > mu is violated: "
            f"alpha*={alpha_star:.4f}, mu={mu}. The book will empty out. "
            f"See Preis et al. Eq. 1-3."
        )
    if not (delta > 0):
        raise ValueError("delta must be > 0 for a stable order book (Eq. 3).")


def run_simulation(
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
    seed: Optional[int] = None,
    depth_record_from: Optional[int] = None,
    depth_record_every: int = 1,
) -> SimulationResult:
    """
    Run the base Preis et al. model for n_steps, after a pre-opening
    sequence of provider-only steps to give the book initial depth.

    n_agents is used for both providers and takers, matching the paper's
    N_A convention (same agent count for both populations).

    If depth_record_from is given, the book's depth profile relative to the
    midpoint is recorded at the end of every depth_record_every-th step from
    that step index (0 = first step after pre-opening) to the end of the run.
    """
    check_stability_condition(alpha, mu, delta)

    rng = random.Random(seed)
    book = OrderBook()

    providers = [
        LiquidityProvider(agent_id=i, alpha=alpha, q_provider=q_provider, lambda_=lambda_)
        for i in range(n_agents)
    ]
    takers = [
        LiquidityTaker(agent_id=n_agents + i, mu=mu, q_taker=q_taker)
        for i in range(n_agents)
    ]

    # --- Pre-opening: providers only, so takers never face an empty book ---
    for t in range(pre_opening_steps):
        for p in providers:
            p.maybe_submit(book, timestamp=t, fallback_price=p0, rng=rng)

    mid_price_series: List[Optional[float]] = []
    total_orders_series: List[int] = []
    n_match_failures = 0
    depth_sum: Dict[int, int] = {}
    n_depth_snapshots = 0

    for t in range(pre_opening_steps, pre_opening_steps + n_steps):
        # 1. Providers act
        for p in providers:
            p.maybe_submit(book, timestamp=t, fallback_price=p0, rng=rng)

        # 2. Cancellation sweep -- each resting order removed w.p. delta.
        # Snapshot ids first: don't mutate the structure you're iterating.
        for side in (Side.BID, Side.ASK):
            for order_id in book.resting_order_ids(side):
                if rng.random() < delta:
                    book.cancel_order(order_id)

        # 3. Takers act
        for taker in takers:
            result = taker.maybe_submit(book, timestamp=t, rng=rng)
            if result is OrderResult.NO_MATCH:
                n_match_failures += 1

        mid_price_series.append(book.mid_price())
        total_orders_series.append(book.total_orders())

        step = t - pre_opening_steps
        if (depth_record_from is not None and step >= depth_record_from
                and (step - depth_record_from) % depth_record_every == 0):
            n_depth_snapshots += _accumulate_depth(book, depth_sum)

    return SimulationResult(
        mid_price_series=mid_price_series,
        total_orders_series=total_orders_series,
        n_match_failures=n_match_failures,
        n_trades=len(book.trades),
        book=book,
        depth_profile_sum=depth_sum,
        n_depth_snapshots=n_depth_snapshots,
    )


if __name__ == "__main__":
    # Paper's representative parameter set (Fig. 2 caption):
    # alpha=0.15, mu=0.025, delta=0.025, lambda_0=100, N_A=250, q=0.5
    result = run_simulation(
        n_agents=250,
        alpha=0.15,
        mu=0.025,
        delta=0.025,
        lambda_=100,
        q_provider=0.5,
        q_taker=0.5,
        n_steps=10_000,   # scaled down from the paper's 1e6 for a quick check
        seed=42,
    )
    prices = [p for p in result.mid_price_series if p is not None]
    print(f"steps recorded: {len(result.mid_price_series)}")
    print(f"trades executed: {result.n_trades}")
    print(f"taker match failures (empty book on target side): {result.n_match_failures}")
    print(f"final total orders in book: {result.total_orders_series[-1]}")
    print(f"mid price: start={prices[0]:.1f}, end={prices[-1]:.1f}, "
          f"min={min(prices):.1f}, max={max(prices):.1f}")
