"""
Tests for LiquidityProvider / LiquidityTaker. Run with: python -m tests.test_agents   (from the project root)

Covers the rules from the paper's model definition: providers place limit
orders only, at exponentially distributed depth around the midpoint (or a
fallback price while the book has none); takers place market orders only, and
side probabilities q_provider / q_taker decide bid vs ask / buy vs sell.
"""

import random

from abm.orderbook import OrderBook, Side, OrderResult
from abm.agents import (LiquidityProvider, LiquidityTaker, ConstantSide, BoundedRandomWalk,
                        MeanRevertingWalk)


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


class ScriptedRandom:
    """Stand-in for random.Random whose random() returns pre-set values in order, so a walk's
    direction and reflection can be worked out by hand."""

    def __init__(self, *values):
        self.values = list(values)

    def random(self):
        return self.values.pop(0)


def raises_value_error(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except ValueError:
        return True
    return False


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


def test_constant_side_never_changes_and_uses_no_random_numbers():
    flow, rng = ConstantSide(0.7), random.Random(3)
    state_before = rng.getstate()
    for _ in range(100):
        flow.advance(rng)
    check("q stays 0.7", flow.q == 0.7)
    check("advance consumed no random numbers (so a constant flow can't change a seeded run)",
          rng.getstate() == state_before)


def test_walk_parameters_are_validated():
    check("step must be positive", raises_value_error(BoundedRandomWalk, step=0.0))
    check("half_width must be a whole number of steps",
          raises_value_error(BoundedRandomWalk, step=0.001, half_width=0.0505))
    check("half_width must be at least one step", raises_value_error(BoundedRandomWalk, step=0.1, half_width=0.0))
    check("q must stay a valid probability", raises_value_error(BoundedRandomWalk, step=0.1, half_width=0.6))
    check("the paper's Fig. 3a and 3c settings are accepted",
          BoundedRandomWalk().K == 50 and MeanRevertingWalk().K == 500)


def test_bounded_walk_starts_at_the_centre_and_moves_one_step_at_a_time():
    flow, rng = BoundedRandomWalk(), random.Random(1)
    check("starts at exactly 1/2", flow.q == 0.5)
    previous, steps_ok = flow.q, True
    for _ in range(2000):
        flow.advance(rng)
        steps_ok = steps_ok and abs(abs(flow.q - previous) - 0.001) < 1e-12
        previous = flow.q
    check("every step changes q by exactly +/-0.001 (including reflected ones)", steps_ok)


def test_bounded_walk_reflects_by_mirroring_back_inside():
    flow = BoundedRandomWalk(step=0.1, half_width=0.2)      # k lives in -2..2
    flow.k = 2
    flow.advance(ScriptedRandom(0.1))                         # 0.1 < 0.5: try +1 -> 3 -> mirrored to 1
    check("upper bound: a step outward ends one step inside (k=2 -> 1)", flow.k == 1)
    flow.k = -2
    flow.advance(ScriptedRandom(0.9))                         # 0.9 >= 0.5: try -1 -> -3 -> mirrored to -1
    check("lower bound: a step outward ends one step inside (k=-2 -> -1)", flow.k == -1)
    flow.k = 0
    flow.advance(ScriptedRandom(0.1))
    check("in the interior a step is just a step (k=0 -> 1)", flow.k == 1)


def test_bounded_walk_stays_within_bounds_and_reaches_both_over_a_long_run():
    flow, rng = BoundedRandomWalk(), random.Random(2)
    qs = []
    for _ in range(30_000):
        flow.advance(rng)
        qs.append(flow.q)
    check(f"q stays within [0.45, 0.55] (min {min(qs):.3f}, max {max(qs):.3f})",
          min(qs) >= 0.45 - 1e-9 and max(qs) <= 0.55 + 1e-9)
    check("and actually reaches both bounds", min(qs) < 0.45 + 1e-9 and max(qs) > 0.55 - 1e-9)


def test_mean_reverting_walk_direction_probabilities_by_hand():
    flow = MeanRevertingWalk()                                # step 0.001
    flow.k = 10                                               # q = 0.51: p(toward centre) = 0.5 + 0.01 = 0.51
    flow.advance(ScriptedRandom(0.50))
    check("above centre, draw 0.50 < 0.51: moves toward the centre (k 10 -> 9)", flow.k == 9)
    flow.k = 10
    flow.advance(ScriptedRandom(0.52))
    check("above centre, draw 0.52 >= 0.51: moves away (k 10 -> 11)", flow.k == 11)
    flow.k = -10
    flow.advance(ScriptedRandom(0.50))
    check("below centre, draw 0.50 < 0.51: moves toward the centre (k -10 -> -9)", flow.k == -9)
    flow.k = 0
    flow.advance(ScriptedRandom(0.3))
    check("exactly at the centre there is no 'toward': a fair coin decides (0.3 -> up)", flow.k == 1)
    flow.k = 0
    flow.advance(ScriptedRandom(0.7))
    check("... (0.7 -> down)", flow.k == -1)


def test_mean_reverting_walk_settles_to_the_theoretical_spread():
    # A pull of 2*step*(q-centre) per step on steps of size step is an Ornstein-Uhlenbeck process, whose
    # stationary standard deviation is sqrt(step/4) = 0.0158 for step 0.001 (relaxation time ~500 steps).
    flow, rng = MeanRevertingWalk(), random.Random(4)
    qs = []
    for _ in range(200_000):
        flow.advance(rng)
        qs.append(flow.q)
    mean = sum(qs) / len(qs)
    std = (sum((q - mean) ** 2 for q in qs) / len(qs)) ** 0.5
    expected = (0.001 / 4) ** 0.5
    check(f"std of q {std:.4f} within 15% of sqrt(step/4) = {expected:.4f}", abs(std - expected) < 0.15 * expected)
    check(f"mean of q {mean:.4f} within 0.01 of 1/2", abs(mean - 0.5) < 0.01)
    check("q stays a valid probability", min(qs) >= 0 and max(qs) <= 1)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
