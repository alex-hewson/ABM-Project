# Decisions: liquidity providers

Decisions for the part of the project that works on the liquidity providers: where they place orders
and how they respond to the order flow (branch `order-splitting`). Earlier decisions are in
`docs/decisions.md` (D1–D37), `docs/volatility_provider/decisions.md` (D38–D40) and
`docs/takers/decisions.md` (D41–D44); numbers carry on from there, so every D number stays unique.

**[Assumed]** = own choice · **[Checked]** = verified against theory or tests · **[Open]** = not yet decided.

---

**D45. Where providers place limit orders. [Assumed]**
- **Why.** D44 found that the model's mid-price moves are almost all half-tick openings and closings
  of the spread (96–97% at λ₀ = 7), where the E-mini's are mostly whole-tick steps (84%) with the
  spread at one tick 99% of the time. In the model a gap left by an emptied queue often stays open,
  because providers place orders at an exponentially distributed distance from the mid-price (Preis
  et al. 2006; P5, P8), so few land where the gap is.
- **What the literature does.**
  - Preis et al. (2006): an exponential distance from the mid-price.
  - Smith, Farmer, Gillemot and Krishnamurthy (2003): uniform over all prices above the best bid
    (sells) or below the best ask (buys), so orders inside the spread are common.
  - Cont and de Larrard (2013), large-tick shares (spread at one tick about 99% of the time): limit
    orders only at the best bid and ask; when a queue empties the price moves exactly one tick, as
    the book has no gaps, and the spread stays at one tick. They report more than 0.7 of price moves
    reversed for Citigroup (the E-mini: 71% followed by a move the other way, D44).
  - Huang, Lehalle and Rosenbaum (2015), the queue-reactive model, for assets with an average spread
    under 2.5 ticks: orders at fixed levels (½, 1½, 2½ ticks) from a reference price, with rates that
    depend on the queue sizes. A version in which the price moves only through the book's own events
    is too calm and reverts too much (volatility 5 against 14 basis points; continuations 0.08
    against 0.39 on their measure); they add outside information, a chance that the reference price
    moves for reasons outside the book.
- **What real traders do** (order-level data; the E-mini file has only the best quotes, so it cannot
  measure this):
  - Bouchaud, Mézard and Potters (2002), three Paris shares, February 2001: the distance is measured
    from the best price on the order's own side (the bid for buys, the ask for sells). Orders one
    tick inside the spread, at the best price and one tick behind it are about equally common and
    together make up roughly half of all limit orders; beyond that P(Δ) ∝ Δ^−(1+μ) with μ ≈ 0.6, out
    to about 100 ticks.
  - Zovko and Farmer (2002), 50 London shares, 1998–2000: also from the same-side best price; the
    cumulative distribution falls as about δ^−1.5 from 10 to 2,000 ticks (orders inside the spread
    left out).
- **Decided: the distance of a new limit order is measured from the best price on its own side** (the
  best bid for a buy, the best ask for a sell), as both empirical papers measure it. Not chosen: the
  mid-price (Preis, the current model) and the opposite best price (Smith et al.).
- **The distribution of the distance in the literature** (all from the same-side best price):

  | paper | market | distribution | near the best price |
  |---|---|---|---|
  | Bouchaud, Mézard and Potters (2002) | 3 Paris shares, Feb 2001 (spread 1.4–2 ticks) | power law P(Δ) ∝ Δ₀^μ/(Δ₁ + Δ)^(1+μ), μ ≈ 0.6, from 1 to about 100 ticks, then a faster fall | one tick inside the spread, at the best and one tick behind about equally common, together about half of all orders |
  | Zovko and Farmer (2002) | 50 London shares, 1998–2000 | cumulative ∝ δ^−1.5 from 10 to 2,000 ticks | not given (inside the spread left out) |
  | Mike and Farmer (2008) | 25 London shares, 2000–2002 | Student t with α ≈ 1.3 degrees of freedom (1–1.65 across shares), in log price, scale about 0.0024, including orders inside the spread | peaked at the best price; fits well behind it, less well inside the spread |
  | Gu, Chen and Zhou (2008) | 23 Shenzhen shares, 2003 | power law, density ∝ x^−(1+α), α ≈ 1.15–1.8; independent of the spread and volatility | not given |

  The exponents disagree (Paris μ ≈ 0.6 against about 1.5–1.8 elsewhere). All four are small-tick
  shares; Mike and Farmer's simulation fails for large-tick shares (the book grows without limit),
  while large-tick models put orders at the best queues or a few fixed levels.
- **Decided: test both the Bouchaud, Mézard and Potters power law and the Mike and Farmer Student t.**
- **Orders on the aggressive side of the best price.** Both distributions put some orders between the
  best price and the opposite best price, or beyond it: Bouchaud et al. find one tick inside the
  spread as common as at the best, and count only orders short of the opposite best as limit orders;
  Mike and Farmer's Student t is centred on the best price, so about half of all orders are more
  aggressive than it, and those reaching the opposite best they treat as market orders (aggressive
  limit orders that trade at once). With a one-tick spread there is no price inside the spread, so in
  the model any such order crosses and trades at once (D6). Providers place about α·N_A = 75 orders
  per step against the takers' 12.5 market orders, so crossing orders could outnumber the takers' and
  splitters' orders and dilute the order flow agreed in D42.
- **Decided: trial both treatments.**
  1. Non-crossing only: an order is placed only if it stays short of the opposite best price; orders
     inside a wider spread are allowed and become the new best. Providers stay providers, as in
     Bouchaud et al.'s definition.
  2. Crossing allowed, as Mike and Farmer: an order that reaches the opposite best price trades at
     once, so providers also act as takers. Their trades count in the order flow and its statistics.
- **Decided: in treatment 1, a distance that would cross is drawn again** until it does not, which
  keeps the shape of the distribution for the orders that stay limit orders, as Bouchaud et al.
  define it. Not chosen: placing it at the best price, which would pile extra orders on the best
  queue and change the shape.
- **Decided: the Bouchaud, Mézard and Potters distribution,** in ticks from the same-side best price
  (Δ = 0 at the best, positive behind it, −1 one tick inside the spread):
  - P(Δ) ∝ 1/(Δ₁ + Δ)^(1+μ) for Δ ≥ 1, with μ = 0.6 (the same for all three of their shares) and
    Δ₁ = 1 (they fitted 1, 0.5 and 0).
  - Δ = −1 and Δ = 0 each as likely as Δ = 1, as they find. Up to 100 ticks this puts about 55–60%
    of orders at Δ = −1, 0 or 1, close to their "roughly half".
  - Beyond 100 ticks the chance tapers off exponentially, as their data fall faster there; any
    distance stays possible, without a hard limit, and the average distance stays finite (with
    μ < 1 it would otherwise be infinite).
  - **Decided: taper length 100 ticks:** beyond 100 ticks the chance is multiplied by
    e^(−(Δ − 100)/100), so 200 ticks is about a third as likely as the power law alone and 500 ticks
    about 2%.
- **Decided: the Mike and Farmer distribution,** a Student t centred on the same-side best price:
  - α = 1.3 degrees of freedom, their value for AstraZeneca (1 to 1.65 across their 25 shares).
  - Scale 5, 11 and 20 ticks, each tested. They measure distances in log price, log(limit price) −
    log(best price), which for small distances is the distance as a share of the price; their scale
    is 0.0024 (0.0020–0.0028 across shares), about 0.24% of the price. The model's price level is
    arbitrary (10⁶ ticks), so the scale is converted with the E-mini's price instead: about 1,150
    index points in May 2010, or 4,600 ticks of 0.25, of which 0.24% is about 11 ticks. 5 and 20
    ticks bracket it, since this conversion is the least certain step.
  - In treatment 1 the half more aggressive than the best is drawn again unless it lands inside a
    wider spread, so the orders placed are close to a half-Student-t behind the best price.
- **Decided: both kinds of takers:** the splitting setup that matched the E-mini's trade signs (D42:
  α = 1.6, N = 1, f = 0.85, q(t) off), and the paper's random takers (q(t) on, as in Fig. 3c/4) as a
  reference.
- **Decided: a control with the Preis providers** (an exponential distance from the mid-price) at
  λ₀ = 7 and 100, with the same takers, so the effect of placement alone is visible.
- **Everything else as before:** each provider acts with chance α = 0.15 per step, on a side chosen
  with equal chance, and every resting order is cancelled with chance δ = 0.025 per step; unit orders.
- **Implementation details (assumed):**
  - A drawn distance is rounded to the nearest tick, as in D5.
  - If the order's own side of the book is empty, its distance is measured from one tick inside the
    opposite best price (where a best price on its own side would be with a one-tick spread); if both
    sides are empty, from the start price (D5).
- **The trial:** 10 provider setups (Bouchaud et al. and Mike and Farmer at 3 scales, each with both
  crossing treatments; the Preis control at λ₀ = 7 and 100) × 2 kinds of takers = 20 jobs. N_A = 500,
  4 runs of 120,000 steps, the first 20,000 left out. Judged by the D38 tests on the mid-price (D43),
  and set beside the E-mini on the sign autocorrelation (D41), the response function and the
  mid-price moves (D44), the spread and its share at one tick, and the queue at the best price.
- **Implementation** (`abm/placement.py`; `run_simulation(placement=...)`; `experiments/placement_sweep.py`;
  `cluster/placement_sweep.slurm`, jobs 0–19):
  - The Bouchaud et al. distances are drawn from a table of Δ = −1 to 3,100 (the taper makes the
    rest negligible, e^−30); the Student t as a normal over the square root of a chi-squared divided
    by its degrees of freedom, times the scale, rounded to the nearest tick.
  - Checked in tests: Δ = −1, 0 and 1 equally likely, P(2)/P(1) = (2/3)^1.6, 55–60% within one tick,
    the taper; the Student t's median distance at 0.91 × scale; no provider order crosses when
    crossing orders are drawn again; without placement a run is exactly as before.
  - Each run records how many provider orders were placed, drawn again and crossed.
- **Preview before the trial** (splitting takers, one run of 15,000 steps, the first 3,000 left out):

  | providers | trades per step | crossed | spread | at one tick | queue | mid moves | ρ₁₀₀ |
  |---|---|---|---|---|---|---|---|
  | Bouchaud et al., drawn again | 12.5 | 0% | 1.01 | 99% | 70 | 0.17% | −0.07 |
  | Bouchaud et al., allowed | 22.9 | 14% | 1.97 | 20% | 26 | 11% | −0.36 |
  | Mike and Farmer 5, drawn again | 12.6 | 0% | 1.45 | 56% | 27 | 6.6% | −0.32 |
  | Mike and Farmer 5, allowed | 35.0 | 30% | 9.0 | 0% | 4 | 56% | −0.36 |
  | Mike and Farmer 11, drawn again | 12.5 | 0% | 2.79 | 13% | 9 | 19% | −0.30 |
  | Mike and Farmer 20, drawn again | 12.4 | 0% | 4.68 | 5% | 5 | 30% | −0.24 |
  | E-mini | | | 1.02 | 99% | 173 | 2.35% | −0.01 |

  Bouchaud et al. with crossing orders drawn again gives the E-mini's spread almost exactly, but the
  mid-price moves on only 0.17% of trades. Allowing crossing turns the providers into heavy takers
  (14–30% of their orders trade at once), and with Mike and Farmer the spread widens to 9–35 ticks.

