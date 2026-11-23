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
- **The E-mini:** to be measured (`python -m experiments.emini stats PATH`). **[Open]**
