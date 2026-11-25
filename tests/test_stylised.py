"""
Tests for the trade-time statistics (analysis/stylised.py), on series whose answers are known.
Run with: python -m tests.test_stylised   (from the project root)
"""

import numpy as np

from analysis.stylised import (LAGS, KURTOSIS_LAGS, SIGN_LAGS, as_orders, changes, order_signs, power_law_exponent, sign_autocorrelation,
                               mid_move_stats, response_function, stylised_facts, trade_signs)


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    assert condition, f"FAILED: {label}"


def segment(prices, spread=1.0, size=10.0):
    n = len(prices)
    return {"trade": np.asarray(prices, dtype=float), "mid": np.asarray(prices, dtype=float),
            "spread": np.full(n, spread), "bid_size": np.full(n, size), "ask_size": np.full(n, size),
            "size": np.ones(n)}


def test_random_walk_gives_the_textbook_values():
    rng = np.random.default_rng(1)
    walks = [segment(np.cumsum(rng.standard_normal(200_000))) for _ in range(3)]
    facts = stylised_facts(walks)
    t = facts["trade"]
    middle = (LAGS >= 10) & (LAGS <= 2000)
    check(f"H close to 0.5 at lags 10-2000 (mean {np.nanmean(t['hurst'][middle]):.3f})",
          np.all(np.abs(t["hurst"][middle] - 0.5) < 0.05))
    check("kurtosis close to 3 at short lags", all(abs(t["kurtosis"][lag] - 3) < 0.1 for lag in (1, 10, 100)))
    check("no autocorrelation of the changes", np.all(np.abs(t["autocorr"][1]["signed"]) < 0.02))
    check("no volatility clustering", np.all(np.abs(t["autocorr"][100]["absolute"]) < 0.05))
    check("a share of about 4.6% beyond 2 standard deviations, as for a normal distribution",
          abs(np.interp(2.0, facts["tail_levels"], t["tail"][10]) - 0.0455) < 0.005)
    check("spread and sizes summarised", facts["spread"]["shares"][1] == 1.0 and facts["best_size"]["quantiles"][50] == 10)
    check("trade size relative to the best size", abs(facts["trade_size"]["per_best_size"] - 0.1) < 1e-12)


def test_bounce_between_two_prices_is_anticorrelated():
    rng = np.random.default_rng(2)
    bounce = 100 + rng.integers(0, 2, 100_000)       # trades at the bid or the ask at random
    t = stylised_facts([segment(bounce)])["trade"]
    check(f"lag-1 autocorrelation of trade-to-trade changes about -0.5 ({t['autocorr'][1]['signed'][0]:+.2f})",
          abs(t["autocorr"][1]["signed"][0] + 0.5) < 0.02)
    check("about half the trades leave the price unchanged", abs(t["zero_steps"] - 0.5) < 0.01)


def test_changes_never_cross_from_one_segment_to_the_next():
    a, b = segment([0, 1, 2]), segment([100, 101, 102])
    check("lag-1 changes stay inside each segment", list(changes([a, b], "trade", 1)) == [1, 1, 1, 1])
    check("segments too short for a lag are skipped", len(changes([a, b], "trade", 5)) == 0)
    short = stylised_facts([a, b])
    check("short segments give NaN, not an error", np.isnan(short["trade"]["kurtosis"][KURTOSIS_LAGS[-1]]))


def signed_segment(signs, mid=100.0):
    """Trades at the ask (mid + 0.5) for +1, the bid for -1, the mid itself for 0."""
    signs = np.asarray(signs, dtype=float)
    n = len(signs)
    return {"trade": mid + 0.5 * signs, "mid": np.full(n, mid), "spread": np.ones(n),
            "bid_size": np.ones(n), "ask_size": np.ones(n)}


def test_trade_signs():
    check("buy above the mid, sell below, 0 at the mid", list(trade_signs(signed_segment([1, -1, 0]))) == [1, -1, 0])
    rng = np.random.default_rng(3)
    coin = signed_segment(rng.choice([-1, 1], 300_000))
    ac = sign_autocorrelation([coin])
    check(f"independent signs: no autocorrelation (largest {np.max(np.abs(ac[1:])):.3f})", np.all(np.abs(ac[1:]) < 0.01))
    check("lag 0 would be 1 by construction; the first lag listed is 1", SIGN_LAGS[0] == 1)
    # Markov signs: keep the last sign with probability p, so the autocorrelation is (2p - 1)^lag.
    p, n = 0.8, 300_000
    flips = rng.random(n) > p
    s = np.where(np.cumsum(flips) % 2 == 0, 1, -1)
    ac = sign_autocorrelation([signed_segment(s)])
    lags = list(SIGN_LAGS)
    for lag in (1, 3, 10):
        check(f"persistent signs: autocorrelation at lag {lag} close to 0.6^{lag} = {0.6 ** lag:.3f} ({ac[lags.index(lag)]:.3f})",
              abs(ac[lags.index(lag)] - 0.6 ** lag) < 0.01)
    # Each segment is a long run of one sign, the opposite of the next: pooled as one series the signs
    # would be strongly correlated, but within each segment there is no variation at all.
    blocks = [signed_segment(np.where(rng.random(20_000) < 0.5, 1, -1) * 0 + sign) for sign in (1, -1, 1)]
    check("pairs never cross from one segment to the next (no variation inside any segment: no answer)",
          np.isnan(sign_autocorrelation(blocks)).all())
    check("segments shorter than the longest lag are left out",
          np.isnan(sign_autocorrelation([signed_segment(rng.choice([-1, 1], 5_000))])).all())
    exact = 0.5 * SIGN_LAGS.astype(float) ** -0.6
    check(f"the power-law exponent of lag^-0.6 is 0.6 ({power_law_exponent(SIGN_LAGS, exact):.3f})",
          abs(power_law_exponent(SIGN_LAGS, exact) - 0.6) < 1e-9)
    facts = stylised_facts([coin])
    check("stylised_facts keeps the sign statistics", "signs" in facts and abs(facts["signs"]["share_buy"] - 0.5) < 0.01)
    check("without timestamps (the model) there is no merged version", "orders" not in facts["signs"])


def test_fills_of_one_order_are_merged():
    seg = signed_segment([1, 1, 1, -1, -1, 1])
    seg["time"] = np.array([0, 0, 1, 1, 2, 2])
    # time 0: two buys (one order); time 1: a buy and a sell (two orders); time 2: a sell and a buy.
    check("same time and same side counted once", list(order_signs(seg)) == [1, 1, -1, -1, 1])
    check("a segment without timestamps is unchanged", list(order_signs(signed_segment([1, 1, -1]))) == [1, 1, -1])
    rng = np.random.default_rng(4)
    orders = rng.choice([-1, 1], 100_000)
    fills = np.repeat(orders, 3)                       # every order fills three resting orders
    seg = signed_segment(fills)
    seg["time"] = np.repeat(np.arange(len(orders)), 3)
    ac_fills, ac_orders = sign_autocorrelation([seg]), sign_autocorrelation([seg], signs=order_signs)
    check(f"three fills per order look persistent fill by fill ({ac_fills[0]:.2f} at lag 1)", ac_fills[0] > 0.6)
    check(f"but the orders themselves are independent ({ac_orders[0]:+.3f})", abs(ac_orders[0]) < 0.01)
    facts = stylised_facts([seg])
    check("stylised_facts reports fills per order", abs(facts["signs"]["orders"]["fills_per_order"] - 3) < 1e-9)


def test_response_function():
    rng = np.random.default_rng(5)
    signs = rng.choice([-1, 1], 200_000)
    lags = list(SIGN_LAGS)
    # Permanent impact: each trade moves the mid-price one tick its way, for good.
    mid = np.concatenate([[0.0], np.cumsum(signs)[:-1]])
    seg = {"trade": mid + 0.5 * signs, "mid": mid}
    r = response_function([seg])[SIGN_LAGS <= 100]      # longer lags add up more unrelated signs: noisier
    check(f"permanent impact: R = 1 at lags 1-100 (from {np.nanmin(r):.3f} to {np.nanmax(r):.3f})",
          np.all(np.abs(r - 1) < 0.05))
    # Impact that lasts one trade: the mid-price is the last trade's sign, so R(1) = 1, then 0.
    mid = np.concatenate([[0.0], signs[:-1]]).astype(float)
    r = response_function([{"trade": mid + 0.5 * signs + 10 * np.sign(signs), "mid": mid}])
    check(f"impact lasting one trade: R(1) = 1 ({r[0]:.3f})", abs(r[0] - 1) < 0.01)
    check(f"and about 0 after ({np.max(np.abs(r[1:])):.3f})", np.all(np.abs(r[1:]) < 0.02))
    seg = signed_segment([1, 1, -1])
    seg["time"] = np.array([0, 0, 1])
    check("per order, the fills of one order count once", list(as_orders(seg)["trade"]) == [100.5, 99.5])
    facts = stylised_facts([signed_segment(signs)])
    check("stylised_facts keeps the response per trade, and per order only with timestamps",
          "per_trade" in facts["response"] and "per_order" not in facts["response"])


def test_mid_move_stats():
    zigzag = {"mid": np.array([0, 0, 0.5, 0.5] * 2000, dtype=float)}
    z = mid_move_stats([zigzag])
    check("a flickering mid-price: every change half a tick and undone by the next",
          z["half_tick"] == 1 and z["undone"] == 1 and z["reversed"] == 1)
    check("changes after every second trade", abs(z["share_of_trades"] - 0.5) < 0.01 and z["gap_median"] == 2)
    rng = np.random.default_rng(6)
    walk = {"mid": np.cumsum(rng.choice([-1.0, 1.0], 100_000))}
    w = mid_move_stats([walk])
    check(f"a random walk: about half the changes go the other way next ({w['reversed']:.3f})", abs(w["reversed"] - 0.5) < 0.01)
    check("whole-tick steps are not half-tick", w["half_tick"] == 0)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
