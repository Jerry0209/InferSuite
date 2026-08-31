#!/usr/bin/env python3
"""plot_iso36_live_overview.py — one 4-panel figure over the 36 count-view picks, from the
LIVE census episodes (ws02, the episodes that produced the trajectories):

  (a) CPU working vs CPU stall  — % of episode wall where at least one fence (tool or
      harness) is active above the burst floors (union, on a 0.2 s grid) vs the rest —
      the rest is dominated by the model round-trip ("GPU"/inference wait).
  (b) Tool vs harness           — fence core-seconds split (exact cgroup accounting).
  (c) # tool calls              — COUNTING RULE (printed + footnote): every action item in
      the SWE-agent trajectory = one command the agent issued and the sandbox executed,
      INCLUDING failed/errored calls and the final submit; model turns that produced no
      action are not counted; there are no sub-agents in this harness.
  (d) median tool-call duration — per-task median over that task's actions'
      execution_time; the AVG bar is the MEAN OF THE 36 PER-TASK MEDIANS (no
      median-of-medians).

AVG row (all panels): unweighted arithmetic mean of the per-task values — NOT
time-weighted, so a long task cannot dominate.

    /home/thu/miniforge3/envs/infersuite-full/bin/python local_agents/kit/plot/plot_iso36_live_overview.py
"""
from __future__ import annotations

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

REPO = os.path.expanduser("~/InferSuite")
ML = f"{REPO}/local_agents/ML_typeid"
OUT = os.environ.get("ISO36_OUT", f"{REPO}/local_agents/ML_iso36/plots")
SEL = f"{ML}/selection_36_count.tsv"

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["DejaVu Serif"], "mathtext.fontset": "dejavuserif",
    "figure.dpi": 150, "savefig.dpi": 300,
    "axes.grid": True, "grid.color": "#d9d9d9", "grid.linewidth": 0.4, "grid.alpha": 0.7,
    "axes.axisbelow": True,
    "xtick.labelsize": 7, "ytick.labelsize": 7, "axes.labelsize": 8, "axes.titlesize": 9,
})
# Okabe-Ito pairs: part-1 / part-2 shared by panels (a) and (b); locked fence colors kept
# for (b) since green/purple = tool/harness across the whole deck.
C_WORK, C_STALL = "#0072B2", "#c9c9c9"
C_TOOL, C_HARN = "#159f77", "#6a51a3"
C_BAR = "#0072B2"
THR_TOOL, THR_HARN = 0.005, 0.02
LANGS = ["C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript"]

mapd = dict(ln.strip().split("\t") for ln in open(f"{ML}/.replay_map.tsv") if "\t" in ln)
sel = [r for r in csv.DictReader(open(SEL), delimiter="\t") if "__" in r.get("instance", "")]
by_lang = collections.defaultdict(list)
for r in sel:
    r["disp"] = r["instance"].split("__", 1)[1]
    by_lang[r["lang"]].append(r)


def cum_usage(path):
    t, u = [], []
    try:
        for ln in open(path):
            p = ln.split()
            if len(p) >= 3 and p[1] == "usage_usec":
                t.append(float(p[0])); u.append(float(p[2]))
    except OSError:
        pass
    # reset-safe cumulative (container cgroup can be recreated)
    cu, tot, prev = [], 0.0, None
    for x in u:
        if prev is not None and x > prev:
            tot += x - prev
        prev = x
        cu.append(tot)
    return np.array(t), np.array(cu) / 1e6


def episode_metrics(live_rd, traj_path):
    tt, tu = cum_usage(f"{live_rd}/cpustat_scope2.tsv")   # tool
    ht, hu = cum_usage(f"{live_rd}/cpustat_scope1.tsv")   # harness
    if len(tt) < 10:
        return None
    t0, t1 = tt[0], tt[-1]
    wall = t1 - t0
    grid = np.arange(t0, t1, 0.2)
    tr = np.diff(np.interp(grid, tt, tu)) / 0.2
    hr = np.diff(np.interp(grid, ht, hu, left=0, right=hu[-1] if len(hu) else 0)) / 0.2 \
        if len(ht) > 1 else np.zeros(len(grid) - 1)
    working = float(np.mean((tr > THR_TOOL) | (hr > THR_HARN))) * 100.0
    tool_cs, harn_cs = float(tu[-1]), float(hu[-1]) if len(hu) else 0.0
    tj = json.load(open(traj_path))
    acts = tj.get("trajectory", [])
    durs = []
    for it in acts:
        et = (it.get("info") or {}).get("execution_time") or it.get("execution_time")
        if isinstance(et, (int, float)):
            durs.append(float(et))
    return dict(wall_s=wall, working_pct=working, stall_pct=100.0 - working,
                tool_cs=tool_cs, harn_cs=harn_cs,
                tool_pct=100.0 * tool_cs / (tool_cs + harn_cs) if tool_cs + harn_cs else 0.0,
                n_calls=len(acts),
                med_dur_s=st.median(durs) if durs else float("nan"))


rows, excluded = [], []
for lang in LANGS:
    for r in by_lang[lang]:
        d = f"{ML}/data/{mapd.get(r['instance'], 'MISSING')}/run_1"
        tp = glob.glob(f"{d}/traj/*/{r['instance']}.traj")
        m = episode_metrics(d, tp[0]) if tp and os.path.isdir(d) else None
        if m is None or m["n_calls"] == 0:
            excluded.append((r["disp"], lang, "no usable live episode data"))
            continue
        rows.append((lang, r["disp"], r["label"], m))

# ---- parsed table + AVG to stdout (sanity check before plotting) ----
print(f"{'lang':<12}{'task':<26}{'cell':<5}{'work%':>7}{'stall%':>7}{'tool%':>7}{'harn%':>7}"
      f"{'#calls':>8}{'medDur_s':>9}")
for lang, disp, cell, m in rows:
    print(f"{lang:<12}{disp:<26}{cell:<5}{m['working_pct']:>7.1f}{m['stall_pct']:>7.1f}"
          f"{m['tool_pct']:>7.1f}{100-m['tool_pct']:>7.1f}{m['n_calls']:>8}{m['med_dur_s']:>9.2f}")
AVG = dict(
    working_pct=st.mean(m["working_pct"] for _, _, _, m in rows),
    tool_pct=st.mean(m["tool_pct"] for _, _, _, m in rows),
    n_calls=st.mean(m["n_calls"] for _, _, _, m in rows),
    med_dur_s=st.mean(m["med_dur_s"] for _, _, _, m in rows),
)
print(f"{'AVG':<12}{'(unweighted mean of ' + str(len(rows)) + ' tasks)':<26}{'':<5}"
      f"{AVG['working_pct']:>7.1f}{100-AVG['working_pct']:>7.1f}{AVG['tool_pct']:>7.1f}"
      f"{100-AVG['tool_pct']:>7.1f}{AVG['n_calls']:>8.1f}{AVG['med_dur_s']:>9.2f}")
RULE = ("counting rule: every action item in the SWE-agent trajectory = one command the "
        "agent issued and the sandbox executed, including failed/errored calls and the "
        "final submit; model turns without an action are not counted; no sub-agents exist "
        "in this harness")
print(RULE)
if excluded:
    print("excluded:", excluded)

# ---- numbers CSV (the R renderers' input): per-task rows + AVG and MEDIAN rows ----
MED = dict(
    working_pct=st.median(m["working_pct"] for _, _, _, m in rows),
    tool_pct=st.median(m["tool_pct"] for _, _, _, m in rows),
    n_calls=st.median(m["n_calls"] for _, _, _, m in rows),
    med_dur_s=st.median(m["med_dur_s"] for _, _, _, m in rows),
)
with open(f"{OUT}/iso36_live_overview_numbers.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["language", "task", "working_pct", "stall_pct", "tool_pct", "harness_pct",
                "n_calls", "med_dur_s"])
    for lang, disp, _c, m in rows:
        w.writerow([lang, disp, round(m["working_pct"], 2), round(m["stall_pct"], 2),
                    round(m["tool_pct"], 2), round(100 - m["tool_pct"], 2),
                    m["n_calls"], round(m["med_dur_s"], 3)])
    for name, agg in (("AVG", AVG), ("MEDIAN", MED)):
        w.writerow([name, name, round(agg["working_pct"], 2),
                    round(100 - agg["working_pct"], 2), round(agg["tool_pct"], 2),
                    round(100 - agg["tool_pct"], 2), round(agg["n_calls"], 1),
                    round(agg["med_dur_s"], 3)])
print(f"{OUT}/iso36_live_overview_numbers.csv  (36 tasks + AVG + MEDIAN)")
if os.environ.get("ISO36_NUMBERS_ONLY"):
    json.dump({f"{l}|{d}": m for l, d, _c, m in rows} | {"AVG": AVG, "MEDIAN": MED,
              "rule": RULE}, open(f"{OUT}/iso36_live_overview_values.json", "w"), indent=1)
    print("numbers-only mode: skipping the matplotlib render")
    sys.exit(0)

# ---- layout ----
GAP, AVGGAP = 0.9, 1.8
ys, ylab, seps = [], [], []
y = 0.0
lang_mid = {}
order = []
for lang in LANGS:
    grp = [x for x in rows if x[0] == lang]
    if not grp:
        continue
    y0 = y
    for x in grp:
        order.append(x); ys.append(y); ylab.append(x[1]); y += 1.0
    lang_mid[lang] = (y0 + y - 1.0) / 2
    seps.append(y - 1.0 + (GAP + 1.0) / 2)
    y += GAP
y += AVGGAP - GAP
Y_AVG = y
Y = np.array(ys)

fig, axes = plt.subplots(1, 4, figsize=(7.5, 5.5), sharey=True, constrained_layout=True)
for ax in axes:
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="x")
    ax.grid(axis="y", visible=False)
    for s_y in seps[:-1]:
        ax.axhline(s_y, color="#e8e8e8", lw=0.5, zorder=0)
    ax.axhline((Y[-1] + Y_AVG) / 2, color="#999999", lw=0.6, ls=(0, (4, 3)), zorder=0)
    ax.invert_yaxis() if ax is axes[0] else None
axes[0].set_ylim(Y_AVG + 1.0, -1.0)

BH = 0.72


def stacked(ax, p1, p1_avg, c1, c2):
    ax.barh(Y, p1, color=c1, height=BH)
    ax.barh(Y, [100 - v for v in p1], left=p1, color=c2, height=BH)
    ax.barh([Y_AVG], [p1_avg], color=c1, height=BH, edgecolor="black", lw=0.9, hatch="//")
    ax.barh([Y_AVG], [100 - p1_avg], left=[p1_avg], color=c2, height=BH,
            edgecolor="black", lw=0.9, hatch="//")
    for yy, v in list(zip(Y, p1)) + [(Y_AVG, p1_avg)]:
        if v >= 8:
            ax.text(v / 2, yy, f"{v:.0f}", ha="center", va="center", fontsize=6, color="white")
        if 100 - v >= 8:
            ax.text(v + (100 - v) / 2, yy, f"{100 - v:.0f}", ha="center", va="center",
                    fontsize=6, color="#333333")
    ax.set_xlim(0, 100)
    ax.set_xticks([0, 25, 50, 75, 100])


def plain(ax, vals, avg, fmt):
    ax.barh(Y, vals, color=C_BAR, height=BH)
    ax.barh([Y_AVG], [avg], color=C_BAR, height=BH, edgecolor="black", lw=0.9, hatch="//")
    vmax = max(max(vals), avg)
    for yy, v in list(zip(Y, vals)) + [(Y_AVG, avg)]:
        ax.text(v + vmax * 0.02, yy, fmt(v), ha="left", va="center", fontsize=6)
    ax.set_xlim(0, vmax * 1.22)


stacked(axes[0], [m["working_pct"] for _, _, _, m in order], AVG["working_pct"], C_WORK, C_STALL)
axes[0].set_title("(a) CPU working vs. stall", pad=4)
stacked(axes[1], [m["tool_pct"] for _, _, _, m in order], AVG["tool_pct"], C_TOOL, C_HARN)
axes[1].set_title("(b) Tool vs. harness", pad=4)
plain(axes[2], [m["n_calls"] for _, _, _, m in order], AVG["n_calls"],
      lambda v: f"{v:.0f}")
axes[2].set_title("(c) # tool calls", pad=4)
plain(axes[3], [m["med_dur_s"] for _, _, _, m in order], AVG["med_dur_s"],
      lambda v: f"{v:.2f}")
axes[3].set_title("(d) median call duration (s)", pad=4)

axes[0].set_yticks(list(Y) + [Y_AVG])
axes[0].set_yticklabels(ylab + ["AVG"], fontsize=5.6)
for lang, mid in lang_mid.items():
    axes[0].text(-1.06, mid, lang, transform=axes[0].get_yaxis_transform(),
                 ha="left", va="center", fontsize=7, fontweight="bold", clip_on=False)

handles = [plt.Rectangle((0, 0), 1, 1, fc=C_WORK), plt.Rectangle((0, 0), 1, 1, fc=C_STALL),
           plt.Rectangle((0, 0), 1, 1, fc=C_TOOL), plt.Rectangle((0, 0), 1, 1, fc=C_HARN)]
fig.legend(handles, ["CPU working", "CPU stall (incl. model wait)", "Tool", "Harness"],
           ncol=4, fontsize=7, loc="upper center", bbox_to_anchor=(0.55, 1.055), frameon=False)
fig.text(0.55, -0.045,
         f"(c) {RULE}.\n(d) AVG = mean of the per-task medians (no median of medians). "
         "AVG rows are unweighted means over the tasks, not time-weighted. "
         "Data: live census episodes (10 Hz cgroup accounting + trajectories).",
         ha="center", fontsize=5.6, color="#555555")
for ext in ("png", "pdf"):
    fig.savefig(f"{OUT}/iso36_live_overview.{ext}", bbox_inches="tight")
json.dump({f"{l}|{d}": m for l, d, _c, m in order} | {"AVG": AVG, "rule": RULE,
          "excluded": excluded},
          open(f"{OUT}/iso36_live_overview_values.json", "w"), indent=1)
print(f"{OUT}/iso36_live_overview.png / .pdf  ({len(order)} tasks, {len(excluded)} excluded)")
