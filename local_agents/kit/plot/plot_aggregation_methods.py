#!/usr/bin/env python3
"""plot_aggregation_methods.py — why the violins aggregate one vote per WORKLOAD.

A reviewer's question (mentor, 2026-09-12): for a metric like IPC, is the violin drawn over
every per-window measurement pooled across workloads, or over one median per workload? The two
are different graphs, so this script renders both from the same data and prints the spread
change for all twelve displayed metrics.

  (A) pooled   — every 100 ms window from every workload, in one violin. Its width is mostly
                 WITHIN-workload variation (an agent compiling vs waiting vs testing), and each
                 workload is weighted by how many windows it contributed, i.e. by how long it
                 ran. Longest/shortest is 14.5x for the agentic tasks and 38x for SPEC.
  (B) one vote — the median of each workload's windows, one value per workload. Its width is
                 ACROSS-workload variation with every workload weighted equally.

The paper figures use (B) for the compact SPEC-vs-Agentic-vs-DCPerf grid, because the claim
there is about how workload FAMILIES differ. The per-window group figures use per-workload
distributions (one violin per column), which is (A) without pooling across workloads.

    ~/miniforge3/envs/infersuite-full/bin/python3 local_agents/kit/plot/plot_aggregation_methods.py
"""
from __future__ import annotations

import collections
import csv
import os
import statistics as st
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO = os.path.expanduser("~/InferSuite")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, f"{REPO}/spec26/kit/plot")
import paper_style as ps  # noqa: E402
from spec_common import episodes as spec_episodes, windows as spec_windows  # noqa: E402

ps.apply()
OUT = f"{REPO}/local_agents/DCPerf/plots/paper_v1"
os.makedirs(OUT, exist_ok=True)
LANGS = ["C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript"]
METRICS = ["IPC", "Branch MPKI", "Branch-direction MPKI", "BTB MPKI (BAClears)",
           "L1I MPKI (code-read)", "uop-cache (DSB) MPKI", "DSB coverage (%)",
           "L1D-load MPKI", "L2-load MPKI", "LLC MPKI", "DRAM read (GB/s)",
           "Context switches (/CPU-s)"]
SPEC_KEY = {"IPC": "IPC", "Branch MPKI": "brMPKI", "Branch-direction MPKI": "branchDir_MPKI",
            "BTB MPKI (BAClears)": "baclears_MPKI", "L1I MPKI (code-read)": "L1I_MPKI",
            "uop-cache (DSB) MPKI": "dsb_miss_MPKI", "DSB coverage (%)": "DSB_pct",
            "L1D-load MPKI": "L1D_MPKI", "L2-load MPKI": "L2_MPKI", "LLC MPKI": "LLC_MPKI",
            "DRAM read (GB/s)": "DRAM_read_GBs", "Context switches (/CPU-s)": "ctx_per_cpu_s"}

ag = collections.defaultdict(lambda: collections.defaultdict(list))
for r in csv.DictReader(open(f"{REPO}/local_agents/ML_iso36/data/l3_study/agg_rows_long.csv")):
    if r["fence"] == "both" and r["metric"] in METRICS and r["grp"] in LANGS:
        ag[r["metric"]][r["col"]].append(float(r["value"]))
sp = collections.defaultdict(lambda: collections.defaultdict(list))
for e in spec_episodes():
    for w in spec_windows(e["dir"]):
        for lab, k in SPEC_KEY.items():
            if w.get(k) is not None:
                sp[lab][e["dir"]].append(float(w[k]))

def spread(v):
    v = sorted(v)
    return v[int((len(v) - 1) * .05)], v[int((len(v) - 1) * .95)]

print(f"{'metric':<28}{'family':<9}{'p5-p95 pooled':>20}{'p5-p95 one-vote':>20}{'width ratio':>13}")
rows = []
for m in METRICS:
    for fam, d in (("SPEC", sp[m]), ("Agentic", ag[m])):
        if not d:
            continue
        pooled = [x for v in d.values() for x in v]
        votes = [st.median(v) for v in d.values()]
        pa, pb = spread(pooled); va, vb = spread(votes)
        ratio = (pb - pa) / (vb - va) if (vb - va) > 0 else float("inf")
        print(f"{m:<28}{fam:<9}{f'{pa:.3g} - {pb:.3g}':>20}{f'{va:.3g} - {vb:.3g}':>20}{ratio:>12.1f}x")
        rows.append([m, fam, len(pooled), len(votes), pa, pb, va, vb, round(ratio, 2)])
with open(f"{OUT}/aggregation_methods_numbers.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["metric", "family", "n_pooled_windows", "n_workloads",
                "pooled_p5", "pooled_p95", "onevote_p5", "onevote_p95", "width_ratio"])
    w.writerows(rows)

# ---- figure: IPC under both aggregations, both families ----
fig, axes = plt.subplots(1, 2, figsize=(6.6, 3.5), sharey=True, constrained_layout=True)
C = {"SPEC": "#2166ac", "Agentic": "#b2182b"}
for ax, (fam, d) in zip(axes, (("SPEC", sp["IPC"]), ("Agentic", ag["IPC"]))):
    pooled = [x for v in d.values() for x in v]
    votes = [st.median(v) for v in d.values()]
    parts = ax.violinplot([pooled, votes], positions=[1, 2], widths=0.72,
                          showextrema=False, showmedians=False)
    for b in parts["bodies"]:
        b.set_facecolor(C[fam]); b.set_edgecolor("black"); b.set_linewidth(0.5); b.set_alpha(0.75)
    for pos, v in ((1, pooled), (2, votes)):
        q1, med, q3 = (sorted(v)[int((len(v) - 1) * p)] for p in (.25, .5, .75))
        ax.vlines(pos, q1, q3, color="white", linewidth=4.5, zorder=3)
        ax.hlines(med, pos - 0.09, pos + 0.09, color="black", linewidth=1.4, zorder=4)
    ax.set_xticks([1, 2])
    ax.set_xticklabels([f"(A) pooled\n{len(pooled):,} windows",
                        f"(B) one vote\n{len(votes)} workloads"], fontsize=7.5)
    ax.set_title(fam, pad=4)
    ax.grid(axis="y"); ax.grid(False, axis="x")
ps.exact_limits(axes[0], "y", 0, 5, 1)
axes[0].set_ylabel("IPC")
for ax in axes:
    ps.assert_exact(ax, "y")
for ext in ("png", "pdf"):
    fig.savefig(f"{OUT}/aggregation_methods_ipc.{ext}", bbox_inches="tight")
print(f"\nwrote {OUT}/aggregation_methods_ipc.png / .pdf")
