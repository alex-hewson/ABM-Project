"""
Limit order book with price-time priority matching.

Based on the structure described in Preis, Golke, Paul & Schneider (2006),
"Multi-agent-based Order Book Model of financial markets", EPL 75, 510.

Prices are represented as integers (ticks), not floats, to avoid
floating-point comparison bugs in price-time priority matching.
"""

from __future__ import annotations

import heapq
import itertools
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, Dict, List, Optional

# Enumeration defining simple order book, buy one side sell the other.
class Side(Enum):
    BID = 1   # buy
    ASK = -1  # sell

class OrderResult(Enum):
    '''
    Outcome of attempted match (for either market order or limit order)
    EXECUTED means a trade happened (obvs!)
    NO_MATCH means for limit order, there is no crossing, so just rests in the book
             for a market order means there is no liquidity (not good!)
    '''
    EXECUTED = 1
    NO_MATCH = 2


@dataclass
class Order:
    """A single resting limit order. Market orders don't need to be
    represented as objects since they execute immediately and never rest."""
    order_id: int
    side: Side
    price: int          # price tick
    timestamp: int       # simulation step at which it was submitted
    agent_id: Optional[int] = None


@dataclass
class Trade:
    """Record of an executed trade, for building price series / stats."""
    timestamp: int
    price: int
    aggressor_side: Side    # side of the order that triggered the trade
    resting_order_id: int
    resting_agent_id: Optional[int]
    aggressor_agent_id: Optional[int]

@dataclass
class MatchResult:
    result: OrderResult
    has_remainder: bool

class OrderBook:
    """
    Central limit order book for a single asset.

    Internally, each side is a dict[price_tick -> deque[Order]] for O(1)
    append/popleft at a given price level (time priority within a level).

    Best bid/ask are tracked via lazy-deletion heaps: a max-heap (via negated
    prices) for bids and a min-heap for asks. "Lazy deletion" means we don't
    remove stale price entries from the heap immediately when a level empties
    or a price is superseded -- we just skip them when popped. This avoids
    O(log n) heap operations on every single cancellation and keeps the
    common-case (matching at the current best price) cheap.
    """

    def __init__(self) -> None:
        self.bids: Dict[int, Deque[Order]] = {}
        self.asks: Dict[int, Deque[Order]] = {}

        self._bid_heap: List[int] = []   # stores -price (max-heap via min-heap)
        self._ask_heap: List[int] = []   # stores price (min-heap)

        self._order_lookup: Dict[int, Order] = {}   # order_id -> Order, for cancellation
        self._id_counter = itertools.count(1)

        self.trades: List[Trade] = []

    # ------------------------------------------------------------------ #
    # Order id generation
    # ------------------------------------------------------------------ #

    def next_order_id(self) -> int:
        return next(self._id_counter)

    # ------------------------------------------------------------------ #
    # Best price / spread queries
    # ------------------------------------------------------------------ #

    def best_bid(self) -> Optional[int]:
        heap = self._bid_heap
        while heap:
            price = -heap[0]
            if price in self.bids and self.bids[price]:
                return price
            heapq.heappop(heap)  # stale entry, discard
        return None

    def best_ask(self) -> Optional[int]:
        heap = self._ask_heap
        while heap:
            price = heap[0]
            if price in self.asks and self.asks[price]:
                return price
            heapq.heappop(heap)  # stale entry, discard
        return None

    def spread(self) -> Optional[int]:
        bb, ba = self.best_bid(), self.best_ask()
        if bb is None or ba is None:
            return None
        return ba - bb

    def mid_price(self) -> Optional[float]:
        bb, ba = self.best_bid(), self.best_ask()
        if bb is None or ba is None:
            return None
        return (bb + ba) / 2.0

    # ------------------------------------------------------------------ #
    # Depth / book state introspection
    # ------------------------------------------------------------------ #

    def depth_at(self, side: Side, price: int) -> int:
        book = self.bids if side is Side.BID else self.asks
        return len(book.get(price, ()))

    def depth_profile(self, side: Side) -> Dict[int, int]:
        """Number of resting orders at each occupied price level on one side."""
        book = self.bids if side is Side.BID else self.asks
        return {p: len(q) for p, q in book.items() if q}

    def total_orders(self) -> int:
        return sum(len(q) for q in self.bids.values()) + \
               sum(len(q) for q in self.asks.values())

    # ------------------------------------------------------------------ #
    # Submitting orders
    # ------------------------------------------------------------------ #

    def submit_limit_order(
        self, side: Side, price: int, timestamp: int, agent_id: Optional[int] = None
    ) -> int:
        """
        Submit a limit order. If it crosses the spread (marketable limit
        order) it executes immediately against resting orders, same as the
        paper's model. Any unexecuted remainder rests in the book.
        Returns the order_id (useful for later cancellation, even if the
        order fully executed and the id is now just a historical reference).
        """
        order_id = self.next_order_id()
        match = self._match_incoming(
            side=side, price=price, timestamp=timestamp,
            agent_id=agent_id, order_id=order_id, is_market_order=False,
        )
        if match.has_remainder:
            self._rest_order(Order(order_id, side, price, timestamp, agent_id))
        return order_id

    def submit_market_order(
        self, side: Side, timestamp: int, agent_id: Optional[int] = None
    ) -> tuple[OrderResult, int]:
        """
        Submit a market order. Executes immediately against the best
        available opposite-side price(s). If the book on the opposite side
        is empty, the order fails to execute, and is reported back via OrderResult.

        Returns (OrderResult, order_id). order_id is still returned on failure (more data).
        """
        order_id = self.next_order_id()
        match = self._match_incoming(
            side=side, price=None, timestamp=timestamp,
            agent_id=agent_id, order_id=order_id, is_market_order=True,
        )
        return match.result, order_id

    def _rest_order(self, order: Order) -> None:
        book = self.bids if order.side is Side.BID else self.asks
        book.setdefault(order.price, deque()).append(order)
        self._order_lookup[order.order_id] = order
        if order.side is Side.BID:
            heapq.heappush(self._bid_heap, -order.price)
        else:
            heapq.heappush(self._ask_heap, order.price)

    # ------------------------------------------------------------------ #
    # Matching engine core
    # ------------------------------------------------------------------ #

    def _match_incoming(
        self,
        side: Side,
        price: Optional[int],
        timestamp: int,
        agent_id: Optional[int],
        order_id: int,
        is_market_order: bool,
    ) -> "MatchResult":
        """
        Attempt to match an incoming order (market or marketable limit)
        against the opposite side of the book, walking through price
        levels if necessary (this is where price impact / slippage for
        larger orders would show up, though this base model uses unit
        order size so at most one resting order is consumed).

        Returns MatchResult with:
            result: OrderResult.EXECUTED if a trade happened
                    OrderResult.NO_MATCH otherwise
            has_remainder: True if there is any unmatched quantity that needs to rest in the orderbook (omly limit orders)
        """
        opposite_book = self.asks if side is Side.BID else self.bids

        while True:
            best_opposite = self.best_ask() if side is Side.BID else self.best_bid()
            if best_opposite is None:
                # opposite side of book is empty -- market order can't fill,
                # limit order has nothing to match against
                return MatchResult(OrderResult.NO_MATCH, has_remainder= not is_market_order)

            if is_market_order:
                crosses = True
            else:
                crosses = (price >= best_opposite) if side is Side.BID else (price <= best_opposite)

            if not crosses:
                return MatchResult(OrderResult.NO_MATCH, has_remainder=True)  # unmatched remainder rests in book

            queue = opposite_book[best_opposite]
            resting_order = queue[0]  # time priority: oldest order at this price

            self._execute_trade(
                timestamp=timestamp,
                price=best_opposite,
                aggressor_side=side,
                resting_order=resting_order,
                aggressor_agent_id=agent_id,
            )

            queue.popleft()
            if not queue:
                del opposite_book[best_opposite]
            self._order_lookup.pop(resting_order.order_id, None)

            # Unit order size in this base model: incoming order is now
            # fully filled after consuming exactly one resting order.
            return MatchResult(OrderResult.EXECUTED, has_remainder=False)

    def _execute_trade(
        self, timestamp: int, price: int, aggressor_side: Side,
        resting_order: Order, aggressor_agent_id: Optional[int],
    ) -> None:
        self.trades.append(Trade(
            timestamp=timestamp,
            price=price,
            aggressor_side=aggressor_side,
            resting_order_id=resting_order.order_id,
            resting_agent_id=resting_order.agent_id,
            aggressor_agent_id=aggressor_agent_id,
        ))

    # ------------------------------------------------------------------ #
    # Cancellation
    # ------------------------------------------------------------------ #

    def cancel_order(self, order_id: int) -> bool:
        """Remove a resting order from the book. Returns False if the
        order_id doesn't exist (already matched or already cancelled)."""
        order = self._order_lookup.pop(order_id, None)
        if order is None:
            return False
        book = self.bids if order.side is Side.BID else self.asks
        queue = book.get(order.price)
        if queue is None:
            return False
        try:
            queue.remove(order)  # O(k) in level depth; fine for typical depths
        except ValueError:
            return False
        if not queue:
            del book[order.price]
        return True

    def resting_order_ids(self, side: Side) -> List[int]:
        """All order_ids currently resting on one side -- useful for the
        per-step cancellation sweep with probability delta."""
        book = self.bids if side is Side.BID else self.asks
        return [o.order_id for q in book.values() for o in q]
