"""Recovery speed against the density of value traders, from the value trader sweep: one figure for
the progress summary. Run from the project root: python experiments/evidence/make_value_figure.py"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from experiments import value_sweep

R = Path("results")
rows = [r for r in csv.DictReader(open(R / "value_sweep" / "summary.csv")) if float(r["fraction"]) > 0]

fig, ax = plt.subplots(figsize=(8.5, 5.8))
xs, ys = [], []
for step, colour in zip(value_sweep.NEWS, ("C0", "C1", "C2", "C3")):
    for size, marker in ((300, "o"), (150, "^")):
        pts = [(float(r["fraction"]) / float(r["spread"]), float(r[f"half_life_{size}"]))
               for r in rows if float(r["news"]) == step and r[f"half_life_{size}"] not in ("", "None")]
        if pts:
            x, y = zip(*pts)
            ax.scatter(x, y, c=colour, marker=marker, s=30, alpha=0.8,
                       label=f"true value step {step:g}, {size}-unit sell")
            xs += x
            ys += y
slope, intercept = np.polyfit(np.log(xs), np.log(ys), 1)
grid_x = np.logspace(np.log10(min(xs)), np.log10(max(xs)), 50)
ax.plot(grid_x, np.exp(intercept) * grid_x ** slope, "k--", lw=1, label=f"fit: half-life ∝ (share / error)$^{{{slope:.2f}}}$")
ax.set(xscale="log", yscale="log", xlabel="share of value traders ÷ their mean error [per tick]",
       ylabel="price half-life after the sell [steps]")
ax.set_title("Fig. 3. Recovery is faster the more value traders sit close to the true value\n"
             "(250 agents; value trader sweep: shares 2–20%, mean errors 50–500 ticks, true value steps 0.25–2;\n"
             "each point the mean of 200 runs; settings that never recovered within 2,000 steps are left out)",
             fontsize=10)
ax.legend(fontsize=7, ncol=2)
fig.tight_layout()
out = R / "evidence" / "value_traders_recovery.png"
fig.savefig(out, dpi=130)
print(f"saved {out} (slope {slope:.2f} over {len(xs)} points)")
