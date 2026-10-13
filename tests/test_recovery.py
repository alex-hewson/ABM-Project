"""
Tests for the shock-recovery measurements. Run with: python -m tests.test_recovery   (from the project root)

Every check uses a made-up series whose answer can be worked out by hand.
"""

import numpy as np

from analysis.recovery import (window, mean_response, pre_shock_level, impact, recovered_fraction,
                               time_to_recover)


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


def test_window_is_cut_around_the_shock():
    series = list(range(100, 120))                 # value = 100 + step
    w = window(series, shock_step=10, before=3, after=4)
    check("window has before + 1 + after values", len(w) == 8)
    check("it starts `before` steps ahead of the shock", w[0] == 107)
    check("index `before` is the shock step itself", w[3] == 110)
    check("it ends `after` steps past the shock", w[-1] == 114)


def test_window_turns_missing_prices_into_nan():
    w = window([1.0, None, 3.0, 4.0], shock_step=1, before=1, after=2)
    check("None becomes NaN", np.isnan(w[1]) and w[0] == 1.0 and w[3] == 4.0)


def test_window_must_fit_inside_the_series():
    series = list(range(10))
    check("too many steps before", raises_value_error(window, series, 2, 3, 1))
    check("too many steps after", raises_value_error(window, series, 8, 1, 2))


def test_mean_response_averages_runs_and_skips_nan():
    mean = mean_response([np.array([1.0, 2.0, np.nan]), np.array([3.0, 4.0, 5.0])])
    check("step-by-step mean, NaN left out", list(mean) == [2.0, 3.0, 5.0])


def step_then(recover_to, before=10, after=50):
    """Level 100 before the shock, 80 at the shock step, then recover_to from the next step on."""
    return np.array([100.0] * before + [80.0] + [recover_to] * after)


def test_level_and_impact():
    r = step_then(80.0)
    check("level before the shock", pre_shock_level(r, before=10) == 100.0)
    check("impact is the move at the shock step (a fall is negative)", impact(r, before=10) == -20.0)
    check("a rise is positive", impact(200.0 - r, before=10) == 20.0)


def test_recovered_fraction_hand_worked():
    check("no recovery: 0", recovered_fraction(step_then(80.0), before=10, tail=5) == 0.0)
    check("back to the old level: 1", recovered_fraction(step_then(100.0), before=10, tail=5) == 1.0)
    check("half way back: 0.5", recovered_fraction(step_then(90.0), before=10, tail=5) == 0.5)
    check("overshoot: above 1", recovered_fraction(step_then(105.0), before=10, tail=5) == 1.25)
    check("no impact at all: NaN", np.isnan(recovered_fraction(np.full(30, 100.0), before=10, tail=5)))


def test_time_to_recover_on_an_exponential_recovery():
    before, tau = 10, 40.0
    k = np.arange(0, 400)
    r = np.concatenate([np.full(before, 100.0), 100.0 - 20.0 * np.exp(-k / tau)])
    # displacement = 20 exp(-k/40); half is undone once exp(-k/40) <= 0.5, i.e. k >= 40 ln 2 = 27.7
    check("half-life of exp(-k/40) is 28 steps", time_to_recover(r, before, fraction=0.5) == 28)
    # 90% undone once exp(-k/40) <= 0.1, i.e. k >= 40 ln 10 = 92.1
    check("90% recovered after 93 steps", time_to_recover(r, before, fraction=0.9) == 93)
    check("fraction recovered by the end is close to 1", abs(recovered_fraction(r, before, tail=20) - 1) < 0.01)


def test_time_to_recover_is_none_when_it_never_happens():
    check("no recovery inside the window: None", time_to_recover(step_then(80.0), before=10) is None)
    check("a partial recovery short of the target: None",
          time_to_recover(step_then(88.0), before=10, fraction=0.5) is None)
    check("but the same series does reach 30%", time_to_recover(step_then(88.0), before=10, fraction=0.3) == 1)
    check("no impact: None", time_to_recover(np.full(30, 100.0), before=10) is None)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
