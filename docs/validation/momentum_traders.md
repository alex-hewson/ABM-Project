# Checks: Momentum traders

Momentum traders, first look and cluster sweep (D31). D numbers refer to `../decisions.md` (D1-D37) and `../volatility_provider/decisions.md` (D38 on), P numbers to `../paper_model.md`. Section numbers run across all the files in this folder; `README.md` here lists which file holds each. Numbers quoted are from the runs named; see `results/` and the code version recorded inside each results file.

---

## 15. Momentum traders (first look)

Fig. 2 setup, no value traders, N_A = 250, 40,000 steps, 6 runs per setting (D31). "Typical move" is
the RMS price change over 200 steps; the autocorrelation is of changes over 10-step blocks, at a lag
of 1 and 3 blocks. No setting emptied a side of the book or left a market order unfilled.

**Window 10, fixed scale of 10 ticks** (the first design):

| Momentum traders | Typical move | Autocorr. lag 1 / lag 3 | Typical predicted move |
|---|---|---|---|
| none | 17.9 | −0.30 / −0.02 | – |
| 50, order 1 | 20.7 | −0.21 / −0.03 | 9 |
| 150, order 1 | 29.4 | +0.17 / −0.20 | 10 |
| 50, order 2 | 18.7 | −0.38 / −0.02 | 45 |
| 150, order 2 | 19.4 | −0.65 / −0.21 | 57 |
| 50, order 3 | 18.5 | −0.29 / −0.03 | 222 |

Over 10 steps the mid-price mostly bounces between bid and ask, so the 2nd and 3rd derivatives are
mostly noise, and the order-2 traders made the bounce stronger instead of following a trend.

**Window 50, each order scaled by its own typical prediction** (the current design):

| Momentum traders | Typical move | Autocorr. lag 1 / lag 3 | Kurtosis |
|---|---|---|---|
| none | 17.9 | −0.30 / −0.02 | 2.88 |
| 50, order 1 | 35.0 | −0.19 / +0.11 | 2.30 |
| 100, order 1 | 66.4 | +0.08 / +0.31 | 1.54 |
| 100, order 2 | 20.4 | +0.17 / −0.21 | 2.75 |
| 100, order 3 | 17.7 | +0.01 / −0.35 | 2.91 |
| 100, orders 1/2/3 mixed | 27.2 | −0.02 / −0.08 | 2.66 |

- Order-1 traders amplify trends: with 100 of them the price moves nearly four times as much, and
  changes 30 steps apart are clearly alike.
- Order-2 and order-3 traders read the curvature, so they tend to sell before a rise turns and buy
  before a fall turns: short trends, then reversals, but little extra movement.
- No fat tails. With strong order-1 momentum the kurtosis falls well below 3: the price swings in
  long, regular waves instead of making rare large jumps.

**Shock test with momentum and value traders** (250 agents, 200 runs per size; value traders: 50, mean
error 50, news 1; momentum traders: order 1, window 50; `results/shock/shock_momentum50.png`,
`shock_value50_momentum50.png`, `shock_value50_momentum100.png`,
`results/meeting/11_momentum_vs_value_shock.png`). Price relative to the true value, 300-unit sell:

| Market | At the order | Lowest point | Half-life |
|---|---|---|---|
| 50 value traders only (sweep) | −37.6 | −37.7 | 92 steps |
| 50 momentum traders only | −35.1 | −68.6 | never |
| 50 value + 50 momentum | −38.8 | −45.8, about 45 steps later | 175 steps |
| 50 value + 100 momentum | −36.0 | −65.2, about 70 steps later | 218 steps |

- Momentum traders keep selling after the order, so the price slides further for 50–70 steps, close
  to their 50-step window. Without value traders it stays down (the control run also wandered by
  about 20 ticks, so part of the extra fall is noise).
- With value traders the fall then turns, the momentum traders follow the new upward trend, and the
  rebound is steep: a V-shape. With 100 momentum traders the price is back at the old level after
  about 300 steps, about the same time as with value traders alone, with a slight overshoot.
- The half-life is measured from the drop at the order, so it does not show the deeper trough or the
  faster rebound.

---

## 18. Momentum trader sweep (cluster)

All 242 combinations (D31; `experiments/momentum_sweep.py`; results in `results/momentum_sweep/`,
table `summary.csv`, heatmaps `summary_*.png`). Shock tests: 250 agents, 200 runs per size; normal
times: N_A = 500, 16 runs of 10^6 steps. With value traders: 20% of takers (50 in the shock test).

**Shock with value traders** (300-unit sell; control: lowest −37.7, half-life 92 steps):
- 10% momentum: the fall is no deeper (−37 to −39 in every mix and window), but recovery is slower:
  half-life 100–270 steps.
- 25% and 50%: deeper and slower. Order 1 is the strongest (50%, window 50: −70, half-life 219);
  order 3 the weakest (−53, 170). Longer windows slow recovery much more: order 1 at 50% with a
  window of 500 falls to −91 and has a half-life of 1,852 steps, close to not recovering.

**Normal times:**
- Order 1 makes the price trend: at 25% the correlation of consecutive 50-step changes turns
  positive (+0.19 at window 50, without value traders), and at 50% the typical move over 200 steps
  is 5 times the control (92 against 19 ticks). With 20% value traders the same happens at 50%
  momentum (+0.48, 63 ticks).
- Orders 2 and 3 do something different: at short windows they make the price oscillate. At 50% with
  window 50 the correlation of consecutive 50-step changes is −0.80 (order 2) and the local Hurst
  exponent at a lag of 100 steps is 1.6 (order 2) and 2.2–2.4 (order 3, window 100). H above 1 is
  not a Hurst exponent in the usual sense: the RMS change rises faster than the lag, as it does over
  the first half of a regular wave. The waves seem to have a period of about twice the window. At
  long windows (200–500) orders 2 and 3 trend like order 1. The earlier view that orders 2 and 3 add
  little (section 16) holds for news, not for normal times.
- No fat tails anywhere: the kurtosis of 200-step changes is 1.1–3.6. Strong momentum lowers it well
  below 3 (1.1 for order 1 at 50%): large, regular swings, close to the value for a sine wave (1.5).
- **To check:** order 1 at 50%, windows 200 and 500, without value traders: H(100) is 0.98 but the
  correlation of consecutive 50-step changes is −0.25 and −0.37, and the fall after a shock (−45 and
  −76) is smaller than at window 100 (−129). These do not fit together; individual price paths
  should be looked at.
