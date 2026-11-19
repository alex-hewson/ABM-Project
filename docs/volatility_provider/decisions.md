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
- **[Open]** The pass/fail criteria: which statistics from the D37 comparison count, and how close to
  the E-mini each must be. To be fixed before the first trial.

**D39. The volatility provider: the first agent to trial. [Open]**
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
- **[Open]** before implementation:
  1. how recent volatility is measured, and over how many steps;
  2. what it is compared with (a long-run average, or a fixed value);
  3. the coupling strength C (Eq. 4 uses 10, on a different quantity);
  4. the shape of the reaction (linear as in Eq. 4, or capped);
  5. the same settings for every volatility provider, or each its own (thresholds, memory);
  6. all providers, or a share of them;
  7. whether the mean-reverting order flow of Fig. 4 stays (replacing only Eq. 4) or goes as well.
- **Not addressed:** the size of the spread. It is set mainly by the mean entry depth λ₀ = 100 ticks;
  volatility providers would make the spread change with volatility but not make it small.
