"""
Tests for the simulation loop. Run with: python -m tests.test_simulation   (from the project root)

The main check is against the paper's Eq. 2, the equilibrium book depth:

    N_eq / N_A = alpha * (1/delta - 1) - mu / delta

This depends on the per-step order (providers -> cancellation -> takers, as in
Eq. 1). At the paper's Fig. 2 parameters the two possible orders differ by only
~0.5%, so a second, faster-dynamics parameter set is used where they differ by
~14% and the test can actually tell them apart.
"""

from abm.orderbook import Side
from abm.agents import ConstantSide, BoundedRandomWalk, MeanRevertingWalk
from abm.simulation import run_simulation, check_stability_condition


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


def test_unknown_method_is_rejected():
    check("method must be 'fast' or 'agents'", raises_value_error(lambda: run_simulation(
        n_agents=10, alpha=0.15, mu=0.025, delta=0.025, lambda_=100, n_steps=10, method="turbo")))


def test_both_methods_reproduce_eq2_and_expected_trade_rate():
    """Equilibrium depth (Eq. 2) and the trade rate (each step, on average mu*N_A market orders
    execute) are known exactly, so they check each method against theory, not just each other."""
    n_agents, alpha, mu, delta, n_steps = 250, 0.3, 0.1, 0.2, 1_500
    expected_depth = eq2_equilibrium_orders(n_agents, alpha, mu, delta)   # 175 (a swapped step order gives 200)
    for method in ("agents", "fast"):
        r = run_simulation(n_agents=n_agents, alpha=alpha, mu=mu, delta=delta, lambda_=100,
                           n_steps=n_steps, seed=3, method=method)
        depth = mean_tail_orders(r)
        check(f"{method}: mean depth {depth:.1f} within 8 of Eq. 2's 175", abs(depth - expected_depth) < 8)
        rate = r.n_trades / n_steps
        check(f"{method}: {rate:.2f} trades/step within 3% of mu*N_A = {mu * n_agents:.0f}",
              abs(rate - mu * n_agents) < 0.03 * mu * n_agents)


def test_fast_method_is_statistically_equivalent_to_reference():
    """Same seed gives different runs under the two methods, so compare statistics averaged over
    seeds. Tolerances are ~3 standard errors of the difference, measured from run-to-run spread."""
    from analysis.hurst import rms_price_change
    n_agents, n_steps, burn_in, tau, seeds = 100, 3_000, 500, 50, range(12)
    stats = {}
    for method in ("agents", "fast"):
        rms, depth, trades = [], [], []
        for s in seeds:
            r = run_simulation(n_agents=n_agents, alpha=0.15, mu=0.025, delta=0.025, lambda_=100,
                               n_steps=n_steps, seed=s, method=method)
            rms.append(rms_price_change(r.mid_price_series[burn_in:], tau))
            depth.append(sum(r.total_orders_series[burn_in:]) / (n_steps - burn_in))
            trades.append(r.n_trades / n_steps)
        stats[method] = tuple(sum(v) / len(v) for v in (rms, depth, trades))
    (rms_a, depth_a, trades_a), (rms_f, depth_f, trades_f) = stats["agents"], stats["fast"]
    check(f"RMS price change at tau={tau}: agents {rms_a:.2f} vs fast {rms_f:.2f} (within 1.0)",
          abs(rms_a - rms_f) < 1.0)
    check(f"mean book depth: agents {depth_a:.1f} vs fast {depth_f:.1f} (within 8)",
          abs(depth_a - depth_f) < 8)
    check(f"trades per step: agents {trades_a:.3f} vs fast {trades_f:.3f} (within 0.04)",
          abs(trades_a - trades_f) < 0.04)


def test_not_keeping_trades_changes_nothing_but_memory():
    kwargs = dict(n_agents=60, alpha=0.15, mu=0.025, delta=0.025, lambda_=100, n_steps=300, seed=8)
    full = run_simulation(**kwargs)
    lean = run_simulation(keep_trades=False, record_trade_prices=True, **kwargs)
    check("identical price path", full.mid_price_series == lean.mid_price_series)
    check("identical book sizes", full.total_orders_series == lean.total_orders_series)
    check("identical trade count", full.n_trades == lean.n_trades == len(full.book.trades))
    check("no Trade objects stored", lean.book.trades == [])


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


def test_a_constant_flow_reproduces_the_plain_run_exactly():
    kwargs = dict(n_agents=60, alpha=0.15, mu=0.025, delta=0.025, lambda_=100, n_steps=300, seed=8)
    for method in ("fast", "agents"):
        plain = run_simulation(method=method, **kwargs)
        flow = run_simulation(method=method, taker_flow=ConstantSide(0.5), **kwargs)
        check(f"{method}: identical price path with a constant flow at 1/2 (no random numbers used)",
              plain.mid_price_series == flow.mid_price_series and plain.n_trades == flow.n_trades)
    check("the flow's q is recorded for every step", list(flow.q_taker_series) == [0.5] * 300)
    check("no q series without a flow", len(plain.q_taker_series) == 0)


def test_the_flows_buy_probability_reaches_the_takers():
    for method in ("fast", "agents"):
        r = run_simulation(n_agents=60, alpha=0.15, mu=0.025, delta=0.025, lambda_=100,
                           n_steps=1_500, seed=5, method=method, taker_flow=ConstantSide(0.9))
        buys = sum(t.aggressor_side is Side.BID for t in r.book.trades)
        fraction = buys / len(r.book.trades)
        check(f"{method}: q=0.9 gives {fraction:.3f} buy-initiated trades (within 0.04 of 0.9)",
              abs(fraction - 0.9) < 0.04)


def test_a_walking_flow_is_recorded_and_reproducible():
    kwargs = dict(n_agents=60, alpha=0.15, mu=0.025, delta=0.025, lambda_=100, n_steps=400, seed=9)
    a = run_simulation(taker_flow=BoundedRandomWalk(), **kwargs)
    b = run_simulation(taker_flow=BoundedRandomWalk(), **kwargs)
    q = a.q_taker_series
    check("one q per step", len(q) == 400)
    check("the first step uses the starting value, exactly 1/2", q[0] == 0.5)
    check("q moves by exactly one step (0.001) between steps",
          all(abs(abs(d) - 0.001) < 1e-12 for d in (q[1:] - q[:-1])))
    check("q stays within the walk's bounds", q.min() >= 0.45 - 1e-9 and q.max() <= 0.55 + 1e-9)
    check("same seed, fresh flow objects: identical q series and price path",
          list(q) == list(b.q_taker_series) and a.mid_price_series == b.mid_price_series)


def test_an_asymmetric_flow_still_gives_a_working_book():
    for flow in (BoundedRandomWalk(), MeanRevertingWalk()):
        r = run_simulation(n_agents=100, alpha=0.15, mu=0.025, delta=0.025, lambda_=100,
                           n_steps=2_000, seed=6, taker_flow=flow)
        check(f"{type(flow).__name__}: no empty-book failures and trades happen",
              r.n_match_failures == 0 and r.n_trades > 0)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
