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
- **Decided: the start of a run.** Until W steps of mid-price changes exist, R = 1 and λ = λ₀, so the
  providers behave as in the Fig. 3c model (fixed depth), as the momentum traders follow no trend before
  their window fills (D31). The long-run average then starts from the first recent value and is a plain
  average of all values so far until it holds as many as its memory, after which it fades, as the
  momentum traders' typical size does (D31). Its first few thousand steps are therefore rough; in a
  10^6-step run that is under 1%, but short trial runs may need to leave them out of the statistics.
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
