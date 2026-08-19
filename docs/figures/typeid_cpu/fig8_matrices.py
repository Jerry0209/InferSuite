#!/usr/bin/env python3
"""Fig 8a/8b  ⟨language × CPU-type⟩ matrices, process view and ownership view.
Fig 8c     why the no-evidence rows carry no CPU-type verdict (ownership view).

Data: local_agents/ML_typeid/cpu_matrix.tsv  (typeid_cpu_matrix.py build)
      local_agents/ML_typeid/selection_30.tsv (typeid_select.py)
Writes 08a/08b/08c png next to this script. Re-run after any matrix rebuild.
"""
import csv, collections, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = "/home/network/InferSuite-Jerry"
ML = f"{REPO}/local_agents/ML_typeid"
SURFACE, INK, INK2, INK3 = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8880"
CAT = {"BUILD": "#eda100", "TEST": "#1baf7a", "SEARCH": "#2a78d6"}
plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
                     "font.size": 9, "text.color": INK, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2,
                     "axes.edgecolor": "#d8d6cf", "axes.linewidth": 0.8})

rows = list(csv.DictReader(open(f"{ML}/cpu_matrix.tsv"), delimiter="\t"))
by_inst = {r["instance"]: r for r in rows}
sel = [s for s in csv.DictReader(open(f"{ML}/selection_30.tsv"), delimiter="\t")
       if s.get("instance") and s["instance"] in by_inst]

LANGS = ["C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript"]
MECH = {"C": "B", "C++": "B", "Rust": "A", "Go": "A", "Java": "J", "PHP": "I", "Ruby": "I",
        "JavaScript": "N", "TypeScript": "N"}
LABS = ["B", "T", "S", "M"]
LABNAME = {"B": "build", "T": "test", "S": "search", "M": "mixed"}
NCOL = len(LABS)          # x index of the no-evidence column
GAP = 0.45                # vertical gap before the totals row
TOT_Y = len(LANGS) + GAP

picks = collections.Counter((by_inst[s["instance"]]["language"],
                             by_inst[s["instance"]]["own_label"]) for s in sel)


def matrix_fig(view, title, sub, fname, accent, show_picks=False):
    cells, low, ntot = collections.Counter(), collections.Counter(), collections.Counter()
    for r in rows:
        if r["language"] not in LANGS:
            continue
        ntot[r["language"]] += 1
        if r[view] == "?":
            low[r["language"]] += 1
        else:
            cells[(r["language"], r[view])] += 1

    fig, ax = plt.subplots(figsize=(8.8, 7.0))
    vmax = max(cells.values()) if cells else 1

    def cell(x, y, v, fc, alpha, fs=11, sub_txt=""):
        ax.add_patch(plt.Rectangle((x, y), 1, 1, fc=fc, alpha=alpha, ec=SURFACE, lw=2))
        if v:
            ax.text(x + 0.5, y + 0.5, str(v), ha="center", va="center", fontsize=fs,
                    color="white" if alpha > 0.55 else INK,
                    fontweight="bold" if alpha > 0.55 else "normal")
        if sub_txt:
            ax.text(x + 0.94, y + 0.94, sub_txt, ha="right", va="bottom", fontsize=7.2,
                    color="white" if alpha > 0.55 else INK2)

    for i, l in enumerate(LANGS):
        for j, c in enumerate(LABS):
            v = cells.get((l, c), 0)
            a = 0.08 + 0.82 * (v / vmax) if v else 0.0
            npick = picks.get((l, c), 0) if show_picks else 0
            cell(j, i, v, accent, a, sub_txt=f"★{npick}" if npick else "")
        cell(NCOL, i, low[l], "#d9d5c8", 0.55 if low[l] else 0.30, fs=10)
        ax.text(NCOL + 1.25, i + 0.5, f"n={ntot[l]}", ha="left", va="center", fontsize=8.5, color=INK3)
        ax.text(-0.15, i + 0.5, l, ha="right", va="center", fontsize=10, color=INK)
        ax.text(-2.05, i + 0.5, f"class {MECH[l]}", ha="left", va="center", fontsize=8, color=INK3)

    # totals row
    for j, c in enumerate(LABS):
        tv = sum(cells.get((l, c), 0) for l in LANGS)
        ax.text(j + 0.5, TOT_Y + 0.45, str(tv) if tv else "—", ha="center", va="center",
                fontsize=10.5, color=INK, fontweight="bold")
    tlow = sum(low.values())
    ax.text(NCOL + 0.5, TOT_Y + 0.45, str(tlow), ha="center", va="center", fontsize=10.5, color=INK2)
    ax.text(NCOL + 1.25, TOT_Y + 0.45, f"n={sum(ntot.values())}", ha="left", va="center",
            fontsize=8.5, color=INK3)
    ax.text(-0.15, TOT_Y + 0.45, "all", ha="right", va="center", fontsize=9.5, color=INK2)
    ax.plot([0, NCOL + 1], [TOT_Y + 0.02, TOT_Y + 0.02], color="#d8d6cf", lw=0.9)

    ax.set_xlim(-2.2, NCOL + 2.4)
    ax.set_ylim(TOT_Y + 1.0, 0)
    ax.set_xticks([j + 0.5 for j in range(NCOL + 1)])
    ax.set_xticklabels([f"{c}\n{LABNAME[c]}" for c in LABS] + ["no\nevidence"], fontsize=9)
    ax.xaxis.tick_top()
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    fig.text(0.02, 0.968, title, fontsize=12, color=INK, ha="left", va="top")
    fig.text(0.02, 0.930, sub, fontsize=8.5, color=INK2, ha="left", va="top")
    fig.subplots_adjust(left=0.20, right=0.98, top=0.80, bottom=0.03)
    fig.savefig(f"{HERE}/{fname}", dpi=170)
    plt.close(fig)
    print("wrote", fname)
    return cells


N = len(rows)
STAMP = "sweep complete 2026-08-19 · 296 token-free replays (285 typeid + 11 older)"
NOEV = ("no evidence = fewer than 10 classified core-s, or under 50% of the fence classified,\n"
        "or replay/live fence ratio outside [0.5, 2] — kept and shown, never voting")

matrix_fig("proc_label", "Process view: what the CPU ran",
           f"{STAMP} · each process credited to its own class\n{NOEV}",
           "08a_matrix_process_view.png", CAT["BUILD"])
matrix_fig("own_label", "Ownership view: which agent command paid",
           f"{STAMP} · each process credited to its nearest driver ancestor\n{NOEV}\n"
           "★ = episodes chosen for the P7 subset (30 picks over 16 populated cells)",
           "08b_matrix_ownership_view.png", CAT["TEST"], show_picks=True)


# ---------- 8c: why the no-evidence rows carry no verdict (ownership view) ----------
def reason(r):
    if "replay-invalid" in (r["flags"] or ""):
        return "replay invalid"
    cls_cs = float(r["classified_pct"]) * float(r["fence"]) / 100.0
    if cls_cs < 10:
        return "thin fence"
    return "mostly unclassified"


REASONS = ["thin fence", "replay invalid", "mostly unclassified"]
RCOL = {"thin fence": "#c9c4b4", "replay invalid": "#d9694f", "mostly unclassified": "#8fa4c0"}
RNOTE = {"thin fence": "toolchain never ran: <10 core-s of classified CPU (bootstrap + shell only)",
         "replay invalid": "replay did not reproduce the live fence (gradle network check, drain cap)",
         "mostly unclassified": "over half the fence spent in unregistered process names"}

per = collections.Counter()
for r in rows:
    if r["own_label"] == "?" and r["language"] in LANGS:
        per[(r["language"], reason(r))] += 1
order = sorted(LANGS, key=lambda l: -sum(per[(l, x)] for x in REASONS))
order = [l for l in order if sum(per[(l, x)] for x in REASONS)]

fig, ax = plt.subplots(figsize=(8.8, 4.6))
for i, l in enumerate(order):
    left = 0
    for rname in REASONS:
        v = per[(l, rname)]
        if not v:
            continue
        ax.barh(i, v, left=left, height=0.62, color=RCOL[rname], edgecolor=SURFACE, lw=1.4)
        ax.text(left + v / 2, i, str(v), ha="center", va="center", fontsize=9,
                color="white" if rname == "replay invalid" else INK)
        left += v
    ax.text(left + 0.4, i, f"of n={sum(1 for r in rows if r['language'] == l)}",
            ha="left", va="center", fontsize=8, color=INK3)
ax.set_yticks(range(len(order)))
ax.set_yticklabels(order, fontsize=9.5)
ax.invert_yaxis()
ax.set_xlabel("episodes with no CPU-type evidence (ownership view)", fontsize=9)
ax.set_xlim(0, max(sum(per[(l, x)] for x in REASONS) for l in order) + 4)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.tick_params(length=0)
ax.grid(axis="x", color="#e6e3da", lw=0.7)
ax.set_axisbelow(True)
tot = sum(per.values())
fig.text(0.02, 0.965, f"Why {tot} of {N} episodes carry no CPU-type verdict", fontsize=12,
         color=INK, ha="left", va="top")
fig.text(0.02, 0.918, "ownership view · the gate keeps these rows visible instead of guessing a type for them",
         fontsize=8.5, color=INK2, ha="left", va="top")
handles = [plt.Rectangle((0, 0), 1, 1, fc=RCOL[r]) for r in REASONS]
ax.legend(handles, [f"{r} — {RNOTE[r]}" for r in REASONS], loc="lower right", frameon=False,
          fontsize=8, handlelength=1.1, labelspacing=0.5)
fig.subplots_adjust(left=0.13, right=0.98, top=0.84, bottom=0.13)
fig.savefig(f"{HERE}/08c_no_evidence_reasons.png", dpi=170)
plt.close(fig)
print("wrote 08c_no_evidence_reasons.png", dict(collections.Counter(
    reason(r) for r in rows if r["own_label"] == "?")))
