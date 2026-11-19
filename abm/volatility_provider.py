"""
Volatility providers (docs/volatility_provider/decisions.md, D39): liquidity providers whose mean entry
depth follows the recent volatility of the mid-price, instead of the takers' hidden buy probability as
in Eq. 4 (paper Fig. 4).

Every volatility provider has the same settings, so the depth is worked out once per step by a
VolatilityGauge and handed to all of them, as Eq. 4's lambda(t) is.

    one change          the mid-price now minus the mid-price k steps ago
    recent volatility   from the changes in the last W steps: their standard deviation ("std", as
                        Leal et al. 2016) or their mean absolute size ("abs", as Kaervik et al. 2018),
                        over a fixed window or a fading one with the same average age (W/2 steps)
    R                   recent volatility / its long-run average (a fading average with an average
                        age of long_memory/2 steps); about 1 in normal times
    depth               "widen":  lambda_0 * (1 + C * max(R - 1, 0))   (never closer than lambda_0)
                        "linear": lambda_0 * (1 + C * (R - 1))         (closer when quieter than usual)

Until W - k changes have been seen, R = 1 and the depth is lambda_0 (the providers behave like the
paper's, with a fixed depth). The fading averages are plain averages of everything so far until
1/count falls to their fading weight, so they settle quickly from the start of a run.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Optional

from abm.agents import LiquidityProvider

MIN_DEPTH = 1.0       # ticks; the depth never goes below this, so the exponential draw stays defined


@dataclass(frozen=True)
class VolatilitySettings:
    """The settings shared by every volatility provider (D39)."""
    measure: str = "std"          # "std" (standard deviation) or "abs" (mean absolute change)
    k: int = 10                   # length of one change, in steps
    window: int = 100             # W: memory of the recent volatility, in steps
    memory: str = "fading"        # "fixed" window or "fading"
    long_memory: int = 5000       # memory of the long-run average, in steps
    form: str = "widen"           # "widen" or "linear"
    coupling: float = 1.0         # C

    def __post_init__(self):
        if self.measure not in ("std", "abs"):
            raise ValueError("measure must be 'std' or 'abs'")
        if self.memory not in ("fixed", "fading"):
            raise ValueError("memory must be 'fixed' or 'fading'")
        if self.form not in ("widen", "linear"):
            raise ValueError("form must be 'widen' or 'linear'")
        if self.k < 1 or self.window <= self.k:
            raise ValueError("k must be at least 1 and the window W longer than k")
        if self.long_memory < 2 or self.coupling < 0:
            raise ValueError("long_memory must be at least 2 and the coupling 0 or more")

    def describe(self) -> str:
        return (f"{self.measure}, k={self.k}, W={self.window} ({self.memory}), long-run {self.long_memory}, "
                f"{self.form}, C={self.coupling:g}")


class FadingMean:
    """An exponentially weighted mean whose average age is `age` steps (weight 1/age per new value),
    starting as a plain mean of everything so far until 1/count falls to that weight."""

    def __init__(self, age: float):
        self.weight = 1.0 / age
        self.count = 0
        self.value = 0.0

    def add(self, x: float) -> None:
        self.count += 1
        w = max(1.0 / self.count, self.weight)
        self.value += w * (x - self.value)


class VolatilityGauge:
    """Works out the recent volatility, R and the providers' mean entry depth from the mid-price,
    once per step. Uses no random numbers, so it never changes what else happens in a run."""

    def __init__(self, settings: VolatilitySettings, lambda_0: float):
        self.s = settings
        self.lambda_0 = lambda_0
        self.mids: deque = deque(maxlen=settings.k + 1)
        self.n_changes = 0
        self.needed = settings.window - settings.k        # changes before the providers start reacting
        if settings.memory == "fixed":
            self.changes: deque = deque(maxlen=self.needed)
            self.sum = self.sum_sq = self.sum_abs = 0.0
        else:
            age = settings.window / 2
            self.mean, self.mean_sq, self.mean_abs = FadingMean(age), FadingMean(age), FadingMean(age)
        self.long_run = FadingMean(settings.long_memory / 2)
        self.ratio = 1.0

    def update(self, mid: Optional[float]) -> None:
        """Take in the mid-price at the end of a step (None if a side of the book was empty, which is
        skipped) and update R for the next step."""
        if mid is None:
            return
        self.mids.append(mid)
        if len(self.mids) <= self.s.k:
            return
        change = self.mids[-1] - self.mids[0]
        self.n_changes += 1
        if self.s.memory == "fixed":
            if len(self.changes) == self.changes.maxlen:
                old = self.changes[0]
                self.sum -= old
                self.sum_sq -= old * old
                self.sum_abs -= abs(old)
            self.changes.append(change)
            self.sum += change
            self.sum_sq += change * change
            self.sum_abs += abs(change)
        else:
            self.mean.add(change)
            self.mean_sq.add(change * change)
            self.mean_abs.add(abs(change))
        if self.n_changes < self.needed:
            return
        recent = self.recent()
        reference = self.long_run.value if self.long_run.count else 0.0
        self.ratio = recent / reference if reference > 0 else 1.0
        self.long_run.add(recent)

    def recent(self) -> float:
        """The recent volatility, by the chosen measure."""
        if self.s.memory == "fixed":
            n = len(self.changes)
            mean, mean_sq, mean_abs = self.sum / n, self.sum_sq / n, self.sum_abs / n
        else:
            mean, mean_sq, mean_abs = self.mean.value, self.mean_sq.value, self.mean_abs.value
        if self.s.measure == "abs":
            return mean_abs
        return math.sqrt(max(mean_sq - mean * mean, 0.0))

    def depth(self) -> float:
        """The mean entry depth for this step."""
        excess = self.ratio - 1.0
        if self.s.form == "widen":
            excess = max(excess, 0.0)
        return max(self.lambda_0 * (1.0 + self.s.coupling * excess), MIN_DEPTH)


@dataclass
class VolatilityProvider(LiquidityProvider):
    """A liquidity provider whose mean entry depth is set each step by the shared VolatilityGauge (passed
    in as lambda_, as Eq. 4's lambda(t) is). Otherwise it is exactly the paper's provider: same chance
    to act, same side choice, same exponential draw of the depth. Kept as its own class so that the
    paper's LiquidityProvider, and every experiment that uses it, stays unchanged."""
