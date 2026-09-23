'''
Agents based on section 3 of the paper the orderbook model came from.

Testing matching functionality to the papers results to verify working model.
'''
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

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
            self, book: OrderBook, timestamp: int, rng: Optional[random.Random] = None
            ) -> Optional[OrderResult]:
        r = rng or random

        if r.random() >= self.mu:
            return None
        return self.submit(book, timestamp, r)

    def submit(
            self, book: OrderBook, timestamp: int, rng: Optional[random.Random] = None
            ) -> OrderResult:
        '''Submit a market order unconditionally: the part of maybe_submit that follows the mu draw.'''
        r = rng or random
        side = Side.BID if r.random() < self.q_taker else Side.ASK

        result, order_id =  book.submit_market_order(side, timestamp, agent_id=self.agent_id)
        return result