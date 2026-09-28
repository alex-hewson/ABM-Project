"""
Tests for the order book depth profile and its lognormal fit.
Run with: python -m tests.test_depth_profile   (from the project root)
"""

import numpy as np

from analysis.depth_profile import (profile_from_depth_sum, combine_sides,
                                    fit_lognormal, LognormalFit)


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


def test_profile_from_depth_sum_matches_brute_force():
    # Keys are HALF-ticks, binned to whole ticks by floor division (as run_simulation's callers
    # do). Floor division rounds toward -inf, not toward zero, so e.g. -8//2 and -7//2 are both
    # -4, while -6//2 is -3 -- checked explicitly here since it's easy to get backwards.
    check("floor division sanity check (easy to get backwards for negatives)",
          -8 // 2 == -7 // 2 == -4 and -6 // 2 == -3)
    depth_sum = {-8: 3, -7: 1, -6: 2, 6: 4, 7: 5, 8: 6}
    profile = profile_from_depth_sum(depth_sum, n_snapshots=10)
    check("half-tick keys -8 and -7 merge into tick -4", profile[-4] == (3 + 1) / 10)
    check("tick -3 gets the -6 entry alone", profile[-3] == 2 / 10)
    check("half-tick keys 6 and 7 merge into tick 3", profile[3] == (4 + 5) / 10)
    check("tick 4 gets the 8 entry alone", profile[4] == 6 / 10)
    check("n_snapshots=0 gives an empty profile, not a division error", profile_from_depth_sum(depth_sum, 0) == {})


def test_combine_sides():
    profile = {-10: 2.0, -5: 1.0, 0: 99.0, 5: 3.0, 20: 4.0}
    combined = combine_sides(profile)
    check("midpoint (tick 0) is excluded", 0 not in combined)
    check("tick 5 sums both sides (-5 and +5)", combined[5] == 1.0 + 3.0)
    check("tick 10 has only the bid side", combined[10] == 2.0)
    check("tick 20 has only the ask side", combined[20] == 4.0)


def test_fit_recovers_known_lognormal_parameters():
    rng = np.random.default_rng(0)
    true_mu, true_sigma = np.log(35), 0.5      # roughly matches the observed peak near 35 ticks
    samples = rng.lognormal(mean=true_mu, sigma=true_sigma, size=200_000)
    x = np.round(samples).astype(int)
    x = x[x > 0]
    profile = {}
    for v in x:
        profile[int(v)] = profile.get(int(v), 0) + 1

    fit = fit_lognormal(profile)
    check(f"recovered mu {fit.mu:.3f} close to true {true_mu:.3f}", abs(fit.mu - true_mu) < 0.02)
    check(f"recovered sigma {fit.sigma:.3f} close to true {true_sigma:.3f}", abs(fit.sigma - true_sigma) < 0.02)
    check("total_weight equals the sample count", fit.total_weight == len(x))


def test_fit_error_cases():
    check("empty profile rejected", raises_value_error(fit_lognormal, {}))
    check("non-positive distance rejected", raises_value_error(fit_lognormal, {0: 5, 1: 2}))
    check("degenerate (single point) profile rejected", raises_value_error(fit_lognormal, {10: 5}))


def test_density_and_scaled_curve():
    fit = LognormalFit(mu=np.log(35), sigma=0.5, total_weight=1200)
    x = np.array([0, -5, 1, 35, 200])
    d = fit.density(x)
    check("density is 0 at x<=0, not an error", d[0] == 0 and d[1] == 0)
    check("density is positive for x>0", np.all(d[2:] > 0))
    scaled = fit.scaled_curve(x)
    check("scaled_curve = total_weight * density", np.allclose(scaled, fit.total_weight * d))
    # The mode of a lognormal is exp(mu - sigma^2), close to 35 for these parameters.
    xs = np.arange(1, 200)
    peak_x = xs[np.argmax(fit.density(xs))]
    check(f"density peaks near exp(mu - sigma^2) (got {peak_x})", abs(peak_x - np.exp(fit.mu - fit.sigma**2)) < 2)


def test_end_to_end_on_a_real_simulation():
    from abm.simulation import run_simulation
    r = run_simulation(n_agents=250, alpha=0.15, mu=0.025, delta=0.025, lambda_=100,
                       n_steps=3000, seed=1, depth_record_from=1000)
    check("some depth snapshots were recorded", r.n_depth_snapshots > 0)
    profile = profile_from_depth_sum(r.depth_profile_sum, r.n_depth_snapshots)
    combined = combine_sides(profile)
    fit = fit_lognormal(combined)
    check("fit parameters are finite", np.isfinite(fit.mu) and np.isfinite(fit.sigma) and fit.sigma > 0)
    check("fitted curve is finite and non-negative over the observed range",
          np.all(np.isfinite(fit.scaled_curve(np.arange(1, 300)))) and
          np.all(fit.scaled_curve(np.arange(1, 300)) >= 0))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
