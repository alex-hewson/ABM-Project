"""
Hand-worked test cases for OrderBook. Run with: python -m tests.test_orderbook   (from the project root)

These aren't exhaustive, but they cover the core invariants you want to
trust before building agents on top of this: price-time priority, spread
narrowing/widening on trades, market order matching, cancellation, and the
edge case of an empty opposite book.
"""

from abm.orderbook import OrderBook, Side, OrderResult


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


def test_market_order_reports_execution_result():
    ob = OrderBook()
    ob.submit_limit_order(Side.ASK, price=101, timestamp=1, agent_id="maker")

    #Other side has liquidity --> should report EXECUTED
    result, order_id = ob.submit_market_order(Side.BID, timestamp=2, agent_id="taker")
    check("a trade was actually recorded", len(ob.trades) == 1)

    #Opposite side (asks) now empty --> should report NO_MATCH, not just pass.
    result2, order_id2 = ob.submit_market_order(Side.BID, timestamp=3, agent_id="taker2")
    check("market order against empty book reports NO_MATCH", result2 is OrderResult.NO_MATCH)
    check("no additional trade recorded on failed market order", len(ob.trades) == 1)
    check("order_id is still returned even on failure (for logging)", order_id2 is not None)


def test_depth_profile_and_total_orders():
    ob = OrderBook()
    ob.submit_limit_order(Side.BID, price=99, timestamp=1)
    ob.submit_limit_order(Side.BID, price=98, timestamp=1)
    ob.submit_limit_order(Side.ASK, price=101, timestamp=1)
    check("total_orders is 3", ob.total_orders() == 3)
    check("bid depth profile has two levels", len(ob.depth_profile(Side.BID)) == 2)


def _check_book_consistency(ob):
    """Compare the book's cached state against a brute-force recount from its price levels."""
    resting = [o.order_id for q in ob.bids.values() for o in q] + \
              [o.order_id for q in ob.asks.values() for o in q]
    assert ob.total_orders() == len(resting), "total_orders disagrees with the price levels"
    assert set(ob._resting_ids) == set(resting), "sampleable id list disagrees with the price levels"
    assert len(ob._resting_ids) == len(set(ob._resting_ids)), "duplicate ids in sampleable list"
    assert all(ob._resting_ids[pos] == oid for oid, pos in ob._resting_pos.items()), "id positions are stale"
    assert ob.best_bid() == (max(ob.bids) if ob.bids else None), "best_bid disagrees with brute force"
    assert ob.best_ask() == (min(ob.asks) if ob.asks else None), "best_ask disagrees with brute force"


def test_cached_state_stays_consistent_under_random_activity():
    import random
    rng = random.Random(0)
    ob = OrderBook()
    ids = []
    for step in range(4000):
        action = rng.random()
        if action < 0.5:
            side = Side.BID if rng.random() < 0.5 else Side.ASK
            ids.append(ob.submit_limit_order(side, 1000 + rng.randint(-30, 30), step))
        elif action < 0.7:
            ob.submit_market_order(Side.BID if rng.random() < 0.5 else Side.ASK, step)
        elif ids:
            ob.cancel_order(ids.pop(rng.randrange(len(ids))))
        _check_book_consistency(ob)
    check("total_orders, sampleable ids and best prices agree with brute force after 4000 random operations", True)


def test_heaps_stay_small_over_a_long_run():
    import random
    rng = random.Random(1)
    ob = OrderBook()
    # Bids in 900-999, asks in 1001-1100: nothing crosses, so orders rest and the book keeps a
    # steady population (~1 new order per step; a market order or cancellation removes ~1).
    for i in range(500):
        ob.submit_limit_order(Side.BID, rng.randint(900, 999), 0)
        ob.submit_limit_order(Side.ASK, rng.randint(1001, 1100), 0)
    for step in range(30_000):
        if rng.random() < 0.5:
            ob.submit_limit_order(Side.BID, rng.randint(900, 999), step)
        else:
            ob.submit_limit_order(Side.ASK, rng.randint(1001, 1100), step)
        if rng.random() < 0.25:
            ob.submit_market_order(Side.BID if rng.random() < 0.5 else Side.ASK, step)
        for oid in ob.sample_resting_order_ids(1 if rng.random() < 0.75 else 0, rng):
            ob.cancel_order(oid)
    check(f"book kept a steady population ({ob.total_orders()} orders)", 300 < ob.total_orders() < 5000)
    check(f"heap sizes ({len(ob._bid_heap)}, {len(ob._ask_heap)}) stay near the ~100 price levels per side, "
          f"not the ~30,000 orders submitted",
          len(ob._bid_heap) < 500 and len(ob._ask_heap) < 500)


def test_sample_resting_order_ids():
    import random
    rng = random.Random(2)
    ob = OrderBook()
    placed = {ob.submit_limit_order(Side.BID, 100 - i, 0) for i in range(20)}
    placed |= {ob.submit_limit_order(Side.ASK, 200 + i, 0) for i in range(20)}
    check("k=0 gives an empty list", ob.sample_resting_order_ids(0, rng) == [])
    sample = ob.sample_resting_order_ids(15, rng)
    check("15 distinct ids", len(sample) == 15 and len(set(sample)) == 15)
    check("all sampled ids are resting orders", set(sample) <= placed)
    check("sampling everything returns every resting order",
          set(ob.sample_resting_order_ids(40, rng)) == placed)
    counts = {}
    for _ in range(4000):
        for oid in ob.sample_resting_order_ids(4, rng):
            counts[oid] = counts.get(oid, 0) + 1
    # each of 40 orders is picked with probability 4/40 per draw -> expect 400 each
    check("sampling is roughly uniform (each order picked 300-500 times of 4000 draws)",
          all(300 < counts.get(oid, 0) < 500 for oid in placed))


def test_trade_hook_and_counter_without_storing_trades():
    def play(book):
        book.submit_limit_order(Side.BID, 100, 0)
        book.submit_limit_order(Side.ASK, 105, 0)
        book.submit_limit_order(Side.ASK, 106, 0)
        book.submit_market_order(Side.BID, 1)      # hits 105
        book.submit_market_order(Side.ASK, 2)      # hits 100
        book.submit_market_order(Side.BID, 3)      # hits 106
        book.submit_market_order(Side.BID, 4)      # nothing left on the ask side: no trade

    prices = []
    lean = OrderBook(keep_trades=False, on_trade=prices.append)
    full = OrderBook()
    play(lean)
    play(full)
    check("hook receives every trade price in order", prices == [105, 100, 106])
    check("n_trades counts trades whether or not they are stored", lean.n_trades == 3 and full.n_trades == 3)
    check("keep_trades=False stores no Trade objects", lean.trades == [])
    check("default still stores them", [t.price for t in full.trades] == [105, 100, 106])
    check("book state is identical either way", lean.best_bid() == full.best_bid() and
          lean.total_orders() == full.total_orders())


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")

