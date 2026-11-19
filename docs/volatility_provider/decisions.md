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
  time (D37) the kurtosis of 100-trade changes is 6.8 (2.5 for the paper's Fig. 2 agents) and the
  autocorrelation of the size of 100-trade changes is +0.42 at lag 1 and +0.30 at lag 10 (+0.08 and
  +0.01 for Fig. 2). Its weak points: the spread is about 200 ticks (E-mini: 1), and its stylised
  facts come from a hidden quantity, the takers' buy probability q(t), which no trader can see.
- **One agent at a time.** Each new kind of agent is added to the starting point on its own and kept
  only if the model keeps or gains stylised facts when checked against the E-mini data (D37);
  otherwise it is thrown out. The next agent is not started until this is settled.
- **Theory first.** The reasoning behind each agent and the meaning of each of its parameters are
  checked and agreed before the agent is implemented.
- **Decided: pass/fail by shape, as a crude first cut of very bad setups.** A setup passes if, in trade
  time (D37), it shows all three of:
  - **(a) fat tails that fade with lag:** kurtosis of the price changes above 3 at short lags (1–10
    trades), falling as the lag grows, and close to 3 by 100–1,000 trades. E-mini: 12.6, 5.9, 3.2 and
    2.9 at 1, 10, 100 and 1,000 trades (aggregational Gaussianity).
  - **(b) a random walk at long lags:** H rising towards 0.5 and close to it beyond a few hundred
    trades. E-mini: 0.24 at 10 trades, 0.51 at 1,000.
  - **(c) a bounce and nothing else:** negative autocorrelation of trade-to-trade changes at lag 1
    (E-mini −0.32), and the autocorrelation of 100-trade changes close to zero (E-mini within ±0.02 at
    lags 1–5).

  Judged by shape, not by distance from the E-mini numbers: the E-mini statistics come from two days
  in a stressed week next to the flash crash (5 and 7 May 2010), so they are rough targets. Closer
  matching comes later.

  Left out for now:
  - **volatility clustering:** in trade time it is almost absent in the E-mini (+0.01 at lag 1, +0.03
    at lag 10 for the size of 100-trade changes), because counting time in trades removes most of it;
    it needs a clock-time comparison to be judged fairly.
  - **spread and depth:** far from the E-mini in every version of the model (Fig. 4: spread 207 ticks
    against 1; median trade ÷ size at the best price 1.0 against 0.012), but set mainly by λ₀, which
    the volatility provider does not change (D39).

  The starting point itself fails (a) and (b): Fig. 4's kurtosis stays near 7 at every lag (8.8, 7.1,
  6.8, 7.7) and its H is 0.21 at 1,000 trades.
- **How "by shape" is tested** (`experiments/volatility_sweep.py`), so that every combination is judged
  the same way. These numbers are rough on purpose:
  - (a) kurtosis at 1 or 10 trades above 3.5; kurtosis at 100 and at 1,000 trades below that; and
    kurtosis at 100 or 1,000 trades between 2.5 and 4.
  - (b) H at about 1,000 trades between 0.4 and 0.6, and higher than H at 10 trades. To be revisited
    once the trial results are in: the providers' memory W is 50–200 steps, roughly 600–2,500 trades
    at N_A = 500, so their effect on H may only show at lags longer than 1,000 trades (e.g. a test over
    1,000–10,000 trades). The check is redone from the saved statistics, so this needs no new runs.
    **Revisited after the trial (D39, trial results):** H at 1,000 trades is about 0.15 in every
    combination and in both controls, and every one of them reaches 0.5 somewhere between 2,000 and
    6,000 trades. A test over 1,000–10,000 trades would therefore let everything pass, controls
    included, and would not separate one setup from another. Whether to change (b): **[Open]**.
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
    (`validation.md`, section 15).
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
- **Trial results (19 November 2026).** All 218 jobs finished (`results/volatility_sweep/summary.csv`
  and `summary.png`). There are about 12.5 trades per step in every run, so 1,000 trades is about 80
  steps. No mid-price gaps occurred.
  - **No combination passes all three tests.** 38 of 216 pass (a), none pass (b) and none pass (c).
  - **(b) and (c) do not depend on the providers.** The values are almost the same in every
    combination and in both controls:

    | | Model (all 218 runs) | E-mini |
    |---|---|---|
    | H at 1,000 trades | 0.10–0.21, nearly all 0.15 | 0.51 |
    | H first reaches 0.5 at | about 3,400 trades (Fig. 4), about 5,600 (fixed depth) | about 100 trades |
    | lag-1 autocorrelation of trade-to-trade changes (bounce) | −0.49 | −0.32 |
    | autocorrelation of 100-trade changes, lag 1 | −0.45 to −0.50 | about 0 |

    Part of this comes from the spread. At about 24 ticks it is wide compared with how far the price
    moves over 100 trades, so trade prices jump back and forth across it. The mid-price also
    reverts, though: in both controls its H falls to about 0.24 at 75–270 trades and only reaches
    0.5 at about 1,000–2,000 trades, and its 100-trade changes have an autocorrelation of −0.32 at lag 1.
    The model's prices therefore move back towards earlier levels over roughly 10–200 steps, with or
    without volatility providers. This matches the Preis model's own H below 0.5 at short times.

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
      time. That gives H of 0.6–0.66 at long lags.

    Varying δ or λ₀ with fixed-depth providers would test the first two.
  - **(a) passes only weakly.** The kurtosis curves that pass are flat after the first lag, e.g.
    4.9, 3.9, 3.8 and 3.8 at 1, 10, 100 and 1,000 trades (`std_k5_W50_fading_L1000_linear`),
    against the E-mini's 12.6, 5.9, 3.2 and 2.9. No combination shows tails that fade with lag the
    way the E-mini's do. The passes are 27 linear with L = 1,000, 4 linear with L = 5,000, and 7 widen
    (W = 50 or 100 with L = 5,000 or 20,000).
  - **Widen form: a small effect at C = 1.** Mean depth is 104–112 ticks and the largest depth 207
    ticks (median; 350 at most). The statistics stay close to the fixed-depth control (median
    kurtosis 3.4, 2.7, 2.6, 2.7).
  - **Linear form with long memory (L = 5,000 or 20,000): unstable.** In 35 of these 72 combinations
    the depth reaches the 1-tick floor. With W = 50 the median spread falls to about 7 ticks, the
    mean depth to about 26 ticks and the kurtosis at 1 trade rises to about 55. At worst the spread
    is 1.2 ticks and the kurtosis 569 (`abs_k20_W50_fixed_L20000_linear`). A likely cause is a
    narrowing loop: in a quiet spell the depth drops below λ₀, so orders sit closer to the price and
    price changes get smaller, so recent volatility falls further below the slowly moving long-run
    average, and the depth drops again. With W = 200 the effect is small (spread about 24, kurtosis
    at 1 trade about 8). The linear form with L = 1,000 stays stable (spread 23.5–24.4 ticks).
  - **Settings that hardly matter:** the measure (std or abs), k (5, 10, 20) and fixed against fading
    memory change the results very little. Only W and L matter: a shorter W and a longer L give
    larger and more variable depths and higher kurtosis.
  - **Conclusion from the trial:** most of the gap to the E-mini in trade time comes from the parts
    the trial held fixed (the takers, λ₀ and cancellation), which give the wide spread and the
    reverting price. It does not come from how the providers react to volatility. Whether
    to keep the volatility provider, change it or throw it out (D38): **[Open]**.
