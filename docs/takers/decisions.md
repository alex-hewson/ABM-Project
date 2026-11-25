# Decisions: liquidity takers

Decisions for the part of the project that works on the liquidity takers' order flow (branch
`volatility-provider`). Earlier decisions are in `docs/decisions.md` (D1–D37) and
`docs/volatility_provider/decisions.md` (D38–D40); numbers carry on from there, so every D number
stays unique.

**[Assumed]** = own choice · **[Checked]** = verified against theory or tests · **[Open]** = not yet decided.

---

**D41. Measure the autocorrelation of trade signs, in the model and the E-mini. [Assumed, Checked]**
- **Why.** The two trials (D39, D40) show that the providers cannot fix tests (b) and (c): the
  mid-price reverts over 100–1,000 trades whatever the providers' depth. The literature puts the
  random walk of real prices down to a balance: limit orders make prices revert, and market orders
  whose signs persist make them trend (Bouchaud, Gefen, Potters and Wyart 2004). Real order signs
  have long memory: their autocorrelation decays as a power law, lag^(−γ), with γ about 0.6
  (0.36–0.77 across London Stock Exchange shares, always below 1; Lillo and Farmer 2004), explained
  by large orders split into many small ones (Lillo, Mike and Farmer 2005). Farmer, Patelli and
  Zovko (2005) and Smith et al. (2003) make the same point from the other side: an order book with
  random order flow makes prices anti-correlated, and real order flow is persistent enough to cancel
  this. In the model the takers' signs are set by q(t), the mean-reverting walk of Fig. 3c. Two
  orders are correlated by 4·Var(q) = step = 0.001, fading over about 1/(2·step) = 500 steps (about
  6,000 trades): almost no persistence at short lags. Before changing the takers, the target is
  measured.
- **Sign of a trade:** +1 if the trade price is above the mid-price in force just before the trade (a
  buy hitting the ask), −1 below it (a sell hitting the bid), 0 at the mid-price, where the side
  cannot be told. In the E-mini the mid-price is from the last quote before the trade (D37).
- **The model's mid-price just before each trade.** The model's per-trade mid-price of D37 is from the
  end of the step before the trade's step, up to one step (about 12.5 trades) old. Judged against it,
  the trades of one step look correlated: a first measurement gave +0.16 at lag 1, falling to about 0
  by lag 10, from that alone. The simulation now records the mid-price in the book at each trade
  (`trade_mids`; the book reports a trade before it removes the filled order, so the book is still as
  it was just before the trade), and the signs use it. The other per-trade statistics still use the
  end-of-step mid-price of D37.
- **Fills of one order.** Each E-mini row is one fill: a market order that takes out several resting
  orders appears as several rows with the same timestamp and side, which makes signs look persistent
  at short lags for a mechanical reason. The E-mini statistics are therefore given twice: per fill,
  and with each run of fills sharing a timestamp and a side counted once (with the number of fills
  per order). In the model every order is one unit, so one fill. Caveat: two separate orders on the
  same side with the same timestamp are also merged.
- **Statistic** (`analysis/stylised.py`, the same code for both, D37): the autocorrelation of the
  signs at 33 log-spaced lags from 1 to 10,000 trades, within each segment, pooled over segments;
  and γ, the slope of log autocorrelation against log lag over 10–1,000 trades (positive values only).
- **The current takers** (fixed depth, N_A = 500, one run of 50,000 steps, the first 5,000 left out,
  563,245 trades): +0.002 at lags 1 and 2, and within ±0.002 at every lag up to 10,000, the same at
  λ₀ = 100 and 7. That matches the expected 0.001 within the noise (about ±0.0013 for this many
  trades). No side was undecided (no trades at the mid-price).
- **The E-mini** (5 and 7 May 2010, regular hours, 1,592,939 fills; measured 23 November 2026):

  | lag | per fill | per order (fills merged) |
  |---|---|---|
  | 1 | +0.805 | +0.453 |
  | 2 | +0.732 | +0.334 |
  | 3 | +0.679 | +0.255 |
  | 10 | +0.468 | +0.080 |
  | 32 | +0.235 | +0.054 |
  | 100 | +0.092 | +0.032 |
  | 316 | +0.031 | +0.017 |
  | 1,000 | +0.017 | +0.002 |
  | 3,162 | +0.004 | +0.004 |
  | 10,000 | +0.006 | −0.000 |

  An order is 2.80 fills on average; 0.1% of fills are at the mid-price (side unknown). The noise
  level is about ±0.001 per fill and ±0.0013 per order (one over the square root of the number of
  signs). Per order, which is the like-for-like comparison with the model (one fill per order), the
  autocorrelation falls fast over the first 10 orders (0.45 to 0.08), then slowly from 10 to a few
  hundred orders (0.08 to 0.02), and is within the noise from about 1,000 orders. The fitted exponent
  depends on the range: γ = 0.36 over 10–100 orders, 0.65 over 10–1,000 and 1.13 over 100–1,000, so
  the slow part steepens towards a cutoff near 1,000 orders. Over 10–1,000 orders γ = 0.65 is inside
  Lillo and Farmer's 0.36–0.77. With two days of data the shape beyond a few hundred orders is not
  well determined.
- **Result.** The E-mini's order signs persist strongly at short lags and weakly out to a few
  hundred orders; the model's takers have no persistence at any lag (0.002 against 0.45 at lag 1,
  0.08 at lag 10 and 0.03 at lag 100). This is the missing half of the balance described above.

**D42. Order splitting: random takers and splitters together. [Assumed]**
- **Why.** D41 found that the E-mini's order signs persist (+0.45 at lag 1, a power law with γ about
  0.65 over 10–1,000 orders) and the model's takers' do not. Splitting large orders into many small
  ones is the explanation in the literature (Lillo, Mike and Farmer 2005), and it is a real feature of
  markets. Branch `order-splitting`.
- **The model it follows** (Lillo, Mike and Farmer 2005, Sections II–III): N hidden orders are active
  at all times. Each time a market order is placed, one of them is picked at random and one unit of it
  is placed; its side is the hidden order's side. A hidden order's size L (in units) is drawn from a
  power law, P(L) = α·L^−(α+1) with α > 1, and its side at random. A finished hidden order is replaced
  at once by a new one. The sign autocorrelation then decays as τ^−(α−1), so γ = α − 1, with a
  prefactor N^(α−2)/α, valid for lags much longer than N (their Eqs. 15, 17). On London Stock Exchange
  data they find γ about 0.57 against α about 1.6. Their model has no largest order size and no
  market orders outside hidden orders.
- **A test on real traders** (Sato and Kanazawa 2023, *Physical Review Letters*): nine years of Tokyo
  Stock Exchange orders with an ID for each account. About 25% of traders split their orders, and they
  place about 80% of the market orders; the rest trade at random. γ = α − 1 matches stock by stock,
  with α typically between 1 and 2 (e.g. 1.62 for Toyota in 2020). The size of the correlation
  depends on how many splitters are active and, strongly, on how unevenly they trade (their companion
  paper, 2024); γ does not.
- **Decided: a mix of random takers and splitters,** as on the Tokyo Stock Exchange. The random takers
  are the current takers: unit market orders with chance μ per step, on a side set by q(t).
- **Decided: q(t) both on and off for the random takers,** each tested. Off means each random order
  is a buy or a sell with equal chance.
- **Decided: pieces of one unit.** Lillo, Mike and Farmer derive γ = α − 1 for pieces of a fixed size.
  A splitter that has to go faster places several unit orders in the same step, which hits the book
  much like one larger order, since all takers act together at the end of a step. Every order stays
  one fill, as the per-order E-mini statistic of D41 assumes. The machinery for larger orders (D26)
  stays available. How many pieces per step: see the pace, below. **[Open]**
- **What the E-mini implies for the mix.** Two market orders in a row come from the same hidden order
  with chance about 1/N, and pieces of different hidden orders have unrelated sides. But a hidden
  order's last unit is followed by a new hidden order with a fresh side, and with α near 1.6 most
  hidden orders are only 1–2 units, so this happens often: only a share 1/α of units is followed by
  another unit of the same order (1 minus one over the average size, α/(α − 1)). The lag-1 sign
  correlation is therefore about 1/(α·N), and with a share f of market orders from splitters (the rest
  from random takers with unrelated sides) about f²/(α·N). Measured with the hidden orders alone
  (`abm/order_splitting.py`, 400,000 units each, f = 1):

  | | N = 1 | N = 2 | N = 5 |
  |---|---|---|---|
  | α = 1.4 | 0.68 | 0.33 | 0.13 |
  | α = 1.6 | 0.56 | 0.28 | 0.11 |
  | α = 1.8 | 0.47 | 0.24 | 0.10 |

  The E-mini's 0.45 therefore needs N = 1 with f about 0.8–0.9 (or α = 1.8 with f = 1); N = 2 reaches
  at most 0.33. At lags 10 and 100, α = 1.6 with N = 2 gives 0.12 and 0.03 (E-mini 0.08 and 0.03), and
  with N = 1 0.17 and 0.04. A first estimate of f²/N, without the 1/α, was too high by a factor of
  about α; it was corrected before the trial, and the ranges below still cover the E-mini.
- **Decided: the ranges.**
  - N, the number of hidden orders active at once: 1, 2, 3, 5 and 10.
  - f, the share of market orders from splitters: 0.5, 0.7, 0.85 and 1.0 (1.0 is the paper's model
    with no random takers; the Tokyo Stock Exchange is about 0.8).
  - q(t) for the random takers: on and off; with f = 1 there are no random takers, so once.
  - That is 5 × 3 × 2 + 5 = 35 combinations, before the size distribution and the rest.
- **Decided: α = 1.4, 1.6 and 1.8,** around the London and Tokyo values (about 1.6) and the E-mini's
  1.4–1.65 (from γ = α − 1 and γ of 0.36–0.65 depending on the fit range). Three values also show
  whether γ follows α − 1 in the model. With the ranges above that is 3 × 35 = 105 combinations.
- **Decided: the smallest hidden order is 1 unit,** as in the paper. With α = 1.6 about two-thirds of
  hidden orders are 1–2 units and the average is α/(α − 1) ≈ 2.7; the long correlations come from the
  rare large ones.
- **Decided: no hard cap on the size.** A real market has no fixed largest order, so a very large
  hidden order must stay possible, only very rare.
- **Decided: the pure power law, as in the paper, for now.** How rare large orders are under it, for
  f = 0.85 and 120,000 steps (about 1.3 million units from splitters, 360,000–570,000 hidden orders per
  run), from P(L ≥ x) = x^−α:

  | hidden orders per run at least | α = 1.4 | α = 1.6 | α = 1.8 |
  |---|---|---|---|
  | 1,000 units | 23 | 7.6 | 2.3 |
  | 10,000 units | 0.9 | 0.19 | 0.04 |
  | 100,000 units | 0.04 | 0.005 | under 0.001 |

  A 10,000-unit order, in about one run in one to five at α = 1.4–1.6, pushes one way for thousands
  of steps at small N. The power law also gives no fade near 1,000 orders like the E-mini's. Not
  chosen for now: a tempered tail, P(L) ∝ L^−(α+1)·e^(−L/L_c), which keeps γ = α − 1 below L_c, makes
  sizes beyond it exponentially rare without a fixed limit, and would give such a fade. It is the
  first thing to try if the pure power law gives runaway runs or no cutoff.
- **Decided: the pace, as in the paper, event by event.** A share f of the N_A takers are splitters, the
  rest random takers. Every taker still acts with chance μ per step, so the total stays about 12.5
  market orders per step (N_A = 500, μ = 0.025), and on average a share f of them comes from splitters.
  - A splitter that acts places one unit of one of the N hidden orders, picked at random with equal
    chance, on that order's side. When a hidden order's last unit is placed, it is replaced at once by
    a new one with a fresh size and side.
  - A random taker that acts places one unit, on a side from q(t) (q on) or with equal chance (q off).
  - Several units of one hidden order in one step happen by themselves, when several splitters act in
    that step and pick the same hidden order. No separate rule is needed.
  - Everyone who acts in a step places their orders in one random order, as value and momentum traders
    already do (`rng.shuffle` in the step), so the splitters' pieces are not placed in one block. A
    block would add sign correlation of its own.
  - Every hidden order is worked at the same pace on average, as in the paper. Sato and Kanazawa
    (2023) call this assumption unrealistic: real splitters trade at different rates. Their companion
    paper (2024) solves a version with uneven rates and finds that γ = α − 1 still holds, but the size
    of the correlation is very sensitive to how uneven the rates are. If the model's γ matches the
    E-mini but the size does not, uneven paces are the first thing to look at.
- **Decided: a new hidden order is a buy or a sell with equal chance,** independent of the price, q(t)
  and other hidden orders, as in the paper. The market stays balanced on average with no built-in
  trend. Not chosen: a side that follows q(t), the recent trend or a value; each would add a link to
  the market that the paper does not have (following the trend would make splitters partly momentum
  traders), so splitting would no longer be tested on its own.
- **Decided: fixed-depth providers at λ₀ = 100 and at λ₀ = 7,** each with every combination above.
  λ₀ = 100 is the paper's providers and the control of both earlier trials, so only the takers change
  and the results line up with D39 and D40. λ₀ = 7 is closer to the E-mini's regime (D40: spread about
  1.6 ticks, the mid-price moving on about 2.7% of trades, against 1.0 and 2.35%); how far a market
  order moves the price differs between the two, which may change what splitting does to H. Not
  chosen: setup 84, which behaved almost exactly like fixed depth at the same λ₀ (D40); and Eq. 4
  (Fig. 4), whose depth is driven by q(t) and has no meaning with q off.
- **The trial:** 2 values of λ₀ × 105 = 210 combinations. Each as in the earlier trials: N_A = 500,
  4 runs of 120,000 steps, the first 20,000 left out. Judged by the D38 tests on the mid-price, and by
  the sign autocorrelation against the E-mini's per-order values (D41: γ, and the values at lags 1,
  10, 100 and 1,000). Also recorded: the number and sizes of hidden orders, and the largest per run.
- **Implementation** (`abm/order_splitting.py`; `run_simulation(splitting=...)`; `experiments/splitting_sweep.py`;
  `cluster/splitting_sweep.slurm`, jobs 0–209):
  - Splitters take the place of the first round(f × N_A) takers. The takers that act in a step are
    drawn in a random order (`rng.sample`), so splitters' and random takers' orders are mixed.
  - A size is drawn as L = floor(U^(−1/α)) with U uniform on (0, 1], so P(L ≥ x) = x^−α for whole
    x ≥ 1; checked against x^−α at x = 2, 10 and 100 (tests).
  - The hidden orders draw from their own random numbers (`split-<seed>`); without splitting a run
    is exactly as before (tested).
  - With N = 1, f = 1 and α = 1.6 the lag-1 sign correlation in a full run is about 0.56, and with
    f = 0.5 about a quarter of that, as estimated above (tests).
- **Trial results (24 November 2026).** All 210 jobs finished (`results/splitting_sweep/summary.csv`,
  `signs.png`, `hurst.png`). All on the mid-price, in trade time; signs per order (D41).
  - **No combination passes all three D38 tests.** (a) passes in all 210, (b) in 72 and (c) in 6, but
    none passes both (b) and (c).
  - **Splitting is the first change that moves (b) and (c).** Without it (fixed depth, D40) H at
    1,000 trades is 0.37 and the autocorrelation of 100-trade changes −0.32. With it:

    | α | H at 1,000 trades | ρ₁₀₀ | passes (b) |
    |---|---|---|---|
    | 1.4 | 0.49–0.70 | −0.31 to −0.04 | 24 of 70 |
    | 1.6 | 0.40–0.56 | −0.32 to −0.16 | 48 of 70 |
    | 1.8 | 0.35–0.47 | −0.34 to −0.22 | 0 of 70 |
    | E-mini | 0.51 | −0.01 | |

  - **The sign autocorrelation matches the E-mini.** With α = 1.6, N = 1 and f = 0.85 the model follows
    the E-mini's per-order curve from lag 1 to 1,000:

    | lag | 1 | 10 | 100 | 1,000 | γ (10–1,000) |
    |---|---|---|---|---|---|
    | model | 0.41 | 0.14 | 0.037 | 0.010 | 0.58 |
    | E-mini | 0.45 | 0.08 | 0.032 | 0.002 | 0.65 |

    It runs a little high at lags 3–30 and has no cutoff near 1,000 orders (expected with the pure
    power law). With α = 1.4 the signs persist too long; with α = 1.8 they fade too fast. The values
    follow f²/(α·N) as estimated above. The signs are identical at λ₀ = 100 and 7, as they should be:
    the takers' sides do not depend on the book.
  - **The shape of H is wrong.** The E-mini's H dips to 0.38 at about 20 trades and is back at 0.5 and
    flat from about 100 trades. In the model the dip comes later and deeper (e.g. α = 1.6, N = 1,
    f = 0.85: 0.36 at about 125 trades at λ₀ = 100, 0.29 at about 160 at λ₀ = 7), and H then rises
    steeply and overshoots (0.63–0.64 at 10,000 trades; up to about 0.8 with α = 1.4). Most passes of
    (b) at α = 1.6 are H crossing 0.5 near 1,000 trades on its way up, since (b) only looks at that one
    lag. The only setups that pass (c) are α = 1.4 at λ₀ = 100 with N = 1–5 and f = 0.85–1 (ρ₁₀₀ −0.04
    to −0.10), and their H at 1,000 trades is 0.66–0.70, so they fail (b). No setting fixes both.
  - **Reading (not tested).** The book's reversion acts at about 100 trades and the splitters'
    persistence at longer lags, so in the model they do not cancel at the same lags; in the E-mini they
    do. Bouchaud, Gefen, Potters and Wyart (2004) describe a real market's price as a random walk
    because the reversion from limit orders keeps pace with persistent market orders. In the model the
    providers do not respond to the order flow at all.
  - **q(t) makes no difference once splitters are present:** between q on and off, H at 1,000 trades
    differs by at most 0.017, ρ₁₀₀ by 0.011 and the lag-1 sign correlation by 0.002.
  - **λ₀:** for the same setting, ρ₁₀₀ is less negative at λ₀ = 100 than at λ₀ = 7.
  - **Stability:** no market order hit an empty book and no step had a missing mid-price. The largest
    hidden order was 68,868 units. With N = 1 the kurtosis at 1,000 trades rises (up to 5.3 at α = 1.6,
    f = 1), since single very large hidden orders dominate the flow.
  - **A measurement artefact.** The model's H is exactly 0.5 below about 10 trades: the price
    statistics use the mid-price at the end of the step before each trade (D37), so the 12 or so
    trades of a step share one mid-price. The mid-price just before each trade is now recorded (D41);
    using it for all price statistics would make short lags comparable and could move the model's dip.
    Whether to change this: **[Open]**.
- **Open after the trial:** the measurement point above; whether to keep q(t) for the random takers,
  given it makes no difference; and what to try next, given that the reversion and the persistence do
  not line up. **[Open]**

**D43. The model's per-trade mid-price: the mid-price just before each trade. [Assumed, Checked]**
- **Why.** The price statistics compared with the E-mini (D37) took the model's per-trade mid-price
  from the end of the step before the trade's step. The 12 or so trades of a step therefore shared
  one mid-price, which made H exactly 0.5 below about 10 trades and hid how often the mid-price moves
  within a step (D42 trial results). The E-mini's per-trade mid-price is the last quote before each
  trade. Since D41 the model records the mid-price in the book just before each trade
  (`trade_mids`); **decided:** every price statistic now uses it (`experiments/common.py`,
  `trade_segment`), as the trade signs already did. A trade with one side of the book empty keeps the
  last mid-price before it. The spread and the units at the best prices still come from the end of the
  step before.
- **Needs new runs.** The result files hold only statistics, not the per-trade series, so the model's
  numbers in D37–D42 stay on the old basis; a trial gives numbers on the new basis only when rerun.
  The E-mini's numbers do not change.
- **What it changes** (one run of 50,000 steps each, the first 5,000 left out, both definitions from
  the same run, N_A = 500, λ₀ = 100):

  | | H(10) | lowest H, at | H(1,000) | ρ₁₀₀ | κ₁ / κ₁₀ / κ₁₀₀ / κ₁₀₀₀ | mid moves |
  |---|---|---|---|---|---|---|
  | fixed depth, end-of-step mid | 0.47 | 0.21 at 161 | 0.34 | −0.33 | 51 / 5.4 / 2.92 / 2.63 | 7.1% |
  | fixed depth, per-trade mid | 0.29 | 0.15 at 161 | 0.28 | −0.37 | 15 / 3.4 / 2.81 / 2.70 | 65% |
  | splitting (α 1.6, N 1, f 0.85), end-of-step | 0.50 | 0.37 at 161 | 0.52 | −0.15 | 53 / 5.6 / 2.94 / 4.52 | 7.1% |
  | splitting, per-trade mid | 0.37 | 0.30 at 45 | 0.50 | −0.22 | 18 / 3.9 / 2.82 / 4.35 | 55% |
  | E-mini | 0.41 | 0.38 at 21 | 0.51 | −0.01 | 61 / 8.6 / 3.50 / 2.90 | 2.35% |

  At λ₀ = 100 the queue at the best price is about 2 units, so most market orders empty it and move
  the mid-price: it moves on 55–65% of trades, not the 7% the end-of-step mid-price suggested (E-mini
  2.35%). With splitting the dip in H moves from about 160 trades to about 45, closer to the
  E-mini's 21, and ρ₁₀₀ becomes more negative. The kurtosis at 1–10 trades falls, since it mostly
  reflects how often the mid-price stays put (D38 (a)).
- **Reruns on the new basis (25 November 2026):** the mean entry depth trial (D40, 30 jobs) and the
  order splitting trial (D42, 210 jobs), with the same settings. The old results are kept in
  `results/lambda_sweep_end_of_step_mid/` and `results/splitting_sweep_end_of_step_mid/`. The first
  volatility provider trial (D39) was not rerun, so the λ₀ = 100 rows that `lambda_sweep collect`
  shows beside the new runs are still on the old basis. Figure: `results/lambda_sweep/mid_moves.png`.
  - **How often the mid-price moves** (fixed-depth control; setup 84 in brackets):

    | λ₀ | 30 | 10 | 8 | 7 | 6 | 5 |
    |---|---|---|---|---|---|---|
    | old basis | 5.8% | 3.6% | 3.1% | 2.7% | 2.0% | 0.5% |
    | new basis | 40% (42%) | 15% (17%) | 11% (13%) | 8.4% (10%) | 4.8% (6.3%) | 1.0% (4.2%) |

    The new values are 2–7 times the old, most at large λ₀; λ₀ = 100 is about 65% (one short run,
    above). The E-mini's 2.35% now lies between λ₀ = 5 and 6, not between 5 and 10. Below λ₀ = 6 the
    control falls steeply as the price starts to freeze; setup 84 holds up better at λ₀ = 5, partly
    because its mean depth is above λ₀.
  - **Mean entry depth trial, (b) and (c):** worse in narrow books on the new basis. For the control,
    H at 1,000 trades is 0.23–0.31 (0.27–0.37 before) and ρ₁₀₀ −0.38 to −0.40 (−0.32 to −0.36
    before) at λ₀ = 6–30; setup 84 is the same within 0.03. D40's conclusion stands, more strongly: a
    narrower book does not fix (b) or (c). The "both ways" setups still freeze below λ₀ = 10.
  - **Order splitting trial:** (a) still passes in all 210, (b) now in 114 (72 before), (c) in none
    (6 before); still none passes both. ρ₁₀₀ is 0.05–0.11 more negative everywhere (best −0.09, at
    α = 1.4 and λ₀ = 100; −0.22 to −0.38 at α = 1.6). H at 1,000 trades is 0.01–0.06 lower; the extra
    passes of (b) come from H at 10 trades falling from about 0.5 to about 0.3, which makes "H(1,000)
    above H(10)" easier to meet, not from a better H at 1,000 trades. The kurtosis at 1 trade falls
    from about 50 to 15–21 (E-mini 61). The mid-price moves on 6–8% of trades at λ₀ = 7 and on 47–64%
    at λ₀ = 100. The sign statistics are unchanged, as they already used this mid-price.
  - **The shape of H with splitting** (`results/splitting_sweep/hurst.png`): the artefact below 10
    trades is gone. The model's H starts near 0.5 and dips from about 5 trades, like the E-mini's,
    but deeper (0.20–0.36 against 0.38), with its lowest point later (30–100 trades against 21), and
    it is back at 0.5 only by about 1,000 trades against about 100, before overshooting as before.
    The E-mini's price reverts a little and briefly; the model's reverts a lot and for long, then
    trends.

**D44. The response function: impact builds up and levels off in the E-mini, not in the model. [Assumed, Checked]**
- **Why.** Order splitting gives the E-mini's sign persistence (D42), but the model's price still
  reverts too much at about 100 trades and trends at longer lags (D42, D43). Bouchaud, Gefen, Potters
  and Wyart (2004) write the price as the sum of the impacts of past trades, each fading with time as
  lag^(−β); with signs correlated as lag^(−γ), the price is a random walk only if β = (1 − γ)/2 (their
  Eq. 23). A faster fade gives H below 1/2 (reversion), a slower one H above 1/2 (trending). With
  γ ≈ 0.65 for the E-mini this needs β ≈ 0.17. Their measure of this balance is the response function.
- **Statistic** (`analysis/stylised.py`, `response_function`; the same code for both, D37):
  R(ℓ) = ⟨(m_(n+ℓ) − m_n)·s_n⟩, the average move of the mid-price ℓ trades after a trade, in that
  trade's direction, in ticks (their Eq. 3). m_n is the mid-price just before trade n (D43) and s_n
  its sign (D41). For the E-mini also per order, with the fills of one order counted once, as the
  paper groups simultaneous trades. In the paper's data (France Telecom) R roughly doubles from
  ℓ = 1 to a peak near 1,000 trades and then falls back a little. They note that with random order
  flow each trade's impact becomes permanent.
- **Measured** (model: two runs of 50,000 steps each, the first 5,000 left out, N_A = 500; E-mini per
  order; figure `results/response/response.png`, curves in `results/response/model_response.pkl`):

  | R(ℓ), ticks | ℓ = 1 | 10 | 100 | 1,000 | 10,000 |
  |---|---|---|---|---|---|
  | E-mini (per order) | 0.059 | 0.272 | 0.350 | 0.424 | 0.590 |
  | fixed depth, λ₀ = 100 | 0.701 | 0.418 | 0.199 | 0.256 | 0.872 |
  | fixed depth, λ₀ = 7 | 0.023 | 0.028 | 0.012 | 0.017 | 0.056 |
  | splitting (α 1.6, N 1, f 0.85), λ₀ = 100 | 0.532 | 0.797 | 0.403 | 1.071 | 1.759 |
  | splitting (α 1.6, N 1, f 0.85), λ₀ = 7 | 0.017 | 0.053 | 0.054 | 0.102 | 0.144 |

  The model's long lags rest on two short runs and are noisy.
- **The E-mini:** the impact builds up over the first 100 or so orders (0.06 to 0.35 ticks) and then
  stays almost level (0.42 at 1,000; about 0.6 at 10,000, noisy). The persistent orders keep pushing,
  the providers keep absorbing, and neither wins: the balance of Bouchaud et al.
- **The model:**
  - Fixed depth, without splitting: each trade's impact fades until about 100–300 trades (the
    book's reversion), then rises again at long lags.
  - Splitting at λ₀ = 7: up to about 200 trades the shape is almost the E-mini's (it builds up and
    levels off), but beyond that it keeps rising, to about 3 times its value at 100 by 10,000
    trades, against under 2 for the E-mini.
  - Splitting at λ₀ = 100: it rises to about 10 trades, falls back by 100 (the book's reversion),
    then rises about five-fold.
  - The size at λ₀ = 7 is about 0.05 ticks against the E-mini's 0.35, although the model's mid-price
    moves more often (6–8% of trades against 2.35%, D43).
- **Two separate problems:**
  1. **Long lags (beyond about 200 trades): the impact keeps growing.** Nothing in the model absorbs
     the splitters' persistence over the long run, so the price trends: the overshoot of H. **[Open]**
  2. **The dip in H at λ₀ = 7 is not the impact fading.** R is level from 20 to 200 trades while H
     dips to 0.2–0.36 there (D43), so the reversion must come from mid-price moves unrelated to the
     direction of trades. A likely source is flicker: the best level empties, the mid-price moves half
     a tick, and moves back when the level refills (the separate noise term in Bouchaud et al.'s
     Eq. 12). That would also explain a small R with frequent mid-price moves. At λ₀ = 100 the dip is
     the impact fading. Checked below; the reading needs restating.
- **Check: how the mid-price moves** (`mid_move_stats`, the same code for both; model one run of 50,000
  steps, the first 5,000 left out; 25 November 2026). Of the mid-price changes from one trade to the
  next:

  | | changes (share of trades) | half a tick | next change the other way | exactly undone by the next | trades between changes (median: all / undone) |
  |---|---|---|---|---|---|
  | E-mini | 2.35% | 16% | 71% | 58% | 23 / 14 |
  | splitting (α 1.6, N 1, f 0.85), λ₀ = 7 | 6.0% | 97% | 71% | 66% | 7 / 7 |
  | fixed depth, λ₀ = 7 | 8.5% | 96% | 74% | 67% | 7 / 7 |
  | splitting, λ₀ = 100 | 55% | 45% | 40% | 10% | 1 / 1 |
  | fixed depth, λ₀ = 100 | 65% | 40% | 50% | 11% | 1 / 1 |

  A random walk would have the next change the other way half the time.
  - **The E-mini reverses as often as the model at λ₀ = 7** (71% against 71–74%; exactly undone 58%
    against 66–67%), so "too much flicker", counted this way, is wrong.
  - **The kind of move differs.** 84% of the E-mini's changes are a whole tick: with the spread at one
    tick 99% of the time, the bid and the ask shift together and the price steps to a new level (and
    often back). 96–97% of the model's are half a tick: one side empties, the spread opens to two
    ticks and closes again (the spread is at one tick only 36–44% of the time at λ₀ = 7, D40).
  - **Restated reading (not tested):** the model has too little lasting impact for its back-and-forth.
    The E-mini's impact levels off at about 0.35 ticks per order; the model's at about 0.05 ticks,
    against frequent half-tick flicker, so the flicker dominates the variance until about 1,000
    trades, where the model's H returns to 0.5 (about 100 for the E-mini). This links problem 2 to
    how the model's spread opens and closes instead of the whole quote moving. **[Open]**
