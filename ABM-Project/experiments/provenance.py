"""
Record which version of the code produced a set of results.

A commit ID alone only identifies the code if nothing has been edited since that
commit, so "dirty" records whether the working folder had uncommitted changes
when the run started. If dirty is True, the results came from code that is not
exactly any commit.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, Optional, Union

REPO_ROOT = Path(__file__).resolve().parent.parent


def _git(repo_dir: Path, *args: str) -> Optional[str]:
    try:
        out = subprocess.run(["git", "-C", str(repo_dir), *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def git_info(repo_dir: Union[str, Path] = REPO_ROOT) -> Dict[str, Optional[Union[str, bool]]]:
    """{'commit': full hash, 'branch': name, 'dirty': bool}; all None if this isn't a git
    repository or git isn't available."""
    repo_dir = Path(repo_dir)
    commit = _git(repo_dir, "rev-parse", "HEAD")
    if commit is None:
        return {"commit": None, "branch": None, "dirty": None}
    status = _git(repo_dir, "status", "--porcelain")
    return {
        "commit": commit,
        "branch": _git(repo_dir, "rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": None if status is None else bool(status),
    }


def describe(info: Dict[str, Optional[Union[str, bool]]]) -> str:
    """One-line summary, e.g. 'a1b2c3d (speedup-loop) + uncommitted changes'."""
    if info["commit"] is None:
        return "commit unknown (not a git repository)"
    text = f"{str(info['commit'])[:7]} ({info['branch']})"
    if info["dirty"]:
        text += " + uncommitted changes"
    return text
