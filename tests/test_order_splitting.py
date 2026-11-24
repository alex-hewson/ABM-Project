"""
Tests for order splitting (abm/order_splitting.py; docs/takers/decisions.md, D42) and its trial
(experiments/splitting_sweep.py). Run with:
python -m tests.test_order_splitting   (from the project root)
"""

import contextlib
import io
import random
import tempfile
from pathlib import Path

import numpy as np

from abm.buy_probability import MeanRevertingWalk
from abm.order_splitting import HiddenOrders, SplittingSettings
from abm.orderbook import Side
from abm.simulation import run_simulation
from analysis.stylised import SIGN_LAGS, sign_autocorrelation
from experiments import splitting_sweep as sweep
from experiments.common import trade_segment
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
    check("a share of 0 is rejected", raises_value_error(lambda: SplittingSettings(share=0)))
    check("a share above 1 is rejected", raises_value_error(lambda: SplittingSettings(share=1.2)))
    check("N must be a whole number of at least 1", raises_value_error(lambda: SplittingSettings(n_hidden=0))
          and raises_value_error(lambda: SplittingSettings(n_hidden=1.5)))
    check("alpha must be above 1", raises_value_error(lambda: SplittingSettings(alpha=1.0)))


def test_sizes_follow_the_power_law():
    h = HiddenOrders(SplittingSettings(alpha=1.6), random.Random(0))
    sizes = np.array([h.draw_size() for _ in range(400_000)])
    check("the smallest size is 1", sizes.min() == 1)
    for x in (2, 10, 100):
        share = np.mean(sizes >= x)
        check(f"P(L >= {x}) close to {x}^-1.6 = {x ** -1.6:.4f} ({share:.4f})", abs(share / x ** -1.6 - 1) < 0.05)


def test_hidden_orders_keep_their_side_and_are_replaced():
    h = HiddenOrders(SplittingSettings(n_hidden=1, alpha=1.6), random.Random(1))
    first_size, first_side = h.sizes[0], h.sides[0]
    sides = [h.next_side() for _ in range(first_size)]
    check("every unit of a hidden order is on its side", all(s is first_side for s in sides))
    check("when its last unit is placed, a new hidden order starts", len(h.sizes) == 2 and h.remaining[0] == h.sizes[1])
    h = HiddenOrders(SplittingSettings(n_hidden=3, alpha=1.6), random.Random(2))
    sides = [h.next_side() for _ in range(200_000)]
    check(f"buys and sells about equally often ({np.mean([s is Side.BID for s in sides]):.3f})",
          abs(np.mean([s is Side.BID for s in sides]) - 0.5) < 0.03)
    check("units placed match the sizes started, less what is left",
          sum(h.sizes) - sum(h.remaining) == 200_000)


KW = dict(n_agents=125, n_steps=4000, seed=3, record_sides=True, record_trades=True, **PARAMS)


def lag1(r):
    return sign_autocorrelation([trade_segment(r, 200)], lags=SIGN_LAGS)[0]


def test_simulation_with_splitters():
    plain = run_simulation(taker_flow=MeanRevertingWalk(), **KW)
    again = run_simulation(taker_flow=MeanRevertingWalk(), splitting=None, **KW)
    check("without splitting the run is as before", run_fingerprint(plain) == run_fingerprint(again))
    check("and no hidden orders are recorded", len(plain.hidden_order_sizes) == 0)
    one = run_simulation(splitting=SplittingSettings(share=1.0, n_hidden=1, alpha=1.6), **KW)
    check("splitters place the market orders: about as many trades as before",
          abs(len(one.trade_prices) / len(plain.trade_prices) - 1) < 0.1)
    check(f"N = 1, f = 1, alpha = 1.6: lag-1 sign correlation near 0.56 ({lag1(one):.2f})", 0.45 < lag1(one) < 0.65)
    half = run_simulation(splitting=SplittingSettings(share=0.5, n_hidden=1, alpha=1.6), **KW)
    check(f"with half random takers, about a quarter of that ({lag1(half):.2f})", 0.08 < lag1(half) < 0.22)
    check(f"and the plain takers have none ({lag1(plain):+.3f})", abs(lag1(plain)) < 0.03)
    check("the hidden order sizes are recorded", len(one.hidden_order_sizes) > 100 and one.hidden_order_sizes.min() >= 1)
    check("splitting needs the paper's unit takers", raises_value_error(lambda: run_simulation(
        splitting=SplittingSettings(), taker_mix={__import__("abm.agents", fromlist=["AgentType"]).AgentType(1, 1): 125}, **KW)))


def test_price_statistics_use_the_mid_just_before_each_trade():
    r = run_simulation(splitting=SplittingSettings(share=0.85, n_hidden=1, alpha=1.6), **KW)
    seg = trade_segment(r, 200)
    keep = r.trade_steps >= 200
    check("the segment's mid-price is the one recorded just before each trade (D43)",
          np.allclose(seg["mid"], r.trade_mids[keep], equal_nan=False))
    same_step = r.trade_steps[keep][1:] == r.trade_steps[keep][:-1]
    moved = np.diff(seg["mid"]) != 0
    check(f"so it can change between two trades of the same step ({np.mean(moved[same_step]):.1%} of them)",
          np.any(moved & same_step))
    check("every trade is above or below its mid-price, none at it", np.all(seg["trade"] != seg["mid"]))


def test_sweep_grid():
    check("2 x 3 x 5 x 7 = 210 jobs", len(sweep.GRID) == 210)
    check("every job has its own name", len({sweep.name_of(i) for i in range(210)}) == 210)
    check("f = 1 is run once, with no random takers", sum(1 for g in sweep.GRID if g[3] == 1.0) == 30
          and all(not g[4] for g in sweep.GRID if g[3] == 1.0))
    check("q(t) on and off for every other share", sum(1 for g in sweep.GRID if g[3] < 1 and g[4]) == 90)


def test_sweep_end_to_end():
    with tempfile.TemporaryDirectory() as tmp:
        tiny = ["--n-runs", "1", "--n-steps", "3000", "--skip", "500", "--workers", "1", "--out-dir", tmp]
        with contextlib.redirect_stdout(io.StringIO()):
            for index in (0, 1, 6):
                sweep.main(["run", "--index", str(index), *tiny])
        again = io.StringIO()
        with contextlib.redirect_stdout(again):
            sweep.main(["run", "--index", "1", *tiny])
        check("running a finished job again skips it", "already done" in again.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            sweep.main(["collect", "--out-dir", tmp, "--emini", str(Path(tmp) / "none.pkl")])
        check("collect works on a partly finished trial", "3 of 210" in out.getvalue())
        check("it writes the table and both figures",
              all((Path(tmp) / f).exists() for f in ("summary.csv", "signs.png", "hurst.png")))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
