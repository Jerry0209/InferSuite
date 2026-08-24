#!/usr/bin/env python3
"""plot_iso36_grid.py — the 18-metric per-window distribution grid over the 36 count-view
picks, 4 tasks clustered per language, SPEC CPU 2026 closing every panel.

Panels: the mentor's 16 (cross_task_grid.py PANELS16) + DRAM read bandwidth + context
switches per CPU-second. The three fe_miss metrics (branch-direction MPKI, BTB MPKI,
uop-cache MPKI) are the ones the previous capture could not profile.

Encoding per panel: x = 9 language clusters + SPEC. Each cluster holds the language's 4
selected tasks (selection order: B,T,S,M cells then majority top-ups) as thin boxes of that
task's PER-WINDOW values (whiskers 5-95%), colored by the task's count-cell type. The SPEC
box is the distribution of the 26 per-benchmark EPISODE values (metrics.json, the shared
implementation) — a suite spread, deliberately not per-window, and labelled as such.

    /home/thu/miniforge3/envs/infersuite-full/bin/python local_agents/kit/plot/plot_iso36_grid.py
"""
from __future__ import annotations

import collections
import csv
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
L3 = f"{DATA}/l3_study"
OUT = f"{REPO}/local_agents/ML_iso36/plots"
SEL = f"{REPO}/local_agents/ML_typeid/selection_36_count.tsv"
sys.path.insert(0, f"{REPO}/spec26/kit/plot")
from spec_common import episodes as spec_episodes  # noqa: E402

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["DejaVu Serif"], "mathtext.fontset": "dejavuserif",
    "font.size": 9.5, "figure.dpi": 130, "savefig.dpi": 220, "savefig.bbox": "tight",
    "axes.grid": True, "grid.color": "#d8d8d8", "grid.linewidth": 0.5, "grid.alpha": 0.6,
    "axes.axisbelow": True,
})
LANGS = ["C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript"]
LSHORT = {"C": "C", "C++": "C++", "Rust": "Rs", "Go": "Go", "Java": "Java", "PHP": "PHP",
          "Ruby": "Rb", "JavaScript": "JS", "TypeScript": "TS"}
# Count-cell type colors (Okabe-Ito subset; SPEC reference is grey).
TCOL = {"B": "#0072B2", "T": "#009E73", "S": "#D55E00", "M": "#CC79A7"}
SPEC_COL = "#999999"

# (window-metric key, SPEC episode-card key, panel title, log?)
PANELS = [
    ("IPC", "IPC", "IPC", False),
    ("branch_MPKI", "brMPKI", "Branch MPKI (all mispredicts)", False),
    ("branchDir_MPKI", "branchDir_MPKI", "Branch-direction MPKI (cond.)", False),
    ("BTB_MPKI", "baclears_MPKI", "BTB MPKI (BAClears)", False),
    ("DSB_pct", "DSB_pct", "DSB coverage (%)", False),
    ("uopCache_MPKI", "dsb_miss_MPKI", "µop-cache (DSB) MPKI", False),
    ("codeRead_MPKI_L1I", "L1I_MPKI", "L1I MPKI (code-read)", False),
    ("L1D_MPKI", "L1D_MPKI", "L1D-load MPKI", False),
    ("L2_MPKI", "L2_MPKI", "L2-load MPKI", False),
    ("LLC_MPKI", "LLC_MPKI", "LLC MPKI", False),
    ("icache_data_stall_pct", "icache_data_stall_pct", "L1I stall (% cycles) — miss-rate proxy", False),
    ("L1D_missrate_pct", "L1D_missrate_pct", "L1D miss rate (%)", False),
    ("L2_missrate_pct", "L2_missrate_pct", "L2-load miss rate (%)", False),
    ("LLC_missrate_pct", "LLC_missrate_pct", "LLC miss rate (%)", False),
    ("AMAT_cyc", "AMAT_cyc", "AMAT (cycles)", False),
    ("MLP", "MLP", "MLP", False),
    ("dram_rd_GBs", "DRAM_read_GBs", "DRAM read bandwidth (GB/s)", False),
    ("ctx_per_cpu_s", "ctx_per_cpu_s", "Context switches (per CPU-s, log)", True),
]

sel = [r for r in csv.DictReader(open(SEL), delimiter="\t") if "__" in r.get("instance", "")]
by_lang = collections.defaultdict(list)
for r in sel:
    by_lang[r["lang"]].append(r)

# per-window rows per task (LONG format from analyze_l3_windows.py)
WIN = {}
for r in sel:
    p = f"{L3}/all_windows_{r['short']}.csv"
    if os.path.exists(p):
        WIN[r["short"]] = list(csv.DictReader(open(p)))

SPEC = spec_episodes()

def wvals(short, metric, fence):
    return [float(x["value"]) for x in WIN.get(short, [])
            if x["metric"] == metric and x["fence"] == fence]

# ---- geometry: 4 slots per language cluster + gap; SPEC slot at the end ----
SLOT_W, GAP = 1.0, 1.6
xpos, xinfo = {}, []          # short -> x; (x, r) for banked columns
x = 0.0
lang_centers = {}
for lang in LANGS:
    x0 = x
    for r in by_lang[lang]:
        xpos[r["short"]] = x
        x += SLOT_W
    lang_centers[lang] = (x0 + x - SLOT_W) / 2
    x += GAP
SPEC_X = x + 0.4
XMAX = SPEC_X + 1.4

vals_dump = {"column_order": [(r["lang"], r["short"], r["label"]) for l in LANGS for r in by_lang[l]]}
os.makedirs(OUT, exist_ok=True)
for fence in ("tool", "harness"):
    fig, axes = plt.subplots(6, 3, figsize=(19.5, 20.0))
    axes = axes.flatten()
    for ax, (wk, sk, title, use_log) in zip(axes, PANELS):
        data, positions, colors, banked = [], [], [], 0
        for lang in LANGS:
            for r in by_lang[lang]:
                v = wvals(r["short"], wk, fence)
                if not v:
                    continue
                data.append(v); positions.append(xpos[r["short"]])
                colors.append(TCOL.get(r["label"], "#777777")); banked += 1
                vals_dump[f"{fence}|{wk}|{r['short']}"] = {
                    "n": len(v), "median": st.median(v),
                    "p5": float(np.percentile(v, 5)), "p95": float(np.percentile(v, 95))}
        sv = [e["metrics"].get(sk) for e in SPEC]
        sv = [v for v in sv if v is not None]
        if sv:
            data.append(sv); positions.append(SPEC_X); colors.append(SPEC_COL)
            vals_dump[f"{fence}|{wk}|SPEC26"] = {
                "n": len(sv), "median": st.median(sv), "min": min(sv), "max": max(sv)}
        if not data:
            ax.axis("off"); continue
        bp = ax.boxplot(data, positions=positions, widths=SLOT_W * 0.78, whis=(5, 95),
                        patch_artist=True, showmeans=False, showfliers=False,
                        medianprops=dict(color="#222222", lw=1.1),
                        whiskerprops=dict(color="#666666", lw=0.7),
                        capprops=dict(color="#666666", lw=0.7))
        for box, c in zip(bp["boxes"], colors):
            box.set_facecolor(c); box.set_alpha(0.75); box.set_edgecolor("white"); box.set_linewidth(0.5)
        if use_log:
            ax.set_yscale("log")
        ax.set_xlim(-0.8, XMAX)
        ax.set_xticks([lang_centers[l] for l in LANGS] + [SPEC_X])
        ax.set_xticklabels([LSHORT[l] for l in LANGS] + ["SPEC"], fontsize=8)
        for l in LANGS[:-1]:
            ax.axvline(lang_centers[l] + (len(by_lang[l]) * SLOT_W) / 2 + GAP / 2 - SLOT_W / 2,
                       color="#e2e2e2", lw=0.6, zorder=0)
        ax.axvline(SPEC_X - GAP / 2 - 0.2, color="#7a8a99", lw=1.0, ls=(0, (4, 3)), zorder=1)
        ax.set_title(title, fontsize=10.5)
        ax.grid(axis="y")
        ax.tick_params(length=0)
    handles = ([plt.Rectangle((0, 0), 1, 1, fc=TCOL[k], alpha=0.75) for k in "BTSM"]
               + [plt.Rectangle((0, 0), 1, 1, fc=SPEC_COL, alpha=0.75)])
    fig.legend(handles, ["build (B)", "test (T)", "search (S)", "mixed (M)",
                         "SPEC 26 (episode values)"],
               ncol=5, fontsize=10, loc="lower center", bbox_to_anchor=(0.5, -0.012), frameon=False)
    fig.suptitle(f"Per-window distributions, 36 count-view picks by language — {fence} fence "
                 f"(box = IQR of 100 ms windows, whiskers 5–95%; SPEC box = 26 episode values)",
                 fontsize=13.5, y=0.9985)
    fig.tight_layout(rect=[0, 0.008, 1, 0.988])
    p = f"{OUT}/iso36_grid_{fence}.png"
    fig.savefig(p)
    plt.close(fig)
    print(f"{p}  ({len(WIN)} tasks with windows)")

json.dump(vals_dump, open(f"{OUT}/iso36_grid_values.json", "w"), indent=1)
print(f"{OUT}/iso36_grid_values.json")
