# Decisions: liquidity providers

Decisions for the part of the project that works on the liquidity providers: where they place orders
and how they respond to the order flow (branch `order-splitting`). Earlier decisions are in
`docs/decisions.md` (D1–D37), `docs/volatility_provider/decisions.md` (D38–D40) and
`docs/takers/decisions.md` (D41–D44); numbers carry on from there, so every D number stays unique.

**[Assumed]** = own choice · **[Checked]** = verified against theory or tests · **[Open]** = not yet decided.

---

**D45. Where providers place limit orders. [Assumed]** (being agreed point by point)
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
- **Still to agree:** the details of each (parameters, units in ticks, and how orders that land
  inside the spread or across it are treated). **[Open]**
