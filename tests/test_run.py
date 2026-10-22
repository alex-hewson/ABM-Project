"""
Tests for the experiment runner (experiments/run.py): the return-distribution bin edges, the
order-flow option and the Eq. 4 entry depth. Run with: python -m tests.test_run   (from the project root)

The bin-edge bug these guard against: edges built for the wrong grid spacing leave alternating bins
empty, which showed up as a zigzag in the plotted |increment| distribution for the trade-price
definitions (docs/decisions.md, D15).
"""

import numpy as np

from abm.agents import AgentType
from experiments.run import split_into_types
from experiments.run import (make_bin_edges, make_flow, describe_flow, make_config, run_one,
                             RETURN_BIN_EDGES, PRICE_DEFINITIONS, FLOWS)
from abm.buy_probability import BoundedRandomWalk, MeanRevertingWalk


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


# ---- bin edges ------------------------------------------------------------------------------------

def grid_points_per_bin(edges, grid_step):
    """Number of multiples of grid_step inside each [edges[i], edges[i+1]) bin."""
    grid = np.arange(0, edges[-1] + grid_step, grid_step)
    grid = grid[grid > 0]      # zero increments are deliberately excluded, not a gap
    counts = np.histogram(grid, bins=edges)[0]
    return counts


def test_edges_at_the_matching_grid_spacing_have_no_empty_bins():
    for grid_step in (0.5, 1.0, 2.0):
        edges = make_bin_edges(grid_step, min_ticks=1.0, max_ticks=200.0, n_points=30)
        counts = grid_points_per_bin(edges, grid_step)
        check(f"grid_step={grid_step}: every bin catches at least one grid point (no zigzag)",
              np.all(counts >= 1))


def test_wrong_grid_spacing_does_produce_empty_bins():
    """Confirms the test above would actually have caught the original bug."""
    edges_for_half_tick_grid = make_bin_edges(0.5, min_ticks=1.0, max_ticks=200.0, n_points=30)
    counts = grid_points_per_bin(edges_for_half_tick_grid, grid_step=1.0)   # applied to an integer series
    check("mismatched grid: at least one empty bin (the original bug)", np.any(counts == 0))


def test_edges_are_positive_increasing_and_exclude_zero():
    for grid_step in (0.5, 1.0):
        edges = make_bin_edges(grid_step)
        check(f"grid_step={grid_step}: strictly increasing", np.all(np.diff(edges) > 0))
        check(f"grid_step={grid_step}: zero increments fall outside every bin", edges[0] > 0)


def test_every_price_definition_has_edges_on_the_right_grid():
    check("all price definitions have edges", set(RETURN_BIN_EDGES) == set(PRICE_DEFINITIONS))
    mid_edges = RETURN_BIN_EDGES["mid"]
    check("'mid' uses the 0.5-tick grid (edges are odd multiples of 0.25)",
          np.allclose((mid_edges * 4) % 2, 1))
    for name in ("last", "first", "median", "mean"):
        edges = RETURN_BIN_EDGES[name]
        check(f"'{name}' uses the 1-tick grid (edges are half-integers)", np.allclose((edges * 2) % 2, 1))


# ---- order flow -----------------------------------------------------------------------------------

def test_make_flow_builds_the_right_process_fresh_each_time():
    check("symmetric: no process", make_flow("symmetric") is None)
    check("bounded: a BoundedRandomWalk", isinstance(make_flow("bounded"), BoundedRandomWalk))
    check("mean-reverting: a MeanRevertingWalk", isinstance(make_flow("mean-reverting"), MeanRevertingWalk))
    a, b = make_flow("bounded"), make_flow("bounded")
    check("each call gives a new object, starting at q = 1/2", a is not b and a.q == b.q == 0.5)
    check("unknown flow rejected", raises_value_error(make_flow, "sideways"))
    check("the command-line choices are exactly the known flows",
          set(FLOWS) == {"symmetric", "bounded", "mean-reverting"})


def test_flow_settings_are_recorded_in_the_config():
    check("symmetric: flow is None (so older Fig. 2 files, which have no flow entry, stay compatible)",
          make_config(1000, {}, "symmetric")["flow"] is None and describe_flow("symmetric") is None)
    bounded = make_config(1000, {}, "bounded")["flow"]
    check("bounded: name and the paper's parameters recorded",
          bounded["name"] == "bounded" and bounded["step"] == 0.001
          and abs(bounded["half_width"] - 0.05) < 1e-12 and bounded["centre"] == 0.5)
    check("mean-reverting: half-width 1/2", abs(describe_flow("mean-reverting")["half_width"] - 0.5) < 1e-12)


def test_run_one_with_a_flow_records_q_statistics():
    r = run_one((125, 0, 3_000, "bounded", 0.0))
    q = r["q_stats"]
    check("q statistics present", q is not None and set(q) == {"mean_sq_dev", "std", "min", "max"})
    check(f"q stayed within the bounded walk's range [{q['min']:.3f}, {q['max']:.3f}]",
          q["min"] >= 0.45 - 1e-9 and q["max"] <= 0.55 + 1e-9)
    check("<(q - 1/2)^2> is at least the variance (it adds the squared mean offset)",
          q["mean_sq_dev"] >= q["std"] ** 2 - 1e-12)
    check("symmetric flow: no q statistics", run_one((125, 0, 3_000, "symmetric", 0.0))["q_stats"] is None)


def test_repeated_runs_are_identical_so_no_state_leaks_between_runs():
    """If a flow object were reused between runs, the second run would start where the first ended."""
    job = (125, 3, 3_000, "mean-reverting", 10.0)
    a, b = run_one(job), run_one(job)
    check("same job twice: identical RMS values, q and lambda statistics",
          all(np.array_equal(a["rms"][p], b["rms"][p]) for p in PRICE_DEFINITIONS)
          and a["q_stats"] == b["q_stats"] and a["lambda_stats"] == b["lambda_stats"])


# ---- Eq. 4 entry depth (Fig. 4) -------------------------------------------------------------------

def test_entry_depth_settings_are_recorded_in_the_config():
    check("no coupling: entry_depth is None (so older results files stay compatible)",
          make_config(1000, {}, "mean-reverting", 0.0)["entry_depth"] is None)
    depth = make_config(1000, {}, "mean-reverting", 10)["entry_depth"]
    check("C_lambda, lambda_0 and sqrt(<(q - 1/2)^2>) = sqrt(step/4) recorded",
          depth["c_lambda"] == 10 and depth["lambda_0"] == 100 and abs(depth["q_rms"] - (0.001 / 4) ** 0.5) < 1e-15)


def test_run_one_with_eq4_records_lambda_statistics():
    r = run_one((125, 0, 3_000, "mean-reverting", 10.0))
    lam = r["lambda_stats"]
    check(f"lambda statistics present (mean {lam['mean']:.0f}, max {lam['max']:.0f})",
          lam is not None and 100 <= lam["mean"] <= lam["max"])
    check("without Eq. 4: no lambda statistics", run_one((125, 0, 3_000, "mean-reverting", 0.0))["lambda_stats"] is None)


def test_depth_coupling_needs_the_mean_reverting_flow():
    import contextlib, io, tempfile
    from pathlib import Path
    from experiments import run
    with tempfile.TemporaryDirectory() as tmp:
        for flow in ("symmetric", "bounded"):
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    run.main(["--flow", flow, "--depth-coupling", "10", "--n-steps", "2000", "--n-runs", "1",
                              "--out", str(Path(tmp) / "x.pkl")])
                message = None
            except SystemExit as e:
                message = str(e)
            check(f"--depth-coupling with --flow {flow} is refused", message is not None and "mean-reverting" in message)
        check("and nothing was started", not any(Path(tmp).iterdir()))


def test_bins_reach_far_enough_and_overflow_is_counted():
    check("bins reach 50,000 ticks for every price definition (paper's Fig. 4b goes to +-4,000)",
          all(edges[-1] >= 49_999 for edges in RETURN_BIN_EDGES.values()))
    r = run_one((125, 0, 3_000, "symmetric", 0.0))
    check("an overflow count is stored for every price definition and lag",
          set(r["return_overflow"]) == set(PRICE_DEFINITIONS)
          and all(set(v) == set(r["return_counts"][p]) for p, v in r["return_overflow"].items()))
    check("and nothing overflows in a normal run", all(n == 0 for v in r["return_overflow"].values() for n in v.values()))


def test_value_trader_settings_are_recorded_in_the_config():
    check("no value traders: recorded as None, as in files made before they existed",
          make_config(1000, {})["value_traders"] is None)
    check("with value traders: their share, true value step and spread are recorded",
          make_config(1000, {}, value=(0.2, 1.5, 30.0))["value_traders"]
          == {"fraction": 0.2, "true_value_step": 1.5, "spread": 30.0})


def same_run(a, b):
    return all(np.array_equal(a["rms"][name], b["rms"][name]) for name in PRICE_DEFINITIONS) and a["n_trades"] == b["n_trades"]


def test_run_one_with_value_traders():
    plain = run_one((125, 0, 3_000, "symmetric", 0.0))
    spelled_out = run_one((125, 0, 3_000, "symmetric", 0.0, (0.0, 7.7, 5.0)))
    with_traders = run_one((125, 0, 3_000, "symmetric", 0.0, (0.4, 1.0, 30.0)))
    check("a job without the value trader settings means none of them", same_run(plain, spelled_out))
    check("with 40% value traders the run is a different one", not same_run(plain, with_traders))
    check("and no market order went unfilled", with_traders["n_match_failures"] == 0)


def test_autocorrelations_are_stored_for_every_price_definition():
    r = run_one((125, 0, 3_000, "symmetric", 0.0))
    check("one entry per price definition", set(r["autocorr"]) == set(PRICE_DEFINITIONS))
    # 3,000 steps = 60 intervals of 50 steps; lags go up to a quarter of that
    check("signed and absolute, 15 lags each for a 3,000-step run",
          all(len(v["signed"]) == 15 and len(v["absolute"]) == 15 for v in r["autocorr"].values()))
    check("every value is a correlation, between -1 and 1",
          all(np.all(np.abs(v[kind]) <= 1) for v in r["autocorr"].values() for kind in ("signed", "absolute")))
    tiny = run_one((125, 0, 150, "symmetric", 0.0))
    check("a run too short for even one lag stores none, without failing", tiny["autocorr"] == {})


def test_agents_are_split_equally_between_the_types_listed():
    check("no types: the paper's agents", split_into_types((), 500) is None and split_into_types(None, 500) is None)
    check("one type: every agent", split_into_types((4,), 500) == {AgentType(4, 4): 500})
    check("three types share 500 as 167, 167, 166",
          split_into_types((1, 2, 4), 500) == {AgentType(1, 1): 167, AgentType(2, 2): 167, AgentType(4, 4): 166})
    check("agent types are recorded in the config, None when not used",
          make_config(1000, {})["agent_types"] is None
          and make_config(1000, {}, types=((), (4,)))["agent_types"] == {"providers": [1], "takers": [4]})


def test_run_one_with_agent_types():
    plain = run_one((125, 0, 3_000, "symmetric", 0.0))
    spelled_out = run_one((125, 0, 3_000, "symmetric", 0.0, (0.0, 1.0, 50.0), ((1,), (1,))))
    lumpy = run_one((125, 0, 3_000, "symmetric", 0.0, (0.0, 1.0, 50.0), ((), (4,))))
    check("type 1 written out is the paper's population", same_run(plain, spelled_out))
    check("4-unit takers every 4 steps give a different run", not same_run(plain, lumpy))
    check("and every market order was filled", lumpy["n_match_failures"] == 0)
    mixed = run_one((125, 0, 3_000, "symmetric", 0.0, (0.4, 1.0, 50.0), ((2,), (4,))))
    check("agent types and value traders can be combined", mixed["n_match_failures"] == 0)


def test_run_one_with_momentum_traders():
    plain = run_one((125, 0, 3_000, "symmetric", 0.0))
    spelled_out = run_one((125, 0, 3_000, "symmetric", 0.0, (0.0, 1.0, 50.0), ((), ()), (0.0, (1,), 50, 1.0)))
    with_traders = run_one((125, 0, 3_000, "symmetric", 0.0, (0.0, 1.0, 50.0), ((), ()), (0.4, (1, 2), 50, 1.0)))
    check("no momentum traders written out is the plain run", same_run(plain, spelled_out))
    check("with 40% momentum traders the run is a different one", not same_run(plain, with_traders))
    check("their settings are recorded in the config, None when not used",
          make_config(1000, {})["momentum_traders"] is None
          and make_config(1000, {}, momentum=(0.2, (1, 2), 50, 1.0))["momentum_traders"]
          == {"fraction": 0.2, "orders": [1, 2], "window": 50, "scale": 1.0})


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
