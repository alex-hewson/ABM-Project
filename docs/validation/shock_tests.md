# Checks: Shock tests

One large market order, then the recovery of the price and the book (D24, D25). D numbers refer to `../decisions.md` (D1-D37) and `../volatility_provider/decisions.md` (D38 on), P numbers to `../paper_model.md`. Section numbers run across all the files in this folder; `README.md` here lists which file holds each. Numbers quoted are from the runs named; see `results/` and the code version recorded inside each results file.

---

## 8. Shock test on the basic model

One market sell order of 50, 150 or 300 units, injected after 2,000 steps (D24). Basic model
(Fig. 2 parameters), N_A = 250, mean of 400 runs per size, 2,000 steps recorded after the shock
(`results/shock/shock_test.png`, made with `experiments/shock.py`, commit e3de4d1 plus the shock code).
Measures as in D25. Before the shock each side of the book holds 606 orders and the spread is 23.2
ticks.

| Size | Price at the shock | Price at the end | Share recovered | Spread at the shock | Spread half-life | Bids at the shock | Bids half-life | Bids 90% back |
|---|---|---|---|---|---|---|---|---|
| 50 | −7.9 | −6.5 | 0.20 | 39.2 | 2 steps | 557 | 28 steps | 89 steps |
| 150 | −18.0 | −18.2 | 0.00 | 59.3 | 1 step | 457 | 27 steps | 90 steps |
| 300 | −38.0 | −40.0 | −0.05 | 99.2 | 1 step | 307 | 28 steps | 90 steps |

Prices are changes in ticks from the step before the shock. The control with no shock ends at +1.0
ticks, so differences of 1–2 ticks are noise. That covers the 0.20 for size 50 (1.4 ticks).

- **The price does not recover.** It drops at the shock and stays there for the rest of the run.
  There is nothing in the model that knows the old price: providers place orders around the current
  midpoint.
- **The drop is half of the widening of the spread** (8 / 18 / 38 ticks against widenings of
  16 / 36 / 76). The sell order removes the top of the bid side; the ask side does not move, so the
  midpoint falls by half the gap. New orders then fill the gap around the new midpoint.
- **The spread closes in one or two steps.** About 37 new limit orders arrive each step, and many
  land inside the gap.
- **The bid side refills as Eq. 1 predicts.** A shortfall shrinks by a factor (1 − δ) each step, which
  gives a half-life of ln 2 / δ = 27.7 steps and 90% after ln 10 / δ = 92 steps (measured: 27–28 and
  89–90). The refill time does not depend on the size of the shock.
- The ask side is not affected.

---

## 9. Shock test with different provider types (first look)

The shock test of section 8, repeated with the providers changed (D27). Takers are the paper's.
Sizes 150 and 300, mean of 200 runs each (`results/shock/shock_providers2.png`, `shock_providers4.png`,
`shock_mixed.png`; commit 26eafb2 plus the agent-type code). The first row is section 8 (400 runs).

| Providers | Spread before | Price at the shock (150 / 300) | Bids half-life (150 / 300) | Bids 90% back (150 / 300) |
|---|---|---|---|---|
| all 1 unit every step | 23.2 | −18.0 / −38.0 | 27 / 28 steps | 90 / 90 steps |
| all 2 units every 2 steps | 22.2 | −18.5 / −38.7 | 29 / 28 | 93 / 97 |
| all 4 units every 4 steps | 21.8 | −18.0 / −37.9 | 27 / 28 | 85 / 86 |
| 100 / 100 / 50 of the three | 22.5 | −17.5 / −37.7 | 29 / 28 | 86 / 90 |

- **The provider type makes no clear difference to the average recovery.** The price impact and the
  refill time are the same within noise for every mix. The price still does not come back.
- This is expected. Every type supplies the same volume per step, and the refill time is set by the
  cancellation probability δ (section 8), which is the same for all of them.
- The spread before the shock is slightly narrower with bigger orders (21.8 against 23.2 ticks).
  Whether that difference is real has not been checked.
- Only averages over runs were compared. Bigger, slower orders should make single runs lumpier,
  which an average does not show.

---

## 10. Shock test with value traders

*First design, with a moving average of the price as the reference. Replaced by the true value (D30);
see section 12.*

The shock test of section 8, with some of the 250 takers replaced by value traders (D28). Sell orders
of 150 and 300 units, mean of 200 runs each (`results/shock/shock_value50.png`, `shock_value125.png`,
`shock_value125_spread10.png`; commit a6777e4 plus the value trader code). The first row is section 8.

Price change in ticks, measured from the step before the shock, for the 300-unit order:

| Value traders | Mean shift | At the shock | +10 steps | +50 | +100 | +200 | +500 | Half-life |
|---|---|---|---|---|---|---|---|---|
| none | – | −38.0 | −39.2 | −37.7 | −36.8 | −36.8 | −39.7 | never |
| 50 | 50 ticks | −37.7 | −31.3 | −23.2 | −18.5 | −10.8 | −5.9 | 101 steps |
| 125 | 50 ticks | −36.3 | −17.9 | −9.1 | −6.0 | −2.0 | −1.2 | 10 steps |
| 125 | 10 ticks | −34.1 | −7.5 | 0.0 | 0.0 | 0.0 | −0.2 | 3 steps |

- **With value traders the price comes back.** With 125 of them it recovers half of the drop in 10
  steps and 90% in 136 steps. The 150-unit order behaves the same way (half-life 13 steps).
- **More value traders, or values closer together, give a faster recovery.** With 50 traders the
  half-life is about 100 steps. With shifts of 10 ticks instead of 50 it is 3 steps.
- **The size of the first drop barely changes** (−34 to −38 ticks). The value traders act after the
  shock, not during it.
- **The bid side refills as before:** half-life 25–27 steps, 90% after 80–93 steps. The refill is still
  set by δ (section 8). So the price recovers faster than the book when there are many value traders.
- **The market stays stable.** No market order went unfilled. The book holds slightly more (613–648
  units per side against 606).
- **Side effects in normal times.** The spread is narrower (20.7, 18.1 and 12.4 ticks against 23.2),
  because value traders often rest orders inside it. In a trial of 48 runs the price also wandered
  less: a standard deviation of 8 ticks over 2,000 steps against 18.5 without value traders.

Checked in `tests/test_simulation.py`: 30 steps after a 300-unit sell, the price has come back by 32
ticks on average with 125 value traders (mean shift 10) and by 6 ticks without (20 runs each; the 6
is noise). The fast and per-agent methods agree with value traders present (volume 1238 vs 1243,
spread 18.1 vs 18.5).
