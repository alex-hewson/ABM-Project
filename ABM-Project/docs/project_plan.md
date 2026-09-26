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
- Asymmetric order flow, model side: shared, time-varying q_taker, bounded and mean-reverting
  walks (D16–D19), on branch `fig3-asymmetric-flow`

Code layout and how to run things: see `README.md`.

**Git:** `main` is still at the reorganisation commit. The finished Fig. 2 baseline exists only on
`speedup-loop` (393cdee), and the Fig. 3 model work on `fig3-asymmetric-flow`, which branches from it.

## Open questions
Each is described in `decisions.md`:
- Price definition: the median trade price is adopted for reported results; it is a calibration of a
  detail the paper does not specify, and must be reported as such (D11)
- Whether the paper's lognormal fit is per side or combined (D14)
- The q_provider variant of asymmetric flow, not implemented (D16)
- Mirrored vs blocked reflection in the bounded walk, untested (D18)
- The calibration procedure for Eq. 4 (below)

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
3. **Add asymmetric order flow (Fig. 3)** — model done (D16–D19); **still to do:** the experiment
   (many seeds; H(Δτ) for N_A = 125/250/500; return distributions for N_A=500) and its plots.
   First single-run looks are in `decisions.md`, section 4.
   - 3a. Bounded random walk (Δs=0.001, S=0.05): expect H up to ≈ 0.9 at medium Δτ and bimodal returns
   - 3c. Mean-reverting walk (Δs=0.001, S=½): expect H closer to real markets (≲ 0.6) and ≈ Gaussian
     returns
4. **Add volatility-coupled entry depth (Eq. 4, Fig. 4)**
   - λ(t) = λ₀ · (1 + |q_taker(t)−½| / √⟨(q_taker−½)²⟩ · C_λ), λ₀=100, C_λ=10
   - ⟨(q−½)²⟩ is "determined separately before the main simulation"; the paper gives no
     procedure, so a calibration pre-run must be designed and documented. The q values it needs
     are already recorded per step (D17).
   - Expected: H(Δτ) qualitatively unchanged, but distinct fat tails (exponential tails on a
     semi-log plot) in P(Δp), confirming fat tails only appear with this feedback mechanism
5. **Checkpoint / write-up**
   - Document the reproduction as validation in the methodology chapter
   - Freeze and tag this version (git tag `baseline-v1`) as the control model for later comparison

---

## Phase 2: HFT extension

**Goal:** introduce agents and mechanisms that can plausibly generate the kind
of instability seen in real HFT-dominated markets (e.g. the May 2010 Flash Crash).

1. **Decide on the core instability mechanism first**, before writing agent code.
   Options discussed:
   - HF momentum/liquidity-taking agents reacting to short-term trend or order
     flow imbalance (event-driven, not clock-driven)
   - HF market makers with inventory limits who withdraw liquidity under stress
     (closer to the empirical Flash Crash narrative — liquidity vacuum, not just
     aggressive selling)
   - Some combination of both
   - **This choice determines the thesis's actual contribution**, so it should be treated
     as a discrete decision point. Jacob Leal et al. and Paddrik et al. are to be read side by side
     before committing.
2. **Implement the chosen HF agent type(s)**
   - Event-driven activation (reacts to price/order-flow changes, not fixed rate)
   - Fast cancellation behavior
   - These agents cannot use the fast method's aggregation (D8), so they need a per-agent loop
3. **Integrate into the simulation loop**
   - Likely a hybrid: LF agents on the clock-based loop, HF agents event-driven within/between steps
4. **Sanity-check stability**
   - Re-verify the α* > μ condition (or its HFT-era equivalent) still holds
   - Confirm any observed "instability" isn't just a parameter/bug artifact —
     compare against the Phase 1 baseline under matched non-HFT parameters

---

## Phase 3: Instability metrics & experiments

1. Implement metrics: realized volatility, book depth over time, extreme-event
   frequency (Paddrik et al.'s events/day metric), cancellation-to-execution ratio
2. Run controlled comparisons: baseline model vs. HFT-augmented model, same
   underlying LF order flow parameters
3. Identify and characterize the destabilizing mechanism concretely (what
   specifically triggers a flash-crash-like event in the model?)

---

## Phase 4: Policy experiments (if time allows)

Test regulatory levers against the model, following Jacob Leal & Napoletano:
- Minimum resting time for limit orders
- Cancellation fees
- Circuit breakers
- Transaction taxes (Tobin-style)

---

## Phase 5: Calibration & write-up

- If real market data is available (e.g. LOBSTER), calibrate order flow rates
  and compare simulated stylized facts against real depth/volatility data
- Consolidate results, methodology, and validation (Phase 1 checkpoint) into
  thesis chapters

---

## Immediate next steps

1. Commit the Fig. 3 model work on `fig3-asymmetric-flow`.
2. Merge `speedup-loop` into `main`, so the finished Fig. 2 baseline is on the main branch.
3. Build the Fig. 3 experiment by generalising the Fig. 2 runner to accept an order-flow process,
   rather than copying it into a second runner.
4. Then Eq. 4 / Fig. 4, and tag `baseline-v1` once Figs. 2–4 are reproduced.
