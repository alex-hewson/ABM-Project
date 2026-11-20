"""Volatility with agent types of 1, 4 and 16 units: one figure for the progress summary.
Run from the project root: python experiments/evidence/make_types_figure.py"""

import pickle
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

R = Path("results")
N = 500
CASES = (("value_traders/side_basic_v0.pkl", "paper's agents\n(all 1 unit)", "k"),
         ("agent_types/types16_providers.pkl", "providers\n1/4/16", "C0"),
         ("agent_types/types16_takers.pkl", "takers\n1/4/16", "C2"),
         ("agent_types/types16_both.pkl", "both\n1/4/16", "C3"))


def load(path):
    with open(R / path, "rb") as f:
        return pickle.load(f)


def rms_at_200(data):
    edges = data["config"]["return_bin_edges"]["median"]
    counts = sum(r["return_counts"]["median"][200] for r in data["runs"] if r["n_agents"] == N)
    centres = np.sqrt(edges[:-1] * edges[1:])
    return float(np.sqrt((counts / counts.sum() * centres ** 2).sum()))


fig, (a, b) = plt.subplots(1, 2, figsize=(12, 4.6), gridspec_kw={"width_ratios": [1, 1.3]})
datas = [load(path) for path, _, _ in CASES]

values = [rms_at_200(d) for d in datas]
bars = a.bar(range(len(CASES)), values, color=[c for _, _, c in CASES], alpha=0.8)
for i, (bar, value) in enumerate(zip(bars, values)):
    text = f"{value:.1f}" if i == 0 else f"{value:.1f}\n(+{value / values[0] - 1:.0%})"
    a.text(bar.get_x() + bar.get_width() / 2, value + 0.4, text, ha="center", va="bottom", fontsize=9)
a.set_xticks(range(len(CASES)), [label for _, label, _ in CASES], fontsize=9)
a.set(ylabel="typical price move over 200 steps [ticks]", ylim=(0, max(values) * 1.25),
      title="(a) Size of price moves over 200 steps (RMS)")

for (path, label, colour), d in zip(CASES, datas):
    runs = [r for r in d["runs"] if r["n_agents"] == N]
    taus = runs[0]["taus"]
    rms = np.mean([r["rms"]["median"] for r in runs], axis=0)
    b.plot(taus, rms, color=colour, lw=1.2, label=label.replace("\n", " "))
b.set(xscale="log", yscale="log", xlabel="time lag Δτ [steps]", ylabel="RMS price change [ticks]",
      title="(b) Size of price moves at every time lag")
b.legend(fontsize=9)
for ax in (a, b):
    ax.title.set_fontsize(10)

fig.suptitle("Fig. 1. Larger, slower agents make the price more volatile\n(N$_A$ = 500, no value traders; agents split "
             "equally between 1 unit every step, 4 units every 4 steps and 16 units every 16 steps;\n"
             "mean of 8 runs of 100,000 steps each)", fontsize=10)
fig.tight_layout()
out = R / "evidence" / "agent_types_volatility.png"
fig.savefig(out, dpi=130)
print(f"saved {out}")
