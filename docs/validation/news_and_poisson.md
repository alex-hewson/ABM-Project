# Checks: News and the Poisson trader

Event studies of news jumps and of large orders at random times (D32-D35). D numbers refer to `../decisions.md` (D1-D37) and `../volatility_provider/decisions.md` (D38 on), P numbers to `../paper_model.md`. Section numbers run across all the files in this folder; `README.md` here lists which file holds each. Numbers quoted are from the runs named; see `results/` and the code version recorded inside each results file.

---

## 16. News event study (first look)

News jumps (D32) inside long runs, averaged around every jump (D33). 250 agents, 50 value traders
(mean error 50, small step 1), momentum traders of order 1 with window 50, jumps of 30 ± 10 ticks at
a chance of 1 in 5,000 per step. 64 runs of 50,000 steps per market; 405 of 696 jumps used. News has
its own random numbers, so all three markets have the same jumps at the same times
(`results/news/compare.png`). Share of the jump taken into the price:

| Market | Step 0 | Half-way | 90% | Largest (when) | End |
|---|---|---|---|---|---|
| 50 value only | 0.04 | 114 steps | 441 steps | no overshoot | 0.97 |
| 50 value + 50 momentum | 0.01 | 76 steps | 250 steps | no clear overshoot | 0.96 |
| 50 value + 100 momentum | 0.04 | 70 steps | 127 steps | 1.18 (about 240 steps) | 0.99 |

- In every market the price takes in the whole jump and stays there. After news the price moves to
  a new level; after a shock (section 15) it comes back. The model tells the two apart.
- Almost nothing happens in the first step. The value traders who now disagree with the price trade
  at the rate μ, so the price moves over tens of steps, not at once.
- For the first 50 steps all three curves are the same. The momentum traders' window is 50 steps, so
  they only see the new trend once it has built up. After that they speed the move up: 90% is
  reached 1.8 times faster with 50 of them and 3.5 times faster with 100.
- With 100 momentum traders the price overshoots by about 18% of the jump, peaking about 240 steps
  after the news, and is back at the new value by about 450 steps.
- Together with section 15: momentum traders push the price further in whatever direction it is
  already going. After news that is towards the new value, so they help, with some overshoot. After
  a large order it is away from the value, so they deepen the fall.
- The "largest" value in the summary table is read off a noisy curve. Without momentum traders its
  maximum (1.05 at step 1,034) is noise, not an overshoot.

**Mixed momentum traders** (same jumps; 100 momentum traders split equally between orders 1, 2 and
3; `results/news/compare_mixed.png`): half-way after 79 steps, 90% after 320, no overshoot, end
0.95. This is close to value traders alone (114 and 441 steps), and slower than 50 order-1 traders
(76 and 250). Only a third of the mixed traders follow the slope; the order-2 and order-3 traders
add little push of their own, and the overshoot of the order-1-only market is gone.

**Jump size** (50 value traders, no momentum traders; jumps of 10 ± 3.3 ticks over 192 runs, 30 ± 10
and 100 ± 33 over 64 runs; `results/news/jump_sizes.png`). Share of the jump taken in:

| Jumps | Jumps used | Half-way | 90% |
|---|---|---|---|
| 10 ticks | 1,167 | 132 steps | 330 steps |
| 30 ticks | 405 | 114 steps | 441 steps |
| 100 ticks | 405 | 233 steps | 620 steps |

- Jumps of 10 and 30 ticks give the same curve within the noise (the 90% times differ because the
  curves are flat there, so where they cross 0.9 is noisy). Inside the value traders' spread
  (mean error 50 ticks), the response is proportional to the news, as D33 assumes.
- Jumps of 100 ticks are taken in about half as fast. At twice the mean error, nearly every value
  trader is on the same side at once, so there are no more traders to add: the buying pressure
  stops growing with the jump and the price climbs at a limited speed. Results in units of the jump
  hold for news inside the spread, not beyond it.

---

## 17. Poisson trader event study (first look)

The Poisson trader (D34) inside long runs, averaged around every order in bands of size (D35). 250
agents; chance 1 in 5,000 per step and 0.06 units per step waited (mean order 300 units); 64 runs of
50,000 steps per market; 364 of 651 orders used. The Poisson trader has its own random numbers, so
all three markets have the same orders at the same times (`results/pressure/compare.png`). In ticks,
every order shown as a sell:

| Market | Band (mean size) | Impact | Lowest | Half-life | Recovered |
|---|---|---|---|---|---|
| paper's agents | 0–150 (73) | −9.6 | −10.3 | never | 0.04 |
| | 150–400 (249) | −31.5 | −33.5 | never | 0.03 |
| | 400+ (695) | −95.5 | −95.5 | never | 0.23 |
| value 50 | 0–150 (73) | −10.1 | −10.1 | 93 | 0.80 |
| | 150–400 (249) | −31.6 | −31.6 | 88 | 1.01 |
| | 400+ (695) | −111.0 | −113.3 | 248 | 1.01 |
| value 50 + momentum 100 (order 1) | 0–150 (73) | −7.7 | −22.4 | 246 | 0.97 |
| | 150–400 (249) | −35.5 | −61.5 | 216 | 1.06 |
| | 400+ (695) | −101.3 | −135.6 | 291 | 1.08 |

- **The event study agrees with the single shock tests.** In the 150–400 band: without value traders
  the price never comes back (section 8); with 50 value traders the half-life is 88 steps (shock
  test: 92); with momentum traders as well the price falls further, to −62 about 70 steps later,
  then recovers with a half-life of 216 steps (shock test: −65 and 218). So the event study
  measures the same thing as the shock test, from orders at random times.
- **Momentum traders deepen the fall for every size,** by about 15–35 ticks, and slow the recovery.
  Even orders under 150 units (impact −8) are followed by a fall to −22.
- **Large orders often empty a side.** A side holds about 600 units at N_A = 250. Of the 80 orders
  over 400 units, 38–45 emptied it. Their impact is then capped by the size of the book.
- **Impact against size** (the price change in the step of the order, fitted between 30 and 500
  units): impact grows like size^0.82 (paper's agents), size^0.94 (value 50) and size^0.85 (with
  momentum). The three agree, as they should: the impact in the step of the order depends only on
  the book. The curve is not a straight line on log scales: it is flatter below about 50 units and
  steeper above about 100, so the book gets thinner further from the midpoint. Real markets show
  impact growing like the square root of size, but that law is for large orders split up and traded
  over time, not single market orders. Whether the model's single-order impact matches real data is
  a question for the E-mini data.
