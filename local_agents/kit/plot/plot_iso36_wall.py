#!/usr/bin/env python3
"""plot_iso36_wall.py — the SECONDS companion to iso36_cpu_work.png (mentor follow-up:
core-seconds can mislead on highly parallel tasks).

For each task: how many SECONDS each fence was actually busy (active wall — the sum of
10 Hz sample intervals above the burst detection floor, tool 0.005 / harness 0.02 cores,
the same floors as every burst figure), drawn as GROUPED bars, never stacked: the two
fences overlap in time, so stacking seconds would double-count. A grey tick marks the
episode wall. The tool bar is annotated with its implied parallelism — core-seconds
divided by busy seconds — which is precisely what a core-seconds bar hides.

Median over each task's 9 replay episodes; per-episode spread banked in the values JSON.

    /home/thu/miniforge3/envs/infersuite-full/bin/python local_agents/kit/plot/plot_iso36_wall.py
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
C_TOOL, C_HARN, C_WALL = "#159f77", "#6a51a3", "#9aa8a2"
THR_TOOL, THR_HARN = 0.005, 0.02               # locked burst floors
LANGS = ["C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript"]


def series(rd, i):
    """[(dt, rate, core_s)] per 10 Hz interval, reset-safe."""
    pts = []
    try:
        for ln in open(f"{rd}/cpustat_scope{i}.tsv"):
            p = ln.split()
            if len(p) >= 3 and p[1] == "usage_usec":
                pts.append((float(p[0]), float(p[2])))
    except OSError:
        return []
    out = []
    for (t0, u0), (t1, u1) in zip(pts, pts[1:]):
        dt = t1 - t0
        if dt <= 0:
            continue
        cs = max(u1 - u0, 0.0) / 1e6
        out.append((dt, cs / dt, cs))
    return out


def episode(rd):
    """(tool_busy_s, harn_busy_s, tool_core_s, wall_s) or None."""
    stool, sharn = series(rd, 2), series(rd, 1)
    if not stool:
        return None
    tb = sum(dt for dt, r, _ in stool if r > THR_TOOL)
    hb = sum(dt for dt, r, _ in sharn if r > THR_HARN)
    tc = sum(cs for _dt, _r, cs in stool)
    wall = sum(dt for dt, _r, _cs in stool)
    return tb, hb, tc, wall


sel = [r for r in csv.DictReader(open(SEL), delimiter="\t") if "__" in r.get("instance", "")]
by_lang = collections.defaultdict(list)
for r in sel:
    r["disp"] = r["instance"].split("__", 1)[1]
    by_lang[r["lang"]].append(r)

rows, values = [], {}
for lang in LANGS:
    for r in by_lang[lang]:
        eps = [e for e in (episode(rd) for rd in
                           sorted(glob.glob(f"{DATA}/glm_replay_swe_{r['short']}/run_*")))
               if e and e[0] > 0]
        if not eps:
            continue
        tb = st.median([e[0] for e in eps])
        hb = st.median([e[1] for e in eps])
        tc = st.median([e[2] for e in eps])
        wall = st.median([e[3] for e in eps])
        rows.append((r["disp"], lang, r["label"], tb, hb, tc, wall))
        values[r["short"]] = {
            "language": lang, "cell": r["label"], "n_episodes": len(eps),
            "tool_busy_s_median": round(tb, 1),
            "tool_busy_s_min": round(min(e[0] for e in eps), 1),
            "tool_busy_s_max": round(max(e[0] for e in eps), 1),
            "harness_busy_s_median": round(hb, 1),
            "episode_wall_s_median": round(wall, 1),
            "tool_parallelism_x": round(tc / tb, 2) if tb else None}

GAP = 1.6
ys, ylab = [], []
y = 0.0
lang_at, seps = {}, []
order = []
for lang in LANGS:
    y0 = y
    for x in [x for x in rows if x[1] == lang]:
        order.append(x); ys.append(y); ylab.append(f"{x[0]} ({x[2]})"); y += 1.0
    lang_at[lang] = (y0, y - 1.0)
    seps.append(y - 1.0 + (GAP + 1.0) / 2)
    y += GAP

fig, ax = plt.subplots(figsize=(11.5, 0.34 * len(order) + 4.2))
Y = np.array(ys)
TB = np.array([x[3] for x in order]); HB = np.array([x[4] for x in order])
TC = np.array([x[5] for x in order]); WL = np.array([x[6] for x in order])
ax.barh(Y - 0.19, TB, color=C_TOOL, height=0.36, label="Tool fence busy")
ax.barh(Y + 0.19, HB, color=C_HARN, height=0.36, label="Agent harness busy")
ax.scatter(WL, Y, marker="|", s=170, color=C_WALL, zorder=3, label="episode wall")
xmax = float(max(WL.max(), TB.max(), HB.max()))
for yy, tb, tc, wl in zip(Y, TB, TC, WL):
    ax.text(max(tb, wl) + xmax * 0.012, yy - 0.19,
            f"{tb:,.0f} s · ×{tc / tb:.1f} cores" if tb else "", va="center", fontsize=8.2)
for lang in LANGS:
    lo, hi = lang_at[lang]
    ax.text(-0.155, (lo + hi) / 2, lang, transform=ax.get_yaxis_transform(),
            ha="left", va="center", fontsize=10, fontweight="bold")
for s in seps[:-1]:
    ax.axhline(s, color="#e2e2e2", lw=0.8, zorder=0)
ax.set_yticks(Y)
ax.set_yticklabels(ylab, fontsize=8.6)
ax.invert_yaxis()
ax.set_ylim(max(Y) + 1.2, min(Y) - 1.2)
ax.set_xlim(0, xmax * 1.32)
ax.set_xlabel("busy time (seconds) — median over the task's 9 replay episodes")
ax.legend(fontsize=9.5, frameon=False, loc="lower right")
ax.set_title("The same work in seconds — fence busy time and tool parallelism, 36 tasks",
             fontsize=12.5, pad=14)
fig.text(0.99, 0.002, "grouped, never stacked: the fences overlap in time · ×N = tool core-seconds ÷ busy seconds "
                      "(average parallelism while busy) · busy = 10 Hz intervals above the burst floors "
                      "(tool 0.005 / harness 0.02 cores)",
         ha="right", va="bottom", fontsize=7.5, color="#888888")
fig.tight_layout(rect=(0.06, 0.015, 1, 0.99))
p = f"{OUT}/iso36_active_wall.png"
fig.savefig(p)
plt.close(fig)
json.dump(values, open(f"{OUT}/iso36_active_wall_values.json", "w"), indent=1)
par = [v["tool_parallelism_x"] for v in values.values() if v["tool_parallelism_x"]]
print(p)
print(f"{len(order)} tasks; tool parallelism median ×{st.median(par):.1f} "
      f"(min ×{min(par):.1f}, max ×{max(par):.1f})")
