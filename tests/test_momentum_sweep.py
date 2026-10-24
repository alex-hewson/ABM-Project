"""
Tests for the momentum trader sweep (experiments/momentum_sweep.py). Run with:
python -m tests.test_momentum_sweep   (from the project root)

A few combinations are run at a tiny scale, then collected, to check the whole chain works. Whether
the numbers mean anything is for the full-size runs.
"""

import contextlib
import io
import tempfile
from pathlib import Path

from experiments import momentum_sweep as sweep


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


def test_grid_has_two_controls_and_every_combination_once():
    check("242 entries: 2 controls and 2 x 3 x 10 x 4 combinations", len(sweep.GRID) == 242)
    check("entries 0 and 1 are the controls, without and with value traders",
          sweep.name_of(0) == "control_noval" and sweep.name_of(1) == "control_val")
    check("every combination appears exactly once", len(set(sweep.GRID)) == 242)
    check("every combination has its own file name", len({sweep.name_of(i) for i in range(242)}) == 242)
    check("names say the settings", sweep.name_of(2) == "noval_s0.1_m1_w50")
    check("ten mixes, each order listed with its share",
          len(sweep.MIXES) == 10 and sweep.describe_mix((1, 1, 2)) == "2/3 order 1, 1/3 order 2"
          and sweep.describe_mix((3,)) == "only order 3" and sweep.describe_mix((1, 2, 3)) == "equal shares of orders 1, 2, 3")


def test_list_shows_every_combination():
    text, error = quietly(sweep.main, ["list"])
    check("242 lines", error is None and len(text.strip().splitlines()) == 242)


def test_run_and_collect_end_to_end():
    with tempfile.TemporaryDirectory() as tmp:
        tiny = ["--n-steps", "3000", "--n-runs", "1", "--shock-runs", "2", "--shock-after", "300",
                "--workers", "2", "--out-dir", tmp]
        momentum_with_value = next(i for i, g in enumerate(sweep.GRID) if g[0] and g[1] == 0.5 and g[2] == (1, 1, 2))
        for index in (0, 1, 5, momentum_with_value):
            _, error = quietly(sweep.main, ["run", "--index", str(index), *tiny])
            check(f"combination {index} ({sweep.name_of(index)}) runs", error is None)
        text, error = quietly(sweep.main, ["collect", "--out-dir", tmp])
        check("collect works on a partly finished sweep", error is None and "238 of 242" in text)
        check("it writes a table and the heatmap figures",
              (Path(tmp) / "summary.csv").exists() and (Path(tmp) / "summary_rms_noval.png").exists()
              and (Path(tmp) / "summary_half_life_val.png").exists())
        rows = (Path(tmp) / "summary.csv").read_text().strip().splitlines()
        check("the table has a header and four rows", len(rows) == 5)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
