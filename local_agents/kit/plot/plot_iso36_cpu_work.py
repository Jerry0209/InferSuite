#!/usr/bin/env python3
"""plot_iso36_cpu_work.py — "CPU work is tool-heavy, but not always" rebuilt over the 36
count-view picks: per-task core-seconds by fence (tool vs harness), from the ML_iso36
matched-configuration replays.

Replays never call the model, so there is no inference wedge and no litellm wedge — the
two fences are the whole story, and core-seconds are exact cgroup cpu.stat accounting.
Each task has NINE replay episodes (one per counter group); the bar shows the per-fence
MEDIAN across them (runs are never pooled), and the per-episode min-max is banked in the
values JSON. Fence usage is summed over positive cpu.stat increments (the tool cgroup is
recreated when the container turns over, so last-minus-first can read low).

    /home/thu/miniforge3/envs/infersuite-full/bin/python local_agents/kit/plot/plot_iso36_cpu_work.py
"""
from __future__ import annotations

import collections
import csv
import glob
import json
import os
import statistics as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

REPO = os.path.expanduser("~/InferSuite")
DATA = f"{REPO}/local_agents/ML_iso36/data"
OUT = f"{REPO}/local_agents/ML_iso36/plots"
SEL = f"{REPO}/local_agents/ML_typeid/selection_36_count.tsv"

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["DejaVu Serif"], "mathtext.fontset": "dejavuserif",
    "font.size": 11, "figure.dpi": 150, "savefig.dpi": 300, "savefig.bbox": "tight",
    "axes.grid": True, "grid.color": "#cccccc", "grid.linewidth": 0.5, "grid.alpha": 0.6,
    "axes.axisbelow": True,
})
C_TOOL, C_HARN = "#159f77", "#6a51a3"          # locked cross-figure fence colors
LANGS = ["C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript"]


def fence_core_s(rd, i):
    """Core-seconds of scope i over the episode, reset-safe (sum of positive increments)."""
    prev, used = None, 0.0
    try:
        for ln in open(f"{rd}/cpustat_scope{i}.tsv"):
            p = ln.split()
            if len(p) >= 3 and p[1] == "usage_usec":
                u = float(p[2])
                if prev is not None and u > prev:
                    used += u - prev
                prev = u
    except OSError:
        return None
    return used / 1e6 if prev is not None else None


sel = [r for r in csv.DictReader(open(SEL), delimiter="\t") if "__" in r.get("instance", "")]
by_lang = collections.defaultdict(list)
for r in sel:
    r["disp"] = r["instance"].split("__", 1)[1]
    by_lang[r["lang"]].append(r)

rows, values = [], {}
for lang in LANGS:
    for r in by_lang[lang]:
        tools, harns = [], []
        for rd in sorted(glob.glob(f"{DATA}/glm_replay_swe_{r['short']}/run_*")):
            t, h = fence_core_s(rd, 2), fence_core_s(rd, 1)
            if t and t > 0:
                tools.append(t)
            if h and h > 0:
                harns.append(h)
        if not tools:
            continue
        t_med, h_med = st.median(tools), (st.median(harns) if harns else 0.0)
        rows.append((r["disp"], lang, r["label"], t_med, h_med))
        values[r["short"]] = {"language": lang, "cell": r["label"], "n_episodes": len(tools),
                              "tool_core_s_median": round(t_med, 1),
                              "tool_core_s_min": round(min(tools), 1),
                              "tool_core_s_max": round(max(tools), 1),
                              "harness_core_s_median": round(h_med, 1),
                              "harness_core_s_min": round(min(harns), 1) if harns else 0,
                              "harness_core_s_max": round(max(harns), 1) if harns else 0}

# ---- layout: one bar per task, grouped by language ----
GAP = 1.6
ys, ylab, seps = [], [], []
y = 0.0
lang_at = {}
for lang in LANGS:
    y0 = y
    for r in rows:
        pass
    for disp, lg, cell, t, h in [x for x in rows if x[1] == lang]:
        ys.append(y); ylab.append(f"{disp} ({cell})")
        y += 1.0
    lang_at[lang] = (y0, y - 1.0)
    seps.append(y - 1.0 + (GAP + 1.0) / 2)
    y += GAP

fig, ax = plt.subplots(figsize=(11.5, 0.30 * len(rows) + 4.2))
order = [x for lang in LANGS for x in rows if x[1] == lang]
T = np.array([x[3] for x in order])
H = np.array([x[4] for x in order])
Y = np.array(ys)
ax.barh(Y, T, color=C_TOOL, height=0.72, label="Tool execution")
ax.barh(Y, H, left=T, color=C_HARN, height=0.72, label="Agent harness")
xmax = float((T + H).max())
for yy, t, h in zip(Y, T, H):
    tot = t + h
    ax.text(tot + xmax * 0.012, yy, f"{tot:,.0f}   ({100 * t / tot:.0f}% tools)",
            va="center", fontsize=8.2)
for lang in LANGS:
    lo, hi = lang_at[lang]
    ax.text(-0.155, (lo + hi) / 2, lang, transform=ax.get_yaxis_transform(),
            ha="left", va="center", fontsize=10, fontweight="bold", rotation=0)
for s in seps[:-1]:
    ax.axhline(s, color="#e2e2e2", lw=0.8, zorder=0)
ax.set_yticks(Y)
ax.set_yticklabels(ylab, fontsize=8.6)
ax.invert_yaxis()
ax.set_ylim(max(Y) + 1.2, min(Y) - 1.2)
ax.set_xlim(0, xmax * 1.30)
ax.set_xlabel("CPU work (core-seconds) — median over the task's 9 replay episodes")
ax.legend(fontsize=9.5, frameon=False, loc="lower right")
ax.set_title("CPU work by fence — 36 count-view picks, matched-configuration replays",
             fontsize=12.5, pad=14)
fig.text(0.99, 0.002, "deterministic replays, model never called (no inference or litellm wedge) · "
                      "cores 4–11 SMT off · (B/T/S/M) = count-view cell · per-episode spread banked",
         ha="right", va="bottom", fontsize=7.5, color="#888888")
fig.tight_layout(rect=(0.06, 0.015, 1, 0.99))
p = f"{OUT}/iso36_cpu_work.png"
fig.savefig(p)
plt.close(fig)
json.dump(values, open(f"{OUT}/iso36_cpu_work_values.json", "w"), indent=1)
tools_share = [100 * x[3] / (x[3] + x[4]) for x in order]
print(p)
print(f"{len(order)} tasks; tools share median {st.median(tools_share):.0f}% "
      f"(min {min(tools_share):.0f}%, max {max(tools_share):.0f}%)")
