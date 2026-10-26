"""
Tests for the phase diagram sweep (experiments/phase_sweep.py). Run with:
python -m tests.test_phase_sweep   (from the project root)

A few combinations are run at a tiny scale, then collected, to check the whole chain works. Whether
the numbers mean anything is for the full-size runs.
"""

import contextlib
import io
import tempfile
from pathlib import Path

from experiments import phase_sweep as sweep


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    assert condition, f"FAILED: {label}"


def quietly(fn, argv):
    """Call fn(argv), returning (printed output, SystemExit message or None)."""
    buffer = io.StringIO()
    exit_message = None
    with contextlib.redirect_stdout(buffer):
        try:
            fn(argv)
        except SystemExit as e:
            exit_message = str(e)
    return buffer.getvalue(), exit_message


def test_grid_has_every_point_that_fits_at_every_size():
    check("44 points: value + momentum at most 100%", len(sweep.POINTS) == 44
          and all(v + m <= 1 + 1e-9 for v, m in sweep.POINTS))
    check("176 combinations, each once", len(sweep.GRID) == 176 and len(set(sweep.GRID)) == 176)
    check("the largest N_A first", sweep.GRID[0][0] == 1000 and sweep.GRID[-1][0] == 125)
    check("every combination has its own file name", len({sweep.name_of(i) for i in range(176)}) == 176)
    text, error = quietly(sweep.main, ["list"])
    check("list shows 176 lines", error is None and len(text.strip().splitlines()) == 176)


def test_run_and_collect_end_to_end():
    with tempfile.TemporaryDirectory() as tmp:
        tiny = ["--n-steps", "3000", "--n-runs", "1", "--pressure-runs", "1", "--workers", "2", "--out-dir", tmp]
        both = sweep.GRID.index((125, 0.2, 0.4))
        for index in (sweep.GRID.index((125, 0.0, 0.0)), both):
            _, error = quietly(sweep.main, ["run", "--index", str(index), *tiny])
            check(f"combination {index} ({sweep.name_of(index)}) runs", error is None)
        text, error = quietly(sweep.main, ["run", "--index", str(both), *tiny])
        check("running it again skips the finished event studies", error is None and "already done" in text)
        text, error = quietly(sweep.main, ["collect", "--out-dir", tmp])
        check("collect works on a partly finished sweep", error is None and "2 of 176" in text)
        check("it writes a table, the autocorrelations and the heatmaps",
              (Path(tmp) / "summary.csv").exists() and (Path(tmp) / "autocorrelations.pkl").exists()
              and (Path(tmp) / "phase_order.png").exists())


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
