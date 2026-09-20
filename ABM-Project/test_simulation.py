"""
Tests for the simulation loop. Run with: python test_simulation.py

The main check is against the paper's Eq. 2, the equilibrium book depth:

    N_eq / N_A = alpha * (1/delta - 1) - mu / delta

This depends on the per-step order (providers -> cancellation -> takers, as in
Eq. 1). At the paper's Fig. 2 parameters the two possible orders differ by only
~0.5%, so a second, faster-dynamics parameter set is used where they differ by
~14% and the test can actually tell them apart.
"""

from orderbook import Side
from simulation import run_simulation, check_stability_condition


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


def eq2_equilibrium_orders(n_agents, alpha, mu, delta):
    return n_agents * (alpha * (1 / delta - 1) - mu / delta)


def mean_tail_orders(result, fraction=0.5):
    tail = result.total_orders_series[int(len(result.total_orders_series) * (1 - fraction)):]
    return sum(tail) / len(tail)


def test_stability_condition_accepts_paper_parameters():
    check("Fig. 2 parameters pass the stability check",
          not raises_value_error(check_stability_condition, 0.15, 0.025, 0.025))


def test_stability_condition_rejects_unstable_parameters():
    check("alpha*(1-delta) <= mu is rejected",
          raises_value_error(check_stability_condition, 0.02, 0.025, 0.025))
    check("delta = 0 is rejected", raises_value_error(check_stability_condition, 0.15, 0.025, 0.0))
    check("run_simulation itself refuses unstable parameters",
          raises_value_error(lambda: run_simulation(
              n_agents=10, alpha=0.02, mu=0.025, delta=0.025, lambda_=100, n_steps=10)))


def test_output_shape_and_basic_sanity():
    n_steps = 500
    r = run_simulation(n_agents=100, alpha=0.15, mu=0.025, delta=0.025, lambda_=100,
                       n_steps=n_steps, seed=1)
    check("one mid-price per step", len(r.mid_price_series) == n_steps)
    check("one book-size entry per step", len(r.total_orders_series) == n_steps)
    check("trades happened", r.n_trades > 0 and r.n_trades == len(r.book.trades))
    check("book size never negative", min(r.total_orders_series) >= 0)
    first = next(p for p in r.mid_price_series if p is not None)
    check("prices start near p0 = 1,000,000", abs(first - 1_000_000) < 1_000)


def test_book_is_never_crossed_at_end():
    r = run_simulation(n_agents=100, alpha=0.15, mu=0.025, delta=0.025, lambda_=100,
                       n_steps=2_000, seed=2)
    bb, ba = r.book.best_bid(), r.book.best_ask()
    check("best bid < best ask (crossing orders must have traded)", bb is not None and ba is not None and bb < ba)


def test_reproducible_with_seed():
    def run(seed):
        return run_simulation(n_agents=50, alpha=0.15, mu=0.025, delta=0.025, lambda_=100,
                              n_steps=300, seed=seed)
    a, b, c = run(11), run(11), run(12)
    check("same seed -> identical mid-price series", a.mid_price_series == b.mid_price_series)
    check("same seed -> identical book sizes", a.total_orders_series == b.total_orders_series)
    check("different seed -> different series", a.mid_price_series != c.mid_price_series)


def test_equilibrium_depth_matches_eq2_at_fig2_parameters():
    n_agents, alpha, mu, delta = 250, 0.15, 0.025, 0.025
    expected = eq2_equilibrium_orders(n_agents, alpha, mu, delta)   # 1212.5
    r = run_simulation(n_agents=n_agents, alpha=alpha, mu=mu, delta=delta, lambda_=100,
                       n_steps=3_000, seed=1)
    measured = mean_tail_orders(r)
    check(f"mean depth {measured:.0f} within 3% of Eq. 2's {expected:.0f}",
          abs(measured - expected) < 0.03 * expected)
    check("no empty-book failures at these parameters", r.n_match_failures == 0)


def test_equilibrium_depth_distinguishes_step_order():
    # Paper order  (providers, cancel, takers): N_eq = 175
    # Swapped order (providers, takers, cancel): N_eq = 200
    n_agents, alpha, mu, delta = 250, 0.3, 0.1, 0.2
    expected = eq2_equilibrium_orders(n_agents, alpha, mu, delta)
    check("Eq. 2 predicts 175 here", abs(expected - 175) < 1e-9)
    for seed in (1, 2, 3):
        r = run_simulation(n_agents=n_agents, alpha=alpha, mu=mu, delta=delta, lambda_=100,
                           n_steps=1_500, seed=seed)
        measured = mean_tail_orders(r)
        check(f"seed {seed}: mean depth {measured:.1f} within 8 of 175 (swapped order would give 200)",
              abs(measured - expected) < 8)


def test_depth_recording_is_consistent_with_total_orders():
    n_steps, record_from, every = 400, 300, 5
    r = run_simulation(n_agents=100, alpha=0.15, mu=0.025, delta=0.025, lambda_=100,
                       n_steps=n_steps, seed=5, depth_record_from=record_from,
                       depth_record_every=every)
    check("midpoint defined throughout (needed for this test)", None not in r.mid_price_series)
    expected_snapshots = len(range(record_from, n_steps, every))
    check(f"{expected_snapshots} snapshots taken", r.n_depth_snapshots == expected_snapshots)
    # Snapshots are taken at the same moment as total_orders_series is recorded.
    expected_orders = sum(r.total_orders_series[record_from::every])
    check("summed profile equals summed book sizes at snapshot steps",
          sum(r.depth_profile_sum.values()) == expected_orders)
    keys = list(r.depth_profile_sum)
    check("bids have negative offsets, asks positive, none at the midpoint",
          min(keys) < 0 < max(keys) and 0 not in keys)


def test_depth_recording_off_by_default():
    r = run_simulation(n_agents=50, alpha=0.15, mu=0.025, delta=0.025, lambda_=100,
                       n_steps=50, seed=1)
    check("no depth data unless requested", r.depth_profile_sum == {} and r.n_depth_snapshots == 0)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
