# The model as defined in the paper

What Preis, Golke, Paul & Schneider (2006), EPL 75, 510 define: the model, its parameters, how
results are measured, and what the paper reports. Nothing in sections 1–7 was decided in this
project. Section 8 lists what the paper leaves out; each gap was filled by a decision recorded in
`decisions.md` (D numbers).

The numbers P1, P2, ... are fixed IDs, like the D numbers in `decisions.md`.

---

## 1. Order book and orders

**P1. One asset, one order book.** Trading is continuous (a continuous double auction). Prices are
multiples of a tick. Best bid p_b, best ask p_a, midpoint p_m = (p_a + p_b)/2.

**P2. Two order types.** A limit order is executed at its limit price or a better one. A market
order has no limit price and is matched at once at the best ask (buy) or best bid (sell).

**P3. Price-time priority.** Better prices are matched first. At one price, orders are matched in
the order they arrived (Fig. 1).

**P4. Unit orders.** Every order is for one unit of the asset.

## 2. Agents

**P5. N_A liquidity providers.** They only place limit orders, around the midpoint, at rate α. An
order goes on the bid side with probability q_provider, otherwise on the ask side.

**P6. N_A liquidity takers.** They only place market orders, at rate μ. An order is a buy with
probability q_taker, otherwise a sell.

**P7. Cancellation.** Limit orders are removed with probability δ per time unit.

**P8. Entry depth.** The distance of a limit order from the midpoint is exponentially distributed
with parameter λ₀. (The paper first mentions a version with uniform depth over a fixed interval.
It is not used for the figures and is not implemented here.)

## 3. Time, stability and start-up

**P9. Time.** Measured in Monte Carlo steps (MCS). The paper does not define the term further.

**P10. Number of orders in the book (Eq. 1–3).**
- Eq. 1: N(t+1) = (N(t) + αN_A)(1 − δ) − μN_A
- Eq. 2, in equilibrium: N_eq / N_A = α(1/δ − 1) − μ/δ
- Eq. 3, with α* = α(1 − δ): N_eq δ / N_A = α* − μ
- A stable book needs α* > μ and δ > 0. Equilibrium is reached after some thousand MCS.

**P11. Pre-opening and price range.** Before the simulation starts there are 10 MCS in which only
limit orders are placed, around the start price p(t₀). The book has 2×10⁶ price ticks and
p(t₀) = 10⁶.

**P12. Parameters for Fig. 2.** α = 0.15, μ = 0.025, δ = 0.025, λ₀ = 100, q_provider = q_taker = 1/2,
N_A = 125, 250 and 500.

**P13. Scale.** Each run is 10⁶ MCS. Each simulation is averaged over 50 runs.

## 4. Measurements

**P14. Hurst exponent.** Defined by ⟨(Δp)²⟩^½(Δτ) ∝ Δτ^H, and shown as H(Δτ) for each N_A.

**P15. Return distributions.** Price increments p(t+Δτ) − p(t) are used, not log returns. Shown for
Δτ = 200, 400, 800 and 1600 at N_A = 500.

**P16. Depth profile.** ⟨N(p − p_m)⟩, the average number of orders at each distance from the
midpoint, averaged over 10⁴ MCS at N_A = 500. The paper says it can be described by a lognormal
distribution and calls this description phenomenological.

**P17. Price path.** Fig. 2a shows p(t) − p(t₀) for one run of 10⁶ MCS at N_A = 250.

## 5. Asymmetric order flow (Fig. 3)

**P18. Bounded random walk of q_taker (Fig. 3a, 3b).** q_taker starts at 1/2 and changes by ±Δs in
each time step. Reflecting boundaries keep it in [1/2 − S, 1/2 + S]. Δs = 0.001, S = 0.05.

**P19. Mean-reverting random walk of q_taker (Fig. 3c, 3d).** The probability of moving closer to
1/2 is 1/2 + |q_taker(t) − 1/2|. Δs = 0.001, S = 1/2. The paper also calls this the feedback random
walk.

**P20. q_provider variant.** The paper says the findings do not change if q_taker is kept at 1/2
and q_provider is changed in the same way instead. Not implemented here (D16).

## 6. Entry depth linked to the trend (Fig. 4)

**P21. Eq. 4.** λ(t) = λ₀ (1 + |q_taker(t) − 1/2| / √⟨(q_taker(t) − 1/2)²⟩ · C_λ), used together with
the mean-reverting walk (P19). λ₀ = 100, C_λ = 10. The average ⟨...⟩ is found separately before the
main simulation. C_λ = 0 gives the fixed depth again.

## 7. What the paper reports

The comparison with the results here is in `validation.md`.

- **Fig. 2 (basic model).** H is below 1/2 at short time scales (anti-persistent). It rises to 1/2
  and stays there for medium and long time scales. The depth profile is roughly lognormal.
- **Fig. 3a, 3b (bounded walk).** H rises up to 0.9 at medium time scales and returns to 1/2 at
  long ones. The return distributions are bimodal. The paper judges this unrealistic.
- **Fig. 3c, 3d (mean-reverting walk).** H is above 1/2 at medium time scales and closer to real
  markets, where a maximum of about 0.6 is expected. The return distributions are approximately
  Gaussian, with no fat tails.
- **Fig. 4 (Eq. 4).** H(Δτ) is qualitatively the same as in Fig. 3c. The return distributions have
  fat tails, which are straight lines on a semi-log plot (exponential). Fig. 4b plots Δp in
  ticks/10³, from −4 to 4.

## 8. What the paper does not say

Each gap was filled by a decision in `decisions.md`.

| Not stated in the paper | Decision |
|---|---|
| What one MCS is, and whether agents act independently in it | D2 |
| Order of events within a step | D3 |
| Whether an order can be cancelled in the step it was placed | D4 |
| Whether λ₀ is the mean depth; how depths are rounded to ticks; what happens with no midpoint | D5 |
| What happens to a limit order that crosses the spread | D6 |
| What happens at the edges of the 2×10⁶-tick book | D7 |
| Which price is used (mid-price or a trade price) | D11 |
| How H(Δτ) is estimated from the data | D12 |
| Which 10⁴ MCS the depth is averaged over; how the lognormal fit is made | D14 |
| Binning and axes of the return distributions | D15 |
| Whether q_taker is one value for the whole market or one per taker | D16 |
| When q_taker changes relative to the takers acting | D17 |
| Whether +Δs and −Δs are equally likely; how the reflecting boundary works | D18 |
| What the mean-reverting walk does at exactly q = 1/2 | D19 |
| How the average in Eq. 4 is found | D21 |
