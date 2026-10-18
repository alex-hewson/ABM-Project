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

**Order sizes (D26).** Adding order sizes to the order book left the baseline unchanged: the test
for D23 still gives the same numbers, and a shock run gives the same result as before. A plain run
is about 8% slower (0.22 to 0.24 ms per step, N_A = 250), because every order now carries and checks
a size.

**Agent types (D27).** Checked in `tests/test_simulation.py` at test parameters α=0.3, μ=0.1, δ=0.2,
N_A=250, where Eq. 2 gives 175 units and μN_A = 25 units traded per step:

| All agents of type | Providers: settled volume | Takers: units traded per step | Takers: settled volume |
|---|---|---|---|
| 1 unit every step | 174.4 | 24.88 | 175.1 |
| 2 units every 2 steps | 175.5 | 24.85 | 175.5 |
| 4 units every 4 steps | 173.6 | 25.08 | 174.5 |

So each type supplies and removes the same volume, and Eq. 2 holds in units. Bigger orders mean
fewer of them for the same volume (174, 89 and 45 resting orders). A mixed population (100 / 100 /
50 of the three types, for both providers and takers) settles at 175.3 units with 24.96 traded per
step. The fast and per-agent methods agree for that mix (174.8 vs 175.4 units, 24.88 vs 25.04
traded per step, over 6 seeds each).

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

## 8. Shock test on the basic model

One market sell order of 50, 150 or 300 units, injected after 2,000 steps (D24). Basic model
(Fig. 2 parameters), N_A = 250, mean of 400 runs per size, 2,000 steps recorded after the shock
(`results/shock_test.png`, made with `experiments/shock.py`, commit e3de4d1 plus the shock code).
Measures as in D25. Before the shock each side of the book holds 606 orders and the spread is 23.2
ticks.

| Size | Price at the shock | Price at the end | Share recovered | Spread at the shock | Spread half-life | Bids at the shock | Bids half-life | Bids 90% back |
|---|---|---|---|---|---|---|---|---|
| 50 | −7.9 | −6.5 | 0.20 | 39.2 | 2 steps | 557 | 28 steps | 89 steps |
| 150 | −18.0 | −18.2 | 0.00 | 59.3 | 1 step | 457 | 27 steps | 90 steps |
| 300 | −38.0 | −40.0 | −0.05 | 99.2 | 1 step | 307 | 28 steps | 90 steps |

Prices are changes in ticks from the step before the shock. The control with no shock ends at +1.0
ticks, so differences of 1–2 ticks are noise. That covers the 0.20 for size 50 (1.4 ticks).

- **The price does not recover.** It drops at the shock and stays there for the rest of the run.
  There is nothing in the model that knows the old price: providers place orders around the current
  midpoint.
- **The drop is half of the widening of the spread** (8 / 18 / 38 ticks against widenings of
  16 / 36 / 76). The sell order removes the top of the bid side; the ask side does not move, so the
  midpoint falls by half the gap. New orders then fill the gap around the new midpoint.
- **The spread closes in one or two steps.** About 37 new limit orders arrive each step, and many
  land inside the gap.
- **The bid side refills as Eq. 1 predicts.** A shortfall shrinks by a factor (1 − δ) each step, which
  gives a half-life of ln 2 / δ = 27.7 steps and 90% after ln 10 / δ = 92 steps (measured: 27–28 and
  89–90). The refill time does not depend on the size of the shock.
- The ask side is not affected.

## 9. Shock test with different provider types (first look)

The shock test of section 8, repeated with the providers changed (D27). Takers are the paper's.
Sizes 150 and 300, mean of 200 runs each (`results/shock_providers2.png`, `shock_providers4.png`,
`shock_mixed.png`; commit 26eafb2 plus the agent-type code). The first row is section 8 (400 runs).

| Providers | Spread before | Price at the shock (150 / 300) | Bids half-life (150 / 300) | Bids 90% back (150 / 300) |
|---|---|---|---|---|
| all 1 unit every step | 23.2 | −18.0 / −38.0 | 27 / 28 steps | 90 / 90 steps |
| all 2 units every 2 steps | 22.2 | −18.5 / −38.7 | 29 / 28 | 93 / 97 |
| all 4 units every 4 steps | 21.8 | −18.0 / −37.9 | 27 / 28 | 85 / 86 |
| 100 / 100 / 50 of the three | 22.5 | −17.5 / −37.7 | 29 / 28 | 86 / 90 |

- **The provider type makes no clear difference to the average recovery.** The price impact and the
  refill time are the same within noise for every mix. The price still does not come back.
- This is expected. Every type supplies the same volume per step, and the refill time is set by the
  cancellation probability δ (section 8), which is the same for all of them.
- The spread before the shock is slightly narrower with bigger orders (21.8 against 23.2 ticks).
  Whether that difference is real has not been checked.
- Only averages over runs were compared. Bigger, slower orders should make single runs lumpier,
  which an average does not show.

## 10. Shock test with value traders

*First design, with a moving average of the price as the reference. Replaced by the true value (D30);
see section 12.*

The shock test of section 8, with some of the 250 takers replaced by value traders (D28). Sell orders
of 150 and 300 units, mean of 200 runs each (`results/shock_value50.png`, `shock_value125.png`,
`shock_value125_spread10.png`; commit a6777e4 plus the value trader code). The first row is section 8.

Price change in ticks, measured from the step before the shock, for the 300-unit order:

| Value traders | Mean shift | At the shock | +10 steps | +50 | +100 | +200 | +500 | Half-life |
|---|---|---|---|---|---|---|---|---|
| none | – | −38.0 | −39.2 | −37.7 | −36.8 | −36.8 | −39.7 | never |
| 50 | 50 ticks | −37.7 | −31.3 | −23.2 | −18.5 | −10.8 | −5.9 | 101 steps |
| 125 | 50 ticks | −36.3 | −17.9 | −9.1 | −6.0 | −2.0 | −1.2 | 10 steps |
| 125 | 10 ticks | −34.1 | −7.5 | 0.0 | 0.0 | 0.0 | −0.2 | 3 steps |

- **With value traders the price comes back.** With 125 of them it recovers half of the drop in 10
  steps and 90% in 136 steps. The 150-unit order behaves the same way (half-life 13 steps).
- **More value traders, or values closer together, give a faster recovery.** With 50 traders the
  half-life is about 100 steps. With shifts of 10 ticks instead of 50 it is 3 steps.
- **The size of the first drop barely changes** (−34 to −38 ticks). The value traders act after the
  shock, not during it.
- **The bid side refills as before:** half-life 25–27 steps, 90% after 80–93 steps. The refill is still
  set by δ (section 8). So the price recovers faster than the book when there are many value traders.
- **The market stays stable.** No market order went unfilled. The book holds slightly more (613–648
  units per side against 606).
- **Side effects in normal times.** The spread is narrower (20.7, 18.1 and 12.4 ticks against 23.2),
  because value traders often rest orders inside it. In a trial of 48 runs the price also wandered
  less: a standard deviation of 8 ticks over 2,000 steps against 18.5 without value traders.

Checked in `tests/test_simulation.py`: 30 steps after a 300-unit sell, the price has come back by 32
ticks on average with 125 value traders (mean shift 10) and by 6 ticks without (20 runs each; the 6
is noise). The fast and per-agent methods agree with value traders present (volume 1238 vs 1243,
spread 18.1 vs 18.5).

## 11. What value traders do to the price in normal times (first look)

*First design, with a moving average of the price as the reference. Replaced by the true value (D30);
see section 12.*

No shock. A share of the takers are value traders (D28, with the default window of 1,000 steps and
mean shift of 50 ticks). 10⁵ steps, 8 runs per N_A, values for N_A = 500 with the median trade price
(`results/side_basic.png`, `side_fig4.png`, made with `plot.py compare`; commit 0282299 plus the
runner options). This is a first look, not a paper-scale run: the lags only reach 10⁴ steps.

RMS and kurtosis are of the price change over 800 steps. The two autocorrelations (D29) are at a
lag of one 50-step block.

**Basic model (Fig. 2 settings)**

| Value traders | H(10) | H(100) | H(10³) | H(10⁴) | RMS | Kurtosis | Autocorr. of changes | Autocorr. of their size |
|---|---|---|---|---|---|---|---|---|
| none | 0.08 | 0.20 | 0.38 | 0.50 | 30.6 | 2.96 | −0.38 | 0.08 |
| 10% | 0.08 | 0.14 | 0.28 | 0.72 | 21.9 | 3.04 | −0.41 | 0.12 |
| 20% | 0.07 | 0.09 | 0.26 | 0.75 | 17.1 | 2.95 | −0.44 | 0.14 |
| 50% | 0.06 | 0.03 | 0.13 | 0.62 | 12.5 | 2.85 | −0.46 | 0.16 |

**Full model (Fig. 4 settings: mean-reverting walk and Eq. 4)**

| Value traders | H(10) | H(100) | H(10³) | H(10⁴) | RMS | Kurtosis | Autocorr. of changes | Autocorr. of their size |
|---|---|---|---|---|---|---|---|---|
| none | 0.09 | 0.38 | 0.68 | 0.53 | 676.5 | 16.55 | −0.27 | 0.36 |
| 20% | 0.02 | 0.01 | 0.05 | 0.37 | 87.1 | 5.11 | −0.50 | 0.40 |
| 50% | 0.01 | 0.00 | 0.01 | 0.30 | 48.4 | 4.46 | −0.49 | 0.36 |

- **Value traders hold the price close to its own recent average.** H falls well below 0.5 for lags
  up to about the window length (1,000 steps), and the price moves less: the RMS change over 800
  steps falls from 30.6 to 12.5 ticks in the basic model.
- **In the full model they remove the trend.** With 20% value traders the peak in H near 10³ (0.68)
  is gone (0.05), and the price moves about 8 times less. The paper's Fig. 3 and Fig. 4 behaviour
  does not survive at these settings.
- **Fat tails get weaker but do not vanish** in the full model (kurtosis 16.6, then 5.1 and 4.5,
  against 3 for a Gaussian). In the basic model the distribution stays Gaussian.
- **Volatility clustering is unchanged in the full model:** the size of price changes stays
  correlated for about 700 steps, with or without value traders. It comes from Eq. 4, where the entry
  depth follows the trend. The basic model has almost none (0.08 at the first lag only).
- **At lags past the window, H in the basic model rises above 0.5** (0.62–0.75 at 10⁴). This was
  first put down to the price catching up once free of the window. That was wrong: it is a drift
  built into this design (section 12). Runs of 10⁵ steps cannot show whether H then
  returns to 0.5; that needs longer runs.

**What this means.** At these settings the value traders are too strong for normal times. Real
prices have H close to 0.5 and no autocorrelation in their changes. So there is a trade-off: value
traders are needed for the price to recover after a shock (section 10), but too many, or with too
long a memory, pin the price down. The number of value traders, the window and the size of the
shifts have to be set so that both hold, and real data should fix them.

## 12. Value trader sweep, and the switch to a true value

**Sweep with the first design.** 48 settings plus a control, run on the cluster
(`experiments/value_sweep.py`; commit 3f726d9): 2–20% value traders, windows of 100–3,000 steps, mean
shifts of 50–500 ticks. Shock test with 200 runs per size; runs without a shock of 10⁶ steps, 16 runs,
N_A = 500.

- Recovery needs small shifts and enough traders. With a mean shift of 50 ticks and 20% value traders
  the half-life after a 300-unit sell was about 100 steps; with 10%, 270–340 steps (windows of 1,000
  and 3,000). With shifts of 500 the price almost never recovered within 2,000 steps.
- Recovery also needs a long window. With 100 steps it never recovered: the reference average had
  caught up with the fallen price before the traders pushed it back.
- H at a lag of 10⁵ steps was 0.84–0.99 for almost every setting, even with 2% value traders, against
  0.41 for the control. That means the price kept moving one way for very long stretches.

**The cause: a drift.** Each trader's value was its shift above the price's own recent average, and
the shifts are drawn at random, so in any one run they do not balance. The price settles where
buyers and sellers balance, about the middle shift away from its own average. Since the average
follows the price, the price can only stay there by moving steadily. Checked directly (N_A = 250, 25
value traders, window 300, mean shift 150, 2×10⁵ steps, 8 runs): in every run the price drifted the
way of the middle shift, by 10–48 ticks per 1,000 steps. Balancing the shifts in mirrored pairs cut
it to 4–10.

**The fix: a true value (D30).** With the same seeds and settings, but with each trader's value set
from a true value that only moves with news (1 tick per step), the price stays a fixed distance from
the true value (about the middle shift) and moves with it. Over 2×10⁵ steps, the price and the true
value moved by the same amount to within 0.7 ticks per 1,000 steps.

**First check of the new design** (laptop, commit 3f726d9 plus the change):
- Shock test, 20% value traders (50 of 250), mean error 50 ticks, news 1 tick per step, 100 runs: the
  price recovers half of a 300-unit drop in 87 steps.
- Without a shock, 20% value traders, same settings, 2×10⁵ steps, 8 runs, N_A = 500: H(10) = 0.07,
  H(100) = 0.20, H(10³) = 0.45, H(10⁴) = 0.50, RMS change over 800 steps 30.2 ticks, kurtosis 3.05.
  These are nearly the same as without value traders (0.08, 0.19, 0.44, 0.48; 30.6 ticks; 2.92). So the
  side effects of the first design (section 11) are gone. Note that 1 tick of news per step was chosen
  to give about the same long-run wandering as the basic model, so the long-lag values are partly an
  input (D30).
