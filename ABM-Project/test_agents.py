"""
Tests for LiquidityProvider / LiquidityTaker. Run with: python test_agents.py

Covers the rules from the paper's model definition: providers place limit
orders only, at exponentially distributed depth around the midpoint (or a
fallback price while the book has none); takers place market orders only, and
side probabilities q_provider / q_taker decide bid vs ask / buy vs sell.
"""

import random

from orderbook import OrderBook, Side, OrderResult
from agents import LiquidityProvider, LiquidityTaker


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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
