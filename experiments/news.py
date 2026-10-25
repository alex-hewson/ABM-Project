"""
Event study of news (docs/decisions.md, D32, D33): long runs in which the true value jumps at random
times, then the price around every jump is lined up and averaged. It shows how fast the price takes
in news, whether it overshoots, and how that depends on the traders in the market.

News moves only the true value, which only value traders see, so there must be value traders. The
other agent options are the shock test's (experiments/shock.py):

    python -m experiments.news run --value-traders 50 --out results/news/value50.pkl
    python -m experiments.news run --value-traders 50 --momentum-traders 50 --out results/news/value50_mom50.pkl
    python -m experiments.news plot --data results/news/value50.pkl results/news/value50_mom50.pkl \\
        --labels "value 50" "value 50 + momentum 50" --out results/news/compare.png

Step 0 of a window is the first step in which value traders know the new value (the jump happens at
the end of the step before). Only jumps with no other jump from 200 steps ahead to --after steps
past are used, and none in the first --warmup steps. Every jump is flipped to point up, the windows
are averaged in ticks, and the average is divided by the mean jump size, so the curves are in units
of the jump (dividing each window by its own jump would let a jump of a fraction of a tick multiply
its noise many times over):

    price    mid-price change since before the jump: 0 before, 1 once the price has moved by the
             whole jump
    gap      mid-price minus the true value, as a change since before the jump: about -1 at step 0
             (the value has jumped, the price not yet), back to 0 once the price has caught up. This
             is the shock test's "price*" turned around: there the price moves and the value does
             not, here the value moves and the price has to follow.

The summary and the figure use the share of the jump the price has taken in: the gap from step 0 on,
plus 1 (0 before the news and when it arrives, 1 once the price has caught up). On average it is the
same as the price curve, but the small steps of the true value (about 45 ticks over 2,000 steps,
more than a jump) are taken out, so it is much less noisy.

The curves are averaged over all jumps used, from all runs. `run` prints a summary and saves the
curves to --out; `plot` draws one or more saved files together and prints their summaries side by side.
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
from analysis.recovery import mean_response
from experiments.provenance import git_info, describe
from experiments.run import PARAMS
from experiments.shock import N_AGENTS, parse_mix, describe_mix

BEFORE = 200          # steps shown (and averaged for the "before" level) ahead of each jump
TAIL = 200            # the "end" level is the mean of this many final steps
CURVES = ("price", "gap")


def run_one(task):
    """One long run: the windows around every clean jump in it, and how many jumps there were."""
    (seed, n_steps, warmup, after, provider_mix, taker_mix, value, momentum, news) = task
    n_value_traders, true_value_step, value_spread = value
    n_momentum_traders, momentum_orders, momentum_window, momentum_scale = momentum
    news_chance, news_jump, news_jump_spread = news
    r = run_simulation(n_agents=N_AGENTS, n_steps=n_steps, seed=seed, keep_trades=False,
                       provider_mix=provider_mix, taker_mix=taker_mix,
                       n_value_traders=n_value_traders, true_value_step=true_value_step, value_spread=value_spread,
                       news_chance=news_chance, news_jump=news_jump, news_jump_spread=news_jump_spread,
                       n_momentum_traders=n_momentum_traders, momentum_orders=momentum_orders,
                       momentum_window=momentum_window, momentum_scale=momentum_scale,
                       **PARAMS)
    mid = np.array([np.nan if m is None else m for m in r.mid_price_series], dtype=float)
    gap = mid - r.true_value_series
    starts = r.news_steps + 1                  # first step with the new value
    keep = clean_events(starts, n_steps, BEFORE, after, start=warmup)
    windows = {name: [] for name in CURVES}
    for start, jump in zip(starts[keep], r.news_jumps[keep]):
        windows["price"].append(signed_window(mid, start, jump, BEFORE, after))
        windows["gap"].append(signed_window(gap, start, jump, BEFORE, after))
    return {"windows": windows, "jumps": r.news_jumps[keep], "n_jumps": len(r.news_steps)}


def steps_to_close(gap: np.ndarray, fraction: float):
    """Steps from step 0 until `fraction` of the jump has been made up, i.e. the gap (in units of the
    jump, -1 when the news arrives) is back above -(1 - fraction). None if never inside the window.
    Measured against the whole jump, not against the gap at step 0, which is already a bit smaller."""
    reached = np.nonzero(gap[BEFORE:] >= -(1.0 - fraction))[0]
    return int(reached[0]) if len(reached) else None


def summary(data) -> dict:
    """The main numbers of one saved event study, all from the share of the jump taken in (1 + gap)."""
    gap = data["means"]["gap"]
    taken = 1.0 + gap[BEFORE:]
    peak = int(np.argmax(taken))
    return {
        "jumps": f"{data['n_used']} of {data['n_jumps']}",
        "at step 0": float(taken[0]),                   # taken in during the first step the news is known
        "half-way": steps_to_close(gap, 0.5),
        "90%": steps_to_close(gap, 0.9),
        "peak": float(taken[peak]),
        "peak at": peak,
        "end": float(np.mean(taken[-TAIL:])),           # 1 = the price has taken in the whole jump
    }


def print_summaries(labels, datas):
    def fmt(x):
        if x is None:
            return "never"
        return f"{x:.2f}" if isinstance(x, float) else str(x)
    keys = list(summary(datas[0]))
    width = max(len(label) for label in labels)
    print(f"\n{'':<{width}} | " + " ".join(f"{k:>11}" for k in keys))
    for label, data in zip(labels, datas):
        s = summary(data)
        print(f"{label:<{width}} | " + " ".join(f"{fmt(s[k]):>11}" for k in keys))
    print("\nShare of the jump taken into the price (price move minus the true value's small steps; 1 = all of it). "
          "'at step 0' = taken\nin during the first step the news is known; 'half-way' and '90%' = steps until that "
          "much is taken in; 'peak' = the\nlargest share (above 1 = overshoot) and the step it comes at; 'end' = the "
          "share at the end of the window.")


def describe_momentum(config) -> str:
    """Which momentum traders a saved study had, for the legend, e.g. 'momentum: order 1 (slope), window 50'."""
    if not config.get("n_momentum_traders"):
        return "no momentum traders"
    seen = {1: "slope", 2: "slope + curvature", 3: "up to 3rd derivative"}
    orders = config["momentum_orders"]
    if len(set(orders)) == 1:
        kind = f"order {orders[0]} ({seen[orders[0]]})"
    else:
        kind = "mix of orders " + ", ".join(str(o) for o in orders)
    return f"momentum: {kind}, window {config['momentum_window']}"


def plot(labels, datas, out):
    fig, (ax_all, ax_zoom) = plt.subplots(1, 2, figsize=(13, 5))
    for colour, (label, data) in enumerate(zip(labels, datas)):
        t = data["t"]
        mean, err = data["means"]["gap"] + (t >= 0), data["errors"]["gap"]      # share of the jump taken in
        for ax in (ax_all, ax_zoom):
            ax.plot(t, mean, color=f"C{colour}", lw=0.9,
                    label=f"{label}\n  ({describe_momentum(data['config'])}; {data['n_used']} jumps)")
            ax.fill_between(t, mean - err, mean + err, color=f"C{colour}", alpha=0.2, lw=0)
    for ax in (ax_all, ax_zoom):
        ax.axhline(0, color="gray", lw=0.5, ls=":")
        ax.axhline(1, color="gray", lw=0.5, ls=":")
        ax.axvline(0, color="gray", lw=0.5, ls=":")
        ax.set(xlabel="steps since the news", ylabel="share of the jump taken in")
    ax_all.set(title="(a) share of the jump taken into the price")
    ax_zoom.set(title="(b) the first 300 steps", xlim=(-30, 300))
    ax_all.legend(fontsize=8)
    first = datas[0]["config"]
    fig.suptitle(f"News event study: N$_A$={N_AGENTS}, jumps of {first['news_jump']:g} ± {first['news_jump_spread']:g} "
                 f"ticks, shaded = ± 1 standard error", fontsize=11)
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
    if not (1 <= args.value_traders <= N_AGENTS) or not (0 <= args.momentum_traders <= N_AGENTS - args.value_traders):
        parser.error(f"--value-traders must be at least 1 (news needs them), and with --momentum-traders "
                     f"add up to at most {N_AGENTS}")
    n_takers = N_AGENTS - args.value_traders - args.momentum_traders
    for name, mix, total in (("--provider-mix", provider_mix, N_AGENTS), ("--taker-mix", taker_mix, n_takers)):
        if mix is not None and sum(mix.values()) != total:
            parser.error(f"{name}: the counts must add up to {total}, got {sum(mix.values())}")
    if not (0 < args.news_chance <= 1):
        parser.error("--news-chance must be above 0 and at most 1")
    if args.warmup < BEFORE or args.after < TAIL or args.n_steps <= args.warmup + args.after:
        parser.error(f"--warmup must be at least {BEFORE}, --after at least {TAIL}, and --n-steps longer than both")

    value = (args.value_traders, args.true_value_step, args.value_spread)
    momentum = (args.momentum_traders, tuple(args.momentum_orders), args.momentum_window, args.momentum_scale)
    news = (args.news_chance, args.news_jump, args.news_jump_spread)
    tasks = [(seed, args.n_steps, args.warmup, args.after, provider_mix, taker_mix, value, momentum, news)
             for seed in range(args.n_runs)]
    config = dict(n_runs=args.n_runs, n_steps=args.n_steps, warmup=args.warmup, after=args.after,
                  n_agents=N_AGENTS, params=PARAMS, git=git_info(),
                  providers=describe_mix(provider_mix), takers=describe_mix(taker_mix, n_takers),
                  provider_mix=provider_mix, taker_mix=taker_mix,
                  n_value_traders=args.value_traders, true_value_step=args.true_value_step,
                  value_spread=args.value_spread,
                  news_chance=args.news_chance, news_jump=args.news_jump, news_jump_spread=args.news_jump_spread,
                  n_momentum_traders=args.momentum_traders, momentum_orders=list(args.momentum_orders),
                  momentum_window=args.momentum_window, momentum_scale=args.momentum_scale)
    print(f"{args.n_runs} runs of {args.n_steps:,} steps, code version {describe(config['git'])}\n"
          f"providers: {config['providers']}\ntakers:    {config['takers']}\n"
          f"plus:      {args.value_traders} value traders (true value step {args.true_value_step:g}, "
          f"spread {args.value_spread:g})"
          + (f"\nplus:      {args.momentum_traders} momentum traders (orders {list(args.momentum_orders)}, "
             f"window {args.momentum_window})" if args.momentum_traders else "")
          + f"\nnews:      chance {args.news_chance:g} per step, jumps of {args.news_jump:g} +- "
            f"{args.news_jump_spread:g} ticks", flush=True)

    start = time.perf_counter()
    windows = {name: [] for name in CURVES}
    jumps, n_jumps = [], 0
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        try:
            for count, r in enumerate(pool.map(run_one, tasks), 1):
                for name in CURVES:
                    windows[name] += r["windows"][name]
                jumps += list(r["jumps"])
                n_jumps += r["n_jumps"]
                if count % 10 == 0 or count == len(tasks):
                    print(f"[{count}/{len(tasks)}] {time.perf_counter() - start:.0f}s elapsed, "
                          f"{len(jumps)} jumps used so far", flush=True)
        except BaseException:
            pool.shutdown(wait=True, cancel_futures=True)    # don't finish the queued runs after an error
            raise
    if not jumps:
        raise SystemExit("No jump could be used: raise --n-steps or --news-chance, or lower --after.")

    unit = float(np.mean(np.abs(jumps)))       # the mean jump: the curves are in units of it
    data = {"config": config, "t": np.arange(-BEFORE, args.after + 1),
            "means": {name: mean_response(windows[name]) / unit for name in CURVES},
            "errors": {name: np.nanstd(np.asarray(windows[name]), axis=0) / np.sqrt(len(jumps)) / unit
                       for name in CURVES},
            "n_used": len(jumps), "n_jumps": n_jumps, "jumps": np.array(jumps)}
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
    run_cmd.add_argument("--warmup", type=int, default=2000, help="no jumps used before this step (default 2000)")
    run_cmd.add_argument("--after", type=int, default=2000, help="steps recorded after each jump (default 2000)")
    run_cmd.add_argument("--news-chance", type=float, default=0.0002,
                         help="chance of news each step (default 0.0002, once per 5,000 steps: more jumps per "
                              "run than the model's 1 in 10,000, with few too close together to use)")
    run_cmd.add_argument("--news-jump", type=float, default=30.0, help="mean size of a jump, in ticks (default 30)")
    run_cmd.add_argument("--news-jump-spread", type=float, default=10.0,
                         help="standard deviation of the jump size, in ticks (default 10)")
    run_cmd.add_argument("--value-traders", type=int, default=50,
                         help="how many of the 250 takers are value traders (default 50)")
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
    run_cmd.add_argument("--out", type=Path, default=Path("results/news/news.pkl"))

    plot_cmd = commands.add_parser("plot", help="draw one or more saved event studies together")
    plot_cmd.add_argument("--data", type=Path, nargs="+", required=True)
    plot_cmd.add_argument("--labels", nargs="+", default=None, help="one per file (default: the file names)")
    plot_cmd.add_argument("--out", type=Path, default=Path("results/news/compare.png"))

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
