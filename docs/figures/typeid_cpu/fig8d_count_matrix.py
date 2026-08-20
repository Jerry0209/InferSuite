#!/usr/bin/env python3
"""Fig 8d — ⟨language × CPU-type⟩ under COUNT weighting (leaf commands), for comparison
with the time-weighted views in 08a/08b. Reference column only: the label, matrix and
selection stay time-weighted (see multi_full_stratification.md, "Count-weighted
classification: tested, not adopted")."""
import csv, collections, glob, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = "/home/network/InferSuite-Jerry"
ML = f"{REPO}/local_agents/ML_typeid"
SURFACE, INK, INK2, INK3 = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8880"
ACCENT = "#2a78d6"
plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "font.size": 9,
                     "text.color": INK, "xtick.color": INK2, "ytick.color": INK2})

rows = list(csv.DictReader(open(f"{ML}/cpu_matrix.tsv"), delimiter="\t"))
LANGS = ["C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript"]
MECH = {"C": "B", "C++": "B", "Rust": "A", "Go": "A", "Java": "J", "PHP": "I", "Ruby": "I",
        "JavaScript": "N", "TypeScript": "N"}
LABS = ["B", "T", "S", "M"]
LABNAME = {"B": "build", "T": "test", "S": "search", "M": "mixed"}
NCOL = len(LABS)
GAP = 0.45
TOT_Y = len(LANGS) + GAP

cells, low, ntot = collections.Counter(), collections.Counter(), collections.Counter()
own_cells = collections.Counter()
for r in rows:
    if r["language"] not in LANGS:
        continue
    ntot[r["language"]] += 1
    if r["leaf_label"] == "?":
        low[r["language"]] += 1
    else:
        cells[(r["language"], r["leaf_label"])] += 1
    if r["own_label"] != "?":
        own_cells[(r["language"], r["own_label"])] += 1

fig, ax = plt.subplots(figsize=(8.8, 7.0))
vmax = max(cells.values()) if cells else 1
for i, l in enumerate(LANGS):
    for j, c in enumerate(LABS):
        v = cells.get((l, c), 0)
        a = 0.08 + 0.82 * (v / vmax) if v else 0.0
        ax.add_patch(plt.Rectangle((j, i), 1, 1, fc=ACCENT, alpha=a, ec=SURFACE, lw=2))
        if v:
            ax.text(j + 0.5, i + 0.5, str(v), ha="center", va="center", fontsize=11,
                    color="white" if a > 0.55 else INK,
                    fontweight="bold" if a > 0.55 else "normal")
        ov = own_cells.get((l, c), 0)          # time-weighted count, for contrast
        if ov or v:
            ax.text(j + 0.94, i + 0.94, f"({ov})", ha="right", va="bottom", fontsize=7,
                    color="white" if a > 0.55 else INK3)
    ax.add_patch(plt.Rectangle((NCOL, i), 1, 1, fc="#d9d5c8", alpha=0.55 if low[l] else 0.30,
                               ec=SURFACE, lw=2))
    if low[l]:
        ax.text(NCOL + 0.5, i + 0.5, str(low[l]), ha="center", va="center", fontsize=10, color=INK2)
    ax.text(NCOL + 1.25, i + 0.5, f"n={ntot[l]}", ha="left", va="center", fontsize=8.5, color=INK3)
    ax.text(-0.15, i + 0.5, l, ha="right", va="center", fontsize=10, color=INK)
    ax.text(-2.05, i + 0.5, f"class {MECH[l]}", ha="left", va="center", fontsize=8, color=INK3)

for j, c in enumerate(LABS):
    tv = sum(cells.get((l, c), 0) for l in LANGS)
    ov = sum(own_cells.get((l, c), 0) for l in LANGS)
    ax.text(j + 0.5, TOT_Y + 0.45, str(tv) if tv else "—", ha="center", va="center",
            fontsize=10.5, color=INK, fontweight="bold")
    ax.text(j + 0.5, TOT_Y + 0.95, f"({ov})", ha="center", va="center", fontsize=8, color=INK3)
ax.text(NCOL + 0.5, TOT_Y + 0.45, str(sum(low.values())), ha="center", va="center",
        fontsize=10.5, color=INK2)
ax.text(NCOL + 1.25, TOT_Y + 0.45, f"n={sum(ntot.values())}", ha="left", va="center",
        fontsize=8.5, color=INK3)
ax.text(-0.15, TOT_Y + 0.45, "all", ha="right", va="center", fontsize=9.5, color=INK2)
ax.plot([0, NCOL + 1], [TOT_Y + 0.02, TOT_Y + 0.02], color="#d8d6cf", lw=0.9)

ax.set_xlim(-2.2, NCOL + 2.4)
ax.set_ylim(TOT_Y + 1.4, 0)
ax.set_xticks([j + 0.5 for j in range(NCOL + 1)])
ax.set_xticklabels([f"{c}\n{LABNAME[c]}" for c in LABS] + ["no\nevidence"], fontsize=9)
ax.xaxis.tick_top()
ax.set_yticks([])
for s in ax.spines.values():
    s.set_visible(False)
ax.tick_params(length=0)
fig.text(0.02, 0.968, "Count view: how many commands ran (reference only)", fontsize=12,
         color=INK, ha="left", va="top")
fig.text(0.02, 0.930,
         "300 replays · every leaf command counted once, whatever its CPU · (grey) = the same cell "
         "under time weighting\n"
         "not the label: a counted search costs 2.2 ms against 35.7 ms for a build command, and the "
         "flips are toolchain shell plumbing\n"
         "caveat: 23 episodes lost receipts to a listener crash (Go 9, JS 6, TS 5) — their counts are "
         "truncated and still shown here",
         fontsize=8.5, color=INK2, ha="left", va="top")
fig.subplots_adjust(left=0.20, right=0.98, top=0.78, bottom=0.03)
fig.savefig(f"{HERE}/08d_matrix_count_view.png", dpi=170)
print("wrote 08d_matrix_count_view.png")
