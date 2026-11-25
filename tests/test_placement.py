"""
Tests for placement from the best price (abm/placement.py; docs/providers/decisions.md, D45) and its
trial (experiments/placement_sweep.py). Run with:
python -m tests.test_placement   (from the project root)
"""

import contextlib
import io
import random
import tempfile
from pathlib import Path

import numpy as np

from abm.buy_probability import MeanRevertingWalk
from abm.orderbook import OrderBook, Side
from abm.placement import DistanceSampler, PlacementSettings, reference_price
from abm.simulation import run_simulation
from experiments import placement_sweep as sweep
from experiments.run import PARAMS
from tests.test_simulation import run_fingerprint


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    assert condition, f"FAILED: {label}"


def raises_value_error(fn):
    try:
        fn()
    except ValueError:
        return True
    return False


def test_settings_are_checked():
    check("an unknown rule is rejected", raises_value_error(lambda: PlacementSettings(rule="uniform")))
    check("an unknown crossing treatment is rejected", raises_value_error(lambda: PlacementSettings(crossing="cap")))
    check("a scale of 0 is rejected", raises_value_error(lambda: PlacementSettings(rule="student", scale=0)))


def test_bmp_distances():
    s = DistanceSampler(PlacementSettings(rule="bmp"))
    rng = random.Random(0)
    d = np.array([s.draw(rng) for _ in range(400_000)])
    p = {k: np.mean(d == k) for k in (-1, 0, 1, 2, 3)}
    check(f"Delta = -1, 0 and 1 equally likely ({p[-1]:.3f}, {p[0]:.3f}, {p[1]:.3f})",
          abs(p[-1] / p[1] - 1) < 0.03 and abs(p[0] / p[1] - 1) < 0.03)
    check(f"P(2)/P(1) = (2/3)^1.6 = {(2 / 3) ** 1.6:.3f} ({p[2] / p[1]:.3f})", abs(p[2] / p[1] / (2 / 3) ** 1.6 - 1) < 0.03)
    near = np.mean(np.abs(d) <= 1)
    check(f"about 55-60% within one tick of the best, as Bouchaud et al. find roughly half ({near:.2f})", 0.5 < near < 0.65)
    check("nothing more aggressive than one tick inside the spread", d.min() == -1)
    w = DistanceSampler(PlacementSettings(rule="bmp")).cumulative
    probs = np.diff(np.concatenate([[0.0], w]))
    values = s.values
    i150, i250 = values.index(150), values.index(250)
    ratio = (probs[i250] / probs[i150]) / ((151 / 251) ** 1.6)
    check(f"beyond 100 ticks the taper adds e^(-100/100) per 100 ticks ({ratio:.4f} against {np.exp(-1):.4f})",
          abs(ratio / np.exp(-1) - 1) < 1e-6)


def test_student_distances():
    for scale in (5, 20):
        s = DistanceSampler(PlacementSettings(rule="student", scale=scale))
        rng = random.Random(1)
        d = np.array([s.draw(rng) for _ in range(200_000)])
        median = np.median(np.abs(d))
        # For a Student t with 1.3 dof, half the values lie within 0.91 scale of the centre.
        check(f"scale {scale}: half of distances within about {0.91 * scale:.1f} ticks ({median:g})",
              abs(median - 0.91 * scale) <= max(1, 0.06 * scale))
        check(f"scale {scale}: centred on the best price (mean sign {np.mean(np.sign(d)):+.3f})", abs(np.mean(np.sign(d))) < 0.01)


def test_reference_price():
    book = OrderBook(keep_trades=False)
    check("an empty book: the start price", reference_price(book, Side.BID, 1000) == 1000)
    book.submit_limit_order(Side.ASK, 1005, 0)
    check("own side empty: one tick inside the opposite best", reference_price(book, Side.BID, 1000) == 1004)
    book.submit_limit_order(Side.BID, 1001, 0)
    check("otherwise the best price on the order's own side",
          reference_price(book, Side.BID, 1000) == 1001 and reference_price(book, Side.ASK, 1000) == 1005)


KW = dict(n_agents=125, n_steps=3000, seed=2, record_sides=True, record_trades=True, **PARAMS)


def test_simulation_with_placement():
    plain = run_simulation(taker_flow=MeanRevertingWalk(), **KW)
    again = run_simulation(taker_flow=MeanRevertingWalk(), placement=None, **KW)
    check("without placement the run is as before (the Preis control)", run_fingerprint(plain) == run_fingerprint(again))
    redraw = run_simulation(taker_flow=MeanRevertingWalk(), placement=PlacementSettings(rule="bmp", crossing="redraw"), **KW)
    c = redraw.placement_counts
    check(f"crossing drawn again: no provider order crosses ({c['crossed']}), some were drawn again ({c['redrawn']})",
          c["crossed"] == 0 and c["redrawn"] > 0)
    check("so only the takers trade: about as many trades as before",
          abs(len(redraw.trade_prices) / len(plain.trade_prices) - 1) < 0.15)
    allow = run_simulation(taker_flow=MeanRevertingWalk(), placement=PlacementSettings(rule="student", crossing="allow"), **KW)
    c = allow.placement_counts
    check(f"crossing allowed: provider orders cross ({c['crossed'] / c['placed']:.0%}) and add trades",
          c["crossed"] > 0 and len(allow.trade_prices) > 1.5 * len(plain.trade_prices))
    check("placement cannot be combined with Eq. 4", raises_value_error(lambda: run_simulation(
        taker_flow=MeanRevertingWalk(), placement=PlacementSettings(), depth_coupling=10, q_rms=0.0158, **KW)))


def test_sweep_grid_and_run():
    check("10 provider setups x 2 kinds of takers = 20 jobs", len(sweep.GRID) == 20)
    check("every job has its own name", len({sweep.name_of(i) for i in range(20)}) == 20)
    with tempfile.TemporaryDirectory() as tmp:
        tiny = ["--n-runs", "1", "--n-steps", "2500", "--skip", "500", "--workers", "1", "--out-dir", tmp]
        with contextlib.redirect_stdout(io.StringIO()):
            for index in (0, 2, 13):
                sweep.main(["run", "--index", str(index), *tiny])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            sweep.main(["collect", "--out-dir", tmp, "--emini", str(Path(tmp) / "none.pkl")])
        check("collect works on a partly finished trial", "3 of 20" in out.getvalue())
        check("it writes the table and both figures",
              all((Path(tmp) / f).exists() for f in ("summary.csv", "hurst.png", "response.png")))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
