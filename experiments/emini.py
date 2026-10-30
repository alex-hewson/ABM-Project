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

`inspect` reads the whole file in chunks and prints, without showing any row: the contracts and row
types present, the date range and timestamp format, how often each field is empty, the tick size,
trade sizes, how often several trades share a timestamp (one large order sweeping several prices),
spreads and the depth at the best prices, and how the rows spread over the hours of the day. Its
output is meant to settle how the data is to be compared with the model (docs/project_plan.md).
"""

from __future__ import annotations

import argparse
import re
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect_cmd = commands.add_parser("inspect", help="summarise the file without showing any rows")
    inspect_cmd.add_argument("path", type=Path, help="the CSV file (kept outside the repository)")
    inspect_cmd.add_argument("--max-rows", type=int, default=None, help="read only this many rows (for a quick look)")
    args = parser.parse_args(argv)
    if not args.path.exists():
        raise SystemExit(f"No such file: {args.path}")
    inspect(args.path, args.max_rows)


if __name__ == "__main__":
    main()
