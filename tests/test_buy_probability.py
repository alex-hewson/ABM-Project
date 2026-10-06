"""
Tests for the buy-probability processes in abm/buy_probability.py (paper Fig. 3).
Run with: python -m tests.test_buy_probability   (from the project root)

Covers ConstantSide, and the bounded and mean-reverting random walks of q_taker: their step size,
reflection at the bounds, direction probabilities, and the settled spread that Eq. 4 uses.
"""

import random

from abm.buy_probability import ConstantSide, BoundedRandomWalk, MeanRevertingWalk


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    assert condition, f"FAILED: {label}"


class ScriptedRandom:
    """Stand-in for random.Random whose random() returns pre-set values in order, so a walk's
    direction and reflection can be worked out by hand."""

    def __init__(self, *values):
        self.values = list(values)

    def random(self):
        return self.values.pop(0)


def raises_value_error(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except ValueError:
        return True
    return False


def test_mean_reverting_walk_reports_its_settled_spread():
    check("stationary_rms is sqrt(step/4) (D19): 0.0158 for step 0.001",
          abs(MeanRevertingWalk().stationary_rms - (0.001 / 4) ** 0.5) < 1e-15)
    check("and scales with the step", abs(MeanRevertingWalk(step=0.004).stationary_rms - 0.001 ** 0.5) < 1e-15)


def test_constant_side_never_changes_and_uses_no_random_numbers():
    flow, rng = ConstantSide(0.7), random.Random(3)
    state_before = rng.getstate()
    for _ in range(100):
        flow.advance(rng)
    check("q stays 0.7", flow.q == 0.7)
    check("advance consumed no random numbers (so a constant flow can't change a seeded run)",
          rng.getstate() == state_before)


def test_walk_parameters_are_validated():
    check("step must be positive", raises_value_error(BoundedRandomWalk, step=0.0))
    check("half_width must be a whole number of steps",
          raises_value_error(BoundedRandomWalk, step=0.001, half_width=0.0505))
    check("half_width must be at least one step", raises_value_error(BoundedRandomWalk, step=0.1, half_width=0.0))
    check("q must stay a valid probability", raises_value_error(BoundedRandomWalk, step=0.1, half_width=0.6))
    check("the paper's Fig. 3a and 3c settings are accepted",
          BoundedRandomWalk().K == 50 and MeanRevertingWalk().K == 500)


def test_bounded_walk_starts_at_the_centre_and_moves_one_step_at_a_time():
    flow, rng = BoundedRandomWalk(), random.Random(1)
    check("starts at exactly 1/2", flow.q == 0.5)
    previous, steps_ok = flow.q, True
    for _ in range(2000):
        flow.advance(rng)
        steps_ok = steps_ok and abs(abs(flow.q - previous) - 0.001) < 1e-12
        previous = flow.q
    check("every step changes q by exactly +/-0.001 (including reflected ones)", steps_ok)


def test_bounded_walk_reflects_by_mirroring_back_inside():
    flow = BoundedRandomWalk(step=0.1, half_width=0.2)      # k lives in -2..2
    flow.k = 2
    flow.advance(ScriptedRandom(0.1))                         # 0.1 < 0.5: try +1 -> 3 -> mirrored to 1
    check("upper bound: a step outward ends one step inside (k=2 -> 1)", flow.k == 1)
    flow.k = -2
    flow.advance(ScriptedRandom(0.9))                         # 0.9 >= 0.5: try -1 -> -3 -> mirrored to -1
    check("lower bound: a step outward ends one step inside (k=-2 -> -1)", flow.k == -1)
    flow.k = 0
    flow.advance(ScriptedRandom(0.1))
    check("in the interior a step is just a step (k=0 -> 1)", flow.k == 1)


def test_bounded_walk_stays_within_bounds_and_reaches_both_over_a_long_run():
    flow, rng = BoundedRandomWalk(), random.Random(2)
    qs = []
    for _ in range(30_000):
        flow.advance(rng)
        qs.append(flow.q)
    check(f"q stays within [0.45, 0.55] (min {min(qs):.3f}, max {max(qs):.3f})",
          min(qs) >= 0.45 - 1e-9 and max(qs) <= 0.55 + 1e-9)
    check("and actually reaches both bounds", min(qs) < 0.45 + 1e-9 and max(qs) > 0.55 - 1e-9)


def test_mean_reverting_walk_direction_probabilities_by_hand():
    flow = MeanRevertingWalk()                                # step 0.001
    flow.k = 10                                               # q = 0.51: p(toward centre) = 0.5 + 0.01 = 0.51
    flow.advance(ScriptedRandom(0.50))
    check("above centre, draw 0.50 < 0.51: moves toward the centre (k 10 -> 9)", flow.k == 9)
    flow.k = 10
    flow.advance(ScriptedRandom(0.52))
    check("above centre, draw 0.52 >= 0.51: moves away (k 10 -> 11)", flow.k == 11)
    flow.k = -10
    flow.advance(ScriptedRandom(0.50))
    check("below centre, draw 0.50 < 0.51: moves toward the centre (k -10 -> -9)", flow.k == -9)
    flow.k = 0
    flow.advance(ScriptedRandom(0.3))
    check("exactly at the centre there is no 'toward': a fair coin decides (0.3 -> up)", flow.k == 1)
    flow.k = 0
    flow.advance(ScriptedRandom(0.7))
    check("... (0.7 -> down)", flow.k == -1)


def test_mean_reverting_walk_settles_to_the_theoretical_spread():
    # A pull of 2*step*(q-centre) per step on steps of size step is an Ornstein-Uhlenbeck process, whose
    # stationary standard deviation is sqrt(step/4) = 0.0158 for step 0.001 (relaxation time ~500 steps).
    flow, rng = MeanRevertingWalk(), random.Random(4)
    qs = []
    for _ in range(200_000):
        flow.advance(rng)
        qs.append(flow.q)
    mean = sum(qs) / len(qs)
    std = (sum((q - mean) ** 2 for q in qs) / len(qs)) ** 0.5
    expected = (0.001 / 4) ** 0.5
    check(f"std of q {std:.4f} within 15% of sqrt(step/4) = {expected:.4f}", abs(std - expected) < 0.15 * expected)
    check(f"mean of q {mean:.4f} within 0.01 of 1/2", abs(mean - 0.5) < 0.01)
    check("q stays a valid probability", min(qs) >= 0 and max(qs) <= 1)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nAll tests passed.")
