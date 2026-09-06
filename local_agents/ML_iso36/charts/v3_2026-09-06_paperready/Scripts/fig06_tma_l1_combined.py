#!/usr/bin/env python3
# fig06_tma_l1_combined — COPY of the canonical generator local_agents/kit/plot/plot_paper_tma_combined.py
# (single source of truth; edit THERE). Runs from the repo root against the
# banked data tree and writes into plots/paper_v1/.
# Regenerate: see charts/README.md.
"""plot_paper_tma_combined.py (paper style; generated from plot_iso36_tma_combined.py) — aggregated TMA Level 1 for the 36 count-view picks with the
TOOL AND HARNESS FENCES COMBINED: one stacked bar per task, census counts pooled across both
fences and all 9 replay episodes.

The continuous PERF_METRICS census is already per-fence (--for-each-cgroup); summing the
topdown-* counts across the two fences weights each fence by the pipeline slots it actually
issued, so the combined bar reads "what the measured partition's pipeline did during this
task" — the harness contributes in proportion to its work, not per-episode averaging.
Per-fence views stay on the per-fence TMA slide; this is the roll-up.

Closing group: SPEC CPU 2026 medians (INT and FP separately, per the spec26 convention).

    /home/thu/miniforge3/envs/infersuite-full/bin/python local_agents/kit/plot/plot_iso36_tma_combined.py
"""
from __future__ import annotations

import collections
import csv
import glob
import json
import os
import statistics as st
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paper_style as ps  # noqa: E402
ps.apply()

REPO = os.path.expanduser("~/InferSuite")
DATA = f"{REPO}/local_agents/ML_iso36/data"
OUT = os.environ.get("ISO36_OUT", f"{REPO}/local_agents/ML_iso36/plots/paper_v1")
SEL = f"{REPO}/local_agents/ML_typeid/selection_36_count.tsv"
# LANG_VERTICAL=1 (PI 2026-09-06): rotate the language group labels 90° so they cannot
# overlap the long task labels; writes *_vertical_labels alongside the original.
VERT = os.environ.get("LANG_VERTICAL") == "1"
STEM = "iso36_tma_l1_combined" + ("_vertical_labels" if VERT else "")
sys.path.insert(0, f"{REPO}/spec26/kit/plot")
from spec_common import episodes as spec_episodes  # noqa: E402

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["DejaVu Serif"], "mathtext.fontset": "dejavuserif",
    "font.size": 11, "figure.dpi": 150, "savefig.dpi": 300, "savefig.bbox": "tight",
    "axes.grid": True, "grid.color": "#cccccc", "grid.linewidth": 0.5, "grid.alpha": 0.6,
    "axes.axisbelow": True,
})
L1COLS = [("retiring", "Retiring", "#009E73"), ("fe-bound", "Frontend-bound", "#0072B2"),
          ("bad-spec", "Bad speculation", "#D55E00"), ("be-bound", "Backend-bound", "#E69F00")]
LANGS = ["C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript"]


def txtcol(h):
    r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
    return "black" if 0.299 * r + 0.587 * g + 0.114 * b > 150 else "white"


def fence_of(cg):
    if "docker-" in cg:
        return "tool"
    if "glm-rep-" in cg or "glm-swe-" in cg:
        return "harness"
    return None


def census_combined(task_dir_glob):
    """Summed topdown-* counts over BOTH fences, all episodes; plus per-fence slot shares."""
    tot = collections.defaultdict(float)
    slots = collections.defaultdict(float)
    for p in sorted(glob.glob(task_dir_glob)):
        for ln in open(p, errors="replace"):
            if ln.startswith("#") or not ln.strip():
                continue
            q = ln.split(",")
            if len(q) < 5 or fence_of(q[4]) is None:
                continue
            try:
                v = float(q[1])
            except ValueError:
                continue
            tot[q[3]] += v
            if q[3] == "slots":
                slots[fence_of(q[4])] += v
    l1 = {k: tot.get(f"topdown-{k}", 0.0) for k, _l, _c in L1COLS}
    s = sum(l1.values())
    if s <= 0:
        return None, None
    return {k: 100.0 * v / s for k, v in l1.items()}, slots


sel = [r for r in csv.DictReader(open(SEL), delimiter="\t") if "__" in r.get("instance", "")]
by_lang = collections.defaultdict(list)
for r in sel:
    r["disp"] = r["instance"].split("__", 1)[1]
    by_lang[r["lang"]].append(r)

rows, values = [], {}
for lang in LANGS:
    for r in by_lang[lang]:
        shares, slots = census_combined(f"{DATA}/glm_replay_swe_{r['short']}/run_*/tma_cont.csv")
        if not shares:
            continue
        tool_slot_pct = 100 * slots.get("tool", 0) / (sum(slots.values()) or 1)
        rows.append((r["disp"], lang, r["label"], shares, tool_slot_pct))
        values[r["short"]] = {"language": lang, "cell": r["label"], "shares": shares,
                              "tool_slot_share_pct": round(tool_slot_pct, 1)}

# SPEC reference (episode census medians, INT / FP)
KEYMAP = {"retiring": "retiring", "bad-spec": "bad_spec", "fe-bound": "fe_bound", "be-bound": "be_bound"}
eps = [e for e in spec_episodes() if e.get("tma", {}).get("l1")]
spec_rows = []
for blk, cond in (("SPEC-int", lambda e: not e["fp"]), ("SPEC-fp", lambda e: e["fp"])):
    ss = [e["tma"]["l1"] for e in eps if cond(e)]
    if ss:
        m = {k: st.median([s[KEYMAP[k]] for s in ss]) for k, _l, _c in L1COLS}
        spec_rows.append((f"{blk} (n={len(ss)})", m))
        values[blk] = {"shares": m, "n": len(ss)}


# ---- paper-style layout: language groups + dotted separators; MEDIAN + SPEC rows on the
# aggregate band closed by a solid black separator ----
MEDROW = {k: st.median([x[3][k] for x in rows]) for k, _l, _c in L1COLS}
msum = sum(MEDROW.values())
MEDROW = {k: 100.0 * v / msum for k, v in MEDROW.items()}
values["MEDIAN"] = {"shares": MEDROW}

GAP = 0.9
ys, ylab, order, seps, lang_mid = [], [], [], [], {}
y = 0.0
for lang in LANGS:
    y0 = y
    for x in [x for x in rows if x[1] == lang]:
        order.append(("task", x)); ys.append(y); ylab.append(f"{x[0]} ({x[2]})"); y += 1.0
    lang_mid[lang] = (y0 + y - 1.0) / 2
    seps.append(y - 1.0 + (GAP + 1.0) / 2)
    y += GAP
seps = seps[:-1]
y += 0.9
AGG_SEP_AT = y - 0.85
BAND_LO = y - 0.62
order.append(("agg", ("MEDIAN (36 tasks)", None, None, MEDROW, None)))
ys.append(y); ylab.append("MEDIAN (36 tasks)"); y += 1.0
for name, m in spec_rows:
    msum = sum(m.values())            # medians of shares are not compositional -- renormalize
    m = {k: 100.0 * v / msum for k, v in m.items()}
    order.append(("agg", (name, None, None, m, None))); ys.append(y); ylab.append(name); y += 1.0
BAND_HI = y - 0.38
Y = np.array(ys)

fig, ax = plt.subplots(figsize=(9.8, 0.20 * len(order) + 3.6))
ax.grid(axis="x"); ax.grid(False, axis="y")
ax.set_ylim(y - 0.3, -0.7)
ps.band(ax, BAND_LO, BAND_HI)
ps.agg_sep(ax, AGG_SEP_AT)
for s in seps:
    ps.lang_sep(ax, s)
ax.tick_params(axis="y", length=0)

left = np.zeros(len(order))
for key, lab, col in L1COLS:
    v = np.array([x[3][key] for _k, x in order])
    lw = np.array([0.9 if k == "agg" else 0.5 for k, _x in order])
    for yy, l, vv, w in zip(Y, left, v, lw):
        ax.barh(yy, vv, left=l, color=col, height=0.8, edgecolor="black", linewidth=w,
                zorder=3, label=lab if yy == Y[0] else None)
        if vv >= 8:
            ax.text(l + vv / 2, yy, f"{vv:.0f}", ha="center", va="center", fontsize=6.2,
                    color=txtcol(col), fontweight="bold", zorder=4)
    left += v
for yy, (kind, x) in zip(Y, order):
    if kind == "task":
        ax.text(101.0, yy, f"{x[4]:.0f}% tool slots", va="center", fontsize=5.8,
                color="#777777", clip_on=False)
for lang, mid in lang_mid.items():
    if VERT:
        ax.text(-0.265, mid, lang, transform=ax.get_yaxis_transform(), rotation=90,
                ha="center", va="center", fontsize=8, fontweight="bold")
    else:
        ax.text(-0.265, mid, lang, transform=ax.get_yaxis_transform(),
                ha="left", va="center", fontsize=8, fontweight="bold")
ps.exact_limits(ax, "x", 0, 100, 25)
ax.set_yticks(Y)
ax.set_yticklabels(ylab, fontsize=6.4)
for t, (kind, _x) in zip(ax.get_yticklabels(), order):
    if kind == "agg":
        t.set_fontweight("bold")
ax.set_xlabel("pipeline slots (%) — both fences combined, slot-weighted")
# paper-ready (PI 2026-09-06): no footer; layout FIRST so the legend centres on the panel
fig.tight_layout(rect=(0.125, 0.01, 0.94, 0.955))
handles = [plt.Rectangle((0, 0), 1, 1, fc=c) for _k, _l, c in L1COLS]
ps.top_legend(fig, handles, [l for _k, l, _c in L1COLS], y=0.985)
ps.assert_exact(ax, "x")
for ext in ("png", "pdf"):
    fig.savefig(f"{OUT}/{STEM}.{ext}", bbox_inches="tight")
json.dump(values, open(f"{OUT}/iso36_tma_combined_values.json", "w"), indent=1)
fe = [x[3]["fe-bound"] for k, x in order if k == "task"]
print(f"{OUT}/{STEM}.png — asserts passed; "
      f"combined frontend-bound median {st.median(fe):.1f}%")
