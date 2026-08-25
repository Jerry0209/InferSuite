#!/usr/bin/env python3
"""Fig 9 — the replay-invalid gate, with every row's cause. Replay fence vs live fence
(log-log) over the full 300-row census: rows inside the [0.5, 2] ratio band are valid
(grey); the 28 outside are colored by the diagnosed cause from
local_agents/ML_typeid/replay_invalid_report.tsv (typeid_replay_invalid_report.py)."""
import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.expanduser("~/InferSuite")
ML = f"{REPO}/local_agents/ML_typeid"
SURFACE, INK, INK2 = "#fcfcfb", "#0b0b0b", "#52514e"
plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "font.size": 10,
                     "text.color": INK, "xtick.color": INK2, "ytick.color": INK2})

CCOL = {"gradle-wrapper-offline": "#D55E00",
        "background-dominated": "#0072B2",
        "drain-cap-background": "#6b4fa0"}
CLAB = {"gradle-wrapper-offline": "gradle wrapper download fails offline (7 lucene) — tests never ran",
        "background-dominated": "live fence = leaked-server background burn over model-wait wall (8)",
        "drain-cap-background": "replay pinned at the 2400 s drain cap on a tiny live fence (13)"}

inv = {r["instance"]: r for r in csv.DictReader(open(f"{ML}/replay_invalid_report.tsv"), delimiter="\t")}
rows = list(csv.DictReader(open(f"{ML}/cpu_matrix.tsv"), delimiter="\t"))

fig, ax = plt.subplots(figsize=(8.6, 7.2))
lo, hi = 0.3, 4000
xs = np.geomspace(lo, hi, 10)
ax.fill_between(xs, xs * 0.5, xs * 2, color="#e8ecdf", alpha=0.8, zorder=0,
                label="valid band: replay/live ∈ [0.5, 2]")
ax.plot(xs, xs, color="#b8b8ae", lw=0.9, zorder=1)

vx, vy = [], []
for r in rows:
    try:
        rep, ratio = float(r["fence"]), float(r["live_ratio"])
    except ValueError:
        continue
    if ratio <= 0 or rep <= 0:
        continue
    live = rep / ratio
    if r["instance"] in inv:
        c = inv[r["instance"]]["cause"]
        ax.scatter(live, rep, s=42, color=CCOL.get(c, "#999"), zorder=3,
                   edgecolor="white", linewidth=0.6)
    else:
        vx.append(live); vy.append(rep)
ax.scatter(vx, vy, s=12, color="#9aa8a2", alpha=0.45, zorder=2, linewidth=0)

for inst, short in (("apache__lucene-12626", "lucene-12626"),
                    ("caddyserver__caddy-6350", "caddy-6350"),
                    ("php-cs-fixer__php-cs-fixer-8367", "php-cs-fixer-8367")):
    if inst in inv:
        o = inv[inst]
        ax.annotate(short, (float(o["live_fence_cs"]), float(o["replay_fence_cs"])),
                    textcoords="offset points", xytext=(8, -3), fontsize=8, color=INK2)

handles = [plt.Line2D([], [], marker="o", ls="", color=CCOL[k], markersize=7,
                      label=CLAB[k]) for k in CCOL]
handles.append(plt.Line2D([], [], marker="o", ls="", color="#9aa8a2", alpha=0.6,
                          markersize=5, label="valid rows (272)"))
ax.legend(handles=handles, fontsize=8.2, loc="upper left", frameon=False)
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xlim(lo, hi); ax.set_ylim(lo, hi)
ax.set_xlabel("live tool fence (core-s)")
ax.set_ylabel("replay tool fence (core-s)")
ax.grid(True, which="both", color="#e4e2da", lw=0.5)
fig.text(0.02, 0.975, "The replay-invalid gate: every excluded row has a measured cause",
         fontsize=12.5, color=INK, ha="left", va="top")
fig.text(0.02, 0.935,
         "300 census replays · shaded = valid ratio band · fence = action CPU + background rate × wall, so a leaked\n"
         "process makes the fence follow the wall: replays compress it (below band) or stretch it to the drain cap (above)",
         fontsize=8.5, color=INK2, ha="left", va="top")
fig.subplots_adjust(left=0.10, right=0.97, top=0.86, bottom=0.08)
fig.savefig(f"{HERE}/09_replay_invalid_causes.png", dpi=170)
print("wrote 09_replay_invalid_causes.png")
