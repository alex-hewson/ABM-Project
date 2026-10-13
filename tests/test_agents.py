"""
Tests for LiquidityProvider / LiquidityTaker. Run with: python -m tests.test_agents   (from the project root)

Covers the rules from the paper's model definition: providers place limit
orders only, at exponentially distributed depth around the midpoint (or a
fallback price while the book has none); takers place market orders only, and
side probabilities q_provider / q_taker decide bid vs ask / buy vs sell.
"""

import random

from abm.orderbook import OrderBook, Side, OrderResult
from abm.agents import (LiquidityProvider, LiquidityTaker, AgentType, is_turn, ValueTrader,
                        draw_value_shift, market_price)


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    assert condition, f"FAILED: {label}"


P0 = 1_000_000


def test_provider_alpha_zero_never_submits():
    book = OrderBook()
    p = LiquidityProvider(agent_id=0, alpha=0.0, q_provider=0.5, lambda_=100)
    rng = random.Random(0)
    ids = [p.maybe_submit(book, t, P0, rng) for t in range(1000)]
    check("alpha=0: never submits", all(i is None for i in ids))
    check("alpha=0: book stays empty", book.total_orders() == 0)


def test_provider_alpha_one_always_submits():
    book = OrderBook()
    p = LiquidityProvider(agent_id=0, alpha=1.0, q_provider=0.5, lambda_=100)
    rng = random.Random(0)
    ids = [p.maybe_submit(book, t, P0, rng) for t in range(200)]
    check("alpha=1: every step returns an order id", all(i is not None for i in ids))


def test_provider_submission_rate_matches_alpha():
    book = OrderBook()
    p = LiquidityProvider(agent_id=0, alpha=0.3, q_provider=0.5, lambda_=100)
    rng = random.Random(1)
    n = 20_000
    hits = sum(p.maybe_submit(book, t, P0, rng) is not None for t in range(n))
    check(f"alpha=0.3: submission rate {hits / n:.3f} within 0.02 of 0.3",
          abs(hits / n - 0.3) < 0.02)


def test_provider_bid_only_prices_at_or_below_reference():
    book = OrderBook()
    p = LiquidityProvider(agent_id=0, alpha=1.0, q_provider=1.0, lambda_=100)
    rng = random.Random(2)
    for t in range(500):
        p.maybe_submit(book, t, P0, rng)
    check("q_provider=1: only bids in the book", len(book.asks) == 0 and len(book.bids) > 0)
    check("q_provider=1: no bid above the fallback price", max(book.bids) <= P0)


def test_provider_ask_only_prices_at_or_above_reference():
    book = OrderBook()
    p = LiquidityProvider(agent_id=0, alpha=1.0, q_provider=0.0, lambda_=100)
    rng = random.Random(3)
    for t in range(500):
        p.maybe_submit(book, t, P0, rng)
    check("q_provider=0: only asks in the book", len(book.bids) == 0 and len(book.asks) > 0)
    check("q_provider=0: no ask below the fallback price", min(book.asks) >= P0)


def test_provider_side_probability():
    book = OrderBook()
    p = LiquidityProvider(agent_id=0, alpha=1.0, q_provider=0.7, lambda_=100)
    rng = random.Random(4)
    n = 5_000
    # Each order is far from crossing, so counting resting orders per side is safe
    # as long as we use a fresh book per submission.
    n_bid = 0
    for t in range(n):
        b = OrderBook()
        p.maybe_submit(b, t, P0, rng)
        n_bid += len(b.bids)
    check(f"q_provider=0.7: bid fraction {n_bid / n:.3f} within 0.03 of 0.7",
          abs(n_bid / n - 0.7) < 0.03)


def test_provider_mean_depth_matches_lambda():
    # Fresh book each time -> no midpoint -> depth is always measured from the fallback.
    p = LiquidityProvider(agent_id=0, alpha=1.0, q_provider=1.0, lambda_=100)
    rng = random.Random(5)
    n = 20_000
    total = 0
    for t in range(n):
        b = OrderBook()
        p.maybe_submit(b, t, P0, rng)
        total += P0 - next(iter(b.bids))
    mean_depth = total / n
    # standard error of the mean is ~ 100/sqrt(20000) = 0.7
    check(f"mean entry depth {mean_depth:.1f} within 3 ticks of lambda=100",
          abs(mean_depth - 100) < 3)


def test_provider_uses_midpoint_when_available():
    book = OrderBook()
    book.submit_limit_order(Side.BID, 400, 0)
    book.submit_limit_order(Side.ASK, 600, 0)   # midpoint = 500, far from P0
    p = LiquidityProvider(agent_id=0, alpha=1.0, q_provider=1.0, lambda_=10)
    rng = random.Random(6)
    for t in range(1, 100):
        p.maybe_submit(book, t, P0, rng)
    # A bid placed off the fallback (1,000,000) would cross the ask at 600 and trade.
    check("orders were placed around the midpoint, not the fallback: no trades", len(book.trades) == 0)
    check("new bids rested in the book", len(book.bids) > 10 and max(book.bids) < 600)


def test_provider_reproducible_with_seed():
    def run(seed):
        book = OrderBook()
        p = LiquidityProvider(agent_id=0, alpha=0.5, q_provider=0.5, lambda_=100)
        rng = random.Random(seed)
        for t in range(300):
            p.maybe_submit(book, t, P0, rng)
        return sorted(book.depth_profile(Side.BID).items()), sorted(book.depth_profile(Side.ASK).items())

    check("same seed -> identical books", run(7) == run(7))
    check("different seed -> different books", run(7) != run(8))


def test_taker_mu_zero_never_submits():
    book = OrderBook()
    book.submit_limit_order(Side.BID, 100, 0)
    book.submit_limit_order(Side.ASK, 101, 0)
    t = LiquidityTaker(agent_id=1, mu=0.0, q_taker=0.5)
    rng = random.Random(0)
    results = [t.maybe_submit(book, s, rng) for s in range(500)]
    check("mu=0: never submits", all(r is None for r in results))
    check("mu=0: no trades", len(book.trades) == 0)


def test_taker_buy_hits_best_ask_and_sell_hits_best_bid():
    book = OrderBook()
    book.submit_limit_order(Side.BID, 100, 0, agent_id="bidder")
    book.submit_limit_order(Side.ASK, 105, 0, agent_id="asker")
    buyer = LiquidityTaker(agent_id=1, mu=1.0, q_taker=1.0)
    result = buyer.maybe_submit(book, 1, random.Random(0))
    check("buy taker: executes", result is OrderResult.EXECUTED)
    check("buy taker: trades at the best ask", book.trades[-1].price == 105)
    check("buy taker: aggressor side is BID", book.trades[-1].aggressor_side is Side.BID)

    seller = LiquidityTaker(agent_id=2, mu=1.0, q_taker=0.0)
    result = seller.maybe_submit(book, 2, random.Random(0))
    check("sell taker: executes", result is OrderResult.EXECUTED)
    check("sell taker: trades at the best bid", book.trades[-1].price == 100)
    check("sell taker: aggressor side is ASK", book.trades[-1].aggressor_side is Side.ASK)


def test_taker_on_empty_book_reports_no_match():
    book = OrderBook()
    t = LiquidityTaker(agent_id=1, mu=1.0, q_taker=0.5)
    result = t.maybe_submit(book, 0, random.Random(0))
    check("empty book: NO_MATCH returned, not an exception", result is OrderResult.NO_MATCH)
    check("empty book: no trades", len(book.trades) == 0)


def test_taker_rate_and_side_probability():
    n = 10_000
    rng = random.Random(9)
    taker = LiquidityTaker(agent_id=1, mu=0.2, q_taker=0.3)
    submitted = buys = 0
    for s in range(n):
        book = OrderBook()
        book.submit_limit_order(Side.BID, 100, 0)
        book.submit_limit_order(Side.ASK, 101, 0)
        result = taker.maybe_submit(book, s, rng)
        if result is not None:
            submitted += 1
            buys += book.trades[-1].aggressor_side is Side.BID
    check(f"mu=0.2: submission rate {submitted / n:.3f} within 0.02 of 0.2",
          abs(submitted / n - 0.2) < 0.02)
    check(f"q_taker=0.3: buy fraction {buys / submitted:.3f} within 0.04 of 0.3",
          abs(buys / submitted - 0.3) < 0.04)


def test_provider_uses_an_overriding_depth_when_given():
    """The Eq. 4 entry depth reaches providers as a per-order override of their own lambda_."""
    p = LiquidityProvider(agent_id=0, alpha=1.0, q_provider=1.0, lambda_=100)
    rng = random.Random(10)
    n = 20_000
    total = 0
    for t in range(n):
        b = OrderBook()
        p.submit(b, t, P0, rng, lambda_=1000)
        total += P0 - next(iter(b.bids))
    mean_depth = total / n
    # standard error of the mean is ~ 1000/sqrt(20000) = 7
    check(f"override lambda_=1000: mean entry depth {mean_depth:.0f} within 30 of 1000", abs(mean_depth - 1000) < 30)
    check("the agent's own lambda_ is unchanged", p.lambda_ == 100)


def test_taker_uses_an_overriding_q_when_given():
    def one_market_order(agent_q, override):
        book = OrderBook()
        book.submit_limit_order(Side.BID, 100, 0)
        book.submit_limit_order(Side.ASK, 105, 0)
        LiquidityTaker(agent_id=1, mu=1.0, q_taker=agent_q).submit(book, 1, random.Random(0), q_taker=override)
        return book.trades[-1].aggressor_side

    check("agent q=0 but override q=1: buys", one_market_order(0.0, 1.0) is Side.BID)
    check("agent q=1 but override q=0: sells", one_market_order(1.0, 0.0) is Side.ASK)
    check("no override: the agent's own q is used", one_market_order(1.0, None) is Side.BID)

def raises_value_error(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except ValueError:
        return True
    return False


def test_agent_type_defaults_to_the_papers_agent_and_is_validated():
    check("default: a chance every step, one unit per order", AgentType() == AgentType(interval=1, size=1))
    check("interval 0 rejected", raises_value_error(AgentType, interval=0))
    check("size 0 rejected", raises_value_error(AgentType, size=0))


def test_is_turn_hand_worked():
    check("interval 1: every step", all(is_turn(t, 1, 0) for t in range(10)))
    check("interval 4, offset 0: steps 0, 4, 8", [t for t in range(10) if is_turn(t, 4, 0)] == [0, 4, 8])
    check("interval 4, offset 1: steps 3, 7", [t for t in range(10) if is_turn(t, 4, 1)] == [3, 7])
    check("interval 2, offset 1: the odd steps", [t for t in range(6) if is_turn(t, 2, 1)] == [1, 3, 5])


def test_slow_provider_only_acts_on_its_own_steps_with_its_own_size():
    book = OrderBook()
    p = LiquidityProvider(agent_id=0, alpha=1.0, q_provider=1.0, lambda_=100, interval=4, size=4, offset=1)
    rng = random.Random(0)
    submitted_at = [t for t in range(16) if p.maybe_submit(book, t, P0, rng) is not None]
    check("alpha=1, interval 4, offset 1: submits on steps 3, 7, 11, 15 only", submitted_at == [3, 7, 11, 15])
    check("four orders rest", book.total_orders() == 4)
    check("each of 4 units: 16 units in total", book.total_volume() == 16
          and all(o.quantity == 4 for queue in book.bids.values() for o in queue))


def test_a_step_that_is_not_the_agents_turn_uses_no_random_numbers():
    book = OrderBook()
    book.submit_limit_order(Side.BID, 100, 0)
    book.submit_limit_order(Side.ASK, 105, 0)
    rng = random.Random(1)
    before = rng.getstate()
    p = LiquidityProvider(agent_id=0, alpha=1.0, q_provider=0.5, lambda_=100, interval=4, size=4)
    t = LiquidityTaker(agent_id=1, mu=1.0, q_taker=0.5, interval=4, size=4)
    results = [p.maybe_submit(book, 1, P0, rng), t.maybe_submit(book, 2, rng), t.maybe_submit(book, 3, rng)]
    check("nothing is submitted off-turn", results == [None, None, None] and book.total_orders() == 2)
    check("and the random stream is untouched", rng.getstate() == before)


def test_sized_taker_takes_its_size_from_the_book():
    book = OrderBook()
    book.submit_limit_order(Side.ASK, 101, 0, quantity=2)
    book.submit_limit_order(Side.ASK, 102, 0, quantity=5)
    taker = LiquidityTaker(agent_id=1, mu=1.0, q_taker=1.0, interval=4, size=4)
    result = taker.maybe_submit(book, 4, random.Random(0))
    check("its turn (step 4): the order is filled", result is OrderResult.EXECUTED)
    check("4 units taken: 2 at 101, then 2 at 102", [(tr.price, tr.quantity) for tr in book.trades] == [(101, 2), (102, 2)])
    check("3 units are left at 102", book.depth_profile(Side.ASK) == {102: 3})


def test_sized_taker_reports_a_partial_fill():
    book = OrderBook()
    book.submit_limit_order(Side.ASK, 101, 0, quantity=3)
    taker = LiquidityTaker(agent_id=1, mu=1.0, q_taker=1.0, size=4)
    check("only 3 of its 4 units could trade: PARTIAL", taker.submit(book, 0, random.Random(0)) is OrderResult.PARTIAL)

def book_with_spread(bid=99, ask=101):
    """One bid and one ask, so the midpoint is half way between them (100 by default)."""
    book = OrderBook()
    book.submit_limit_order(Side.BID, bid, 0, agent_id="bidder")
    book.submit_limit_order(Side.ASK, ask, 0, agent_id="asker")
    return book


def test_value_shift_is_plus_or_minus_an_exponential():
    rng = random.Random(0)
    shifts = [draw_value_shift(rng, 50.0) for _ in range(20_000)]
    mean = sum(shifts) / len(shifts)
    mean_size = sum(abs(x) for x in shifts) / len(shifts)
    share_positive = sum(x > 0 for x in shifts) / len(shifts)
    # standard error of the mean is ~ 50*sqrt(2)/sqrt(20000) = 0.5
    check(f"mean shift {mean:.2f} within 2 ticks of 0", abs(mean) < 2)
    check(f"mean size {mean_size:.1f} within 2 ticks of the spread 50", abs(mean_size - 50) < 2)
    check(f"share above zero {share_positive:.3f} within 0.02 of 1/2", abs(share_positive - 0.5) < 0.02)
    check("spread 0: every shift is exactly 0", draw_value_shift(random.Random(1), 0) == 0.0)


def test_market_price_is_the_midpoint_or_the_best_price_there_is():
    check("both sides: the midpoint", market_price(book_with_spread(99, 102), reference=500.0) == 100.5)
    asks_only = OrderBook()
    asks_only.submit_limit_order(Side.ASK, 101, 0)
    check("asks only: the best ask", market_price(asks_only, reference=500.0) == 101.0)
    bids_only = OrderBook()
    bids_only.submit_limit_order(Side.BID, 99, 0)
    check("bids only: the best bid", market_price(bids_only, reference=500.0) == 99.0)
    check("empty book: the reference", market_price(OrderBook(), reference=500.0) == 500.0)


def test_value_trader_buys_when_the_price_is_below_its_value():
    book = book_with_spread()                                   # midpoint 100
    trader = ValueTrader(agent_id=7, mu=1.0, shift=3.7)         # value = 100 + 3.7 = 103.7
    order_id = trader.submit(book, 1, reference=100.0)
    check("an order was placed", order_id is not None)
    check("it bought at the best ask, 101 (below its limit of 103)",
          len(book.trades) == 1 and book.trades[0].price == 101 and book.trades[0].aggressor_side is Side.BID)
    check("the trade is the trader's", book.trades[0].aggressor_agent_id == 7)


def test_value_trader_sells_when_the_price_is_above_its_value():
    book = book_with_spread()
    trader = ValueTrader(agent_id=7, mu=1.0, shift=-3.2)        # value = 96.8
    trader.submit(book, 1, reference=100.0)
    check("it sold at the best bid, 99 (above its limit of 97)",
          len(book.trades) == 1 and book.trades[0].price == 99 and book.trades[0].aggressor_side is Side.ASK)


def test_value_trader_never_trades_at_a_price_worse_than_its_value():
    book = OrderBook()
    book.submit_limit_order(Side.BID, 99, 0)
    book.submit_limit_order(Side.ASK, 101, 0)
    book.submit_limit_order(Side.ASK, 104, 0)
    trader = ValueTrader(agent_id=7, mu=1.0, shift=3.7, size=2)     # value 103.7: will pay up to 103
    trader.submit(book, 1, reference=100.0)
    check("it buys the unit at 101 but not the one at 104",
          [(tr.price, tr.quantity) for tr in book.trades] == [(101, 1)] and book.best_ask() == 104)
    check("the unit it could not buy rests as a bid at 103 (its value, rounded down)",
          book.best_bid() == 103 and book.depth_profile(Side.BID)[103] == 1)

    book = book_with_spread()
    ValueTrader(agent_id=7, mu=1.0, shift=-3.2).submit(book, 1, reference=200.0)    # value 196.8, price 100
    check("a buyer's limit is rounded down and a seller's up: value 196.8 with the price at 100 buys",
          book.trades[0].aggressor_side is Side.BID)
    book = book_with_spread()
    ValueTrader(agent_id=7, mu=1.0, shift=0.4, size=2).submit(book, 1, reference=95.0)   # value 95.4 < 100: sell
    check("selling 2 with value 95.4: sells 1 at 99, rests the other at 96 (rounded up), not below its value",
          [(tr.price, tr.quantity) for tr in book.trades] == [(99, 1)] and book.best_ask() == 96)


def test_value_trader_rests_inside_the_spread_when_its_value_does_not_cross():
    book = book_with_spread(bid=95, ask=105)                    # midpoint 100
    ValueTrader(agent_id=7, mu=1.0, shift=2.5).submit(book, 1, reference=100.0)     # value 102.5: buy, limit 102
    check("no trade: 102 is below the best ask", len(book.trades) == 0)
    check("its order rests at 102 and is the new best bid", book.best_bid() == 102 and book.total_orders() == 3)


def test_value_trader_does_nothing_when_the_price_is_at_its_value():
    book = book_with_spread()
    check("value = price: no order", ValueTrader(agent_id=7, mu=1.0, shift=0.0).submit(book, 1, reference=100.0) is None)
    check("the book is unchanged", book.total_orders() == 2 and len(book.trades) == 0)


def test_value_trader_supplies_the_missing_side_of_a_one_sided_book():
    book = OrderBook()
    book.submit_limit_order(Side.ASK, 101, 0)                   # the bid side is empty: price = 101
    ValueTrader(agent_id=7, mu=1.0, shift=-20.0).submit(book, 1, reference=140.0)   # value 120 > 101
    check("it buys from the asks that are there", len(book.trades) == 1 and book.trades[0].price == 101)
    empty = OrderBook()
    ValueTrader(agent_id=7, mu=1.0, shift=5.0).submit(empty, 1, reference=100.0)    # price = reference = 100
    check("into an empty book, a trader above the reference posts a bid at its value", empty.best_bid() == 105)


def test_value_trader_acts_at_its_rate_and_only_on_its_turn():
    book = book_with_spread()
    rng = random.Random(2)
    never = ValueTrader(agent_id=7, mu=0.0, shift=5.0)
    check("mu = 0: never submits", all(never.maybe_submit(book, t, 100.0, rng) is None for t in range(200)))
    slow = ValueTrader(agent_id=8, mu=1.0, shift=0.4, interval=4, offset=1)     # value 100.4: bids at 100, never trades
    acted = [t for t in range(12) if slow.maybe_submit(book, t, 100.0, rng) is not None]
    check("interval 4, offset 1, mu = 1: acts on steps 3, 7, 11 only", acted == [3, 7, 11])
    n = 10_000
    sometimes = ValueTrader(agent_id=9, mu=0.3, shift=0.4)
    hits = sum(sometimes.maybe_submit(book_with_spread(), t, 100.0, rng) is not None for t in range(n))
    check(f"mu = 0.3: submission rate {hits / n:.3f} within 0.02 of 0.3", abs(hits / n - 0.3) < 0.02)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
