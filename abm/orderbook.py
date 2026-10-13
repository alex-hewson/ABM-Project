"""
Limit order book with price-time priority matching.

Based on the structure described in Preis, Golke, Paul & Schneider (2006),
"Multi-agent-based Order Book Model of financial markets", EPL 75, 510.

Prices are represented as integers (ticks), not floats, to avoid
floating-point comparison bugs in price-time priority matching. ()
"""

from __future__ import annotations

import heapq
import itertools
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Deque, Dict, List, Optional

# Enumeration defining simple order book, buy one side sell the other.
class Side(Enum):
    BID = 1   # buy
    ASK = -1  # sell

class OrderResult(Enum):
    '''
    Outcome of attempted match (for either market order or limit order)
    EXECUTED means a trade happened (obvs!), and the whole order was filled
    NO_MATCH means for limit order, there is no crossing, so just rests in the book
             for a market order means there is no liquidity (not good!)
    '''
    EXECUTED = 1
    NO_MATCH = 2
    # Only possible for orders bigger than one unit: part of the order traded and part did not.
    # A market order that used up the whole opposite side, or a limit order whose remainder now rests.
    PARTIAL = 3


# slots=True stores each order compactly (no per-order dict), and eq=False makes two orders "equal" only
# if they are the very same object. Both make the book faster, and neither changes what it does: order
# ids are unique, so two different orders were never equal anyway.
@dataclass(slots=True, eq=False)
class Order:
    """A single resting limit order. Market orders don't need to be
    represented as objects since they execute immediately and never rest."""
    order_id: int
    side: Side
    price: int          # price tick
    timestamp: int       # simulation step at which it was submitted
    agent_id: Optional[int] = None
    quantity: int = 1    # units still unfilled. Goes down as the order is partly filled; 1 in the base model


@dataclass
class Trade:
    """Record of an executed trade, for building price series / stats."""
    timestamp: int
    price: int
    aggressor_side: Side    # side of the order that triggered the trade
    resting_order_id: int
    resting_agent_id: Optional[int]
    aggressor_agent_id: Optional[int]
    quantity: int = 1       # units that changed hands in this trade

@dataclass
class MatchResult:
    """Records the outcome of an incoming order, importantly the amount of unfilled remainder that needs to rest in the book (for limit orders)
    In a limit order that doesn't cross the spread, remainder is the whole order."""
    result: OrderResult
    remaining: int       # units of the incoming order that did not trade (0 if it was filled completely)

class OrderBook:
    """
    Central limit order book for a single asset.

    Internally, each side is a dict[price_tick -> deque[Order]], so each price level is given by a deque of resting orders.
    When a order is matched, the deque is popped from the left (oldest order at that price). New orders enter the right of the deque (time priority within a level)
    
    To find the best bid/ask, a heap of prices is kept for each side. (Heap is only used for this, it only keeps one entry of each price level in the book)
    Best ask uses a min-heap, best bid uses a max-heap (done by making the prices negative and using a min-heap).
    The heap is lazily cleaned of stale entries (by seeing if the current best price is still in the book, so don't check whole heap on every order).
    The heap is also cleaned when it grows too large (more than 2x number of price levels + 64), to avoid large growth from stale entries.
    """

    def __init__(self, keep_trades: bool = True, on_trade: Optional[Callable[[int], None]] = None) -> None:
        """
        keep_trades=False stops the book storing a Trade object per trade (self.trades stays empty;
        self.n_trades still counts them). A 10^6-step run executes millions of trades, so long runs
        that don't need the full record should turn this off.
        on_trade, if given, is called with the price of every trade as it happens.
        """
        self.bids: Dict[int, Deque[Order]] = {}
        self.asks: Dict[int, Deque[Order]] = {}

        self._bid_heap: List[int] = []   # stores -price (max-heap via min-heap)
        self._ask_heap: List[int] = []   # stores price (min-heap)

        self._order_lookup: Dict[int, Order] = {}   # order_id -> Order, for cancellation

        # Resting order ids as an indexable list (with id -> position), so that a uniformly
        # random subset can be drawn in O(k). Removal swaps the last id into the gap, to avoid shifting the whole list.
        self._resting_ids: List[int] = []
        self._resting_pos: Dict[int, int] = {}
        self._id_counter = itertools.count(1)

        # Running totals for each side, kept up to date on every order so they never need recounting:
        # the number of resting orders, and their total size in units. The two are equal while every
        # order is one unit.
        self._bid_orders = 0
        self._ask_orders = 0
        self._bid_volume = 0
        self._ask_volume = 0

        self.trades: List[Trade] = []
        self.n_trades = 0            # number of trades, whatever their size
        self.volume_traded = 0       # units traded (equal to n_trades while every order is one unit)
        self._keep_trades = keep_trades
        self._on_trade = on_trade

    # ------------------------------------------------------------------ #
    # Order id generation
    # ------------------------------------------------------------------ #

    def next_order_id(self) -> int:
        return next(self._id_counter)

    # ------------------------------------------------------------------ #
    # Best price / spread queries
    # ------------------------------------------------------------------ #

    def best_bid(self) -> Optional[int]:
        """Heap just checks if the best price is still in book, and removes it until it is. Returns None if the book is empty."""
        heap = self._bid_heap
        while heap:
            price = -heap[0] #negative heap, since heapq is a min-heap and we need a max-heap for bids
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
        """Number of resting units at a given price level on one side (the sizes of the orders there, added up).

        Currently not used, but is faster than depth_profile() if only one level is needed. (Perhaps for an advanced liquidity taker that wants to see depth before ordering.)"""
        book = self.bids if side is Side.BID else self.asks
        return sum(o.quantity for o in book.get(price, ()))

    def depth_profile(self, side: Side) -> Dict[int, int]:
        """Number of resting units at each occupied price level on one side.
        Essentially just depth_at() for all levels, as a dict."""
        book = self.bids if side is Side.BID else self.asks
        return {p: sum(o.quantity for o in q) for p, q in book.items() if q}

    def total_orders(self) -> int:
        """Number of resting orders, whatever their size. This is what cancellation works on: an order
        is cancelled as a whole."""
        return len(self._order_lookup)

    def total_volume(self) -> int:
        """Number of resting units: the sizes of all resting orders added up."""
        return self._bid_volume + self._ask_volume

    def orders_on(self, side: Side) -> int:
        """Number of resting orders on one side."""
        return self._bid_orders if side is Side.BID else self._ask_orders

    def volume_on(self, side: Side) -> int:
        """Number of resting units on one side."""
        return self._bid_volume if side is Side.BID else self._ask_volume

    # ------------------------------------------------------------------ #
    # Submitting orders
    # ------------------------------------------------------------------ #

    def submit_limit_order(
        self, side: Side, price: int, timestamp: int, agent_id: Optional[int] = None, quantity: int = 1
    ) -> int:
        """
        Submit a limit order. If it crosses the spread (marketable limit
        order) it executes immediately against resting orders, same as the
        paper's model. Any unexecuted remainder rests in the book.
        Returns the order_id (useful for later cancellation, even if the
        order fully executed and the id is now just a historical reference).

        quantity is the size of the order in units (1 in the base model). A bigger order rests as ONE
        order with that size: it keeps its place in the queue while it is filled bit by bit, and
        cancel_order removes whatever is left of it in one go.
        """
        if quantity < 1:
            raise ValueError("quantity must be at least 1")
        order_id = self.next_order_id()
        match = self._match_incoming(
            side=side, price=price, timestamp=timestamp,
            agent_id=agent_id, order_id=order_id, is_market_order=False, quantity=quantity,
        )
        if match.remaining > 0:
            self._rest_order(Order(order_id, side, price, timestamp, agent_id, quantity=match.remaining))
        return order_id

    def submit_market_order(
        self, side: Side, timestamp: int, agent_id: Optional[int] = None, quantity: int = 1
    ) -> tuple[OrderResult, int]:
        """
        Submit a market order. Executes immediately against the best
        available opposite-side price(s). If the book on the opposite side
        is empty, the order fails to execute, and is reported back via OrderResult.

        Returns (OrderResult, order_id). order_id is still returned on failure (more data).

        quantity is the size of the order in units (1 in the base model). A bigger order takes the best
        price first, then the next best, and so on until it is filled. If the opposite side runs out
        first, the result is PARTIAL (or NO_MATCH if nothing traded at all) and the unfilled part is
        dropped: a market order never rests. volume_traded shows how many units did trade.
        """
        if quantity < 1:
            raise ValueError("quantity must be at least 1")
        order_id = self.next_order_id()
        match = self._match_incoming(
            side=side, price=None, timestamp=timestamp,
            agent_id=agent_id, order_id=order_id, is_market_order=True, quantity=quantity,
        )
        return match.result, order_id

    def _rest_order(self, order: Order) -> None:
        book = self.bids if order.side is Side.BID else self.asks
        new_level = order.price not in book                #Only make a new order level if there isn't already one at that price
        book.setdefault(order.price, deque()).append(order)   #dict.setdefault(key, default)
        #The line above does the following: if order.price is present in book (the dict), it leaves book untouched, and returns the existing deque at that order.price.
        #If order.price isn't in the book, it makes an empty deque() at that value.
        #In both cases it then appends the new order to the deque. (So last in the time priority, since they pop left)

        self._order_lookup[order.order_id] = order    #Puts the order in the order_id -> Order dict
        self._resting_pos[order.order_id] = len(self._resting_ids) #Finds the position of the order in the resting_ids list (it will be the next entry in the list after it is appended to it, so its index will be the length before its added). Adds this position to the resting_pos dict.
        self._resting_ids.append(order.order_id) #Appends the id to the resting_ids list
        if order.side is Side.BID:
            self._bid_orders += 1
            self._bid_volume += order.quantity
        else:
            self._ask_orders += 1
            self._ask_volume += order.quantity

        # A price only needs a heap entry when its level is created; pushing one per order
        # (an earlier grew the heaps without bound.)
        if new_level:
            if order.side is Side.BID:
                heapq.heappush(self._bid_heap, -order.price)
                if len(self._bid_heap) > 2 * len(self.bids) + 64:
                    self._bid_heap = [-p for p in self.bids]     # drop stale entries
                    heapq.heapify(self._bid_heap)
            else:
                heapq.heappush(self._ask_heap, order.price)
                if len(self._ask_heap) > 2 * len(self.asks) + 64:
                    self._ask_heap = list(self.asks)
                    heapq.heapify(self._ask_heap)

    def _forget(self, order_id: int) -> Optional[Order]:
        """Stop tracking a resting order (matched or cancelled). Returns the Order,
        or None if it wasn't resting."""
        order = self._order_lookup.pop(order_id, None)
        if order is None:
            return None
        pos = self._resting_pos.pop(order_id)    #Deletes the order_id -> position entry from _resting_pos, and returns the value stored there (the position/index of the order in _resting_ids)
        last_id = self._resting_ids.pop()
        if last_id != order_id:              # move the last id into the freed slot
            self._resting_ids[pos] = last_id
            self._resting_pos[last_id] = pos
        # order.quantity is whatever was still unfilled: 0 if it traded completely (its units were
        # already taken off the volume trade by trade), all that was left of it if it was cancelled.
        if order.side is Side.BID:
            self._bid_orders -= 1
            self._bid_volume -= order.quantity
        else:
            self._ask_orders -= 1
            self._ask_volume -= order.quantity
        return order

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
        quantity: int = 1,
    ) -> "MatchResult":
        """
        Attempt to match an incoming order (market or marketable limit)
        against the opposite side of the book, walking through price
        levels if necessary (this is where price impact / slippage for
        larger orders shows up: an order of one unit consumes at most one
        resting unit, a bigger order can work through several orders and levels).

        Returns MatchResult with:
            result: OrderResult.EXECUTED if the whole order traded
                    OrderResult.PARTIAL if only part of it traded
                    OrderResult.NO_MATCH if none of it traded
            remaining: units that did not trade. For a limit order these rest in the orderbook; for a market order they are dropped.
        """
        opposite_book = self.asks if side is Side.BID else self.bids
        remaining = quantity

        while remaining > 0:
            best_opposite = self.best_ask() if side is Side.BID else self.best_bid()
            if best_opposite is None:
                # opposite side of book is empty -- market order can't fill (any further),
                # limit order has nothing (more) to match against
                break

            if is_market_order:
                crosses = True  #Market order always crosses the spread, since it just executes at the best available price
            else:
                assert price is not None
                crosses = (price >= best_opposite) if side is Side.BID else (price <= best_opposite) #Checks if limit order crosses the spread, True if it does, False if it doesn't.

            if not crosses:
                break  # the unmatched remainder of a limit order rests in the book

            queue = opposite_book[best_opposite]
            resting_order = queue[0]  # time priority: oldest order at this price

            # Trade as much as both orders allow: the whole resting order, or only part of it if the
            # incoming order is smaller. With unit orders this is always exactly 1.
            traded = min(remaining, resting_order.quantity)
            self._execute_trade(
                timestamp=timestamp,
                price=best_opposite,
                aggressor_side=side,
                resting_order=resting_order,
                aggressor_agent_id=agent_id,
                quantity=traded,
            )
            remaining -= traded
            resting_order.quantity -= traded
            if side is Side.BID:          # a buy takes units off the ask side, a sell off the bid side
                self._ask_volume -= traded
            else:
                self._bid_volume -= traded

            if resting_order.quantity == 0:
                # Resting order completely filled: take it out of the queue. A partly filled one stays
                # at the front, so it keeps its time priority.
                queue.popleft()
                if not queue:
                    del opposite_book[best_opposite]
                self._forget(resting_order.order_id)     #If the level is now empty (popped the last entry), delete the level from the book and forget the order id from the resting order list.

        if remaining == 0:
            return MatchResult(OrderResult.EXECUTED, remaining=0)
        if remaining == quantity:
            return MatchResult(OrderResult.NO_MATCH, remaining=remaining)
        return MatchResult(OrderResult.PARTIAL, remaining=remaining)

    def _execute_trade(
        self, timestamp: int, price: int, aggressor_side: Side,
        resting_order: Order, aggressor_agent_id: Optional[int], quantity: int = 1,
    ) -> None:
        self.n_trades += 1
        self.volume_traded += quantity
        if self._on_trade is not None:
            self._on_trade(price)
        if self._keep_trades:
            self.trades.append(Trade(
                timestamp=timestamp,
                price=price,
                aggressor_side=aggressor_side,
                resting_order_id=resting_order.order_id,
                resting_agent_id=resting_order.agent_id,
                aggressor_agent_id=aggressor_agent_id,
                quantity=quantity,
            ))

    # ------------------------------------------------------------------ #
    # Cancellation
    # ------------------------------------------------------------------ #

    def cancel_order(self, order_id: int) -> bool:
        """Remove a resting order from the book. Returns False if the
        order_id doesn't exist (already matched or already cancelled)."""
        order = self._forget(order_id)
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

    def sample_resting_order_ids(self, k: int, rng) -> List[int]:
        """k distinct resting order ids chosen uniformly at random (both sides), in O(k).
        rng is a random.Random."""
        return rng.sample(self._resting_ids, k)

    def resting_order_ids(self, side: Side) -> List[int]:
        """All order_ids currently resting on one side -- useful for the
        per-step cancellation sweep with probability delta."""
        book = self.bids if side is Side.BID else self.asks
        return [o.order_id for q in book.values() for o in q]
        """
        To read the above return more easily, it is equivalent to this:
        result = []
        for q in book.values():        # outer loop: q is each price level's deque
            for o in q:                 # inner loop: o is each Order in that deque
                result.append(o.order_id)
        return result
        """
