#!/usr/bin/env python3
"""Fig 7 (simple): the classification pipeline as one left-to-right chain."""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

HERE = os.path.dirname(os.path.abspath(__file__))
SURFACE, INK, INK2, INK3 = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8880"
AMBER, GREEN, BLUE = "#eda100", "#1baf7a", "#2a78d6"
plt.rcParams.update({"figure.facecolor": SURFACE, "font.size": 10})

fig, ax = plt.subplots(figsize=(11.5, 4.6))
ax.set_xlim(0, 100); ax.set_ylim(0, 40); ax.axis("off")


def node(x, y, w, h, title, sub, fc="#ffffff", ec="#c9c6bd", lw=1.0):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                                boxstyle="round,pad=0.3,rounding_size=1", fc=fc, ec=ec, lw=lw, zorder=2))
    ax.text(x, y + (2.4 if sub else 0), title, ha="center", va="center", fontsize=10.5,
            fontweight="bold", color=INK, zorder=3)
    if sub:
        ax.text(x, y - 2.6, sub, ha="center", va="center", fontsize=8.5, color=INK2,
                zorder=3, linespacing=1.4)


def arr(x0, y0, x1, y1, label="", dy=1.8, ls="-", color=INK2):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=12,
                                 lw=1.3, color=color, ls=ls, zorder=1))
    if label:
        ax.text((x0 + x1) / 2, (y0 + y1) / 2 + dy, label, ha="center", va="bottom",
                fontsize=8.5, color=color, zorder=3)


Y = 24
# 1 receipts
node(9, Y, 16, 12, "exit receipts", "one row per process\nname · parent · exact CPU",
     fc="#eef6ff", ec=BLUE, lw=1.4)
# 2 tag
node(31, Y, 16, 12, "tag each process", "by name, fixed table\ncompile · test-run · search …")
arr(17.3, Y, 22.7, Y)
# 3 collapse
node(52, Y, 15, 12, "collapse", "BUILD / TEST / SEARCH")
arr(39.3, Y, 44.3, Y)
# 4 two views (stacked)
node(73, Y + 6.5, 17, 9, "process view", "each process → its own class",
     fc="#fff7e6", ec=AMBER, lw=1.4)
node(73, Y - 6.5, 17, 9, "ownership view", "each process → its nearest\ndriver ancestor's class",
     fc="#eaf7f1", ec=GREEN, lw=1.4)
arr(59.8, Y + 1.5, 64.3, Y + 5.5)
arr(59.8, Y - 1.5, 64.3, Y - 5.5)
# 5 label
node(93, Y, 12, 12, "label", "leader ≥ 10 pt\n→ B / T / S\nelse M")
arr(81.8, Y + 5.5, 86.8, Y + 1.5)
arr(81.8, Y - 5.5, 86.8, Y - 1.5)

# footnote row
ax.text(50, 6.5, "helper inputs:  container CPU total → coverage %   ·   2 Hz command log → full argv for long-lived processes (name alone can't tell `cargo test` from `cargo build`)",
        ha="center", fontsize=8.5, color=INK3)
ax.text(50, 3.0, "scaffold (bash, sleep) and unrecognised names never vote — they only lower the classified %",
        ha="center", fontsize=8.5, color=INK3)

ax.text(1, 37.5, "From receipts to a type label", fontsize=12.5, color=INK, fontweight="bold")
ax.text(1, 34.6, "only the receipts are recorded during the replay; everything after the first box runs offline and can be re-run",
        fontsize=8.5, color=INK2)
fig.subplots_adjust(left=0.01, right=0.99, top=0.98, bottom=0.02)
fig.savefig(f"{HERE}/fig7_flowchart.png", dpi=170)
print("wrote")
