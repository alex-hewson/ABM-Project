"""
Tests for the autocorrelation measures. Run with: python -m tests.test_autocorr   (from the project root)

Each check uses a made-up series whose autocorrelation is known.
"""

import numpy as np

from analysis.autocorr import interval_changes, autocorrelation, change_autocorrelations


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


def test_interval_changes_hand_worked():
    prices = [10, 11, 13, 12, 16, 20, 19, 25, 24]      # every 2nd value: 10, 13, 16, 19, 24
    check("changes over blocks of 2 steps", list(interval_changes(prices, 2)) == [3, 3, 3, 5])
    check("interval 1 is the plain step-by-step change", list(interval_changes([1, 4, 2], 1)) == [3, -2])
    check("an interval of 0 is rejected", raises_value_error(interval_changes, prices, 0))


def test_alternating_series_is_perfectly_anti_correlated():
    x = np.array([1.0, -1.0] * 500)
    rho = autocorrelation(x, 4)
    # lag 1: every value is followed by its opposite; lag 2: by itself. The sums run over N - lag
    # terms but are divided by all N, so the sizes are (N - lag) / N, not exactly 1.
    check("lag 1: -1 (to within 1/N)", abs(rho[0] + 1) < 0.002)
    check("lag 2: +1 (to within 2/N)", abs(rho[1] - 1) < 0.003)
    check("lags 3 and 4 repeat the pattern", rho[2] < -0.99 and rho[3] > 0.99)


def test_independent_noise_has_no_autocorrelation():
    x = np.random.default_rng(0).normal(size=40_000)
    rho = autocorrelation(x, 20)
    # standard error per lag is 1/sqrt(40000) = 0.005
    check(f"every lag within 0.02 of zero (largest {np.abs(rho).max():.3f})", np.abs(rho).max() < 0.02)


def test_ar1_series_decays_geometrically():
    rng = np.random.default_rng(1)
    phi, n = 0.6, 200_000
    noise = rng.normal(size=n)
    x = np.empty(n)
    x[0] = noise[0]
    for i in range(1, n):
        x[i] = phi * x[i - 1] + noise[i]           # theory: autocorrelation at lag k is phi^k
    rho = autocorrelation(x, 4)
    check(f"lag 1: {rho[0]:.3f} within 0.01 of 0.6", abs(rho[0] - 0.6) < 0.01)
    check(f"lag 2: {rho[1]:.3f} within 0.01 of 0.36", abs(rho[1] - 0.36) < 0.01)
    check(f"lag 4: {rho[3]:.3f} within 0.01 of 0.1296", abs(rho[3] - 0.1296) < 0.01)


def test_constant_series_and_bad_lags():
    check("a series that never varies gives NaN, not an error", np.isnan(autocorrelation([5.0] * 50, 3)).all())
    check("a lag as long as the series is rejected", raises_value_error(autocorrelation, [1.0, 2.0, 3.0], 3))
    check("a lag of 0 is rejected", raises_value_error(autocorrelation, [1.0, 2.0, 3.0], 0))


def test_volatility_clustering_shows_in_absolute_changes_only():
    # Price changes with a random sign, but small for 200 intervals and then large for 200, over and
    # over. The sign of one change says nothing about the next; its size says a lot.
    rng = np.random.default_rng(2)
    interval, blocks = 5, 400
    sizes = np.repeat(np.tile([1.0, 6.0], blocks // 2), 200)
    changes = sizes * rng.choice([-1.0, 1.0], size=len(sizes))
    prices = np.concatenate([[0.0], np.cumsum(changes)])
    prices = np.repeat(prices, interval)[: len(changes) * interval + 1]     # hold each price for 5 steps
    out = change_autocorrelations(prices, interval, max_lag=10)
    check(f"signed changes: no autocorrelation (largest {np.abs(out['signed']).max():.3f}, below 0.03)",
          np.abs(out["signed"]).max() < 0.03)
    check(f"absolute changes: strongly positive at lag 1 ({out['absolute'][0]:.2f}, above 0.9)", out["absolute"][0] > 0.9)
    check("and still positive 10 intervals later", out["absolute"][9] > 0.8)


def test_trending_price_shows_in_signed_changes():
    # A price that keeps going the same way for 50 intervals at a time.
    rng = np.random.default_rng(3)
    direction = np.repeat(rng.choice([-1.0, 1.0], size=400), 50)
    changes = direction + rng.normal(scale=0.5, size=len(direction))
    prices = np.concatenate([[0.0], np.cumsum(changes)])
    out = change_autocorrelations(prices, 1, max_lag=5)
    check(f"signed changes: clearly positive at lag 1 ({out['signed'][0]:.2f}, above 0.6)", out["signed"][0] > 0.6)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
