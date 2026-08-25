#!/usr/bin/env python3
"""plot_iso36_rows_agg.py — the AGGREGATED variant of the row-format comparison
(mentor follow-up, 2026-08-25): SPEC collapsed to TWO bars (SPEC-int, SPEC-fp), plus a
Python comparison group, then the nine multilingual language groups. Appended beside
iso36_rows_* — never replacing it.

Columns per row:
  SPEC-int, SPEC-fp — ONE box each: the distribution of per-benchmark window-MEDIANS
      (14 int / 12 fp benchmarks; each benchmark votes once — pooling raw windows would
      let long benchmarks dominate).
  Python — scikit-learn, astropy, sympy from the matched-configuration SWE_iso8 replays
      (same cores 4-11 SMT-off, 100 ms windows; 8 shared groups). A fourth slot is
      reserved and marked: no fourth Python task has a banked matched capture, and no new
      profiling is run for it. The three fe_miss metrics (branch-direction MPKI, BTB
      MPKI, uop-cache MPKI) were never captured for Python — those cells carry a
      "to be measured" mark, deliberately not a zero.
  9 languages x 4 tasks — identical to iso36_rows_*.

    /home/thu/miniforge3/envs/infersuite-full/bin/python local_agents/kit/plot/plot_iso36_rows_agg.py
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
PYL3 = f"{REPO}/local_agents/SWE_iso8/data/l3_study"
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
LCOL = {"C": "#0072B2", "C++": "#56B4E9", "Rust": "#D55E00", "Go": "#009E73",
        "Java": "#E69F00", "PHP": "#CC79A7", "Ruby": "#6b4fa0",
        "JavaScript": "#F0E442", "TypeScript": "#000000"}
PY_COL = "#8c510a"
INT_COL, FP_COL = "#4d4d4d", "#b3b3b3"
PYTASKS = ["scikit-learn", "astropy", "sympy"]

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
PYWIN = {t: (list(csv.DictReader(open(f"{PYL3}/all_windows_{t}.csv")))
             if os.path.exists(f"{PYL3}/all_windows_{t}.csv") else []) for t in PYTASKS}

print("loading SPEC per-window data (cached) ...")
SPEC = spec_episodes()
SWIN = {e["benchmark"]: spec_windows(e["dir"]) for e in SPEC}
SPEC_GROUPS = {"SPEC-int": [e["benchmark"] for e in SPEC if not e["fp"]],
               "SPEC-fp": [e["benchmark"] for e in SPEC if e["fp"]]}


def wvals(rows, metric, fence):
    return [float(x["value"]) for x in rows if x["metric"] == metric and x["fence"] == fence]


def spec_agg(gname, metric):
    """One value per benchmark: the median of its windows for this metric."""
    meds = []
    for b in SPEC_GROUPS[gname]:
        v = [r[metric] for r in SWIN[b] if metric in r and r[metric] is not None]
        if len(v) >= 5:
            meds.append(st.median(v))
    return meds


# ---- layout: SPEC-int | SPEC-fp || Python (3 + reserved) || 9 languages ----
SLOT, GGAP = 1.0, 2.2
cols, groups = [], []
x = 0.0
for g, col in (("SPEC-int", INT_COL), ("SPEC-fp", FP_COL)):
    cols.append((x, "specagg", g, col, f"{g} ({len(SPEC_GROUPS[g])})"))
    groups.append((g, x, x)); x += SLOT + GGAP * 0.35
x += GGAP * 0.65
x0 = x
for t in PYTASKS:
    cols.append((x, "python", t, PY_COL, t)); x += SLOT
cols.append((x, "reserved", "py4", PY_COL, "(4th: to fill)")); x += SLOT
groups.append(("Python", x0, x - SLOT)); x += GGAP
for lang in LANGS:
    x0 = x
    for r in by_lang[lang]:
        cols.append((x, "agent", r["short"], LCOL[lang], r["disp"])); x += SLOT
    groups.append((lang, x0, x - SLOT)); x += GGAP
XMAX = x - GGAP
PY_LO, PY_HI = groups[2][1], groups[2][2]

vals_dump = {"columns": [(k, key) for _x, k, key, _c, _t in cols],
             "spec_aggregation": "one value per benchmark = median of its windows; "
                                 "box over those per-benchmark medians"}
for fence in ("tool", "harness"):
    nrow = len(PANELS)
    fig, axes = plt.subplots(nrow, 1, figsize=(17, 2.1 * nrow), sharex=True)
    for ax, (ak, sk, label, use_log) in zip(axes, PANELS):
        data, pos, colors = [], [], []
        py_present = False
        for cx, kind, key, col, _t in cols:
            if kind == "specagg":
                v = spec_agg(key, sk)
            elif kind == "python":
                v = wvals(PYWIN[key], ak, fence)
            elif kind == "reserved":
                continue
            else:
                v = wvals(WIN.get(key, []), ak, fence)
            if len(v) < 3:
                continue
            if kind == "python":
                py_present = True
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
        if not py_present:
            ax.text((PY_LO + PY_HI) / 2, 0.5, "to be\nmeasured", transform=ax.get_xaxis_transform(),
                    ha="center", va="center", fontsize=8.5, style="italic", color="#8c510a")
        if use_log:
            ax.set_yscale("log")
        ax.set_xlim(-0.9, XMAX + 0.9)
        ax.set_ylabel(label, fontsize=9.5)
        ax.tick_params(length=0, labelsize=8)
        for _g, lo, hi in groups[:-1]:
            ax.axvline(hi + (SLOT + GGAP) / 2, color="#e6e6e6", lw=0.6, zorder=0)
        ax.axvline(groups[1][2] + (SLOT + GGAP * 0.65) / 2 + SLOT / 2, color="#7a8a99",
                   lw=1.1, ls=(0, (4, 3)), zorder=1)
    axb = axes[-1]
    axb.set_xticks([c[0] for c in cols])
    axb.set_xticklabels([c[4] for c in cols], rotation=90, fontsize=7.2)
    # one combined header over the two single-column SPEC groups (separate headers collide)
    axes[0].text((groups[0][1] + groups[1][2]) / 2, 1.04, "SPEC CPU 2026",
                 transform=axes[0].get_xaxis_transform(), ha="center", va="bottom",
                 fontsize=10.5, fontweight="bold", color=INT_COL)
    for g, lo, hi in groups[2:]:
        color = PY_COL if g == "Python" else LCOL[g]
        axes[0].text((lo + hi) / 2, 1.04, g, transform=axes[0].get_xaxis_transform(),
                     ha="center", va="bottom", fontsize=10.5, fontweight="bold", color=color)
    fig.suptitle(f"Per-window distributions, aggregated SPEC — {fence} fence · "
                 "SPEC-int / SPEC-fp = box over per-benchmark window-medians · Python = "
                 "matched-configuration replays · 100 ms windows, box = IQR, whiskers 5–95%",
                 fontsize=12.5, y=1.0)
    fig.tight_layout(rect=[0, 0, 1, 0.995])
    p = f"{OUT}/iso36_rows_agg_{fence}.png"
    fig.savefig(p)
    plt.close(fig)
    print(p)

json.dump(vals_dump, open(f"{OUT}/iso36_rows_agg_values.json", "w"), indent=1)
print(f"{OUT}/iso36_rows_agg_values.json")
