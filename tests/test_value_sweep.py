"""
Tests for the value trader sweep (experiments/value_sweep.py). Run with:
python -m tests.test_value_sweep   (from the project root)

Two combinations are run at a tiny scale, then collected, to check the whole chain works. Whether
the numbers mean anything is for the full-size runs.
"""

import contextlib
import io
import tempfile
from pathlib import Path

from experiments import value_sweep


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


def test_grid_has_a_control_and_every_combination_once():
    check("49 entries: the control and 4 x 4 x 3 combinations", len(value_sweep.GRID) == 49)
    check("entry 0 is the control, with no value traders", value_sweep.GRID[0][0] == 0 and value_sweep.name_of(0) == "control")
    check("every combination appears exactly once", len(set(value_sweep.GRID[1:])) == 48)
    names = [value_sweep.name_of(i) for i in range(49)]
    check("every combination has its own file name", len(set(names)) == 49)
    check("names say the settings", value_sweep.name_of(1) == "f0.02_news0.25_s50")
    check("shares become whole numbers of the shock test's 250 agents",
          [value_sweep.shock_traders(f) for f in value_sweep.FRACTIONS] == [5, 12, 25, 50])


def test_list_shows_every_combination():
    text, error = quietly(value_sweep.main, ["list"])
    check("49 lines, numbered 0 to 48", error is None and len(text.strip().splitlines()) == 49 and "48  " in text)


def test_bad_index_is_refused():
    _, error = quietly(value_sweep.main, ["run", "--index", "49", "--workers", "1"])
    check("index 49 does not exist", error is not None)


def test_run_and_collect_end_to_end():
    with tempfile.TemporaryDirectory() as tmp:
        tiny = ["--n-steps", "3000", "--n-runs", "1", "--shock-runs", "2", "--shock-after", "300",
                "--workers", "2", "--out-dir", tmp]
        _, error = quietly(value_sweep.main, ["collect", "--out-dir", tmp])
        check("collect with nothing finished says so", error is not None and "No finished" in error)

        for index in (0, 23):
            _, error = quietly(value_sweep.main, ["run", "--index", str(index), *tiny])
            check(f"combination {index} runs", error is None)
        files = sorted(p.name for p in Path(tmp).iterdir())
        name = value_sweep.name_of(23)
        check("each combination leaves a shock result and a normal-times result",
              {"shock_control.pkl", "normal_control.pkl", f"shock_{name}.pkl", f"normal_{name}.pkl"} <= set(files))

        _, error = quietly(value_sweep.main, ["run", "--index", "23", *tiny])
        check("running a finished combination again is harmless", error is None)

        text, error = quietly(value_sweep.main, ["collect", "--out-dir", tmp])
        check("collect works on a partly finished sweep", error is None)
        check("it lists the 47 combinations still missing", "47 of 49 combinations have not finished" in text)
        check("and has a row for each finished one", "control " in text and name in text)
        check("it writes a table and a figure",
              (Path(tmp) / "summary.csv").exists() and (Path(tmp) / "summary.png").exists())
        rows = (Path(tmp) / "summary.csv").read_text().strip().splitlines()
        check("the table has a header and two rows", len(rows) == 3)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
