#!/usr/bin/env python3
# fig01_live_overview — COPY of the canonical generator local_agents/kit/plot/plot_paper_live_overview.py
# (single source of truth; edit THERE). Runs from the repo root against the
# banked data tree and writes into plots/paper_v1/.
# Regenerate: see charts/README.md.
"""plot_paper_live_overview.py — the 4-panel live overview in the PAPER style
(paper_style.py; mentor spec 2026-08-31), over the revised all-resolved 36.

Reads  : plots/paper_v1/iso36_live_overview_numbers.csv  (36 tasks + AVG + MEDIAN rows,
         written by plot_iso36_live_overview.py — regenerate it first when data changes)
Writes : plots/paper_v1/iso36_live_overview.{png,pdf}

Style deltas vs the archived 2026-08-28 figure (which stays frozen): value axes terminate
exactly on their outermost tick (100 sits ON the border); outward ticks; dotted grey grid;
black edge on every bar; AVG joined by a MEDIAN row, both on a grey band behind the bars
with value labels; solid black aggregate separator; dotted language separators; Libertine.
"""
import csv
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paper_style as ps  # noqa: E402

ps.apply()
REPO = os.path.expanduser("~/InferSuite")
OUT = os.environ.get("ISO36_OUT", f"{REPO}/local_agents/ML_iso36/plots/paper_v1")
LANGS = ["C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript"]
C_WORK, C_STALL = "#0072B2", "#c9c9c9"
C_TOOL, C_HARN = "#159f77", "#6a51a3"
C_BAR = "#0072B2"

rows = list(csv.DictReader(open(f"{OUT}/iso36_live_overview_numbers.csv")))
tasks = [r for r in rows if r["language"] in LANGS]
agg = {r["language"]: r for r in rows if r["language"] in ("AVG", "MEDIAN")}
assert len(tasks) == 36 and set(agg) == {"AVG", "MEDIAN"}, "numbers CSV incomplete"
for r in rows:
    for k in ("working_pct", "stall_pct", "tool_pct", "harness_pct", "n_calls", "med_dur_s"):
        r[k] = float(r[k])

# ---- y layout: language groups (top->bottom), separators, aggregate band ----
GAP = 0.9
ys, ylab, seps, lang_mid = [], [], [], {}
y = 0.0
for lang in LANGS:
    grp = [r for r in tasks if r["language"] == lang]
    y0 = y
    for r in grp:
        ys.append(y); ylab.append(r["task"]); y += 1.0
    lang_mid[lang] = (y0 + y - 1.0) / 2
    seps.append(y - 1.0 + (GAP + 1.0) / 2)
    y += GAP
seps = seps[:-1]                       # no separator after the last language
y += 0.9
Y_AGG = {"AVG": y, "MEDIAN": y + 1.0}
BAND_LO, BAND_HI = y - 0.62, y + 1.62
AGG_SEP_AT = y - 0.85
Y = np.array(ys)

fig, axes = plt.subplots(1, 4, figsize=(7.6, 5.9), sharey=True, constrained_layout=True)
for ax in axes:
    ax.grid(axis="x")
    ax.grid(False, axis="y")
    ax.invert_yaxis() if False else None
    ax.set_ylim(Y_AGG["MEDIAN"] + 0.9, -0.7)          # top->bottom, aggregates at bottom
    ps.band(ax, BAND_LO, BAND_HI)
    ps.agg_sep(ax, AGG_SEP_AT)
    for s in seps:
        ps.lang_sep(ax, s)
    ax.tick_params(axis="y", length=0)


def stacked(ax, key1, key2, c1, c2):
    for r, yy in list(zip(tasks, Y)) + [(agg[a], Y_AGG[a]) for a in ("AVG", "MEDIAN")]:
        is_agg = r["language"] in Y_AGG
        v1, v2 = r[key1], r[key2]
        lw = 0.9 if is_agg else 0.5
        ax.barh(yy, v1, height=0.8, color=c1, edgecolor="black", linewidth=lw, zorder=3)
        ax.barh(yy, v2, left=v1, height=0.8, color=c2, edgecolor="black", linewidth=lw,
                zorder=3)
        fs = 6.4 if is_agg else 5.8
        fw = "bold" if is_agg else "normal"
        if v1 >= 8:
            ax.text(v1 / 2, yy, f"{v1:.0f}", ha="center", va="center", fontsize=fs,
                    color="white", fontweight=fw, zorder=4)
        if v2 >= 8:
            ax.text(v1 + v2 / 2, yy, f"{v2:.0f}", ha="center", va="center", fontsize=fs,
                    color="#333333", fontweight=fw, zorder=4)
    ps.exact_limits(ax, "x", 0, 100, 25)


def plain(ax, key, fmt, step):
    vmax = max(r[key] for r in rows)
    cap = ps.cap_for(vmax, step)
    for r, yy in list(zip(tasks, Y)) + [(agg[a], Y_AGG[a]) for a in ("AVG", "MEDIAN")]:
        is_agg = r["language"] in Y_AGG
        v = r[key]
        ax.barh(yy, v, height=0.8, color=C_BAR, edgecolor="black",
                linewidth=0.9 if is_agg else 0.5, zorder=3)
        ax.text(v + cap * 0.02, yy, fmt(v), ha="left", va="center",
                fontsize=6.4 if is_agg else 5.8,
                fontweight="bold" if is_agg else "normal", color="#222222", zorder=4)
    ps.exact_limits(ax, "x", 0, cap, step)


stacked(axes[0], "working_pct", "stall_pct", C_WORK, C_STALL)
axes[0].set_title("(a) CPU working vs. stall", pad=4)
axes[0].set_xlabel("% of episode wall", fontsize=8)
stacked(axes[1], "tool_pct", "harness_pct", C_TOOL, C_HARN)
axes[1].set_title("(b) Tool vs. harness", pad=4)
axes[1].set_xlabel("% of fence core-seconds", fontsize=8)
plain(axes[2], "n_calls", lambda v: f"{v:.0f}", 100)
axes[2].set_title("(c) # tool calls", pad=4)
axes[2].set_xlabel("calls", fontsize=8)
plain(axes[3], "med_dur_s", lambda v: f"{v:.2f}", 0.1)
axes[3].set_title("(d) median call duration", pad=4)
axes[3].set_xlabel("seconds", fontsize=8)

axes[0].set_yticks(list(Y) + list(Y_AGG.values()))
axes[0].set_yticklabels(ylab + ["AVG", "MEDIAN"], fontsize=5.6)
for t in axes[0].get_yticklabels()[-2:]:
    t.set_fontweight("bold")
for lang, mid in lang_mid.items():
    axes[0].text(-1.04, mid, lang, transform=axes[0].get_yaxis_transform(),
                 ha="left", va="center", fontsize=7, fontweight="bold", clip_on=False)

handles = [plt.Rectangle((0, 0), 1, 1, fc=c) for c in (C_WORK, C_STALL, C_TOOL, C_HARN)]
ps.top_legend(fig, handles, ["CPU working", "CPU stall (incl. model wait)",
                             "Tool", "Harness"], y=1.05)
fig.text(0.5, -0.045,
         "36 live census episodes of the revised selection (all officially resolved). "
         "(c) every trajectory action incl. failed/errored calls and the final submit; "
         "model-only turns not counted.\nAVG = unweighted mean over the 36 tasks; MEDIAN = "
         "median over the 36 per-task values (panel d: median of the per-task medians). "
         "Grey band = aggregate rows.",
         ha="center", fontsize=5.8, color="#555555")

for ax in axes:
    ps.assert_exact(ax, "x")
for ext in ("png", "pdf"):
    fig.savefig(f"{OUT}/iso36_live_overview.{ext}", bbox_inches="tight")
print(f"{OUT}/iso36_live_overview.png / .pdf — axis-limit asserts passed")
