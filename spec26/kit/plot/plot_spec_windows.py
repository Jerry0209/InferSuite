#!/usr/bin/env python3
"""plot_spec_windows.py — the per-window layer: one distribution and one timeline per
(benchmark, metric), for the galleries.

    /home/thu/miniforge3/envs/infersuite-full/bin/python spec26/kit/plot/plot_spec_windows.py [bench ...]

Output goes to SPEC_WIN (default ~/spec26-infra/infra/plots/windows) — OUTSIDE this repo, on
purpose: ~1.8 k PNGs is campaign data, not a tracked figure set, exactly like the agentic
l3_study per-window plots under the gitignored local_agents/*/data trees. Only the galleries
built from them get published.

What a window is here, precisely
--------------------------------
One 100 ms interval in which exactly ONE counter group was installed. So a metric's
distribution is over the windows that carried ITS group — roughly 1/11 of the episode's
windows, spread across the whole run by the shuffled rotation, never a contiguous slice.
IPC is the exception: cycles and instructions ride in every group, so IPC has every window.

The distribution median is NOT the episode value. The episode value is a ratio of sums; this
is a distribution of per-window ratios. Where they disagree the program has phases, and that
disagreement is the point of the figure — see spec_phase_timelines.png.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from spec_common import (  # noqa: E402
    C_FP, C_INT, GALLERY_ORDER, WINDOW_METRICS, WINOUT, episodes, series, windows,
)

plt.rcParams.update({"savefig.dpi": 115})

ONLY = set(sys.argv[1:])
EPS = [e for e in episodes() if not ONLY or e["short"] in ONLY or e["benchmark"] in ONLY]
os.makedirs(WINOUT, exist_ok=True)
print(f"per-window figures for {len(EPS)} benchmark(s) -> {WINOUT}")

made = 0
for e in EPS:
    rows = windows(e["dir"])
    col = C_FP if e["fp"] else C_INT
    b = e["short"]
    n_metrics = 0
    for k in GALLERY_ORDER:
        t, v = series(rows, k)
        if len(v) < 5:
            continue          # fewer than 5 windows is not a distribution, it is a rumour
        n_metrics += 1
        unit = WINDOW_METRICS[k][1]
        grp = WINDOW_METRICS[k][0]
        ep = e["metrics"].get(k)

        # ---- distribution -------------------------------------------------------------
        fig, ax = plt.subplots(figsize=(4.4, 3.1))
        bp = ax.boxplot([v], orientation="vertical", widths=0.45, patch_artist=True,
                        whis=(5, 95), showfliers=True,
                        flierprops=dict(marker="o", ms=2.4, mfc="none", mec="#999"),
                        medianprops=dict(color="#d95f02", lw=1.8))
        bp["boxes"][0].set_facecolor(col)
        bp["boxes"][0].set_alpha(0.4)
        bp["boxes"][0].set_edgecolor(col)
        ax.scatter([1], [float(np.mean(v))], marker="^", s=42, color="#333", zorder=4)
        if ep is not None:
            ax.axhline(ep, color="#1b6ca8", lw=1.2, ls="--")
            ax.text(1.42, ep, " episode", color="#1b6ca8", fontsize=7.5, va="center", ha="left")
        ax.set_xticks([1])
        ax.set_xticklabels([f"{len(v)} windows\n(group: {grp})"], fontsize=8)
        ax.set_ylabel(unit, fontsize=8.5)
        ax.tick_params(axis="y", labelsize=8)
        ax.set_title(f"{b} — {k}", fontsize=10)
        ax.text(0.02, 0.985, f"median {np.median(v):.3g}\nIQR {np.percentile(v,25):.3g}–"
                             f"{np.percentile(v,75):.3g}\n5–95% {np.percentile(v,5):.3g}–"
                             f"{np.percentile(v,95):.3g}",
                transform=ax.transAxes, fontsize=7.4, va="top", color="#555")
        fig.savefig(os.path.join(WINOUT, f"box_{b}_{k}.png"), bbox_inches="tight")
        plt.close(fig)

        # ---- timeline -----------------------------------------------------------------
        fig, ax = plt.subplots(figsize=(10.2, 2.5))
        ax.plot(t, v, lw=0.7, color=col, alpha=0.9, marker="." if len(v) < 120 else None, ms=3)
        if ep is not None:
            ax.axhline(ep, color="#1b6ca8", lw=1.1, ls="--")
        ax.set_xlim(0, max(t.max(), 1e-9))
        ax.set_xlabel("seconds into the episode", fontsize=8.5)
        ax.set_ylabel(unit, fontsize=8.5)
        ax.tick_params(labelsize=8)
        ax.set_title(f"{b} — {k} over the episode "
                     f"({len(v)} windows carrying group '{grp}')", fontsize=10)
        fig.savefig(os.path.join(WINOUT, f"timeline_{b}_{k}.png"), bbox_inches="tight")
        plt.close(fig)
        made += 2
    print(f"  {b:<12} {n_metrics:>2} metrics")

print(f"{made} figures written to {WINOUT}")
