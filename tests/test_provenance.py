"""
Tests for recording the code version alongside results.
Run with: python -m tests.test_provenance   (from the project root)
"""

import subprocess
import tempfile
from pathlib import Path

from experiments.provenance import git_info, describe


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    assert condition, f"FAILED: {label}"


def test_project_repo_reports_commit_branch_and_dirty_flag():
    info = git_info()
    check("commit is a full 40-character hash", isinstance(info["commit"], str) and len(info["commit"]) == 40)
    check("branch name is recorded", bool(info["branch"]))
    check("dirty is a bool", isinstance(info["dirty"], bool))


def test_outside_a_repository_returns_none_without_raising():
    with tempfile.TemporaryDirectory() as tmp:
        info = git_info(tmp)
    check("all fields None outside a repository", info == {"commit": None, "branch": None, "dirty": None})
    check("describe still produces text", "unknown" in describe(info))


def test_dirty_flag_follows_uncommitted_changes():
    with tempfile.TemporaryDirectory() as tmp:
        def git(*args):
            subprocess.run(["git", "-C", tmp, "-c", "user.name=t", "-c", "user.email=t@t", *args],
                           check=True, capture_output=True)
        git("init")
        (Path(tmp) / "a.txt").write_text("one")
        git("add", "a.txt")
        git("commit", "-m", "first")
        clean = git_info(tmp)
        (Path(tmp) / "a.txt").write_text("two")
        dirty = git_info(tmp)
    check("clean repo: dirty is False", clean["dirty"] is False)
    check("edited file: dirty is True", dirty["dirty"] is True)
    check("commit is unchanged by the edit", clean["commit"] == dirty["commit"])
    check("describe flags uncommitted changes", "uncommitted" in describe(dirty) and "uncommitted" not in describe(clean))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
