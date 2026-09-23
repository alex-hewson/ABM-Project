"""
Tests for the Fig. 2 return-distribution bin edges.
Run with: python -m tests.test_fig2   (from the project root)

The bug these guard against: edges built for the wrong grid spacing leave alternating bins
empty, which showed up as a zigzag in the plotted |increment| distribution for the trade-price
definitions (docs/decisions.md, D15).
"""

import numpy as np

from experiments.fig2 import make_bin_edges, RETURN_BIN_EDGES, PRICE_DEFINITIONS


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    assert condition, f"FAILED: {label}"


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
    check("mismatched grid: at least one empty bin (this is the bug we're guarding against)",
          np.any(counts == 0))


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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
