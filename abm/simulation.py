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

import itertools
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional

import numpy as np

from abm.orderbook import OrderBook, Side, OrderResult
from abm.agents import LiquidityProvider, LiquidityTaker, ValueTrader, AgentType, draw_value_shift
from abm.buy_probability import SideProbability


SHOCK_AGENT_ID = -1    # agent_id on the shock's orders, so its trades can be told apart


@dataclass
class Shock:
    """One large market order injected into a run, to study how the book recovers afterwards.

    It is a single market order of `size` units, submitted at the end of step `step` (after that
    step's takers). It takes the best price first, then the next, so it eats into the book from the
    best price outwards.
    side = Side.ASK is a sell (the price falls), Side.BID is a buy (the price rises).
    step counts from 0 = first step after the pre-opening."""
    step: int
    size: int
    side: Side = Side.ASK


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

    # The buy probability q_taker used by that step's takers, one entry per step. Filled only if
    # run_simulation was given a taker_flow (asymmetric order flow); empty otherwise.
    q_taker_series: np.ndarray = field(default_factory=lambda: np.empty(0))
    # The providers' mean entry depth lambda(t) used in each step. Filled only if run_simulation was
    # given a depth_coupling above 0 (Eq. 4, paper Fig. 4); empty otherwise.
    lambda_series: np.ndarray = field(default_factory=lambda: np.empty(0))

    # The state of each side of the book at the end of every step. Filled only if
    # run_simulation(record_sides=True); empty otherwise. Best prices are NaN while that side is empty.
    best_bid_series: np.ndarray = field(default_factory=lambda: np.empty(0))
    best_ask_series: np.ndarray = field(default_factory=lambda: np.empty(0))
    n_bids_series: np.ndarray = field(default_factory=lambda: np.empty(0))     # resting buy orders
    n_asks_series: np.ndarray = field(default_factory=lambda: np.empty(0))     # resting sell orders
    bid_volume_series: np.ndarray = field(default_factory=lambda: np.empty(0))  # resting units, buy side
    ask_volume_series: np.ndarray = field(default_factory=lambda: np.empty(0))  # resting units, sell side
    # How many units of the shock found nothing left to trade against (0 if there was no shock).
    shock_unfilled: int = 0
    # Value traders (filled only if run_simulation had n_value_traders above 0): the shared reference
    # price they used in each step, and each trader's own fixed shift from it.
    reference_series: np.ndarray = field(default_factory=lambda: np.empty(0))
    value_shifts: np.ndarray = field(default_factory=lambda: np.empty(0))


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


def _check_mix(mix: Optional[Mapping[AgentType, int]], n_agents: int, name: str) -> Dict[AgentType, int]:
    """The mix to use: {agent type: number of agents}. None means the paper's population, every
    agent acting every step with unit orders."""
    if mix is None:
        return {AgentType(): n_agents}
    if any(count < 0 for count in mix.values()):
        raise ValueError(f"{name}: the number of agents of a type cannot be negative")
    if sum(mix.values()) != n_agents:
        raise ValueError(f"{name}: the numbers of agents must add up to n_agents = {n_agents}, "
                         f"got {sum(mix.values())}")
    return {agent_type: count for agent_type, count in mix.items() if count > 0}


def _turn_lists(agents) -> List[List[List[int]]]:
    """For the fast method: which agents get their chance on which steps.

    One entry per agent type. Each entry is a list of `interval` lists of agent indices: entry[r]
    holds the agents of that type whose turn comes on the steps t with t % interval == r."""
    by_type: Dict[tuple, List[List[int]]] = {}
    for index, agent in enumerate(agents):
        lists = by_type.setdefault((agent.interval, agent.size), [[] for _ in range(agent.interval)])
        lists[-agent.offset % agent.interval].append(index)    # (t + offset) % interval == 0
    return list(by_type.values())


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
    taker_flow: Optional[SideProbability] = None,
    depth_coupling: float = 0.0,
    q_rms: Optional[float] = None,
    shock: Optional[Shock] = None,
    record_sides: bool = False,
    provider_mix: Optional[Mapping[AgentType, int]] = None,
    taker_mix: Optional[Mapping[AgentType, int]] = None,
    n_value_traders: int = 0,
    value_window: int = 1000,
    value_spread: float = 50.0,
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

    taker_flow (see buy_probability.py) makes the takers' buy probability a shared, time-varying value
    (asymmetric order flow, paper Fig. 3) instead of the fixed q_taker, which is then ignored. Each
    step's takers use taker_flow.q; it then advances, so the first step uses its starting value
    (1/2). The values used are returned in result.q_taker_series. Pass a fresh flow object per run. 
    (Don't use the same one between simulations, as will start in different places)

    depth_coupling (C_lambda in the paper's Eq. 4) makes the providers' mean entry depth change with the
    order-flow imbalance: lambda(t) = lambda_ * (1 + |q(t) - 1/2| / q_rms * depth_coupling), where q(t)
    is the takers' buy probability in that step and q_rms is sqrt(<(q - 1/2)^2>). 0 (the default) keeps
    the depth fixed at lambda_. It needs a taker_flow and q_rms. Providers and takers in a step use the
    same q(t). The values used are returned in result.lambda_series.

    shock injects one large market order (see Shock) at the end of the given step. None (the default)
    leaves the run exactly as it was without this option.

    record_sides=True stores the best bid, the best ask, and the number of resting orders and of
    resting units on each side at the end of every step (result.best_bid_series etc.). Orders and
    units are the same number while every order is one unit. It uses no random numbers, so it does
    not change the run.

    provider_mix and taker_mix give agents different speeds and order sizes (see AgentType). Each is
    {agent type: number of agents} and must add up to n_agents, e.g.
        {AgentType(1, 1): 100, AgentType(2, 2): 100, AgentType(4, 4): 50}.
    None (the default) is the paper's population. Agents of a slower type are spread evenly over the
    steps: the i-th agent of a type has offset i % interval, so about the same number get their
    chance on every step. On its step an agent still acts with probability alpha (or mu), as before.

    n_value_traders turns that many of the n_agents takers into value traders (see ValueTrader in
    agents.py); 0 (the default) leaves the run exactly as it was. They act at the same rate mu, so the
    number of orders per step is unchanged. Their shared reference price is the mean of the mid-price
    at the end of the last value_window steps (the start price until there is any history). Each
    trader's own value is the reference plus a fixed shift, + or - with equal chance and exponentially
    distributed with mean value_spread ticks. If taker_mix is given with value traders, it must add
    up to the takers that are left, n_agents - n_value_traders. The reference used in each step is
    returned in result.reference_series.
    """
    if method not in ("fast", "agents"):
        raise ValueError(f"method must be 'fast' or 'agents', got {method!r}")
    if depth_coupling < 0:
        raise ValueError("depth_coupling must be 0 or more")
    if depth_coupling > 0 and taker_flow is None:
        raise ValueError("depth_coupling needs a taker_flow: lambda(t) depends on the takers' q(t)")
    if depth_coupling > 0 and not (q_rms and q_rms > 0):
        raise ValueError("depth_coupling needs q_rms > 0, the value of sqrt(<(q - 1/2)^2>) in Eq. 4")
    if shock is not None and not (0 <= shock.step < n_steps):
        raise ValueError(f"shock.step must be a recorded step, 0 to {n_steps - 1}")
    if shock is not None and shock.size < 1:
        raise ValueError("shock.size must be at least 1")
    if not (0 <= n_value_traders <= n_agents):
        raise ValueError(f"n_value_traders must be between 0 and n_agents = {n_agents}")
    if value_window < 1:
        raise ValueError("value_window must be at least 1 step")
    if value_spread < 0:
        raise ValueError("value_spread must be 0 or more")
    provider_mix = _check_mix(provider_mix, n_agents, "provider_mix")
    taker_mix = _check_mix(taker_mix, n_agents - n_value_traders, "taker_mix")
    fast = method == "fast"    #Checks which method has been selected
    check_stability_condition(alpha, mu, delta)

    rng = random.Random(seed)
    step_trade_prices: List[int] = []     # prices of the trades in the current step
    book = OrderBook(keep_trades=keep_trades,
                     on_trade=step_trade_prices.append if record_trade_prices else None)

    # Agents are created type by type. Within a type, agent i gets offset i % interval, which spreads
    # that type evenly over the steps. With the default mix this is the paper's population.
    provider_ids, taker_ids = itertools.count(0), itertools.count(n_agents)     # agent ids, as before
    providers = [
        LiquidityProvider(agent_id=next(provider_ids), alpha=alpha, q_provider=q_provider, lambda_=lambda_,
                          interval=agent_type.interval, size=agent_type.size, offset=i % agent_type.interval)
        for agent_type, count in provider_mix.items() for i in range(count)
    ]
    takers = [
        LiquidityTaker(agent_id=next(taker_ids), mu=mu, q_taker=q_taker,
                       interval=agent_type.interval, size=agent_type.size, offset=i % agent_type.interval)
        for agent_type, count in taker_mix.items() for i in range(count)
    ]
    # Value traders take the place of some of the takers. Each draws its own shift once, here.
    value_traders = [
        ValueTrader(agent_id=next(taker_ids), mu=mu, shift=draw_value_shift(rng, value_spread))
        for _ in range(n_value_traders)
    ]
    provider_turns, taker_turns, value_turns = _turn_lists(providers), _turn_lists(takers), _turn_lists(value_traders)
    recent_mids: deque = deque()      # mid-prices of the last value_window steps, for the reference price
    recent_mids_sum = 0.0

    def reference_price() -> float:
        """The value traders' shared reference: the mean of the recent mid-prices."""
        return recent_mids_sum / len(recent_mids) if recent_mids else float(p0)

    def acting_agents(turns: List[List[List[int]]], t: int, probability: float) -> List[int]:
        """Fast method: the agents that act in step t. For each type, take the agents whose turn it
        is, draw how many of them act from a Binomial, and pick that many at random."""
        acting: List[int] = []
        for lists in turns:
            on_turn = lists[t % len(lists)]
            if on_turn:
                #rng.sample(population, k) selects k unique elements from population w/o replacement
                acting += [on_turn[j] for j in rng.sample(range(len(on_turn)),
                                                          rng.binomialvariate(len(on_turn), probability))]
        if len(turns) > 1:
            rng.shuffle(acting)     # so that no type always goes first within a step
        return acting

    def providers_act(t: int, lam: Optional[float] = None) -> None:
        """lam, if not None, is this step's mean entry depth lambda(t) (Eq. 4); None means each
        provider uses its own fixed lambda_."""
        if fast:
            #So binomial distribution of agents each with prob alpha, then gives number of active agents.
            #Then each selected agent submits an order.
            for i in acting_agents(provider_turns, t, alpha):
                providers[i].submit(book, t, p0, rng, lambda_=lam)
        else:
            for p in providers:
                #Each agent individually decided whether to submit
                p.maybe_submit(book, timestamp=t, fallback_price=p0, rng=rng, lambda_=lam)

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

    def takers_act(t: int, q: Optional[float], reference: float) -> int:
        """Returns the number of market orders that were not filled completely (the book side
        they needed was empty, or ran out part-way through a bigger order).
        Also submits the takers orders, under normal conditions failures should stay 0.
        q, if not None, is this step's shared buy probability (asymmetric flow); None means
        each taker uses its own fixed q_taker.
        Value traders act in this part of the step too, with reference as their shared reference
        price. Their orders are limit orders, so they are never counted as failures."""
        failures = 0
        if fast and not value_traders:
            for i in acting_agents(taker_turns, t, mu):
                if takers[i].submit(book, t, rng, q_taker=q) is not OrderResult.EXECUTED:
                    failures += 1
        elif fast:
            # Takers and value traders act in one random order, so neither always goes first.
            acting = [(takers[i], False) for i in acting_agents(taker_turns, t, mu)] \
                + [(value_traders[i], True) for i in acting_agents(value_turns, t, mu)]
            rng.shuffle(acting)
            for agent, is_value_trader in acting:
                if is_value_trader:
                    agent.submit(book, t, reference)
                elif agent.submit(book, t, rng, q_taker=q) is not OrderResult.EXECUTED:
                    failures += 1
        else:
            everyone = takers + value_traders
            if value_traders:
                rng.shuffle(everyone)       # one random order, as in the fast method
            for agent in everyone:
                if isinstance(agent, ValueTrader):
                    agent.maybe_submit(book, timestamp=t, reference=reference, rng=rng)
                else:
                    outcome = agent.maybe_submit(book, timestamp=t, rng=rng, q_taker=q)
                    if outcome is not None and outcome is not OrderResult.EXECUTED:
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
    q_taker_series = np.empty(n_steps) if taker_flow is not None else np.empty(0)
    lambda_series = np.empty(n_steps) if depth_coupling > 0 else np.empty(0)
    n_side = n_steps if record_sides else 0
    best_bid_series, best_ask_series = np.full(n_side, np.nan), np.full(n_side, np.nan)
    n_bids_series, n_asks_series = np.zeros(n_side, dtype=int), np.zeros(n_side, dtype=int)
    bid_volume_series, ask_volume_series = np.zeros(n_side, dtype=int), np.zeros(n_side, dtype=int)
    shock_unfilled = 0
    reference_series = np.empty(n_steps) if value_traders else np.empty(0)

    for t in range(pre_opening_steps, pre_opening_steps + n_steps):
        step = t - pre_opening_steps
        q_now = taker_flow.q if taker_flow is not None else None     # this step's q, used all step
        lambda_now = None
        if depth_coupling > 0:                  # Eq. 4
            lambda_now = lambda_ * (1 + abs(q_now - 0.5) / q_rms * depth_coupling)
            lambda_series[step] = lambda_now

        providers_act(t, lambda_now)            # 1. Providers act
        cancellation_sweep()                    # 2. Each resting order removed w.p. delta
        reference_now = reference_price() if value_traders else 0.0
        if value_traders:
            reference_series[step] = reference_now
        n_match_failures += takers_act(t, q_now, reference_now)    # 3. Takers (and value traders) act
        if taker_flow is not None:
            q_taker_series[step] = q_now
            taker_flow.advance(rng)             # next step's value; step 0 used the starting value

        if shock is not None and step == shock.step:
            # One large market order. It uses no random numbers.
            traded_before = book.volume_traded
            book.submit_market_order(shock.side, t, agent_id=SHOCK_AGENT_ID, quantity=shock.size)
            shock_unfilled = shock.size - (book.volume_traded - traded_before)   # above 0 if that side ran out

        mid_now = book.mid_price()
        mid_price_series.append(mid_now)
        total_orders_series.append(book.total_orders())
        if value_traders and mid_now is not None:
            # Keep the last value_window mid-prices and their sum, for the next step's reference.
            recent_mids.append(mid_now)
            recent_mids_sum += mid_now
            if len(recent_mids) > value_window:
                recent_mids_sum -= recent_mids.popleft()
        if record_sides:
            best_bid, best_ask = book.best_bid(), book.best_ask()
            if best_bid is not None:
                best_bid_series[step] = best_bid
            if best_ask is not None:
                best_ask_series[step] = best_ask
            n_bids_series[step] = book.orders_on(Side.BID)
            n_asks_series[step] = book.orders_on(Side.ASK)
            bid_volume_series[step] = book.volume_on(Side.BID)
            ask_volume_series[step] = book.volume_on(Side.ASK)

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
        q_taker_series=q_taker_series,
        lambda_series=lambda_series,
        best_bid_series=best_bid_series,
        best_ask_series=best_ask_series,
        n_bids_series=n_bids_series,
        n_asks_series=n_asks_series,
        bid_volume_series=bid_volume_series,
        ask_volume_series=ask_volume_series,
        shock_unfilled=shock_unfilled,
        reference_series=reference_series,
        value_shifts=np.array([v.shift for v in value_traders]),
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
