# Decisions and assumptions log

Methodology decisions taken during the course of the project: what was done, why, and the
evidence behind it. For what is done and what comes next, see `project_plan.md`.

**[Paper]** = taken from the paper · **[Assumed]** = Paper unclear, so need to make own decision ·
**[Checked]** = verified against theory or tests · **[Open]** = not yet decided.

Decision numbers (D1, D2, ...) are fixed IDs in order of creation, not positions in this file, so
references to them from code comments stay valid when entries are moved.

Numbers quoted are from the runs named; see `results/` and the code version
recorded inside each results file.

---

## 1. Model

**D1. Base model and parameters. [Paper]**
Providers place limit orders (rate α, exponential depth λ₀ around the midpoint), takers place
market orders (rate μ), each resting order is removed with probability δ per step, unit order size,
price-time priority. Fig. 2 parameters: α=0.15, μ=0.025, δ=0.025, λ₀=100, q_provider=q_taker=0.5,
N_A = 125/250/500. Stability requires α(1−δ) > μ and δ > 0 (Eq. 1–3); the code refuses to run otherwise.

**D2. One "MCS" = one simulation step; agents are independent per step. [Assumed]**
The paper uses the term MCS (Monte Carlo step) without defining it. It is taken to be one step in
which every provider independently acts with probability α and every taker with probability μ, which
gives the αN_A limit orders and μN_A market orders per step that Eq. 1 requires.

**D3. Order of events within a step: providers → cancellation → takers. [Assumed, Checked]**
Not stated in the text, but implied by Eq. 1, N(t+1) = (N+αN_A)(1−δ) − μN_A.
Checked in `tests/test_simulation.py`: at test parameters α=0.3, μ=0.1, δ=0.2, Eq. 2 predicts 175
resting orders and the simulation gives ≈175, while the swapped order would give 200 (at the Fig. 2
parameters the two orders differ by only 0.5%, too little to tell apart).
The price recorded at the end of a step is read just after the takers have acted
and before providers replenish the book. This matters for short-lag results (see D11).

**D4. Cancellation applies to every resting order, including ones placed in the same step.
[Assumed, follows Eq. 1]** Each is removed independently with probability δ.

**D5. Entry depth: exponential with mean λ₀, rounded to the nearest tick; reference price is the
midpoint, or a fallback (the start price) while the book has no midpoint. [Assumed]**
The paper says "exponentially distributed" and "around the midpoint", but gives no rounding rule.
Prices are rounded to whole ticks. When there is no midpoint, the start price p(t₀) = 10⁶ is used,
the middle of the paper's 2×10⁶-tick book. In practice the fallback only matters during the
pre-opening; it would also apply if one side of the book emptied mid-run, which has not happened.

**D6. Marketable limit orders execute immediately at the resting order's price. [Paper, Assumed]**
The paper says limit orders execute "at the assigned limit or some better price". With unit orders,
a crossing limit order consumes one resting order. Provider orders rarely cross (depth ≥ 0 from
the midpoint), so this hardly affects results.

**D7. Pre-opening: 10 provider-only steps around p(t₀) = 10⁶. Prices are unbounded integers.
[Paper, Assumed]** The paper uses a book with 2×10⁶ price ticks; the tick grid here is not bounded.
Prices stay within a few thousand ticks of the start, so this should not matter.

### Asymmetric order flow (paper Fig. 3; `abm/agents.py`, `taker_flow` in `run_simulation`)

**D16. One market-wide q_taker(t), shared by every taker in a step; q_provider is left alone.
[Paper, Assumed]** The paper describes "a random walk of the variable q_taker", a single variable, so all
takers in a step use the same buy probability and a temporary imbalance (a "trend") builds up. Each
taker's own `q_taker` is overridden by the current shared value. The paper also says the results are
unchanged if q_provider is perturbed instead; that variant is **not implemented** (open).

**D17. Timing: takers use the current q, then q moves to its next value. [Assumed]** So the first
recorded step uses exactly q = 1/2 (the paper's q(t₀) = 1/2), and the pre-opening steps do not advance
it. Providers and cancellation are unaffected (they don't use q_taker). The q used at every step is
saved in `result.q_taker_series`, which Eq. 4 will need.

**D18. Bounded random walk (Fig. 3a): ±Δs with equal probability, reflected at 1/2 ± S by mirroring.
[Paper, Assumed]** Paper values Δs = 0.001, S = 0.05. "Reflecting boundary" is not defined in the
paper; this model mirrors a step that would leave the range back inside (k = K+1 becomes K−1, so from the bound
the walk always steps inward). The other natural reading, a blocked step that leaves q at the bound,
differs only in how much time is spent exactly at the bound; whether that matters is untested.
q is stored as an integer count of steps from 1/2 (q = 1/2 + k·Δs) so "at the centre" and "at a bound"
are exact comparisons, and S must be a whole multiple of Δs (otherwise an error).

**D19. Mean-reverting walk (Fig. 3c): moves toward 1/2 with probability 1/2 + |q − 1/2|, else away.
[Paper, Assumed tie-break, Checked]** Paper values Δs = 0.001, S = 1/2 (so q may range over [0, 1]).
At exactly q = 1/2 there is no "toward", so a fair coin is used (the paper doesn't say). *Derived, and
verified by test and simulation:* this is a discrete Ornstein–Uhlenbeck process. The average pull is
2Δs·(q − 1/2) per step, so q settles to a standard deviation of √(Δs/4) = 0.0158 (simulated: 0.0150,
`tests/test_agents.py` checks it within 15%) and forgets its history over about 1/(2Δs) = 500 steps.
So the S = 1/2 bound is effectively never reached. The 500-step memory also fits the paper-scale
Fig. 3c: H is above 1/2 from about Δτ ≈ 300 to 10⁴, with its peak near Δτ ≈ 10³.

**D20. Fig. 3 experiment setup. [Assumed, Checked]**
`experiments/run.py` (was `fig2.py`) runs one flow at a time: `--flow symmetric`, `bounded` or
`mean-reverting`. Each flow gets its own results file, which records the flow's settings. This stops
runs from different flows being mixed by `--resume`, or a file being plotted as the wrong panel. The
symmetric flow gives the same results as the old Fig. 2 runner, so `fig2_final.pkl` still works.

A new flow is made for every run, so each run starts at q = 1/2. Reusing one flow would start each
run where the last one finished.

Each run also saves ⟨(q − 1/2)²⟩ and the spread of q, which Eq. 4 needs. Checked against theory on
the 50-run data: the bounded walk spreads q evenly over [0.45, 0.55], so √⟨(q − 1/2)²⟩ should be
0.1/√12 = 0.0289 (measured 0.0288–0.0289). The mean-reverting walk should give Δs/4 = 2.50×10⁻⁴
(D19), and gives 2.50×10⁻⁴ for all N_A. This is the value Eq. 4 needs.

Only |Δp| histograms are saved, so the signed distributions in the Fig. 3 insets are made by
mirroring them (half the |Δp| density on each side of zero). This only works because both walks are
symmetric about q = 1/2, so the distributions are symmetric too. Like the paper, the inset shows all
four Δτ, which shows the bounded walk's distribution going from one peak (Δτ = 200) to two
(Δτ = 800 and 1600).

### Volatility-coupled entry depth (paper Fig. 4, Eq. 4; `depth_coupling` in `run_simulation`)

**D21. Eq. 4, with the derived value of √⟨(q − 1/2)²⟩. [Paper, Assumed, Checked]**
λ(t) = λ₀ (1 + |q_taker(t) − 1/2| / √⟨(q_taker − 1/2)²⟩ · C_λ), with λ₀ = 100 and C_λ = 10, on top of the
mean-reverting walk, as in the paper. It is only allowed with that walk.

The paper says the average in Eq. 4 is "determined separately before the main simulation", but gives
no procedure. The derived value √(Δs/4) = 0.0158 (D19) is used. The Fig. 3 runs measured the same
value (D20), so a separate calibration run is not needed.

Each step, λ(t) is worked out from that step's q, and every provider in the step uses it. The takers
use the same q (D17), so λ(t) and q_taker(t) always belong to the same step. The pre-opening uses λ₀.
The λ used at every step is saved in `result.lambda_series`, and each run stores its mean and maximum.

Checked: `tests/test_simulation.py` compares λ(t) with Eq. 4 at every step, and C_λ = 0 gives exactly
the same run as the fixed depth. With C_λ = 10, λ(t) averages about 900 ticks and reaches about
4,400 (trial runs), against a fixed 100 before.

---

## 2. Implementation choices that could change results

**D8. Two simulation methods: `"agents"` (reference) and `"fast"` (used for all results). [Checked]**
"agents" is the literal model: every agent flips its own coin, every order is tested for
cancellation. "fast" draws *how many* providers act, orders are cancelled and takers act from a
Binomial, then picks that many at random. This is exact in distribution because the agents are
identical and independent. Cost fell from ≈0.9 to ≈0.25 ms per step (N_A=250). Same seed gives
*different* runs under the two methods, so they are compared statistically
(`tests/test_simulation.py`; over 12 seeds: depth 485.9 vs 485.6, theory 485; trades/step 2.494 vs
2.502, theory 2.5).
*Limitation:* this shortcut only works for identical, independent agents. HFT agents that react to
the book cannot be aggregated, so Phase 2 will need a per-agent loop for them.

**D9. Reproducibility. [Checked]**
Python `random.Random`, seeds 0…n−1 per (N_A, run). Every results file records
the git commit, branch and whether the working tree was clean (`experiments/provenance.py`).
Environment for the reported runs: Python 3.14.6, numpy 2.5.0, matplotlib 3.11.0 on an Intel
i5-8365U laptop (4 cores / 8 threads). The fast method needs Python ≥ 3.12 (`random.binomialvariate`).

**D10. A book with an empty side aborts a Fig. 2 run instead of being patched. [Assumed]**
`run_simulation` itself records `None` as the mid-price for any step with an empty side and carries
on. The experiment runner (`experiments/run.py`) then refuses that run: building the price series raises an error naming the
seed, so a one-sided book stops the experiment rather than being interpolated over. Reason: for an
instability study, "the book went one-sided" is itself an event that should be seen. Not triggered in
any run so far (0 empty-book failures in all 150 runs of `fig2_final.pkl`).

---

## 3. Measurement choices

**D11. Which "price"? [Assumed: median trade price per step, adopted for the reported results]**
The paper says "price" without saying whether it means the mid-price or a trade price. In this
step-based model the answer changes the Hurst exponent at short lags substantially, because a trade
price "bounces" between bid and ask. Long-lag behaviour (H → 0.5) is the same for all.

Readings taken from the paper's Fig. 2c by eye: lowest H ≈ 0.08 near
Δτ ≈ 10, curve higher to the left; H(100) ≈ 0.22–0.25; reaches ≈ 0.5 at Δτ ≈ 10³–10⁴;
N_A = 500 is the lowest curve.

Five definitions compared on the paper-scale run (`fig2_final.pkl`, commit 393cdee: 10⁶ steps,
50 runs per N_A), values for N_A = 125 / 250 / 500:

| Price definition | lowest H (Δτ ≤ 200) | H(100) | first reaches H ≥ 0.48 at Δτ ≈ |
|---|---|---|---|
| last trade in step | 0.048 / 0.032 / 0.022 | 0.19 / 0.15 / 0.11 | 4,700–15,000 |
| **median trade in step** | **0.082 / 0.084 / 0.081** | **0.23 / 0.21 / 0.19** | **4,100–6,300** |
| first trade in step | 0.087 / 0.095 / 0.096 | 0.24 / 0.23 / 0.22 | 4,100–6,300 |
| mean of the step's trades | 0.127 / 0.140 / 0.133 | 0.28 / 0.28 / 0.26 | 2,300–2,600 |
| mid-price | 0.266 / 0.237 / 0.216 | 0.38 / 0.35 / 0.33 | 700–1,500 |

Median and first-trade both match the readings for the minimum and H(100). Only median also gives
the paper's ordering, with N_A = 500 lowest at the minimum (by a small margin); first-trade puts
N_A = 500 highest. Last-trade is too low and the mid-price far too high. The median trade price is
therefore used for the reported Fig. 2 (`results/fig2_final.png`). **This is calibrating an
unspecified detail, not a finding**, and the match rests on a few rough readings of a figure.
It must be reported as "the paper does not state its price definition; the median trade price per
step is used because it reproduces the short-lag behaviour of Fig. 2c". All five definitions remain
stored in every results file (`analysis/prices.py`), so the comparison can be redrawn.
*Why the definition matters here:* takers act in one block at the end of a step, so the last trade
of a step comes when the book is most depleted and the first trade comes right after replenishment.
The paper's own update scheme is probably different and is not specified (see D3).

**D12. Hurst exponent H(Δτ). [Assumed, Checked]**
Defined as in the paper by ⟨(Δp)²⟩^½(Δτ) ∝ Δτ^H, but reported as a *local* slope of log RMS vs log Δτ
(centred difference between neighbouring lags; one-sided difference at the first and last lag),
so H varies with Δτ as in Fig. 2c. RMS is over all overlapping windows p(t+Δτ) − p(t). Lags are ≈80
log-spaced values from 1 to n_steps/10. H is computed per run, then averaged over runs (not H of
averaged RMS). The paper does not specify its estimator. Validated on synthetic series: a straight
line gives H = 1 at every lag including the ends, a power law is recovered exactly, a random walk
gives ≈ 0.5 (`tests/test_hurst.py`). The earlier estimator dropped the end lags, so its curve
started at Δτ = 14 and ended near 7×10⁴; this hid the rise of H to the left of its minimum.
Long lags are noisy: few independent windows remain at Δτ ≳ 10⁴.

**D13. Scale and averaging. [Paper, Checked]**
As in the paper: 10⁶ steps, averaged over 50 runs per N_A. The reported Fig. 2 is `fig2_final.pkl`
(commit 393cdee, clean working tree, 150 runs, 0 empty-book failures). Mean book sizes are
606 / 1212 / 2425 orders against Eq. 2's 606 / 1212.5 / 2425.
*Approach to H = 0.5:* averaged over Δτ = 10³–10⁴, H is 0.492 / 0.487 / 0.488 (mid-price) and
0.477 / 0.469 / 0.468 (median) for N_A = 125 / 250 / 500, each ± 0.003–0.004 (standard error over
50 runs). This is significantly below 0.5 for every N_A, so it is not noise: H is still rising
through that window and only reaches ≈ 0.5 near Δτ ≈ 10⁴ (the median curve first passes 0.48 at
Δτ ≈ 4,100–6,300). This is consistent with the reading of the paper's Fig. 2c (H reaches ≈ 0.5 at
Δτ ≈ 10³–10⁴). An earlier 10-run trial (commit f9bae8f) had shown the same effect for N_A = 250 only,
at the edge of its noise.

**D14. Depth profile ⟨N(p − p_m)⟩ and its lognormal fit. [Assumed, Checked]**
Recorded at the end of every step over the last 10⁴ steps, N_A = 500, as resting orders per tick by
distance from the midpoint, stored in half-tick units (the midpoint can sit on a half tick) and
binned to 1 tick. The paper says it "can be described by a lognormal distribution" but gives no
fitting procedure, and scipy is not installed, so the fit method here is not the paper's
(`analysis/depth_profile.py`):
both sides are folded onto one axis (`combine_sides`, verified symmetric: 1212.2 vs 1212.8 total
weight on the 50-run data), then (μ, σ) come from a weighted quadratic regression of
ln(N(x)) + ln(x) against ln(x) — exact for a lognormal density, so no iteration is needed.
*Weighting matters a lot here and was tuned by inspection, not derived*: an unweighted regression, a
regression weighted just by count, and an earlier method-of-moments attempt all put the fitted peak
25–50% further from the midpoint than the data's actual peak (a method-of-moments fit on the full
50-run data put it at 53 ticks against an actual 34–35), because those all let the noisy far tail
pull the fit. Weighting by count² (effectively count⁴ on the squared residual, since numpy's own
`w` parameter already applies one power) keeps the fit close to the bulk of the distribution;
mode ≈ 36.8 ticks, peak height ≈ 9.4, both close to the data's ≈35 / ≈10 (`results/fig2_final.png`,
panel b).
*Also found and fixed while building this*: fitting to the folded (both-sides-combined) profile
gives the *combined* mass at each distance; plotting that curve mirrored onto both sides of the
book (without halving it) double-counts, since each side only has half that mass. **[Open]**
whether the paper fits each side separately, combined as here, or some other way; and how much its
fit deviates from its data (the paper's figure has not been compared directly for fit quality; the
paper itself calls the lognormal description "phenomenological", i.e. approximate).

**D15. Return distributions. [Assumed, Checked]**
Price *increments* p(t+Δτ) − p(t) (not log returns), as in the paper, for Δτ = 200, 400, 800, 1600
at N_A = 500. Plotted as |Δp| on log-log axes with log-spaced bin edges. Each price definition
(D11) needs edges on its own grid: the mid-price only takes multiples of 0.5 tick, a trade price
only takes whole ticks. Edges are placed half a grid step off every grid multiple, so each bin
holds a whole number of grid values.
*Bug found and fixed (commit 393cdee):* the first version built one set of edges, sized for
the 0.5-tick (mid-price) grid, and used it for every price definition. Applied to a trade price
(whole ticks), alternating bins then caught one grid point or none, producing a visible zigzag in
panel (d) for `last`/`first`/`median`/`mean` (`fig2_full.png`, spotted by the user). `mid` was
unaffected, and panel (c), which is RMS-based, is unaffected either way. Fixed by building edges
per price definition (`make_bin_edges` in `experiments/run.py`, then called `fig2.py`); guarded by
`tests/test_run.py`, which includes a test that reproduces the original bug on mismatched
edges. The affected results were regenerated in `fig2_final.pkl` (the Hurst values in it are
identical to the earlier run's, as expected, since the simulation code did not change).
Increments below half a grid step (including zero) fall outside the bins. **[Open]** the paper's
axis convention for panel (d) is unconfirmed. Kurtosis estimated from the binned counts (mid-price):
2.7–2.9 (Gaussian = 3), rising with Δτ, so no fat tails in the symmetric model, as the paper reports.
This is only approximate.

**D22. Return bins reach 50,000 ticks, and anything beyond is counted. [Assumed, Checked]**
The paper's Fig. 4b shows price changes out to ±4,000 ticks, close to the old 5,000-tick limit of the
bins. So the bins now go to 50,000 ticks (about 11 bins per factor of 10, as before). Increments
beyond the last bin would be left out of the histogram without any sign, so each run now also counts
them, and the plotter warns if there are any. None so far. Results files made before this change keep
their own bin edges, so they still plot correctly.

For Fig. 4b the distribution is drawn as the paper does: signed Δp (made by mirroring, as in D20) on a
linear axis in ticks/10³, against P(Δp) on a log axis. On these axes an exponential tail is a straight
line. The same model without Eq. 4 can be added as dashed lines for comparison.

---

## 4. What has and has not been compared with the paper

- **Fig. 2, reproduced qualitatively at paper scale** (`fig2_final.png`, 10⁶ steps, 50 runs per N_A):
  price-path scale (±1000 ticks in 10⁶ steps), depth profile shape and its lognormal fit (D14),
  H(Δτ) anti-persistent at short lags with its minimum ≈ 0.08 near Δτ ≈ 10 and rising to ≈ 0.5 by
  Δτ ≈ 10⁴ (with the median trade price, D11), and Gaussian return distributions.
- **Fig. 3, reproduced qualitatively at paper scale** (`fig3_final.png`, 10⁶ steps, 50 runs per N_A,
  commit a65a28c, median trade price; D16–D20).
  - Bounded walk: H peaks at 0.80 / 0.84 / 0.87 (N_A = 125 / 250 / 500) near Δτ ≈ 10³, and is back to
    0.5 by Δτ ≈ 7×10⁴. Paper: "up to 0.9", then 1/2 at long lags. The return distribution goes from one
    peak at Δτ = 200 to two peaks at Δτ = 800 and 1600 (at ±150 ticks for Δτ = 1600), as in the paper's
    bimodal distribution and its inset. The inset's height (0.0136 at Δτ = 200) also matches the
    paper's (about 0.012).
  - Mean-reverting walk: H peaks at 0.56 / 0.60 / 0.63 near Δτ ≈ 10³, and is back to 0.5 by
    Δτ ≈ 1–3×10⁴. Paper: closer to real markets, where H is at most about 0.6. The return distributions
    have one peak and a kurtosis of 2.75–2.95, close to Gaussian (3). Paper: approximately Gaussian.
  - In both, a larger N_A gives a higher peak H.
- Fig. 4, trial only (10⁵ steps, 4 runs per N_A, median trade price; `results/fig4_trial.png`; D21, D22).
  With Eq. 4 the return distributions have fat tails: at Δτ = 1600 they reach about ±4,000 ticks,
  and the tails are close to straight lines on the semi-log plot (exponential), as in the paper.
  Kurtosis is 5.5–8.8, against 2.7–2.9 for the same model with a fixed depth. H(Δτ) keeps the same
  shape as in Fig. 3c (peak about 0.62–0.71 near Δτ ≈ 10³). Paper: "qualitatively the same". Not a
  reproduction until the paper-scale run is done.

## 5. Still open

- **Depth-profile fit (D14):** whether the paper fits each side separately or combined.
- **Asymmetric flow (D16, D18):** the q_provider variant the paper mentions, and whether mirror vs
  blocked reflection matters.
- **Baseline tag:** tagging the finished baseline (`baseline-v1`) as the control model.
