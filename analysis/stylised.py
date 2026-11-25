"""
Statistics of a market in trade time, computed the same way for the model and for real data
(docs/decisions.md, D37), so that any difference between them comes from the markets, not the code.

The input is a list of segments: stretches with no gap inside them (one model run, or one trading
session of real data). Changes and autocorrelations are taken within a segment, never across a gap.
Each segment is a dict of arrays with one entry per trade, in order:

    trade       the trade price, in ticks
    mid         the mid-price just before the trade, in ticks
    spread      the spread just before the trade, in ticks
    bid_size    units resting at the best bid just before the trade
    ask_size    units resting at the best ask just before the trade
    size        the trade's size in units (optional)
    time        the trade's timestamp (optional; real data), used only to merge the fills of one order

Time is counted in trades: a lag of 10 is ten trades later.
"""

from __future__ import annotations

from typing import Dict, List, Sequence

import numpy as np

from analysis.autocorr import change_autocorrelations
from analysis.hurst import local_slopes, log_spaced_taus

LAGS = np.array(log_spaced_taus(1, 20_000, 40))        # lags for the RMS change and H, in trades
KURTOSIS_LAGS = (1, 10, 100, 1000)
TAIL_LAGS = (10, 100, 1000)
TAIL_LEVELS = np.logspace(-1, np.log10(30), 40)        # |change| in units of its standard deviation
AUTOCORR = {1: 20, 100: 50}                            # interval in trades: number of lags
PRICES = ("trade", "mid")
# The price that model and data are compared on (D37): the mid-price. The trade price jumps back and
# forth between bid and ask (the bid-ask bounce), which adds a reversal that is not a move of the
# price itself, so it is kept only to measure that bounce.
PRICE = "mid"
# Lags for the autocorrelation of trade signs (buy +1, sell -1), in trades.
SIGN_LAGS = np.unique(np.round(np.logspace(0, 4, 33)).astype(int))
SIGN_FIT = (10, 1000)                                  # lags over which the power-law exponent is fitted


def trade_signs(segment: Dict[str, np.ndarray]) -> np.ndarray:
    """+1 for a trade above the mid-price in force just before it (a buy hitting the ask), -1 below it
    (a sell hitting the bid), 0 at the mid-price or with no mid-price, where the side cannot be told."""
    s = np.sign(segment["trade"] - segment["mid"])
    return np.nan_to_num(s, nan=0.0)


def first_fills(segment: Dict[str, np.ndarray]) -> np.ndarray:
    """True for the first fill of each order: a run of fills that share a timestamp and a side is one
    market order that took out several resting orders (real data). Without "time" (the model, where
    every order is one fill) every fill is an order."""
    s = trade_signs(segment)
    keep = np.ones(len(s), dtype=bool)
    if "time" in segment and len(s) > 1:
        t = segment["time"]
        keep[1:] = ~((t[1:] == t[:-1]) & (s[1:] == s[:-1]) & (s[1:] != 0))
    return keep


def order_signs(segment: Dict[str, np.ndarray]) -> np.ndarray:
    """The trade signs with the fills of one order counted once (see first_fills)."""
    return trade_signs(segment)[first_fills(segment)]


def as_orders(segment: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
    """The segment with only the first fill of each order: its trade price, and the mid-price just
    before the order (D41)."""
    keep = first_fills(segment)
    return {"trade": segment["trade"][keep], "mid": segment["mid"][keep]}


def mid_move_stats(segments: Sequence[Dict[str, np.ndarray]]) -> dict:
    """How the mid-price moves from trade to trade (D44): of the trades, the share after which the
    mid-price has changed; of those changes, the share of half a tick (one side of the spread moving),
    the share followed by a change the other way, and the share exactly undone by the next change
    (flicker: e.g. the best level empties and refills), with the median number of trades between a
    change and the next one, for all changes and for undone ones. Within segments only."""
    n_trades = n_moves = half = reversed_ = undone = 0
    gaps_all, gaps_undone = [], []
    for seg in segments:
        m = np.asarray(seg["mid"], dtype=float)
        d = np.diff(m)
        ok = np.isfinite(d)
        n_trades += int(ok.sum())
        idx = np.flatnonzero(ok & (d != 0))
        moves = d[idx]
        n_moves += len(moves)
        half += int(np.sum(np.isclose(np.abs(moves), 0.5)))
        if len(moves) > 1:
            back = np.sign(moves[1:]) == -np.sign(moves[:-1])
            exact = np.isclose(moves[1:], -moves[:-1])
            gaps = idx[1:] - idx[:-1]
            reversed_ += int(back.sum())
            undone += int(exact.sum())
            gaps_all.append(gaps)
            gaps_undone.append(gaps[exact])
    pairs = max(n_moves - len(segments), 1)
    all_gaps = np.concatenate(gaps_all) if gaps_all else np.empty(0)
    undone_gaps = np.concatenate(gaps_undone) if gaps_undone else np.empty(0)
    return {"share_of_trades": n_moves / n_trades if n_trades else float("nan"),
            "half_tick": half / n_moves if n_moves else float("nan"),
            "reversed": reversed_ / pairs, "undone": undone / pairs,
            "gap_median": float(np.median(all_gaps)) if len(all_gaps) else float("nan"),
            "gap_median_undone": float(np.median(undone_gaps)) if len(undone_gaps) else float("nan")}


def response_function(segments: Sequence[Dict[str, np.ndarray]], lags=SIGN_LAGS) -> np.ndarray:
    """R(l) = <(m_(n+l) - m_n) * s_n>: how far the mid-price has moved, on average, l trades after a
    trade, in the direction of that trade, in ticks (Bouchaud, Gefen, Potters and Wyart 2004, Eq. 3).
    m_n is the mid-price just before trade n and s_n its sign; pairs stay within a segment."""
    total, count = np.zeros(len(lags)), np.zeros(len(lags))
    for seg in segments:
        s, m = trade_signs(seg), np.asarray(seg["mid"], dtype=float)
        for i, lag in enumerate(lags):
            if len(m) > lag:
                moves = (m[lag:] - m[:-lag]) * s[:-lag]
                ok = np.isfinite(moves)
                total[i] += moves[ok].sum()
                count[i] += ok.sum()
    return np.where(count > 0, total / np.maximum(count, 1), np.nan)


def sign_autocorrelation(segments: Sequence[Dict[str, np.ndarray]], lags=SIGN_LAGS, signs=trade_signs) -> np.ndarray:
    """Autocorrelation of trade signs at each lag, within segments (never across a gap), pooled over
    segments weighted by the number of pairs. Each segment's own mean sign is subtracted. signs is the
    function giving one segment's signs (trade_signs, or order_signs to merge fills of one order)."""
    max_lag = int(max(lags))
    num, pairs = np.zeros(max_lag + 1), np.zeros(max_lag + 1)
    for seg in segments:
        s = signs(seg)
        n = len(s)
        if n <= max_lag:
            continue
        s = s - s.mean()
        f = np.fft.rfft(s, 2 * n)
        products = np.fft.irfft(f * np.conj(f))[: max_lag + 1]      # sum of s_i * s_(i+lag) for each lag
        num += products
        pairs += n - np.arange(max_lag + 1)
    if pairs[0] == 0 or num[0] == 0:
        return np.full(len(lags), np.nan)
    c = (num / pairs) / (num[0] / pairs[0])
    return c[np.asarray(lags)]


def power_law_exponent(lags, values, fit=SIGN_FIT) -> float:
    """gamma in values ~ lag^(-gamma), from a straight line through log value against log lag over the
    fit range, using only positive values. NaN if fewer than 3 points are usable."""
    lags, values = np.asarray(lags, dtype=float), np.asarray(values, dtype=float)
    ok = (lags >= fit[0]) & (lags <= fit[1]) & np.isfinite(values) & (values > 0)
    if ok.sum() < 3:
        return float("nan")
    slope = np.polyfit(np.log(lags[ok]), np.log(values[ok]), 1)[0]
    return float(-slope)


def changes(segments: Sequence[Dict[str, np.ndarray]], kind: str, lag: int) -> np.ndarray:
    """Every change over `lag` trades, from every segment long enough (overlapping, as for H)."""
    parts = [s[kind][lag:] - s[kind][:-lag] for s in segments if len(s[kind]) > lag]
    return np.concatenate(parts) if parts else np.empty(0)


def kurtosis(x: np.ndarray) -> float:
    """Fourth moment over the squared second, about the mean: 3 for a normal distribution."""
    if len(x) < 4:
        return float("nan")
    d = x - x.mean()
    m2 = np.mean(d ** 2)
    return float(np.mean(d ** 4) / m2 ** 2) if m2 > 0 else float("nan")


def tail(x: np.ndarray) -> np.ndarray:
    """Share of |change| at or above each of TAIL_LEVELS standard deviations."""
    if len(x) == 0 or x.std() == 0:
        return np.full(len(TAIL_LEVELS), np.nan)
    sd = x.std()
    a = np.sort(np.abs(x - x.mean()) / sd)
    return 1.0 - np.searchsorted(a, TAIL_LEVELS, side="left") / len(a)


def mean_autocorrelation(segments, kind: str, interval: int, n_lags: int) -> Dict[str, np.ndarray]:
    """Autocorrelation of the signed and absolute changes over `interval` trades at lags 1 to n_lags,
    computed in each segment and averaged, weighted by the number of changes in it."""
    sums = {"signed": np.zeros(n_lags), "absolute": np.zeros(n_lags)}
    weight = 0
    for s in segments:
        n_changes = len(s[kind]) // interval - 1
        if n_changes <= 4 * n_lags:                  # too short for this many lags
            continue
        ac = change_autocorrelations(s[kind], interval, n_lags)
        for name in sums:
            sums[name] += np.nan_to_num(ac[name]) * n_changes
        weight += n_changes
    return {name: (total / weight if weight else np.full(n_lags, np.nan)) for name, total in sums.items()}


def stylised_facts(segments: Sequence[Dict[str, np.ndarray]]) -> dict:
    """All the statistics, as a dict of numbers and small arrays (never the series themselves)."""
    out: dict = {"n_trades": int(sum(len(s["trade"]) for s in segments)), "n_segments": len(segments),
                 "lags": LAGS, "tail_levels": TAIL_LEVELS}
    for kind in PRICES:
        rms = np.array([np.sqrt(np.mean(c ** 2)) if len(c := changes(segments, kind, lag)) else np.nan
                        for lag in LAGS])
        ok = np.isfinite(rms) & (rms > 0)
        hurst = np.full(len(LAGS), np.nan)
        if ok.sum() >= 2:
            hurst[ok] = local_slopes(LAGS[ok], rms[ok])
        out[kind] = {
            "rms": rms,
            "hurst": hurst,
            "kurtosis": {lag: kurtosis(changes(segments, kind, lag)) for lag in KURTOSIS_LAGS},
            "tail": {lag: tail(changes(segments, kind, lag)) for lag in TAIL_LAGS},
            "autocorr": {interval: mean_autocorrelation(segments, kind, interval, n)
                         for interval, n in AUTOCORR.items()},
            "zero_steps": float(np.mean(changes(segments, kind, 1) == 0)),     # share of trades with no price change
        }
    spread = np.concatenate([s["spread"] for s in segments])
    spread = spread[np.isfinite(spread)]
    ticks = np.clip(np.round(spread).astype(int), 0, 4)
    out["spread"] = {"mean": float(spread.mean()), "shares": [float(np.mean(ticks == k)) for k in range(5)]}
    best = np.concatenate([np.concatenate([s["bid_size"], s["ask_size"]]) for s in segments])
    best = best[np.isfinite(best)]
    out["best_size"] = {"mean": float(best.mean()),
                        "quantiles": {q: float(np.percentile(best, q)) for q in (10, 50, 90, 99)}}
    if all("size" in s for s in segments):
        sizes = np.concatenate([s["size"] for s in segments])
        sizes = sizes[np.isfinite(sizes)]
        out["trade_size"] = {"mean": float(sizes.mean()), "median": float(np.median(sizes)),
                             "per_best_size": float(np.median(sizes) / np.median(best))}
    signs = np.concatenate([trade_signs(s) for s in segments])
    ac = sign_autocorrelation(segments)
    out["signs"] = {"lags": SIGN_LAGS, "autocorr": ac, "gamma": power_law_exponent(SIGN_LAGS, ac),
                    "share_buy": float(np.mean(signs > 0)), "share_unknown": float(np.mean(signs == 0))}
    if all("time" in s for s in segments):              # real data: also with the fills of one order merged
        ac = sign_autocorrelation(segments, signs=order_signs)
        n_orders = sum(len(order_signs(s)) for s in segments)
        out["signs"]["orders"] = {"autocorr": ac, "gamma": power_law_exponent(SIGN_LAGS, ac),
                                  "fills_per_order": float(len(signs) / n_orders) if n_orders else float("nan")}
    out["response"] = {"lags": SIGN_LAGS, "per_trade": response_function(segments)}
    out["mid_moves"] = mid_move_stats(segments)
    if all("time" in s for s in segments):              # real data: also per order, fills merged
        out["response"]["per_order"] = response_function([as_orders(s) for s in segments])
    return out


def summary_rows(facts: dict) -> List[tuple]:
    """(label, value) pairs for a side-by-side table. Price statistics are of the mid-price (PRICE, D37),
    except the bid-ask bounce, which only the trade price has."""
    t = facts[PRICE]
    rows = [("trades", f"{facts['n_trades']:,}"),
            ("trades with no mid-price change", f"{t['zero_steps']:.0%}"),
            ("trades with no trade-price change", f"{facts['trade']['zero_steps']:.0%}"),
            ("mean spread (ticks)", f"{facts['spread']['mean']:.2f}"),
            ("spread of 1 tick", f"{facts['spread']['shares'][1]:.0%}"),
            ("median units at best price", f"{facts['best_size']['quantiles'][50]:g}")]
    if "trade_size" in facts:
        rows.append(("median trade / median best size", f"{facts['trade_size']['per_best_size']:.3f}"))
    for lag in KURTOSIS_LAGS:
        rows.append((f"kurtosis, {lag}-trade mid changes", f"{t['kurtosis'][lag]:.1f}"))
    i = list(LAGS).index(min(LAGS, key=lambda x: abs(x - 1000)))
    j = list(LAGS).index(min(LAGS, key=lambda x: abs(x - 10)))
    rows += [("H at 10 trades", f"{t['hurst'][j]:.2f}"), ("H at 1000 trades", f"{t['hurst'][i]:.2f}"),
             ("autocorr. of trade-to-trade mid changes, lag 1", f"{t['autocorr'][1]['signed'][0]:+.2f}"),
             ("bid-ask bounce (trade price, lag 1)", f"{facts['trade']['autocorr'][1]['signed'][0]:+.2f}"),
             ("autocorr. of 100-trade mid changes, lag 1", f"{t['autocorr'][100]['signed'][0]:+.2f}"),
             ("autocorr. of |100-trade mid changes|, lag 1", f"{t['autocorr'][100]['absolute'][0]:+.2f}"),
             ("autocorr. of |100-trade mid changes|, lag 10", f"{t['autocorr'][100]['absolute'][9]:+.2f}")]
    if "signs" in facts:                                  # files made before the sign statistic lack it
        g = facts["signs"]
        lags = list(g["lags"])
        for lag in (1, 10, 100, 1000):
            rows.append((f"autocorr. of trade signs, lag {lag}", f"{g['autocorr'][lags.index(lag)]:+.3f}"))
        rows += [(f"power-law exponent of sign autocorr. ({SIGN_FIT[0]}-{SIGN_FIT[1]} trades)", f"{g['gamma']:.2f}"),
                 ("trades whose side cannot be told (at the mid)", f"{g['share_unknown']:.1%}")]
        if "mid_moves" in facts:
            mm = facts["mid_moves"]
            rows += [("mid-price changes: half a tick", f"{mm['half_tick']:.0%}"),
                     ("mid-price changes: next change the other way", f"{mm['reversed']:.0%}"),
                     ("mid-price changes: exactly undone by the next", f"{mm['undone']:.0%}"),
                     ("trades between changes (median: all / undone)", f"{mm['gap_median']:g} / {mm['gap_median_undone']:g}")]
        if "response" in facts:
            rows += response_rows(facts["response"]["per_trade"], "response R(l), ticks")
            if "per_order" in facts["response"]:
                rows += response_rows(facts["response"]["per_order"], "same, fills of one order merged")
        if "orders" in g:
            o = g["orders"]
            for lag in (1, 10, 100, 1000):
                rows.append((f"same, fills of one order merged, lag {lag}", f"{o['autocorr'][lags.index(lag)]:+.3f}"))
            rows += [("same, fills of one order merged: exponent", f"{o['gamma']:.2f}"),
                     ("fills per order (same time and side)", f"{o['fills_per_order']:.2f}")]
    return rows


def response_rows(r: np.ndarray, label: str) -> List[tuple]:
    """R at a few lags, and where it peaks, for the summary table."""
    lags = list(SIGN_LAGS)
    rows = [(f"{label}, lag {lag}", f"{r[lags.index(lag)]:+.3f}") for lag in (1, 10, 100, 1000, 10000)]
    if np.isfinite(r).any():
        peak = int(np.nanargmax(r))
        rows.append((f"{label}: largest", f"{r[peak]:+.3f} at lag {lags[peak]}"))
    return rows
