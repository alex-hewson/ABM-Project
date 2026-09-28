# HFT/Order-Book ABM — Project Plan

What is done and what comes next. The reasoning and evidence behind each choice are in
`decisions.md` (cited below by number, e.g. D11).

Paper: Preis et al. (2006), EPL 75, 510 (`SimpleOrderBookModelPaper.pdf`, kept outside the
repository in OneDrive `Work/ABM/Papers/`).

## Where things stand

**Done:**
- Order book matching engine: price-time priority, limit and market orders, cancellation
- Liquidity providers and takers; simulation loop in the order implied by Eq. 1 (D3)
- Fast simulation method, about 3× faster, statistically equivalent to the per-agent loop (D8)
- Long runs save each finished run to disk and can be resumed; every results file records the
  code version (D9)
- Hurst exponent H(Δτ) (D12), return distributions (D15), depth profile with lognormal fit (D14)
- **Fig. 2 reproduced qualitatively at paper scale**: `results/fig2_final.pkl` / `.png`,
  10⁶ steps, 50 runs per N_A, commit 393cdee (D11, D13)
- Asymmetric order flow: shared, time-varying q_taker, bounded and mean-reverting walks (D16–D19)
- One experiment runner and one plotter for both figures (`experiments/run.py --flow ...`,
  `experiments/plot.py fig2|fig3`) (D20)
- **Fig. 3 reproduced qualitatively at paper scale**: `results/fig3_bounded.pkl`,
  `results/fig3_mean_reverting.pkl`, `results/fig3_final.png`, 10⁶ steps, 50 runs per N_A,
  commit a65a28c (`decisions.md`, section 4)
- Volatility-coupled entry depth (Eq. 4), runner option `--depth-coupling` and `plot.py fig4` (D21, D22)
- **Fig. 4 reproduced at paper scale**: `results/fig4.pkl` / `.png`, 10⁶ steps, 50 runs per N_A,
  commit acd8ebe; fat exponential tails whose widths match the paper's Fig. 4b (`decisions.md`,
  section 4)

Code layout and how to run things: see `README.md`.

**Git:** `main` holds Figs. 2 and 3; Fig. 4 is on branch `fig4-entry-depth`. The project folder is the repository root, so a clone gives the
project directly, with one README.

## Open questions
Each is described in `decisions.md`:
- Price definition: the median trade price is adopted for reported results; it is a calibration of a
  detail the paper does not specify, and must be reported as such (D11)
- Whether the paper's lognormal fit is per side or combined (D14)
- The q_provider variant of asymmetric flow, not implemented (D16)
- Mirrored vs blocked reflection in the bounded walk, untested (D18)

---

## Phase 1: Baseline model (reproduce Preis et al. 2006)

**Goal:** a working, validated reproduction of the base paper before touching HFT.
This is the methodological foundation — everything built later is compared against this baseline.

1. ~~**Liquidity provider / taker agents** and the per-step simulation loop~~ (done; D1–D8)
2. ~~**Reproduce Fig. 2**~~ (done at paper scale, `fig2_final`; symmetric, q=0.5; α=0.15, μ=0.025,
   δ=0.025, λ₀=100)
   - (a) Price path over 10⁶ MCS, N_A=250
   - (b) Depth profile ⟨N(p−p_m)⟩ over the last 10⁴ MCS, N_A=500, with lognormal fit (D14)
   - (c) H(Δτ) for N_A = 125, 250, 500: minimum ≈ 0.08 near Δτ ≈ 10, rising to ≈ 0.5 by
     Δτ ≈ 10⁴ (D11, D13)
   - (d) Return distributions for Δτ = 200, 400, 800, 1600, N_A=500: no fat tails (D15)
3. ~~**Add asymmetric order flow (Fig. 3)**~~ (done at paper scale, `fig3_final`; D16–D20)
   - 3a. Bounded random walk (Δs=0.001, S=0.05): H peaks at 0.80–0.87 near Δτ ≈ 10³; returns bimodal
   - 3c. Mean-reverting walk (Δs=0.001, S=½): H peaks at 0.56–0.63; returns close to Gaussian
4. ~~**Add volatility-coupled entry depth (Eq. 4, Fig. 4)**~~ (done at paper scale, `fig4`; D21, D22)
   - λ(t) = λ₀ · (1 + |q_taker(t)−½| / √⟨(q_taker−½)²⟩ · C_λ), λ₀=100, C_λ=10
   - ⟨(q−½)²⟩ is "determined separately before the main simulation"; the paper gives no
     procedure. The derived value √(Δs/4) = 0.0158 is used (D21); the Fig. 3 runs measured the same.
   - Result: H(Δτ) the same shape as Fig. 3c with a slightly higher peak (as in the paper), and fat
     exponential tails in P(Δp) (kurtosis 6.9–9.4, against 2.75–2.95 without Eq. 4)
5. **Checkpoint / write-up**
   - Document the reproduction as validation in the methodology chapter
   - Freeze and tag this version (git tag `baseline-v1`) as the control model for later comparison

---

## Phase 2: Large sell orders and flash crashes

Planned in `phase2_plan.md`: a large seller and intermediaries with inventory limits are added to the
Phase 1 model, based on Kirilenko et al. (2017). Four steps: large seller only; intermediaries with
limited capacity; fast and slow intermediaries; interventions such as a trading pause. The earlier
Phase 2–5 outline in this file is replaced by that plan.

---

## Immediate next steps

1. Commit the Fig. 4 results and the Phase 2 plan, merge `fig4-entry-depth` into `main`, and tag
   `baseline-v1`.
2. Discuss `phase2_plan.md` at the first supervisor meeting.
3. Phase 2, step 1: decide the crash definition, then add the large seller.
