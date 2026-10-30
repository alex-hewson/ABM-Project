"""
Tests for the E-mini data tools (experiments/emini.py), on a small made-up file in the same format.
Run with: python -m tests.test_emini   (from the project root)
"""

import contextlib
import io
import tempfile
from pathlib import Path

from experiments import emini


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    assert condition, f"FAILED: {label}"


HEADER = "#RIC,Domain,Date-Time,Type,Price,Volume,Bid Price,Bid Size,Ask Price,Ask Size"
ROWS = [
    "ESZ6,Market Price,2026-09-01T13:30:00.000000001Z,Quote,,,6500.00,40,6500.25,35",
    "ESZ6,Market Price,2026-09-01T13:30:00.100000000Z,Trade,6500.25,3,,,,",
    "ESZ6,Market Price,2026-09-01T13:30:00.100000000Z,Trade,6500.50,7,,,,",     # same timestamp: a sweep
    "ESZ6,Market Price,2026-09-01T13:30:00.200000000Z,Quote,,,6500.25,10,6500.75,12",
    "ESZ6,Market Price,2026-09-01T14:00:00.000000000Z,Trade,6500.25,1,,,,",
    "ESH7,Market Price,2026-09-02T13:30:00.000000000Z,Quote,,,6550.00,5,6550.25,6",
    "ESZ6,Market Price,2026-09-02T13:30:00.000000000Z,Correction,6500.25,1,,,,",
]


def test_inspect_summarises_without_rows():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sample.csv"
        path.write_text("\n".join([HEADER, *ROWS]) + "\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            s = emini.inspect(path)
        text = out.getvalue()
    check("every row counted", s.rows == 7)
    check("contracts and types counted", s.by_ric["ESZ6"] == 6 and s.by_type["Trade"] == 3 and s.by_type["Quote"] == 3)
    check("tick size found from the prices", abs(s.tick() - 0.25) < 1e-9)
    check("two trades sharing a timestamp found once", s.same_time_trades == 1)
    check("spreads of 1 and 2 ticks", s.spreads[0.25] == 2 and s.spreads[0.5] == 1)
    check("timestamp format reported with nanoseconds", "9 digits after the seconds" in text)
    check("two calendar days", len(s.days) == 2)
    check("unknown row types reported", "Correction 1" in text)
    check("no row of the data is printed", not any(row in text for row in ROWS) and "6500.25,3" not in text)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
