"""
Tests for the Hurst estimator. Run with: python -m tests.test_hurst   (from the project root)

The estimator is checked against series where the answer is known exactly
(a straight line has H = 1) or approximately (a random walk has H = 0.5), plus
one hand-worked RMS calculation.

Multi-run averaging of H(delta tau) is not tested here: it's done by
experiments/run.py itself now (an earlier standalone analysis/average_hurst.py
did this before the runner existed; removed once the runner superseded it --
see docs/project_plan.md).
"""

import math

import numpy as np

from analysis.hurst import (rms_price_change, log_spaced_taus, hurst_curve, synthetic_random_walk,
                            rms_at_lags, local_slopes)


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    assert condition, f"FAILED: {label}"


def test_rms_price_change_hand_worked():
    prices = [0, 1, 3, 6]
    # tau=1: diffs 1, 2, 3 -> sqrt((1 + 4 + 9) / 3)
    check("rms at tau=1", math.isclose(rms_price_change(prices, 1), math.sqrt(14 / 3)))
    # tau=2: diffs 3, 5 -> sqrt((9 + 25) / 2)
    check("rms at tau=2", math.isclose(rms_price_change(prices, 2), math.sqrt(17)))


def test_log_spaced_taus_properties():
    taus = log_spaced_taus(10, 10_000, 25)
    check("starts at min_tau and ends at max_tau", taus[0] == 10 and taus[-1] == 10_000)
    check("strictly increasing (sorted, no duplicates)", all(a < b for a, b in zip(taus, taus[1:])))
    # ratio between neighbours should be roughly constant in log space
    ratios = [b / a for a, b in zip(taus[10:], taus[11:])]
    check("roughly constant ratio between neighbours at the high end",
          max(ratios) / min(ratios) < 1.1)
    check("low-end rounding collisions are deduplicated",
          len(log_spaced_taus(1, 10, 30)) <= 10)


def test_hurst_of_straight_line_is_one():
    line = [float(t) for t in range(20_000)]
    taus, hs = hurst_curve(line, min_tau=10, max_tau=5_000, n_points=15)
    check("ballistic motion: H = 1 at every lag", all(math.isclose(h, 1.0, abs_tol=1e-9) for h in hs))


def test_hurst_curve_drops_one_point_at_each_end():
    walk = synthetic_random_walk(20_000, seed=3)
    all_taus = log_spaced_taus(10, 2_000, 12)
    taus, hs = hurst_curve(walk, min_tau=10, max_tau=2_000, n_points=12)
    check("one H per interior tau", len(taus) == len(hs) == len(all_taus) - 2)
    check("outer taus are dropped", taus[0] == all_taus[1] and taus[-1] == all_taus[-2])


def test_hurst_curve_ignores_lags_longer_than_series():
    short = synthetic_random_walk(500, seed=4)
    taus, hs = hurst_curve(short, min_tau=10, max_tau=100_000, n_points=20)
    check("no tau exceeds the usable series length", max(taus) <= len(short) - 2)


def test_hurst_of_random_walk_is_about_half():
    walk = synthetic_random_walk(100_000, seed=1)
    taus, hs = hurst_curve(walk, min_tau=10, max_tau=5_000, n_points=20)
    mean_h = sum(hs) / len(hs)
    # single runs are noisy at large lags (individual H values wander by ~0.1), hence a loose bound
    check(f"mean H {mean_h:.3f} within 0.05 of 0.5", abs(mean_h - 0.5) < 0.05)


def test_rms_at_lags_matches_the_reference_implementation():
    walk = synthetic_random_walk(3_000, seed=6)
    taus = [1, 2, 7, 50, 400]
    fast = rms_at_lags(walk, taus)
    slow = [rms_price_change(walk, t) for t in taus]
    check("numpy RMS equals the pure-Python RMS at every lag", np.allclose(fast, slow))


def test_local_slopes_recover_a_known_power_law_including_the_ends():
    taus = np.array(log_spaced_taus(1, 10_000, 40))
    for exponent in (0.3, 0.5, 1.0):
        slopes = local_slopes(taus, taus ** exponent)
        check(f"RMS ~ tau^{exponent}: slope is {exponent} at every lag, first and last included",
              np.allclose(slopes, exponent))
    check("one slope per lag (no end points lost)", len(local_slopes(taus, taus)) == len(taus))


def test_local_slopes_end_points_are_one_sided():
    taus = np.array([1.0, 10.0, 100.0])
    values = np.array([1.0, 10.0, 1000.0])       # slope 1 between the first two lags, 2 between the last two
    slopes = local_slopes(taus, values)
    check("first lag uses the difference to its neighbour", np.isclose(slopes[0], 1.0))
    check("last lag uses the difference to its neighbour", np.isclose(slopes[-1], 2.0))
    check("interior uses the centred difference", np.isclose(slopes[1], 1.5))


def test_stored_rms_route_agrees_with_hurst_curve_and_a_random_walk():
    walk = synthetic_random_walk(100_000, seed=1)
    taus = np.array(log_spaced_taus(10, 5_000, 20))
    slopes = local_slopes(taus, rms_at_lags(walk, taus))
    old_taus, old_h = hurst_curve(walk, min_tau=10, max_tau=5_000, n_points=20)
    check("interior slopes equal hurst_curve's values",
          np.allclose(slopes[1:-1], old_h) and list(taus[1:-1]) == list(old_taus))
    check(f"random walk: mean H {slopes.mean():.3f} within 0.05 of 0.5", abs(slopes.mean() - 0.5) < 0.05)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
