"""
Placement trial (docs/providers/decisions.md, D45): providers that place limit orders at a distance
from the best price on their own side, against the paper's providers, with two kinds of takers:

    providers   Bouchaud et al. (power law, mu 0.6, delta1 1, taper beyond 100 ticks), and Mike and
                Farmer (Student t, 1.3 dof, scale 5, 11, 20 ticks), each with crossing orders drawn
                again or allowed to trade; plus the Preis control (exponential distance from the
                mid-price) at lambda_0 = 7 and 100: 10 setups
    takers      the splitting setup of D42 (alpha 1.6, N 1, f 0.85, q(t) off), and the paper's random
                takers (q(t) on)

That is 10 x 2 = 20 jobs, numbered 0 to 19 (see `list`). Each is N_A = 500, 4 runs of 120,000 steps,
the first 20,000 left out, as in the earlier trials, on the per-trade mid-price (D43).

    python -m experiments.placement_sweep list
    python -m experiments.placement_sweep run --index 7 --workers 4
    python -m experiments.placement_sweep collect

`run` is meant for a cluster job array (cluster/placement_sweep.slurm). Results go to
results/placement_sweep/; running an index again skips it if it is done. `collect` writes
summary.csv, prints a table per kind of taker beside the E-mini, and draws H and the response
function against lag (hurst.png, response.png).
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

from abm.order_splitting import SplittingSettings
from abm.placement import PlacementSettings
from abm.simulation import run_simulation
from analysis.stylised import KURTOSIS_LAGS, LAGS, PRICE, SIGN_LAGS, stylised_facts
from experiments import run as runner
from experiments import volatility_sweep as first
from experiments.common import trade_segment
from experiments.provenance import describe, git_info

N_AGENTS = 500
PROVIDERS = [("preis", 7), ("preis", 100), ("bmp", "redraw"), ("bmp", "allow")] + \
            [("student", scale, crossing) for scale in (5, 11, 20) for crossing in ("redraw", "allow")]
TAKERS = ("split", "random")
GRID = list(itertools.product(TAKERS, PROVIDERS))
OUT_DIR = runner.RESULTS_DIR / "placement_sweep"
EMINI = first.EMINI
SPLITTING = SplittingSettings(share=0.85, n_hidden=1, alpha=1.6)
REPORT_LAGS = (1, 10, 100, 1000, 10000)


def provider_name(p) -> str:
    if p[0] == "preis":
        return f"preis_lam{p[1]}"
    if p[0] == "bmp":
        return f"bmp_{p[1]}"
    return f"student{p[1]}_{p[2]}"


def name_of(index: int) -> str:
    takers, p = GRID[index]
    return f"{takers}_{provider_name(p)}"


def provider_kwargs(p) -> dict:
    if p[0] == "preis":
        return {"lambda_": p[1]}
    if p[0] == "bmp":
        return {"placement": PlacementSettings(rule="bmp", crossing=p[1])}
    return {"placement": PlacementSettings(rule="student", crossing=p[2], scale=p[1])}


def run_one(task):
    """One run of one combination: its trade-time segment, and how the providers placed orders."""
    index, seed, n_steps, skip = task
    takers, p = GRID[index]
    taker_kwargs = {"splitting": SPLITTING} if takers == "split" else {"taker_flow": runner.make_flow("mean-reverting")}
    r = run_simulation(n_agents=N_AGENTS, n_steps=n_steps, seed=seed, keep_trades=False, record_sides=True,
                       record_trades=True, **taker_kwargs, **{**runner.PARAMS, **provider_kwargs(p)})
    return trade_segment(r, skip), {**{k: int(v) for k, v in r.placement_counts.items()},
                                    "trades_per_step": len(r.trade_prices) / n_steps,
                                    "mid_gaps": int(sum(m is None for m in r.mid_price_series)),
                                    "match_failures": int(r.n_match_failures)}


def run_index(index: int, workers: int, n_runs: int, n_steps: int, skip: int, out_dir: Path) -> None:
    out = out_dir / f"{name_of(index)}.pkl"
    if out.exists():
        print(f"{out.name} already done")
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"job {index}: {name_of(index)}", flush=True)
    start = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(run_one, [(index, seed, n_steps, skip) for seed in range(n_runs)]))
    facts = stylised_facts([seg for seg, _ in results])
    extra = {key: float(np.sum([e[key] for _, e in results])) for key in results[0][1] if key != "trades_per_step"}
    extra["trades_per_step"] = float(np.mean([e["trades_per_step"] for _, e in results]))
    takers, p = GRID[index]
    data = {"index": index, "name": name_of(index), "takers": takers, "provider": provider_name(p), "facts": facts,
            "extra": extra, "check": first.check(facts), "n_runs": n_runs, "n_steps": n_steps, "skip": skip,
            "git": git_info()}
    with open(out, "wb") as fh:
        pickle.dump(data, fh)
    c = data["check"]
    print(f"{facts['n_trades']:,} trades, {time.perf_counter() - start:.0f}s; spread {facts['spread']['mean']:.2f}; "
          f"mid moves on {facts['mid_moves']['share_of_trades']:.2%} of trades; "
          f"(a) {c['a_fat_tails_fading']}, (b) {c['b_random_walk']}, (c) {c['c_bounce_only']}")


def at(values, lags, lag) -> float:
    return float(values[list(lags).index(lag)])


def row_of(data: dict) -> dict:
    f = data["facts"]
    t, g, r, mm = f[PRICE], f["signs"], f["response"]["per_trade"], f["mid_moves"]
    row = {k: data[k] for k in ("index", "name", "takers", "provider")}
    row.update({f"kurtosis_{lag}": t["kurtosis"][lag] for lag in KURTOSIS_LAGS})
    row.update({"H_10": t["hurst"][first.nearest(10)], "H_1000": t["hurst"][first.nearest(1000)],
                "ac1": t["autocorr"][1]["signed"][0], "ac100_lag1": t["autocorr"][100]["signed"][0],
                "sign_1": at(g["autocorr"], SIGN_LAGS, 1), "sign_100": at(g["autocorr"], SIGN_LAGS, 100),
                "sign_gamma": g["gamma"]})
    row.update({f"R_{lag}": at(r, SIGN_LAGS, lag) for lag in REPORT_LAGS})
    row.update({"mid_moves": mm["share_of_trades"], "half_tick": mm["half_tick"], "reversed": mm["reversed"],
                "undone": mm["undone"], "spread": f["spread"]["mean"], "spread_1_tick": f["spread"]["shares"][1],
                "best_size_median": f["best_size"]["quantiles"][50]})
    ex = data["extra"]
    row.update({"trades_per_step": ex["trades_per_step"],
                "crossed_share": ex["crossed"] / ex["placed"] if ex.get("placed") else float("nan"),
                "mid_gaps": ex["mid_gaps"], "match_failures": ex["match_failures"]})
    row.update(first.check(f))
    return row


def collect(out_dir: Path, emini: Path) -> list:
    datas = []
    for index in range(len(GRID)):
        path = out_dir / f"{name_of(index)}.pkl"
        if path.exists():
            with open(path, "rb") as fh:
                datas.append(pickle.load(fh))
    print(f"{len(datas)} of {len(GRID)} jobs finished")
    if not datas:
        raise SystemExit(f"No finished jobs in {out_dir}.")
    rows = [row_of(d) for d in datas]
    with open(out_dir / "summary.csv", "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    e = None
    if emini.exists():
        with open(emini, "rb") as fh:
            e = pickle.load(fh)
    header = (f"  {'providers':20} | {'k(100)':>6} {'k(1e3)':>6} {'H(10)':>5} {'H(1e3)':>6} {'ac100':>6} | {'s(1)':>5} | "
              f"{'R(1)':>6} {'R(100)':>6} {'R(1e4)':>6} | {'moves':>6} {'half':>5} {'undone':>6} | {'spread':>6} {'1tick':>5} "
              f"{'queue':>5} {'cross':>5} {'tr/st':>5} | a b c")
    if e is not None and "mid_moves" in e:
        t, mm, r = e[PRICE], e["mid_moves"], e["response"]["per_order"]
        print(f"\nE-mini (response and signs per order):\n{header}")
        print(f"  {'E-mini':20} | {t['kurtosis'][100]:6.2f} {t['kurtosis'][1000]:6.2f} {t['hurst'][first.nearest(10)]:5.2f} "
              f"{t['hurst'][first.nearest(1000)]:6.2f} {t['autocorr'][100]['signed'][0]:+6.2f} | "
              f"{at(e['signs']['orders']['autocorr'], SIGN_LAGS, 1):5.2f} | {at(r, SIGN_LAGS, 1):6.3f} "
              f"{at(r, SIGN_LAGS, 100):6.3f} {at(r, SIGN_LAGS, 10000):6.3f} | {mm['share_of_trades']:6.2%} "
              f"{mm['half_tick']:5.0%} {mm['undone']:6.0%} | {e['spread']['mean']:6.2f} {e['spread']['shares'][1]:5.0%} "
              f"{e['best_size']['quantiles'][50]:5g}")
    for takers in TAKERS:
        mine = [r for r in rows if r["takers"] == takers]
        if not mine:
            continue
        print(f"\ntakers: {'splitting (D42)' if takers == 'split' else 'random (q on)'}\n{header}")
        for r in sorted(mine, key=lambda r: r["index"]):
            print(f"  {r['provider']:20} | {r['kurtosis_100']:6.2f} {r['kurtosis_1000']:6.2f} {r['H_10']:5.2f} {r['H_1000']:6.2f} "
                  f"{r['ac100_lag1']:+6.2f} | {r['sign_1']:5.2f} | {r['R_1']:6.3f} {r['R_100']:6.3f} {r['R_10000']:6.3f} | "
                  f"{r['mid_moves']:6.2%} {r['half_tick']:5.0%} {r['undone']:6.0%} | {r['spread']:6.2f} {r['spread_1_tick']:5.0%} "
                  f"{r['best_size_median']:5g} {r['crossed_share']:5.0%} {r['trades_per_step']:5.1f} | "
                  + " ".join("y" if r[key] else "-" for key in ("a_fat_tails_fading", "b_random_walk", "c_bounce_only")))
    passes = [r["name"] for r in rows if r["passes"]]
    print(f"\npass all three D38 tests: {', '.join(passes) if passes else 'none'}")

    # H and the response function (divided by its value at lag 100) against lag: one row per kind of
    # taker; Preis controls, Bouchaud et al., and Mike and Farmer in separate panels.
    by = {(d["takers"], d["provider"]): d for d in datas}
    families = [("Preis control", [("preis_lam7", "#2a78d6", "-"), ("preis_lam100", "#2a78d6", "--")]),
                ("Bouchaud et al.", [("bmp_redraw", "#eb6834", "-"), ("bmp_allow", "#eb6834", "--")]),
                ("Mike and Farmer", [(f"student{s}_{c}", col, "-" if c == "redraw" else "--")
                                     for s, col in ((5, "#1baf7a"), (11, "#eda100"), (20, "#e87ba4"))
                                     for c in ("redraw", "allow")])]
    for what, filename in (("hurst", "hurst.png"), ("response", "response.png")):
        fig, axes = plt.subplots(len(TAKERS), len(families), figsize=(15, 9), squeeze=False)
        for (i, takers), (j, (title, members)) in itertools.product(enumerate(TAKERS), enumerate(families)):
            ax = axes[i, j]
            for provider, colour, ls in members:
                d = by.get((takers, provider))
                if d is None:
                    continue
                if what == "hurst":
                    ax.plot(LAGS, d["facts"][PRICE]["hurst"], ls, color=colour, lw=1.4, label=provider)
                else:
                    r = d["facts"]["response"]["per_trade"]
                    ax.plot(SIGN_LAGS, r / at(r, SIGN_LAGS, 100), ls, color=colour, lw=1.4, label=provider)
            if e is not None:
                if what == "hurst":
                    ax.plot(LAGS, e[PRICE]["hurst"], "k", lw=2.2, label="E-mini")
                elif "response" in e:
                    r = e["response"]["per_order"]
                    ax.plot(SIGN_LAGS, r / at(r, SIGN_LAGS, 100), "k", lw=2.2, label="E-mini (per order)")
            ax.set_xscale("log")
            ax.axhline(0.5 if what == "hurst" else 1.0, color="gray", lw=0.6, ls=":")
            ax.set(xlabel="lag [trades]", ylabel="H (mid-price)" if what == "hurst" else "R(ℓ) / R(100)")
            ax.set_title(f"{title}, takers: {'splitting' if takers == 'split' else 'random'}", fontsize=9)
            if ax.get_legend_handles_labels()[0]:
                ax.legend(fontsize=7, frameon=False)
        label = "Hurst exponent" if what == "hurst" else "response function (solid: crossing drawn again; dashed: allowed)"
        fig.suptitle(f"Placement trial: {label} (N$_A$ = {N_AGENTS}, trade time)", fontsize=11)
        fig.text(0.995, 0.005, "code version: " + describe(datas[0]["git"]), ha="right", va="bottom", fontsize=7, color="gray")
        fig.tight_layout()
        fig.savefig(out_dir / filename, dpi=115)
        plt.close(fig)
    print(f"saved {out_dir / 'summary.csv'}, {out_dir / 'hurst.png'} and {out_dir / 'response.png'}")
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="show the jobs and their numbers")
    run_cmd = commands.add_parser("run", help="run one job")
    run_cmd.add_argument("--index", type=int, required=True, help=f"0 to {len(GRID) - 1}")
    run_cmd.add_argument("--workers", type=int, required=True, help="processes to use: the CPUs the job was given")
    run_cmd.add_argument("--n-runs", type=int, default=4, help="runs per job (default 4)")
    run_cmd.add_argument("--n-steps", type=int, default=120_000, help="steps per run (default 120,000)")
    run_cmd.add_argument("--skip", type=int, default=20_000, help="steps left out at the start of each run (default 20,000)")
    collect_cmd = commands.add_parser("collect", help="summary tables and figures")
    collect_cmd.add_argument("--emini", type=Path, default=EMINI, help="E-mini statistics to compare with, if present")
    for sub in (run_cmd, collect_cmd):
        sub.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    if args.command == "list":
        for index in range(len(GRID)):
            print(f"{index:3d}  {name_of(index)}")
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
