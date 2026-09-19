"""
Tests for the Hurst estimator and multi-run averaging. Run with: python test_hurst.py

The estimator is checked against series where the answer is known exactly
(a straight line has H = 1) or approximately (a random walk has H = 0.5), plus
one hand-worked RMS calculation.
"""

import math

from hurst import rms_price_change, log_spaced_taus, hurst_curve, synthetic_random_walk
from average_hurst import average_hurst_over_runs


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


def test_average_hurst_over_runs():
    kwargs = dict(n_agents=100, alpha=0.15, mu=0.025, delta=0.025, lambda_=100,
                  n_steps=2_000, min_tau=10, max_tau=500, n_points=10)
    r = average_hurst_over_runs(n_runs=3, base_seed=0, **kwargs)
    check("n_runs recorded", r.n_runs == 3)
    check("all output lists have one entry per tau",
          len(r.taus) == len(r.mean_h) == len(r.min_h) == len(r.max_h))
    check("min <= mean <= max at every tau",
          all(lo <= m <= hi for lo, m, hi in zip(r.min_h, r.mean_h, r.max_h)))

    single = average_hurst_over_runs(n_runs=1, base_seed=0, **kwargs)
    check("with one run, mean == min == max",
          single.mean_h == single.min_h == single.max_h)
    check("averaging is deterministic for a given base_seed",
          average_hurst_over_runs(n_runs=3, base_seed=0, **kwargs).mean_h == r.mean_h)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
