"""
E-mini S&P 500 futures data (Refinitiv / LSEG Tick History "Time and Sales" format), for comparing the
model with a real market. The data stays outside the repository: every command takes the file's path
as an argument, and prints or saves only summaries, never rows of the data.

Expected columns:

    #RIC        contract code, e.g. ESZ6 (December 2026)
    Domain      e.g. Market Price
    Date-Time   timestamp, ISO 8601
    Type        Trade or Quote (others are counted and otherwise ignored)
    Price, Volume                                   filled on Trade rows
    Bid Price, Bid Size, Ask Price, Ask Size        filled on Quote rows: the best price on each side

    python -m experiments.emini inspect PATH_TO_CSV
    python -m experiments.emini stats PATH_TO_CSV

`stats` computes the statistics of analysis/stylised.py in trade time, the same ones as for the model
(experiments/emini_compare.py), from regular trading hours (13:30-20:15 UTC) on the days given
(default 5 and 7 May 2010, leaving out the flash crash of 6 May). Each day is one segment. For every
trade the mid-price, spread and sizes at the best prices are those of the last quote before it.
Prices are converted to ticks of 0.25. Only the statistics are saved (results/emini/emini_stats.pkl).

`inspect` reads the whole file in chunks and prints, without showing any row: the contracts and row
types present, the date range and timestamp format, how often each field is empty, the tick size,
trade sizes, how often several trades share a timestamp (one large order sweeping several prices),
spreads and the depth at the best prices, and how the rows spread over the hours of the day. Its
output is meant to settle how the data is to be compared with the model (docs/project_plan.md).
"""

from __future__ import annotations

import argparse
import pickle
import re
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from analysis.stylised import stylised_facts, summary_rows

TICK = 0.25                                  # E-mini S&P 500 tick size, in index points (found by inspect)
DAYS = ("2010-05-05", "2010-05-07")
SESSION = ("13:30", "20:15")                 # regular trading hours in UTC (08:30-15:15 Chicago, in May)
STATS_OUT = Path("results/emini/emini_stats.pkl")
COLUMNS = ["#RIC", "Domain", "Date-Time", "Type", "Price", "Volume", "Bid Price", "Bid Size", "Ask Price", "Ask Size"]
NUMERIC = ["Price", "Volume", "Bid Price", "Bid Size", "Ask Price", "Ask Size"]
CHUNK = 1_000_000


def timestamp_pattern(text: str) -> str:
    """The shape of a timestamp with every digit replaced, e.g. '2026-09-01T13:30:00.123Z' ->
    'dddd-dd-ddTdd:dd:dd.dddZ', so the format can be reported without the values."""
    return re.sub(r"\d", "d", text)


class Summary:
    """Running totals over the chunks of the file."""

    def __init__(self):
        self.rows = 0
        self.by_ric = Counter()
        self.by_type = Counter()
        self.by_ric_type = Counter()
        self.domains = Counter()
        self.patterns = Counter()
        self.empty = {kind: Counter() for kind in ("Trade", "Quote")}
        self.typed_rows = Counter()
        self.first, self.last = None, None
        self.out_of_order = 0
        self.days = Counter()
        self.hours = Counter()
        self.prices = set()
        self.volumes = []
        self.same_time_trades = 0
        self.trade_steps = Counter()
        self.spreads = Counter()
        self.crossed = 0
        self.bid_sizes, self.ask_sizes = [], []
        self.last_trade = {}        # per contract: (timestamp text, price) of the last trade seen

    def add(self, chunk: pd.DataFrame) -> None:
        self.rows += len(chunk)
        self.by_ric.update(chunk["#RIC"].fillna("(empty)"))
        self.by_type.update(chunk["Type"].fillna("(empty)"))
        self.by_ric_type.update(zip(chunk["#RIC"].fillna("(empty)"), chunk["Type"].fillna("(empty)")))
        self.domains.update(chunk["Domain"].fillna("(empty)"))
        stamps = chunk["Date-Time"].dropna().astype(str)
        self.patterns.update(timestamp_pattern(s) for s in stamps.iloc[:: max(1, len(stamps) // 1000)])

        times = pd.to_datetime(chunk["Date-Time"], format="ISO8601", utc=True, errors="coerce")
        valid = times.dropna()
        if len(valid):
            self.first = valid.min() if self.first is None else min(self.first, valid.min())
            self.last = valid.max() if self.last is None else max(self.last, valid.max())
            self.out_of_order += int((valid.diff().dt.total_seconds() < 0).sum())
            self.days.update(valid.dt.strftime("%Y-%m-%d"))
            self.hours.update(valid.dt.hour)

        for kind in ("Trade", "Quote"):
            rows = chunk[chunk["Type"] == kind]
            self.typed_rows[kind] += len(rows)
            for column in NUMERIC:
                self.empty[kind][column] += int(rows[column].isna().sum())

        trades = chunk[chunk["Type"] == "Trade"].dropna(subset=["Price"])
        self.prices.update(np.round(trades["Price"].to_numpy(), 6))
        self.volumes.append(trades["Volume"].dropna().to_numpy())
        for ric, group in trades.groupby("#RIC", sort=False):
            stamp, price = group["Date-Time"].astype(str).to_numpy(), group["Price"].to_numpy()
            previous = self.last_trade.get(ric)
            if previous is not None:
                stamp, price = np.concatenate([[previous[0]], stamp]), np.concatenate([[previous[1]], price])
            self.same_time_trades += int((stamp[1:] == stamp[:-1]).sum())
            self.trade_steps.update(np.round(np.abs(np.diff(price)), 6))
            self.last_trade[ric] = (stamp[-1], price[-1])

        quotes = chunk[chunk["Type"] == "Quote"].dropna(subset=["Bid Price", "Ask Price"])
        self.prices.update(np.round(quotes["Bid Price"].to_numpy(), 6))
        self.prices.update(np.round(quotes["Ask Price"].to_numpy(), 6))
        spread = np.round((quotes["Ask Price"] - quotes["Bid Price"]).to_numpy(), 6)
        self.spreads.update(spread)
        self.crossed += int((spread <= 0).sum())
        self.bid_sizes.append(quotes["Bid Size"].dropna().to_numpy())
        self.ask_sizes.append(quotes["Ask Size"].dropna().to_numpy())

    def tick(self) -> float:
        """The smallest gap between two prices that occur: the tick size."""
        prices = np.sort(np.fromiter(self.prices, float))
        gaps = np.round(np.diff(prices), 6)
        gaps = gaps[gaps > 0]
        return float(gaps.min()) if len(gaps) else float("nan")


def share(part: int, whole: int) -> str:
    return f"{part / whole:.1%}" if whole else "-"


def quantiles(values: np.ndarray, label: str) -> str:
    if len(values) == 0:
        return f"{label}: none"
    q = np.percentile(values, [50, 90, 99])
    return (f"{label}: median {q[0]:g}, 90% below {q[1]:g}, 99% below {q[2]:g}, largest {values.max():g}, "
            f"mean {values.mean():.2f}")


def report(s: Summary, seconds: float) -> None:
    print(f"\n{s.rows:,} rows read in {seconds:.0f}s\n")
    print("Contracts (#RIC) and row types:")
    for ric, n in s.by_ric.most_common():
        types = ", ".join(f"{kind} {s.by_ric_type[(ric, kind)]:,}" for kind in s.by_type if s.by_ric_type[(ric, kind)])
        print(f"  {ric:12} {n:>12,} rows ({share(n, s.rows)})   {types}")
    print("Row types: " + ", ".join(f"{kind} {n:,} ({share(n, s.rows)})" for kind, n in s.by_type.most_common()))
    print("Domain: " + ", ".join(f"{d} {n:,}" for d, n in s.domains.most_common()))

    print("\nTimestamps:")
    sampled = sum(s.patterns.values())
    for pattern, n in s.patterns.most_common(3):
        digits = len(re.match(r"d*", pattern.split(".", 1)[1]).group()) if "." in pattern else 0
        print(f"  format {pattern}   ({digits} digits after the seconds; {share(n, sampled)} of rows sampled)")
    if s.first is not None:
        print(f"  from {s.first} to {s.last} (UTC), {len(s.days)} calendar days with data, "
              f"median {int(np.median(list(s.days.values()))):,} rows per day")
    print(f"  rows earlier than the row before: {s.out_of_order:,}")
    print("  rows per hour of the day (UTC): " + ", ".join(f"{h:02d}h {share(s.hours[h], s.rows)}" for h in range(24)))

    print("\nEmpty fields (share of the rows of that type):")
    for kind in ("Trade", "Quote"):
        n = s.typed_rows[kind]
        print(f"  {kind:5} rows: " + ", ".join(f"{c} {share(s.empty[kind][c], n)}" for c in NUMERIC))

    tick = s.tick()
    print(f"\nTick size (smallest gap between prices that occur): {tick:g}")
    volumes = np.concatenate(s.volumes) if s.volumes else np.empty(0)
    print("Trades:")
    print("  " + quantiles(volumes, "size (contracts)"))
    print(f"  trades with the same timestamp as the trade before (same contract): {s.same_time_trades:,} "
          f"({share(s.same_time_trades, len(volumes))})")
    steps = sum(s.trade_steps.values())
    if steps and np.isfinite(tick):
        moves = Counter()
        for gap, n in s.trade_steps.items():
            moves[min(int(round(gap / tick)), 4)] += n
        print("  price change from one trade to the next: " + ", ".join(
            f"{'4+' if k == 4 else k} tick{'s' if k != 1 else ''} {share(moves[k], steps)}" for k in range(5)))
    n_quotes = sum(s.spreads.values())
    print("Quotes:")
    if n_quotes and np.isfinite(tick):
        ticks = Counter()
        for gap, n in s.spreads.items():
            ticks[min(max(int(round(gap / tick)), 0), 4)] += n
        print("  spread: " + ", ".join(f"{'4+' if k == 4 else k} tick{'s' if k != 1 else ''} {share(ticks[k], n_quotes)}"
                                       for k in range(5)))
    print(f"  crossed or locked quotes (ask at or below bid): {s.crossed:,} ({share(s.crossed, n_quotes)})")
    for name, sizes in (("bid", s.bid_sizes), ("ask", s.ask_sizes)):
        print("  " + quantiles(np.concatenate(sizes) if sizes else np.empty(0), f"{name} size at the best price (contracts)"))
    others = {k: n for k, n in s.by_type.items() if k not in ("Trade", "Quote")}
    if others:
        print("\nOther row types (ignored by later analysis unless decided otherwise): "
              + ", ".join(f"{k} {n:,}" for k, n in others.items()))


def inspect(path: Path, max_rows: int | None = None) -> Summary:
    start = time.perf_counter()
    summary = Summary()
    reader = pd.read_csv(path, usecols=lambda c: c in COLUMNS, chunksize=CHUNK, nrows=max_rows,
                         dtype={"#RIC": "string", "Domain": "string", "Date-Time": "string", "Type": "string"})
    for count, chunk in enumerate(reader, 1):
        missing = [c for c in COLUMNS if c not in chunk.columns]
        if missing:
            raise SystemExit(f"Columns not found: {missing}. This script expects: {COLUMNS}")
        for column in NUMERIC:
            chunk[column] = pd.to_numeric(chunk[column], errors="coerce")
        summary.add(chunk)
        print(f"  {count * CHUNK:,} rows read..." if len(chunk) == CHUNK else "", end="\r" if len(chunk) == CHUNK else "",
              flush=True)
    report(summary, time.perf_counter() - start)
    return summary


QUOTE_FIELDS = ["Bid Price", "Bid Size", "Ask Price", "Ask Size"]


def trade_segments(path: Path, days=DAYS, session=SESSION, max_rows: int | None = None) -> list:
    """One segment per day (analysis/stylised.py): every trade in the session, with the last quote
    before it. Reads the file in chunks; the last quote is carried over from one chunk to the next."""
    parts = {day: [] for day in days}
    last_quote = pd.DataFrame([[np.nan] * 4], columns=QUOTE_FIELDS)
    reader = pd.read_csv(path, usecols=lambda c: c in COLUMNS, chunksize=CHUNK, nrows=max_rows,
                         dtype={"#RIC": "string", "Domain": "string", "Date-Time": "string", "Type": "string"})
    for chunk in reader:
        for column in NUMERIC:
            chunk[column] = pd.to_numeric(chunk[column], errors="coerce")
        is_quote = chunk["Type"] == "Quote"
        quotes = chunk[QUOTE_FIELDS].where(is_quote)
        # The quote in force at every row: the last quote row at or before it (carried over from the
        # previous chunk for the first rows). A trade row's own quote fields are empty, so it gets the
        # quote before it.
        filled = pd.concat([last_quote, quotes]).ffill().iloc[1:]
        filled.index = chunk.index
        if is_quote.any():
            last_quote = filled[is_quote].iloc[[-1]].reset_index(drop=True)
        trades = (chunk["Type"] == "Trade") & chunk["Price"].notna()
        if not trades.any():
            continue
        times = pd.to_datetime(chunk.loc[trades, "Date-Time"], format="ISO8601", utc=True)
        day = times.dt.strftime("%Y-%m-%d")
        clock = times.dt.strftime("%H:%M")
        keep = day.isin(days) & (clock >= session[0]) & (clock < session[1])
        if not keep.any():
            continue
        rows = chunk.loc[trades][keep.to_numpy()]
        q = filled.loc[rows.index]
        frame = pd.DataFrame({
            "day": day[keep].to_numpy(),
            "trade": rows["Price"].to_numpy() / TICK,
            "mid": (q["Bid Price"] + q["Ask Price"]).to_numpy() / 2 / TICK,
            "spread": (q["Ask Price"] - q["Bid Price"]).to_numpy() / TICK,
            "bid_size": q["Bid Size"].to_numpy(), "ask_size": q["Ask Size"].to_numpy(),
            "size": rows["Volume"].to_numpy()})
        for d, group in frame.groupby("day"):
            parts[d].append(group)
    segments = []
    for d in days:
        if not parts[d]:
            print(f"no trades found on {d} between {session[0]} and {session[1]} UTC")
            continue
        frame = pd.concat(parts[d])
        segment = {name: frame[name].to_numpy(dtype=float) for name in ("trade", "mid", "spread", "bid_size", "ask_size", "size")}
        segment["mid"] = pd.Series(segment["mid"]).ffill().bfill().to_numpy()    # before the session's first quote
        segments.append(segment)
        print(f"{d}: {len(frame):,} trades")
    return segments


def stats(path: Path, out: Path, days=DAYS, session=SESSION, max_rows: int | None = None) -> dict:
    start = time.perf_counter()
    segments = trade_segments(path, days, session, max_rows)
    if not segments:
        raise SystemExit("No trades in the chosen days and hours.")
    facts = stylised_facts(segments)
    facts["source"] = {"days": list(days), "session_utc": list(session), "tick": TICK,
                       "trades_per_day": [len(s["trade"]) for s in segments]}
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        pickle.dump(facts, f)
    print(f"\nE-mini, {', '.join(days)}, {session[0]}-{session[1]} UTC ({time.perf_counter() - start:.0f}s):")
    for label, value in summary_rows(facts):
        print(f"  {label:45} {value}")
    print(f"saved {out} (statistics only, no rows of the data)")
    return facts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect_cmd = commands.add_parser("inspect", help="summarise the file without showing any rows")
    stats_cmd = commands.add_parser("stats", help="statistics in trade time, to compare with the model")
    for sub in (inspect_cmd, stats_cmd):
        sub.add_argument("path", type=Path, help="the CSV file (kept outside the repository)")
        sub.add_argument("--max-rows", type=int, default=None, help="read only this many rows (for a quick look)")
    stats_cmd.add_argument("--days", nargs="+", default=list(DAYS), help="days to use, YYYY-MM-DD (default 5 and 7 May 2010)")
    stats_cmd.add_argument("--session", nargs=2, default=list(SESSION), metavar=("FROM", "TO"),
                           help="hours to use, HH:MM in UTC (default 13:30 20:15)")
    stats_cmd.add_argument("--out", type=Path, default=STATS_OUT)
    args = parser.parse_args(argv)
    if not args.path.exists():
        raise SystemExit(f"No such file: {args.path}")
    if args.command == "inspect":
        inspect(args.path, args.max_rows)
    else:
        stats(args.path, args.out, tuple(args.days), tuple(args.session), args.max_rows)


if __name__ == "__main__":
    main()
