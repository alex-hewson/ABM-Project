# Decisions and assumptions log

Things that will need explaining or defending when the thesis is written: every point where the
paper (Preis, Golke, Paul & Schneider 2006, *EPL* 75, 510) was silent or ambiguous, every
implementation choice that could change results, and how each was checked. Keep this up to date
as the project goes on; it is meant to be raided for the methodology chapter.

Status tags: **[Paper]** taken from the paper · **[Assumed]** our choice, paper silent ·
**[Checked]** verified against theory or tests · **[Open]** not yet decided.

Numbers quoted are from the runs named; see `results/` (not tracked by git) and the code version
recorded inside each results file.

---

## 1. Model specification

**D1. Base model and parameters. [Paper]**
Providers place limit orders (rate α, exponential depth λ₀ around the midpoint), takers place
market orders (rate μ), each resting order is removed with probability δ per step, unit order size,
price-time priority. Fig. 2 parameters: α=0.15, μ=0.025, δ=0.025, λ₀=100, q_provider=q_taker=0.5,
N_A = 125/250/500. Stability requires α(1−δ) > μ and δ > 0 (Eq. 1–3); the code refuses to run otherwise.

**D2. One "MCS" = one simulation step; agents are independent per step. [Assumed]**
The paper never defines an MCS precisely. We take it to be one step in which every provider
independently acts with probability α and every taker with probability μ (so about αN_A limit
orders and μN_A market orders per step, as Eq. 1 requires).

**D3. Order of events within a step: providers → cancellation → takers. [Assumed, Checked]**
Not stated in the text, but implied by Eq. 1, N(t+1) = (N+αN_A)(1−δ) − μN_A. An earlier version
did providers → takers → cancellation. At the Fig. 2 parameters the two orders differ by only
0.5% in equilibrium depth, so tests use faster parameters (α=0.3, μ=0.1, δ=0.2) where Eq. 2
predicts 175 orders and the swapped order would give 200; the simulation gives ≈175
(`tests/test_simulation.py`, verified to fail if the order is swapped).
*Consequence:* the price recorded at the end of a step is read just after the takers have acted
and before providers replenish the book. This matters for short-lag results (see D12).

**D4. Cancellation applies to every resting order, including ones placed in the same step.
[Assumed, follows Eq. 1]** Each is removed independently with probability δ.

**D5. Entry depth: exponential with mean λ₀, rounded to the nearest tick; reference price is the
midpoint, or a fallback (the start price) while the book has no midpoint. [Assumed]**
The paper says "exponentially distributed" and "around the midpoint". Rounding rule and the
fallback are ours. The fallback only matters during the pre-opening.

**D6. Marketable limit orders execute immediately at the resting order's price. [Paper, Assumed]**
The paper says limit orders execute "at the assigned limit or some better price". With unit orders,
a crossing limit order consumes one resting order. Provider orders rarely cross (depth ≥ 0 from
the midpoint), so this hardly affects results.

**D7. Pre-opening: 10 provider-only steps around p(t₀) = 10⁶. Prices are unbounded integers.
[Paper, Assumed]** The paper uses a book with 2×10⁶ price ticks; we do not bound the tick grid.
Prices stay within a few thousand ticks of the start, so this should not matter.

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
Python `random.Random` (Mersenne Twister), seeds 0…n−1 per (N_A, run). Every results file records
the git commit, branch and whether the working tree was clean (`experiments/provenance.py`).
Environment for the reported runs: Python 3.14.6, numpy 2.5.0, matplotlib 3.11.0 on an Intel
i5-8365U laptop (4 cores / 8 threads). The fast method needs Python ≥ 3.12 (`random.binomialvariate`).

**D10. A book with an empty side aborts a run instead of being patched. [Assumed]**
If the midpoint is undefined at any step the run raises an error naming the seed, instead of
interpolating. Reason: for an instability study, "the book went one-sided" is itself an event that
should be seen. Not triggered in any run so far (0 empty-book failures in all N_A).

---

## 3. Measurement choices

**D11. Which "price"? [OPEN. The single most important pending decision]**
The paper says "price" without saying whether it means the mid-price or a trade price. In our
step-based model the answer changes the Hurst exponent at short lags substantially, because a trade
price "bounces" between bid and ask. Long-lag behaviour (H → 0.5) is the same for all.

Readings taken from the paper's Fig. 2c by eye (by the user, not by overlay): lowest H ≈ 0.08 near
Δτ ≈ 10, curve higher to the left; H(100) ≈ 0.22–0.25; reaches ≈ 0.5 at Δτ ≈ 10³–10⁴;
N_A = 500 is the lowest curve.

Minimum of H(Δτ) for Δτ ≤ 100, N_A = 250 / 500 (2 seeds, 10⁵ steps, single runs, ±0.005):

| Price definition | min H | H(100) |
|---|---|---|
| last trade in step | 0.03 / 0.02 | 0.15 / 0.11 |
| random trade in step | 0.05 / 0.04 | 0.18 / 0.16 |
| **median trade in step** | **0.08 / 0.07** | **0.20–0.22 / 0.19–0.20** |
| **first trade in step** | **0.086 / 0.088** | **0.22–0.23 / 0.22** |
| mean of the step's trades | 0.13 / 0.12 | 0.27 / 0.26 |
| mid-price | 0.22 / 0.21 | 0.34 / 0.34 |

Median and first-trade match the readings; "median" also gives the right N_A ordering; last-trade
is too low; the mid-price is far too high. **This is calibrating an unspecified detail, not a
finding**, and the match rests on three rough readings of a figure. Whatever is chosen must be
reported as "the paper does not state its price definition; we use X because it reproduces the
short-lag behaviour of Fig. 2c". The runner now stores all five definitions
(`analysis/prices.py`), and `plot_fig2.py` draws a comparison, so the choice can be made after the
full run.
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

**D13. Scale and averaging. [Paper, Assumed]**
Paper: 10⁶ steps, average over 50 runs. Medium trial (commit f9bae8f, mid-price, old estimator):
10⁶ steps × 10 runs per N_A, ≈1 hour. Results: mean book size 606 / 1212 / 2425 orders vs Eq. 2's
606 / 1212.5 / 2425. N_A=250 read H = 0.477 ± 0.008 over Δτ = 10³–10⁴, about 3 standard errors below
0.5; may be a slow approach, recheck with 50 runs. The final number of runs is still to be chosen.

**D14. Depth profile ⟨N(p − p_m)⟩. [Assumed]**
Recorded at the end of every step over the last 10⁴ steps, N_A = 500, as resting orders per tick by
distance from the midpoint, stored in half-tick units (the midpoint can sit on a half tick) and
binned to 1 tick. The paper says it "can be described by a lognormal distribution"; how it was fitted
is not stated. **[Open]** the fitting method. Our profile peaks at ≈10 orders/tick near ±35 ticks with
a gap at the midpoint; the paper's axis reaches ≈12.

**D15. Return distributions. [Assumed]**
Price *increments* p(t+Δτ) − p(t) (not log returns), as in the paper, for Δτ = 200, 400, 800, 1600
at N_A = 500. Plotted as |Δp| on log-log axes with log-spaced bins whose edges are placed a quarter
tick off the half-tick price grid (otherwise bins catch uneven numbers of grid values and produce
spurious bumps). Increments below 0.75 ticks (including zero) fall outside the bins. **[Open]** the
paper's axis convention for panel (d) is unconfirmed. Kurtosis estimated from the binned counts:
2.7–2.9 (Gaussian = 3), rising with Δτ, so no fat tails in the symmetric model, as the paper reports.
This is only approximate.

---

## 4. What has and has not been compared with the paper

- The paper's *figures* have not been overlaid. Only its text was read programmatically; comparisons to
  Fig. 2 rest on the user's readings of the PDF. An overlay or digitised curves would be stronger.
- Reproduced (qualitatively): price-path scale (±1000 ticks in 10⁶ steps), depth profile shape,
  anti-persistent H at short lags rising to ≈ 0.5, Gaussian return distributions.
- Not yet reproduced or checked: exact short-lag H (D11), the lognormal fit, Figs. 3 and 4.

## 5. To decide later

- **Price definition** (D11), then re-run at the chosen scale.
- **Lognormal fit** for the depth profile (D14).
- **Asymmetric flow (Fig. 3):** the bounded random walk's reflecting boundary at ½ ± S and the
  mean-reverting step probability ½ + |q − ½| are described in words; the exact implementation
  (what "reflecting" does at the boundary, whether q_taker is shared by all takers each step) is ours.
- **Eq. 4 (volatility-coupled depth):** ⟨(q_taker − ½)²⟩ is "determined separately before the main
  simulation"; the paper gives no procedure, so the calibration run must be designed and documented.
- **Number of runs** for the final baseline, and tagging it (`baseline-v1`) as the control model.
