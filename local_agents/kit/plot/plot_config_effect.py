#!/usr/bin/env python3
"""plot_config_effect.py — what the SMT / window-length caveat was actually worth.

Every cross-campaign figure used to carry a prose caveat: the agentic campaign ran SMT-ON on
20 logical CPUs at 2 s windows, while SPEC ran SMT-off on 8 cores at 100 ms. On 2026-08-07/08
the agentic replays were re-captured on the SPEC configuration, which turns that caveat into a
measurement.

CONFOUND CONTROL — the whole point of this figure. The matched capture covers 12 tasks and the
legacy one covers 2, so comparing the two populations wholesale would mix a CONFIGURATION change
with a TASK-SET change. This figure therefore uses only the two tasks present in BOTH captures
(babel, fmtlib), replayed from the same trajectories through the same kit. The only thing that
differs is the configuration.

    /home/thu/miniforge3/envs/infersuite-full/bin/python local_agents/kit/plot/plot_config_effect.py

Output: local_agents/SWE_iso8/plots/agentic_config_effect.png (+ values JSON beside it).
"""
from __future__ import annotations

import json
import os
import re
import statistics as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

SPEC_INFRA = os.path.expanduser("~/spec26-infra/infra")
MATCHED = os.path.join(SPEC_INFRA, "comparison_iso8.json")
LEGACY = os.path.join(SPEC_INFRA, "comparison.json")
OUT = os.path.expanduser("~/InferSuite/local_agents/SWE_iso8/plots")

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["DejaVu Serif"], "mathtext.fontset": "dejavuserif",
    "font.size": 11, "figure.dpi": 150, "savefig.dpi": 300, "savefig.bbox": "tight",
    "axes.grid": True, "grid.color": "#cccccc", "grid.linewidth": 0.5, "grid.alpha": 0.6,
    "axes.axisbelow": True,
})
C_OLD, C_NEW = "#9aa8b2", "#159f77"
L1COLS = [("retiring", "Retiring", "#009E73"), ("fe_bound", "Frontend-bound", "#0072B2"),
          ("bad_spec", "Bad speculation", "#D55E00"), ("be_bound", "Backend-bound", "#E69F00")]

PAIR = {"babel", "fmtlib"}      # the only tasks in BOTH captures


def task(r):
    return re.sub(r"^glm_(replay_)?swe_", "", r["name"].split("/")[0])


def pop(path):
    c = json.load(open(path))
    return [r for r in c["agentic"]
            if "glm_replay_swe_" in r["dir"] and len(r["groups"]) == 1 and task(r) in PAIR]


def med(rows, k, tma=False):
    src = "tma_l1" if tma else "metrics"
    v = [r[src].get(k) for r in rows if r[src].get(k) is not None]
    return (st.median(v), len(v)) if v else (None, 0)


LEG, MAT = pop(LEGACY), pop(MATCHED)
assert LEG and MAT, "both captures must contain babel + fmtlib replays"

# Grouped so the reader sees WHY each moves: the sibling thread competed for exactly these.
GROUPS = [
    ("Instruction supply\n(shared with the SMT sibling)",
     [("L1I_MPKI", "L1I MPKI"), ("MITE_pct", "MITE %"), ("DSB_pct", "DSB %"), ("MS_pct", "MS %")]),
    ("Data side\n(shared caches)",
     [("L1D_MPKI", "L1D MPKI"), ("LLC_MPKI", "LLC MPKI"), ("DRAM_read_GBs", "DRAM GB/s"),
      ("MLP", "MLP"), ("AMAT_cyc", "AMAT")]),
    ("Throughput & system",
     [("IPC", "IPC"), ("brMPKI", "branch MPKI"), ("kernel_pct", "kernel %")]),
]
ROWS = [(k, lab, title) for title, ks in GROUPS for k, lab in ks]

fig, (ax, axr) = plt.subplots(1, 2, figsize=(14.6, 7.2), gridspec_kw={"width_ratios": [1.35, 1]})
Y, labels, vals, bands = [], [], {}, []
y = 0
for title, ks in GROUPS:
    y0 = y
    for k, lab in ks:
        a, na = med(LEG, k)
        b, nb = med(MAT, k)
        if a is None or b is None or a == 0:
            continue
        pct = (b / a - 1) * 100
        col = C_NEW if pct > 0 else "#b03a2e"
        ax.plot([0, pct], [y, y], color=col, lw=2.0, zorder=2, alpha=0.55)
        ax.plot([pct], [y], marker="o", ms=8, color=col, zorder=3)
        ax.text(pct + (1.6 if pct >= 0 else -1.6), y, f"{pct:+.1f}%", va="center",
                ha="left" if pct >= 0 else "right", fontsize=9,
                color=col, fontweight="bold")
        labels.append(lab)
        Y.append(y)
        vals[k] = {"legacy_median": a, "legacy_n": na, "matched_median": b, "matched_n": nb,
                   "pct_change": pct}
        y += 1
    bands.append((title, y0, y - 1))
    y += 0.9                      # gap between metric groups
ax.axvline(0, color="#5a6b78", lw=1.2)
ax.set_yticks(Y)
ax.set_yticklabels(labels, fontsize=9.5)
ax.invert_yaxis()
ax.set_xlim(-26, 26)
ax.set_xlabel("change when the SMT sibling is removed and windows drop 2 s → 100 ms  (%)")
ax.set_title("Same two tasks, same trajectories — only the configuration differs", fontsize=11.5)
# Group headings: without them the three bands read as one list and the reader cannot see
# that the shared-resource metrics all move the same way.
for title, y0, y1 in bands:
    ax.text(-0.235, (y0 + y1) / 2, title, transform=ax.get_yaxis_transform(), ha="center",
            va="center", fontsize=8.6, color="#1b6ca8", fontweight="bold", clip_on=False)
ax.text(0.5, 1.045, "n = 2 replay episodes per metric (babel, fmtlib) · IPC: 14",
        transform=ax.transAxes, ha="center", va="bottom", fontsize=8.4, color="#5a6b78")

# TMA: the shape is what has to hold, and it does
x = np.arange(len(L1COLS))
w = 0.36
lv = [med(LEG, k, tma=True)[0] for k, _l, _c in L1COLS]
mv = [med(MAT, k, tma=True)[0] for k, _l, _c in L1COLS]
axr.bar(x - w / 2, lv, w, color=C_OLD, label="SMT-ON, 2 s windows (retired)")
axr.bar(x + w / 2, mv, w, color=C_NEW, label="SMT-off cores 4–11, 100 ms (matched)")
for xi, (a, b) in enumerate(zip(lv, mv)):
    axr.text(xi - w / 2, a + 0.6, f"{a:.1f}", ha="center", fontsize=8.6, color="#5a6b78")
    axr.text(xi + w / 2, b + 0.6, f"{b:.1f}", ha="center", fontsize=8.6, color=C_NEW,
             fontweight="bold")
    axr.text(xi, max(a, b) + 3.0, f"{b-a:+.1f} pp", ha="center", fontsize=8.4, color="#333")
axr.set_xticks(x)
axr.set_xticklabels([lab for _k, lab, _c in L1COLS], fontsize=9)
axr.set_ylabel("share of pipeline slots (%)")
axr.set_ylim(0, max(max(lv), max(mv)) * 1.3)
axr.legend(fontsize=9, frameon=False, loc="upper right")
axr.set_title("TMA Level 1 — the shape barely moves", fontsize=11.5)
fig.suptitle("What the SMT / window-length caveat was worth — measured, not asserted",
             fontsize=13, y=0.99)
fig.text(0.99, 0.002, "Intel Xeon w5-3425 · SWE-agent × GLM-5.2 deterministic replays "
                      "(model never called) · dedicated counter group per episode",
         ha="right", va="bottom", fontsize=7, color="#888888")
fig.tight_layout(rect=(0, 0.015, 1, 0.95))
os.makedirs(OUT, exist_ok=True)
p = os.path.join(OUT, "agentic_config_effect.png")
fig.savefig(p)
plt.close(fig)
vals["tma_l1"] = {k: {"legacy": a, "matched": b, "delta_pp": b - a}
                  for (k, _l, _c), a, b in zip(L1COLS, lv, mv)}
vals["_populations"] = {"tasks": sorted(PAIR), "legacy_episodes": len(LEG),
                        "matched_episodes": len(MAT)}
json.dump(vals, open(os.path.join(OUT, "config_effect_values.json"), "w"), indent=1)
print(p)
print(f"  IPC {vals['IPC']['legacy_median']:.3f} -> {vals['IPC']['matched_median']:.3f} "
      f"({vals['IPC']['pct_change']:+.1f}%)")
