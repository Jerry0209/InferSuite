#!/usr/bin/env python3
"""plot_paper_wall.py (paper style; generated from plot_iso36_wall.py) — the SECONDS companion to iso36_cpu_work.png (mentor follow-up:
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
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paper_style as ps  # noqa: E402
ps.apply()

REPO = os.path.expanduser("~/InferSuite")
DATA = f"{REPO}/local_agents/ML_iso36/data"
OUT = os.environ.get("ISO36_OUT", f"{REPO}/local_agents/ML_iso36/plots/paper_v1")
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


# ---- paper-style layout with AVG + MEDIAN aggregate rows ----
TB36 = [x[3] for x in rows]; HB36 = [x[4] for x in rows]
TC36 = [x[5] for x in rows]; WL36 = [x[6] for x in rows]
AGG = {"AVG": (st.mean(TB36), st.mean(HB36), st.mean(TC36), st.mean(WL36)),
       "MEDIAN": (st.median(TB36), st.median(HB36), st.median(TC36), st.median(WL36))}
for name, (tb, hb, tc, wl) in AGG.items():
    values[name] = {"tool_busy_s": round(tb, 1), "harness_busy_s": round(hb, 1),
                    "episode_wall_s": round(wl, 1), "tool_parallelism_x": round(tc / tb, 2)}

GAP = 0.9
ys, ylab, seps, lang_mid, order = [], [], [], {}, []
y = 0.0
for lang in LANGS:
    y0 = y
    for x in [x for x in rows if x[1] == lang]:
        order.append(x); ys.append(y); ylab.append(f"{x[0]} ({x[2]})"); y += 1.0
    lang_mid[lang] = (y0 + y - 1.0) / 2
    seps.append(y - 1.0 + (GAP + 1.0) / 2)
    y += GAP
seps = seps[:-1]
y += 0.9
Y_AGG = {"AVG": y, "MEDIAN": y + 1.0}
BAND_LO, BAND_HI = y - 0.62, y + 1.62
AGG_SEP_AT = y - 0.85
Y = np.array(ys)

fig, ax = plt.subplots(figsize=(9.8, 0.24 * len(order) + 3.8))
ax.grid(axis="x"); ax.grid(False, axis="y")
ax.set_ylim(Y_AGG["MEDIAN"] + 0.9, -0.7)
ps.band(ax, BAND_LO, BAND_HI)
ps.agg_sep(ax, AGG_SEP_AT)
for s in seps:
    ps.lang_sep(ax, s)
ax.tick_params(axis="y", length=0)

TB = np.array([x[3] for x in order]); HB = np.array([x[4] for x in order])
TC = np.array([x[5] for x in order]); WL = np.array([x[6] for x in order])
allmax = float(max(WL.max(), TB.max(), HB.max(), AGG["AVG"][3]))
cap = ps.cap_for(allmax, 100, headroom=1.26)
def rowpair(yy, tb, hb, tc, wl, lw, fs, fw):
    ax.barh(yy - 0.19, tb, height=0.36, color=C_TOOL, edgecolor="black", linewidth=lw, zorder=3)
    ax.barh(yy + 0.19, hb, height=0.36, color=C_HARN, edgecolor="black", linewidth=lw, zorder=3)
    ax.scatter([wl], [yy], marker="|", s=150, color="#5c6b64", zorder=4)
    if tb:
        ax.text(max(tb, wl) + cap * 0.012, yy, f"{tb:,.0f} s · ×{tc / tb:.1f} cores",
                va="center", fontsize=fs, fontweight=fw, zorder=4)
for yy, tb, hb, tc, wl in zip(Y, TB, HB, TC, WL):
    rowpair(yy, tb, hb, tc, wl, 0.5, 6.2, "normal")
for name, yy in Y_AGG.items():
    tb, hb, tc, wl = AGG[name]
    rowpair(yy, tb, hb, tc, wl, 0.9, 6.8, "bold")
ps.exact_limits(ax, "x", 0, cap, 100)
ax.set_yticks(list(Y) + list(Y_AGG.values()))
ax.set_yticklabels(ylab + ["AVG", "MEDIAN"], fontsize=6.4)
for t in ax.get_yticklabels()[-2:]:
    t.set_fontweight("bold")
for lang, mid in lang_mid.items():
    ax.text(-0.265, mid, lang, transform=ax.get_yaxis_transform(),
            ha="left", va="center", fontsize=8, fontweight="bold")
ax.set_xlabel("busy time (seconds) — median over the task's 9 replay episodes")
# paper-ready (PI 2026-09-06): no footer; layout FIRST so the legend centres on the panel
fig.tight_layout(rect=(0.125, 0.01, 1, 0.945))
handles = [plt.Rectangle((0, 0), 1, 1, fc=C_TOOL), plt.Rectangle((0, 0), 1, 1, fc=C_HARN),
           plt.Line2D([0], [0], marker="|", color="#5c6b64", linestyle="none", markersize=9)]
ps.top_legend(fig, handles, ["Tool fence busy", "Agent harness busy", "Episode wall"],
              y=0.985)
ps.assert_exact(ax, "x")
for ext in ("png", "pdf"):
    fig.savefig(f"{OUT}/iso36_active_wall.{ext}", bbox_inches="tight")
json.dump(values, open(f"{OUT}/iso36_active_wall_values.json", "w"), indent=1)
par = [v["tool_parallelism_x"] for k, v in values.items()
       if k not in ("AVG", "MEDIAN") and v.get("tool_parallelism_x")]
print(f"{OUT}/iso36_active_wall.png — asserts passed; tool parallelism median x{st.median(par):.1f}")
