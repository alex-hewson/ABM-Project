# HFT/Order-Book ABM — Project Plan

## Where things stand

**Done:**
- Reviewed Preis et al. (2006) as the base model to build from
- Designed overall architecture (order book core → baseline agents →
  feedback mechanisms → HFT extension → instability metrics)
- Implemented and tested the core `OrderBook` matching engine in Python
  (price-time priority, limit/market orders, cancellation, lazy-deletion
  heaps for best bid/ask)
- Verified performance is adequate for the order book alone (~18s estimated per
  10⁶-step run **before agent overhead** — see open issues below)
- Implemented `LiquidityProvider` / `LiquidityTaker` (`agents.py`)
- Implemented the simulation loop with cancellation sweep and the α(1−δ) > μ
  stability check (`simulation.py`)
- Implemented the Hurst estimator H(Δτ), validated on a synthetic random walk
  (`hurst.py`); multi-run averaging is now done by `experiments/fig2.py` itself
  (an earlier standalone `average_hurst.py` did this too, more simply, before
  the runner existed — removed once the runner fully superseded it)

Code layout (see `README.md`): `abm/` (orderbook, agents, simulation), `analysis/`
(hurst, prices, returns, depth_profile), `experiments/` (fig2, plot_fig2), `tests/`.
Run everything from the project root with `python -m ...`.

Paper: `Papers/SimpleOrderBookModelPaper.pdf` (Preis et al. 2006, EPL 75, 510).
Read directly; details below are checked against it.

### Open issues (found reviewing the code against the paper)

1. ~~Step order differs from Eq. 1.~~ **Fixed:** `simulation.py` now runs
   providers → cancellation → takers, matching Eq. 1. Check: at the Fig. 2
   parameters, mean book depth over the last 200 of 1,000 steps was ~1,236 vs
   Eq. 2's 1,212.5.
2. ~~**Speed.**~~ **Improved on branch `speedup-loop`.** Originally ~0.9 ms/step
   at N_A=250 (~15 min per 10⁶ steps), with heaps that grew without bound.
   Now `run_simulation(method="fast")` (the default) draws *how many* providers
   act / orders are cancelled / takers act from a Binomial and picks that many
   at random, which is statistically equivalent for IID agents; heaps no longer
   bloat; `total_orders()` is O(1). Measured single-process: N_A=250 ≈ 27 s per
   10⁵ steps, N_A=500 ≈ 66 s (about 3× faster than before). The literal
   per-agent loop is kept as `method="agents"` (the reference), and
   `tests/test_simulation.py` checks the two agree. The machine has 4 physical
   cores (8 threads, laptop chip), so parallel runs give only ~2.4× speedup.
   The 12-run trial (10⁵ steps) went 506 s → 177 s. Estimated paper scale
   (10⁶ steps, 50 runs × N_A = 125/250/500): ~15 h CPU ≈ 6 h wall. What's left
   is real per-order cost in the matching engine.
3. ~~**No tests** for agents, simulation or hurst.~~ **Done:** `test_agents.py`,
   `test_simulation.py`, `test_hurst.py` (run each with `python <file>`; ~4 s
   total). Includes an Eq. 2 equilibrium-depth check that fails if the step
   order is swapped (verified on a scratch copy).
4. **Git case mismatch:** git tracks `Agents.py`, file on disk is `agents.py`.
5. **Fig. 2c short-lag H does not match (UNRESOLVED).** The paper's curve has
   its lowest point ≈0.08 near Δτ≈10 (user's reading of the PDF; y-axis starts
   at 0.05). Ours (mid-price) bottoms out at 0.22–0.27 at Δτ≈10–20. The paper
   doesn't say mid-price vs trade price. One-run checks (seed 0, 10⁵ steps):
   mid-price H(10) = 0.27/0.24/0.21 and reaches 0.48 by Δτ≈300–800;
   last-trade-price H(10) = 0.06/0.05/0.03 (N_A = 125/250/500), H(100) ≈
   0.11–0.19, and reaches 0.48 only at Δτ≈2,500–3,400. The paper's 0.08 lies
   between/nearer the trade price. More readings from the paper: H(100) ≈
   0.22–0.25, curves reach 0.5 at Δτ≈10³–10⁴, N_A=500 lowest at the minimum
   → the trade price fits, the mid-price does not. **But which trade price:**
   H at short lags depends strongly on where in the step it is sampled
   (2 seeds, 10⁵ steps; min H for N_A=250/500): last trade in step
   0.03/0.02, random trade 0.05/0.04, median 0.08/0.07, first trade
   0.086/0.088, mean of the step's trades 0.13/0.12, mid-price 0.22/0.21.
   Median and first-trade match the paper's ≈0.08 and H(100)≈0.2 (median also
   gives the N_A ordering); last-trade is too low. None is obviously "the"
   definition — the paper doesn't say — so this is a convention we must
   choose, justify and document, not a finding. **Done:** the runner now
   stores RMS price change per lag (~80 lags, 1 to n_steps/10) and return
   histograms for five definitions (mid, last, first, median, mean), and
   `plot_fig2.py --price ...` plus a comparison figure lets the choice be made
   after the full run. Still to do: pick one (see `docs/decisions.md`, D11).
5b. ~~**Fig. 2c x-range**~~ **Fixed:** H is derived at plot time from stored
   RMS values with one-sided differences at the ends, so the curve now spans
   Δτ = 1 to n_steps/10 and shows the rise to the left of the minimum.
   (Results files from before this change (format 1) can't be plotted or
   extended and must be regenerated.)
6. **Run aborts on a one-sided book** (`analysis/prices.py:price_series` raises
   on a `None` mid-price). Deliberate, but a long run could hit it.
7. ~~**Nothing committed** since "Moved files."~~ Committed; ongoing since.

---

## Phase 1: Baseline model (reproduce Preis et al. 2006)

**Goal:** a working, validated reproduction of the base paper before touching HFT.
This is your methodological foundation — anything you build later gets compared
against this baseline.

1. **Liquidity provider / taker agents**
   - ~~Implement the two agent classes described in Section 3 of the design doc~~
   - ~~Providers: limit orders only, rate α, exponentially distributed entry depth (λ₀)~~
   - ~~Takers: market orders only, rate μ~~
   - ~~Wire up the per-step simulation loop~~ (done; see open issue 1 on step order)
2. **Reproduce Fig. 2** (symmetric, q=0.5; α=0.15, μ=0.025, δ=0.025, λ₀=100)
   - (a) Price path over 10⁶ MCS, N_A=250
   - (b) Equilibrium depth profile ⟨N(p−p_m)⟩ averaged over 10⁴ MCS, N_A=500,
     with lognormal fit *(done — mode ≈37 ticks, peak ≈9.4, vs data's ≈35/≈10;
     see `docs/decisions.md` D14 for the fitting method and its caveats)*
   - (c) H(Δτ) for N_A = 125, 250, 500 vs random walk: anti-persistent at short
     Δτ, reaching 0.5 and staying there. Paper averages 50 runs. *(done at
     10⁶ steps × 10 runs, commit f9bae8f: H = 0.23–0.28 at short lags, 0.48–0.50
     ± 0.01 at 10³–10⁴, consistent with 0.5 at long lags but noisy (±0.03).
     Extend to 50 runs with `--n-runs 50 --resume`.)*
   - (d) **Return distributions P(Δp)** for Δτ = 200, 400, 800, 1600, N_A=500
     *(done: no fat tails, kurtosis ≈ 2.7–2.9 (Gaussian = 3), rising with Δτ.
     Axis convention of the paper's panel unconfirmed — check against the PDF.)*
3. **Add asymmetric order flow** (needs shared, time-varying q_taker; currently
   a fixed per-agent parameter)
   - 3a. Bounded random walk: q_taker starts at ½, steps ±Δs each step,
     Δs=0.001, reflecting bounds ½±S with S=0.05. Expect H rising to ~0.9 at
     medium Δτ and *bimodal* returns (Fig. 3a/3b)
   - 3c. Mean-reverting walk: probability of stepping toward ½ is
     ½+|q−½|, Δs=0.001, S=½. Expect a more realistic H(Δτ) and ~Gaussian
     returns (Fig. 3c/3d)
   - Paper notes the same results if q_provider is perturbed instead
4. **Add volatility-coupled entry depth** (Eq. 4)
   - λ(t) = λ₀ · (1 + |q_taker(t)−½| / √⟨(q_taker−½)²⟩ · C_λ), λ₀=100, C_λ=10
   - The average ⟨(q−½)²⟩ is "determined separately before the main
     simulation" — paper gives no procedure, so a calibration pre-run must be
     designed and documented
   - Reproduce Fig. 4 — H(Δτ) qualitatively unchanged, but distinct fat tails
     (exponential tails on semi-log plot) in P(Δp). Confirms fat tails only
     appear with this feedback mechanism
5. **Checkpoint / write-up**
   - Document this reproduction as validation in your methodology chapter
   - Keep this version frozen/tagged (e.g. git tag `baseline-v1`) as your control
     model for later comparison

**Estimated effort:** this is the biggest chunk of remaining "safe" work — budget
real time here, since a shaky baseline undermines everything downstream.

---

## Phase 2: HFT extension

**Goal:** introduce agents and mechanisms that can plausibly generate the kind
of instability seen in real HFT-dominated markets (e.g. the May 2010 Flash Crash).

1. **Decide on your core instability mechanism first**, before writing agent code.
   Options discussed:
   - HF momentum/liquidity-taking agents reacting to short-term trend or order
     flow imbalance (event-driven, not clock-driven)
   - HF market makers with inventory limits who withdraw liquidity under stress
     (closer to the empirical Flash Crash narrative — liquidity vacuum, not just
     aggressive selling)
   - Some combination of both
   - **This choice determines your thesis's actual contribution** — worth treating
     as a discrete decision point rather than drifting into it. Suggest reading
     Jacob Leal et al. and Paddrik et al. side by side before committing.
2. **Implement the chosen HF agent type(s)**
   - Event-driven activation (reacts to price/order-flow changes, not fixed rate)
   - Fast cancellation behavior
3. **Integrate into the simulation loop**
   - Likely need to move from pure rate-based stepping to a hybrid: LF agents on
     the clock-based loop, HF agents event-driven within/between steps
4. **Sanity-check stability**
   - Re-verify the α* > μ condition (or its HFT-era equivalent) still holds
   - Confirm any observed "instability" isn't just a parameter/bug artifact —
     compare against Phase 1 baseline under matched non-HFT parameters

---

## Phase 3: Instability metrics & experiments

1. Implement metrics: realized volatility, book depth over time, extreme-event
   frequency (Paddrik et al.'s events/day metric), cancellation-to-execution ratio
2. Run controlled comparisons: baseline model vs. HFT-augmented model, same
   underlying LF order flow parameters
3. Identify and characterize the destabilizing mechanism concretely (what
   specifically triggers a flash-crash-like event in your model?)

---

## Phase 4: Policy experiments (if time allows)

Test regulatory levers against your model, following Jacob Leal & Napoletano:
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

## Immediate next step

1. Commit the work so far (open issues 4 and 7).
2. Decide how to handle speed before full-scale runs (open issue 2).
3. Fig. 2 reproduction (panels a–d) as the first concrete milestone.
