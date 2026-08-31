#!/usr/bin/env python3
"""plot_paper_cpu_work.py — per-task CPU work by fence (tool + harness in ONE stacked
bar) in the PAPER style (paper_style.py; mentor 2026-08-31), over the revised 36.

Data identical to plot_iso36_cpu_work.py (exact cgroup cpu.stat, per-fence MEDIAN over
the task's 9 replay episodes, reset-safe); adds AVG and MEDIAN aggregate rows on the grey
band with value labels, dotted language separators, exact axis-border alignment.

Writes: plots/paper_v1/iso36_cpu_work.{png,pdf} + iso36_cpu_work_values.json
"""
import collections
import csv
import glob
import json
import os
import statistics as st
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paper_style as ps  # noqa: E402

ps.apply()
REPO = os.path.expanduser("~/InferSuite")
DATA = f"{REPO}/local_agents/ML_iso36/data"
OUT = os.environ.get("ISO36_OUT", f"{REPO}/local_agents/ML_iso36/plots/paper_v1")
SEL = f"{REPO}/local_agents/ML_typeid/selection_36_count.tsv"
C_TOOL, C_HARN = "#159f77", "#6a51a3"
LANGS = ["C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript"]


def fence_core_s(rd, i):
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
assert len(rows) == 36, f"expected 36 tasks, got {len(rows)}"

T36 = [x[3] for x in rows]
H36 = [x[4] for x in rows]
AGG = {"AVG": (st.mean(T36), st.mean(H36)), "MEDIAN": (st.median(T36), st.median(H36))}
values["AVG"] = {"tool_core_s": round(AGG["AVG"][0], 1), "harness_core_s": round(AGG["AVG"][1], 1)}
values["MEDIAN"] = {"tool_core_s": round(AGG["MEDIAN"][0], 1),
                    "harness_core_s": round(AGG["MEDIAN"][1], 1)}

# ---- layout ----
GAP = 0.9
ys, ylab, seps, lang_mid = [], [], [], {}
y = 0.0
order = []
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

fig, ax = plt.subplots(figsize=(9.6, 0.20 * len(rows) + 3.4))
ax.grid(axis="x"); ax.grid(False, axis="y")
ax.set_ylim(Y_AGG["MEDIAN"] + 0.9, -0.7)
ps.band(ax, BAND_LO, BAND_HI)
ps.agg_sep(ax, AGG_SEP_AT)
for s in seps:
    ps.lang_sep(ax, s)
ax.tick_params(axis="y", length=0)

vmax = max(t + h for _, _, _, t, h in order)
cap = ps.cap_for(vmax, 100, headroom=1.24)
for (disp, lg, cell, t, h), yy in zip(order, Y):
    ax.barh(yy, t, height=0.8, color=C_TOOL, zorder=3, **ps.BAR_EDGE)
    ax.barh(yy, h, left=t, height=0.8, color=C_HARN, zorder=3, **ps.BAR_EDGE)
    tot = t + h
    ax.text(tot + cap * 0.012, yy, f"{tot:,.0f}  ({100 * t / tot:.0f}% tools)",
            va="center", fontsize=6.2, zorder=4)
for name, yy in Y_AGG.items():
    t, h = AGG[name]
    ax.barh(yy, t, height=0.8, color=C_TOOL, edgecolor="black", linewidth=0.9, zorder=3)
    ax.barh(yy, h, left=t, height=0.8, color=C_HARN, edgecolor="black", linewidth=0.9,
            zorder=3)
    ax.text(t + h + cap * 0.012, yy, f"{t + h:,.0f}  ({100 * t / (t + h):.0f}% tools)",
            va="center", fontsize=6.8, fontweight="bold", zorder=4)
ps.exact_limits(ax, "x", 0, cap, 100)
ax.set_yticks(list(Y) + list(Y_AGG.values()))
ax.set_yticklabels(ylab + ["AVG", "MEDIAN"], fontsize=6.4)
for t in ax.get_yticklabels()[-2:]:
    t.set_fontweight("bold")
for lang, mid in lang_mid.items():
    ax.text(-0.20, mid, lang, transform=ax.get_yaxis_transform(),
            ha="left", va="center", fontsize=8, fontweight="bold")
ax.set_xlabel("CPU work (core-seconds) — median over the task's 9 replay episodes")
handles = [plt.Rectangle((0, 0), 1, 1, fc=C_TOOL), plt.Rectangle((0, 0), 1, 1, fc=C_HARN)]
ps.top_legend(fig, handles, ["Tool execution", "Agent harness"], y=0.985)
fig.text(0.5, -0.012,
         "deterministic replays of the revised all-resolved 36, model never called (no "
         "inference or litellm wedge) · cores 4–11 SMT off · (B/T/S/M) = count-view "
         "cell · AVG/MEDIAN = unweighted over the 36 task medians · spread banked",
         ha="center", fontsize=6, color="#666666")
fig.tight_layout(rect=(0.09, 0.01, 1, 0.955))
ps.assert_exact(ax, "x")
for ext in ("png", "pdf"):
    fig.savefig(f"{OUT}/iso36_cpu_work.{ext}", bbox_inches="tight")
json.dump(values, open(f"{OUT}/iso36_cpu_work_values.json", "w"), indent=1)
print(f"{OUT}/iso36_cpu_work.png / .pdf — asserts passed; "
      f"AVG {sum(AGG['AVG']):,.0f} core-s, MEDIAN {sum(AGG['MEDIAN']):,.0f} core-s")
