"""
Tests for the shock-test experiment. Run with: python -m tests.test_shock   (from the project root)

Short runs only: these check that each run hands back the right stretch of each series, not the
physics (the shock itself is tested in tests/test_simulation.py).
"""

import numpy as np

from experiments.shock import run_one, BEFORE, QUANTITIES


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    assert condition, f"FAILED: {label}"


WARMUP, AFTER = 300, 250


def test_each_run_returns_one_window_per_quantity():
    r = run_one((40, 3, WARMUP, AFTER, False))
    check("all four quantities are returned", all(q in r for q in QUANTITIES))
    check("each window has BEFORE + 1 + after values", all(len(r[q]) == BEFORE + 1 + AFTER for q in QUANTITIES))
    check("the price is measured from the step before the shock", r["price"][BEFORE - 1] == 0.0)
    check("the spread is positive throughout", np.all(r["spread"] > 0))


def test_same_seed_is_identical_until_the_shock():
    control = run_one((0, 3, WARMUP, AFTER, False))
    sell = run_one((40, 3, WARMUP, AFTER, False))
    buy = run_one((40, 3, WARMUP, AFTER, True))
    check("before the shock, the control and the shocked run agree on every quantity",
          all(np.array_equal(control[q][:BEFORE], sell[q][:BEFORE]) for q in QUANTITIES))
    check("the sell order takes 40 orders off the bid side at the shock step",
          control["n_bids"][BEFORE] - sell["n_bids"][BEFORE] == 40
          and control["n_asks"][BEFORE] == sell["n_asks"][BEFORE])
    check("and the price falls", sell["price"][BEFORE] < control["price"][BEFORE])
    check("the buy order takes 40 orders off the ask side instead",
          control["n_asks"][BEFORE] - buy["n_asks"][BEFORE] == 40
          and control["n_bids"][BEFORE] == buy["n_bids"][BEFORE])
    check("and the price rises", buy["price"][BEFORE] > control["price"][BEFORE])
    check("a shock this small is fully filled", sell["unfilled"] == 0 and buy["unfilled"] == 0)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
