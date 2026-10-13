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
    for side, levels in ((Side.BID, ob.bids), (Side.ASK, ob.asks)):
        orders = [o for q in levels.values() for o in q]
        assert ob.orders_on(side) == len(orders), "orders_on disagrees with the price levels"
        assert ob.volume_on(side) == sum(o.quantity for o in orders), "volume_on disagrees with the price levels"
        assert all(o.quantity >= 1 for o in orders), "a resting order with nothing left was not removed"
    assert ob.total_volume() == ob.volume_on(Side.BID) + ob.volume_on(Side.ASK)


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

def raises_value_error(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except ValueError:
        return True
    return False


def test_unit_orders_count_the_same_as_orders_or_as_volume():
    ob = OrderBook()
    ob.submit_limit_order(Side.BID, price=99, timestamp=1)
    ob.submit_limit_order(Side.BID, price=99, timestamp=2)
    ob.submit_limit_order(Side.ASK, price=101, timestamp=3)
    check("orders and volume agree per side", ob.orders_on(Side.BID) == ob.volume_on(Side.BID) == 2
          and ob.orders_on(Side.ASK) == ob.volume_on(Side.ASK) == 1)
    check("and in total", ob.total_orders() == ob.total_volume() == 3)
    ob.submit_market_order(Side.ASK, timestamp=4)
    check("a unit trade counts once as a trade and once as volume", ob.n_trades == 1 and ob.volume_traded == 1)
    check("the trade record has quantity 1", ob.trades[0].quantity == 1)


def test_sized_limit_order_rests_as_one_order():
    ob = OrderBook()
    ob.submit_limit_order(Side.BID, price=99, timestamp=1, quantity=4)
    check("one order", ob.total_orders() == 1 and ob.orders_on(Side.BID) == 1)
    check("of four units", ob.total_volume() == 4 and ob.volume_on(Side.BID) == 4)
    check("depth at its price is in units", ob.depth_at(Side.BID, 99) == 4 and ob.depth_profile(Side.BID) == {99: 4})
    check("nothing on the other side", ob.volume_on(Side.ASK) == 0 and ob.orders_on(Side.ASK) == 0)


def test_sized_market_order_fills_oldest_first_and_leaves_the_rest():
    ob = OrderBook()
    first = ob.submit_limit_order(Side.ASK, price=101, timestamp=1, agent_id="first", quantity=2)
    second = ob.submit_limit_order(Side.ASK, price=101, timestamp=2, agent_id="second", quantity=4)
    result, _ = ob.submit_market_order(Side.BID, timestamp=3, agent_id="taker", quantity=3)
    check("fully filled: EXECUTED", result is OrderResult.EXECUTED)
    check("two trades: 2 units from the older order, then 1 from the newer",
          [(tr.resting_order_id, tr.quantity) for tr in ob.trades] == [(first, 2), (second, 1)])
    check("n_trades counts trades, volume_traded counts units", ob.n_trades == 2 and ob.volume_traded == 3)
    check("the older order is gone, the newer one has 3 units left",
          ob.total_orders() == 1 and ob.depth_at(Side.ASK, 101) == 3 and ob.volume_on(Side.ASK) == 3)


def test_sized_market_order_walks_through_price_levels():
    ob = OrderBook()
    ob.submit_limit_order(Side.ASK, price=101, timestamp=1, quantity=2)
    ob.submit_limit_order(Side.ASK, price=102, timestamp=1, quantity=2)
    ob.submit_limit_order(Side.ASK, price=103, timestamp=1, quantity=5)
    result, _ = ob.submit_market_order(Side.BID, timestamp=2, quantity=6)
    check("fully filled", result is OrderResult.EXECUTED)
    check("best price first, then the next: 2 @ 101, 2 @ 102, 2 @ 103",
          [(tr.price, tr.quantity) for tr in ob.trades] == [(101, 2), (102, 2), (103, 2)])
    check("the emptied levels are gone and the best ask has moved up", ob.best_ask() == 103)
    check("3 units are left at 103", ob.depth_profile(Side.ASK) == {103: 3})


def test_market_order_bigger_than_the_book_side_is_partly_filled():
    ob = OrderBook()
    ob.submit_limit_order(Side.BID, price=99, timestamp=1, quantity=3)
    ob.submit_limit_order(Side.BID, price=98, timestamp=1, quantity=2)
    result, _ = ob.submit_market_order(Side.ASK, timestamp=2, quantity=8)
    check("only part traded: PARTIAL", result is OrderResult.PARTIAL)
    check("everything available traded: 5 units", ob.volume_traded == 5)
    check("the bid side is now empty", ob.best_bid() is None and ob.volume_on(Side.BID) == 0 and ob.total_orders() == 0)
    check("the unfilled 3 units did not rest anywhere", ob.volume_on(Side.ASK) == 0)
    result2, _ = ob.submit_market_order(Side.ASK, timestamp=3, quantity=8)
    check("against the now-empty side nothing trades: NO_MATCH", result2 is OrderResult.NO_MATCH and ob.volume_traded == 5)


def test_partly_filled_order_keeps_its_place_in_the_queue():
    ob = OrderBook()
    big = ob.submit_limit_order(Side.ASK, price=101, timestamp=1, quantity=4)
    small = ob.submit_limit_order(Side.ASK, price=101, timestamp=2, quantity=1)
    ob.submit_market_order(Side.BID, timestamp=3)
    ob.submit_market_order(Side.BID, timestamp=4)
    check("both unit market orders hit the older, bigger order", [tr.resting_order_id for tr in ob.trades] == [big, big])
    check("it has 2 units left and is still ahead of the newer order",
          ob.asks[101][0].order_id == big and ob.asks[101][0].quantity == 2 and ob.asks[101][1].order_id == small)


def test_cancelling_a_sized_order_removes_all_that_is_left_of_it():
    ob = OrderBook()
    big = ob.submit_limit_order(Side.BID, price=99, timestamp=1, quantity=4)
    ob.submit_limit_order(Side.BID, price=99, timestamp=2, quantity=1)
    ob.submit_market_order(Side.ASK, timestamp=3)             # the big order now has 3 units left
    check("before cancelling: 2 orders, 4 units", ob.orders_on(Side.BID) == 2 and ob.volume_on(Side.BID) == 4)
    check("cancel succeeds", ob.cancel_order(big) is True)
    check("the whole remainder went in one go: 1 order, 1 unit left",
          ob.orders_on(Side.BID) == 1 and ob.volume_on(Side.BID) == 1 and ob.depth_at(Side.BID, 99) == 1)
    check("cancelling it again does nothing", ob.cancel_order(big) is False and ob.volume_on(Side.BID) == 1)


def test_sized_limit_order_that_crosses_trades_then_rests_the_remainder():
    ob = OrderBook()
    ob.submit_limit_order(Side.ASK, price=101, timestamp=1, quantity=2)
    ob.submit_limit_order(Side.ASK, price=102, timestamp=1, quantity=2)
    ob.submit_limit_order(Side.ASK, price=103, timestamp=1, quantity=4)
    bid = ob.submit_limit_order(Side.BID, price=102, timestamp=2, quantity=5)
    check("it trades with every ask at or below its limit: 2 @ 101, 2 @ 102",
          [(tr.price, tr.quantity) for tr in ob.trades] == [(101, 2), (102, 2)])
    check("it does not trade above its limit", ob.depth_profile(Side.ASK) == {103: 4})
    check("the 1 unit left over rests as a bid at its limit price",
          ob.best_bid() == 102 and ob.depth_profile(Side.BID) == {102: 1} and ob.bids[102][0].order_id == bid)


def test_order_size_must_be_at_least_one():
    ob = OrderBook()
    check("limit order of size 0 rejected", raises_value_error(ob.submit_limit_order, Side.BID, 99, 1, quantity=0))
    check("market order of size 0 rejected", raises_value_error(ob.submit_market_order, Side.BID, 1, quantity=0))
    check("nothing was added to the book", ob.total_orders() == 0)


def test_counters_stay_consistent_with_sized_orders_under_random_activity():
    import random
    rng = random.Random(5)
    ob = OrderBook()
    ids = []
    for step in range(4000):
        action = rng.random()
        size = rng.choice((1, 1, 2, 4, 7))
        if action < 0.5:
            side = Side.BID if rng.random() < 0.5 else Side.ASK
            ids.append(ob.submit_limit_order(side, 1000 + rng.randint(-30, 30), step, quantity=size))
        elif action < 0.7:
            ob.submit_market_order(Side.BID if rng.random() < 0.5 else Side.ASK, step, quantity=size)
        elif ids:
            ob.cancel_order(ids.pop(rng.randrange(len(ids))))
        _check_book_consistency(ob)
    check("order counts, volumes and best prices agree with brute force after 4000 random sized operations", True)
    check("units traded = the quantities of all trades added up", ob.volume_traded == sum(tr.quantity for tr in ob.trades))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")

