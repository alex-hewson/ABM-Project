# HFT/Order-Book ABM — Project Plan

What is done and what comes next. The choices made are in `decisions.md` (cited below by number,
e.g. D11), the evidence for them in `validation.md`, and what the paper itself defines in
`paper_model.md`.

Paper: Preis, Golke, Paul & Schneider (2006), "Multi-agent-based Order Book Model of financial
markets", EPL 75, 510.

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
  commit a65a28c (`validation.md`, section 4)
- Volatility-coupled entry depth (Eq. 4), runner option `--depth-coupling` and `plot.py fig4` (D21, D22)
- **Fig. 4 reproduced at paper scale**: `results/fig4.pkl` / `.png`, 10⁶ steps, 50 runs per N_A,
  commit acd8ebe; fat exponential tails whose widths match the paper's Fig. 4b (`validation.md`,
  section 5)
- Shock test on the basic model: one large market order, then price, spread and orders per side are
  recorded (D24, D25; `experiments/shock.py`). The book refills, the price does not come back
  (`validation.md`, section 8)
- Order sizes above one unit in the order book: partial fills, market orders that work through
  several price levels, cancellation of a whole order (D26)
- Agent types with different speeds and order sizes, for providers and takers, in any mix (D27).
  Each type trades the same volume, and the first type alone is exactly the baseline
  (`validation.md`, section 1)
- Value traders, which buy below their own value and sell above it (D28). With them the price
  recovers after a shock; without them it never does (`validation.md`, section 10)
- Autocorrelation of price changes and of their size (volatility clustering) (D29), a runner option
  for value traders, and a plot that compares results files (`plot.py compare`)
- First look at what value traders do in normal times: at the default settings they hold the price
  too close to its average and remove the trend of Figs. 3–4 (`validation.md`, section 11)
- Value traders estimate a true value that ignores the price, which removed a drift (D30); final
  value trader sweep: recovery speed depends on their share divided by their error (`validation.md`,
  section 14)
- Momentum traders that follow the trend from 1–3 derivatives of recent prices (D31). They deepen a
  crash, then speed the rebound (`validation.md`, section 15). A sweep over their share, mix of
  orders and window is on the cluster
- News: jumps in the true value at random times (D32), and an event study that averages the price
  around every jump (D33). The price takes in all of the news; order-1 momentum traders speed this
  up and make it overshoot (`validation.md`, section 16)
- The Poisson trader: large market orders at random times, sized by the wait since the last (D34),
  and its event study (D35). It reproduces the single shock tests from orders at random times, and
  gives impact against order size (`validation.md`, section 17)

Code layout and how to run things: see `README.md`.

**Git:** `main` holds all of Phase 1. The finished baseline is tagged `baseline-v1` (D23). Phase 2 is
on a chain of branches (shock-test → … → poisson-trader), not yet merged into `main`.

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
   - ~~Freeze and tag this version (git tag `baseline-v1`) as the control model for later comparison~~
     (done; D23)
   - Still to do: document the reproduction as validation in the methodology chapter

---

## Phase 2: Recovery after a flash crash or flash rally

Aim, as set by the supervisors: study how the market recovers after a large order, and validate the
model against a traditional market using real order book data (E-mini futures data from Dr Karam,
expected mid-October 2026). Crypto or prediction markets are an optional extension if time allows.

Agents that ignore the market cannot make the price recover (`validation.md`, sections 8 and 9), so
agents that react to it are being added, starting with value traders (D28).

Direction set at the supervisor meeting on 13 October 2026: study how the market recovers after a
large order, not what causes the crash. The first task is agents with different speeds and order
sizes: 1 unit with a chance to act every step, 2 units every 2 steps, 4 units every 4 steps. Each
type trades the same volume on average.

Agreed so far:
- Both providers and takers can have these types; providers first.
- A slower agent still acts with a probability when its turn comes, not at a fixed rate.
- Each agent has its own starting offset, so slow agents do not all act on the same steps.
- An order of size 4 is cancelled as a whole.

The plan for the rest of Phase 2 is in `phase2_plan.md`.

---

## Immediate next steps

1. Collect and read the momentum trader sweep when the cluster jobs finish
   (`python -m experiments.momentum_sweep collect`).
2. Check whether the response to news is proportional to the jump: jumps of 10, 30 and 100 ticks,
   inside and beyond the value traders' spread (D32, D33).
3. The scaling of correlation functions and phase changes (the physics supervisor's request, 20
   October 2026): a phase diagram over the shares of value and momentum traders. Value traders pull
   the price back, momentum traders push it on, so the market should change from recovering to
   running away. The recovery time after a shock is a relaxation time, which may grow near the
   boundary. To be designed before building; the momentum sweep should set its ranges.
4. Merge the Phase 2 branches into `main`.
5. Fat tails: providers that place their orders further from the midpoint when recent volatility is
   high. This keeps the idea of Eq. 4 (entry depth widens in turbulent times), but providers react
   to something they can see, the recent price changes, instead of the takers' hidden buy
   probability. The basic model has no fat tails without it (`decisions.md`, section 5).
6. When the E-mini data arrives: find out its form and the rules for using it, keep it out of the
   repository, then measure order rates and the response to large orders in it.
