# Checks: Agent types

Agents with different speeds and order sizes in normal times (D27). D numbers refer to `../decisions.md` (D1-D37) and `../volatility_provider/decisions.md` (D38 on), P numbers to `../paper_model.md`. Section numbers run across all the files in this folder; `README.md` here lists which file holds each. Numbers quoted are from the runs named; see `results/` and the code version recorded inside each results file.

---

## 13. Agent types in normal times (no value traders)

Long runs without a shock or value traders, with every provider, every taker, or both placing 4 units
every 4 steps (D27). 10^5 steps, 8 runs, N_A = 500, median trade price (`results/agent_types/types_*.pkl`,
`results/meeting/6_agent_types_normal_times.png`). RMS and kurtosis are of the change over 200 steps.

| Agents | H(10) | H(100) | H(10^3) | RMS | Kurtosis | Autocorr. of changes | Of their size |
|---|---|---|---|---|---|---|---|
| paper's (1 unit every step) | 0.08 | 0.20 | 0.38 | 19.2 | 2.79 | −0.38 | 0.08 |
| providers 4 every 4 | 0.08 | 0.21 | 0.43 | 22.4 | 2.82 | −0.37 | 0.07 |
| takers 4 every 4 | 0.10 | 0.23 | 0.43 | 23.1 | 2.80 | −0.35 | 0.06 |
| both | 0.09 | 0.22 | 0.42 | 24.3 | 2.81 | −0.36 | 0.07 |

- Lumpier agents make the price move more: the RMS change rises by 17–27%.
- The price is slightly less anti-persistent at short and medium lags.
- No fat tails: the kurtosis stays at 2.8, as for the paper's agents.
- Shock tests with the same types (200 runs, `results/shock/shock_takers4.png`, `shock_both4.png`): the price
  does not recover, and the bid side refills with the same half-life (28–30 steps) as before. With
  4-unit takers the spread before the shock was narrower (17.5 ticks against 23.2); this has not
  been explained.

**The same agent types in the Fig. 4 setup** (mean-reverting walk and Eq. 4, no value traders; same
scale; `results/agent_types/types_fig4_*.pkl`, `results/meeting/8_agent_types_fig4_setup.png`):

| Agents | H(100) | H(10^3) | RMS (200 steps) | Kurtosis at Δτ = 200 / 400 / 800 / 1600 | Size autocorr. |
|---|---|---|---|---|---|
| paper's | 0.38 | 0.68 | 261 | 13.4 / 16.0 / 16.6 / 16.5 | 0.36 |
| providers 4 every 4 | 0.34 | 0.65 | 276 | 9.1 / 8.9 / 7.4 / 6.2 | 0.36 |
| takers 4 every 4 | 0.36 | 0.64 | 282 | 8.6 / 8.4 / 7.4 / 6.2 | 0.35 |
| both | 0.30 | 0.60 | 283 | 8.3 / 7.9 / 6.2 / 4.6 | 0.36 |

The kurtosis looks lower with lumpier agents, but the comparison is not reliable at this scale: the
paper-scale run of the paper's agents (section 5) gave 6.9–9.4, the same range as the agent types
here. With 8 runs of 10^5 steps the kurtosis depends on a few very large moves. The other columns
change little. Volatility clustering, which comes from Eq. 4, is unchanged.

**Agent types of 1, 4 and 16 units together** (Fig. 2 setup, no value traders, agents split equally
between the three types; 10^5 steps, 8 runs, N_A = 500; `results/agent_types/types16_*.pkl`,
`results/meeting/9_agent_types_1_4_16.png`):

| Agents | H(10) | H(100) | H(10^3) | RMS (200 steps) | Kurtosis (200–1600) | Autocorr. of changes | Of their size |
|---|---|---|---|---|---|---|---|
| paper's | 0.08 | 0.20 | 0.38 | 19.2 | 2.8–3.0 | −0.38 | 0.08 |
| providers 1/4/16 | 0.09 | 0.25 | 0.43 | 24.2 | 2.8–3.0 | −0.34 | 0.05 |
| takers 1/4/16 | 0.12 | 0.25 | 0.46 | 24.6 | 2.8–2.9 | −0.32 | 0.05 |
| both | 0.12 | 0.27 | 0.45 | 27.1 | 2.9–3.0 | −0.33 | 0.05 |

The larger sizes show the same pattern as the 4-unit types, more strongly: the price moves 26–41%
more and turns back less at short lags. Still no fat tails, and slightly less volatility clustering.
Shock test with both mixed (200 runs, `results/shock/shock_types16_both.png`): the price does not recover
(−41 ticks at the shock for 300 units, against −38 with the paper's agents) and the bid side refills
with a half-life of 25–30 steps, as before.
