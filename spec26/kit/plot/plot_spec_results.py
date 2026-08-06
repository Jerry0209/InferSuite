#!/usr/bin/env python3
"""plot_spec_results.py — the SPEC CPU 2026 baseline figures, in the thesis figure family.

Run with the environment that carries matplotlib (matplotlib is not in the repo .venv):

    /home/thu/miniforge3/envs/infersuite-full/bin/python spec26/kit/plot/plot_spec_results.py

Output: spec26/plots/ (thesis-ready) + spec26/plots/values_dump.json, which carries every
number any figure displays so a reader can check a bar without reading pixels — the same
audit contract local_agents/kit/plot/plot_glm_results.py holds itself to.

Two populations appear in the comparison figures and they are never merged:
  SPEC       26 episodes, one ref command line each, 1 copy on 1 isolated SMT-free core.
  agentic    SWE-agent x GLM-5.2 (local_agents/SWE_clean). Split by instrument —
             7 full 8-group rotation episodes (same instrument as SPEC; primary) and
             19 dedicated-single-group replays (independent corroboration).
Only the eight CERTIFIED shared counter groups feed any SPEC-vs-agentic number.
"""
from __future__ import annotations

import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from spec_common import (  # noqa: E402
    C_AGENT, C_FP, C_INT, C_SPEC, L1COLS, OUT, UOPCOLS,
    agentic_split, cat_divider, cat_sorted, comparison, duty, episodes, n_int, save, series,
    slots_per_cycle, txtcol, windows,
)

EPS = episodes()
WIN = {e["benchmark"]: windows(e["dir"]) for e in EPS}
CMP = comparison()
ROT, REP = agentic_split(CMP)
# SPEC-only figures use all 11 counter groups (the richest SPEC number). Every SPEC-vs-agentic
# figure must instead use SPEC8 — the same episodes reloaded over the eight CERTIFIED shared
# groups, because the agentic campaign only ever rotated those eight. IPC is the metric that
# actually moves: it is total instructions over total cycles across ALL windows, so a
# different group mix samples a different part of the program (26-episode median 2.427 over
# 11 groups vs 2.418 over 8). Per-event ratios are immune — their denominators are already
# co-counted per group — but mixing the two sources in one bar chart is indefensible anyway.
SPEC8 = CMP["spec"]
VALUES: dict = {"n_spec": len(EPS), "n_agentic_rotation": len(ROT), "n_agentic_replay": len(REP)}
print(f"SPEC episodes {len(EPS)} · agentic rotation {len(ROT)} · agentic replay {len(REP)}")
os.makedirs(OUT, exist_ok=True)


def m(e: dict, k: str):
    return e["metrics"].get(k)


def bcol(e: dict) -> str:
    return C_FP if e["fp"] else C_INT


def med(rows: list[dict], k: str):
    v = [r["metrics"].get(k) for r in rows]
    v = [x for x in v if x is not None]
    return statistics.median(v) if v else None


def medtma(rows: list[dict], k: str):
    v = [r["tma_l1"].get(k) for r in rows if r["tma_l1"].get(k) is not None]
    return statistics.median(v) if v else None


# ================= Fig 1: what was captured ======================================================
# The suite before any microarchitecture: how long each benchmark ran and how many windows that
# bought. A metric's credibility here is bounded by its window count, so the count is a figure,
# not a footnote.
order = cat_sorted(EPS)
fig, (a1, a2) = plt.subplots(1, 2, figsize=(13.8, 8.2), sharey=True)
Y = np.arange(len(order))
a1.barh(Y, [e["wall_s"] for e in order], color=[bcol(e) for e in order], height=0.68)
for y, e in enumerate(order):
    a1.text(e["wall_s"] + 4, y, f"{e['wall_s']:.0f}s", va="center", fontsize=8)
a1.set_xlabel("episode wall time (s) — one ref command line, 1 copy")
a1.set_xlim(0, max(e["wall_s"] for e in order) * 1.14)
a1.invert_yaxis()
a1.set_yticks(Y)
a1.set_yticklabels([e["benchmark"] for e in order], fontsize=8.6)
a1.set_title("How long each benchmark ran", fontsize=11)
cat_divider(a1, order)

a2.barh(Y, [e["n_windows"] for e in order], color=[bcol(e) for e in order], height=0.68)
for y, e in enumerate(order):
    a2.text(e["n_windows"] + 25, y, f"{e['n_windows']}", va="center", fontsize=8)
a2.axvline(55, color="#c0392b", lw=1.2, ls="--")
a2.text(58, len(order) - 0.6, "MIN_WINDOWS = 55\n(5 full rotations)", fontsize=8, color="#c0392b",
        va="top")
a2.set_xlabel("100 ms counting windows captured")
a2.set_xlim(0, max(e["n_windows"] for e in order) * 1.14)
a2.set_title("How much counting that bought", fontsize=11)
cat_divider(a2, order)
fig.legend(handles=[Patch(color=C_INT, label=f"SPECrate integer ({n_int(EPS)})"),
                    Patch(color=C_FP, label=f"SPECrate floating-point ({len(EPS)-n_int(EPS)})")],
           ncol=2, frameon=False, fontsize=9.5, loc="upper center", bbox_to_anchor=(0.5, 0.965))
fig.suptitle(f"SPEC CPU 2026 baseline capture — {len(EPS)} benchmarks, "
             f"{sum(e['n_windows'] for e in EPS):,} windows "
             "(integer block, then floating-point, each by SPEC number)", fontsize=12.5, y=1.0)
save(fig, "spec_suite_overview.png")
def n_launched(e: dict) -> int:
    """Windows the kit LAUNCHED, from windows.tsv (one banked row per window).

    Not the same as n_windows, which counts windows that produced parseable counter values.
    The suite-wide gap is 2 windows: perf was reaped before it wrote anything. Reporting the
    launched count as if it were the counted count would overstate coverage by exactly those
    two, which is trivial — and reporting only the counted one hides that the gap exists.
    """
    p = os.path.join(e["dir"], "windows.tsv")
    return max(0, sum(1 for _ in open(p)) - 1) if os.path.exists(p) else e["n_windows"]


VALUES["capture"] = {e["benchmark"]: {"wall_s": e["wall_s"], "windows": e["n_windows"],
                                  "windows_launched": n_launched(e),
                                  "fp": e["fp"], "cmd_index": e["meta"].get("cmd_index"),
                                  "size": e["meta"].get("size")} for e in EPS}

# ================= Fig 2: the instrument checking itself =========================================
# Three independent statements about the capture, none of which uses the metric values:
#   (a) slots/cycle — continuous TMA against windowed cycles. Different counters, different
#       instruments; the answer must be the core's issue width (Golden Cove: 6).
#   (b) counting duty — perf's own elapsed over the window span. The ~20 ms per-window arm/tear
#       cost is a property of the tool, so it must be reported, not hidden.
#   (c) rotation balance — every group must get a fair share of windows, or a metric is
#       systematically sampled from a different part of the program than its neighbours.
sp = {e["benchmark"]: slots_per_cycle(e, WIN[e["benchmark"]]) for e in EPS}
dt = {e["benchmark"]: duty(WIN[e["benchmark"]], e["dir"]) for e in EPS}
fig, axes = plt.subplots(1, 3, figsize=(15.6, 5.6))
names = [e["benchmark"] for e in EPS]
X = np.arange(len(names))

ax = axes[0]
ax.axhline(6.0, color="#c0392b", lw=1.4)
ax.plot(X, [sp[n] for n in names], "o", color=C_SPEC, ms=5)
ax.set_xticks(X)
ax.set_xticklabels(names, rotation=90, fontsize=6.6)
ax.set_ylim(5.6, 6.4)
ax.set_ylabel("TMA slots / windowed cycle")
ax.set_title("(a) two instruments agree on the core", fontsize=11)
vals = [sp[n] for n in names if sp[n]]
ax.text(0.98, 0.10, "Golden Cove issue width = 6", color="#c0392b", fontsize=9, ha="right",
        transform=ax.transAxes)
ax.text(0.02, 0.93, f"range {min(vals):.2f}–{max(vals):.2f}\nover {len(vals)} episodes",
        transform=ax.transAxes, fontsize=8.5, color="#444", va="top")

ax = axes[1]
ax.bar(X, [100 * dt[n] for n in names], color=C_SPEC, width=0.7)
ax.axhline(100 * statistics.median([dt[n] for n in names]), color="#c0392b", lw=1.2, ls="--")
ax.set_xticks(X)
ax.set_xticklabels(names, rotation=90, fontsize=6.6)
ax.set_ylim(0, 100)
ax.set_ylabel("% of episode with counters installed")
ax.set_title("(b) counting duty at 100 ms windows", fontsize=11)
ax.text(0.03, 0.30, f"median {100*statistics.median([dt[n] for n in names]):.1f}%\n"
                    "~20 ms fixed perf setup per window,\nspent BETWEEN windows and\n"
                    "uncorrelated with program phase",
        transform=ax.transAxes, fontsize=8.5, color="#0d3f63", va="top",
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor="#cfd8dc", alpha=0.92))

# (c) rotation balance. A per-episode heatmap of 286 cells reads as one flat block — which is
# the right answer but shows nothing. One box per GROUP over the 26 episodes shows the same
# fact and shows its spread: every group must sit on 1/11 of the windows, or a metric is
# systematically sampled from a different part of the program than its neighbours.
ax = axes[2]
GORD = (EPS[0]["meta"].get("gorder") or "").split()
share = [[100.0 * e["windows_per_group"].get(g, 0) / e["n_windows"] for e in EPS] for g in GORD]
bp = ax.boxplot(share, widths=0.6, patch_artist=True, whis=(0, 100),
                medianprops=dict(color="#d95f02", lw=1.6))
for patch in bp["boxes"]:
    patch.set_facecolor(C_SPEC)
    patch.set_alpha(0.45)
    patch.set_edgecolor(C_SPEC)
ax.axhline(100 / len(GORD), color="#c0392b", lw=1.2, ls="--")
ax.set_xticks(range(1, len(GORD) + 1))
ax.set_xticklabels(GORD, rotation=90, fontsize=8)
ax.set_ylabel("% of the episode's windows")
ax.set_ylim(0, 16)
ax.set_title("(c) rotation balance across 26 episodes", fontsize=11)
ax.text(0.98, 0.93, f"uniform = {100/len(GORD):.1f}%  ({len(GORD)} groups)\n"
                    "box = IQR, whiskers = full range",
        transform=ax.transAxes, fontsize=8.5, color="#444", ha="right", va="top")
fig.suptitle("The instrument, verified against itself — no metric value is used on this figure",
             fontsize=12.5, y=1.0)
fig.tight_layout(rect=(0, 0.015, 1, 0.95))
save(fig, "spec_instrument.png")
VALUES["instrument"] = {"slots_per_cycle": sp, "duty": dt,
                        "slots_per_cycle_range": [min(vals), max(vals)],
                        "duty_median": statistics.median([dt[n] for n in names])}

# ================= Fig 3: TMA level 1 ============================================================
rows = cat_sorted(EPS)
fig, ax = plt.subplots(figsize=(9.6, 0.42 * len(rows) + 2.4))
Y = np.arange(len(rows))
left = np.zeros(len(rows))
for key, lab, col in L1COLS:
    v = np.array([e["tma"]["l1"][key] for e in rows])
    ax.barh(Y, v, left=left, color=col, height=0.66, label=lab, edgecolor="white", linewidth=0.7)
    for y, (l, vv) in enumerate(zip(left, v)):
        if vv >= 7:
            ax.text(l + vv / 2, y, f"{vv:.0f}", ha="center", va="center", fontsize=7.6,
                    color=txtcol(col), fontweight="bold")
    left += v
ax.set_yticks(Y)
ax.set_yticklabels([e["benchmark"] for e in rows], fontsize=8.6)
ax.invert_yaxis()
ax.set_xlim(0, 100)
ax.grid(axis="x")
cat_divider(ax, rows)
ax.set_xlabel("pipeline slots (%) — continuous census, whole episode, zero GP counters")
ax.legend(ncol=4, fontsize=9, loc="upper center", bbox_to_anchor=(0.5, -0.055), frameon=False)
ax.set_title("TMA Level 1 — integer block, then floating-point", fontsize=12, pad=10)
save(fig, "spec_tma_l1.png")
VALUES["tma_l1"] = {e["benchmark"]: e["tma"]["l1"] for e in EPS}

# ================= Fig 4: TMA level 2 ============================================================
L2COLS = [("light_ops", "Light ops", "#009E73"), ("heavy_ops", "Heavy ops", "#00614a"),
          ("fetch_lat", "Fetch latency", "#0072B2"), ("fetch_bw", "Fetch bandwidth", "#63a7d4"),
          ("br_mispredict", "Branch mispredict", "#D55E00"),
          ("machine_clears", "Machine clears", "#8c3b00"),
          ("mem_bound", "Memory-bound", "#E69F00"), ("core_bound", "Core-bound", "#8a6100")]
fig, ax = plt.subplots(figsize=(10.4, 0.42 * len(rows) + 2.6))
left = np.zeros(len(rows))
for key, lab, col in L2COLS:
    v = np.array([max(0.0, e["tma"]["l2"][key]) for e in rows])
    ax.barh(Y, v, left=left, color=col, height=0.66, label=lab, edgecolor="white", linewidth=0.6)
    for y, (l, vv) in enumerate(zip(left, v)):
        if vv >= 9:
            ax.text(l + vv / 2, y, f"{vv:.0f}", ha="center", va="center", fontsize=7.4,
                    color=txtcol(col), fontweight="bold")
    left += v
ax.set_yticks(Y)
ax.set_yticklabels([e["benchmark"] for e in rows], fontsize=8.6)
ax.invert_yaxis()
ax.set_xlim(0, 100)
ax.grid(axis="x")
cat_divider(ax, rows)
ax.set_xlabel("pipeline slots (%) — L2 siblings computed as remainders, as in the agentic kit")
ax.legend(ncol=4, fontsize=8.5, loc="upper center", bbox_to_anchor=(0.5, -0.055), frameon=False)
ax.set_title("TMA Level 2 — which half of each L1 bucket carries the stall", fontsize=12, pad=10)
save(fig, "spec_tma_l2.png")
VALUES["tma_l2"] = {e["benchmark"]: e["tma"]["l2"] for e in EPS}

# ================= Fig 5: signature heatmap on ABSOLUTE scales ===================================
# Identical construction to the agentic signature figure: shade = position on a FIXED domain
# reference range, so a cell means the same thing in both campaigns and across both figures.
# The printed number is always the truth; the shade is only a reading aid.
COLS = [("IPC", "IPC", 0.0, 6.0, "{:.2f}"),
        ("brMPKI", "Branch MPKI", 0.0, 20.0, "{:.1f}"),
        ("DSB_pct", "DSB coverage %", 0.0, 100.0, "{:.0f}"),
        ("L1I_MPKI", "L1I MPKI", 0.0, 20.0, "{:.1f}"),
        ("L1D_MPKI", "L1D-load MPKI", 0.0, 40.0, "{:.1f}"),
        ("LLC_MPKI", "LLC MPKI", 0.0, 10.0, "{:.2f}"),
        ("AMAT_cyc", "AMAT (cyc)", 5.0, 50.0, "{:.1f}"),
        ("MLP", "MLP", 1.0, 16.0, "{:.1f}"),
        ("DRAM_read_GBs", "DRAM read GB/s", 0.0, 12.0, "{:.2f}"),
        ("kernel_pct", "kernel %", 0.0, 20.0, "{:.1f}")]
srows = sorted(EPS, key=lambda e: -(m(e, "IPC") or 0))
M = np.zeros((len(srows), len(COLS)))
for i, e in enumerate(srows):
    for j, (k, _l, lo, hi, _f) in enumerate(COLS):
        v = m(e, k)
        M[i, j] = np.nan if v is None else min(max((v - lo) / (hi - lo), 0), 1)
fig, ax = plt.subplots(figsize=(13.2, 0.42 * len(srows) + 3.0))
im = ax.imshow(M, aspect="auto", cmap="Purples", vmin=0, vmax=1)
for i, e in enumerate(srows):
    for j, (k, _l, _lo, _hi, fv) in enumerate(COLS):
        v = m(e, k)
        ax.text(j, i, "n/a" if v is None else fv.format(v), ha="center", va="center", fontsize=8.2,
                color="black" if (np.isnan(M[i, j]) or M[i, j] < 0.55) else "white")
ax.set_xticks(range(len(COLS)))
ax.set_xticklabels([f"{lab}\n[{lo:g}–{hi:g}]" for _k, lab, lo, hi, _f in COLS], fontsize=8.4)
ax.set_yticks(range(len(srows)))
ax.set_yticklabels([f"{e['benchmark']}{'  ·FP' if e['fp'] else ''}" for e in srows],
                   fontsize=8.4)
ax.grid(False)
ax.set_title("Per-benchmark hardware signature on absolute reference scales (sorted by IPC)",
             fontsize=12, pad=12)
cb = fig.colorbar(im, ax=ax, fraction=0.02, pad=0.015)
cb.set_label("position on the absolute scale (0 = low ref, 1 = high ref)", fontsize=9)
save(fig, "spec_signature.png")
VALUES["signature"] = {e["benchmark"]: {k: m(e, k) for k, *_x in COLS} for e in EPS}

# ================= Fig 6: instruction supply =====================================================
fig, (ax, ax2) = plt.subplots(1, 2, figsize=(14.2, 8.0), sharey=True,
                              gridspec_kw={"width_ratios": [1.55, 1]})
urows = cat_sorted(EPS)
Y = np.arange(len(urows))
left = np.zeros(len(urows))
for key, lab, col in UOPCOLS:
    v = np.array([m(e, key) or 0.0 for e in urows])
    ax.barh(Y, v, left=left, color=col, height=0.66, label=lab, edgecolor="white", linewidth=0.7)
    for y, (l, vv) in enumerate(zip(left, v)):
        if vv >= 8:
            ax.text(l + vv / 2, y, f"{vv:.0f}", ha="center", va="center", fontsize=7.6,
                    color=txtcol(col), fontweight="bold")
    left += v
ax.set_yticks(Y)
ax.set_yticklabels([e["benchmark"] for e in urows], fontsize=8.6)
ax.invert_yaxis()
ax.set_xlim(0, 100)
cat_divider(ax, urows)
ax.set_xlabel("share of delivered uops (%)")
ax.legend(ncol=4, fontsize=8.6, loc="upper center", bbox_to_anchor=(0.5, -0.06), frameon=False)
ax.set_title("Where uops come from", fontsize=11.5)

ax2.barh(Y, [m(e, "L1I_MPKI") or 0 for e in urows], color=[bcol(e) for e in urows], height=0.66)
for y, e in enumerate(urows):
    v = m(e, "L1I_MPKI") or 0
    ax2.text(v + 0.6, y, f"{v:.1f}", va="center", fontsize=7.8)
ax2.set_xlabel("L1I MPKI (L2 code reads / 1000 insn)")
ax2.set_xlim(0, max(m(e, "L1I_MPKI") or 0 for e in urows) * 1.2)
cat_divider(ax2, urows)
ax2.set_title("What it costs to feed them", fontsize=11.5)
fig.suptitle("Instruction supply — integer block, then floating-point (SPEC runs almost entirely out of the uop cache)",
             fontsize=12.5, y=0.995)
save(fig, "spec_uop_supply.png")
VALUES["uop_supply"] = {e["benchmark"]: {k: m(e, k) for k in
                                     ("DSB_pct", "MITE_pct", "MS_pct", "LSD_pct", "L1I_MPKI")}
                        for e in EPS}

# ================= Fig 7: the memory ladder ======================================================
PANELS = [("L1D_MPKI", "L1D-load MPKI", False), ("LLC_MPKI", "LLC (demand-load) MPKI", True),
          ("DRAM_read_GBs", "DRAM read bandwidth (GB/s)", False), ("MLP", "MLP (outstanding)", False)]
fig, axes = plt.subplots(2, 2, figsize=(14.4, 10.4))
rr = cat_sorted(EPS)
for axx, (k, lab, logx) in zip(axes.ravel(), PANELS):
    Yv = np.arange(len(rr))
    vals_ = [m(e, k) or 0.0 for e in rr]
    axx.barh(Yv, vals_, color=[bcol(e) for e in rr], height=0.68)
    if logx:
        axx.set_xscale("symlog", linthresh=0.01)
    for y, v in enumerate(vals_):
        axx.text(v * (1.08 if logx else 1.0) + (0 if logx else max(vals_) * 0.012), y,
                 f"{v:.2f}" if v < 10 else f"{v:.1f}", va="center", fontsize=7.4)
    axx.set_yticks(Yv)
    axx.set_yticklabels([e["benchmark"] for e in rr], fontsize=7.4)
    axx.invert_yaxis()
    cat_divider(axx, rr)
    axx.set_title(lab, fontsize=11)   # the title IS the axis label here; don't print it twice
axes[0][1].text(0.5, -0.135, "LLC_MPKI counts DEMAND loads that missed L3. Prefetch-friendly "
                "streaming code moves GB/s while reading ~0 here — read the DRAM panel for "
                "memory pressure.", transform=axes[0][1].transAxes, ha="center", fontsize=8.2,
                color="#a04000")
fig.suptitle("The memory ladder (integer block, then floating-point) — and why one rung must not be read as the whole ladder",
             fontsize=12.5, y=0.995)
fig.tight_layout(rect=(0, 0, 1, 0.97))
save(fig, "spec_memory_ladder.png")
VALUES["memory"] = {e["benchmark"]: {k: m(e, k) for k, *_x in PANELS} for e in EPS}

# ================= Fig 8: the landscape ==========================================================
# The agent appears on this figure, so BOTH axes must be comparable: IPC comes from the
# shared-8 reload on the SPEC side too, not from the 11-group episode value.
IPC8 = {r["name"]: r["metrics"]["IPC"] for r in SPEC8}
fig, ax = plt.subplots(figsize=(11.2, 7.6))
for e in EPS:
    x, y = IPC8[e["benchmark"]], e["tma"]["l1"]["be_bound"] + e["tma"]["l1"]["fe_bound"]
    ax.scatter(x, y, s=28 + 90 * np.sqrt(e["wall_s"] / max(q["wall_s"] for q in EPS)),
               color=bcol(e), alpha=0.85, edgecolor="white", linewidth=0.8, zorder=3)
    ax.annotate(e["benchmark"], (x, y), textcoords="offset points", xytext=(6, 4), fontsize=7.4,
                color="#333")
ag_ipc, ag_st = med(ROT, "IPC"), (medtma(ROT, "be_bound") + medtma(ROT, "fe_bound"))
ax.scatter([ag_ipc], [ag_st], marker="*", s=520, color=C_AGENT, edgecolor="white", linewidth=1.2,
           zorder=4, label=f"agentic median (n={len(ROT)} rotation episodes)")
ax.annotate("SWE-agent × GLM-5.2", (ag_ipc, ag_st), textcoords="offset points", xytext=(10, -14),
            fontsize=10, color=C_AGENT, fontweight="bold")
ax.set_xlabel("IPC (instructions per cycle)")
ax.set_ylabel("stalled pipeline slots (%) — TMA frontend-bound + backend-bound")
ax.set_title("The landscape: 26 SPEC benchmarks and where the agent sits in it", fontsize=12.5)
ax.legend(handles=[Patch(color=C_INT, label="SPECrate integer"),
                   Patch(color=C_FP, label="SPECrate floating-point"),
                   plt.Line2D([], [], marker="*", ls="", color=C_AGENT, ms=15,
                              label=f"agentic median (n={len(ROT)})")],
          fontsize=9.5, frameon=False, loc="lower left")
ax.text(0.99, 0.02, "marker area ∝ √(episode wall time)", transform=ax.transAxes, ha="right",
        fontsize=8.2, color="#777")
save(fig, "spec_landscape.png")
VALUES["landscape"] = {"agentic_median_IPC": ag_ipc, "agentic_median_stall_pct": ag_st}

# ================= Fig 9: the headline comparison ================================================
# Paired medians on a log axis (the ratios span 0.04x to 14x — a linear axis would show one bar).
# SPEC carries its full 26-episode range as a whisker; the agentic side carries its rotation
# range, and the dedicated-group replays are plotted as an independent second opinion.
CMPROWS = [("L1I_MPKI", "L1I MPKI", "/1000 insn"),
           ("kernel_pct", "kernel time", "% of cycles"),
           ("MITE_pct", "MITE (legacy decode)", "% of uops"),
           ("MS_pct", "microcode sequencer", "% of uops"),
           ("brMPKI", "branch MPKI", "/1000 insn"),
           ("LLC_MPKI", "LLC demand-miss MPKI", "/1000 insn"),
           ("MLP", "MLP", "outstanding"),
           ("AMAT_cyc", "AMAT", "cycles"),
           ("L1D_MPKI", "L1D-load MPKI", "/1000 insn"),
           ("DSB_pct", "DSB (uop cache)", "% of uops"),
           ("IPC", "IPC", "insn/cycle"),
           ("DRAM_read_GBs", "DRAM read BW", "GB/s")]


def rng(rows, k):
    v = [r["metrics"].get(k) for r in rows]
    v = [x for x in v if x is not None]
    return (min(v), max(v)) if v else (None, None)


fig, ax = plt.subplots(figsize=(12.6, 8.6))
Y = np.arange(len(CMPROWS))
h = 0.3
for i, (k, lab, unit) in enumerate(CMPROWS):
    s, a = med(SPEC8, k), med(ROT, k)
    slo, shi = rng(SPEC8, k)
    alo, ahi = rng(ROT, k)
    ax.barh(i - h / 2, s, height=h, color=C_SPEC, zorder=3)
    ax.barh(i + h / 2, a, height=h, color=C_AGENT, zorder=3)
    ax.plot([max(slo, 1e-3), max(shi, 1e-3)], [i - h / 2] * 2, color="#0d3f63", lw=1.1, zorder=4)
    ax.plot([max(alo, 1e-3), max(ahi, 1e-3)], [i + h / 2] * 2, color="#0b5c44", lw=1.1, zorder=4)
    rp = med(REP, k)
    if rp is not None:
        ax.plot([rp], [i + h / 2], marker="D", ms=4.5, color="#0b5c44", mfc="white", zorder=5)
    ratio = a / s if s else float("nan")
    # get_yaxis_transform() = (axes fraction in x, DATA coordinates in y). transAxes would
    # need the inverted axis undone by hand and silently prints every ratio against the
    # wrong row.
    ax.text(1.006, i, f"{ratio:>5.2f}×", transform=ax.get_yaxis_transform(),
            va="center", fontsize=9.5,
            color="#b03a2e" if ratio >= 2 else ("#1e8449" if ratio <= 0.5 else "#555"))
    VALUES.setdefault("comparison", {})[k] = {
        "spec_median": s, "spec_range": [slo, shi], "agentic_rotation_median": a,
        "agentic_rotation_range": [alo, ahi], "agentic_replay_median": rp,
        "ratio_agentic_over_spec": ratio}
ax.set_xscale("log")
ax.set_yticks(Y)
ax.set_yticklabels([f"{lab}\n({unit})" for _k, lab, unit in CMPROWS], fontsize=9)
ax.invert_yaxis()
ax.grid(axis="x", which="both")
ax.set_xlabel("median value (log scale) — the eight shared counter groups only")
ax.text(1.006, 1.015, "agent / SPEC", transform=ax.transAxes, fontsize=9, color="#333")
ax.legend(handles=[Patch(color=C_SPEC, label=f"SPEC CPU 2026 (n={len(SPEC8)})"),
                   Patch(color=C_AGENT, label=f"agentic, 8-group rotation (n={len(ROT)})"),
                   plt.Line2D([], [], marker="D", ls="", color="#0b5c44", mfc="white", ms=6,
                              label=f"agentic, dedicated-group replays (n={len(REP)}) — "
                                    "independent check")],
          fontsize=9.5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.075), ncol=3)
ax.set_title("Traditional compute vs agentic work: same instrument, same formulas, same machine",
             fontsize=12.5, pad=12)
save(fig, "spec_vs_agentic_metrics.png")

# ================= Fig 10: TMA comparison ========================================================
fig, (axa, axb) = plt.subplots(1, 2, figsize=(14.0, 5.4), gridspec_kw={"width_ratios": [1, 1.25]})
bars = [(f"SPEC CPU 2026\nmedian of {len(EPS)}", {k: med(EPS, "IPC") for k in ()},
         {k: statistics.median([e["tma"]["l1"][k] for e in EPS]) for k, *_x in L1COLS}),
        (f"agentic — rotation\nmedian of {len(ROT)}",
         {}, {k: medtma(ROT, k) for k, *_x in L1COLS}),
        (f"agentic — replays\nmedian of {len(REP)}",
         {}, {k: medtma(REP, k) for k, *_x in L1COLS})]
Y = np.arange(len(bars))
left = np.zeros(len(bars))
for key, lab, col in L1COLS:
    v = np.array([b[2][key] for b in bars])
    axa.barh(Y, v, left=left, color=col, height=0.55, label=lab, edgecolor="white", linewidth=0.8)
    for y, (l, vv) in enumerate(zip(left, v)):
        if vv >= 7:
            axa.text(l + vv / 2, y, f"{vv:.0f}", ha="center", va="center", fontsize=9,
                     color=txtcol(col), fontweight="bold")
    left += v
axa.set_yticks(Y)
axa.set_yticklabels([b[0] for b in bars], fontsize=9.5)
axa.invert_yaxis()
axa.set_xlim(0, 100)
axa.set_xlabel("pipeline slots (%)")
axa.legend(ncol=2, fontsize=8.8, loc="upper center", bbox_to_anchor=(0.5, -0.14), frameon=False)
axa.set_title("TMA Level 1 — the least SMT-sensitive view", fontsize=11.5)

# per-episode scatter: the medians above are not hiding a bimodal suite
axb.scatter([e["tma"]["l1"]["fe_bound"] for e in EPS], [e["tma"]["l1"]["be_bound"] for e in EPS],
            s=46, color=C_SPEC, alpha=0.85, edgecolor="white", linewidth=0.7, label="SPEC episode")
axb.scatter([r["tma_l1"]["fe_bound"] for r in ROT], [r["tma_l1"]["be_bound"] for r in ROT],
            s=70, color=C_AGENT, alpha=0.9, edgecolor="white", linewidth=0.7, marker="*",
            label="agentic rotation episode")
axb.scatter([r["tma_l1"]["fe_bound"] for r in REP], [r["tma_l1"]["be_bound"] for r in REP],
            s=26, facecolor="none", edgecolor=C_AGENT, linewidth=1.0, label="agentic replay episode")
lim = max(axb.get_xlim()[1], axb.get_ylim()[1])
axb.plot([0, lim], [0, lim], color="#bbb", lw=1, ls="--", zorder=0)
axb.text(lim * 0.72, lim * 0.78, "backend = frontend", fontsize=8.5, color="#999", rotation=45)
axb.set_xlabel("frontend-bound (% of slots)")
axb.set_ylabel("backend-bound (% of slots)")
axb.legend(fontsize=9, frameon=False, loc="upper right")
axb.set_title("Every episode, not just the medians", fontsize=11.5)
fig.suptitle("Where the pipeline slots go: SPEC stalls on the back end, the agent on the front end",
             fontsize=12.5, y=1.02)
save(fig, "spec_vs_agentic_tma.png")
VALUES["tma_compare"] = {
    "spec": {k: statistics.median([e["tma"]["l1"][k] for e in EPS]) for k, *_x in L1COLS},
    "agentic_rotation": {k: medtma(ROT, k) for k, *_x in L1COLS},
    "agentic_replay": {k: medtma(REP, k) for k, *_x in L1COLS}}

# ================= Fig 11: the frontend story, in distributions ==================================
# The headline claim is "the agent is frontend-bound and SPEC is not". A median bar can be an
# accident of one benchmark, so this shows the whole SPEC distribution with the agentic episodes
# drawn on top of it: the question is whether the agent lands INSIDE the SPEC suite's range.
FRONT = [("L1I_MPKI", "L1I MPKI", "log"), ("MITE_pct", "MITE (legacy decode) %", "linear"),
         ("DSB_pct", "DSB (uop cache) %", "linear"), ("kernel_pct", "kernel time %", "log")]
fig, axes = plt.subplots(1, 4, figsize=(15.4, 5.6))
for axx, (k, lab, scale) in zip(axes, FRONT):
    sv = [r["metrics"][k] for r in SPEC8 if r["metrics"].get(k) is not None]
    av = [r["metrics"][k] for r in ROT if r["metrics"].get(k) is not None]
    bv = [r["metrics"][k] for r in REP if r["metrics"].get(k) is not None]
    axx.boxplot([sv], orientation="vertical", widths=0.42, positions=[0], patch_artist=True,
                boxprops=dict(facecolor=C_SPEC, alpha=0.35, edgecolor=C_SPEC),
                medianprops=dict(color="#d95f02", lw=2), whis=(5, 95), showfliers=False)
    axx.scatter(np.random.default_rng(7).normal(0, 0.055, len(sv)), sv, s=16, color=C_SPEC,
                alpha=0.75, zorder=3)
    axx.scatter(np.random.default_rng(9).normal(1, 0.055, len(av)), av, s=52, color=C_AGENT,
                marker="*", zorder=3)
    axx.scatter(np.random.default_rng(11).normal(1, 0.075, len(bv)), bv, s=20, facecolor="none",
                edgecolor=C_AGENT, zorder=3)
    if scale == "log":
        axx.set_yscale("log")
    axx.set_xticks([0, 1])
    axx.set_xticklabels([f"SPEC\n(n={len(sv)})", f"agentic\n(rot {len(av)} · replay {len(bv)})"],
                        fontsize=9)
    axx.set_xlim(-0.5, 1.5)
    axx.set_title(lab, fontsize=11)
    # The honest statement is a RANK, not a "beyond the range". SPEC's spread is enormous
    # (L1I MPKI 0.03-93), so almost anything lands inside it; what matters is WHERE. Report
    # how many of the 26 benchmarks are more extreme than the agentic median, in the
    # direction that means "worse instruction supply".
    amed = statistics.median(av)
    worse = sum(1 for x in sv if (x < amed if k == "DSB_pct" else x > amed))
    pctl = 100.0 * sum(1 for x in sv if x <= amed) / len(sv)
    axx.text(0.5, -0.20, f"agentic median = SPEC p{pctl:.0f}\n"
                         f"{worse}/{len(sv)} SPEC benchmarks are more extreme",
             transform=axx.transAxes, ha="center", fontsize=8.4, color="#555")
    VALUES.setdefault("frontend", {})[k] = {"spec_min": min(sv), "spec_max": max(sv),
                                            "spec_median": statistics.median(sv),
                                            "agentic_rotation": av, "agentic_replay": bv,
                                            "agentic_rotation_median": amed,
                                            "spec_percentile_of_agentic_median": pctl,
                                            "n_spec_more_extreme": worse}
fig.legend(handles=[plt.Line2D([], [], marker="o", ls="", color=C_SPEC, ms=6,
                               label="one SPEC benchmark"),
                    plt.Line2D([], [], marker="*", ls="", color=C_AGENT, ms=12,
                               label="agentic episode — 8-group rotation"),
                    plt.Line2D([], [], marker="o", ls="", mfc="none", color=C_AGENT, ms=6,
                               label="agentic episode — dedicated-group replay")],
           ncol=3, frameon=False, fontsize=9.5, loc="lower center", bbox_to_anchor=(0.5, 0.015))
fig.suptitle("Instruction supply and system time: the agent sits in the SPEC suite's tail, "
             "not in its middle", fontsize=12.5, y=1.0)
fig.tight_layout(rect=(0, 0.10, 1, 0.94))
save(fig, "spec_vs_agentic_frontend.png")

# ================= Fig 12: per-window distributions across the suite =============================
# The episode-level figures are sums. This is the layer underneath them: every 100 ms window,
# so a benchmark that averages 1.6 IPC because it alternates 0.5 and 2.1 stops looking steady.
GRID = ["IPC", "DSB_pct", "MITE_pct", "L1I_MPKI", "brMPKI", "L1D_MPKI",
        "LLC_MPKI", "MLP", "stalls_l3_miss_pct", "bound_on_loads_pct", "ports_0_pct", "kernel_pct"]
gorder = cat_sorted(EPS)
fig, axes = plt.subplots(3, 4, figsize=(19.6, 15.2))
for axx, k in zip(axes.ravel(), GRID):
    data, labs, cols = [], [], []
    for e in gorder:
        _t, v = series(WIN[e["benchmark"]], k)
        if len(v) >= 5:
            data.append(v)
            labs.append(e["benchmark"])
            cols.append(bcol(e))
    bp = axx.boxplot(data, orientation="horizontal", widths=0.62, patch_artist=True, whis=(5, 95),
                     showfliers=False, medianprops=dict(color="#d95f02", lw=1.4))
    for patch, c in zip(bp["boxes"], cols):
        patch.set_facecolor(c)
        patch.set_alpha(0.45)
        patch.set_edgecolor(c)
    axx.set_yticks(range(1, len(labs) + 1))
    axx.set_yticklabels(labs, fontsize=6.8)
    axx.invert_yaxis()
    # boxplot positions start at 1, so the INT|FP boundary shifts by one
    cat_divider(axx, [e for e in gorder if e["benchmark"] in set(labs)], offset=1, label=False)
    if k in ("L1I_MPKI", "LLC_MPKI", "brMPKI", "kernel_pct"):
        # symlog spans zero symmetrically by default and draws a negative decade that no
        # rate can occupy; clamp it back to the physical domain.
        axx.set_xscale("symlog", linthresh=0.01)
        axx.set_xlim(left=0)
    axx.set_title(k, fontsize=10.5)
    axx.tick_params(axis="x", labelsize=8)
fig.legend(handles=[Patch(color=C_INT, alpha=0.45, label="SPECrate integer"),
                    Patch(color=C_FP, alpha=0.45, label="SPECrate floating-point")],
           ncol=2, frameon=False, fontsize=11, loc="upper center", bbox_to_anchor=(0.5, 0.983))
fig.suptitle("Per-window distributions — integer block, then floating-point · box = IQR, "
             "orange = median, whiskers = 5–95 %, one box per benchmark (100 ms windows)",
             fontsize=13, y=0.997)
fig.tight_layout(rect=(0, 0, 1, 0.973))
save(fig, "spec_window_grid.png")

# ================= Fig 13: phase behaviour =======================================================
# Why the distribution layer exists at all: some benchmarks are a single steady state and some
# walk through several. The episode number is the same object in both cases and hides the
# difference; a timeline does not.
PHASE = ["721.gcc_r", "723.llvm_r", "710.omnetpp_r", "709.cactus_r", "749.fotonik3d_r",
         "782.lbm_r"]
byname = {e["benchmark"]: e for e in EPS}
fig, axes = plt.subplots(len(PHASE), 1, figsize=(13.4, 2.05 * len(PHASE)), sharex=False)
for axx, nm in zip(axes, PHASE):
    e = byname[nm]
    t, v = series(WIN[e["benchmark"]], "IPC")
    axx.plot(t, v, lw=0.55, color=bcol(e), alpha=0.9)
    ep = m(e, "IPC")
    axx.axhline(ep, color="#d95f02", lw=1.2, ls="--")
    axx.text(0.995, 0.9, f"{nm} — episode IPC {ep:.2f}, per-window {np.min(v):.2f}–{np.max(v):.2f}",
             transform=axx.transAxes, ha="right", va="top", fontsize=9.2)
    axx.set_ylabel("IPC", fontsize=9)
    axx.set_xlim(0, t.max())
    axx.tick_params(labelsize=8)
axes[-1].set_xlabel("seconds into the episode (one point per 100 ms window)")
fig.suptitle("Phases are real: the episode number is a sum over states, not a description of one",
             fontsize=12.5, y=0.998)
fig.tight_layout(rect=(0, 0, 1, 0.975))
save(fig, "spec_phase_timelines.png")
VALUES["phases"] = {nm: {"episode_IPC": m(byname[nm], "IPC"),
                         "window_min": float(np.min(series(WIN[byname[nm]["benchmark"]], "IPC")[1])),
                         "window_max": float(np.max(series(WIN[byname[nm]["benchmark"]], "IPC")[1]))}
                    for nm in PHASE}

# ================= INT vs FP: the categorical contrast, banked =================================
# The figures are ordered INT-then-FP precisely so this contrast is visible before a number is
# read. Bank it so the deck prose and the report quote a computed value, never an eyeballed one.
def int_fp(getter):
    i = [v for e in EPS if not e["fp"] and (v := getter(e)) is not None]
    f = [v for e in EPS if e["fp"] and (v := getter(e)) is not None]
    if not i or not f:
        return None
    mi, mf = statistics.median(i), statistics.median(f)
    return {"int_median": mi, "fp_median": mf, "int_n": len(i), "fp_n": len(f),
            "int_over_fp": (mi / mf) if mf else None,
            "int_range": [min(i), max(i)], "fp_range": [min(f), max(f)]}


VALUES["int_vs_fp"] = {
    **{f"tma_{k}": int_fp(lambda e, k=k: e["tma"]["l1"][k])
       for k in ("retiring", "fe_bound", "bad_spec", "be_bound")},
    **{k: int_fp(lambda e, k=k: m(e, k))
       for k in ("IPC", "brMPKI", "DSB_pct", "MITE_pct", "L1I_MPKI", "L1D_MPKI", "LLC_MPKI",
                 "MLP", "DRAM_read_GBs", "kernel_pct")},
    "n_badspec_over_10pct": {
        "int": sum(1 for e in EPS if not e["fp"] and e["tma"]["l1"]["bad_spec"] > 10),
        "fp": sum(1 for e in EPS if e["fp"] and e["tma"]["l1"]["bad_spec"] > 10)},
    "n_dram_over_4GBs": {
        "int": sum(1 for e in EPS if not e["fp"] and (m(e, "DRAM_read_GBs") or 0) > 4),
        "fp": sum(1 for e in EPS if e["fp"] and (m(e, "DRAM_read_GBs") or 0) > 4)},
}
iv = VALUES["int_vs_fp"]
print(f"  INT vs FP — branch MPKI {iv['brMPKI']['int_median']:.2f} vs "
      f"{iv['brMPKI']['fp_median']:.3f} ({iv['brMPKI']['int_over_fp']:.0f}x) · "
      f"bad-spec {iv['tma_bad_spec']['int_median']:.1f}% vs {iv['tma_bad_spec']['fp_median']:.1f}% · "
      f"backend {iv['tma_be_bound']['int_median']:.1f}% vs {iv['tma_be_bound']['fp_median']:.1f}%")

# ================= audit dump ====================================================================
json.dump(VALUES, open(os.path.join(OUT, "values_dump.json"), "w"), indent=1, default=float)
print(f"  {os.path.join(OUT, 'values_dump.json')}")
