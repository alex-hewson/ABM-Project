"""
Event study: how a quantity behaves around events that happen at random times inside a long run
(news jumps now, large orders later), instead of one shock placed by hand.

Each event's window is cut out of the run with recovery.window(), and windows from many events are
averaged with recovery.mean_response(). Two things are needed first:

    clean_events()     which events can be used: a full window inside the run, and no other event
                       inside it, so each average shows one event at a time
    signed_window()    one event's window, flipped so that every event points the same way, so
                       events of both signs can be averaged

To put the average in units of the event, divide it by the mean event size afterwards. Dividing each
window by its own event's size instead would let a tiny event multiply its noise many times over.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from analysis.recovery import window


def clean_events(steps: Sequence[int], n_steps: int, before: int, after: int, start: int = 0) -> np.ndarray:
    """True for each event (at the given steps, in order) whose window, from `before` steps ahead to
    `after` steps past, lies inside the run, starts at or after `start` (e.g. to skip the steps
    while the market settles), and holds no other event."""
    steps = np.asarray(steps, dtype=int)
    keep = (steps - before >= start) & (steps + after < n_steps)
    gap_ahead = np.diff(steps, prepend=np.iinfo(int).min // 2)    # steps since the event before
    gap_past = np.diff(steps, append=np.iinfo(int).max // 2)      # steps until the next event
    return keep & (gap_ahead > before) & (gap_past > after)


def signed_window(series: Sequence[float], step: int, size: float, before: int, after: int) -> np.ndarray:
    """The window around one event, as a change from the mean of the `before` steps ahead of it,
    multiplied by the sign of the event (`size`). A move the same way as the event shows as positive."""
    if size == 0:
        raise ValueError("an event of size 0 has no direction")
    w = window(series, step, before, after)
    return (w - np.nanmean(w[:before])) * np.sign(size)
