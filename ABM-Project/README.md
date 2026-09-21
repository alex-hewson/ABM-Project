# HFT / Order-Book Agent-Based Model

An agent-based model of a limit order book, built on Preis, Golke, Paul & Schneider (2006),
"Multi-agent-based Order Book Model of financial markets", *EPL* 75, 510. The plan is to
reproduce that paper as a validated baseline, then extend it with high-frequency trading
agents to study market instability (e.g. the May 2010 Flash Crash).

Current status and next steps are in [docs/project_plan.md](docs/project_plan.md).

## Layout

| Folder | Contents |
|---|---|
| `abm/` | The model: `orderbook.py` (matching engine), `agents.py` (liquidity providers / takers), `simulation.py` (step loop) |
| `analysis/` | Measurements on simulation output: `hurst.py` (Hurst exponent), `average_hurst.py` (averaging over runs), `returns.py` (return distributions), `prices.py` (price series under different definitions of "price") |
| `experiments/` | Scripts that reproduce the paper's figures: `fig2.py` (run + save data), `plot_fig2.py` (draw from saved data), `provenance.py` (records the git commit in saved results) |
| `tests/` | Tests for all of the above |
| `docs/` | `project_plan.md` (status and next steps), `decisions.md` (assumptions and choices to note in the thesis) |
| `results/` | Generated data and plots (not tracked by git) |

## Running things

Run every command from the project root, using `python -m` so the imports resolve.

Tests (each file is self-contained and prints PASS/FAIL per check):

```
python -m tests.test_orderbook
python -m tests.test_agents
python -m tests.test_simulation
python -m tests.test_hurst
python -m tests.test_returns
python -m tests.test_prices
python -m tests.test_provenance
python -m tests.test_checkpoint
```

A single simulation with the paper's Fig. 2 parameters (short run):

```
python -m abm.simulation
```

Fig. 2 reproduction. Runs are independent and spread over CPU cores; the paper-scale
default (10^6 steps, 50 runs per N_A) takes many hours, so try a small one first:

```
python -m experiments.fig2 --n-steps 100000 --n-runs 4 --out results/fig2_quick.pkl
python -m experiments.plot_fig2 --data results/fig2_quick.pkl --out results/fig2_quick.png
```

The paper doesn't say which "price" it uses, so each run stores results for five definitions (`mid`,
`last`, `first`, `median`, `mean`). `--price median` picks one for panels (c) and (d); a second
figure, `fig2_quick_price_definitions.png`, compares all five (see `docs/decisions.md`, D11).

Each run is saved as soon as it finishes (in `<name>.pkl.parts/`), so an interruption
(sleep, crash, power cut) loses at most the runs in progress. To continue, repeat the same
command with `--resume`; already-saved runs are skipped. `--resume` also extends a finished
experiment: run 10 seeds now, then rerun with `--n-runs 50 --resume` to add the other 40. It
refuses if the settings or code version differ from the saved runs (`--allow-code-change`
overrides the code check when you know the change doesn't affect the simulation).

## Requirements

Python 3.12+ (the fast simulation method uses `random.binomialvariate`) with `numpy` and `matplotlib`.
