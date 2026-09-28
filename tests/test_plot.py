"""
Smoke tests for the figure plotter (experiments/plot.py): tiny experiments are run for each flow,
then each figure is drawn from them. Checks that the figures are produced, and that files made with
the wrong flow are refused. Run with: python -m tests.test_plot   (from the project root)

These only check that plotting works end to end; whether the figures are *right* is judged by
looking at them against the paper.
"""

import contextlib
import io
import tempfile
from pathlib import Path

from experiments import run, plot

STEPS = 3_000       # just long enough for the largest return lag (1600) and a depth profile


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


def make_results(folder, flow):
    out = Path(folder) / f"{flow}.pkl"
    _, error = quietly(run.main, ["--flow", flow, "--n-steps", str(STEPS), "--n-runs", "1",
                                  "--workers", "3", "--out", str(out)])
    assert error is None, error
    return out


def test_both_figures_are_drawn_and_mismatched_files_refused():
    with tempfile.TemporaryDirectory() as tmp:
        symmetric = make_results(tmp, "symmetric")
        bounded = make_results(tmp, "bounded")
        reverting = make_results(tmp, "mean-reverting")

        fig2_png = Path(tmp) / "fig2.png"
        _, error = quietly(plot.main, ["fig2", "--data", str(symmetric), "--out", str(fig2_png)])
        check("fig2 drawn, plus the price-definition comparison",
              error is None and fig2_png.exists() and (Path(tmp) / "fig2_price_definitions.png").exists())

        fig3_png = Path(tmp) / "fig3.png"
        text, error = quietly(plot.main, ["fig3", "--bounded", str(bounded), "--mean-reverting", str(reverting),
                                          "--out", str(fig3_png)])
        check("fig3 drawn", error is None and fig3_png.exists())
        check("fig3 reports <(q - 1/2)^2> for both flows (needed for Eq. 4)",
              "bounded walk, N_A=500: <(q - 1/2)^2>" in text and "mean-reverting walk, N_A=500" in text)

        _, error = quietly(plot.main, ["fig3", "--bounded", str(reverting), "--mean-reverting", str(bounded),
                                       "--out", str(Path(tmp) / "wrong.png")])
        check("fig3 with the two files swapped is refused, naming the flow",
              error is not None and "flow" in error and not (Path(tmp) / "wrong.png").exists())

        _, error = quietly(plot.main, ["fig2", "--data", str(bounded), "--out", str(Path(tmp) / "wrong.png")])
        check("fig2 from a bounded-walk file is refused", error is not None and "flow" in error)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
