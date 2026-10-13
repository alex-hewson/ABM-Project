"""
Shock test: inject one large market order into the baseline model and watch the book afterwards.

    python -m experiments.shock                                  # default: sizes 0, 50, 150, 300
    python -m experiments.shock --sizes 0 100 400 --n-runs 400 --out results/shock_test.png

Each run is the basic model (paper Fig. 2 parameters, symmetric order flow). It runs for --warmup
steps so the book settles, then one market sell order of the given size is injected (run_simulation's
shock option), and the run goes on for --after steps. --buy injects a buy order instead.

For every size the same seeds are used, so the runs are identical up to the shock. Size 0 is the
control with no shock: it shows how much of a curve is noise.

--provider-mix and --taker-mix give the agents different speeds and order sizes (abm/agents.py,
AgentType). Each item is K:COUNT, meaning COUNT agents that get a chance to act every K steps and
place orders of K units. The counts must add up to 250. For example, a market of 4-step providers,
and one with all three types:

    python -m experiments.shock --provider-mix 4:250 --out results/shock_providers4.png
    python -m experiments.shock --provider-mix 1:100 2:100 4:50 --out results/shock_mixed.png

INTERVAL/SIZE:COUNT sets the two separately, e.g. 4/1:250 for unit orders every 4 steps. Without
these options every agent is the paper's (1:250).

Recorded each step and averaged over runs:
    price    mid-price minus its value at the step before the shock
    spread   best ask minus best bid
    volume   number of resting units on each side of the book (= number of orders while every
             order is one unit)

The figure is saved to --out, and the averaged curves to the same name with .pkl. A summary table
(impact, share recovered, recovery times; see analysis/recovery.py) is printed.
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

from abm.agents import AgentType
from abm.orderbook import Side
from abm.simulation import run_simulation, Shock
from analysis.recovery import window, mean_response, pre_shock_level, impact, recovered_fraction, time_to_recover
from experiments.provenance import git_info, describe
from experiments.run import PARAMS

N_AGENTS = 250
BEFORE = 200          # steps shown (and averaged for the "before" level) ahead of the shock
TAIL = 200            # the "end" level is the mean of this many final steps
QUANTITIES = ("price", "spread", "bid_volume", "ask_volume")


def parse_mix(items):
    """['1:100', '4:150'] -> {AgentType(1, 1): 100, AgentType(4, 4): 150}. K:COUNT gives agents that
    act every K steps with orders of K units; INTERVAL/SIZE:COUNT sets the two separately.
    None (option not given) stays None, which run_simulation reads as the paper's population."""
    if items is None:
        return None
    mix = {}
    for item in items:
        try:
            kind, count = item.split(":")
            interval, size = kind.split("/") if "/" in kind else (kind, kind)
            agent_type = AgentType(int(interval), int(size))
            mix[agent_type] = mix.get(agent_type, 0) + int(count)
        except ValueError as error:
            raise ValueError(f"cannot read mix item {item!r}: expected K:COUNT or INTERVAL/SIZE:COUNT") from error
    return mix


def describe_mix(mix):
    """Short text for a mix, e.g. '100 x 1 unit every step, 150 x 4 units every 4 steps'."""
    if mix is None:
        mix = {AgentType(): N_AGENTS}
    parts = []
    for agent_type, count in mix.items():
        units = "1 unit" if agent_type.size == 1 else f"{agent_type.size} units"
        every = "every step" if agent_type.interval == 1 else f"every {agent_type.interval} steps"
        parts.append(f"{count} x {units} {every}")
    return ", ".join(parts)


def run_one(task):
    """One run: returns the window around the shock for each recorded quantity."""
    size, seed, warmup, after, buy, provider_mix, taker_mix = task
    shock = Shock(step=warmup, size=size, side=Side.BID if buy else Side.ASK) if size > 0 else None
    r = run_simulation(n_agents=N_AGENTS, n_steps=warmup + after + 1, seed=seed, shock=shock,
                       record_sides=True, keep_trades=False, provider_mix=provider_mix, taker_mix=taker_mix,
                       **PARAMS)
    mid = window(r.mid_price_series, warmup, BEFORE, after)
    return {
        "size": size,
        "price": mid - mid[BEFORE - 1],          # change since the step before the shock
        "spread": window(r.best_ask_series - r.best_bid_series, warmup, BEFORE, after),
        "bid_volume": window(r.bid_volume_series, warmup, BEFORE, after),
        "ask_volume": window(r.ask_volume_series, warmup, BEFORE, after),
        "unfilled": r.shock_unfilled,
    }


def summarise(means, sizes, buy):
    """Print, for each shock size, what the shock did and how much of it was undone."""
    hit_side = "ask_volume" if buy else "bid_volume"
    print(f"\n{'size':>5} | {'price: impact':>13} {'end':>7} {'recovered':>9} | "
          f"{'spread: before':>14} {'at shock':>8} {'half-life':>9} | "
          f"{'volume: before':>14} {'at shock':>8} {'half-life':>9} {'90% back':>8}")
    for size in sizes:
        m = means[size]
        if size == 0:
            print(f"{size:>5} | {'(control)':>13} {np.mean(m['price'][-TAIL:]):>7.1f}")
            continue
        price, spread, volume = m["price"], m["spread"], m[hit_side]
        def steps(x):
            return "never" if x is None else str(x)
        print(f"{size:>5} | {impact(price, BEFORE):>13.1f} {np.mean(price[-TAIL:]):>7.1f} "
              f"{recovered_fraction(price, BEFORE, TAIL):>9.2f} | "
              f"{pre_shock_level(spread, BEFORE):>14.1f} {spread[BEFORE]:>8.1f} {steps(time_to_recover(spread, BEFORE)):>9} | "
              f"{pre_shock_level(volume, BEFORE):>14.0f} {volume[BEFORE]:>8.0f} {steps(time_to_recover(volume, BEFORE)):>9} "
              f"{steps(time_to_recover(volume, BEFORE, 0.9)):>8}")
    print("\nprice in ticks; volume = resting units on the side the shock hit; "
          "'recovered' = share of the price move undone by the end "
          "(1 = back to the old price, 0 = none);\nhalf-life and '90% back' in steps after the shock.")


def plot(means, sizes, config, out):
    after = config["after"]
    t = np.arange(-BEFORE, after + 1)
    what = "buy" if config["buy"] else "sell"
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    (ax_price, ax_zoom), (ax_spread, ax_volume) = axes

    for colour, size in enumerate(sizes):
        m, c = means[size], f"C{colour}"
        label = "no shock" if size == 0 else f"size {size}"
        ax_price.plot(t, m["price"], color=c, lw=0.9, label=label)
        ax_zoom.plot(t, m["price"], color=c, lw=0.9, label=label)
        ax_spread.plot(t, m["spread"], color=c, lw=0.9, label=label)
        ax_volume.plot(t, m["bid_volume"], color=c, lw=0.9, label=f"{label}: bids")
        ax_volume.plot(t, m["ask_volume"], color=c, lw=0.9, ls="--", label=f"{label}: asks")

    ax_price.set(title="(a) mid-price change", xlabel="steps since the shock", ylabel="price change [ticks]")
    ax_zoom.set(title="(b) mid-price change, first 300 steps", xlabel="steps since the shock",
                ylabel="price change [ticks]", xlim=(-30, 300))
    ax_spread.set(title="(c) spread", xlabel="steps since the shock", ylabel="spread [ticks]", xlim=(-30, 300))
    ax_volume.set(title="(d) resting units per side (solid: bids, dashed: asks)",
                  xlabel="steps since the shock", ylabel="units", xlim=(-30, 300))
    for ax in (ax_price, ax_zoom, ax_spread):
        ax.axvline(0, color="gray", lw=0.5, ls=":")
        ax.legend(fontsize=8)
    ax_volume.axvline(0, color="gray", lw=0.5, ls=":")
    ax_price.axhline(0, color="gray", lw=0.5, ls=":")
    ax_zoom.axhline(0, color="gray", lw=0.5, ls=":")

    fig.suptitle(f"Shock test: one market {what} order at step 0, basic model, N$_A$={N_AGENTS}, "
                 f"mean of {config['n_runs']} runs\n"
                 f"providers: {config['providers']}   |   takers: {config['takers']}", fontsize=11)
    fig.text(0.995, 0.005, "code version: " + describe(config["git"]), ha="right", va="bottom",
             fontsize=7, color="gray")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=110)
    plt.close(fig)
    print(f"saved {out}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sizes", type=int, nargs="+", default=[0, 50, 150, 300],
                        help="shock sizes in units; 0 is the control with no shock")
    parser.add_argument("--n-runs", type=int, default=200, help="runs per size")
    parser.add_argument("--warmup", type=int, default=2000, help="steps before the shock")
    parser.add_argument("--after", type=int, default=2000, help="steps after the shock")
    parser.add_argument("--buy", action="store_true", help="inject a buy order instead of a sell order")
    parser.add_argument("--provider-mix", nargs="+", metavar="K:COUNT", default=None,
                        help="provider types, e.g. 1:100 2:100 4:50 (default: all 1:250)")
    parser.add_argument("--taker-mix", nargs="+", metavar="K:COUNT", default=None,
                        help="taker types, in the same form (default: all 1:250)")
    parser.add_argument("--workers", type=int, default=None, help="processes to use (default: all cores)")
    parser.add_argument("--out", type=Path, default=Path("results/shock_test.png"))
    args = parser.parse_args()
    if args.warmup < BEFORE or args.after < TAIL:
        parser.error(f"--warmup must be at least {BEFORE} and --after at least {TAIL}")

    try:
        provider_mix, taker_mix = parse_mix(args.provider_mix), parse_mix(args.taker_mix)
    except ValueError as error:
        parser.error(str(error))
    for name, mix in (("--provider-mix", provider_mix), ("--taker-mix", taker_mix)):
        if mix is not None and sum(mix.values()) != N_AGENTS:
            parser.error(f"{name}: the counts must add up to {N_AGENTS}, got {sum(mix.values())}")

    sizes = sorted(set(args.sizes))
    tasks = [(size, seed, args.warmup, args.after, args.buy, provider_mix, taker_mix)
             for size in sizes for seed in range(args.n_runs)]
    config = dict(sizes=sizes, n_runs=args.n_runs, warmup=args.warmup, after=args.after, buy=args.buy,
                  n_agents=N_AGENTS, params=PARAMS, git=git_info(),
                  providers=describe_mix(provider_mix), takers=describe_mix(taker_mix),
                  provider_mix=provider_mix, taker_mix=taker_mix)
    print(f"{len(tasks)} runs: sizes {sizes}, {args.n_runs} runs each, code version {describe(config['git'])}\n"
          f"providers: {config['providers']}\ntakers:    {config['takers']}", flush=True)

    start = time.perf_counter()
    windows = {size: {q: [] for q in QUANTITIES} for size in sizes}
    unfilled = {size: 0 for size in sizes}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        try:
            for count, r in enumerate(pool.map(run_one, tasks, chunksize=4), 1):
                for q in QUANTITIES:
                    windows[r["size"]][q].append(r[q])
                unfilled[r["size"]] += r["unfilled"] > 0
                if count % 100 == 0 or count == len(tasks):
                    print(f"[{count}/{len(tasks)}] {time.perf_counter() - start:.0f}s elapsed", flush=True)
        except BaseException:
            pool.shutdown(wait=True, cancel_futures=True)    # don't finish the queued runs after an error
            raise

    means = {size: {q: mean_response(windows[size][q]) for q in QUANTITIES} for size in sizes}
    for size in sizes:
        if unfilled[size]:
            print(f"WARNING: size {size} emptied that side of the book in {unfilled[size]} of {args.n_runs} runs; "
                  "steps with no midpoint are left out of the averages")

    summarise(means, sizes, args.buy)
    plot(means, sizes, config, args.out)
    data_out = args.out.with_suffix(".pkl")
    with open(data_out, "wb") as f:
        pickle.dump({"config": config, "means": means, "t": np.arange(-BEFORE, args.after + 1)}, f)
    print(f"saved {data_out}")


if __name__ == "__main__":
    main()
