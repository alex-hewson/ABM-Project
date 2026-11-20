"""
Model against E-mini: the statistics of analysis/stylised.py in trade time, for a few versions of the
model, set beside the same statistics from the E-mini data (docs/decisions.md, D37). Prices are
compared on the mid-price; the trade price is shown only for the bid-ask bounce.

    python -m experiments.emini_compare model --workers 8          # runs the model markets below
    python -m experiments.emini_compare compare                    # table and figure, model against data

The data statistics come from `python -m experiments.emini stats PATH` (results/emini/emini_stats.pkl).

Model markets (N_A = 500, each run one segment; per trade, the mid-price, spread and sizes at the best
prices are those at the end of the step before the trade's step, so trades in step 0 are left out):

    baseline    the paper's agents (Fig. 2)
    fig4        mean-reverting order flow with volatility-coupled entry depth, C = 10 (Fig. 4)
    v20_m10     20% value traders and 10% momentum traders (order 1, window 50): reverting side of
                the phase diagram boundary (D36)
    v20_m30     20% value traders and 30% momentum traders: trending side
"""

from __future__ import annotations

import argparse
import pickle
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from abm.simulation import run_simulation
from analysis.stylised import AUTOCORR, KURTOSIS_LAGS, LAGS, PRICE, TAIL_LEVELS, stylised_facts, summary_rows
from experiments import run as runner
from experiments.common import trade_segment
from experiments.provenance import describe, git_info

N_AGENTS = 500
MARKETS = {
    "baseline": dict(label="model: paper's agents (Fig. 2)"),
    "fig4": dict(label="model: Fig. 4 (volatility-coupled depth)", flow="mean-reverting", depth_coupling=10.0),
    "v20_m10": dict(label="model: 20% value, 10% momentum", value=0.2, momentum=0.1),
    "v20_m30": dict(label="model: 20% value, 30% momentum", value=0.2, momentum=0.3),
}
OUT_DIR = Path("results/emini")
DATA_FILE = OUT_DIR / "emini_stats.pkl"


def run_one(task):
    """One model run, as one segment of per-trade arrays."""
    name, seed, n_steps = task
    market = MARKETS[name]
    flow = runner.make_flow(market.get("flow", "symmetric"))
    coupling = market.get("depth_coupling", 0.0)
    r = run_simulation(n_agents=N_AGENTS, n_steps=n_steps, seed=seed, keep_trades=False,
                       record_sides=True, record_trades=True, taker_flow=flow, depth_coupling=coupling,
                       q_rms=flow.stationary_rms if coupling > 0 else None,
                       n_value_traders=round(market.get("value", 0.0) * N_AGENTS),
                       n_momentum_traders=round(market.get("momentum", 0.0) * N_AGENTS), momentum_orders=(1,),
                       **runner.PARAMS)
    return trade_segment(r)


def model(names, n_runs: int, n_steps: int, workers, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        start = time.perf_counter()
        with ProcessPoolExecutor(max_workers=workers) as pool:
            segments = list(pool.map(run_one, [(name, seed, n_steps) for seed in range(n_runs)]))
        facts = stylised_facts(segments)
        facts["source"] = {"market": name, "label": MARKETS[name]["label"], "n_agents": N_AGENTS,
                           "n_runs": n_runs, "n_steps": n_steps, "git": git_info()}
        with open(out_dir / f"model_{name}.pkl", "wb") as f:
            pickle.dump(facts, f)
        print(f"{name}: {n_runs} runs of {n_steps:,} steps, {facts['n_trades']:,} trades "
              f"({time.perf_counter() - start:.0f}s)", flush=True)


def load_all(out_dir: Path, names):
    sets = []
    if (out_dir / DATA_FILE.name).exists():
        with open(out_dir / DATA_FILE.name, "rb") as f:
            data = pickle.load(f)
        data["source"]["label"] = "E-mini, " + " and ".join(d[-5:] for d in data["source"]["days"])
        sets.append(data)
    else:
        print(f"no data statistics in {out_dir / DATA_FILE.name}: run `python -m experiments.emini stats PATH` first")
    for name in names:
        path = out_dir / f"model_{name}.pkl"
        if path.exists():
            with open(path, "rb") as f:
                sets.append(pickle.load(f))
    return sets


def compare(out_dir: Path, names) -> None:
    sets = load_all(out_dir, names)
    if not sets:
        raise SystemExit("Nothing to compare yet.")
    labels = [s["source"]["label"] for s in sets]
    rows = [summary_rows(s) for s in sets]
    width = max(len(label) for label, _ in rows[0])
    print("\n" + " " * width + " | " + " | ".join(f"{label[:22]:>22}" for label in labels))
    for i, (label, _) in enumerate(rows[0]):
        print(f"{label:{width}} | " + " | ".join(f"{r[i][1]:>22}" if i < len(r) else f"{'-':>22}" for r in rows))

    colours = ["k"] + [f"C{i}" for i in range(len(sets) - 1)]
    fig, axes = plt.subplots(2, 3, figsize=(17, 9.5))
    (a, b, c), (d, e, f) = axes
    for s, label, colour in zip(sets, labels, colours):
        lw = 2 if colour == "k" else 1.1
        t = s[PRICE]                      # the mid-price (D37); the trade price only for the bounce in (d)
        a.plot(LAGS, t["rms"], color=colour, lw=lw, label=label)
        b.plot(LAGS, t["hurst"], color=colour, lw=lw, label=label)
        c.plot(TAIL_LEVELS, t["tail"][100], color=colour, lw=lw, label=label)
        n1 = AUTOCORR[1]
        d.plot(range(1, n1 + 1), t["autocorr"][1]["signed"], "o-", ms=3, color=colour, lw=lw, label=label)
        d.plot(range(1, n1 + 1), s["trade"]["autocorr"][1]["signed"], ":", color=colour, lw=lw)
        n100 = AUTOCORR[100]
        e.plot(range(1, n100 + 1), t["autocorr"][100]["absolute"], color=colour, lw=lw, label=label)
        f.plot(KURTOSIS_LAGS, [t["kurtosis"][lag] for lag in KURTOSIS_LAGS], "o-", color=colour, lw=lw, label=label)
    gauss = np.array([np.mean(np.abs(np.random.default_rng(0).standard_normal(200_000)) >= x) for x in TAIL_LEVELS])
    c.plot(TAIL_LEVELS, gauss, "k:", lw=1, label="normal distribution")
    a.set(xscale="log", yscale="log", xlabel="lag [trades]", ylabel="RMS change of the mid-price [ticks]",
          title="(a) size of price changes against lag")
    b.axhline(0.5, color="gray", lw=0.6, ls=":")
    b.set(xscale="log", xlabel="lag [trades]", ylabel="H", title="(b) Hurst exponent (local slope of (a))")
    c.set(xscale="log", yscale="log", xlabel="|change| / standard deviation", ylabel="share at least this large",
          title="(c) tails of 100-trade mid changes", ylim=(1e-6, 1.5))
    d.axhline(0, color="gray", lw=0.6, ls=":")
    d.set(xlabel="lag [trades]", ylabel="autocorrelation", title="(d) trade-to-trade changes: mid-price (solid), trade price (dotted, bid-ask bounce)")
    e.axhline(0, color="gray", lw=0.6, ls=":")
    e.set(xlabel="lag [blocks of 100 trades]", ylabel="autocorrelation",
          title="(e) size of 100-trade mid changes (volatility clustering)")
    f.axhline(3, color="gray", lw=0.6, ls=":")
    f.set(xscale="log", xlabel="lag [trades]", ylabel="kurtosis", title="(f) kurtosis of mid changes (normal = 3)")
    for ax in axes.flat:
        ax.title.set_fontsize(10)
    a.legend(fontsize=8)
    model_git = next((s["source"]["git"] for s in sets if "git" in s["source"]), None)
    fig.suptitle("Model against E-mini S&P 500 futures, in trade time (regular hours; model N$_A$ = 500)", fontsize=11)
    if model_git:
        fig.text(0.995, 0.005, "model code version: " + describe(model_git), ha="right", va="bottom", fontsize=7, color="gray")
    fig.tight_layout()
    out = out_dir / "compare.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print(f"\nsaved {out}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    model_cmd = commands.add_parser("model", help="run the model markets and save their statistics")
    model_cmd.add_argument("--markets", nargs="+", choices=list(MARKETS), default=list(MARKETS))
    model_cmd.add_argument("--n-runs", type=int, default=4, help="runs per market (default 4)")
    model_cmd.add_argument("--n-steps", type=int, default=100_000, help="steps per run (default 100,000)")
    model_cmd.add_argument("--workers", type=int, default=None, help="processes to use (default: all cores)")
    compare_cmd = commands.add_parser("compare", help="table and figure, model against data")
    compare_cmd.add_argument("--markets", nargs="+", choices=list(MARKETS), default=list(MARKETS))
    for sub in (model_cmd, compare_cmd):
        sub.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    if args.command == "model":
        model(args.markets, args.n_runs, args.n_steps, args.workers, args.out_dir)
    else:
        compare(args.out_dir, args.markets)


if __name__ == "__main__":
    main()
