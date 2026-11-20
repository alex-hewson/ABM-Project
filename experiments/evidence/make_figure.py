"""News against a large order, with and without momentum traders: one figure for the progress summary.
Run from the project root: python experiments/evidence/make_figure.py"""

import pickle
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

R = Path("results")


def load(path):
    with open(R / path, "rb") as f:
        return pickle.load(f)


fig, (a, b) = plt.subplots(1, 2, figsize=(13, 4.8))

for path, label, colour in (("news/value50.pkl", "value traders", "C0"),
                            ("news/value50_mom100.pkl", "value + momentum traders", "C1")):
    d = load(path)
    t = d["t"]
    mean, err = d["means"]["gap"] + (t >= 0), d["errors"]["gap"]
    a.plot(t, mean, color=colour, lw=1, label=label)
    a.fill_between(t, mean - err, mean + err, color=colour, alpha=0.2, lw=0)
a.axhline(1, color="gray", lw=0.6, ls=":")
a.axhline(0, color="gray", lw=0.6, ls=":")
a.axvline(0, color="gray", lw=0.6, ls=":")
a.set(title="(a) News: the true value jumps (405 jumps of about 30 ticks)", xlim=(-100, 1000),
      xlabel="steps since the news", ylabel="share of the jump taken into the price")
a.legend(fontsize=9, loc="lower right")

for path, label, colour in (("pressure/plain.pkl", "paper's agents only (plain price)", "k"),
                            ("pressure/value50.pkl", "value traders", "C0"),
                            ("pressure/value50_mom100.pkl", "value + momentum traders", "C1")):
    d = load(path)
    band = d["bands"]["150-400"]
    t = d["t"]
    b.plot(t, band["mean"], color=colour, lw=1, label=label)
    b.fill_between(t, band["mean"] - band["error"], band["mean"] + band["error"], color=colour, alpha=0.2, lw=0)
b.axhline(0, color="gray", lw=0.6, ls=":")
b.axvline(0, color="gray", lw=0.6, ls=":")
b.set(title="(b) Pressure: a large sell order, no new information (153 orders of 150-400 units)", xlim=(-100, 1000),
      xlabel="steps since the order", ylabel="price change relative to the true value [ticks]")
b.legend(fontsize=9, loc="lower right")
for ax in (a, b):
    ax.title.set_fontsize(10)

fig.suptitle("Fig. 2. Recovery after news and after a large order (250 agents; 50 value traders; 100 momentum traders "
             "following the slope of the last 50 prices; shaded = ± 1 standard error)", fontsize=10)
fig.tight_layout()
out = R / "evidence" / "news_vs_pressure.png"
fig.savefig(out, dpi=130)
print(f"saved {out}")
