#!/usr/bin/env python3
"""plot_iso36_rows.py — the FINAL chart format for the ML_iso36 vs SPEC comparison
(mentor spec, 2026-08-25): one metric per full-width row, workloads grouped as
SPEC-int | SPEC-fp | one group per language.

Every column is one workload's PER-WINDOW distribution (thin box, whiskers 5-95%):
first the 14 SPECrate-int and 12 SPECrate-fp benchmarks (two neutral greys), then the
9 languages' 4 tasks each, one color per language (same color within a group). Both
sides are 100 ms windows on the same configuration; SPEC per-window derivations come
from spec26/kit/plot/spec_common.py (extended 2026-08-25 with the miss rates,
branch-direction MPKI and ctx/CPU-s so all 18 metrics exist on both sides).

Outputs per fence: iso36_rows_<fence>.png (18 stacked full-width rows) and a values
dump with every box's n/median/p5/p95.

    /home/thu/miniforge3/envs/infersuite-full/bin/python local_agents/kit/plot/plot_iso36_rows.py
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
L3 = f"{REPO}/local_agents/ML_iso36/data/l3_study"
OUT = f"{REPO}/local_agents/ML_iso36/plots"
SEL = f"{REPO}/local_agents/ML_typeid/selection_36_count.tsv"
sys.path.insert(0, f"{REPO}/spec26/kit/plot")
from spec_common import episodes as spec_episodes, windows as spec_windows  # noqa: E402

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["DejaVu Serif"], "mathtext.fontset": "dejavuserif",
    "font.size": 10, "figure.dpi": 120, "savefig.dpi": 170, "savefig.bbox": "tight",
    "axes.grid": True, "grid.color": "#d8d8d8", "grid.linewidth": 0.5, "grid.alpha": 0.6,
    "axes.axisbelow": True,
})

LANGS = ["C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript"]
# One color per language (Okabe-Ito + the house harness purple); SPEC in two neutrals.
LCOL = {"C": "#0072B2", "C++": "#56B4E9", "Rust": "#D55E00", "Go": "#009E73",
        "Java": "#E69F00", "PHP": "#CC79A7", "Ruby": "#6b4fa0",
        "JavaScript": "#F0E442", "TypeScript": "#000000"}
INT_COL, FP_COL = "#4d4d4d", "#b3b3b3"

# (agent window-metric key, SPEC window-metric key, row label, log-y)
PANELS = [
    ("IPC", "IPC", "IPC (insn / cycle)", False),
    ("branch_MPKI", "brMPKI", "Branch MPKI (all mispredicts)", False),
    ("branchDir_MPKI", "branchDir_MPKI", "Branch-direction MPKI (cond.)", False),
    ("BTB_MPKI", "baclears_MPKI", "BTB MPKI (BAClears)", False),
    ("DSB_pct", "DSB_pct", "DSB coverage (% of delivered uops)", False),
    ("uopCache_MPKI", "dsb_miss_MPKI", "µop-cache (DSB) MPKI", False),
    ("codeRead_MPKI_L1I", "L1I_MPKI", "L1I MPKI (code-read)", False),
    ("L1D_MPKI", "L1D_MPKI", "L1D-load MPKI", False),
    ("L2_MPKI", "L2_MPKI", "L2-load MPKI", False),
    ("LLC_MPKI", "LLC_MPKI", "LLC MPKI", False),
    ("icache_data_stall_pct", "icache_data_stall_pct", "L1I stall (% cycles)", False),
    ("L1D_missrate_pct", "L1D_missrate_pct", "L1D miss rate (%)", False),
    ("L2_missrate_pct", "L2_missrate_pct", "L2-load miss rate (%)", False),
    ("LLC_missrate_pct", "LLC_missrate_pct", "LLC miss rate (%)", False),
    ("AMAT_cyc", "AMAT_cyc", "AMAT (cycles)", False),
    ("MLP", "MLP", "MLP (outstanding L1D misses)", False),
    ("dram_rd_GBs", "DRAM_read_GBs", "DRAM read bandwidth (GB/s)", False),
    ("ctx_per_cpu_s", "ctx_per_cpu_s", "Context switches (per CPU-s, log)", True),
]

sel = [r for r in csv.DictReader(open(SEL), delimiter="\t") if "__" in r.get("instance", "")]
by_lang = collections.defaultdict(list)
for r in sel:
    r["disp"] = r["instance"].split("__", 1)[1]
    by_lang[r["lang"]].append(r)

WIN = {}
for r in sel:
    p = f"{L3}/all_windows_{r['short']}.csv"
    if os.path.exists(p):
        WIN[r["short"]] = list(csv.DictReader(open(p)))

print("loading SPEC per-window data (26 episodes; cached after first run) ...")
SPEC = sorted(spec_episodes(), key=lambda e: (e["fp"], e["benchmark"]))
SWIN = {e["benchmark"]: spec_windows(e["dir"]) for e in SPEC}


def avals(short, metric, fence):
    return [float(x["value"]) for x in WIN.get(short, [])
            if x["metric"] == metric and x["fence"] == fence]


def svals(bench, metric):
    return [r[metric] for r in SWIN[bench] if metric in r and r[metric] is not None]


# ---- shared x layout: SPEC-int | SPEC-fp | 9 language groups ----
SLOT, GGAP = 1.0, 2.2
cols = []          # (x, kind, key, color, ticklabel)
x = 0.0
groups = []        # (label, x_lo, x_hi)
x0 = x
for e in [e for e in SPEC if not e["fp"]]:
    cols.append((x, "spec", e["benchmark"], INT_COL, e["benchmark"])); x += SLOT
groups.append(("SPEC-int", x0, x - SLOT)); x += GGAP
x0 = x
for e in [e for e in SPEC if e["fp"]]:
    cols.append((x, "spec", e["benchmark"], FP_COL, e["benchmark"])); x += SLOT
groups.append(("SPEC-fp", x0, x - SLOT)); x += GGAP
for lang in LANGS:
    x0 = x
    for r in by_lang[lang]:
        cols.append((x, "agent", r["short"], LCOL[lang], r["disp"])); x += SLOT
    groups.append((lang, x0, x - SLOT)); x += GGAP
XMAX = x - GGAP

vals_dump = {"columns": [(k, key) for _x, k, key, _c, _t in cols]}
for fence in ("tool", "harness"):
    nrow = len(PANELS)
    fig, axes = plt.subplots(nrow, 1, figsize=(20, 2.1 * nrow), sharex=True)
    for ax, (ak, sk, label, use_log) in zip(axes, PANELS):
        data, pos, colors = [], [], []
        for cx, kind, key, col, _t in cols:
            v = svals(key, sk) if kind == "spec" else avals(key, ak, fence)
            if len(v) < 5:
                continue
            data.append(v); pos.append(cx); colors.append(col)
            vals_dump[f"{fence}|{ak}|{key}"] = {
                "n": len(v), "median": st.median(v),
                "p5": float(np.percentile(v, 5)), "p95": float(np.percentile(v, 95))}
        if not data:
            ax.axis("off"); continue
        bp = ax.boxplot(data, positions=pos, widths=SLOT * 0.72, whis=(5, 95),
                        patch_artist=True, showfliers=False,
                        medianprops=dict(color="#111111", lw=1.2),
                        whiskerprops=dict(color="#777777", lw=0.7),
                        capprops=dict(color="#777777", lw=0.7))
        for box, c in zip(bp["boxes"], colors):
            box.set_facecolor(c)
            box.set_alpha(0.85)
            box.set_edgecolor("#666666" if c == "#F0E442" else "white")
            box.set_linewidth(0.5)
        if use_log:
            ax.set_yscale("log")
        ax.set_xlim(-0.9, XMAX + 0.9)
        ax.set_ylabel(label, fontsize=9.5)
        ax.tick_params(length=0, labelsize=8)
        for _g, lo, hi in groups[:-1]:
            ax.axvline(hi + (SLOT + GGAP) / 2, color="#e6e6e6", lw=0.6, zorder=0)
        # SPEC | agent divider, heavier
        ax.axvline(groups[1][2] + (SLOT + GGAP) / 2, color="#7a8a99", lw=1.1,
                   ls=(0, (4, 3)), zorder=1)
    # bottom axis: per-workload labels + group labels
    axb = axes[-1]
    axb.set_xticks([c[0] for c in cols])
    axb.set_xticklabels([c[4] for c in cols], rotation=90, fontsize=6.8)
    for g, lo, hi in groups:
        color = (INT_COL if g == "SPEC-int" else FP_COL if g == "SPEC-fp" else LCOL[g])
        axes[0].text((lo + hi) / 2, 1.04, g, transform=axes[0].get_xaxis_transform(),
                     ha="center", va="bottom", fontsize=10.5, fontweight="bold",
                     color=color if g != "SPEC-fp" else "#8c8c8c")
    fig.suptitle(f"Per-window distributions, one metric per row — {fence} fence · "
                 "SPEC-int | SPEC-fp | 9 languages × 4 tasks · 100 ms windows, "
                 "box = IQR, whiskers 5–95%", fontsize=13, y=1.0)
    fig.tight_layout(rect=[0, 0, 1, 0.995])
    p = f"{OUT}/iso36_rows_{fence}.png"
    fig.savefig(p)
    plt.close(fig)
    print(p)

json.dump(vals_dump, open(f"{OUT}/iso36_rows_values.json", "w"), indent=1)
print(f"{OUT}/iso36_rows_values.json")
