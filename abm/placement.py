"""
Where providers place limit orders (docs/providers/decisions.md, D45).

The distance of a new limit order is measured in ticks from the best price on its own side (the best
bid for a buy, the best ask for a sell): Delta = 0 at the best, positive behind it, negative more
aggressive (towards and beyond the opposite best). Two distributions of Delta:

  "bmp"      Bouchaud, Mezard and Potters (2002): P(Delta) proportional to 1/(delta1 + Delta)^(1 + mu)
             for Delta >= 1, with Delta = -1 and 0 each as likely as Delta = 1, and an exponential
             taper beyond taper_start ticks (e^(-(Delta - taper_start)/taper_length)).
  "student"  Mike and Farmer (2008): a Student t with dof degrees of freedom and the given scale in
             ticks, centred on the best price, rounded to the nearest tick.

Two treatments of an order that would reach the opposite best price (cross the spread):

  "redraw"   draw the distance again until it does not, so providers only place limit orders.
  "allow"    place it anyway: it trades at once (D6), so the provider also acts as a taker.

If an order's own side of the book is empty, its distance is measured from one tick inside the
opposite best price; if both sides are empty, from the start price.
"""

from __future__ import annotations

import bisect
import math
import random
from dataclasses import dataclass, field
from typing import List, Optional

from abm.agents import LiquidityProvider
from abm.orderbook import OrderBook, Side

RULES = ("bmp", "student")
CROSSING = ("redraw", "allow")


@dataclass(frozen=True)
class PlacementSettings:
    rule: str = "bmp"
    crossing: str = "redraw"
    mu: float = 0.6                # bmp: power-law exponent
    delta1: float = 1.0            # bmp: offset
    taper_start: int = 100         # bmp: ticks beyond which the chance tapers off
    taper_length: float = 100.0    # bmp: length of the exponential taper, in ticks
    dof: float = 1.3               # student: degrees of freedom
    scale: float = 11.0            # student: scale, in ticks

    def __post_init__(self):
        if self.rule not in RULES:
            raise ValueError(f"rule must be one of {RULES}")
        if self.crossing not in CROSSING:
            raise ValueError(f"crossing must be one of {CROSSING}")
        if self.mu <= 0 or self.delta1 < 0 or self.taper_start < 1 or self.taper_length <= 0:
            raise ValueError("mu must be above 0, delta1 at least 0, taper_start at least 1, taper_length above 0")
        if self.dof <= 0 or self.scale <= 0:
            raise ValueError("dof and scale must be above 0")

    def describe(self) -> str:
        if self.rule == "bmp":
            shape = f"Bouchaud et al. (mu = {self.mu:g}, delta1 = {self.delta1:g}, taper beyond {self.taper_start})"
        else:
            shape = f"Mike and Farmer (Student t, {self.dof:g} dof, scale {self.scale:g} ticks)"
        return f"{shape}, crossing orders {'drawn again' if self.crossing == 'redraw' else 'allowed'}"


class DistanceSampler:
    """Draws Delta, in whole ticks, from the chosen distribution."""

    def __init__(self, settings: PlacementSettings):
        self.settings = settings
        if settings.rule == "bmp":
            s = settings
            # Weights for Delta = -1, 0, 1, 2, ...; the taper makes them negligible (e^-30) by the end.
            last = s.taper_start + int(30 * s.taper_length)
            near = (s.delta1 + 1) ** -(1 + s.mu)
            weights = [near, near]
            for delta in range(1, last + 1):
                w = (s.delta1 + delta) ** -(1 + s.mu)
                if delta > s.taper_start:
                    w *= math.exp(-(delta - s.taper_start) / s.taper_length)
                weights.append(w)
            total = sum(weights)
            self.values = list(range(-1, last + 1))
            self.cumulative: List[float] = []
            running = 0.0
            for w in weights:
                running += w / total
                self.cumulative.append(running)
            self.cumulative[-1] = 1.0

    def draw(self, rng: random.Random) -> int:
        s = self.settings
        if s.rule == "bmp":
            return self.values[bisect.bisect_left(self.cumulative, rng.random())]
        # Student t: a standard normal over the square root of a chi-squared / dof.
        chi2 = rng.gammavariate(s.dof / 2, 2.0)
        t = rng.gauss(0.0, 1.0) / math.sqrt(max(chi2, 1e-300) / s.dof)
        return int(round(s.scale * t))


@dataclass
class PlacementCounts:
    """Shared by all providers of a run: how many orders were placed, drawn again, or crossed."""
    placed: int = 0
    redrawn: int = 0
    crossed: int = 0


def reference_price(book: OrderBook, side: Side, fallback: int) -> int:
    """The best price on the order's own side; if that side is empty, one tick inside the opposite
    best price; if both are empty, the fallback (start) price."""
    own, other = (book.best_bid(), book.best_ask()) if side is Side.BID else (book.best_ask(), book.best_bid())
    if own is not None:
        return own
    if other is not None:
        return other - 1 if side is Side.BID else other + 1
    return int(fallback)


@dataclass
class PlacingProvider(LiquidityProvider):
    """A provider that acts like the paper's (chance alpha per step, side with chance q_provider), but
    places its order at a distance from the best price on its own side (D45). lambda_ is not used."""
    sampler: Optional[DistanceSampler] = field(default=None, repr=False)
    counts: Optional[PlacementCounts] = field(default=None, repr=False)

    def submit(self, book: OrderBook, timestamp: int, fallback_price: int, rng: Optional[random.Random] = None,
               lambda_: Optional[float] = None) -> int:
        r = rng or random
        side = Side.BID if r.random() < self.q_provider else Side.ASK
        ref = reference_price(book, side, fallback_price)
        opposite = book.best_ask() if side is Side.BID else book.best_bid()
        while True:
            delta = self.sampler.draw(r)
            price = ref - delta if side is Side.BID else ref + delta
            crosses = opposite is not None and (price >= opposite if side is Side.BID else price <= opposite)
            if not crosses or self.sampler.settings.crossing == "allow":
                break
            self.counts.redrawn += 1
        self.counts.placed += 1
        if crosses:
            self.counts.crossed += 1
        return book.submit_limit_order(side, price, timestamp, agent_id=self.agent_id, quantity=self.size)
