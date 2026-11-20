# Changelog

What has been done, in the order it was done. What comes next is in `project_plan.md`. D numbers
refer to `decisions.md` (D1–D37) and `volatility_provider/decisions.md` (D38 on); the checks behind
each step are in `validation/` (see `validation/README.md` for which file holds each section).

---

## Phase 1: reproducing Preis et al. (2006)

Goal: a working, validated reproduction of the base paper, as the control model for everything
built later. Finished and tagged `baseline-v1` (D23).

- Order book matching engine: price-time priority, limit and market orders, cancellation
- Liquidity providers and takers; simulation loop in the order implied by Eq. 1 (D1–D8)
- Fast simulation method, about 3× faster, statistically equivalent to the per-agent loop (D8)
- Long runs save each finished run to disk and can be resumed; every results file records the
  code version (D9)
- Hurst exponent H(Δτ) (D12), return distributions (D15), depth profile with lognormal fit (D14)
- **Fig. 2 reproduced qualitatively at paper scale** (symmetric, q = 0.5; α = 0.15, μ = 0.025,
  δ = 0.025, λ₀ = 100): `results/phase1/fig2_final.pkl` / `.png`, 10⁶ steps, 50 runs per N_A,
  commit 393cdee (D11, D13)
  - (a) price path over 10⁶ MCS, N_A = 250
  - (b) depth profile ⟨N(p − p_m)⟩ over the last 10⁴ MCS, N_A = 500, with lognormal fit (D14)
  - (c) H(Δτ) for N_A = 125, 250, 500: minimum ≈ 0.08 near Δτ ≈ 10, rising to ≈ 0.5 by
    Δτ ≈ 10⁴ (D11, D13)
  - (d) return distributions for Δτ = 200, 400, 800, 1600, N_A = 500: no fat tails (D15)
- Asymmetric order flow: shared, time-varying q_taker, bounded and mean-reverting walks (D16–D19)
- One experiment runner and one plotter for all figures (`experiments/run.py --flow ...`,
  `experiments/plot.py fig2|fig3|fig4`) (D20)
- **Fig. 3 reproduced qualitatively at paper scale**: `results/phase1/fig3_bounded.pkl`,
  `results/phase1/fig3_mean_reverting.pkl`, `results/phase1/fig3_final.png`, 10⁶ steps, 50 runs per
  N_A, commit a65a28c (`validation/phase1_reproduction.md`, section 4)
  - 3a. bounded random walk (Δs = 0.001, S = 0.05): H peaks at 0.80–0.87 near Δτ ≈ 10³; returns bimodal
  - 3c. mean-reverting walk (Δs = 0.001, S = ½): H peaks at 0.56–0.63; returns close to Gaussian
- Volatility-coupled entry depth (Eq. 4), runner option `--depth-coupling` and `plot.py fig4` (D21, D22)
- **Fig. 4 reproduced at paper scale**: `results/phase1/fig4.pkl` / `.png`, 10⁶ steps, 50 runs per
  N_A, commit acd8ebe (`validation/phase1_reproduction.md`, section 5)
  - λ(t) = λ₀ · (1 + |q_taker(t) − ½| / √⟨(q_taker − ½)²⟩ · C_λ), λ₀ = 100, C_λ = 10
  - ⟨(q − ½)²⟩ is "determined separately before the main simulation"; the paper gives no
    procedure. The derived value √(Δs/4) = 0.0158 is used (D21); the Fig. 3 runs measured the same.
  - H(Δτ) the same shape as Fig. 3c with a slightly higher peak (as in the paper), and fat
    exponential tails in P(Δp) (kurtosis 6.9–9.4, against 2.75–2.95 without Eq. 4), whose widths
    match the paper's Fig. 4b
- Version frozen and tagged `baseline-v1` as the control model (D23)

---

## Phase 2

### Recovery after a large order (from 13 October 2026)

Direction set at the supervisor meeting on 13 October 2026: study how the market recovers after a
large order, not what causes the crash, and validate the model against a traditional market using
real order book data (E-mini futures data from Dr Karam). Crypto or prediction markets were an
optional extension if time allowed. Agents that ignore the market cannot make the price recover
(`validation/shock_tests.md`, sections 8 and 9), so agents that react to it were added, starting
with value traders.

The first task was agents with different speeds and order sizes: 1 unit with a chance to act every
step, 2 units every 2 steps, 4 units every 4 steps, each type trading the same volume on average.
Agreed then: both providers and takers can have these types, providers first; a slower agent still
acts with a probability when its turn comes, not at a fixed rate; each agent has its own starting
offset, so slow agents do not all act on the same steps; an order of size 4 is cancelled as a whole.
The plan for the rest of Phase 2 at that time is kept in `archive/phase2_plan.md`.

- Shock test on the basic model: one large market order, then price, spread and orders per side are
  recorded (D24, D25; `experiments/shock.py`). The book refills, the price does not come back
  (`validation/shock_tests.md`, section 8)
- Order sizes above one unit in the order book: partial fills, market orders that work through
  several price levels, cancellation of a whole order (D26)
- Agent types with different speeds and order sizes, for providers and takers, in any mix (D27).
  Each type trades the same volume, and the first type alone is exactly the baseline
  (`validation/phase1_reproduction.md`, section 1)
- Value traders, which buy below their own value and sell above it (D28). With them the price
  recovers after a shock; without them it never does (`validation/shock_tests.md`, section 10)
- Autocorrelation of price changes and of their size (volatility clustering) (D29), a runner option
  for value traders, and a plot that compares results files (`plot.py compare`)
- First look at what value traders do in normal times: at the default settings they hold the price
  too close to its average and remove the trend of Figs. 3–4 (`validation/value_traders.md`, section 11)
- Value traders estimate a true value that ignores the price, which removed a drift (D30); final
  value trader sweep: recovery speed depends on their share divided by their error
  (`validation/value_traders.md`, section 14)
- Momentum traders that follow the trend from 1–3 derivatives of recent prices (D31). They deepen a
  crash, then speed the rebound (`validation/momentum_traders.md`, section 15)
- News: jumps in the true value at random times (D32), and an event study that averages the price
  around every jump (D33). The price takes in all of the news; order-1 momentum traders speed this
  up and make it overshoot (`validation/news_and_poisson.md`, section 16). News jump-size test done
- The Poisson trader: large market orders at random times, sized by the wait since the last (D34),
  and its event study (D35). It reproduces the single shock tests from orders at random times, and
  gives impact against order size (`validation/news_and_poisson.md`, section 17)
- Momentum trader sweep on the cluster, collected (`validation/momentum_traders.md`, section 18)
- Phase diagram sweep, value against momentum traders for N_A = 125–1000 (D36;
  `validation/phase_diagram.md`, section 19). Its finite-size analysis is still to do
- Phase 2 branches merged into `main` (30 October 2026)
- E-mini data received (5–7 May 2010) and kept outside the repository; the same trade-time
  statistics computed for the data and the model (D37)

### Recovery as the research question (November 2026, before 17 November)

**What trader behaviours drive market recovery after a flash crash in a limit order book?**

Set out after a mind map of market features (supervisor meeting of 3 November 2026; plan sent to
the supervisors in mid-November). Liquidity and volatility are not set directly: they change only
through what the agents do. So trader behaviour was the main variable, through:
- **Cancellations.** They remove liquidity directly (e.g. an investor pulling all their orders in a
  stock to invest elsewhere), and many at about the same time can raise volatility.
- **Fundamentalists** (the value traders, D28), present in most crash recovery models.
- **Agents that respond to volatility.**
- **Heterogeneity:** randomness between agents following the same strategy, different response
  thresholds, and different speeds. Activity (trades per second) is linked to this.

**What recovery means.** Most papers use price recovery, e.g. Leal et al. (2016): a crash is a drop
of at least 5% that recovers within 30 minutes. Recovery of depth and of the spread was to be
measured as well.

**Method.** Add one feature at a time and check after each whether the model still matches the
E-mini data (D37). Calibrate on normal market data first, then try to recreate the crash.

### Flash crashes that emerge from the order book (from 17 November 2026)

The current aim; see `project_plan.md`.

- One agent at a time from the Fig. 4 setup, judged against the E-mini by shape (D38)
- The volatility provider: providers whose entry depth follows recent volatility instead of Eq. 4
  (D39). Trial of 216 setups on the cluster: none passes all three D38 tests; tests (b) and (c)
  are set by the parts the trial held fixed, not by the providers (19 November 2026)
- Model and E-mini compared on the mid-price, as D37 intended; the D38 tests and the trial results
  redone on the mid-price (20 November 2026)
- Mean entry depth trial: the four strongest volatility provider setups and a fixed-depth control at
  λ₀ = 30, 10, 8, 7, 6 and 5 (D40), submitted to the cluster (20 November 2026)
- Code tidy-up: meeting figure scripts tracked (`experiments/evidence/`), `requirements.txt`,
  results sorted into folders, the checks split by part (`validation/`), this changelog
