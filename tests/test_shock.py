"""
Tests for the shock-test experiment. Run with: python -m tests.test_shock   (from the project root)

Short runs only: these check that each run hands back the right stretch of each series, not the
physics (the shock itself is tested in tests/test_simulation.py).
"""

import numpy as np

from abm.agents import AgentType
from experiments.shock import run_one, parse_mix, describe_mix, BEFORE, QUANTITIES


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    assert condition, f"FAILED: {label}"


WARMUP, AFTER = 300, 250
NO_VALUE_TRADERS = (0, 1.0, 50.0)        # (how many, true value step, spread): none, so the last two are unused


def test_each_run_returns_one_window_per_quantity():
    r = run_one((40, 3, WARMUP, AFTER, False, None, None, NO_VALUE_TRADERS))
    check("all four quantities are returned", all(q in r for q in QUANTITIES))
    check("each window has BEFORE + 1 + after values", all(len(r[q]) == BEFORE + 1 + AFTER for q in QUANTITIES))
    check("the price is measured from the step before the shock", r["price"][BEFORE - 1] == 0.0)
    check("the spread is positive throughout", np.all(r["spread"] > 0))


def test_same_seed_is_identical_until_the_shock():
    control = run_one((0, 3, WARMUP, AFTER, False, None, None, NO_VALUE_TRADERS))
    sell = run_one((40, 3, WARMUP, AFTER, False, None, None, NO_VALUE_TRADERS))
    buy = run_one((40, 3, WARMUP, AFTER, True, None, None, NO_VALUE_TRADERS))
    check("before the shock, the control and the shocked run agree on every quantity",
          all(np.array_equal(control[q][:BEFORE], sell[q][:BEFORE]) for q in QUANTITIES))
    check("the sell order takes 40 units off the bid side at the shock step",
          control["bid_volume"][BEFORE] - sell["bid_volume"][BEFORE] == 40
          and control["ask_volume"][BEFORE] == sell["ask_volume"][BEFORE])
    check("and the price falls", sell["price"][BEFORE] < control["price"][BEFORE])
    check("the buy order takes 40 units off the ask side instead",
          control["ask_volume"][BEFORE] - buy["ask_volume"][BEFORE] == 40
          and control["bid_volume"][BEFORE] == buy["bid_volume"][BEFORE])
    check("and the price rises", buy["price"][BEFORE] > control["price"][BEFORE])
    check("a shock this small is fully filled", sell["unfilled"] == 0 and buy["unfilled"] == 0)


def raises_value_error(fn, *args):
    try:
        fn(*args)
    except ValueError:
        return True
    return False


def test_mix_options_are_read_correctly():
    check("no option: None, which means the paper's population", parse_mix(None) is None)
    check("K:COUNT gives interval = size = K",
          parse_mix(["1:100", "2:100", "4:50"]) == {AgentType(1, 1): 100, AgentType(2, 2): 100, AgentType(4, 4): 50})
    check("INTERVAL/SIZE:COUNT sets the two separately", parse_mix(["4/1:250"]) == {AgentType(4, 1): 250})
    check("the same type given twice is added up", parse_mix(["2:100", "2:50"]) == {AgentType(2, 2): 150})
    check("nonsense is rejected", raises_value_error(parse_mix, ["fast:10"]) and raises_value_error(parse_mix, ["4"]))
    check("an interval of 0 is rejected", raises_value_error(parse_mix, ["0:10"]))


def test_mix_description():
    check("default", describe_mix(None) == "250 x 1 unit every step")
    check("mixed", describe_mix({AgentType(1, 1): 100, AgentType(4, 4): 150})
          == "100 x 1 unit every step, 150 x 4 units every 4 steps")


def test_a_run_with_slow_big_providers_supplies_the_same_volume():
    slow = run_one((0, 3, 600, AFTER, False, {AgentType(4, 4): 250}, None, NO_VALUE_TRADERS))
    plain = run_one((0, 3, 600, AFTER, False, None, None, NO_VALUE_TRADERS))
    slow_volume = float(slow["bid_volume"].mean() + slow["ask_volume"].mean())
    plain_volume = float(plain["bid_volume"].mean() + plain["ask_volume"].mean())
    check(f"resting volume with 4-step providers ({slow_volume:.0f}) within 6% of the paper's population ({plain_volume:.0f})",
          abs(slow_volume - plain_volume) < 0.06 * plain_volume)


def test_price_relative_to_the_true_value():
    plain = run_one((300, 3, WARMUP, AFTER, False, None, None, NO_VALUE_TRADERS))
    check("without value traders it is just the price change", np.array_equal(plain["price_vs_value"], plain["price"]))
    no_news = run_one((300, 3, WARMUP, AFTER, False, None, None, (50, 0.0, 50.0)))
    check("with value traders but no news the true value never moves, so it is again the price change",
          np.allclose(no_news["price_vs_value"], no_news["price"]))
    news = run_one((300, 3, WARMUP, AFTER, False, None, None, (50, 2.0, 50.0)))
    check("with news it differs from the plain price change", not np.allclose(news["price_vs_value"], news["price"]))
    check("both are measured from the step before the shock",
          news["price_vs_value"][BEFORE - 1] == 0 and news["price"][BEFORE - 1] == 0)


def test_a_run_with_value_traders_differs_only_by_having_them():
    plain = run_one((0, 3, WARMUP, AFTER, False, None, None, NO_VALUE_TRADERS))
    again = run_one((0, 3, WARMUP, AFTER, False, None, None, (0, 7.7, 5.0)))
    with_traders = run_one((0, 3, WARMUP, AFTER, False, None, None, (125, 1.0, 20.0)))
    check("with 0 value traders the true value step and spread settings change nothing",
          all(np.array_equal(plain[q], again[q]) for q in QUANTITIES))
    check("with 125 value traders the run is a different one", not np.array_equal(plain["spread"], with_traders["spread"]))
    check("and the book still has both sides throughout", np.all(with_traders["spread"] > 0))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
