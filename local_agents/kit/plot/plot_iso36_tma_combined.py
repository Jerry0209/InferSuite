#!/usr/bin/env python3
"""plot_iso36_tma_combined.py — aggregated TMA Level 1 for the 36 count-view picks with the
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

REPO = os.path.expanduser("~/InferSuite")
DATA = f"{REPO}/local_agents/ML_iso36/data"
OUT = f"{REPO}/local_agents/ML_iso36/plots"
SEL = f"{REPO}/local_agents/ML_typeid/selection_36_count.tsv"
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

GAP = 1.6
ys, ylab, order = [], [], []
y = 0.0
lang_at, seps = {}, []
for lang in LANGS:
    y0 = y
    for x in [x for x in rows if x[1] == lang]:
        order.append(("task", x)); ys.append(y); ylab.append(f"{x[0]} ({x[2]})"); y += 1.0
    lang_at[lang] = (y0, y - 1.0)
    seps.append(y - 1.0 + (GAP + 1.0) / 2)
    y += GAP
y0 = y
for name, m in spec_rows:
    order.append(("spec", (name, None, None, m, None))); ys.append(y); ylab.append(name); y += 1.0
lang_at["SPEC CPU 2026"] = (y0, y - 1.0)

fig, ax = plt.subplots(figsize=(11.5, 0.30 * len(order) + 4.4))
Y = np.array(ys)
left = np.zeros(len(order))
for key, lab, col in L1COLS:
    v = np.array([x[3][key] for _k, x in order])
    ax.barh(Y, v, left=left, color=col, height=0.72, label=lab, edgecolor="white", linewidth=0.6)
    for yy, (l, vv) in zip(Y, zip(left, v)):
        if vv >= 8:
            ax.text(l + vv / 2, yy, f"{vv:.0f}", ha="center", va="center", fontsize=7.6,
                    color=txtcol(col), fontweight="bold")
    left += v
for kind, x in order:
    if kind == "task":
        pass
for yy, (kind, x) in zip(Y, order):
    if kind == "task":
        ax.text(101.2, yy, f"{x[4]:.0f}% tool slots", va="center", fontsize=7.2, color="#888888")
for lang in LANGS + ["SPEC CPU 2026"]:
    lo, hi = lang_at[lang]
    ax.text(-0.20, (lo + hi) / 2, lang, transform=ax.get_yaxis_transform(),
            ha="left", va="center", fontsize=9.5, fontweight="bold")
for s in seps:
    ax.axhline(s, color="#e2e2e2", lw=0.8, zorder=0)
ax.set_yticks(Y)
ax.set_yticklabels(ylab, fontsize=8.4)
ax.invert_yaxis()
ax.set_ylim(max(Y) + 1.2, min(Y) - 1.2)
ax.set_xlim(0, 100)
ax.grid(axis="x")
ax.set_xlabel("pipeline slots (%) — both fences combined, slot-weighted")
ax.legend(ncol=4, fontsize=9, loc="upper center", bbox_to_anchor=(0.5, -0.035), frameon=False)
ax.set_title("TMA Level 1, tool + harness combined — 36 count-view picks",
             fontsize=12.5, pad=14)
fig.text(0.99, 0.002, "continuous PERF_METRICS census, counts summed over both fences and all 9 episodes "
                      "per task (slot-weighted) · right margin: the tool fence's share of the slots · "
                      "SPEC rows = per-benchmark episode medians",
         ha="right", va="bottom", fontsize=7.3, color="#888888")
fig.tight_layout(rect=(0.07, 0.02, 1, 0.99))
p = f"{OUT}/iso36_tma_l1_combined.png"
fig.savefig(p)
plt.close(fig)
json.dump(values, open(f"{OUT}/iso36_tma_combined_values.json", "w"), indent=1)
fe = [x[3]["fe-bound"] for k, x in order if k == "task"]
print(p)
print(f"{len(fe)} tasks; combined frontend-bound median {st.median(fe):.1f}% "
      f"(min {min(fe):.1f}, max {max(fe):.1f})")
