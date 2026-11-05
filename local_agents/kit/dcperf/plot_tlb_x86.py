#!/usr/bin/env python3
"""plot_tlb_x86.py — the TLB hierarchy, SPEC on ARM and x86 and the Server set on x86.

One panel per metric, one column per population, one dot per benchmark/workload, a bar at the
median. Log y: the populations span up to 5 decades (ARM code-side rates reach 2e-6 MPKI). A value
below the panel floor would be drawn AT the floor as a hollow dot and counted in the column label;
with the floors below, none is. Inputs: local_agents/tlb_x86/{server_tlb_x86.csv,spec_tlb_x86.csv,arm_vs_x86_tlb.csv}
(the last two copied from spec-x86). Writes local_agents/tlb_x86/plots/tlb_hierarchy.png.

  ~/miniforge3/envs/infersuite-full/bin/python3 plot_tlb_x86.py
"""
import csv
import os
import statistics as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
D = f"{REPO}/local_agents/tlb_x86"
# fixed categorical order (dataviz reference palette, validated light: all checks pass)
POP = [("SPEC · ARM", "#2a78d6"), ("SPEC · x86", "#eb6834"), ("Server · x86", "#1baf7a")]
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
# (x86 metric, ARM metric or None, panel title, unit, floor)
PANELS = [("dTLB_L1_MPKI", "L1D-TLB MPKI", "L1 data-TLB misses", "per kilo-instruction", 1e-3),
          ("dTLB_walk_MPKI", "DTLB-walk MPKI", "Data page walks", "per kilo-instruction", 1e-4),
          ("iTLB_L1_MPKI", "L1I-TLB MPKI", "L1 instruction-TLB misses", "per kilo-instruction", 1e-6),
          ("iTLB_walk_MPKI", "ITLB-walk MPKI", "Instruction page walks", "per kilo-instruction", 1e-6),
          ("dtlb_load_walk_pct", None, "Cycles walking (data loads)", "% of cycles", 1e-3),
          ("itlb_walk_pct", None, "Cycles walking (code)", "% of cycles", 1e-3)]


def col(path, key, val):
    out = {}
    for r in csv.DictReader(ln for ln in open(path) if not ln.startswith("#")):
        if r.get(val) not in (None, "", "None"):
            out[r[key]] = float(r[val])
    return out


def arm(metric):
    out = {}
    for r in csv.DictReader(ln for ln in open(f"{D}/arm_vs_x86_tlb.csv") if not ln.startswith("#")):
        if r["arm_metric"] == metric and r["arm_ratio_of_sums"] not in ("", "None"):
            out[r["benchmark"]] = float(r["arm_ratio_of_sums"])
    return out


def main():
    os.makedirs(f"{D}/plots", exist_ok=True)
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": INK2, "axes.labelcolor": INK2,
                         "xtick.color": INK2, "ytick.color": INK2, "font.family": "DejaVu Sans"})
    fig, axes = plt.subplots(2, 3, figsize=(11, 6.6), facecolor=SURF)
    for ax, (xm, am, title, unit, floor) in zip(axes.flat, PANELS):
        ax.set_facecolor(SURF)
        cols = [arm(am) if am else None, col(f"{D}/spec_tlb_x86.csv", "benchmark", xm),
                col(f"{D}/server_tlb_x86.csv", "workload", xm)]
        labels, xs = [], []
        for i, ((name, color), vals) in enumerate(zip(POP, cols)):
            if vals is None:
                continue
            v = sorted(vals.values())
            below = sum(1 for x in v if x < floor)
            n = len(v)
            for j, x in enumerate(v):
                jit = (j / max(n - 1, 1) - 0.5) * 0.36
                y = max(x, floor)
                ax.plot(i + jit, y, "o", ms=5, mfc=(SURF if x < floor else color), mec=color, mew=1.2,
                        zorder=3)
            med = st.median(v)
            ax.plot([i - 0.28, i + 0.28], [max(med, floor)] * 2, color=INK, lw=2, solid_capstyle="round", zorder=4)
            ax.annotate(f"{med:.3g}", (i + 0.3, max(med, floor)), va="center", fontsize=8, color=INK)
            labels.append(f"{name}\nn={n}" + (f", {below}<floor" if below else ""))
            xs.append(i)
        ax.set_yscale("log")
        ax.set_xticks(xs, labels, fontsize=8)
        ax.set_xlim(-0.6 if am else 0.4, 2.75)
        ax.set_title(title, fontsize=10, color=INK, loc="left")
        ax.set_ylabel(unit)
        ax.grid(axis="y", color=GRID, lw=0.6, which="major")
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    fig.tight_layout()
    p = f"{D}/plots/tlb_hierarchy.png"
    fig.savefig(p, dpi=160, facecolor=SURF)
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
