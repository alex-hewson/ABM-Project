"""
Tests for the return-distribution helpers. Run with: python test_returns.py
"""

import numpy as np

from returns import return_counts, counts_to_density


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    assert condition, f"FAILED: {label}"


def test_signed_counts_hand_worked():
    prices = [0, 1, 3, 0, 6]      # tau=1 increments: +1, +2, -3, +6
    counts = return_counts(prices, 1, bin_edges=[-3.5, -0.5, 0.5, 1.5, 2.5, 6.5])
    # bins: [-3.5,-0.5) [-0.5,0.5) [0.5,1.5) [1.5,2.5) [2.5,6.5]
    check("signed counts", list(counts) == [1, 0, 1, 1, 1])


def test_absolute_counts_fold_negative_increments():
    prices = [0, 1, 3, 0, 6]
    counts = return_counts(prices, 1, bin_edges=[0.5, 1.5, 2.5, 3.5, 6.5], absolute=True)
    # |increments| = 1, 2, 3, 6
    check("absolute counts", list(counts) == [1, 1, 1, 1])


def test_lag_uses_tau_step():
    prices = [0, 10, 0, 10, 0]    # tau=2 increments: 0, 0, 0
    counts = return_counts(prices, 2, bin_edges=[-0.5, 0.5])
    check("tau=2 sees three zero increments", list(counts) == [3])


def test_out_of_range_increments_not_counted():
    counts = return_counts([0, 100], 1, bin_edges=[0.5, 10.5], absolute=True)
    check("increment of 100 falls outside [0.5, 10.5]", counts.sum() == 0)


def test_density_integrates_to_one():
    rng = np.random.default_rng(0)
    walk = np.cumsum(rng.choice([-1.0, 1.0], size=50_000))
    edges = np.linspace(-100.5, 100.5, 202)
    dens = counts_to_density(return_counts(walk, 10, edges), edges)
    check("density integrates to 1", np.isclose((dens * np.diff(edges)).sum(), 1.0))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
