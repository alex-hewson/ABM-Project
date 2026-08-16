"""
Hand-worked test cases for OrderBook. Run with: python3 test_orderbook.py

These aren't exhaustive, but they cover the core invariants you want to
trust before building agents on top of this: price-time priority, spread
narrowing/widening on trades, market order matching, cancellation, and the
edge case of an empty opposite book.
"""

from orderbook import OrderBook, Side


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    assert condition, f"FAILED: {label}"


def test_empty_book():
    ob = OrderBook()
    check("empty book: best_bid is None", ob.best_bid() is None)
    check("empty book: best_ask is None", ob.best_ask() is None)
    check("empty book: spread is None", ob.spread() is None)


def test_basic_resting_and_priority():
    ob = OrderBook()
    # Two bids at the same price -- time priority means first in, first matched
    id1 = ob.submit_limit_order(Side.BID, price=100, timestamp=1, agent_id="A")
    id2 = ob.submit_limit_order(Side.BID, price=100, timestamp=2, agent_id="B")
    check("best_bid is 100 after two resting bids", ob.best_bid() == 100)
    check("depth at 100 is 2", ob.depth_at(Side.BID, 100) == 2)

    # A market sell should match the OLDEST bid (agent A) first
    ob.submit_market_order(Side.ASK, timestamp=3, agent_id="C")
    check("one trade recorded", len(ob.trades) == 1)
    trade = ob.trades[0]
    check("trade matched resting agent A (time priority)", trade.resting_agent_id == "A")
    check("trade price is 100", trade.price == 100)
    check("depth at 100 now 1 (agent B still resting)", ob.depth_at(Side.BID, 100) == 1)


def test_spread_and_matching_like_paper_figure_1():
    # Loosely follows the structure of Fig. 1 in Preis et al.: a resting
    # ask and bid at the same price get matched, spread widens afterward.
    ob = OrderBook()
    ob.submit_limit_order(Side.BID, price=100, timestamp=1, agent_id="bidder")
    ob.submit_limit_order(Side.ASK, price=102, timestamp=1, agent_id="asker")
    check("initial spread is 2", ob.spread() == 2)

    # A marketable limit buy at 102 crosses and trades immediately
    ob.submit_limit_order(Side.BID, price=102, timestamp=2, agent_id="aggressive_buyer")
    check("trade occurred at price 102", ob.trades[-1].price == 102)
    check("ask side now empty at 102", ob.depth_at(Side.ASK, 102) == 0)
    # best bid falls back to the earlier resting bid at 100
    check("best_bid falls back to 100", ob.best_bid() == 100)
    check("best_ask is now None (no asks left)", ob.best_ask() is None)


def test_market_order_against_empty_book_is_dropped_not_raised():
    ob = OrderBook()
    # No asks in the book at all -- a market buy should just do nothing
    ob.submit_market_order(Side.BID, timestamp=1, agent_id="X")
    check("no trades recorded", len(ob.trades) == 0)
    check("book still empty", ob.total_orders() == 0)


def test_cancellation():
    ob = OrderBook()
    id1 = ob.submit_limit_order(Side.BID, price=100, timestamp=1, agent_id="A")
    id2 = ob.submit_limit_order(Side.BID, price=100, timestamp=2, agent_id="B")
    ok = ob.cancel_order(id1)
    check("cancel returns True for existing order", ok is True)
    check("depth at 100 now 1 after cancelling agent A", ob.depth_at(Side.BID, 100) == 1)
    # market sell should now match agent B (the only one left)
    ob.submit_market_order(Side.ASK, timestamp=3, agent_id="C")
    check("trade matched remaining agent B", ob.trades[-1].resting_agent_id == "B")

    # cancelling a non-existent / already-matched order should return False, not raise
    check("cancel on already-matched order returns False", ob.cancel_order(id1) is False)


def test_price_level_removed_when_emptied():
    ob = OrderBook()
    oid = ob.submit_limit_order(Side.ASK, price=105, timestamp=1, agent_id="A")
    check("price level 105 present", 105 in ob.depth_profile(Side.ASK))
    ob.cancel_order(oid)
    check("price level 105 removed after cancel empties it", 105 not in ob.depth_profile(Side.ASK))
    check("best_ask is None after emptying only level", ob.best_ask() is None)


def test_best_price_walks_correctly_after_level_exhausted():
    ob = OrderBook()
    ob.submit_limit_order(Side.ASK, price=101, timestamp=1, agent_id="A")
    ob.submit_limit_order(Side.ASK, price=102, timestamp=1, agent_id="B")
    check("best ask starts at 101", ob.best_ask() == 101)
    ob.submit_market_order(Side.BID, timestamp=2, agent_id="taker1")
    check("best ask now 102 after 101 consumed", ob.best_ask() == 102)


def test_depth_profile_and_total_orders():
    ob = OrderBook()
    ob.submit_limit_order(Side.BID, price=99, timestamp=1)
    ob.submit_limit_order(Side.BID, price=98, timestamp=1)
    ob.submit_limit_order(Side.ASK, price=101, timestamp=1)
    check("total_orders is 3", ob.total_orders() == 3)
    check("bid depth profile has two levels", len(ob.depth_profile(Side.BID)) == 2)


if __name__ == "__main__":
    test_empty_book()
    test_basic_resting_and_priority()
    test_spread_and_matching_like_paper_figure_1()
    test_market_order_against_empty_book_is_dropped_not_raised()
    test_cancellation()
    test_price_level_removed_when_emptied()
    test_best_price_walks_correctly_after_level_exhausted()
    test_depth_profile_and_total_orders()
    print("\nAll tests passed.")

