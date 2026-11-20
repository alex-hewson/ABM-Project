# HFT/Order-Book ABM — Project Plan

The current aim, where things stand, the open questions and what comes next. What has been done
is in `changelog.md`. The choices made are in `decisions.md` (D1–D37) and in each later part's
decisions file, e.g. `volatility_provider/decisions.md` (D38 on); the evidence for them is in
`validation/`; what the paper itself defines is in `paper_model.md`. `README.md` in this folder
says which file is which.

Paper: Preis, Golke, Paul & Schneider (2006), "Multi-agent-based Order Book Model of financial
markets", EPL 75, 510.

## Project aim (from 17 November 2026)

**A model that behaves like a normal market almost all the time, but on very rare occasions
produces a flash crash that starts from features of the order book itself.**

Set at the supervisor meeting of 17 November 2026. Recovery after a crash has already been studied
in other papers, so creating a crash from within the model is the more interesting question. Most
runs should show nothing of note; a crash should be rare and should not need an outside shock.

**Method.** First build a model that matches the stylised facts of a real market (D37, compared with
the E-mini data), with no crash needed. Add one kind of agent at a time and keep it only if the
stylised facts survive (D38). Start from Preis-type agents, with providers that react to recent
volatility (D39), then possibly value traders (D28). No model can be fully accurate: different
parameter mixes can give the same outcome.

The earlier aims (recovery after a large order, from 13 October 2026; recovery as the research
question, November 2026) are recorded in `changelog.md`.

## Where things stand

- **Phase 1** (reproducing Preis et al. 2006) is finished and tagged `baseline-v1` (D23).
- **Phase 2, current aim:** the volatility provider (D39) has been trialled over 216 setups. None
  passes all three D38 tests on the mid-price. The fat tails are within reach, but the price
  reverts too strongly (tests (b) and (c)), whatever the providers do. The model's book is also in
  a different regime from the E-mini (a spread of about 24 ticks against 1).
- **Running:** the mean entry depth trial (D40), the four strongest volatility provider setups and
  a fixed-depth control at λ₀ = 30, 10, 8, 7, 6 and 5, on the cluster.

Code layout and how to run things: see `../README.md`.

**Git:** `main` holds Phase 1 and Phase 2 up to the E-mini data. Current work is on the branch
`volatility-provider`; the code tidy-up is on `code-tidy-up`.

## Open questions

- Price definition for the paper's figures: the median trade price is adopted; it is a calibration
  of a detail the paper does not specify, and must be reported as such (D11). Comparisons with the
  E-mini use the mid-price (D37)
- Whether the paper's lognormal fit is per side or combined (D14)
- The q_provider variant of asymmetric flow, not implemented (D16)
- Mirrored vs blocked reflection in the bounded walk, untested (D18)
- Whether to change test (b) of D38 (D38)
- Whether to keep, change or throw out the volatility provider (D39)

## Immediate next steps

1. Collect and judge the mean entry depth trial (D40): whether a narrower book alone (the
   controls) brings H and the 100-trade autocorrelation closer to the E-mini, and whether the
   volatility providers keep their fat tails.
2. At least two kinds of agent matching the stylised facts by the supervisor meeting of
   24 November 2026. Then possibly value traders (D28).
3. Write down what counts as "correct" for takers and providers alone (the regime, the facts a book
   of random traders can produce, and what is left to later agents), from the literature checked on
   20 November 2026 (Farmer, Patelli and Zovko 2005; Smith et al. 2003; Wyart et al. 2008).
4. Ask for "normal" E-mini data to calibrate on. The days available (5 and 7 May 2010) are either
   side of the flash crash, in a period of market stress, so they may not be typical.
5. Then look for what in the order book could, very rarely, set off a crash.
6. Still to do from earlier: the finite-size analysis of the phase diagram (section 19), and the
   write-up of the Phase 1 reproduction for the methodology chapter.
