"""
Simulation loop for the Preis et al. (2006) order book model.

Wires together LiquidityProvider and LiquidityTaker agents (agents.py)
around the OrderBook matching engine (orderbook.py). 
Cancellcation also occurs here, as it isn't agent behaviour (An agent can't cancel anothers resting order).
Hence cancellation implemented here as a book-level sweep, with probability delta once per step (as in the paper)


Per-step order, following the paper's Eq. 1,

N(t) is total number of orders
alpha is rate that liquidity providers submit limit orders (or prob of them submitting an order individually)
N_A is the number of liquidity providers (equals number of takers in simple model)
delta is probability of order being removed (cancelled)
mu is rate that liq takers submit market orders

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

import numpy as np

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

    # dict below describes the order book's average shape: how many orders sit at each distance from the
    # midpoint (not raw price / dist from centre), averaged over many points in time during the run (see
    # depth_record_from below).

    #This dict holds a running total (sum) of orders at each distance, from various snapshots taken by depth_record_from.
    #An average is calculated at the end by dividing this sum by number of snapshots taken (n_depth_snapshots)
    #This avg is the paper's <N(p-p_m)> in fig. 2b

    #Each key in the dict is a half distance (so a price 0.5 away is 1 key away). 
    #Doubling of the price to get the key avoids floats.  midpoint key = 2*price - (best_bid + best_ask)  (bids and asks are integers)
    #Negative entry is a bid, positive is an ask.
    depth_profile_sum: Dict[int, int] = field(default_factory=dict)
    n_depth_snapshots: int = 0
    
    # Per-step summaries of the trade prices in that step ("first", "last", "median", "mean"), with NaN
    # for steps with no trade. Filled only if run_simulation(record_trade_prices=True). The median of an
    # even number of trades is the upper of the two middle values. See analysis/prices.py.
    trade_price_steps: Dict[str, np.ndarray] = field(default_factory=dict)


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
    method: str = "fast",
    keep_trades: bool = True,
    record_trade_prices: bool = False,
) -> SimulationResult:
    """
    Run the base Preis et al. model for n_steps, after a pre-opening
    sequence of provider-only steps to give the book initial depth.

    n_agents is used for both providers and takers, matching the paper's
    N_A convention (same agent count for both populations).

    If depth_record_from is given, the book's depth profile relative to the
    midpoint is recorded at the end of every depth_record_every-th step from
    that step index (0 = first step after pre-opening) to the end of the run (every 1 step by default).

    method selects how each step's random events are generated. Both give the
    same distribution of outcomes; they differ only in cost and random stream
    (the same seed gives different, but statistically equivalent, runs):
      "agents": the literal reference. Every agent flips its own alpha / mu coin
                and every resting order is tested for cancellation, one by one.
      "fast":   draws how many providers act, orders are cancelled and takers
                act from a Binomial, then picks that many agents / orders at
                random. Valid because agents are IID and each order is
                cancelled independently with probability delta. Several times
                faster; use for long runs.

    record_trade_prices=True stores the first / last / median / mean trade price
    of every step (result.trade_price_steps) in a compact form.
    keep_trades=False stops the book keeping a Trade object per trade, which
    saves a lot of memory in long runs (result.book.trades is then empty;
    result.n_trades still counts the trades).
    """
    if method not in ("fast", "agents"):
        raise ValueError(f"method must be 'fast' or 'agents', got {method!r}")
    fast = method == "fast"    #Checks which method has been selected
    check_stability_condition(alpha, mu, delta)

    rng = random.Random(seed)
    step_trade_prices: List[int] = []     # prices of the trades in the current step
    book = OrderBook(keep_trades=keep_trades,
                     on_trade=step_trade_prices.append if record_trade_prices else None)

    providers = [
        LiquidityProvider(agent_id=i, alpha=alpha, q_provider=q_provider, lambda_=lambda_)
        for i in range(n_agents)
    ]
    takers = [
        LiquidityTaker(agent_id=n_agents + i, mu=mu, q_taker=q_taker)
        for i in range(n_agents)
    ]

    def providers_act(t: int) -> None:
        if fast:
            #rng.sample(population, k) selects k unique elements from population w/o replacement
            #So binomial distribution of agents each with prob alpha, then gives number of active agents.
            #Then each selected agent submits an order.
            for i in rng.sample(range(n_agents), rng.binomialvariate(n_agents, alpha)):
                providers[i].submit(book, t, p0, rng)
        else:
            for p in providers:
                #Each agent individually decided whether to submit
                p.maybe_submit(book, timestamp=t, fallback_price=p0, rng=rng)

    def cancellation_sweep() -> None:
        if fast:
            #Randomly selects k orders to be cancelled (k decided as though each agent has prob delta of cancelling)
            k = rng.binomialvariate(book.total_orders(), delta)
            for order_id in book.sample_resting_order_ids(k, rng):
                book.cancel_order(order_id)
        else:
            # Snapshot ids first: don't mutate the structure you're iterating.
            for side in (Side.BID, Side.ASK):
                for order_id in book.resting_order_ids(side):
                    if rng.random() < delta:
                        book.cancel_order(order_id)

    def takers_act(t: int) -> int:
        """Returns the number of market orders that found an empty book.
        Also submits the takers orders, under normal conditions failures should stay 0"""
        failures = 0
        if fast:
            for i in rng.sample(range(n_agents), rng.binomialvariate(n_agents, mu)):
                if takers[i].submit(book, t, rng) is OrderResult.NO_MATCH:
                    failures += 1
        else:
            for taker in takers:
                if taker.maybe_submit(book, timestamp=t, rng=rng) is OrderResult.NO_MATCH:
                    failures += 1
        return failures

    # --- Pre-opening: providers only, so takers never face an empty book ---
    for t in range(pre_opening_steps):
        providers_act(t)
    step_trade_prices.clear()    # any pre-opening trades don't belong to a recorded step

    trade_price_steps = {name: np.full(n_steps, np.nan) for name in ("first", "last", "median", "mean")} \
        if record_trade_prices else {}
    mid_price_series: List[Optional[float]] = []
    total_orders_series: List[int] = []
    n_match_failures = 0
    depth_sum: Dict[int, int] = {}
    n_depth_snapshots = 0

    for t in range(pre_opening_steps, pre_opening_steps + n_steps):
        providers_act(t)                        # 1. Providers act
        cancellation_sweep()                    # 2. Each resting order removed w.p. delta
        n_match_failures += takers_act(t)       # 3. Takers act

        mid_price_series.append(book.mid_price())
        total_orders_series.append(book.total_orders())

        step = t - pre_opening_steps
        if record_trade_prices and step_trade_prices:
            trade_price_steps["first"][step] = step_trade_prices[0]
            trade_price_steps["last"][step] = step_trade_prices[-1]
            trade_price_steps["median"][step] = sorted(step_trade_prices)[len(step_trade_prices) // 2]
            trade_price_steps["mean"][step] = sum(step_trade_prices) / len(step_trade_prices)
            step_trade_prices.clear()
        if (depth_record_from is not None and step >= depth_record_from
                and (step - depth_record_from) % depth_record_every == 0):
            n_depth_snapshots += _accumulate_depth(book, depth_sum)

    return SimulationResult(
        mid_price_series=mid_price_series,
        total_orders_series=total_orders_series,
        n_match_failures=n_match_failures,
        n_trades=book.n_trades,
        book=book,
        depth_profile_sum=depth_sum,
        n_depth_snapshots=n_depth_snapshots,
        trade_price_steps=trade_price_steps,
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
