"""
Tests for the event study (analysis/events.py and experiments/news.py). Run with:
python -m tests.test_events   (from the project root)
"""

import contextlib
import io
import pickle
import tempfile
from pathlib import Path

import numpy as np

from analysis.events import clean_events, signed_window
from experiments import news, pressure


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    assert condition, f"FAILED: {label}"


def test_only_events_alone_in_a_full_window_are_kept():
    steps = [50, 300, 1000, 1100, 2000, 2950]
    keep = clean_events(steps, n_steps=3000, before=100, after=200, start=0)
    check("too close to the start: dropped", not keep[0])
    check("on its own: kept", keep[1] and keep[4])
    check("two events inside each other's windows: both dropped", not keep[2] and not keep[3])
    check("too close to the end: dropped", not keep[5])
    check("nothing used before the start step",
          not clean_events([300], n_steps=3000, before=100, after=200, start=500)[0])
    check("no events: nothing to keep", len(clean_events([], 3000, 100, 200)) == 0)


def test_windows_are_flipped_to_point_the_way_of_the_event():
    series = np.concatenate([np.full(100, 10.0), np.full(101, 40.0)])     # a rise of 30 at step 100
    up = signed_window(series, 100, 30.0, before=50, after=100)
    down = signed_window(-series, 100, -30.0, before=50, after=100)
    check("a change from the level before: 0 before, +30 after", np.all(up[:50] == 0) and np.all(up[50:] == 30))
    check("a fall after a downward event looks the same", np.array_equal(up, down))
    against = signed_window(series, 100, -5.0, before=50, after=100)
    check("a rise after a downward event shows as negative, whatever the event's size", np.all(against[50:] == -30))


def test_news_event_study_end_to_end():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "news.pkl"
        with contextlib.redirect_stdout(io.StringIO()):
            news.main(["run", "--n-runs", "2", "--n-steps", "12000", "--news-chance", "0.0005", "--after", "1000",
                       "--workers", "2", "--out", str(out)])
        with open(out, "rb") as f:
            data = pickle.load(f)
        check(f"{data['n_used']} of {data['n_jumps']} jumps used", 0 < data["n_used"] <= data["n_jumps"])
        check("one value per step of the window", all(len(m) == 200 + 1 + 1000 for m in data["means"].values()))
        gap = data["means"]["gap"]
        check(f"the gap falls by {gap[200] - gap[199]:.2f} at step 0, close to 1: the value has jumped, the price "
              f"not yet", -1.2 < gap[200] - gap[199] < -0.8)
        s = news.summary(data)
        check("the summary reads numbers off the curves", isinstance(s["end"], float) and s["peak at"] >= 0)
        figure = Path(tmp) / "compare.png"
        with contextlib.redirect_stdout(io.StringIO()):
            news.main(["plot", "--data", str(out), str(out), "--labels", "a", "b", "--out", str(figure)])
        check("plot draws saved files together", figure.exists())


def test_poisson_event_study_end_to_end():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "pressure.pkl"
        with contextlib.redirect_stdout(io.StringIO()):
            pressure.main(["run", "--n-runs", "2", "--n-steps", "15000", "--poisson-chance", "0.0005",
                           "--poisson-rate", "0.15", "--after", "1000", "--workers", "2", "--out", str(out)])
        with open(out, "rb") as f:
            data = pickle.load(f)
        check(f"{data['n_used']} of {data['n_orders']} orders used", 0 < data["n_used"] <= data["n_orders"])
        check("one size and one impact per order used",
              len(data["sizes"]) == len(data["impacts"]) == data["n_used"] and np.isfinite(data["impacts"]).all())
        check("the size bands hold every order once, and 'all' holds them together",
              sum(b["n"] for name, b in data["bands"].items() if name != "all") == data["n_used"]
              == data["bands"]["all"]["n"])
        check("every order, shown as a sell, makes the price fall on average",
              all(b["mean"][200] < b["mean"][150] for b in data["bands"].values()))
        figure = Path(tmp) / "compare.png"
        with contextlib.redirect_stdout(io.StringIO()):
            pressure.main(["plot", "--data", str(out), str(out), "--labels", "a", "b", "--out", str(figure)])
        check("plot draws saved files, one row each", figure.exists())


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
