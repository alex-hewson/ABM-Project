'''
Agents based on section 3 of the paper the orderbook model came from.

Testing matching functionality to the papers results to verify working model.
'''
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional, Protocol

from abm.orderbook import OrderBook, Side, OrderResult


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

    def maybe_submit(
            self, book: OrderBook, timestamp: int, fallback_price: int, rng: Optional[random.Random] = None
    ) -> Optional[int]:
        '''
        Probability alpha of submitting an order in this step.
        
        "fallback price" = price before there is a midpoint (beginning of sim).

        rng gives a seeded random instance (to test reproducibility of results)

        return order_id if order submitted, else returns None.
        '''

        r = rng or random
        if r.random() >= self.alpha:
            return None
        return self.submit(book, timestamp, fallback_price, r)

    def submit(
            self, book: OrderBook, timestamp: int, fallback_price: int, rng: Optional[random.Random] = None
    ) -> int:
        '''
        Submit a limit order unconditionally: the part of maybe_submit that follows the alpha draw.
        Included as a separate function to allow fast simulation loop to decide how many providers act in a step in one go.
        Returns the order_id.
        '''
        r = rng or random
        mid = book.mid_price()
        reference_price = mid if mid is not None else fallback_price

        #Exponentially distrbuted entry depth, lambda_ is the mean. expovariate(1/mean) draws from an exponential distribution about the given mean.
        #Arg is rate, hence 1/mean.
        depth = r.expovariate(1.0/self.lambda_)

        side = Side.BID if r.random() < self.q_provider else Side.ASK
        if side is Side.BID:
            price = int(round(reference_price-depth))
        else:
            price = int(round(reference_price+depth))

        return book.submit_limit_order(side, price, timestamp, agent_id=self.agent_id)


'''
The liquidity takers just submit market orders with probability mu.
Probability of a buy order (so removing the cheapest ask) is given by q_taker, with sell order prob 1-q_taker.
'''
@dataclass
class LiquidityTaker:
    agent_id: int
    mu: float        #Probability of submitting a market order
    q_taker: float   # Probability of entering on the buy side


    def maybe_submit(
            self, book: OrderBook, timestamp: int, rng: Optional[random.Random] = None,
            q_taker: Optional[float] = None,
            ) -> Optional[OrderResult]:
        r = rng or random

        if r.random() >= self.mu:
            return None
        return self.submit(book, timestamp, r, q_taker)

    def submit(
            self, book: OrderBook, timestamp: int, rng: Optional[random.Random] = None,
            q_taker: Optional[float] = None,
            ) -> OrderResult:
        '''
        Submit a market order unconditionally: the part of maybe_submit that follows the mu draw.

        q_taker, if given, replaces this agent's own q_taker for this one order. That is how a shared,
        time-varying buy probability (see SideProbability below) reaches every taker: the simulation
        passes the current value in, so there is one q for the whole market at each step.
        '''
        r = rng or random
        q = self.q_taker if q_taker is None else q_taker
        side = Side.BID if r.random() < q else Side.ASK

        result, order_id =  book.submit_market_order(side, timestamp, agent_id=self.agent_id)
        return result

'''
Time-varying side probability ("asymmetric order flow", Preis et al. 2006, Fig. 3).

In the symmetric model q_taker is a constant 1/2. The paper's perturbation makes it a single,
market-wide quantity q_taker(t) that changes from step to step, so every taker in a step shares the
same buy probability and a temporary imbalance builds up (a "trend"). Two ways of changing it:

  BoundedRandomWalk   (Fig. 3a)  q moves +/-step with equal probability each step, reflected at
                                  centre +/- half_width (paper: step 0.001, half_width 0.05).
  MeanRevertingWalk   (Fig. 3c)  q moves one step toward the centre with probability
                                  1/2 + |q - centre|, else away (paper: step 0.001, half_width 1/2).

Each process holds the value in force now (.q) and moves to the next step's value on advance(rng).
The value is kept as an integer count k of steps from the centre, q = centre + k*step, so that
"exactly at the centre" and "exactly at a bound" are exact comparisons, not float ones.
A process is stateful: create a fresh one for every simulation run.
'''
class SideProbability(Protocol):
    """What the simulation needs from any of the processes below: the current probability, and a way
    to move to the next step's value.
    This just describes what q and advance should look like (what needs to be in them) the class is never actually called."""

    @property
    def q(self) -> float: ...

    def advance(self, rng: random.Random) -> None: ...


class ConstantSide:
    """A side probability that never changes (the symmetric baseline). Uses no random numbers.
    Doesn't actually do anything either, just returns q and advance as what they already are.
    Can be used in sims where q doesn't change, but can also just be skipped over by passing
    q_taker= to run_simulation instead."""

    def __init__(self, q: float):
        self._q = q

    @property
    def q(self) -> float:
        return self._q

    def advance(self, rng: random.Random) -> None:
        pass


class _LatticeWalk:
    """Shared machinery: q = centre + k*step with integer k reflected back into [-K, K]."""

    def __init__(self, step: float, half_width: float, centre: float = 0.5):
        if step <= 0:
            raise ValueError("step must be positive")
        n_steps_to_bound = round(half_width / step)
        if n_steps_to_bound < 1 or abs(n_steps_to_bound * step - half_width) > 1e-9:
            raise ValueError(f"half_width ({half_width}) must be a positive whole multiple of step ({step})")
        if centre - half_width < -1e-9 or centre + half_width > 1 + 1e-9:
            raise ValueError("centre +/- half_width must stay inside [0, 1]: q is a probability")
        self.step = step
        self.centre = centre
        self.K = n_steps_to_bound        # the walk lives in k = -K ... +K
        self.k = 0                       # starts exactly at the centre

    @property
    def q(self) -> float:
        return self.centre + self.k * self.step

    def _direction(self, rng: random.Random) -> int:
        """+1 or -1: which way to move this step. Defined by the subclass.
        Hence this is the only part of the walk not shared by the two methods in Fig. 3.
        So this is just a placeholder."""
        raise NotImplementedError

    def advance(self, rng: random.Random) -> None:
        self.k += self._direction(rng)
        # Reflecting boundary: a step past the bound is mirrored back inside, so it ends one step
        # inside the bound (K+1 -> K-1). The paper says "reflecting" without saying how.
        #Notice difference between current position k and max/min position K.
        if self.k > self.K:
            self.k = 2 * self.K - self.k
        elif self.k < -self.K:
            self.k = -2 * self.K - self.k


class BoundedRandomWalk(_LatticeWalk):
    """Fig. 3a: an unbiased random walk in q, reflected at centre +/- half_width."""

    def __init__(self, step: float = 0.001, half_width: float = 0.05, centre: float = 0.5):
        super().__init__(step, half_width, centre)

    def _direction(self, rng: random.Random) -> int:
        #Just 50/50 chance of either way
        return 1 if rng.random() < 0.5 else -1


class MeanRevertingWalk(_LatticeWalk):
    """
    Fig. 3c: each step q moves one step toward the centre with probability 1/2 + |q - centre|,
    otherwise one step away. At exactly the centre there is no "toward", so the direction is a fair
    coin flip (the paper doesn't cover this case).

    This is (a discrete) Ornstein-Uhlenbeck process: the average pull toward the centre is 2*step*(q - centre)
    per step, so q hovers within a standard deviation of sqrt(step/4) of the centre (0.016 for step 0.001)
    and forgets its past over about 1/(2*step) = 500 steps. The default half_width of 1/2 (q anywhere in
    [0, 1]) therefore almost never comes into play.
    """

    def __init__(self, step: float = 0.001, half_width: float = 0.5, centre: float = 0.5):
        super().__init__(step, half_width, centre)

    def _direction(self, rng: random.Random) -> int:
        if self.k == 0:
            return 1 if rng.random() < 0.5 else -1
        toward = -1 if self.k > 0 else 1
        p_toward = 0.5 + abs(self.k) * self.step
        return toward if rng.random() < p_toward else -toward
