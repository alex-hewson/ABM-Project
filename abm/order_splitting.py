"""
Order splitting (docs/takers/decisions.md, D42), after Lillo, Mike and Farmer (2005).

N hidden (large) orders are active at all times. A share of the takers are splitters: when a
splitter acts, it places one unit of one of the N hidden orders, picked at random with equal chance,
on that order's side. A hidden order's size L, in units, has P(L >= x) = x^(-alpha) for x = 1, 2, ...
(a pure power law, smallest size 1, no cap), and its side is a buy or a sell with equal chance. When
its last unit is placed it is replaced at once by a new one. The other takers are the paper's random
takers, unchanged. Every hidden order is worked at the same pace on average, as in the paper.

The hidden orders draw from their own random numbers, so the sizes and sides do not depend on the
rest of the run.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional

from abm.agents import LiquidityTaker
from abm.orderbook import OrderBook, OrderResult, Side


@dataclass(frozen=True)
class SplittingSettings:
    share: float = 0.85        # f: share of the takers that are splitters (so, on average, of market orders)
    n_hidden: int = 2          # N: hidden orders active at once
    alpha: float = 1.6         # tail exponent of the hidden order sizes

    def __post_init__(self):
        if not 0 < self.share <= 1:
            raise ValueError("share must be above 0 and at most 1")
        if not (isinstance(self.n_hidden, int) and self.n_hidden >= 1):
            raise ValueError("n_hidden must be a whole number, at least 1")
        if not self.alpha > 1:
            raise ValueError("alpha must be above 1 (below it the mean size is infinite)")

    def describe(self) -> str:
        return f"share {self.share:g}, N = {self.n_hidden}, alpha = {self.alpha:g}"


class HiddenOrders:
    """The N hidden orders: each one's units left to place and its side."""

    def __init__(self, settings: SplittingSettings, rng: random.Random):
        self.settings = settings
        self.rng = rng
        self.remaining: List[int] = [0] * settings.n_hidden
        self.sides: List[Side] = [Side.BID] * settings.n_hidden
        self.sizes: List[int] = []             # the size of every hidden order started, in order
        for i in range(settings.n_hidden):
            self._start(i)

    def draw_size(self) -> int:
        """L = floor(U^(-1/alpha)) with U uniform on (0, 1], so P(L >= x) = x^(-alpha) for whole x >= 1."""
        u = 1.0 - self.rng.random()            # (0, 1]: never 0, so the size is always finite
        return int(u ** (-1.0 / self.settings.alpha))

    def _start(self, i: int) -> None:
        size = self.draw_size()
        self.remaining[i] = size
        self.sides[i] = Side.BID if self.rng.random() < 0.5 else Side.ASK
        self.sizes.append(size)

    def next_side(self) -> Side:
        """Pick a hidden order at random, take one unit from it, and return its side. A finished hidden
        order is replaced at once by a new one."""
        i = self.rng.randrange(self.settings.n_hidden)
        side = self.sides[i]
        self.remaining[i] -= 1
        if self.remaining[i] == 0:
            self._start(i)
        return side


@dataclass
class SplittingTaker(LiquidityTaker):
    """A taker that acts like the paper's takers (chance mu per step), but whose market orders are
    units of the shared hidden orders instead of random sides. q_taker and the shared q(t) are not
    used."""
    hidden: Optional[HiddenOrders] = field(default=None, repr=False)

    def submit(self, book: OrderBook, timestamp: int, rng: Optional[random.Random] = None,
               q_taker: Optional[float] = None) -> OrderResult:
        side = self.hidden.next_side()
        result, _ = book.submit_market_order(side, timestamp, agent_id=self.agent_id, quantity=1)
        return result
