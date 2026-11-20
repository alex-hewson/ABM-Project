"""
Volatility provider trial (docs/volatility_provider/decisions.md, D38, D39): every combination of the
volatility provider's settings, run from the Fig. 4 setup with Eq. 4 replaced, and judged by the
pass/fail check of D38 in trade time, on the mid-price (analysis/stylised.py, D37).

Every combination of:

    measure              std (standard deviation, Leal), abs (mean absolute change, Kaervik)
    k                    5, 10, 20 steps (length of one change)
    W                    50, 100, 200 steps (memory of the recent volatility)
    memory shape         fixed window, fading
    long-run memory      1,000, 5,000, 20,000 steps
    form                 widen, linear (C = 1)

That is 216 combinations, plus two controls: Fig. 4 itself (Eq. 4) and the same takers with a fixed
depth (Fig. 3c); 218 in all, numbered 0 to 217 (see `list`). The takers follow the mean-reverting walk
of Fig. 3c/4 in every one. Each is N_A = 500, 4 runs of 120,000 steps; the first 20,000 steps of each
run are left out of the statistics, while the long-run averages settle (D39).

    python -m experiments.volatility_sweep list
    python -m experiments.volatility_sweep run --index 7 --workers 4
    python -m experiments.volatility_sweep collect

`run` is meant for a cluster job array (cluster/volatility_sweep.slurm). Results go to
results/volatility_sweep/. Running an index again skips it if it is done. `collect` can be run at any
time; it writes summary.csv, prints which combinations pass, and draws the passing ones against the
controls (and the E-mini, if results/emini/emini_stats.pkl is there). The pass/fail check is redone
from the saved statistics every time, so its thresholds (below) can be changed after the runs.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import pickle
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from abm.simulation import run_simulation
from abm.volatility_provider import VolatilitySettings
from analysis.stylised import KURTOSIS_LAGS, LAGS, PRICE, stylised_facts
from experiments import run as runner
from experiments.emini_compare import trade_segment
from experiments.provenance import describe, git_info

N_AGENTS = 500
MEASURES = ("std", "abs")
KS = (5, 10, 20)
WINDOWS = (50, 100, 200)
MEMORIES = ("fixed", "fading")
LONG_MEMORIES = (1000, 5000, 20000)
FORMS = ("widen", "linear")
CONTROLS = ("fig4", "fixed_depth")
GRID = list(CONTROLS) + [VolatilitySettings(measure=m, k=k, window=w, memory=s, long_memory=lm, form=f, coupling=1.0)
                         for m, k, w, s, lm, f in itertools.product(MEASURES, KS, WINDOWS, MEMORIES, LONG_MEMORIES, FORMS)]
OUT_DIR = runner.RESULTS_DIR / "volatility_sweep"
EMINI = runner.RESULTS_DIR / "emini" / "emini_stats.pkl"

# The D38 pass/fail check, judged by shape. The numbers below turn "by shape" into a test that can be
# applied the same way to every combination; they are rough on purpose (D38).
FAT_TAILS_SHORT = 3.5          # (a) kurtosis at 1 or 10 trades above this: clearly fatter than normal (3)
NEAR_NORMAL = (2.5, 4.0)       # (a) kurtosis at 100 or 1,000 trades inside this: close to normal
RANDOM_WALK_H = (0.4, 0.6)     # (b) H at about 1,000 trades inside this
NO_CORRELATION = 0.1           # (c) |autocorrelation of 100-trade changes| at lags 1-5 below this


def name_of(index: int) -> str:
    g = GRID[index]
    if isinstance(g, str):
        return f"control_{g}"
    return f"{g.measure}_k{g.k}_W{g.window}_{g.memory}_L{g.long_memory}_{g.form}"


def run_one(task):
    """One run of one combination: its trade-time segment, and how the depth behaved."""
    index, seed, n_steps, skip = task
    return simulate(GRID[index], seed, n_steps, skip)


def simulate(g, seed: int, n_steps: int, skip: int, lambda_0: float = runner.PARAMS["lambda_"]):
    """One run of a grid entry g (a control name or VolatilitySettings) with mean entry depth lambda_0:
    its trade-time segment, and how the depth behaved. Also used by the lambda_0 trial (D40)."""
    params = {**runner.PARAMS, "lambda_": lambda_0}
    flow = runner.make_flow("mean-reverting")
    if g == "fig4":
        extra = dict(depth_coupling=10.0, q_rms=flow.stationary_rms)
    elif g == "fixed_depth":
        extra = {}
    else:
        extra = dict(volatility=g)
    r = run_simulation(n_agents=N_AGENTS, n_steps=n_steps, seed=seed, keep_trades=False, record_sides=True,
                       record_trades=True, taker_flow=flow, **extra, **params)
    lam = r.lambda_series[skip:] if len(r.lambda_series) else np.full(n_steps - skip, float(lambda_0))
    return trade_segment(r, skip), {"lambda_mean": float(lam.mean()), "lambda_min": float(lam.min()),
                                    "lambda_max": float(lam.max()),
                                    "lambda_over_2x": float(np.mean(lam > 2 * lambda_0)),
                                    "mid_gaps": int(sum(m is None for m in r.mid_price_series))}


def nearest(lag: int) -> int:
    return int(np.argmin(np.abs(LAGS - lag)))


def check(facts: dict) -> dict:
    """The three D38 tests, each True or False, and whether all pass. They use the mid-price (D37)."""
    t = facts[PRICE]
    k = t["kurtosis"]
    short, long_ = max(k[1], k[10]), (k[100], k[1000])
    fat_fading = (short > FAT_TAILS_SHORT and k[100] < short and k[1000] < short
                  and any(NEAR_NORMAL[0] <= x <= NEAR_NORMAL[1] for x in long_))
    h10, h1000 = t["hurst"][nearest(10)], t["hurst"][nearest(1000)]
    random_walk = bool(RANDOM_WALK_H[0] <= h1000 <= RANDOM_WALK_H[1] and h1000 > h10)
    signed = t["autocorr"][100]["signed"][:5]
    bounce_only = bool(t["autocorr"][1]["signed"][0] < 0 and np.all(np.abs(signed) < NO_CORRELATION))
    return {"a_fat_tails_fading": bool(fat_fading), "b_random_walk": random_walk, "c_bounce_only": bounce_only,
            "passes": bool(fat_fading and random_walk and bounce_only)}


def run_index(index: int, workers: int, n_runs: int, n_steps: int, skip: int, out_dir: Path) -> None:
    out = out_dir / f"{name_of(index)}.pkl"
    if out.exists():
        print(f"{out.name} already done")
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    g = GRID[index]
    print(f"combination {index}: {name_of(index)}" + ("" if isinstance(g, str) else f" ({g.describe()})"), flush=True)
    start = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(run_one, [(index, seed, n_steps, skip) for seed in range(n_runs)]))
    facts = stylised_facts([seg for seg, _ in results])
    depth = {key: float(np.mean([d[key] for _, d in results])) for key in results[0][1]}
    depth["lambda_max"] = max(d["lambda_max"] for _, d in results)
    depth["lambda_min"] = min(d["lambda_min"] for _, d in results)
    data = {"index": index, "name": name_of(index), "settings": g, "facts": facts, "depth": depth,
            "check": check(facts), "n_runs": n_runs, "n_steps": n_steps, "skip": skip, "git": git_info()}
    with open(out, "wb") as f:
        pickle.dump(data, f)
    c = data["check"]
    print(f"{facts['n_trades']:,} trades, {time.perf_counter() - start:.0f}s; mean depth {depth['lambda_mean']:.0f} ticks; "
          f"(a) {c['a_fat_tails_fading']}, (b) {c['b_random_walk']}, (c) {c['c_bounce_only']} -> "
          f"{'PASS' if c['passes'] else 'fail'}")


def row_of(data: dict) -> dict:
    t, g = data["facts"][PRICE], data["settings"]
    row = {"index": data["index"], "name": data["name"]}
    if isinstance(g, str):
        row.update(measure="", k="", window="", memory="", long_memory="", form="")
    else:
        row.update(measure=g.measure, k=g.k, window=g.window, memory=g.memory, long_memory=g.long_memory, form=g.form)
    row.update({f"kurtosis_{lag}": t["kurtosis"][lag] for lag in KURTOSIS_LAGS})
    row.update({"H_10": t["hurst"][nearest(10)], "H_1000": t["hurst"][nearest(1000)],
                "ac1": t["autocorr"][1]["signed"][0], "ac100_lag1": t["autocorr"][100]["signed"][0],
                "trade_bounce": data["facts"]["trade"]["autocorr"][1]["signed"][0],
                "spread": data["facts"]["spread"]["mean"]})
    row.update(data["depth"])
    row.update(data["check"])
    return row


def collect(out_dir: Path, emini: Path) -> list:
    datas, missing = [], []
    for index in range(len(GRID)):
        path = out_dir / f"{name_of(index)}.pkl"
        if path.exists():
            with open(path, "rb") as f:
                datas.append(pickle.load(f))
        else:
            missing.append(name_of(index))
    print(f"{len(datas)} of {len(GRID)} combinations finished")
    if not datas:
        raise SystemExit(f"No finished combinations in {out_dir}.")
    for d in datas:
        d["check"] = check(d["facts"])      # redone from the saved statistics, so the thresholds can change
    rows = [row_of(d) for d in datas]
    with open(out_dir / "summary.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n{'combination':42} | {'k(1)':>5} {'k(10)':>5} {'k(100)':>6} {'k(1e3)':>6} | {'H(10)':>5} {'H(1e3)':>6} | "
          f"{'ac1':>6} {'ac100':>6} | {'depth':>5} {'max':>5} | a b c")
    shown = [r for r in rows if r["name"].startswith("control")] + [r for r in rows if r["passes"]]
    for r in shown:
        print(f"{r['name']:42} | {r['kurtosis_1']:5.1f} {r['kurtosis_10']:5.1f} {r['kurtosis_100']:6.1f} "
              f"{r['kurtosis_1000']:6.1f} | {r['H_10']:5.2f} {r['H_1000']:6.2f} | {r['ac1']:+6.2f} {r['ac100_lag1']:+6.2f} | "
              f"{r['lambda_mean']:5.0f} {r['lambda_max']:5.0f} | "
              + " ".join("y" if r[key] else "-" for key in ("a_fat_tails_fading", "b_random_walk", "c_bounce_only")))
    passes = sum(r["passes"] for r in rows)
    print(f"\n{passes} of {len(rows) - sum(r['name'].startswith('control') for r in rows)} combinations pass all three "
          f"(controls shown above for reference).")
    for key, label in (("a_fat_tails_fading", "(a) fat tails fading"), ("b_random_walk", "(b) random walk"),
                       ("c_bounce_only", "(c) bounce only")):
        print(f"  {label}: {sum(r[key] for r in rows if not r['name'].startswith('control'))} pass")

    # Kurtosis and H against lag: the controls, the E-mini if available, and up to 8 passing combinations.
    fig, (a, b) = plt.subplots(1, 2, figsize=(13, 5))
    curves = []
    if emini.exists():
        with open(emini, "rb") as f:
            curves.append(("E-mini (5 and 7 May 2010)", pickle.load(f), "k", 2.0))
    by_name = {d["name"]: d for d in datas}
    for name, colour in (("control_fig4", "C3"), ("control_fixed_depth", "C7")):
        if name in by_name:
            curves.append((name.replace("control_", "control: "), by_name[name]["facts"], colour, 1.5))
    for i, d in enumerate([d for d in datas if d["check"]["passes"]][:8]):
        curves.append((d["name"], d["facts"], f"C{i % 3}", 0.8))
    for label, facts, colour, lw in curves:
        t = facts[PRICE]
        a.plot(KURTOSIS_LAGS, [t["kurtosis"][lag] for lag in KURTOSIS_LAGS], "o-", color=colour, lw=lw, ms=3, label=label)
        b.plot(LAGS, t["hurst"], color=colour, lw=lw, label=label)
    a.axhline(3, color="gray", lw=0.6, ls=":")
    a.set(xscale="log", xlabel="lag [trades]", ylabel="kurtosis of mid-price changes", title="(a) fat tails fading with lag")
    b.axhline(0.5, color="gray", lw=0.6, ls=":")
    b.set(xscale="log", xlabel="lag [trades]", ylabel="H (mid-price)", title="(b) Hurst exponent")
    a.legend(fontsize=6)
    fig.suptitle(f"Volatility provider trial (N$_A$ = {N_AGENTS}, trade time, mid-price): {passes} combinations pass D38", fontsize=11)
    fig.text(0.995, 0.005, "code version: " + describe(datas[0]["git"]), ha="right", va="bottom", fontsize=7, color="gray")
    fig.tight_layout()
    fig.savefig(out_dir / "summary.png", dpi=120)
    plt.close(fig)
    print(f"saved {out_dir / 'summary.csv'} and {out_dir / 'summary.png'}")
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="show the combinations and their numbers")
    run_cmd = commands.add_parser("run", help="run one combination")
    run_cmd.add_argument("--index", type=int, required=True, help=f"0 to {len(GRID) - 1}")
    run_cmd.add_argument("--workers", type=int, required=True, help="processes to use: the CPUs the job was given")
    run_cmd.add_argument("--n-runs", type=int, default=4, help="runs per combination (default 4)")
    run_cmd.add_argument("--n-steps", type=int, default=120_000, help="steps per run (default 120,000)")
    run_cmd.add_argument("--skip", type=int, default=20_000, help="steps left out at the start of each run (default 20,000)")
    collect_cmd = commands.add_parser("collect", help="summary table, pass/fail and figure")
    collect_cmd.add_argument("--emini", type=Path, default=EMINI, help="E-mini statistics to draw alongside, if present")
    for sub in (run_cmd, collect_cmd):
        sub.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    if args.command == "list":
        for index in range(len(GRID)):
            g = GRID[index]
            print(f"{index:3d}  {name_of(index):42}  " + (g if isinstance(g, str) else g.describe()))
    elif args.command == "run":
        if not 0 <= args.index < len(GRID):
            parser.error(f"--index must be 0 to {len(GRID) - 1}")
        if args.skip >= args.n_steps:
            parser.error("--skip must be smaller than --n-steps")
        run_index(args.index, args.workers, args.n_runs, args.n_steps, args.skip, args.out_dir)
    else:
        collect(args.out_dir, args.emini)


if __name__ == "__main__":
    main()
