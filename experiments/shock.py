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

--value-traders N turns N of the 250 takers into value traders (abm/agents.py, ValueTrader), which
buy when the price is below their own value and sell when it is above. Their values are estimates of
the asset's true value, which only moves with news (docs/decisions.md, D30). --true-value-step sets
how much it moves each step, and --value-spread how far apart the traders' estimates are (mean error,
in ticks):

    python -m experiments.shock --value-traders 125 --out results/shock_value125.png

--news-chance, --news-jump and --news-jump-spread add news, jumps in the true value at random times,
as in experiments/run.py (docs/decisions.md, D32). They need value traders.

--momentum-traders N turns N of the takers into momentum traders (abm/agents.py, MomentumTrader),
which follow the trend of the last --momentum-window mid-prices; --momentum-orders and
--momentum-scale as in experiments/run.py. Value and momentum traders can be combined:

    python -m experiments.shock --value-traders 50 --momentum-traders 50 --out results/shock_both.png

Recorded each step and averaged over runs:
    price    mid-price minus its value at the step before the shock
    spread   best ask minus best bid
    volume   number of resting units on each side of the book (= number of orders while every
             order is one unit)
    price_vs_value
             the mid-price minus the true value (docs/decisions.md, D30), as a change since the step
             before the shock. The true value keeps moving with news after the shock, which adds
             noise to the plain price; this takes it out, so it measures whether the price has gone
             back to what the asset is worth. Without value traders there is no true value, and
             this is the same as the price change. Recovery (the summary table, panels (a) and (b))
             is measured on this.

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
QUANTITIES = ("price", "price_vs_value", "spread", "bid_volume", "ask_volume")


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


def describe_mix(mix, n_agents=N_AGENTS):
    """Short text for a mix, e.g. '100 x 1 unit every step, 150 x 4 units every 4 steps'.
    n_agents is how many agents there are when no mix was given."""
    if mix is None:
        mix = {AgentType(): n_agents}
    parts = []
    for agent_type, count in mix.items():
        units = "1 unit" if agent_type.size == 1 else f"{agent_type.size} units"
        every = "every step" if agent_type.interval == 1 else f"every {agent_type.interval} steps"
        parts.append(f"{count} x {units} {every}")
    return ", ".join(parts)


def run_one(task):
    """One run: returns the window around the shock for each recorded quantity."""
    size, seed, warmup, after, buy, provider_mix, taker_mix, value, *more = task
    n_value_traders, true_value_step, value_spread = value
    n_momentum_traders, momentum_orders, momentum_window, momentum_scale = more[0] if more else (0, (1,), 50, 1.0)
    news_chance, news_jump, news_jump_spread = more[1] if len(more) > 1 else (0.0, 30.0, 10.0)
    shock = Shock(step=warmup, size=size, side=Side.BID if buy else Side.ASK) if size > 0 else None
    r = run_simulation(n_agents=N_AGENTS, n_steps=warmup + after + 1, seed=seed, shock=shock,
                       record_sides=True, keep_trades=False, provider_mix=provider_mix, taker_mix=taker_mix,
                       n_value_traders=n_value_traders, true_value_step=true_value_step, value_spread=value_spread,
                       news_chance=news_chance, news_jump=news_jump, news_jump_spread=news_jump_spread,
                       n_momentum_traders=n_momentum_traders, momentum_orders=momentum_orders,
                       momentum_window=momentum_window, momentum_scale=momentum_scale,
                       **PARAMS)
    mid = window(r.mid_price_series, warmup, BEFORE, after)
    price = mid - mid[BEFORE - 1]                # change since the step before the shock
    if n_value_traders:
        gap = mid - window(r.true_value_series, warmup, BEFORE, after)
        price_vs_value = gap - gap[BEFORE - 1]
    else:
        price_vs_value = price                   # no true value: as if it never moved
    return {
        "size": size,
        "price": price,
        "price_vs_value": price_vs_value,
        "spread": window(r.best_ask_series - r.best_bid_series, warmup, BEFORE, after),
        "bid_volume": window(r.bid_volume_series, warmup, BEFORE, after),
        "ask_volume": window(r.ask_volume_series, warmup, BEFORE, after),
        "unfilled": r.shock_unfilled,
    }


def summarise(means, sizes, buy):
    """Print, for each shock size, what the shock did and how much of it was undone."""
    hit_side = "ask_volume" if buy else "bid_volume"
    print(f"\n{'size':>5} | {'price*: impact':>14} {'end':>7} {'recovered':>9} {'half-life':>9} | "
          f"{'spread: before':>14} {'at shock':>8} {'half-life':>9} | "
          f"{'volume: before':>14} {'at shock':>8} {'half-life':>9} {'90% back':>8}")
    for size in sizes:
        m = means[size]
        if size == 0:
            print(f"{size:>5} | {'(control)':>14} {np.mean(m['price_vs_value'][-TAIL:]):>7.1f}")
            continue
        price, spread, volume = m["price_vs_value"], m["spread"], m[hit_side]
        def steps(x):
            return "never" if x is None else str(x)
        print(f"{size:>5} | {impact(price, BEFORE):>14.1f} {np.mean(price[-TAIL:]):>7.1f} "
              f"{recovered_fraction(price, BEFORE, TAIL):>9.2f} {steps(time_to_recover(price, BEFORE)):>9} | "
              f"{pre_shock_level(spread, BEFORE):>14.1f} {spread[BEFORE]:>8.1f} {steps(time_to_recover(spread, BEFORE)):>9} | "
              f"{pre_shock_level(volume, BEFORE):>14.0f} {volume[BEFORE]:>8.0f} {steps(time_to_recover(volume, BEFORE)):>9} "
              f"{steps(time_to_recover(volume, BEFORE, 0.9)):>8}")
    print("\nprice* = mid-price minus the true value (just the price without value traders), in ticks; "
          "volume = resting units\non the side the shock hit; 'recovered' = share of the price* move undone by "
          "the end (1 = all, 0 = none);\nhalf-life and '90% back' in steps after the shock.")


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
        ax_zoom.plot(t, m["price_vs_value"], color=c, lw=0.9, label=label)
        ax_spread.plot(t, m["spread"], color=c, lw=0.9, label=label)
        ax_volume.plot(t, m["bid_volume"], color=c, lw=0.9, label=f"{label}: bids")
        ax_volume.plot(t, m["ask_volume"], color=c, lw=0.9, ls="--", label=f"{label}: asks")

    ax_price.set(title="(a) mid-price change", xlabel="steps since the shock", ylabel="price change [ticks]")
    ax_zoom.set(title="(b) mid-price minus true value: what recovery is measured on",
                xlabel="steps since the shock", ylabel="change [ticks]")
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
                 f"providers: {config['providers']}   |   takers: {config['takers']}"
                 + (f"   |   {config['value_traders']}" if config["n_value_traders"] else "")
                 + (f"   |   {config['momentum_traders']}" if config.get("n_momentum_traders") else ""), fontsize=11)
    fig.text(0.995, 0.005, "code version: " + describe(config["git"]), ha="right", va="bottom",
             fontsize=7, color="gray")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=110)
    plt.close(fig)
    print(f"saved {out}")


def main(argv=None):
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
    parser.add_argument("--value-traders", type=int, default=0,
                        help="how many of the 250 takers are value traders (default 0)")
    parser.add_argument("--true-value-step", type=float, default=1.0,
                        help="how much the true value moves each step: the standard deviation, in ticks (default 1)")
    parser.add_argument("--value-spread", type=float, default=50.0,
                        help="mean distance of a value trader's own value from the true value, in ticks (default 50)")
    parser.add_argument("--news-chance", type=float, default=0.0,
                        help="chance each step that news makes the true value jump, e.g. 0.0001 (default 0: none)")
    parser.add_argument("--news-jump", type=float, default=30.0,
                        help="mean size of a news jump, in ticks (default 30)")
    parser.add_argument("--news-jump-spread", type=float, default=10.0,
                        help="standard deviation of the jump size, in ticks (default 10)")
    parser.add_argument("--momentum-traders", type=int, default=0,
                        help="how many of the takers are momentum traders (default 0)")
    parser.add_argument("--momentum-orders", type=int, nargs="+", default=[1], choices=(1, 2, 3),
                        help="how many derivatives they see; several are split equally (default 1)")
    parser.add_argument("--momentum-window", type=int, default=50,
                        help="steps of past mid-prices they read the trend from (default 50)")
    parser.add_argument("--momentum-scale", type=float, default=1.0,
                        help="signal, in units of its typical size, that makes them fairly sure (default 1)")
    parser.add_argument("--workers", type=int, default=None, help="processes to use (default: all cores)")
    parser.add_argument("--out", type=Path, default=Path("results/shock_test.png"))
    args = parser.parse_args(argv)
    if args.warmup < BEFORE or args.after < TAIL:
        parser.error(f"--warmup must be at least {BEFORE} and --after at least {TAIL}")

    try:
        provider_mix, taker_mix = parse_mix(args.provider_mix), parse_mix(args.taker_mix)
    except ValueError as error:
        parser.error(str(error))
    if not (0 <= args.value_traders <= N_AGENTS) or not (0 <= args.momentum_traders <= N_AGENTS - args.value_traders):
        parser.error(f"--value-traders and --momentum-traders must be 0 or more and add up to at most {N_AGENTS}")
    n_takers = N_AGENTS - args.value_traders - args.momentum_traders   # both take the place of takers
    for name, mix, total in (("--provider-mix", provider_mix, N_AGENTS), ("--taker-mix", taker_mix, n_takers)):
        if mix is not None and sum(mix.values()) != total:
            parser.error(f"{name}: the counts must add up to {total}, got {sum(mix.values())}")
    value = (args.value_traders, args.true_value_step, args.value_spread)
    momentum = (args.momentum_traders, tuple(args.momentum_orders), args.momentum_window, args.momentum_scale)
    if not (0 <= args.news_chance <= 1) or args.news_jump < 0 or args.news_jump_spread < 0:
        parser.error("--news-chance must be between 0 and 1, and --news-jump and --news-jump-spread 0 or more")
    if args.news_chance > 0 and args.value_traders == 0:
        parser.error("--news-chance needs --value-traders: news moves the true value, which only value traders see")
    news = (args.news_chance, args.news_jump, args.news_jump_spread)

    sizes = sorted(set(args.sizes))
    tasks = [(size, seed, args.warmup, args.after, args.buy, provider_mix, taker_mix, value, momentum, news)
             for size in sizes for seed in range(args.n_runs)]
    config = dict(sizes=sizes, n_runs=args.n_runs, warmup=args.warmup, after=args.after, buy=args.buy,
                  n_agents=N_AGENTS, params=PARAMS, git=git_info(),
                  providers=describe_mix(provider_mix), takers=describe_mix(taker_mix, n_takers),
                  provider_mix=provider_mix, taker_mix=taker_mix,
                  n_value_traders=args.value_traders, true_value_step=args.true_value_step,
                  value_spread=args.value_spread,
                  value_traders=f"{args.value_traders} value traders (true value step {args.true_value_step:g}, "
                                f"spread {args.value_spread:g})",
                  news_chance=args.news_chance, news_jump=args.news_jump, news_jump_spread=args.news_jump_spread,
                  news=f"news: chance {args.news_chance:g} per step, jumps of {args.news_jump:g} "
                       f"+- {args.news_jump_spread:g} ticks",
                  n_momentum_traders=args.momentum_traders, momentum_orders=list(args.momentum_orders),
                  momentum_window=args.momentum_window, momentum_scale=args.momentum_scale,
                  momentum_traders=f"{args.momentum_traders} momentum traders (orders {list(args.momentum_orders)}, "
                                   f"window {args.momentum_window})")
    print(f"{len(tasks)} runs: sizes {sizes}, {args.n_runs} runs each, code version {describe(config['git'])}\n"
          f"providers: {config['providers']}\ntakers:    {config['takers']}"
          + (f"\nplus:      {config['value_traders']}" if args.value_traders else "")
          + (f"\nplus:      {config['momentum_traders']}" if args.momentum_traders else "")
          + (f"\nplus:      {config['news']}" if args.news_chance else ""), flush=True)

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
