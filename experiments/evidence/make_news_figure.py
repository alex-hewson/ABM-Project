"""News event study with jumps of three sizes: one figure for the progress summary.
Run from the project root: python experiments/evidence/make_news_figure.py"""

import pickle
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

R = Path("results")
CASES = (("news/value50_jump10.pkl", "jumps of about 10 ticks", "C0"),
         ("news/value50.pkl", "jumps of about 30 ticks", "C1"),
         ("news/value50_jump100.pkl", "jumps of about 100 ticks", "C3"))

fig, ax = plt.subplots(figsize=(9, 5.2))
for path, label, colour in CASES:
    with open(R / path, "rb") as f:
        d = pickle.load(f)
    t = d["t"]
    mean, err = d["means"]["gap"] + (t >= 0), d["errors"]["gap"]
    ax.plot(t, mean, color=colour, lw=1.1,
            label=f"{label} ({d['n_used']} jumps from {d['config']['n_runs']} runs)")
    ax.fill_between(t, mean - err, mean + err, color=colour, alpha=0.2, lw=0)
ax.axhline(1, color="gray", lw=0.6, ls=":")
ax.axhline(0, color="gray", lw=0.6, ls=":")
ax.axvline(0, color="gray", lw=0.6, ls=":")
ax.set(xlim=(-100, 1500), xlabel="steps since the news", ylabel="share of the jump taken into the price")
ax.set_title("Fig. 3. News event study: the price moves to the new true value after every jump\n"
             "(250 agents, 50 value traders with a mean error of 50 ticks; each run 50,000 steps;\n"
             "the price around every jump lined up and averaged; shaded = ± 1 standard error)", fontsize=10)
ax.legend(fontsize=9, loc="lower right")
fig.tight_layout()
out = R / "evidence" / "news_event_study.png"
fig.savefig(out, dpi=130)
print(f"saved {out}")
