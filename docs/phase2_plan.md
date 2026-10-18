# Phase 2 Plan (draft)

Rough plan for the rest of the project. To discuss with supervisors.

## Idea

Study how a market recovers after a flash crash or flash rally, not what causes it. The cause is
taken to be a large order.

In the base model the price never recovers after a large order. Nothing pulls it back, and the book
refills at a rate set only by the cancellation rate. So agents that react to the market are needed.

The model is to be validated on real order book data from a traditional market (E-mini futures)
first. Crypto or prediction markets only if there is time.

## Done so far

- Shock test: one large market order, then the price, spread and book are recorded as it recovers.
- Orders bigger than one unit.
- Agents with different speeds and order sizes (1 unit every step, 2 every 2, 4 every 4). Each type
  trades the same volume. On their own they do not change the average recovery.
- Value traders, which buy below their own idea of the value and sell above it. With them the price
  recovers. At the first settings tried, they also hold the price too still in normal times.

## Steps

1. Sweep the value trader settings (how many, how long their memory, how far apart their values)
   to find settings that give recovery without holding the price still. Running on the cluster.
2. E-mini data: measure order arrival and cancellation rates, order sizes, the spread and the depth
   of the book, and set the model's parameters from them. Then find large orders in the data and
   measure how the real book recovers after them.
3. Compare the model with the data: recovery after large orders, plus spread, volatility and the
   return distribution.
4. Fast and slow value traders. Maybe a market maker with an inventory limit.
5. If time allows: crypto or prediction markets, and interventions such as a trading pause.

Each step should give a result on its own. Rough timing: steps 1–3 by Christmas, step 4 by the end
of February, then write-up.

## Unsure about

- What the data contains: its form, dates, and the rules for using it.
- How to turn simulation steps into real time.
- What "recovery" should mean: the price coming back, the book refilling, or both. And how to
  measure it in real data.
- Whether value traders can give recovery without making the price too still.

## Not planned

Herding traders (Novotny 2026; Lux & Marchesi 1999). Maybe at the end if there is time.

## Main references

- Preis, Golke, Paul & Schneider (2006), Multi-agent-based Order Book Model of financial markets,
  EPL.
- Kirilenko, Kyle, Samadi & Tuzun (2017), The Flash Crash: High-Frequency Trading in an Electronic
  Market, Journal of Finance.
- Farmer, Patelli & Zovko (2005), The predictive power of zero intelligence in financial markets,
  PNAS. An example of testing an order book model against real data.
