"""
Tests for the experiment runner (experiments/run.py): the return-distribution bin edges, the
order-flow option and the Eq. 4 entry depth. Run with: python -m tests.test_run   (from the project root)

The bin-edge bug these guard against: edges built for the wrong grid spacing leave alternating bins
empty, which showed up as a zigzag in the plotted |increment| distribution for the trade-price
definitions (docs/decisions.md, D15).
"""

import numpy as np

from experiments.run import (make_bin_edges, make_flow, describe_flow, make_config, run_one,
                             RETURN_BIN_EDGES, PRICE_DEFINITIONS, FLOWS)
from abm.agents import BoundedRandomWalk, MeanRevertingWalk


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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
