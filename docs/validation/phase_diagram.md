# Checks: Phase diagram

Value against momentum traders for several system sizes (D36). D numbers refer to `../decisions.md` (D1-D37) and `../volatility_provider/decisions.md` (D38 on), P numbers to `../paper_model.md`. Section numbers run across all the files in this folder; `README.md` here lists which file holds each. Numbers quoted are from the runs named; see `results/` and the code version recorded inside each results file.

---

## 19. Phase diagram sweep (cluster)

All 176 combinations (D36; `experiments/phase_sweep.py`; results in `results/phase_sweep/`, table
`summary.csv`, heatmaps `phase_*.png`, autocorrelation functions `autocorrelations.pkl`). Order-1
momentum traders, window 50; value traders with mean error 50 ticks.

- **The Poisson order scaling works:** with orders of a quarter of one side, the impact is the same
  at every N_A (about −20 ticks at 20% value traders), 0–2% of orders empty a side, and 10–13% with
  orders of half of one side, as expected (D36). No normal-times run had a step with a side empty.
- **Order parameter** (correlation of consecutive 50-step price changes): about −0.37 with no
  momentum traders, rising steadily with the momentum share and changing sign along a line in the
  plane. With no value traders it crosses zero near 20% momentum; with 20% value traders near 30%;
  with 60% value traders near 45%. Value traders push the boundary to higher momentum shares.
- **It gets sharper with system size.** With no value traders, from 10% to 30% momentum the order
  parameter rises by 0.37 at N_A = 125 and by 0.66 at N_A = 1000, and the zero crossing moves to
  lower momentum shares as N_A grows. This is what a phase transition looks like in finite systems;
  whether the curves at different N_A collapse onto one (finite-size scaling) is the next analysis.
- **The time to recover does not blow up at that line.** With value traders present, the half-life
  rises smoothly with the momentum share and falls with the value share (20% value: about 60 steps
  with no momentum, about 310 with 80%, at every N_A). It hardly depends on N_A. Even deep on the
  trending side (20% value, 80% momentum, correlation +0.79) the price still recovers. So "trending"
  and "not recovering" are different: recovery only fails without value traders. The expected
  critical slowing down at the boundary is not seen in the half-life.
- **Artefact:** without value traders and with 60–80% momentum, the half-life comes out as about 25
  steps. There the price trends so strongly that the order's impact is small against the trend,
  whose direction is unrelated to the order, so the averaged curve returns to zero for that reason,
  not because the price recovers. The same applies to 5% value traders at N_A = 1000 with 50–80%
  momentum. Half-lives without value traders should not be read as recovery.
- Also to check: at N_A = 1000, no value traders, the order parameter is +0.92 at 60% momentum but
  +0.80 at 80%.
- No fat tails anywhere (kurtosis 1.0–3.3).
