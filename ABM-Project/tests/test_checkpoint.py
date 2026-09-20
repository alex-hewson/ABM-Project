"""
Tests for saving progress as an experiment runs, and resuming it.
Run with: python -m tests.test_checkpoint   (from the project root)

The end-to-end tests run the real Fig. 2 runner at a tiny scale (2,000 steps). To prove that
saved runs are *reused* and not silently recomputed, they overwrite a saved run's
`mean_orders` with an impossible marker value and check the marker survives to the final file.
"""

import contextlib
import io
import pickle
import tempfile
from pathlib import Path

import numpy as np

from experiments import fig2
from experiments.checkpoint import (atomic_pickle, parts_dir_for, has_parts, save_meta, save_part,
                                    load_parts, check_compatible)
from experiments.provenance import git_info

MARKER = -12345.0
STEPS = 2000


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    assert condition, f"FAILED: {label}"


def run_main(out, *extra, n_runs=1, n_steps=STEPS):
    """Run the fig2 runner in-process, returning (its printed output, SystemExit message or None)."""
    argv = ["--n-steps", str(n_steps), "--n-runs", str(n_runs), "--workers", "2", "--out", str(out), *extra]
    buffer = io.StringIO()
    exit_message = None
    with contextlib.redirect_stdout(buffer):
        try:
            fig2.main(argv)
        except SystemExit as e:
            exit_message = str(e)
    return buffer.getvalue(), exit_message


def load_final(out):
    with open(out, "rb") as f:
        return pickle.load(f)


# ---- unit tests ---------------------------------------------------------------------------------

def test_save_and_load_parts_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        parts = Path(tmp) / "x.pkl.parts"
        parts.mkdir()
        run = {"n_agents": 250, "seed": 3, "h": np.array([0.1, 0.2]), "note": "hello"}
        save_part(parts, (250, 3), run)
        loaded = load_parts(parts)
        leftovers = list(parts.glob("*.tmp"))
    check("one run comes back under its key", list(loaded) == [(250, 3)])
    check("contents preserved, including numpy arrays",
          loaded[(250, 3)]["note"] == "hello" and np.array_equal(loaded[(250, 3)]["h"], run["h"]))
    check("no temporary files left behind", leftovers == [])


def test_unreadable_part_is_skipped_with_a_warning():
    with tempfile.TemporaryDirectory() as tmp:
        parts = Path(tmp) / "x.pkl.parts"
        parts.mkdir()
        save_part(parts, (125, 0), {"n_agents": 125, "seed": 0})
        (parts / "run_125_1.pkl").write_bytes(b"this is not a pickle")
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            loaded = load_parts(parts)
    check("the good run is loaded, the corrupt one skipped", list(loaded) == [(125, 0)])
    check("a warning names the bad file", "run_125_1.pkl" in buffer.getvalue())


def test_has_parts():
    with tempfile.TemporaryDirectory() as tmp:
        parts = Path(tmp) / "x.pkl.parts"
        check("missing folder: False", has_parts(parts) is False)
        parts.mkdir()
        check("empty folder: False", has_parts(parts) is False)
        save_meta(parts, {"n_steps": 1})
        check("folder with files: True", has_parts(parts) is True)


def test_compatibility_rules():
    base = {"n_steps": 1000, "params": {"alpha": 0.15}, "edges": np.array([1.0, 2.0]), "git": {"commit": "a" * 40}}
    keys = ("n_steps", "params", "edges")

    check_compatible(base, dict(base, edges=np.array([1.0, 2.0])), keys)
    check("identical settings, including arrays, are compatible", True)

    def rejected(current, **kw):
        try:
            check_compatible(base, current, keys, **kw)
        except ValueError as e:
            return str(e)
        return None

    check("different n_steps rejected, message names the setting", "n_steps" in (rejected(dict(base, n_steps=2000)) or ""))
    check("different nested parameters rejected", rejected(dict(base, params={"alpha": 0.2})) is not None)
    check("different array rejected", rejected(dict(base, edges=np.array([1.0, 3.0]))) is not None)
    other_commit = dict(base, git={"commit": "b" * 40})
    check("different git commit rejected", rejected(other_commit) is not None)
    check("...unless explicitly allowed", rejected(other_commit, allow_code_change=True) is None)
    check("unknown commit (no git) is not an obstacle", rejected(dict(base, git={"commit": None})) is None)
    check("different number of runs is not compared", rejected(dict(base, n_runs=999)) is None)


# ---- end-to-end tests (real runner, tiny scale) ----------------------------------------------------

def test_resume_reuses_saved_runs_and_finishes():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "r.pkl"
        parts = parts_dir_for(out)
        # Simulate an interruption after one run finished.
        save_meta(parts, fig2.make_config(STEPS, git_info()))
        saved = fig2.run_one((125, 0, STEPS))
        saved["mean_orders"] = MARKER
        save_part(parts, (125, 0), saved)

        text, error = run_main(out, "--resume")
        final = load_final(out)
        parts_left = parts.exists()

    check("no error", error is None)
    check("reports 1 of 3 runs already saved", "resuming: 1 of 3 runs already saved, 2 to go" in text)
    check("only the 2 missing runs were simulated", text.count("done (") == 2)
    check("final file has all 3 runs", len(final["runs"]) == 3)
    reused = [r for r in final["runs"] if (r["n_agents"], r["seed"]) == (125, 0)][0]
    check("the saved run was reused, not recomputed (marker survived)", reused["mean_orders"] == MARKER)
    check("temporary folder removed after success", parts_left is False)


def test_refuses_to_overwrite_unfinished_run_without_resume():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "r.pkl"
        parts = parts_dir_for(out)
        save_meta(parts, fig2.make_config(STEPS, git_info()))
        save_part(parts, (125, 0), {"n_agents": 125, "seed": 0, "mean_orders": MARKER})
        text, error = run_main(out)
        still_there = has_parts(parts)
    check("refuses, and tells the user about --resume", error is not None and "--resume" in error)
    check("saved runs untouched", still_there)


def test_resume_refuses_when_settings_changed():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "r.pkl"
        parts = parts_dir_for(out)
        save_meta(parts, fig2.make_config(STEPS, git_info()))
        save_part(parts, (125, 0), {"n_agents": 125, "seed": 0, "mean_orders": MARKER})
        text, error = run_main(out, "--resume", n_steps=STEPS + 500)
    check("refuses, naming the setting that differs", error is not None and "n_steps" in error)


def test_extending_a_finished_experiment_reuses_its_runs():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "r.pkl"
        run_main(out, n_runs=1)
        first = load_final(out)
        first["runs"][0]["mean_orders"] = MARKER          # tag a run so we can see it survive
        tagged_key = (first["runs"][0]["n_agents"], first["runs"][0]["seed"])
        atomic_pickle(first, out)

        text, error = run_main(out, "--resume", n_runs=2)
        extended = load_final(out)

        dropping_text, dropping_error = run_main(out, "--resume", n_runs=1)
        after_refusal = load_final(out)

    check("no error", error is None)
    check("reports 3 of 6 runs already saved", "resuming: 3 of 6 runs already saved, 3 to go" in text)
    check("final file now has 6 runs", len(extended["runs"]) == 6 and extended["config"]["n_runs"] == 2)
    tagged = [r for r in extended["runs"] if (r["n_agents"], r["seed"]) == tagged_key][0]
    check("the earlier run was reused, not recomputed", tagged["mean_orders"] == MARKER)
    check("shrinking --n-runs is refused, not silently dropping runs",
          dropping_error is not None and "n-runs" in dropping_error)
    check("and the results file is left intact", len(after_refusal["runs"]) == 6)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
