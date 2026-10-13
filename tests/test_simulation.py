"""
Tests for the simulation loop. Run with: python -m tests.test_simulation   (from the project root)

The main check is against the paper's Eq. 2, the equilibrium book depth:

    N_eq / N_A = alpha * (1/delta - 1) - mu / delta

This depends on the per-step order (providers -> cancellation -> takers, as in
Eq. 1). At the paper's Fig. 2 parameters the two possible orders differ by only
~0.5%, so a second, faster-dynamics parameter set is used where they differ by
~14% and the test can actually tell them apart.
"""

import hashlib

import numpy as np

from abm.orderbook import Side
from abm.buy_probability import ConstantSide, BoundedRandomWalk, MeanRevertingWalk
from abm.agents import AgentType, is_turn
from abm.simulation import run_simulation, check_stability_condition, Shock, SHOCK_AGENT_ID, _turn_lists


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


def test_depth_coupling_zero_changes_nothing():
    kwargs = dict(n_agents=60, alpha=0.15, mu=0.025, delta=0.025, lambda_=100, n_steps=300, seed=8)
    for method in ("fast", "agents"):
        plain = run_simulation(method=method, taker_flow=MeanRevertingWalk(), **kwargs)
        zero = run_simulation(method=method, taker_flow=MeanRevertingWalk(), depth_coupling=0.0,
                              q_rms=0.0158, **kwargs)
        check(f"{method}: depth_coupling=0 gives an identical run", plain.mid_price_series == zero.mid_price_series)
    check("no lambda series without coupling", len(zero.lambda_series) == 0)


def test_lambda_follows_eq4_every_step():
    flow = MeanRevertingWalk()
    r = run_simulation(n_agents=60, alpha=0.15, mu=0.025, delta=0.025, lambda_=100, n_steps=2_000, seed=4,
                       taker_flow=flow, depth_coupling=10, q_rms=flow.stationary_rms)
    q, lam = r.q_taker_series, r.lambda_series
    expected = 100 * (1 + abs(q - 0.5) / flow.stationary_rms * 10)
    check("one lambda per step", len(lam) == 2_000)
    check("lambda(t) = lambda_0 (1 + |q(t) - 1/2| / q_rms * C) at every step, using that step's q",
          np.allclose(lam, expected))
    check("first step: q = 1/2, so lambda = lambda_0", lam[0] == 100)
    check(f"lambda varies over the run (up to {lam.max():.0f})", lam.max() > 200)
    check("no empty-book failures", r.n_match_failures == 0)


def test_depth_coupling_is_validated():
    kwargs = dict(n_agents=10, alpha=0.15, mu=0.025, delta=0.025, lambda_=100, n_steps=10)
    check("negative coupling rejected", raises_value_error(lambda: run_simulation(
        taker_flow=MeanRevertingWalk(), depth_coupling=-1, q_rms=0.0158, **kwargs)))
    check("coupling without a taker flow rejected (lambda(t) needs q(t))", raises_value_error(lambda: run_simulation(
        depth_coupling=10, q_rms=0.0158, **kwargs)))
    check("coupling without q_rms rejected", raises_value_error(lambda: run_simulation(
        taker_flow=MeanRevertingWalk(), depth_coupling=10, **kwargs)))

def run_fingerprint(result):
    """A few numbers that pin down a whole run: any change to the model's behaviour changes them."""
    mids = np.array([np.nan if m is None else m for m in result.mid_price_series])
    orders = np.array(result.total_orders_series, dtype=np.int64)
    digest = hashlib.sha256(mids.tobytes() + orders.tobytes()).hexdigest()[:16]
    return (result.n_trades, result.mid_price_series[-1], int(orders.sum()), digest)


def test_baseline_runs_are_unchanged():
    """D23: with every later option switched off, a run must be exactly the baseline-v1 run.
    The expected numbers were recorded from the baseline-v1 code (Python 3.14, same seed). A
    different Python version may draw different random numbers and so fail this test without the
    model having changed."""
    kwargs = dict(n_agents=125, alpha=0.15, mu=0.025, delta=0.025, lambda_=100, n_steps=2000, seed=7)
    check("fast method, symmetric flow",
          run_fingerprint(run_simulation(method="fast", **kwargs)) == (6354, 999958.0, 1191216, "a389d34531df7fca"))
    check("per-agent method, symmetric flow",
          run_fingerprint(run_simulation(method="agents", **kwargs)) == (6289, 999953.0, 1198539, "11703c537bb45397"))
    walk = MeanRevertingWalk()
    eq4 = run_simulation(taker_flow=walk, depth_coupling=10, q_rms=walk.stationary_rms, **kwargs)
    check("mean-reverting walk with Eq. 4", run_fingerprint(eq4) == (6101, 1000114.5, 1194788, "72a6cd9711c108d4"))


SHOCK_KWARGS = dict(n_agents=125, alpha=0.15, mu=0.025, delta=0.025, lambda_=100, n_steps=600, seed=11)


def test_recording_the_sides_does_not_change_the_run():
    plain = run_simulation(**SHOCK_KWARGS)
    sides = run_simulation(record_sides=True, **SHOCK_KWARGS)
    check("same run with and without record_sides", run_fingerprint(plain) == run_fingerprint(sides))
    check("off by default: the side series are empty", len(plain.best_bid_series) == 0 and len(plain.n_bids_series) == 0)
    check("one entry per step", len(sides.best_bid_series) == 600 and len(sides.n_asks_series) == 600)
    check("bids + asks = total orders, every step",
          np.array_equal(sides.n_bids_series + sides.n_asks_series, np.array(sides.total_orders_series)))
    check("the final counts match the final book, counted side by side",
          sides.n_bids_series[-1] == len(sides.book.resting_order_ids(Side.BID))
          and sides.n_asks_series[-1] == len(sides.book.resting_order_ids(Side.ASK)))
    check("with unit orders, the units on each side equal the orders on it, every step",
          np.array_equal(sides.bid_volume_series, sides.n_bids_series)
          and np.array_equal(sides.ask_volume_series, sides.n_asks_series))
    mids = np.array(sides.mid_price_series, dtype=float)
    check("midpoint = (best bid + best ask) / 2, every step",
          np.array_equal((sides.best_bid_series + sides.best_ask_series) / 2, mids))
    check("the final entries describe the final book",
          sides.best_bid_series[-1] == sides.book.best_bid() and sides.best_ask_series[-1] == sides.book.best_ask())


def test_sell_shock_removes_exactly_its_size_from_the_bids():
    step, size = 400, 60
    plain = run_simulation(record_sides=True, **SHOCK_KWARGS)
    hit = run_simulation(record_sides=True, shock=Shock(step=step, size=size), **SHOCK_KWARGS)
    check("identical up to the step before the shock",
          plain.mid_price_series[:step] == hit.mid_price_series[:step]
          and np.array_equal(plain.n_bids_series[:step], hit.n_bids_series[:step]))
    check(f"at the shock step the bid side holds exactly {size} fewer orders",
          plain.n_bids_series[step] - hit.n_bids_series[step] == size)
    check("the ask side is untouched at the shock step", plain.n_asks_series[step] == hit.n_asks_series[step]
          and plain.best_ask_series[step] == hit.best_ask_series[step])
    check("the best bid, and so the midpoint, falls", hit.best_bid_series[step] < plain.best_bid_series[step]
          and hit.mid_price_series[step] < plain.mid_price_series[step])
    shock_trades = [tr for tr in hit.book.trades if tr.aggressor_agent_id == SHOCK_AGENT_ID]
    check(f"the shock made exactly {size} trades, all sells, all in the shock step",
          len(shock_trades) == size and all(tr.aggressor_side is Side.ASK for tr in shock_trades)
          and len({tr.timestamp for tr in shock_trades}) == 1)
    check("each of its trades is against a one-unit resting order, so each is for 1 unit",
          all(tr.quantity == 1 for tr in shock_trades))
    prices = [tr.price for tr in shock_trades]
    check("it worked down through the bids: each trade at the same or a lower price", prices == sorted(prices, reverse=True))
    check("fully filled", hit.shock_unfilled == 0 and plain.shock_unfilled == 0)


def test_buy_shock_is_the_mirror_image():
    step, size = 400, 60
    plain = run_simulation(record_sides=True, **SHOCK_KWARGS)
    hit = run_simulation(record_sides=True, shock=Shock(step=step, size=size, side=Side.BID), **SHOCK_KWARGS)
    check(f"the ask side holds exactly {size} fewer orders", plain.n_asks_series[step] - hit.n_asks_series[step] == size)
    check("the bid side is untouched", plain.n_bids_series[step] == hit.n_bids_series[step])
    check("the midpoint rises", hit.mid_price_series[step] > plain.mid_price_series[step])


def test_shock_larger_than_the_book_side_empties_it():
    step = 400
    plain = run_simulation(record_sides=True, **SHOCK_KWARGS)
    bids_before = int(plain.n_bids_series[step])
    hit = run_simulation(record_sides=True, shock=Shock(step=step, size=bids_before + 25), **SHOCK_KWARGS)
    check("the bid side is empty at the shock step", hit.n_bids_series[step] == 0 and np.isnan(hit.best_bid_series[step]))
    check("with no bids there is no midpoint", hit.mid_price_series[step] is None)
    check("the 25 orders that found no buyer are reported", hit.shock_unfilled == 25)


def test_shock_parameters_are_validated():
    check("shock before the first step rejected", raises_value_error(
        lambda: run_simulation(shock=Shock(step=-1, size=5), **SHOCK_KWARGS)))
    check("shock after the last step rejected", raises_value_error(
        lambda: run_simulation(shock=Shock(step=600, size=5), **SHOCK_KWARGS)))
    check("shock of size 0 rejected", raises_value_error(
        lambda: run_simulation(shock=Shock(step=10, size=0), **SHOCK_KWARGS)))

# Faster dynamics than the paper's parameters (as in the Eq. 2 tests above), so a short run settles.
MIX_KWARGS = dict(n_agents=250, alpha=0.3, mu=0.1, delta=0.2, lambda_=100, n_steps=3000)
MIX_EQ2_VOLUME = eq2_equilibrium_orders(250, 0.3, 0.1, 0.2)      # 175 units
MIX_TRADED_PER_STEP = 250 * 0.1                                  # mu * N_A = 25 units


def settled_volume(result):
    """Mean resting units over the second half of a run (needs record_sides=True)."""
    volume = result.bid_volume_series + result.ask_volume_series
    return float(np.mean(volume[len(volume) // 2:]))


def test_the_default_mix_is_the_papers_population():
    kwargs = dict(n_agents=125, alpha=0.15, mu=0.025, delta=0.025, lambda_=100, n_steps=1000, seed=3)
    for method in ("fast", "agents"):
        plain = run_simulation(method=method, **kwargs)
        explicit = run_simulation(method=method, provider_mix={AgentType(1, 1): 125},
                                  taker_mix={AgentType(1, 1): 125}, **kwargs)
        check(f"{method}: writing the default mix out gives the identical run",
              run_fingerprint(plain) == run_fingerprint(explicit))


def test_mix_must_add_up_to_the_number_of_agents():
    kwargs = dict(n_agents=100, alpha=0.15, mu=0.025, delta=0.025, lambda_=100, n_steps=10)
    check("too few providers rejected", raises_value_error(
        lambda: run_simulation(provider_mix={AgentType(1, 1): 60, AgentType(4, 4): 30}, **kwargs)))
    check("too many takers rejected", raises_value_error(
        lambda: run_simulation(taker_mix={AgentType(2, 2): 101}, **kwargs)))
    check("a negative count rejected", raises_value_error(
        lambda: run_simulation(provider_mix={AgentType(1, 1): 110, AgentType(4, 4): -10}, **kwargs)))
    ok = run_simulation(provider_mix={AgentType(1, 1): 60, AgentType(4, 4): 40, AgentType(2, 2): 0}, **kwargs)
    check("a mix that adds up runs (a type with 0 agents is ignored)", len(ok.mid_price_series) == 10)


def test_slow_agents_are_spread_evenly_over_the_steps():
    class Stub:
        def __init__(self, interval, offset):
            self.interval, self.size, self.offset = interval, interval, offset
    agents = [Stub(4, i % 4) for i in range(10)] + [Stub(1, 0) for _ in range(3)]
    fours, ones = _turn_lists(agents)
    check("one list per step of the cycle", len(fours) == 4 and len(ones) == 1)
    check("10 agents over 4 steps: 3, 2, 2, 3 (never more than one apart)", [len(x) for x in fours] == [3, 2, 2, 3])
    check("every agent is on exactly one list", sorted(i for x in fours for i in x) == list(range(10)))
    check("each list holds the agents whose turn that step is",
          all(is_turn(t, 4, agents[i].offset) for t in range(4) for i in fours[t]))
    check("an every-step type has all its agents on its one list", ones == [[10, 11, 12]])


def test_every_provider_type_supplies_the_same_volume():
    """1 unit every step, 2 every 2 steps, 4 every 4 steps: the same units per step on average,
    so the book settles at the same volume (Eq. 2, counted in units)."""
    volumes, orders = {}, {}
    for k in (1, 2, 4):
        r = run_simulation(provider_mix={AgentType(k, k): 250}, record_sides=True, seed=20 + k, **MIX_KWARGS)
        volumes[k] = settled_volume(r)
        orders[k] = float(np.mean(r.total_orders_series[1500:]))
        check(f"providers of type {k}: settled volume {volumes[k]:.1f} within 4% of Eq. 2's {MIX_EQ2_VOLUME:.0f}",
              abs(volumes[k] - MIX_EQ2_VOLUME) < 0.04 * MIX_EQ2_VOLUME)
        check(f"providers of type {k}: no market order went unfilled", r.n_match_failures == 0)
    check("with unit orders, orders = units", abs(orders[1] - volumes[1]) < 1e-9)
    check(f"bigger orders mean fewer of them for the same volume ({orders[1]:.0f} > {orders[2]:.0f} > {orders[4]:.0f})",
          orders[1] > orders[2] > orders[4])


def test_every_taker_type_removes_the_same_volume():
    for k in (1, 2, 4):
        r = run_simulation(taker_mix={AgentType(k, k): 250}, record_sides=True, seed=30 + k, **MIX_KWARGS)
        per_step = r.book.volume_traded / MIX_KWARGS["n_steps"]
        check(f"takers of type {k}: {per_step:.2f} units traded per step, within 3% of mu*N_A = {MIX_TRADED_PER_STEP:.0f}",
              abs(per_step - MIX_TRADED_PER_STEP) < 0.03 * MIX_TRADED_PER_STEP)
        volume = settled_volume(r)
        check(f"takers of type {k}: settled volume {volume:.1f} within 4% of Eq. 2's {MIX_EQ2_VOLUME:.0f}",
              abs(volume - MIX_EQ2_VOLUME) < 0.04 * MIX_EQ2_VOLUME)


def test_a_mixed_population_settles_at_the_same_volume():
    mix = {AgentType(1, 1): 100, AgentType(2, 2): 100, AgentType(4, 4): 50}
    r = run_simulation(provider_mix=mix, taker_mix=mix, record_sides=True, seed=41, **MIX_KWARGS)
    volume = settled_volume(r)
    check(f"mixed providers and takers: settled volume {volume:.1f} within 4% of Eq. 2's {MIX_EQ2_VOLUME:.0f}",
          abs(volume - MIX_EQ2_VOLUME) < 0.04 * MIX_EQ2_VOLUME)
    per_step = r.book.volume_traded / MIX_KWARGS["n_steps"]
    check(f"and {per_step:.2f} units traded per step, within 3% of {MIX_TRADED_PER_STEP:.0f}",
          abs(per_step - MIX_TRADED_PER_STEP) < 0.03 * MIX_TRADED_PER_STEP)


def test_fast_and_per_agent_methods_agree_for_a_mixed_population():
    mix = {AgentType(1, 1): 100, AgentType(2, 2): 100, AgentType(4, 4): 50}
    stats = {}
    for method in ("fast", "agents"):
        volumes, traded = [], []
        for seed in range(6):
            r = run_simulation(provider_mix=mix, taker_mix=mix, record_sides=True, method=method, seed=seed,
                               **{**MIX_KWARGS, "n_steps": 1500})
            volumes.append(settled_volume(r))
            traded.append(r.book.volume_traded / 1500)
        stats[method] = (float(np.mean(volumes)), float(np.mean(traded)))
    (v_fast, t_fast), (v_agents, t_agents) = stats["fast"], stats["agents"]
    check(f"settled volume: fast {v_fast:.1f} vs per-agent {v_agents:.1f}, within 2%", abs(v_fast - v_agents) < 0.02 * v_agents)
    check(f"units traded per step: fast {t_fast:.2f} vs per-agent {t_agents:.2f}, within 2%",
          abs(t_fast - t_agents) < 0.02 * t_agents)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
