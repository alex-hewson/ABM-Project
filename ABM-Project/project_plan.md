# HFT/Order-Book ABM — Project Plan

## Where things stand

**Done:**
- Reviewed Preis et al. (2006) as the base model to build from
- Designed overall architecture (order book core → baseline agents →
  feedback mechanisms → HFT extension → instability metrics)
- Implemented and tested the core `OrderBook` matching engine in Python
  (price-time priority, limit/market orders, cancellation, lazy-deletion
  heaps for best bid/ask)
- Verified performance is adequate for paper-scale simulations (~18s
  estimated per 10⁶-step run before agent overhead)

Files so far: `orderbook.py`, `test_orderbook.py`.

---

## Phase 1: Baseline model (reproduce Preis et al. 2006)

**Goal:** a working, validated reproduction of the base paper before touching HFT.
This is your methodological foundation — anything you build later gets compared
against this baseline.

1. **Liquidity provider / taker agents**
   - Implement the two agent classes described in Section 3 of the design doc
   - Providers: limit orders only, rate α, exponentially distributed entry depth (λ₀)
   - Takers: market orders only, rate μ
   - Wire up the per-step simulation loop (Poisson/rate-based, per paper)
2. **Reproduce Fig. 2** (symmetric, q=0.5 case)
   - Price path over 10⁶ MCS
   - Equilibrium depth profile (lognormal-ish)
   - Hurst exponent H(Δτ) converging to 0.5 at long timescales
3. **Add asymmetric order flow** (Section on perturbations)
   - Mean-reverting random walk for q_taker
   - Reproduce Fig. 3c (non-trivial Hurst exponent at medium timescales)
4. **Add volatility-coupled entry depth** (Eq. 4)
   - Reproduce Fig. 4 — confirm fat tails only appear with this feedback mechanism
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

Implement the Phase 1 liquidity provider / taker agents and the simulation loop,
targeting a Fig. 2 reproduction as the first concrete milestone.
