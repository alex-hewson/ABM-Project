"""
Event study of the Poisson trader (docs/decisions.md, D34, D35): long runs in which it places large
market orders at random times, then the price around every order is lined up and averaged, in bands
of order size. It is the shock test (experiments/shock.py) with many shocks of random size inside
normal runs instead of one placed by hand, and it also gives the impact of an order against its size.

The agent options are the shock test's:

    python -m experiments.pressure run --out results/pressure/plain.pkl
    python -m experiments.pressure run --value-traders 50 --out results/pressure/value50.pkl
    python -m experiments.pressure run --value-traders 50 --momentum-traders 100 --out results/pressure/value50_mom100.pkl
    python -m experiments.pressure plot --data results/pressure/plain.pkl results/pressure/value50.pkl \\
        --labels "paper's agents" "value 50" --out results/pressure/compare.png

Step 0 of a window is the step at the end of which the order was placed, so its price already shows
the full impact (as in the shock test). Only orders with no other order from 200 steps ahead to
--after steps past are used, and none in the first --warmup steps. Every order is flipped to look
like a sell, so a fall is negative, and the windows are averaged in ticks within each size band
(impact is not proportional to size, so they are not divided by it). The price is measured
relative to the true value when there are value traders, as in the shock test ("price*"), and is
the plain mid-price change otherwise. An order that empties the other side of the book leaves no
mid-price at step 0; the next step's is used for it.

To get more orders per run, the defaults are a chance of 1 in 5,000 per step and 0.06 units per step
waited, instead of the model's 1 in 10,000 and 0.03. The sizes have the same distribution (mean 300
units); the orders just come twice as often.
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
from analysis.events import clean_events, signed_window
from analysis.recovery import mean_response, recovered_fraction, time_to_recover
from experiments.provenance import git_info, describe
from experiments.run import PARAMS
from experiments.shock import N_AGENTS, parse_mix, describe_mix

BEFORE = 200          # steps shown (and averaged for the "before" level) ahead of each order
TAIL = 200            # the "end" level is the mean of this many final steps
LOWEST_WITHIN = 500   # the lowest point is looked for in this many steps after the order
BANDS = (0, 150, 400, np.inf)     # order size bands, in units
FIT_SIZES = (30, 500)             # sizes the impact power is fitted over: below 30 the impact is lost in the
                                  # noise; above 500 orders start to empty a side of the book (N_A = 250)


def band_name(low, high) -> str:
    return f"{low:g}-{high:g}" if np.isfinite(high) else f"{low:g}+"


def run_one(task):
    """One long run: the window around every clean order in it, with the order's size."""
    (seed, n_steps, warmup, after, provider_mix, taker_mix, value, momentum, poisson) = task
    n_value_traders, true_value_step, value_spread = value
    n_momentum_traders, momentum_orders, momentum_window, momentum_scale = momentum
    poisson_chance, poisson_rate = poisson
    r = run_simulation(n_agents=N_AGENTS, n_steps=n_steps, seed=seed, keep_trades=False,
                       provider_mix=provider_mix, taker_mix=taker_mix,
                       n_value_traders=n_value_traders, true_value_step=true_value_step, value_spread=value_spread,
                       poisson_chance=poisson_chance, poisson_rate=poisson_rate,
                       n_momentum_traders=n_momentum_traders, momentum_orders=momentum_orders,
                       momentum_window=momentum_window, momentum_scale=momentum_scale,
                       **PARAMS)
    mid = np.array([np.nan if m is None else m for m in r.mid_price_series], dtype=float)
    measured = mid - r.true_value_series if n_value_traders else mid
    keep = clean_events(r.poisson_steps, n_steps, BEFORE, after, start=warmup)
    windows = []
    for step, size in zip(r.poisson_steps[keep], r.poisson_sizes[keep]):
        w = signed_window(measured, step, -size, BEFORE, after)     # every order shown as a sell
        if np.isnan(w[BEFORE]):
            # The order emptied the other side, so there is no mid-price at step 0: use the next step's,
            # once the providers have refilled it, so the order still counts at step 0.
            w[BEFORE] = w[BEFORE + 1]
        windows.append(w)
    return {"windows": windows, "sizes": np.abs(r.poisson_sizes[keep]),
            "unfilled": r.poisson_unfilled[keep], "n_orders": len(r.poisson_steps)}


def band_summary(curve: np.ndarray) -> dict:
    """The shock test's numbers, read off one band's averaged curve (in ticks, a fall is negative)."""
    after = curve[BEFORE:]
    return {
        "impact": float(curve[BEFORE]),
        "lowest": float(np.nanmin(after[:LOWEST_WITHIN])),
        "half-life": time_to_recover(curve, BEFORE),
        "recovered": recovered_fraction(curve, BEFORE, TAIL),
        "end": float(np.nanmean(curve[-TAIL:])),
    }


def impact_power(sizes: np.ndarray, impacts: np.ndarray):
    """Mean impact in log-spaced size bins, and the power of a fit impact = A x size^power through the
    bins between FIT_SIZES. Returns (bin centres, mean impact per bin, which bins were fitted, power),
    impact as a positive number of ticks."""
    ok = np.isfinite(impacts)
    sizes, falls = sizes[ok], -impacts[ok]
    edges = np.logspace(np.log10(max(sizes.min(), 1)), np.log10(sizes.max() + 1), 11)
    centres, means = [], []
    for low, high in zip(edges[:-1], edges[1:]):
        inside = (sizes >= low) & (sizes < high)
        if inside.sum() >= 5 and falls[inside].mean() > 0:
            centres.append(float(np.sqrt(low * high)))
            means.append(float(falls[inside].mean()))
    centres, means = np.array(centres), np.array(means)
    fitted = (centres >= FIT_SIZES[0]) & (centres <= FIT_SIZES[1])
    power = float(np.polyfit(np.log(centres[fitted]), np.log(means[fitted]), 1)[0]) if fitted.sum() >= 3 else float("nan")
    return centres, means, fitted, power


def print_summaries(labels, datas):
    def fmt(x):
        if x is None:
            return "never"
        return f"{x:.2f}" if isinstance(x, float) else str(x)
    keys = ("impact", "lowest", "half-life", "recovered", "end")
    width = max(len(label) for label in labels)
    print(f"\n{'':<{width}} | {'band':>8} {'orders':>7} {'mean size':>9} {'emptied':>7} | "
          + " ".join(f"{k:>9}" for k in keys))
    for label, data in zip(labels, datas):
        for name, band in data["bands"].items():
            s = band_summary(band["mean"])
            print(f"{label:<{width}} | {name:>8} {band['n']:>7} {band['mean_size']:>9.0f} {band['emptied']:>7} | "
                  + " ".join(f"{fmt(s[k]):>9}" for k in keys))
        _, _, _, power = impact_power(data["sizes"], data["impacts"])
        print(f"{label:<{width}} | impact grows like size^{power:.2f} between {FIT_SIZES[0]} and {FIT_SIZES[1]} units "
              f"({data['n_used']} of {data['n_orders']} orders used)")
    print("\nIn ticks, every order shown as a sell (relative to the true value when there are value traders). "
          "'emptied' = orders that\nemptied the other side of the book; 'lowest' = within 500 steps; 'half-life' = "
          "steps until half of the impact is undone;\n'recovered' = share of the impact undone by the end "
          "(1 = all, 0 = none).")


def plot(labels, datas, out):
    fig, axes = plt.subplots(len(datas), 2, figsize=(13, 4.2 * len(datas)), squeeze=False)
    for (ax_curve, ax_size), label, data in zip(axes, labels, datas):
        t = data["t"]
        for colour, (name, band) in enumerate(data["bands"].items()):
            mean, err = band["mean"], band["error"]
            ax_curve.plot(t, mean, color=f"C{colour}", lw=0.9,
                          label=f"{name} units ({band['n']} orders, mean {band['mean_size']:.0f})")
            ax_curve.fill_between(t, mean - err, mean + err, color=f"C{colour}", alpha=0.2, lw=0)
        ax_curve.axhline(0, color="gray", lw=0.5, ls=":")
        ax_curve.axvline(0, color="gray", lw=0.5, ls=":")
        what = "price minus true value" if data["config"]["n_value_traders"] else "mid-price"
        ax_curve.set(title=f"{label}: {what} after an order (shown as a sell)",
                     xlabel="steps since the order", ylabel="change [ticks]")
        ax_curve.title.set_fontsize(9)
        ax_curve.legend(fontsize=8)

        ok = np.isfinite(data["impacts"])
        ax_size.scatter(data["sizes"][ok], -data["impacts"][ok], s=6, alpha=0.3, color="gray", label="each order")
        centres, means, fitted, power = impact_power(data["sizes"], data["impacts"])
        ax_size.plot(centres, means, "o-", color="C3", mfc="white", label="mean per size bin")
        ax_size.plot(centres[fitted], means[fitted], "o", color="C3",
                     label=f"fitted ({FIT_SIZES[0]}-{FIT_SIZES[1]} units): size$^{{{power:.2f}}}$")
        if fitted.sum() >= 3:
            ref = means[fitted][0] * np.sqrt(centres / centres[fitted][0])
            ax_size.plot(centres, ref, color="gray", lw=0.8, ls="--", label="size$^{0.5}$, for comparison")
        ax_size.set(xscale="log", yscale="log", title=f"{label}: impact against order size",
                    xlabel="order size [units]", ylabel="fall in the step of the order [ticks]")
        ax_size.title.set_fontsize(9)
        ax_size.legend(fontsize=8)
    first = datas[0]["config"]
    fig.suptitle(f"Poisson trader event study: N$_A$={N_AGENTS}, chance {first['poisson_chance']:g} per step, "
                 f"{first['poisson_rate']:g} units per step waited; shaded = ± 1 standard error", fontsize=11)
    fig.text(0.995, 0.005, "code version: " + describe(first["git"]), ha="right", va="bottom", fontsize=7, color="gray")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=110)
    plt.close(fig)
    print(f"saved {out}")


def run(args, parser):
    try:
        provider_mix, taker_mix = parse_mix(args.provider_mix), parse_mix(args.taker_mix)
    except ValueError as error:
        parser.error(str(error))
    if not (0 <= args.value_traders <= N_AGENTS) or not (0 <= args.momentum_traders <= N_AGENTS - args.value_traders):
        parser.error(f"--value-traders and --momentum-traders must be 0 or more and add up to at most {N_AGENTS}")
    n_takers = N_AGENTS - args.value_traders - args.momentum_traders
    for name, mix, total in (("--provider-mix", provider_mix, N_AGENTS), ("--taker-mix", taker_mix, n_takers)):
        if mix is not None and sum(mix.values()) != total:
            parser.error(f"{name}: the counts must add up to {total}, got {sum(mix.values())}")
    if not (0 < args.poisson_chance <= 1) or args.poisson_rate <= 0:
        parser.error("--poisson-chance must be above 0 and at most 1, and --poisson-rate above 0")
    if args.warmup < BEFORE or args.after < max(TAIL, LOWEST_WITHIN) or args.n_steps <= args.warmup + args.after:
        parser.error(f"--warmup must be at least {BEFORE}, --after at least {max(TAIL, LOWEST_WITHIN)}, "
                     f"and --n-steps longer than both")

    value = (args.value_traders, args.true_value_step, args.value_spread)
    momentum = (args.momentum_traders, tuple(args.momentum_orders), args.momentum_window, args.momentum_scale)
    poisson = (args.poisson_chance, args.poisson_rate)
    tasks = [(seed, args.n_steps, args.warmup, args.after, provider_mix, taker_mix, value, momentum, poisson)
             for seed in range(args.n_runs)]
    config = dict(n_runs=args.n_runs, n_steps=args.n_steps, warmup=args.warmup, after=args.after,
                  n_agents=N_AGENTS, params=PARAMS, git=git_info(),
                  providers=describe_mix(provider_mix), takers=describe_mix(taker_mix, n_takers),
                  provider_mix=provider_mix, taker_mix=taker_mix,
                  n_value_traders=args.value_traders, true_value_step=args.true_value_step,
                  value_spread=args.value_spread,
                  poisson_chance=args.poisson_chance, poisson_rate=args.poisson_rate,
                  n_momentum_traders=args.momentum_traders, momentum_orders=list(args.momentum_orders),
                  momentum_window=args.momentum_window, momentum_scale=args.momentum_scale)
    print(f"{args.n_runs} runs of {args.n_steps:,} steps, code version {describe(config['git'])}\n"
          f"providers: {config['providers']}\ntakers:    {config['takers']}"
          + (f"\nplus:      {args.value_traders} value traders (true value step {args.true_value_step:g}, "
             f"spread {args.value_spread:g})" if args.value_traders else "")
          + (f"\nplus:      {args.momentum_traders} momentum traders (orders {list(args.momentum_orders)}, "
             f"window {args.momentum_window})" if args.momentum_traders else "")
          + f"\nPoisson trader: chance {args.poisson_chance:g} per step, {args.poisson_rate:g} units per step "
            f"waited (mean order {args.poisson_rate / args.poisson_chance:.0f} units)", flush=True)

    start = time.perf_counter()
    windows, sizes, unfilled, n_orders = [], [], [], 0
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        try:
            for count, r in enumerate(pool.map(run_one, tasks), 1):
                windows += r["windows"]
                sizes += list(r["sizes"])
                unfilled += list(r["unfilled"])
                n_orders += r["n_orders"]
                if count % 10 == 0 or count == len(tasks):
                    print(f"[{count}/{len(tasks)}] {time.perf_counter() - start:.0f}s elapsed, "
                          f"{len(sizes)} orders used so far", flush=True)
        except BaseException:
            pool.shutdown(wait=True, cancel_futures=True)    # don't finish the queued runs after an error
            raise
    if not sizes:
        raise SystemExit("No order could be used: raise --n-steps or --poisson-chance, or lower --after.")

    windows, sizes, unfilled = np.asarray(windows), np.asarray(sizes), np.asarray(unfilled)
    bands = {}
    for low, high in zip(BANDS[:-1], BANDS[1:]):
        inside = (sizes >= low) & (sizes < high)
        if inside.any():
            bands[band_name(low, high)] = {
                "mean": mean_response(windows[inside]),
                "error": np.nanstd(windows[inside], axis=0) / np.sqrt(inside.sum()),
                "n": int(inside.sum()), "mean_size": float(sizes[inside].mean()),
                "emptied": int((unfilled[inside] > 0).sum())}
    data = {"config": config, "t": np.arange(-BEFORE, args.after + 1), "bands": bands,
            # Each order's own impact: the change from the step before to step 0. The curves above are
            # measured from the mean of the 200 steps before, which in a trending market can be far from
            # the price just before the order and would swamp the impact of small orders.
            "sizes": sizes, "impacts": windows[:, BEFORE] - windows[:, BEFORE - 1],
            "n_used": len(sizes), "n_orders": n_orders}
    print_summaries([args.out.stem], [data])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "wb") as f:
        pickle.dump(data, f)
    print(f"saved {args.out}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    run_cmd = commands.add_parser("run", help="run the event study for one market")
    run_cmd.add_argument("--n-runs", type=int, default=64, help="runs (default 64)")
    run_cmd.add_argument("--n-steps", type=int, default=50_000, help="steps per run (default 50,000)")
    run_cmd.add_argument("--warmup", type=int, default=2000, help="no orders used before this step (default 2000)")
    run_cmd.add_argument("--after", type=int, default=2000, help="steps recorded after each order (default 2000)")
    run_cmd.add_argument("--poisson-chance", type=float, default=0.0002,
                         help="chance of an order each step (default 0.0002, once per 5,000 steps)")
    run_cmd.add_argument("--poisson-rate", type=float, default=0.06,
                         help="units per step since the last order (default 0.06: mean order 300 units)")
    run_cmd.add_argument("--value-traders", type=int, default=0,
                         help="how many of the 250 takers are value traders (default 0)")
    run_cmd.add_argument("--true-value-step", type=float, default=1.0,
                         help="small step of the true value each step, standard deviation in ticks (default 1)")
    run_cmd.add_argument("--value-spread", type=float, default=50.0,
                         help="mean distance of a value trader's own value from the true value, in ticks (default 50)")
    run_cmd.add_argument("--momentum-traders", type=int, default=0,
                         help="how many of the takers are momentum traders (default 0)")
    run_cmd.add_argument("--momentum-orders", type=int, nargs="+", default=[1], choices=(1, 2, 3),
                         help="how many derivatives they see; several are split equally (default 1)")
    run_cmd.add_argument("--momentum-window", type=int, default=50,
                         help="steps of past mid-prices they read the trend from (default 50)")
    run_cmd.add_argument("--momentum-scale", type=float, default=1.0,
                         help="signal, in units of its typical size, that makes them fairly sure (default 1)")
    run_cmd.add_argument("--provider-mix", nargs="+", metavar="K:COUNT", default=None,
                         help="provider types, e.g. 1:100 2:100 4:50 (default: all 1:250)")
    run_cmd.add_argument("--taker-mix", nargs="+", metavar="K:COUNT", default=None,
                         help="taker types; must add up to the takers left after value and momentum traders")
    run_cmd.add_argument("--workers", type=int, default=None, help="processes to use (default: all cores)")
    run_cmd.add_argument("--out", type=Path, default=Path("results/pressure/pressure.pkl"))

    plot_cmd = commands.add_parser("plot", help="draw one or more saved event studies, one row each")
    plot_cmd.add_argument("--data", type=Path, nargs="+", required=True)
    plot_cmd.add_argument("--labels", nargs="+", default=None, help="one per file (default: the file names)")
    plot_cmd.add_argument("--out", type=Path, default=Path("results/pressure/compare.png"))

    args = parser.parse_args(argv)
    if args.command == "run":
        run(args, parser)
    else:
        labels = args.labels or [p.stem for p in args.data]
        if len(labels) != len(args.data):
            parser.error("give one label per file")
        datas = []
        for path in args.data:
            with open(path, "rb") as f:
                datas.append(pickle.load(f))
        print_summaries(labels, datas)
        plot(labels, datas, args.out)


if __name__ == "__main__":
    main()
