#!/usr/bin/env python3
"""Fig 7  classification flowchart (raw files -> receipts -> tags -> two views -> label)
Fig 8a/8b  ⟨language × CPU-type⟩ matrices, process view and ownership view, current sweep state.
Data: local_agents/ML_typeid/cpu_matrix.tsv (typeid_cpu_matrix.py build)."""
import csv, collections, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = "/home/network/InferSuite-Jerry"
SURFACE, INK, INK2, INK3 = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8880"
CAT = {"BUILD": "#eda100", "TEST": "#1baf7a", "SEARCH": "#2a78d6"}
plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
                     "font.size": 9, "text.color": INK, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2,
                     "axes.edgecolor": "#d8d6cf", "axes.linewidth": 0.8})

# =============================== Fig 7: flowchart ===================================
fig, ax = plt.subplots(figsize=(11.5, 7.6))
ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")


def box(x, y, w, h, title, body="", fc="#ffffff", ec="#c9c6bd", tfs=9.5, bfs=8, lw=1.0):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.2",
                                fc=fc, ec=ec, lw=lw, zorder=2))
    ty = y + h - 2.6 if body else y + h / 2
    ax.text(x + w / 2, ty, title, ha="center", va="center", fontsize=tfs,
            fontweight="bold", color=INK, zorder=3)
    if body:
        ax.text(x + w / 2, y + (h - 3.2) / 2 - 0.4, body, ha="center", va="center",
                fontsize=bfs, color=INK2, zorder=3, linespacing=1.35)


def arrow(x0, y0, x1, y1, label="", lx=None, ly=None, color=INK2, ls="-", lfs=7.5, rad=0.0):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=11,
                                 lw=1.1, color=color, ls=ls, zorder=1,
                                 connectionstyle=f"arc3,rad={rad}"))
    if label:
        ax.text(lx if lx is not None else (x0 + x1) / 2, ly if ly is not None else (y0 + y1) / 2 + 1.6,
                label, ha="center", va="bottom", fontsize=lfs, color=color, zorder=3,
                bbox=dict(boxstyle="round,pad=0.15", fc=SURFACE, ec="none"))


# lane headers
ax.text(1, 97, "DURING REPLAY  (record only)", fontsize=9, color=INK3, fontweight="bold")
ax.text(1, 60.2, "AFTER REPLAY  (classify; re-runnable)", fontsize=9, color=INK3, fontweight="bold")
ax.plot([0, 100], [63.5, 63.5], color="#d8d6cf", lw=0.8, ls="--")

# --- top lane: three raw files -----------------------------------------------------
box(2, 76, 30, 16, "taskstats.tsv — exit receipts",
    "one row per process death\ncomm · pid · ppid · utime+stime (exact) · etime\nkernel netlink · nothing too short to see",
    fc="#eef6ff", ec="#2a78d6", lw=1.3)
box(35, 76, 30, 16, "cpustat_scope2.tsv — fence total",
    "container cgroup cpu.stat usage_usec\n10 Hz · exact kernel accounting\n(denominator: coverage %)",
    fc="#f4f4f2")
box(68, 76, 30, 16, "cmdlog.tsv — 2 Hz argv",
    "pid + full command line while alive\nhelper only: `cargo test` vs `cargo build`\n(comm is truncated to 15 chars)",
    fc="#f4f4f2")
ax.text(1, 94.2, "sweagent run-replay · no model call · four pollers at nice 19", fontsize=8,
        color=INK3, style="italic")

# --- bottom lane ------------------------------------------------------------------
# step 1: fence membership + fine tag
box(2, 42, 30, 15, "1 · fence + fine tag",
    "in-fence if ppid chain reaches a pid ever\nseen in the tool cgroup\nname → fine tag (fixed table, first hit wins):\ncompile · build-drv · pkg · test-run · runtime\nlint · search · vcs · scaffold · other",
    bfs=7.6)
arrow(17, 76, 17, 57.5, "receipts", lx=13.2, ly=68)
ax.plot([50, 50], [76, 63.8], color=INK2, lw=1.1, zorder=1)
ax.plot([50, 99, 99], [63.8, 63.8, 34.5], color=INK2, lw=1.1, zorder=1)
arrow(99, 34.5, 92, 32.5, "")
ax.text(75, 65.2, "fence total = denominator (coverage %, classified %)", fontsize=7.5, color=INK2, ha="center",
        bbox=dict(boxstyle="round,pad=0.15", fc=SURFACE, ec="none"), zorder=3)
arrow(83, 76, 27, 57.5, "argv for long-lived pids only", lx=52, ly=69.5, ls="--", rad=0.10)

# step 2: collapse
box(37, 45, 24, 10, "2 · collapse",
    "BUILD = compile+build-drv+pkg\nTEST = test-run+runtime+lint\nSEARCH = search+vcs", bfs=7.6)
arrow(32, 49.5, 37, 50)

# step 3: two views
box(2, 12, 30, 22, "3a · PROCESS view",
    "credit each process's CPU\nto its OWN class\n\nrustc → BUILD, whoever started it\nno ancestor walk · no argv needed\n= what the CPU physically ran",
    fc="#fff7e6", ec="#eda100", lw=1.3, bfs=7.6)
box(37, 12, 30, 22, "3b · OWNERSHIP view",
    "credit each process's CPU to its\nnearest DRIVER ancestor\n(test-run / build-drv / pkg)\n\ndriver class decided by its children:\n`go` that spawned vet/*.test = test\n= which agent command paid for it\n(P7 window ontology, validated ≤13 pt)",
    fc="#eaf7f1", ec="#1baf7a", lw=1.3, bfs=7.4)
arrow(17, 42, 17, 34)
arrow(49, 45, 52, 34)
arrow(32, 47, 46, 34, "", rad=-0.15)

# step 4: shares + label
box(72, 14, 26, 18, "4 · shares → label",
    "share = class core-s ÷ classified core-s\n\nleader if ≥ 10 pt ahead → B / T / S\nelse → M (mixed)\n\nflags: low-coverage <80 %\nlow-classified <50 % · drain",
    bfs=7.6)
arrow(32, 20, 72, 22, "", rad=0.12)
arrow(67, 23, 72, 23)

# outputs
box(72, 42, 26, 12, "cpu_matrix.tsv",
    "own_B/T/S · own_label\nproc_B/T/S · proc_label\ncoverage · classified % · flags", fc="#f4f4f2", bfs=7.6)
arrow(85, 32, 85, 42)
ax.text(85, 57.2, "⟨language × CPU-type⟩ matrix\none per view → ≤30 selection", ha="center", linespacing=1.3,
        fontsize=8.5, color=INK, fontweight="bold")
arrow(85, 54, 85, 55.2, "")

# scaffold / other note
ax.text(50, 4.5, "scaffold (bash, sleep, swerex-remote) and `other` (unregistered names) never vote — they only lower classified %.",
        ha="center", fontsize=7.4, color=INK3)
ax.text(50, 1.5, "repo-payload registry (jq, rg, hugo…): the repo's own binary is TEST in the process view but never owns children.",
        ha="center", fontsize=7.4, color=INK3)

ax.set_title("From receipts to a type label", fontsize=12, color=INK, loc="left", pad=8)
fig.subplots_adjust(left=0.02, right=0.98, top=0.95, bottom=0.02)
fig.savefig(f"{HERE}/fig7_flowchart.png", dpi=170)
print("wrote fig7")

# =============================== Fig 8: matrices ====================================
rows = list(csv.DictReader(open(f"{REPO}/local_agents/ML_typeid/cpu_matrix.tsv"), delimiter="\t"))
LANGS = ["C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript"]
MECH = {"C": "B", "C++": "B", "Rust": "A", "Go": "A", "Java": "J", "PHP": "I", "Ruby": "I",
        "JavaScript": "N", "TypeScript": "N"}
LABS = ["B", "T", "S", "M"]
LABNAME = {"B": "build", "T": "test", "S": "search", "M": "mixed"}


def lowev(r):
    return float(r["coverage"]) < 80 or float(r["classified_pct"]) < 50


def matrix_fig(view, title, sub, fname, accent):
    cells = collections.Counter(); low = collections.Counter(); ntot = collections.Counter()
    for r in rows:
        if r["language"] not in LANGS:
            continue
        ntot[r["language"]] += 1
        if lowev(r):
            low[r["language"]] += 1
        else:
            cells[(r["language"], r[view])] += 1
    fig, ax = plt.subplots(figsize=(8.6, 6.4))
    vmax = max(cells.values()) if cells else 1
    for i, l in enumerate(LANGS):
        for j, c in enumerate(LABS):
            v = cells.get((l, c), 0)
            a = 0.08 + 0.82 * (v / vmax) if v else 0.0
            ax.add_patch(plt.Rectangle((j, i), 1, 1, fc=accent, alpha=a, ec=SURFACE, lw=2))
            if v:
                ax.text(j + 0.5, i + 0.5, str(v), ha="center", va="center", fontsize=11,
                        color="white" if a > 0.55 else INK, fontweight="bold" if a > 0.55 else "normal")
        # low-evidence + n columns
        ax.add_patch(plt.Rectangle((len(LABS), i), 1, 1, fc="#eceae3", ec=SURFACE, lw=2))
        if low[l]:
            ax.text(len(LABS) + 0.5, i + 0.5, str(low[l]), ha="center", va="center", fontsize=10, color=INK2)
        ax.text(len(LABS) + 1.25, i + 0.5, f"n={ntot[l]}", ha="left", va="center", fontsize=8.5, color=INK3)
        ax.text(-0.15, i + 0.5, f"{l}", ha="right", va="center", fontsize=10, color=INK)
        ax.text(-2.05, i + 0.5, f"class {MECH[l]}", ha="left", va="center", fontsize=8, color=INK3)
    ax.set_xlim(-2.2, len(LABS) + 2.4); ax.set_ylim(len(LANGS), 0)
    ax.set_xticks([j + 0.5 for j in range(len(LABS) + 1)])
    ax.set_xticklabels([f"{c}\n{LABNAME[c]}" for c in LABS] + ["low-\nevidence"], fontsize=9)
    ax.xaxis.tick_top(); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    fig.text(0.02, 0.965, title, fontsize=12, color=INK, ha="left", va="top")
    fig.text(0.02, 0.925, sub, fontsize=8.5, color=INK2, ha="left", va="top")
    fig.subplots_adjust(left=0.20, right=0.98, top=0.80, bottom=0.03)
    fig.savefig(f"{HERE}/{fname}", dpi=170)
    print("wrote", fname)
    return cells


n = len(rows)
p = matrix_fig("proc_label", "Process view: what the CPU ran",
               f"{n} replayed episodes so far · each process credited to its own class\nlow-evidence = coverage <80% or classified <50% (kept, not voting)",
               "fig8a_matrix_process.png", CAT["BUILD"])
o = matrix_fig("own_label", "Ownership view: which agent command paid",
               f"{n} replayed episodes so far · each process credited to its nearest driver ancestor\nP7 window ontology (validated on 3 strict cases)",
               "fig8b_matrix_ownership.png", CAT["TEST"])
