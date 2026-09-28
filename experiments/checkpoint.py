"""
Save experiment results one run at a time, so that a crash, sleep or power cut doesn't lose
hours of work.

Layout: for a results file `results/x.pkl`, finished runs are written to `results/x.pkl.parts/`,
one small file per run, plus `meta.pkl` holding the settings the runs were made with. When the
experiment completes, the runner combines the parts into `x.pkl` and removes the folder.

Every write goes to a temporary file first and is then renamed into place, so a file is either
complete or absent, never half-written.
"""

from __future__ import annotations

import os
import pickle
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

import numpy as np

META = "meta.pkl"


def atomic_pickle(obj: Any, path: Path) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        pickle.dump(obj, f)
    os.replace(tmp, path)


def parts_dir_for(out: Path) -> Path:
    return out.with_name(out.name + ".parts")


def has_parts(parts_dir: Path) -> bool:
    """True if an earlier (unfinished) run left files behind."""
    return parts_dir.is_dir() and any(parts_dir.glob("*.pkl"))


def save_meta(parts_dir: Path, config: dict) -> None:
    parts_dir.mkdir(parents=True, exist_ok=True)
    atomic_pickle(config, parts_dir / META)


def load_meta(parts_dir: Path) -> dict:
    with open(parts_dir / META, "rb") as f:
        return pickle.load(f)


def save_part(parts_dir: Path, key: Tuple, run: dict) -> None:
    name = "run_" + "_".join(str(k) for k in key) + ".pkl"
    atomic_pickle((key, run), parts_dir / name)


def load_parts(parts_dir: Path) -> Dict[Tuple, dict]:
    """All readable saved runs, keyed by the key they were saved under. An unreadable file
    (which the atomic write should make impossible, but disks fail) is skipped with a warning,
    so that run simply gets redone."""
    runs = {}
    for path in sorted(parts_dir.glob("run_*.pkl")):
        try:
            with open(path, "rb") as f:
                key, run = pickle.load(f)
        except Exception as error:
            print(f"WARNING: could not read {path.name} ({error}); that run will be redone.")
            continue
        runs[tuple(key)] = run
    return runs


def _equal(a: Any, b: Any) -> bool:
    """Equality that also works for dicts that may contain numpy arrays (nested, e.g. one array
    of bin edges per price definition), where plain == either raises or is wrong for arrays."""
    if isinstance(a, dict) or isinstance(b, dict):
        return isinstance(a, dict) and isinstance(b, dict) and a.keys() == b.keys() \
            and all(_equal(a[k], b[k]) for k in a)
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        return np.array_equal(a, b)
    return a == b


def check_compatible(saved: dict, current: dict, keys: Iterable[str], allow_code_change: bool = False) -> None:
    """Raise ValueError unless saved runs can be safely combined with new ones: the settings named
    in `keys` must match exactly, and the code version (git commit) must be the same unless
    allow_code_change is set. Deliberately not compared: the number of runs, so a finished
    experiment can be extended with more seeds."""
    for key in keys:
        a, b = saved.get(key), current.get(key)
        if not _equal(a, b):
            raise ValueError(f"Cannot resume: setting {key!r} differs from the saved runs "
                             f"(saved {a!r}, now {b!r}). Mixing them would make the results meaningless.")
    saved_commit = (saved.get("git") or {}).get("commit")
    current_commit = (current.get("git") or {}).get("commit")
    if saved_commit and current_commit and saved_commit != current_commit and not allow_code_change:
        raise ValueError(f"Cannot resume: the code is at commit {current_commit[:7]} but the saved runs were made "
                         f"at {saved_commit[:7]}. If the difference doesn't affect the simulation "
                         f"(e.g. only docs changed), add --allow-code-change.")
