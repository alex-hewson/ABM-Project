# Phase 2 Plan (draft)

Rough plan for after the baseline model. To discuss with supervisors.

## Idea

Kirilenko et al. (2017) found that HFTs did not cause the Flash Crash, but could not absorb the
large sell order either. Intermediaries only held a few thousand contracts at most, while the sell
algorithm was selling 75,000.

Question: when does a large sell order turn into a flash crash in the Preis model, and what stops it?

## Steps

1. Add one large seller to the baseline. Compare selling at a fixed rate with selling a share of
   recent volume (like the May 2010 algorithm).
2. Add a few intermediaries with inventory limits. Vary the seller's size against the
   intermediaries' capacity.
3. Compare fast (HFT-like) and slow (market-maker-like) intermediaries.
4. Test interventions, e.g. a trading pause like the 5-second one on May 6.

Each step should give a result on its own, so the project can stop after any of them if time runs
short. Rough timing: steps 1–2 by Christmas, steps 3–4 by the end of February, then write-up.

## Unsure about

- How to define a crash. A percentage drop doesn't really work, since the price starts at 10⁶ ticks.
  Maybe relative to normal volatility instead?
- How to turn simulation steps into real time (the algorithm sold 9% of the last minute's volume).
- How the intermediaries should decide when to trade. Paddrik et al.'s position-limit rule is one
  option.
- Whether this is the right amount of work for the year.

## Not planned

Herding traders (Novotny 2026; Lux & Marchesi 1999). Maybe at the end if there is time.

## Main references

- Kirilenko, Kyle, Samadi & Tuzun (2017), The Flash Crash: High-Frequency Trading in an Electronic
  Market, Journal of Finance.
- Paddrik, Hayes, Scherer & Beling (2014), OFR Working Paper 14-09.
- Jacob Leal, Napoletano, Roventini & Fagiolo (2016), Rock around the clock, Journal of
  Evolutionary Economics.
