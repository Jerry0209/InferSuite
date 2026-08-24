#!/usr/bin/env python3
"""plot_iso36_tma.py — TMA Level 1 for the 36 count-view picks, grouped 4 tasks per
language, with the SPEC CPU 2026 baseline as the closing panel.

Layout: one figure per fence (tool, harness): a 2x5 grid of panels — nine language panels
of 4 stacked bars each (one per selected task), and a tenth panel holding the SPEC 26
suite medians (INT and FP blocks separately, per the spec26 convention).

Numbers: the continuous PERF_METRICS census (tma_cont.csv), counts POOLED across a task's
9 dedicated-group replay episodes (the census is group-independent; pooling weights by
episode length exactly like every other episode-level ratio). Per-episode spread is banked
in the values JSON so the pooling can be checked rather than trusted — same convention as
plot_tma_l1_fences.py, which this adapts. SPEC panel: median of the per-benchmark episode
census shares over the same four buckets.

    /home/thu/miniforge3/envs/infersuite-full/bin/python local_agents/kit/plot/plot_iso36_tma.py
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
DATA = f"{REPO}/local_agents/ML_iso36/data"
OUT = f"{REPO}/local_agents/ML_iso36/plots"
SEL = f"{REPO}/local_agents/ML_typeid/selection_36_count.tsv"
sys.path.insert(0, f"{REPO}/spec26/kit/plot")
from spec_common import episodes as spec_episodes  # noqa: E402

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["DejaVu Serif"], "mathtext.fontset": "dejavuserif",
    "font.size": 10, "figure.dpi": 150, "savefig.dpi": 300, "savefig.bbox": "tight",
    "axes.grid": True, "grid.color": "#cccccc", "grid.linewidth": 0.5, "grid.alpha": 0.6,
    "axes.axisbelow": True,
})
# Okabe-Ito, same assignment as plot_tma_l1_fences.py — fixed across every TMA figure.
L1COLS = [("retiring", "Retiring", "#009E73"), ("fe-bound", "Frontend-bound", "#0072B2"),
          ("bad-spec", "Bad speculation", "#D55E00"), ("be-bound", "Backend-bound", "#E69F00")]
LANGS = ["C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript"]


def txtcol(h):
    r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
    return "black" if 0.299 * r + 0.587 * g + 0.114 * b > 150 else "white"


def fence_of(cg):
    if "docker-" in cg:
        return "tool"
    if "glm-rep-" in cg or "glm-swe-" in cg:
        return "harness"
    return None


def read_census(path):
    out = collections.defaultdict(lambda: collections.defaultdict(float))
    for ln in open(path, errors="replace"):
        if ln.startswith("#") or not ln.strip():
            continue
        p = ln.split(",")
        if len(p) < 5:
            continue
        f = fence_of(p[4])
        if f is None:
            continue
        try:
            out[f][p[3]] += float(p[1])
        except ValueError:
            continue
    return out


def shares(ev):
    l1 = {k: ev.get(f"topdown-{k}", 0.0) for k, _l, _c in L1COLS}
    tot = sum(l1.values())
    return {k: 100.0 * v / tot for k, v in l1.items()} if tot > 0 else None


# ---- selection: task order, display names ----
sel = [r for r in csv.DictReader(open(SEL), delimiter="\t") if "__" in r.get("instance", "")]
by_lang = collections.defaultdict(list)
for r in sel:
    by_lang[r["lang"]].append(r)

# ---- agent census, pooled per task ----
POOLED, SPREAD, N_EP = {}, {}, {}
for r in sel:
    t = r["short"]
    pooled = collections.defaultdict(lambda: collections.defaultdict(float))
    per_ep = collections.defaultdict(list)
    for p in sorted(glob.glob(f"{DATA}/glm_replay_swe_{t}/run_*/tma_cont.csv")):
        cen = read_census(p)
        for f, ev in cen.items():
            for k, v in ev.items():
                pooled[f][k] += v
            s = shares(ev)
            if s:
                per_ep[f].append(s)
    for f, ev in pooled.items():
        s = shares(ev)
        if s:
            POOLED[(t, f)] = s
            N_EP[(t, f)] = len(per_ep[f])
            SPREAD[(t, f)] = {k: {"min": min(e[k] for e in per_ep[f]),
                                  "max": max(e[k] for e in per_ep[f])}
                              for k, _l, _c in L1COLS} if per_ep[f] else {}

# ---- SPEC medians (INT / FP), from each benchmark's continuous census ----
spec = {}
eps = [e for e in spec_episodes() if e.get("tma", {}).get("l1")]
KEYMAP = {"retiring": "retiring", "bad-spec": "bad_spec", "fe-bound": "fe_bound", "be-bound": "be_bound"}
for blk, cond in (("INT", lambda e: not e["fp"]), ("FP", lambda e: e["fp"])):
    ss = [e["tma"]["l1"] for e in eps if cond(e)]
    if ss:
        spec[blk] = {k: st.median([s[KEYMAP[k]] for s in ss]) for k, _l, _c in L1COLS}
        spec[f"n_{blk}"] = len(ss)

# ---- figures ----
os.makedirs(OUT, exist_ok=True)
vals = {"spec": spec}
for fence in ("tool", "harness"):
    fig, axes = plt.subplots(2, 5, figsize=(16.5, 6.4), sharex=True)
    axes = axes.flatten()
    for ax, lang in zip(axes[:9], LANGS):
        rows = [r for r in by_lang[lang] if (r["short"], fence) in POOLED]
        Y = np.arange(len(rows))
        left = np.zeros(len(rows))
        for key, lab, col in L1COLS:
            v = np.array([POOLED[(r["short"], fence)][key] for r in rows])
            ax.barh(Y, v, left=left, color=col, height=0.62, edgecolor="white", linewidth=0.6)
            for y, (l, vv) in enumerate(zip(left, v)):
                if vv >= 12:
                    ax.text(l + vv / 2, y, f"{vv:.0f}", ha="center", va="center", fontsize=7.5,
                            color=txtcol(col), fontweight="bold")
            left += v
        for r in rows:
            vals[f"{r['short']}|{fence}"] = {
                "language": lang, "cell": r["label"], "shares": POOLED[(r["short"], fence)],
                "n_episodes": N_EP[(r["short"], fence)],
                "per_episode_range": SPREAD.get((r["short"], fence), {})}
        ax.set_yticks(Y)
        ax.set_yticklabels([f"{r['short']} ({r['label']})" for r in rows], fontsize=7.6)
        ax.invert_yaxis()
        ax.set_xlim(0, 100)
        ax.set_ylim(max(len(rows), 4) - 0.5, -0.5)   # 4 slots even when tasks are missing
        ax.grid(axis="x")
        ax.set_title(lang, fontsize=10.5)
    # SPEC panel
    ax = axes[9]
    blocks = [b for b in ("INT", "FP") if b in spec]
    Y = np.arange(len(blocks))
    left = np.zeros(len(blocks))
    for key, lab, col in L1COLS:
        v = np.array([spec[b][key] for b in blocks])
        ax.barh(Y, v, left=left, color=col, height=0.5, edgecolor="white", linewidth=0.6)
        for y, (l, vv) in enumerate(zip(left, v)):
            if vv >= 12:
                ax.text(l + vv / 2, y, f"{vv:.0f}", ha="center", va="center", fontsize=7.5,
                        color=txtcol(col), fontweight="bold")
        left += v
    ax.set_yticks(Y)
    ax.set_yticklabels([f"SPEC26 {b} (n={spec[f'n_{b}']})" for b in blocks], fontsize=7.6)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_ylim(max(len(blocks), 4) - 0.5, -0.5)
    ax.grid(axis="x")
    ax.set_title("SPEC CPU 2026", fontsize=10.5)
    for ax in axes[5:]:
        ax.set_xlabel("pipeline slots (%)", fontsize=8.5)
    handles = [plt.Rectangle((0, 0), 1, 1, fc=c) for _k, _l, c in L1COLS]
    fig.legend(handles, [l for _k, l, _c in L1COLS], ncol=4, fontsize=9.5,
               loc="lower center", bbox_to_anchor=(0.5, -0.035), frameon=False)
    fig.suptitle(f"TMA Level 1 — {fence} fence", fontsize=13, y=1.005)
    fig.text(0.99, 0.995, "count-view selection, 4 tasks per language · 9 episodes pooled "
                          "per task · cores 4–11, SMT off, 100 ms", ha="right", va="top",
             fontsize=7.5, color="#888888")
    fig.tight_layout(rect=[0, 0.02, 1, 0.97])
    p = f"{OUT}/iso36_tma_l1_{fence}.png"
    fig.savefig(p)
    plt.close(fig)
    n = sum(1 for k in vals if k.endswith(f"|{fence}"))
    print(f"{p}  ({n} tasks banked)")

json.dump(vals, open(f"{OUT}/iso36_tma_values.json", "w"), indent=1)
print(f"{OUT}/iso36_tma_values.json")
