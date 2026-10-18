# Decisions and assumptions log

Choices made in this project: what was chosen and why. Kept short on purpose.
- What the paper itself defines is in `paper_model.md` (P numbers).
- The tests and numbers behind each choice are in `validation.md`.
- What is done and what comes next is in `project_plan.md`.

**[Assumed]** = Paper unclear, so need to make own decision ·
**[Checked]** = verified against theory or tests · **[Open]** = not yet decided.

Decision numbers (D1, D2, ...) are fixed IDs in order of creation, not positions in this file, so
references to them from code comments stay valid when entries are moved.

---

## 1. Model

**D1. Base model and parameters.** The paper's (P1–P13), so nothing was decided. One addition: the
code refuses to run unless the stability condition α(1−δ) > μ and δ > 0 holds.

**D2. One "MCS" = one simulation step. [Assumed]**
The paper does not define MCS. In one step every provider acts with probability α and every taker
with probability μ, independently. This gives the αN_A and μN_A orders per step that Eq. 1 needs.

**D3. Order within a step: providers → cancellation → takers. [Assumed, Checked]**
Not stated, but implied by Eq. 1. A test confirms it. The price for a step is read after the takers
have acted and before the book is refilled, which matters at short lags (D11).

**D4. An order can be cancelled in the step it was placed. [Assumed]** Follows Eq. 1.

**D5. Entry depth. [Assumed]**
- λ₀ is taken as the mean depth. The paper only calls it a "parameter"; as a rate it would give
  depths of about 0.01 ticks.
- Prices are rounded to the nearest tick. The paper gives no rounding rule.
- With no midpoint, the start price 10⁶ is used. This only happens in the pre-opening.

**D6. A limit order that crosses the spread executes at once, at the resting order's price.
[Assumed]** The paper only says limit orders execute at the limit "or some better price". This is
rare, so it hardly affects results.

**D7. Prices are unbounded integers. [Assumed]**
The paper's book has 2×10⁶ ticks. Prices stay within a few thousand ticks of the start, so the
edges should not matter.

### Changing buy probability (Fig. 3)

**D16. One q_taker(t) for the whole market. [Assumed]**
The paper does not say whether q_taker is one value or one per taker. One shared value is used, so a
trend builds up. The q_provider variant the paper mentions (P20) is not implemented.

**D17. Takers use the current q, then q moves. [Assumed]**
So the first step uses exactly q = 1/2. The pre-opening does not move q.

**D18. Bounded walk: +Δs and −Δs equally likely; reflection by mirroring. [Assumed]**
The paper gives neither. A step past the bound ends one step inside it. The other reading (the step
is blocked and q stays at the bound) is untested.

**D19. Mean-reverting walk: a fair coin at exactly q = 1/2. [Assumed, Checked]**
The paper does not cover this case. Derived: q settles to a spread of √(Δs/4) = 0.0158 and forgets
its past over about 500 steps. A test and the Fig. 3 runs give the same value.

**D20. Fig. 3 runs. [Assumed, Checked]**
- Every run starts with a new walk at q = 1/2.
- Each flow has its own results file, so runs from different flows cannot be mixed.
- Only |Δp| histograms are saved. The signed distributions in the insets are made by mirroring them,
  which works because both walks are symmetric about 1/2.

### Entry depth linked to the trend (Eq. 4, Fig. 4)

**D21. The average in Eq. 4 is the derived value √(Δs/4) = 0.0158. [Assumed, Checked]**
The paper says the average is found "separately before the main simulation", but gives no method.
The derived value (D19) is used; the Fig. 3 runs measured the same. λ(t) uses the same step's q as
the takers. The pre-opening uses λ₀. The code only allows Eq. 4 with the mean-reverting walk.

---

## 2. Implementation

**D8. The "fast" method is used for all results. [Checked]**
It draws how many agents act from a binomial, then picks that many at random. This is exact because
the agents are identical and independent, and about 3× faster. It agrees statistically with the
per-agent loop. *Limitation:* agents that react to the book cannot be grouped this way, so Phase 2
needs a per-agent loop for them.

**D9. Reproducibility. [Checked]**
Seeds 0…n−1 per (N_A, run). Every results file records the git commit, branch and whether the
working tree was clean. The fast method needs Python ≥ 3.12.

**D10. A book with an empty side stops the run. [Assumed]**
It is not patched over. For an instability study, a one-sided book is an event that should be seen.
It has not happened in any run.

**D23. The baseline is git tag `baseline-v1`. [Checked]**
It is the control model for Phase 2. With the new agents switched off, a run should give the same
results as the baseline. `tests/test_simulation.py` checks this against numbers recorded from the
baseline code.

---

## 3. Measurement

**D11. Price = median trade price in each step. [Assumed]**
The paper does not say which price it uses, and the choice changes H a lot at short lags. Five
definitions were compared; the median matches the paper's Fig. 2c best. **This is calibrating an
unspecified detail, not a finding**, and must be reported as such. All five are stored in every
results file.

**D12. H(Δτ) is the local slope of log RMS against log Δτ. [Assumed, Checked]**
The paper defines H (P14) but not how to estimate it. About 80 log-spaced lags are used. H is worked
out per run, then averaged. Long lags (Δτ ≳ 10⁴) are noisy.

**D13. Scale.** 10⁶ steps and 50 runs per N_A are the paper's (P13). The checks on the Fig. 2 run are
in `validation.md`.

**D14. Depth profile: last 10⁴ steps, lognormal fit by weighted regression. [Assumed, Checked]**
The paper does not say which 10⁴ steps, or how the fit is made. The two sides are folded together
and fitted with weights of count². The weights were chosen by inspection, not derived: other
choices put the peak 25–50% too far out. **[Open]** whether the paper fits each side separately.

**D15. Return distributions: |Δp| in log-spaced bins on each price's own grid. [Assumed, Checked]**
The mid-price moves in half ticks and a trade price in whole ticks. Bins that do not match the grid
give a zigzag. **[Open]** the paper's axis convention for Fig. 2d.

**D29. Autocorrelation of price changes. [Assumed, Checked]**
Measured on the price change over blocks of 50 steps that do not overlap, at lags of 1 to 100
blocks. Two versions: of the changes themselves (0 in real markets; below 0 means the price tends
to turn back), and of their absolute size (above 0 means volatility clustering). The block of 50
steps is a choice: long enough that single-step noise does not dominate, short enough to leave
many blocks per run. Checked on made-up series with known answers.

**D22. Return bins reach 50,000 ticks, and anything beyond is counted. [Assumed, Checked]**
The tails in Fig. 4b reach several thousand ticks. Nothing has fallen beyond the bins so far.
Fig. 4b is drawn as in the paper: signed Δp on a linear axis, probability on a log axis.

---

## 4. Phase 2: shocks and recovery

**D24. A shock is one market order of a given size. [Assumed]**
It is submitted at the end of a step, after that step's takers, so the price recorded for the step
shows the full impact. It eats into the book from the best price outwards. It uses no random
numbers, so a run with a shock is identical to the run without it up to that step.

**D25. How recovery is measured. [Assumed]**
- Curves are averaged over many runs first. One run is too noisy.
- Level before = mean of the 200 steps before the shock. The price is measured from the step just
  before the shock.
- Impact = value at the shock step minus the level before.
- Share recovered = how much of the impact is undone by the end (mean of the last 200 steps).
- Half-life = steps until half of the impact is undone.

**D26. Orders bigger than one unit. [Assumed]**
The paper only has unit orders (P4), so all of this is added:
- A limit order of size k rests as one order. It keeps its place in the queue while it is filled
  bit by bit.
- It is cancelled as a whole. The cancellation probability δ applies to each order, not each unit.
- A market order of size k takes the best price first, then the next, until it is filled. If the
  other side runs out, the unfilled part is dropped.
- A trade is one fill between two orders, of any size. The trade prices of a step (D11) count each
  trade once, whatever its size.
- Depth is counted in units. Orders and units are both recorded, and are equal while every order
  is one unit.

With every order at size 1 the model is exactly the baseline (D23).

**D27. Agent types: different speeds and order sizes. [Assumed, Checked]**
Agreed with supervisors on 13 October 2026; the details below are assumptions.
- A type has an interval and a size. An agent with interval k gets a chance to act every k-th
  step, and its orders are of the given size. The three types used are 1 unit every step, 2 units
  every 2 steps and 4 units every 4 steps, so each trades the same volume on average.
- On its step an agent still acts with probability α (or μ), not every time.
- Agents of one type are spread evenly over the steps: agent i has offset i mod k. The offsets
  are fixed, not random, so about the same number of agents get a turn on every step.
- Providers and takers can both have types, in any mix that adds up to N_A.
- When several types act in one step, their orders are put in random order, so no type always
  goes first.
- A market order that is only partly filled counts as a failed order, like one that finds an
  empty book.

With every agent of the first type the model is exactly the baseline (D23). Eq. 1 and Eq. 2 still
hold, counted in units.

**D28. Value traders: the first agents that react to the market. [Assumed, Checked]**
Added because agents that ignore the market cannot make the price recover (`validation.md`,
sections 8 and 9).
- All value traders estimate the asset's true value (D30).
- Each trader's own value is the true value plus a fixed error (its shift). The error is + or − with
  equal chance, with a size drawn from an exponential distribution (mean 50 ticks by default). So
  the traders disagree about the value: most are near the true value, a few are far from it.
- On its turn a trader compares its value with the midpoint. Price below its value: it buys.
  Price above: it sells.
- It uses a limit order at its value, rounded so that it never trades at a worse price than its
  value. If the order crosses the spread it trades at once; if not, it rests in the book.
- Value traders take the place of some of the takers and act at the same rate μ, so the number of
  orders per step is unchanged. Takers and value traders act in one random order within a step.
- A trader keeps its shift for the whole run.

The defaults (mean error 50 ticks, and news of 1 tick per step in D30) are placeholders, not fitted
to anything. With no value traders the model is exactly the baseline (D23).

**D30. The true value: a random walk driven by news. [Assumed, Checked]**
- It starts at the midpoint at the end of the pre-opening. Each step it moves by a random step from a
  normal distribution, with a standard deviation of 1 tick by default ("news"). It does not depend on
  the price.
- Why: the first version used a moving average of the price as the reference, so each trader's value
  followed the price. A trader that started bullish stayed bullish whatever the price did. When the
  shifts did not balance, the price ran away from its own average: a drift of 10–48 ticks per 1,000
  steps, in the direction of the traders' middle shift (`validation.md`, section 12). A real value
  investor does not change its valuation just because the price has moved.
- The price now sits a fixed distance from the true value, about the traders' middle error, where
  buyers and sellers balance. It does not drift away.
- **Consequence:** over long times the price follows the true value, so its long-run random walk is
  an input (the amount of news), not a result of the order book. Results at long lags (e.g. H close
  to 0.5) cannot count as evidence. Shorter times, and the recovery after a shock, are still the
  order book's own. The news step is to be set from the long-run volatility of real data.

---

## 5. Still open

- **Depth-profile fit (D14):** whether the paper fits each side separately or combined.
- **Asymmetric flow (D16, D18):** the q_provider variant the paper mentions, and whether mirror vs
  blocked reflection matters.
- **Value trader settings (D28, D30).** How many there are, the size of their errors and the amount
  of news are not fitted to anything yet. They are to be set from real order book data.
- **Fat tails in the new model.** The basic model has none (kurtosis about 3, a Gaussian), with or
  without value traders. In Phase 1 they only came from Eq. 4, which depends on the trend in the
  takers' buy probability. Real markets have them, so the E-mini comparison will need a source of fat
  tails, e.g. providers that place orders further away when recent volatility is high. The true value
  design has not been tried in the Fig. 4 model yet.
- **Where the order book hands over to news.** Up to some time scale the price's randomness is the
  order book's own; beyond it, it follows the true value. Where that happens, and whether it matches
  real data, has not been measured.
- **Which mixes of agent types to compare,** and whether speed and size should also be varied
  separately (e.g. unit orders every 4 steps).
