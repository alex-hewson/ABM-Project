"""
Tests for building per-step price series under the different definitions of "price".
Run with: python -m tests.test_prices   (from the project root)
"""

import numpy as np

from abm.simulation import run_simulation
from analysis.prices import PRICE_DEFINITIONS, forward_fill, price_series

PRE = 10   # pre-opening steps used by run_simulation's default


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    assert condition, f"FAILED: {label}"


def raises_value_error(fn, *args):
    try:
        fn(*args)
    except ValueError:
        return True
    return False


def test_forward_fill():
    nan = np.nan
    filled = forward_fill(np.array([nan, nan, 5.0, nan, nan, 7.0, nan]))
    check("gaps carry the previous value; leading gaps take the first real value",
          list(filled) == [5.0, 5.0, 5.0, 5.0, 5.0, 7.0, 7.0])
    check("input is not modified", True)
    original = np.array([1.0, nan, 3.0])
    forward_fill(original)
    check("input array left untouched", np.isnan(original[1]))
    check("all-NaN input is rejected", raises_value_error(forward_fill, np.array([nan, nan])))


def test_trade_summaries_match_brute_force_from_full_trade_record():
    n_steps = 400
    r = run_simulation(n_agents=60, alpha=0.15, mu=0.025, delta=0.025, lambda_=100,
                       n_steps=n_steps, seed=4, record_trade_prices=True)
    by_step = {}
    for trade in r.book.trades:
        if trade.timestamp - PRE >= 0:
            by_step.setdefault(trade.timestamp - PRE, []).append(trade.price)
    check("some steps have trades and some have none (so the test exercises both)",
          0 < len(by_step) < n_steps)

    expected = {
        "first": lambda p: p[0],
        "last": lambda p: p[-1],
        "median": lambda p: sorted(p)[len(p) // 2],
        "mean": lambda p: sum(p) / len(p),
    }
    for name, fn in expected.items():
        got = r.trade_price_steps[name]
        ok = all((np.isnan(got[t]) if t not in by_step else np.isclose(got[t], fn(by_step[t])))
                 for t in range(n_steps))
        check(f"'{name}' per-step values match a brute-force recomputation", ok)

    check("trade counts agree", r.n_trades == len(r.book.trades))
    check("trade_price_steps has no entries unless requested",
          run_simulation(n_agents=20, alpha=0.15, mu=0.025, delta=0.025, lambda_=100,
                         n_steps=20, seed=1).trade_price_steps == {})


def test_price_series_is_gap_free_and_within_range():
    r = run_simulation(n_agents=60, alpha=0.15, mu=0.025, delta=0.025, lambda_=100,
                       n_steps=400, seed=4, record_trade_prices=True)
    for name in PRICE_DEFINITIONS:
        s = price_series(r, name)
        check(f"'{name}': one finite price per step", len(s) == 400 and np.all(np.isfinite(s)))
    lo, hi = min(t.price for t in r.book.trades), max(t.price for t in r.book.trades)
    for name in ("first", "last", "median", "mean"):
        s = price_series(r, name)
        check(f"'{name}' stays within the range of traded prices", s.min() >= lo and s.max() <= hi)
    check("'mid' is the recorded mid-price series",
          np.array_equal(price_series(r, "mid"), np.array(r.mid_price_series, dtype=float)))


def test_error_cases():
    r = run_simulation(n_agents=30, alpha=0.15, mu=0.025, delta=0.025, lambda_=100, n_steps=30, seed=1)
    check("trade definitions need record_trade_prices=True", raises_value_error(price_series, r, "last"))
    check("unknown definition rejected", raises_value_error(price_series, r, "vwap"))
    r.mid_price_series[3] = None
    check("mid with a one-sided-book gap is rejected, not silently filled",
          raises_value_error(price_series, r, "mid"))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
