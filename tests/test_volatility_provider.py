"""
Tests for the volatility providers (abm/volatility_provider.py; docs/volatility_provider/decisions.md,
D39) and their trial (experiments/volatility_sweep.py). Run with:
python -m tests.test_volatility_provider   (from the project root)
"""

import contextlib
import io
import math
import tempfile
from pathlib import Path

import numpy as np

from abm.buy_probability import MeanRevertingWalk
from abm.simulation import run_simulation
from abm.volatility_provider import FadingMean, VolatilityGauge, VolatilityProvider, VolatilitySettings
from experiments import volatility_sweep as sweep
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


def feed(gauge, mids):
    for m in mids:
        gauge.update(m)
    return gauge


def test_settings_are_checked():
    check("an unknown measure is rejected", raises_value_error(lambda: VolatilitySettings(measure="range")))
    check("W must be longer than k", raises_value_error(lambda: VolatilitySettings(k=10, window=10)))
    check("an unknown form is rejected", raises_value_error(lambda: VolatilitySettings(form="power")))
    check("a negative coupling is rejected", raises_value_error(lambda: VolatilitySettings(coupling=-1)))


def test_fading_mean_starts_plain_then_fades():
    m = FadingMean(age=4)
    for x in (1, 2, 3):
        m.add(x)
    check("a plain mean while 1/count is above the fading weight", abs(m.value - 2.0) < 1e-12)
    m.add(10)                              # count 4: weight 1/4 either way: 2 + (10 - 2) / 4 = 4
    m.add(10)                              # count 5: weight stays 1/4 (not 1/5): 4 + (10 - 4) / 4 = 5.5
    check("then each new value has weight 1/age", abs(m.value - 5.5) < 1e-12)


def test_measures_on_a_known_series():
    # The mid-price rises by 1 every step: every 2-step change is +2.
    steady = [float(i) for i in range(40)]
    for memory in ("fixed", "fading"):
        std = feed(VolatilityGauge(VolatilitySettings(measure="std", k=2, window=10, memory=memory), 100), steady)
        absolute = feed(VolatilityGauge(VolatilitySettings(measure="abs", k=2, window=10, memory=memory), 100), steady)
        check(f"{memory}: a steady one-way move has standard deviation 0", abs(std.recent()) < 1e-9)
        check(f"{memory}: and mean absolute change 2", abs(absolute.recent() - 2.0) < 1e-9)
    # Up 1, down 1, alternately: 1-step changes are +1, -1, +1, ...
    zigzag = [float(i % 2) for i in range(41)]
    g = feed(VolatilityGauge(VolatilitySettings(measure="std", k=1, window=11, memory="fixed"), 100), zigzag)
    check("a +1/-1 zigzag over an even window has standard deviation 1", abs(g.recent() - 1.0) < 1e-9)
    check("the fixed window holds W - k changes", len(g.changes) == 10)


def test_no_reaction_until_the_window_has_filled():
    g = VolatilityGauge(VolatilitySettings(k=5, window=20), 100)
    rng = np.random.default_rng(0)
    mids = np.cumsum(rng.standard_normal(60)) * 10
    for i, m in enumerate(mids):
        g.update(m)
        if g.n_changes < g.needed:
            assert g.depth() == 100 and g.ratio == 1.0
    check("depth lambda_0 and R = 1 until W - k changes have been seen", g.n_changes >= g.needed)
    g.update(None)
    check("a step with no mid-price is skipped", g.n_changes == len(mids) - 5)


def test_forms_of_the_reaction():
    for ratio, widen, linear in ((1.0, 100, 100), (2.0, 200, 200), (0.5, 100, 50)):
        for form, expected in (("widen", widen), ("linear", linear)):
            g = VolatilityGauge(VolatilitySettings(form=form, coupling=1.0), 100)
            g.ratio = ratio
            check(f"{form}, R = {ratio}: depth {expected}", abs(g.depth() - expected) < 1e-9)
    g = VolatilityGauge(VolatilitySettings(form="linear", coupling=1.0), 100)
    g.ratio = 0.0
    check("the depth never goes below one tick", g.depth() == 1.0)


def test_ratio_against_the_long_run_average():
    rng = np.random.default_rng(1)
    quiet = list(np.cumsum(rng.standard_normal(3000)))
    g = feed(VolatilityGauge(VolatilitySettings(k=5, window=50, long_memory=1000), 100), quiet)
    check(f"in steady conditions R stays near 1 ({g.ratio:.2f})", 0.6 < g.ratio < 1.6)
    burst = list(quiet[-1] + np.cumsum(rng.standard_normal(60) * 5))
    feed(g, burst)
    check(f"a burst five times as volatile sends R well above 1 ({g.ratio:.2f})", g.ratio > 2.5)


KW = dict(n_agents=125, n_steps=3000, seed=4, **PARAMS)


def test_simulation_with_volatility_providers():
    fixed = run_simulation(taker_flow=MeanRevertingWalk(), **KW)
    c0 = run_simulation(taker_flow=MeanRevertingWalk(), volatility=VolatilitySettings(coupling=0.0), **KW)
    check("with C = 0 the run is identical to the fixed-depth run (the gauge uses no random numbers)",
          run_fingerprint(fixed) == run_fingerprint(c0))
    widen = run_simulation(taker_flow=MeanRevertingWalk(), volatility=VolatilitySettings(form="widen"), **KW)
    linear = run_simulation(taker_flow=MeanRevertingWalk(), volatility=VolatilitySettings(form="linear"), **KW)
    check("the depth used each step is recorded", len(widen.lambda_series) == 3000 and len(fixed.lambda_series) == 0)
    check("'widen' never comes closer than lambda_0", widen.lambda_series.min() >= 100)
    check("'linear' also comes closer in quiet spells", linear.lambda_series.min() < 100)
    check("they cannot be combined with Eq. 4", raises_value_error(lambda: run_simulation(
        taker_flow=MeanRevertingWalk(), volatility=VolatilitySettings(), depth_coupling=10, q_rms=0.0158, **KW)))
    check("VolatilityProvider is a LiquidityProvider, so it acts the same way given the depth",
          issubclass(VolatilityProvider, __import__("abm.agents", fromlist=["LiquidityProvider"]).LiquidityProvider))


def test_sweep_grid_and_check():
    check("216 combinations plus 2 controls", len(sweep.GRID) == 218 and sweep.GRID[:2] == ["fig4", "fixed_depth"])
    check("every combination has its own name", len({sweep.name_of(i) for i in range(218)}) == 218)
    lags = sweep.LAGS
    good_price = {"kurtosis": {1: 60.0, 10: 8.6, 100: 3.5, 1000: 2.9},
                  "hurst": np.where(lags < 200, 0.4, 0.5),
                  "autocorr": {1: {"signed": np.array([-0.06])}, 100: {"signed": np.array([-0.01, 0.02, -0.02, 0.0, 0.0])}}}
    bad_price = {**good_price, "kurtosis": {1: 3.2, 10: 2.6, 100: 2.5, 1000: 2.6}, "hurst": np.full(len(lags), 0.15)}
    good = {"mid": good_price, "trade": bad_price}
    check("the check uses the mid-price (D37)", sweep.PRICE == "mid")
    check("an E-mini-like mid-price passes all three", sweep.check(good)["passes"])
    check("whatever the trade price does", sweep.check({"mid": good_price, "trade": good_price})["passes"])
    check("and a good trade price does not rescue a bad mid-price", not sweep.check({"mid": bad_price, "trade": good_price})["passes"])
    flat = {"mid": {**good_price, "kurtosis": {1: 150, 10: 16, 100: 8.9, 1000: 8.0}}}
    check("Fig. 4-like tails that do not fade fail (a)", not sweep.check(flat)["a_fat_tails_fading"])
    reverting = {"mid": {**good_price, "hurst": np.full(len(lags), 0.2)}}
    check("H of 0.2 at long lags fails (b)", not sweep.check(reverting)["b_random_walk"])
    anti = {"mid": {**good_price, "autocorr": {1: {"signed": np.array([-0.06])},
                                               100: {"signed": np.array([-0.32, 0, 0, 0, 0])}}}}
    check("strong anti-correlation of 100-trade changes fails (c)", not sweep.check(anti)["c_bounce_only"])


def test_sweep_end_to_end():
    with tempfile.TemporaryDirectory() as tmp:
        tiny = ["--n-runs", "1", "--n-steps", "4000", "--skip", "500", "--workers", "1", "--out-dir", tmp]
        with contextlib.redirect_stdout(io.StringIO()):
            for index in (0, 1, 2):
                sweep.main(["run", "--index", str(index), *tiny])
            again = io.StringIO()
        with contextlib.redirect_stdout(again):
            sweep.main(["run", "--index", "2", *tiny])
        check("running a finished combination again skips it", "already done" in again.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            sweep.main(["collect", "--out-dir", tmp, "--emini", str(Path(tmp) / "none.pkl")])
        check("collect works on a partly finished trial", "3 of 218" in out.getvalue())
        check("it writes the table and the figure", (Path(tmp) / "summary.csv").exists() and (Path(tmp) / "summary.png").exists())


def test_lambda_sweep():
    from experiments import lambda_sweep as lam
    check("6 values of lambda_0 for the control and 4 setups: 30 jobs", len(lam.GRID) == 30)
    check("the controls come first", all(lam.GRID[i][0] == 1 for i in range(6)) and lam.name_of(0) == "lam30_control_fixed_depth")
    check("the setups are the agreed four", lam.SETUPS[1:] == (105, 21, 35, 84))
    check("every job has its own name", len({lam.name_of(i) for i in range(30)}) == 30)
    seg, depth = sweep.simulate(sweep.GRID[105], seed=0, n_steps=1500, skip=500, lambda_0=10)
    check("lambda_0 reaches the volatility providers: their depth is about 10, not 100", 1 <= depth["lambda_mean"] < 30)
    seg, depth = sweep.simulate("fixed_depth", seed=0, n_steps=1500, skip=500, lambda_0=10)
    check("and the fixed-depth control", depth["lambda_mean"] == 10)
    with tempfile.TemporaryDirectory() as tmp:
        tiny = ["--n-runs", "1", "--n-steps", "3000", "--skip", "500", "--workers", "1", "--out-dir", tmp]
        with contextlib.redirect_stdout(io.StringIO()):
            for index in (1, 7):
                lam.main(["run", "--index", str(index), *tiny])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            lam.main(["collect", "--out-dir", tmp, "--first-dir", str(Path(tmp) / "none"), "--emini", str(Path(tmp) / "none.pkl")])
        check("collect works on a partly finished trial", "2 of 30" in out.getvalue())
        check("it writes the table and the figure", (Path(tmp) / "summary.csv").exists() and (Path(tmp) / "summary.png").exists())


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
