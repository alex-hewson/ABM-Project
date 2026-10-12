# Checks and comparison with the paper

The evidence behind `decisions.md`: tests, numbers from the runs, and how the results compare with
the paper. D numbers refer to `decisions.md`, P numbers to `paper_model.md`.

Numbers quoted are from the runs named; see `results/` and the code version recorded inside each
results file.

---

## 1. Model checks

**Order of events (D3).** Checked in `tests/test_simulation.py`: at test parameters α=0.3, μ=0.1,
δ=0.2, Eq. 2 predicts 175 resting orders and the simulation gives ≈175, while the swapped order would
give 200. At the Fig. 2 parameters the two orders differ by only 0.5%, too little to tell apart.

**Book size (Eq. 2).** In the paper-scale Fig. 2 run the mean book sizes are 606 / 1212 / 2425 orders
(N_A = 125 / 250 / 500) against Eq. 2's 606 / 1212.5 / 2425. No run had an empty side of the book
(0 failures in 150 runs; D10).

**Fast method (D8).** Cost fell from ≈0.9 to ≈0.25 ms per step (N_A=250). The same seed gives
different runs under the two methods, so they are compared statistically
(`tests/test_simulation.py`; over 12 seeds: depth 485.9 vs 485.6, theory 485; trades/step 2.494 vs
2.502, theory 2.5).

**Hurst estimator (D12).** Validated on synthetic series: a straight line gives H = 1 at every lag
including the ends, a power law is recovered exactly, a random walk gives ≈ 0.5
(`tests/test_hurst.py`).

**Mean-reverting walk (D19).** The average pull is 2Δs·(q − 1/2) per step, so this is a discrete
Ornstein–Uhlenbeck process. q settles to a standard deviation of √(Δs/4) = 0.0158 (simulated: 0.0150,
`tests/test_buy_probability.py` checks it within 15%) and forgets its history over about
1/(2Δs) = 500 steps. So the S = 1/2 bound is effectively never reached. The 500-step memory also fits
the paper-scale Fig. 3c: H is above 1/2 from about Δτ ≈ 300 to 10⁴, with its peak near Δτ ≈ 10³.

**Spread of q (D20, D21).** Checked against theory on the 50-run data. The bounded walk spreads q
evenly over [0.45, 0.55], so √⟨(q − 1/2)²⟩ should be 0.1/√12 = 0.0289 (measured 0.0288–0.0289). The
mean-reverting walk should give ⟨(q − 1/2)²⟩ = Δs/4 = 2.50×10⁻⁴, and gives 2.50×10⁻⁴ for all N_A.
This is the value Eq. 4 needs.

**Eq. 4 (D21).** `tests/test_simulation.py` compares λ(t) with Eq. 4 at every step, and C_λ = 0 gives
exactly the same run as the fixed depth. With C_λ = 10, λ(t) averages about 900 ticks and reaches at
most 5,792 (paper-scale run), against a fixed 100 before.

## 2. Choice of price (D11)

Readings taken from the paper's Fig. 2c by eye: lowest H ≈ 0.08 near Δτ ≈ 10, curve higher to the
left; H(100) ≈ 0.22–0.25; reaches ≈ 0.5 at Δτ ≈ 10³–10⁴; N_A = 500 is the lowest curve.

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
N_A = 500 highest. Last-trade is too low and the mid-price far too high.

*Why the definition matters here:* takers act in one block at the end of a step, so the last trade
of a step comes when the book is most depleted and the first trade comes right after replenishment.
The paper's own update scheme is probably different and is not specified (see D3).

## 3. Fig. 2

**Reproduced qualitatively at paper scale** (`fig2_final.png`, 10⁶ steps, 50 runs per N_A, commit
393cdee, clean working tree): price-path scale (±1000 ticks in 10⁶ steps), depth profile shape and
its lognormal fit, H(Δτ) anti-persistent at short lags with its minimum ≈ 0.08 near Δτ ≈ 10 and
rising to ≈ 0.5 by Δτ ≈ 10⁴ (with the median trade price), and Gaussian return distributions.

**Approach to H = 0.5.** Averaged over Δτ = 10³–10⁴, H is 0.492 / 0.487 / 0.488 (mid-price) and
0.477 / 0.469 / 0.468 (median) for N_A = 125 / 250 / 500, each ± 0.003–0.004 (standard error over
50 runs). This is significantly below 0.5 for every N_A, so it is not noise: H is still rising
through that window and only reaches ≈ 0.5 near Δτ ≈ 10⁴ (the median curve first passes 0.48 at
Δτ ≈ 4,100–6,300). This is consistent with the reading of the paper's Fig. 2c (H reaches ≈ 0.5 at
Δτ ≈ 10³–10⁴).

**Depth profile fit (D14).** The two sides are symmetric (1212.2 vs 1212.8 total weight on the 50-run
data). The weighted fit gives mode ≈ 36.8 ticks and peak height ≈ 9.4, both close to the data's
≈35 / ≈10. An unweighted regression, a regression weighted just by count, and a method-of-moments
fit all put the fitted peak 25–50% further from the midpoint than the data's actual peak (method of
moments: 53 ticks against an actual 34–35), because they let the noisy far tail pull the fit. The
paper's figure has not been compared directly for fit quality.

**Return distributions (D15).** Kurtosis estimated from the binned counts (mid-price): 2.7–2.9
(Gaussian = 3), rising with Δτ, so no fat tails in the symmetric model, as the paper reports. This is
only approximate.

## 4. Fig. 3

**Reproduced qualitatively at paper scale** (`fig3_final.png`, 10⁶ steps, 50 runs per N_A, commit
a65a28c, median trade price).

- Bounded walk: H peaks at 0.80 / 0.84 / 0.87 (N_A = 125 / 250 / 500) near Δτ ≈ 10³, and is back to
  0.5 by Δτ ≈ 7×10⁴. Paper: "up to 0.9", then 1/2 at long lags. The return distribution goes from one
  peak at Δτ = 200 to two peaks at Δτ = 800 and 1600 (at ±150 ticks for Δτ = 1600), as in the paper's
  bimodal distribution and its inset. The inset's height (0.0136 at Δτ = 200) also matches the
  paper's (about 0.012).
- Mean-reverting walk: H peaks at 0.56 / 0.60 / 0.63 near Δτ ≈ 10³, and is back to 0.5 by
  Δτ ≈ 1–3×10⁴. Paper: closer to real markets, where H is at most about 0.6. The return distributions
  have one peak and a kurtosis of 2.75–2.95, close to Gaussian (3). Paper: approximately Gaussian.
- In both, a larger N_A gives a higher peak H.

## 5. Fig. 4

**Reproduced at paper scale** (`fig4.png`, 10⁶ steps, 50 runs per N_A, commit acd8ebe, median trade
price). λ(t) averaged 898 ticks, with a maximum of 5,792 in any run.

- Return distributions (N_A = 500) have fat, exponential tails: straight lines on the semi-log plot.
  Kurtosis is 9.4 / 9.3 / 8.4 / 6.9 for Δτ = 200 / 400 / 800 / 1600, against 2.75–2.95 for the same
  model with a fixed depth. The tail widths match readings taken from the paper's Fig. 4b by eye:

  | Δτ | Paper (by eye) | Here |
  |---|---|---|
  | 200 | reaches 10⁻⁷ at Δp ≈ 2,000–2,500 | 2,170 |
  | 400 | reaches 10⁻⁷ at Δp ≈ 3,000–3,500 | 3,160 |
  | 800 | P(4,000) about halfway between 10⁻⁶ and 10⁻⁷ | 3.5×10⁻⁷ |
  | 1600 | P(4,000) between 10⁻⁵ and 10⁻⁶, closer to 10⁻⁵ | 2.6×10⁻⁶ |

  Only Δτ = 1600 is a little low, by less than a factor of 2. The paper's curves look noisy because
  it seems to plot every Δp value; the log bins here (D22) average neighbouring values, so the
  curves are smooth.
- H(Δτ) has the same shape as in Fig. 3c, with a higher peak: 0.62 / 0.66 / 0.70 (N_A = 125 / 250 /
  500) near Δτ ≈ 600–800, against 0.56 / 0.60 / 0.63 without Eq. 4. The paper's Fig. 4a peak is also
  slightly higher than its Fig. 3c peak (above 0.7 against just under 0.7). Its peaks are a little
  higher than the ones here. With the mid-price the peaks are 0.67 (Fig. 3c) and 0.74 (Fig. 4a) for
  N_A = 500, closer to the paper's. So the median trade price, chosen to match Fig. 2c at short
  lags, may slightly lower the peak heights. This is a small offset and does not change any
  conclusion.

## 6. Code versions

**Baseline (D23).** The tag `baseline-v1` is on the commit that split the docs into
`paper_model.md`, `decisions.md` and this file. It was first put on commit ce38110 and then moved
forward, so that the baseline has the tidied files.

The three figures were made at earlier commits: Fig. 2 at 393cdee, Fig. 3 at a65a28c, Fig. 4 at
acd8ebe. The Fig. 2 and Fig. 3 runs used older code, but the later changes only added options (the
walks, Eq. 4) that are switched off for those figures.

Since the Fig. 4 run the model has not changed. The buy-probability classes were moved from
`abm/agents.py` to `abm/buy_probability.py` (commit 71850fe); the code was moved, not changed. Two
small edits (an added check in `orderbook.py`, and passing `rng` on in `agents.py`) do not change
behaviour. All 108 tests pass.

**Environment (D9).** Python 3.14.6, numpy 2.5.0, matplotlib 3.11.0 on an Intel i5-8365U laptop
(4 cores / 8 threads).

## 7. Bugs found and fixed

**Return histogram bins (D15; fixed in commit 393cdee).** The first version built one set of bin
edges, sized for the 0.5-tick (mid-price) grid, and used it for every price definition. Applied to a
trade price (whole ticks), alternating bins then caught one grid point or none, producing a visible
zigzag in panel (d). The mid-price was unaffected, and panel (c), which is RMS-based, is unaffected
either way. Fixed by building edges per price definition (`make_bin_edges` in `experiments/run.py`);
`tests/test_run.py` includes a test that reproduces the original bug on mismatched edges. The
affected results were regenerated in `fig2_final.pkl`.

**Lognormal fit drawn too high (D14).** Fitting to the folded (both sides combined) profile gives
the combined mass at each distance. Plotting that curve mirrored onto both sides of the book without
halving it double-counts, since each side only has half that mass.

**Hurst curve cut short (D12).** The earlier estimator dropped the first and last lags, so its curve
started at Δτ = 14 and ended near 7×10⁴. This hid the rise of H to the left of its minimum.
