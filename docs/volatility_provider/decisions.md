# Decisions: volatility provider

Decisions for the part of the project that trials agents one at a time, starting with providers that
react to recent volatility (branch `volatility-provider`). Earlier decisions (D1–D37) are in
`docs/decisions.md`; numbers carry on from there, so every D number stays unique.

**[Assumed]** = own choice · **[Checked]** = verified against theory or tests · **[Open]** = not yet decided.

---

**D38. Trial agents one at a time, starting from the Fig. 4 setup. [Assumed]**
Follows the project aim of 17 November 2026 (`project_plan.md`, Phase 2): a model that is normal
almost all the time but very rarely produces a flash crash from within. The first step is a stable
model that matches the stylised facts, with no crash needed.
- **Starting point:** the Preis Fig. 4 model (mean-reverting order flow with volatility-coupled entry
  depth, Eq. 4, D21). It is the only version so far with fat tails and volatility clustering: in trade
  time, on the mid-price (D37), the kurtosis of 100-trade changes is 8.9 (2.9 for the paper's Fig. 2
  agents) and the autocorrelation of the size of 100-trade changes is +0.42 at lag 1 and +0.28 at
  lag 10 (+0.05 and 0.00 for Fig. 2). Its weak points: the spread is about 200 ticks (E-mini: 1), and its stylised
  facts come from a hidden quantity, the takers' buy probability q(t), which no trader can see.
- **One agent at a time.** Each new kind of agent is added to the starting point on its own and kept
  only if the model keeps or gains stylised facts when checked against the E-mini data (D37);
  otherwise it is thrown out. The next agent is not started until this is settled.
- **Theory first.** The reasoning behind each agent and the meaning of each of its parameters are
  checked and agreed before the agent is implemented.
- **Decided: pass/fail by shape, as a crude first cut of very bad setups.** A setup passes if, in trade
  time and on the mid-price (D37), it shows all three of:
  - **(a) fat tails that fade with lag:** kurtosis of the price changes above 3 at short lags (1–10
    trades), falling as the lag grows, and close to 3 by 100–1,000 trades. E-mini: 60.9, 8.6, 3.5 and
    2.9 at 1, 10, 100 and 1,000 trades (aggregational Gaussianity). At 1–10 trades most of this comes
    from how rarely the mid-price moves, not from large moves: the E-mini's mid-price is unchanged
    over 98% of trades, and a change that is zero most of the time and ±1 tick with chance p has
    kurtosis 1/p (here about 42) with no large moves at all.
  - **(b) a random walk at long lags:** H rising towards 0.5 and close to it beyond a few hundred
    trades. E-mini: 0.41 at 10 trades, 0.51 at 1,000.
  - **(c) a bounce and nothing else:** negative autocorrelation of trade-to-trade changes at lag 1
    (E-mini −0.06; the trade price's bid-ask bounce, −0.32, is not part of the test), and the
    autocorrelation of 100-trade changes close to zero (E-mini −0.01 to +0.01 at lags 1–5).

  The first version of these tests, and of the trial results (D39), used the trade price by mistake;
  both were redone on the mid-price on 20 November 2026 (D37).

  Judged by shape, not by distance from the E-mini numbers: the E-mini statistics come from two days
  in a stressed week next to the flash crash (5 and 7 May 2010), so they are rough targets. Closer
  matching comes later.

  Left out for now:
  - **volatility clustering:** in trade time it is almost absent in the E-mini (−0.02 at lag 1, +0.04
    at lag 10 for the size of 100-trade changes), because counting time in trades removes most of it;
    it needs a clock-time comparison to be judged fairly.
  - **spread and depth:** far from the E-mini in every version of the model (Fig. 4: spread 207 ticks
    against 1; median trade ÷ size at the best price 1.0 against 0.012), but set mainly by λ₀, which
    the volatility provider does not change (D39).

  The starting point itself fails all three: Fig. 4's kurtosis does not come down to 3 (150, 16, 8.9
  and 8.0 at 1, 10, 100 and 1,000 trades), its H is 0.47 at both 10 and 1,000 trades, and its
  100-trade changes have an autocorrelation of −0.31 at lag 1.
- **How "by shape" is tested** (`experiments/volatility_sweep.py`), so that every combination is judged
  the same way. These numbers are rough on purpose:
  - (a) kurtosis at 1 or 10 trades above 3.5; kurtosis at 100 and at 1,000 trades below that; and
    kurtosis at 100 or 1,000 trades between 2.5 and 4.
  - (b) H at about 1,000 trades between 0.4 and 0.6, and higher than H at 10 trades. To be revisited
    once the trial results are in: the providers' memory W is 50–200 steps, roughly 600–2,500 trades
    at N_A = 500, so their effect on H may only show at lags longer than 1,000 trades (e.g. a test over
    1,000–10,000 trades). The check is redone from the saved statistics, so this needs no new runs.
    **Revisited after the trial (D39, trial results):** on the mid-price, H at 1,000 trades is
    0.27–0.55 (median 0.37; 0.37 for the fixed-depth control, 0.47 for Fig. 4), and all but one
    combination reach 0.5 somewhere between about 950 and 3,400 trades. A test over 1,000–10,000
    trades would therefore let nearly everything pass, controls included, and would not separate one
    setup from another. Whether to change (b): **[Open]**.
  - (c) the lag-1 autocorrelation of trade-to-trade changes below 0, and the autocorrelation of
    100-trade changes within ±0.1 at lags 1–5.

**D39. The volatility provider: the first agent to trial. [Assumed]**
- **Idea:** a provider that places its limit orders further from the best price when recent price
  moves have been large. It keeps the idea of Eq. 4 (entry depth widens in turbulent times), but
  reacts to something it can see, the recent volatility, instead of the hidden q(t). Volatility then
  feeds back on itself: providers back away, the book thins near the mid-price, orders move the price
  more, and volatility rises further. Whether this gives bursts or runs away is the first thing to test.
- **Support in the literature** (to be read and checked): optimal market making, where the best spread
  grows with volatility (Avellaneda & Stoikov 2008); the observed link between spread and volatility in
  order-driven markets (Wyart, Bouchaud, Kockelkoren, Potters & Vettorazzo 2008); liquidity providers
  withdrawing from the E-mini as volatility rose during the flash crash (Kirilenko, Kyle, Samadi &
  Tuzun 2017).
- **Decided:** a separate class, `VolatilityProvider`, next to the existing `LiquidityProvider`, which
  stays unchanged so that every earlier experiment still runs exactly as before.
- **Decided: the takers keep the mean-reverting walk of Fig. 4** (their buy probability q(t), D19).
  Only what the providers' entry depth reacts to changes: recent volatility instead of q(t) (Eq. 4).
  Without the walk the takers' chance of buying would stay fixed at 1/2, with no stretches of mostly
  buying or mostly selling. The walk stands in for the persistent order flow of real markets (large
  orders split into many small ones over hours; Lillo & Farmer 2004), and keeping it means the trial
  changes one thing only.
- **Decided: two ways of measuring recent volatility, both available as a setting,** to be compared in
  small runs before one is chosen. Both use changes of the mid-price:
  - **standard deviation of the changes** (as Leal et al. 2016): subtract the average change over the
    window, square, average, take the square root. A large move counts heavily. A steady one-way move
    counts as zero, since every change is the same and none differs from the average.
  - **mean absolute change** (as Kärvik et al. 2018): drop the sign of each change and average the
    sizes. Nothing is subtracted, so a steady one-way move does count, and one large move counts less
    than with squaring.

  Log returns (Veryzhenko & Oriol 2016) are not used separately: price moves are tens of ticks on a
  price of about 10^6 ticks, so a log return is the price change divided by an almost constant number,
  which cancels once recent volatility is compared with typical volatility.
- **Decided: the time horizon is two settings, tried over a small grid.**
  - **k, the length of one change:** the mid-price now minus the mid-price k steps ago. Changes over
    1 step are mostly the price bouncing between bid and ask (in trade time, consecutive trade-to-trade
    changes are correlated at −0.49), and a 10-step window was mostly noise for the momentum traders
    (`../validation/momentum_traders.md`, section 15).
  - **W, the providers' memory:** at each step the volatility is worked out from all the k-step changes
    in the last W steps (overlapping, so about W − k of them). A short memory reacts fast but is noisy:
    the relative error of a standard deviation from n independent changes is about 1/√(2n). A long
    memory smooths over the swings to be followed: the takers' buy probability q(t) changes by its
    typical amount over roughly 250 steps, and Fig. 4's volatility clustering lasts of order 100 steps.
  - **Grid:** k = 5, 10, 20 steps and W = 50, 100, 200 steps, for both measures, in small runs.
- **Decided: two shapes of memory, both tried; the fading one preferred.**
  - **Fixed window:** each change counts equally until it is W steps old, then drops out at once.
  - **Fading:** every past change counts, with a weight that falls by the same factor each step
    (an exponentially weighted average). So that the two shapes compare like for like, the fading
    memory is set to give its changes the same average age as the fixed window (W/2 steps), i.e. a
    weight falling by a factor e every W/2 steps. No sudden drop when a large change leaves the
    window. The momentum traders already use this kind of average for their typical signal size (D31).
- **Decided: recent volatility is compared with a long-run average of itself.** Each provider reacts
  to how unusual the recent volatility is (recent ÷ long-run), not to its raw size in ticks, as Eq. 4
  reacts to |q − 1/2| ÷ √⟨(q − 1/2)²⟩. The long-run average uses a much slower memory than W. Unlike a
  fixed reference measured before the run (as in Eq. 4), it adapts: in a lasting turbulent spell it
  catches up, the ratio drifts back to 1 and the providers stop widening, which damps the feedback
  loop. That suits the first aim, a stable model. Turbulence that lasts is in effect treated as
  normal.
- **Decided: the long-run memory is 5,000 steps,** faded in the same way as the recent memory (average
  age 2,500 steps); 1,000 and 20,000 are also tried. It must be much longer than the recent memory W
  (50–200 steps), or recent ÷ long-run would hardly move from 1; and short enough to adapt, so that it
  averages over the normal swings (Fig. 4's bursts last of order 100 steps, q(t) swings over about 250)
  but drifts during spells much longer than usual. 5,000 steps is 0.5% of a 10^6-step run.
- **Decided: the start of a run.** Until W − k changes (a full window) have been seen, R = 1 and
  λ = λ₀, so the providers behave as in the Fig. 3c model (fixed depth), as the momentum traders follow
  no trend before their window fills (D31). The long-run average then starts from the first recent value
  and is a plain average of all values so far until 1/count falls to its fading weight (count = half its
  memory, 2,500 for 5,000 steps), after which it fades, as the momentum traders' typical size does
  (D31). Its first few thousand steps are therefore rough; in a 10^6-step run that is under 1%, but
  short trial runs leave them out of the statistics (below).
- **Decided: two shapes of reaction, both tried, with coupling C = 1.** With R = recent volatility ÷
  long-run average (about 1 in normal times), the providers' mean entry depth is:
  - **widen only:** λ = λ₀ · (1 + C · max(R − 1, 0)). As in Eq. 4, λ₀ is a floor: providers back away
    when volatility is above normal and never come closer than λ₀.
  - **linear both ways:** λ = λ₀ · (1 + C · (R − 1)). Providers also come closer when it is quieter
    than normal, so the average depth stays near λ₀. With C = 1 this is λ = λ₀ · R, depth in
    proportion to volatility, roughly the relation between spread and volatility seen in real markets
    (Wyart et al. 2008). It cannot go below zero for C ≤ 1; a larger C would need a floor.

  A straight copy of Eq. 4, λ₀ · (1 + C · R), is not used: Eq. 4's |q − 1/2| is zero when the order flow
  is balanced, but normal volatility is not zero (R ≈ 1), so providers would sit at (1 + C) λ₀ even in
  normal times. Eq. 4's C = 10 does not carry over either: R is noisy (with k = 10 and W = 100 an
  estimate rests on about 10 independent changes, so R wobbles by roughly ±20–30% from noise alone),
  and C = 10 would make providers react mostly to that noise. Eq. 4's form also explains Fig. 4's wide
  spread: |q − 1/2| ÷ √⟨(q − 1/2)²⟩ averages about 0.8, so the mean depth there is about 9 λ₀.
- **Decided: no cap on λ.** However large R gets, nothing limits how far out the providers place
  their orders. The only damping is the long-run reference, which catches up during a lasting
  turbulent spell. A short, sharp burst is therefore not limited: if the trial runs show the loop
  running away, a cap is the first thing to reconsider.
- **Decided: every volatility provider has the same settings** (measure, k, W, long-run memory, form,
  C), so they all see the same recent volatility and react to it in the same way, as all providers
  react to the same q(t) in Eq. 4. This is a basic first model. The volatility is then worked out
  once per step instead of once per provider, which keeps runs fast. It also stands for a shared
  reaction across the market: when volatility rises, all of them back away together. Different
  settings per provider (different thresholds or memories) are a later step.
- **Decided: every provider is a volatility provider.** The Fig. 4 providers (Eq. 4) are replaced
  completely; there are no ordinary fixed-depth providers alongside them.
- **Not addressed:** the size of the spread. It is set mainly by the mean entry depth λ₀ = 100 ticks;
  volatility providers would make the spread change with volatility but not make it small.
- **Implementation** (`abm/volatility_provider.py`; `run_simulation(volatility=...)`):
  - `VolatilityGauge` works out the depth once per step from the mid-prices up to the end of the step
    before, and every provider receives it, as Eq. 4's λ(t) is passed in. It uses no random numbers:
    with C = 0 a run is identical, step for step, to the fixed-depth run (tested).
  - `VolatilityProvider` is the paper's `LiquidityProvider` with this depth: same chance to act, same
    side choice, same exponential draw of the distance from the price.
  - A step with one side of the book empty (no mid-price) is skipped by the gauge.
  - Fading averages give each new value the weight 1/(average age): 2/W for the recent volatility and
    2/L for the long-run average.
  - R uses the long-run average from before the current value is added.
  - The depth never goes below 1 tick, so the exponential draw stays defined. With C = 1 and the
    "linear" form this is reached only if the mid-price has not moved at all over the whole window.
- **Trial runs** (`experiments/volatility_sweep.py`, `cluster/volatility_sweep.slurm`): all 216
  combinations, plus two controls: Fig. 4 itself and the same takers with a fixed depth (Fig. 3c), 218
  jobs. Each is N_A = 500, 4 runs of 120,000 steps; the first 20,000 steps of each run are left out of
  the statistics while the long-run averages settle. Each combination is checked against D38
  automatically.
- **Trial results (19 November 2026; redone on the mid-price on 20 November, D37).** All 218 jobs
  finished (`results/volatility_sweep/summary.csv` and `summary.png`). There are about 12.5 trades per
  step in every run, so 1,000 trades is about 80 steps. No mid-price gaps occurred. The first
  write-up used the trade price by mistake; the numbers below are all for the mid-price, apart from
  the bid-ask bounce.
  - **No combination passes all three tests.** 136 of 216 pass (a), 1 passes (b) and 4 pass (c).
  - **(b) and (c) do not depend on the providers.** The values are almost the same in every stable
    combination and in both controls:

    | | Model | E-mini |
    |---|---|---|
    | H at 1,000 trades | 0.27–0.55 (median 0.37; fixed depth 0.37, Fig. 4 0.47) | 0.51 |
    | H first reaches 0.5 at | about 950–3,400 trades (fixed depth about 2,000) | about 125 trades |
    | autocorrelation of trade-to-trade changes, lag 1 | 0.00 | −0.06 |
    | autocorrelation of 100-trade changes, lag 1 | −0.37 to −0.06 (stable setups −0.35 to −0.25; controls −0.32, −0.31) | −0.01 |
    | bid-ask bounce (trade price, lag 1; not tested) | −0.49 | −0.32 |

    The only combinations that pass (b) or (c) are four linear ones with W = 50 and L = 5,000 or
    20,000, where the spread has collapsed to 1–3 ticks (see the linear form below). The one that
    passes (b) has a kurtosis of about 500 even at 1,000 trades.

    In both controls the mid-price H falls to about 0.24 at 75–270 trades and only reaches 0.5 at
    about 1,200–2,000 trades. The model's prices therefore move back towards earlier levels over
    roughly 10–200 steps, with or without volatility providers. This matches the Preis model's own H
    below 0.5 at short times, and the strong negative autocorrelation of prices that Farmer, Patelli
    and Zovko (2005) and Smith et al. (2003) report for order books with random order flow.

    The volatility provider changes only the mean distance λ at which providers place their orders,
    and how it varies over time. Everything else is the same in every run of the trial:
    - the takers: market orders, with the buy probability q(t) following the mean-reverting walk;
    - the providers' chance to act, their side choice and the exponential draw of the distance;
    - cancellation: each order in the book removed with probability δ = 0.025 per step;
    - α, μ, N_A and λ₀ = 100.

    Since (b) and (c) come out the same whatever λ does, including in the fixed-depth control, they
    are set by these fixed parts. Which parts is not yet tested. Likely explanations:
    - **The spread comes from λ₀.** Orders are placed about 100 ticks from the price on average, which
      leaves a gap of about 24 ticks between the best bid and the best ask.
    - **The mid-price reverting comes from cancellation (untested).** Orders left in the book hold a
      memory of where the price has been. With δ = 0.025 an order lasts about 1/δ = 40 steps on
      average, about 500 trades. The reversion is strongest at about 6–22 steps (75–270 trades) and has
      faded by about 80–160 steps (1,000–2,000 trades), a few order lifetimes.
    - **H above 0.5 at about 10,000 trades comes from the takers (untested).** q(t) stays away from 1/2
      for about 250 steps at a time, so the order flow leans one way and the price drifts over that
      time. That gives a mid-price H of 0.64–0.68 at about 12,000 trades.

    Varying δ or λ₀ with fixed-depth providers would test the first two.
  - **(a) passes for every widen combination, but it says little.** All 108 widen combinations pass,
    with median kurtosis 53, 5.7, 3.1 and 2.7 at 1, 10, 100 and 1,000 trades, against the E-mini's
    60.9, 8.6, 3.5 and 2.9. The fixed-depth control passes too (50.9, 5.4, 2.9, 2.6), so the pass does
    not come from the volatility provider. At 1–10 trades the values mostly reflect how rarely the
    mid-price moves (unchanged over 93% of trades in the model, 98% in the E-mini; see D38 (a)). At
    100 and 1,000 trades the model is slightly below 3, so its tails there are thinner than a normal
    distribution's; the E-mini is at or slightly above 3.
  - **Widen form: a small effect at C = 1.** Mean depth is 104–112 ticks and the largest depth 207
    ticks (median; 350 at most). The statistics stay close to the fixed-depth control.
  - **Linear form: tails that do not fade, and unstable with long memory.** With L = 1,000 the
    kurtosis comes down more slowly than the E-mini's (median 68, 7.3, 3.9, 3.6), and 12 of the 36
    combinations fail (a). With L = 5,000 or 20,000 the kurtosis stays high at every lag (median 7.4
    and 6.8 at 100 and 1,000 trades for L = 5,000; 20 and 22 for L = 20,000). In 35 of these 72
    combinations the depth reaches the 1-tick floor. With W = 50 the median spread falls to about 7
    ticks and the median kurtosis is 870, 92, 48 and 48. At worst the spread is 1.2 ticks and the
    kurtosis 13,858, 1,414, 683 and 504 (`abs_k20_W50_fixed_L20000_linear`). A likely cause is a
    narrowing loop: in a quiet spell the depth drops below λ₀, so orders sit closer to the price and
    price changes get smaller, so recent volatility falls further below the slowly moving long-run
    average, and the depth drops again. With W = 200 the spread stays at about 24 ticks. The linear
    form with L = 1,000 stays stable (spread 23.5–24.4 ticks).
  - **Settings that hardly matter:** the measure (std or abs), k (5, 10, 20) and fixed against fading
    memory change the results very little. Only W and L matter: a shorter W and a longer L give
    larger and more variable depths and higher kurtosis.
  - **Conclusion from the trial:** most of the gap to the E-mini in trade time comes from the parts
    the trial held fixed (the takers, λ₀ and cancellation), which give the wide spread and the
    reverting price. It does not come from how the providers react to volatility. Whether
    to keep the volatility provider, change it or throw it out (D38): **[Open]**.

**D40. Narrower books: the four strongest setups at λ₀ = 30, 10, 8, 7, 6 and 5. [Assumed]**
- **Why.** In the first trial (D39) tests (b) and (c) fail in every stable setup and in both
  controls, all at λ₀ = 100. Prices in order books with random order flow are known to be
  anti-correlated at short times (Farmer, Patelli and Zovko 2005; Smith et al. 2003), and Smith et
  al. find the effect weaker when ticks are coarse compared with the typical price scale. The model's
  book is also in a different regime from the E-mini. Wyart et al. (2008) separate large-tick
  markets, where the spread is nearly always one tick and the queue at the best price is far larger
  than a trade (trade ÷ queue about 0.01), from small-tick ones (about 0.2–0.3). The E-mini is
  large-tick (spread 1.02 ticks, 99% of the time at one tick, trade ÷ queue 0.012); the model at
  λ₀ = 100 is not even small-tick (spread 24 ticks, never one tick, trade ÷ queue 0.5). The first
  trial varied the depth over time around λ₀ = 100 but never changed λ₀ itself.
- **Values.** At λ₀ = 100 the spread is about λ₀ ÷ 4, which puts the E-mini's one tick at λ₀ ≈ 4.
  A second estimate from the queue: the book holds about 1,200 orders per side at N_A = 500 whatever
  λ₀ is (Eq. 3); spread over about λ₀ ticks, the queue at the best price is roughly 1,200 ÷ λ₀, and
  the E-mini's queue is about 80 trades, which puts λ₀ near 15. This is rough, since market orders
  eat the orders nearest the mid-price.

  A check before the trial (fixed-depth providers, one run of 15,000 steps, the first 3,000 left
  out) found a lower limit:

  | λ₀ | spread (ticks) | median queue at the best price | trades that move the mid-price |
  |---|---|---|---|
  | 10 | 2.4 | 14 | 3.7% |
  | 5 | – | – | 0.54% |
  | 3 | 1.00 | 164 | 0% |
  | 2 | 1.00 | 325 | 0% |
  | E-mini | 1.02 | 173 | 2.4% |

  At λ₀ = 3 and below the queues are so long that the takers never empty one, and the price does not
  move at all; none of the D38 statistics can be computed. The E-mini's mid-price moves on 2.4% of
  trades, between λ₀ = 5 and 10. **Decided:** λ₀ = 30, 10, 8, 7, 6 and 5. Not chosen: 3, 2 and 1
  (a frozen price).
- **Setups.** The first trial's top ten (stable, passing (a) on the mid-price, closest to the
  E-mini) were mostly copies of one setup, since the measure, k and fixed against fading memory
  hardly matter (D39). **Decided:** one setup from each group of form, W and L that behaves
  differently, the closest to the E-mini in its group:

  | Setup | Reaction | W | L | κ₁₀₀ / κ₁₀₀₀ at λ₀ = 100 |
  |---|---|---|---|---|
  | 105 (`std_k20_W200_fading_L1000_linear`) | both ways | 200 | 1,000 | 3.29 / 2.93 |
  | 21 (`std_k5_W100_fading_L1000_linear`) | both ways | 100 | 1,000 | 3.59 / 3.30 |
  | 35 (`std_k5_W200_fading_L5000_linear`) | both ways | 200 | 5,000 | 4.19 / 3.71 |
  | 84 (`std_k20_W50_fading_L20000_widen`) | outward only | 50 | 20,000 | 3.17 / 2.82 |

  "Closest" uses |H₁₀₀₀ − 0.51| ÷ 0.1 + |ρ₁₀₀ + 0.01| ÷ 0.1 + |κ₁₀₀ − 3.5| + |κ₁₀₀₀ − 2.9|. The
  weighting is a choice for ranking only, not a test. The outward-only groups all behave alike and
  close to the fixed-depth control, so one stands for them.
- **Controls.** Fixed-depth providers at every λ₀, to tell the effect of a narrower book from the
  effect of the volatility providers in it.
- **Judging.** As in the first trial: D38 on the mid-price. A setup that loses its fat tails (fails
  (a)) at a smaller λ₀ is dropped. Also reported, though not pass/fail: the share of trades that
  move the mid-price, the spread and its share at one tick, and the median queue at the best price.
- **What changes at small λ₀.**
  - The providers' mean depth cannot go below 1 tick (D39). At λ₀ = 5 the linear form reaches this
    floor when R falls below 0.2, so it rarely matters.
  - The depth draws are coarse: at λ₀ = 5 most orders land 0–10 ticks from the mid-price.
  - Orders are placed on their own side of the mid-price, so they never cross the spread (D6).
  - Trades per step (about 12.5) do not depend on λ₀, so the trade-time scale is unchanged.
- **Runs** (`experiments/lambda_sweep.py`, `cluster/lambda_sweep.slurm`): 5 setups (the control and
  the four) × 6 values of λ₀ = 30 jobs. Each is the same as in the first trial: mean-reverting
  takers, N_A = 500, 4 runs of 120,000 steps, the first 20,000 left out. `collect` sets the first
  trial's λ₀ = 100 results beside them.
