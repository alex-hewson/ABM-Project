# Checks: Value traders

Value traders in normal times, and the value trader sweeps, before and after the switch to a true value (D28, D30). D numbers refer to `../decisions.md` (D1-D37) and `../volatility_provider/decisions.md` (D38 on), P numbers to `../paper_model.md`. Section numbers run across all the files in this folder; `README.md` here lists which file holds each. Numbers quoted are from the runs named; see `results/` and the code version recorded inside each results file.

---

## 11. What value traders do to the price in normal times (first look)

*First design, with a moving average of the price as the reference. Replaced by the true value (D30);
see section 12.*

No shock. A share of the takers are value traders (D28, with the default window of 1,000 steps and
mean shift of 50 ticks). 10⁵ steps, 8 runs per N_A, values for N_A = 500 with the median trade price
(`results/value_traders/side_basic.png`, `side_fig4.png`, made with `plot.py compare`; commit 0282299 plus the
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

---

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

**Recovery measured relative to the true value (D25).** With news, the true value keeps moving after
the shock and adds noise to the plain price. Checked on 5% value traders (12 of 250), news 2 ticks per
step, mean error 50, 200 runs: on the plain price the half-lives were 199 steps (150-unit order) and
842 steps (300-unit order); relative to the true value they are 195 and 490. The plain-price numbers
are exactly those of the cluster run of the same setting, so the laptop and the cluster give the same
results.

---

## 14. Value trader sweep with the true value: final results

All 49 settings (true value design, D30), cluster, commit e274e66 for the shock tests (recovery
measured relative to the true value, D25) and c8d0943 for the runs without a shock. Table:
`results/value_sweep/summary.csv`; figures: `results/meeting/4_sweep_recovery_half_life.png`,
`5_news_sets_long_run.png`, `10_recovery_vs_density.png`.

- **Recovery speed is set mainly by the share of value traders divided by their mean error**, i.e. how
  many traders sit near the true value. Across all settings that recovered within 2,000 steps, the
  half-life goes as (share / error) to the power −0.85 (67 points, both shock sizes). With 20% value
  traders and a mean error of 50 ticks the half-life is about 90 steps for every amount of news; with
  10% and 50 ticks about 210. The scatter is larger for weak settings, and settings that never
  recovered are left out of the fit, so the exponent is only a rough figure.
- Measuring recovery relative to the true value made the half-lives nearly independent of the news
  for strong settings (e.g. 20% / 50 ticks: 89, 106, 92, 89 steps for news 0.25, 0.5, 1, 2; on the plain
  price the last was 122).
- **Short lags** (H(10), H(100), autocorrelations) match the control except for the strongest settings,
  where news reaches down to about the recovery time (about 100 steps).
- **Long lags** follow the news: H(10³–10⁴) below 0.5 for news 0.25–0.5, about the control's for news 1,
  above 0.5 for news 2.
- **No fat tails** anywhere: kurtosis 2.75–3.08.
- With news 1 and strong value traders (20%, 50 ticks) the price recovers half of a crash in about 90
  steps while its normal-times statistics are nearly those of the model without value traders. This
  depends on 1 tick of news per step matching the order book's own wandering (D30).
