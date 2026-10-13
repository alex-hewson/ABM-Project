'''
Agents based on section 3 of the paper the orderbook model came from.

Testing matching functionality to the papers results to verify working model.
'''
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

from abm.orderbook import OrderBook, Side, OrderResult


@dataclass(frozen=True)
class AgentType:
    """How often an agent gets a chance to act, and how big its orders are.

    interval = 1, size = 1 is the paper's agent: a chance to act every step, one unit per order.
    An agent with interval k only gets its chance every k-th step. With size = interval (1 unit every
    step, 2 units every 2 steps, 4 units every 4 steps) every type trades the same number of units
    per step on average, so the types differ in speed and lumpiness but not in volume."""
    interval: int = 1
    size: int = 1

    def __post_init__(self):
        if self.interval < 1 or self.size < 1:
            raise ValueError("interval and size must both be at least 1")


def is_turn(timestamp: int, interval: int, offset: int) -> bool:
    """True on the steps where an agent with this interval and offset gets its chance to act:
    every interval-th step. The offset (0 to interval - 1) shifts which steps those are, so that
    slow agents can be spread over the steps instead of all acting together."""
    return (timestamp + offset) % interval == 0


'''
The liquidity provider only submits limit orders around the midpoint.
The midpoint is p_m = (p_a + p_b)/2, where p_a, p_b are best ask and best bid respectively.
The initial midpoint is set to 1,000,000 ticks, on a 2,000,000 tick model, so in the middle (literally "the midpoint")
Initially only limit orders can be placed, to allow the order book to populate properly without instability.

At every step each provider submits a limit order with probability alpha. 
P(bid) = 1-P(ask), and prices are offset from the midpoint by an exponential distribution (e^-{lambda})

The providers and takers are IID, as the paper requires. So random decision each step regardless of the last decision.


In the fast loop of the simulation, the decisions to submit an order / cancel are made in one go, then attributed to individual agents.
This avoids looping through all agents every step (slow)
Hence just submit instead of maybe_submit (and maybe_submit now just runs into submit)
'''
@dataclass
class LiquidityProvider:
    agent_id: int
    alpha: float       # probability of submitting an order
    q_provider: float  # probability of entering on the bid side
    lambda_: float     # mean entry depth
    interval: int = 1  # gets a chance to act every interval-th step (see AgentType)
    size: int = 1      # units per order
    offset: int = 0    # which of those steps: acts when (timestamp + offset) is a multiple of interval 

    def maybe_submit(
            self, book: OrderBook, timestamp: int, fallback_price: int, rng: Optional[random.Random] = None,
            lambda_: Optional[float] = None,
    ) -> Optional[int]:
        '''
        Probability alpha of submitting an order in this step.
        
        "fallback price" = price before there is a midpoint (beginning of sim).

        rng gives a seeded random instance (to test reproducibility of results)

        return order_id if order submitted, else returns None.
        '''

        if not is_turn(timestamp, self.interval, self.offset):
            return None        # not this agent's step: nothing happens, and no random number is used
        r = rng or random
        if r.random() >= self.alpha:
            return None
        return self.submit(book, timestamp, fallback_price, rng, lambda_)

    def submit(
            self, book: OrderBook, timestamp: int, fallback_price: int, rng: Optional[random.Random] = None,
            lambda_: Optional[float] = None,
    ) -> int:
        '''
        Submit a limit order unconditionally: the part of maybe_submit that follows the alpha draw.
        Included as a separate function to allow fast simulation loop to decide how many providers act in a step in one go.
        Returns the order_id.

        lambda_, if given, replaces this agent's own mean entry depth for this one order. That is how the
        time-varying entry depth of Eq. 4 (paper Fig. 4) reaches every provider: the simulation works out
        lambda(t) each step and passes it in, in the same way as q_taker for the takers.
        '''
        r = rng or random
        mid = book.mid_price()
        reference_price = mid if mid is not None else fallback_price
        mean_depth = self.lambda_ if lambda_ is None else lambda_

        #Exponentially distrbuted entry depth, lambda_ is the mean. expovariate(1/mean) draws from an exponential distribution about the given mean.
        #Arg is rate, hence 1/mean.
        depth = r.expovariate(1.0/mean_depth)

        side = Side.BID if r.random() < self.q_provider else Side.ASK
        if side is Side.BID:
            price = int(round(reference_price-depth))
        else:
            price = int(round(reference_price+depth))

        return book.submit_limit_order(side, price, timestamp, agent_id=self.agent_id, quantity=self.size)


'''
The liquidity takers just submit market orders with probability mu.
Probability of a buy order (so removing the cheapest ask) is given by q_taker, with sell order prob 1-q_taker.
'''
@dataclass
class LiquidityTaker:
    agent_id: int
    mu: float        #Probability of submitting a market order
    q_taker: float   # Probability of entering on the buy side
    interval: int = 1  # gets a chance to act every interval-th step (see AgentType)
    size: int = 1      # units per order
    offset: int = 0    # which of those steps: acts when (timestamp + offset) is a multiple of interval


    def maybe_submit(
            self, book: OrderBook, timestamp: int, rng: Optional[random.Random] = None,
            q_taker: Optional[float] = None,
            ) -> Optional[OrderResult]:
        if not is_turn(timestamp, self.interval, self.offset):
            return None        # not this agent's step: nothing happens, and no random number is used
        r = rng or random

        if r.random() >= self.mu:
            return None
        return self.submit(book, timestamp, rng, q_taker)

    def submit(
            self, book: OrderBook, timestamp: int, rng: Optional[random.Random] = None,
            q_taker: Optional[float] = None,
            ) -> OrderResult:
        '''
        Submit a market order unconditionally: the part of maybe_submit that follows the mu draw.

        q_taker, if given, replaces this agent's own q_taker for this one order. That is how a shared,
        time-varying buy probability (see buy_probability.py) reaches every taker: the simulation
        passes the current value in, so there is one q for the whole market at each step.
        '''
        r = rng or random
        q = self.q_taker if q_taker is None else q_taker
        side = Side.BID if r.random() < q else Side.ASK

        result, order_id =  book.submit_market_order(side, timestamp, agent_id=self.agent_id, quantity=self.size)
        return result
