"""
Tests for the trade-time statistics (analysis/stylised.py), on series whose answers are known.
Run with: python -m tests.test_stylised   (from the project root)
"""

import numpy as np

from analysis.stylised import LAGS, KURTOSIS_LAGS, stylised_facts, changes


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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
