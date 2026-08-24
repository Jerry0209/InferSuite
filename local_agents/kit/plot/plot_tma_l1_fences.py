#!/usr/bin/env python3
"""plot_tma_l1_fences.py — TMA Level 1 per FENCE, per task, from the matched-configuration
capture (measured cores 4-11 with SMT off, 100 ms windows).

The deck's original TMA-L1 figure was built from the SMT-ON campaign and covered four Python
tasks. This is the same view rebuilt on the re-capture: 12 tasks in 10 languages, and the
harness and tool fences kept apart, because they are different programs doing different work
and averaging them hides exactly the thing the study is about.

Where the numbers come from
---------------------------
`tma_cont.csv` is the CONTINUOUS TMA census: perf reads the PERF_METRICS register with
`--for-each-cgroup=<harness>,<tool>`, so every reading is already attributed to a fence and no
general-purpose counter is consumed. Each task has 8 replay episodes (one per shared counter
group); the census is group-independent, so all 8 measure the same thing and are pooled —
counts summed, which weights by episode length exactly as every other episode-level ratio in
this study does. The per-episode spread is written to the values JSON so the pooling can be
checked rather than trusted.

    /home/thu/miniforge3/envs/infersuite-full/bin/python local_agents/kit/plot/plot_tma_l1_fences.py
"""
from __future__ import annotations

import collections
import glob
import json
import os
import re
import statistics as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

DATA = os.path.expanduser("~/InferSuite/local_agents/SWE_iso8/data")
OUT = os.path.expanduser("~/InferSuite/local_agents/SWE_iso8/plots")

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["DejaVu Serif"], "mathtext.fontset": "dejavuserif",
    "font.size": 11, "figure.dpi": 150, "savefig.dpi": 300, "savefig.bbox": "tight",
    "axes.grid": True, "grid.color": "#cccccc", "grid.linewidth": 0.5, "grid.alpha": 0.6,
    "axes.axisbelow": True,
})
L1COLS = [("retiring", "Retiring", "#009E73"), ("fe-bound", "Frontend-bound", "#0072B2"),
          ("bad-spec", "Bad speculation", "#D55E00"), ("be-bound", "Backend-bound", "#E69F00")]
# Language per task, so the y axis carries the axis the multilingual study cares about.
LANG = {"astropy": "Python", "scikit-learn": "Python", "sympy": "Python", "babel": "JavaScript",
        "vuejs": "TypeScript", "fmtlib": "C++", "jqlang": "C", "prometheus": "Go",
        "google": "Java", "tokio-rs": "Rust", "rubocop": "Ruby", "php-cs-fixer": "PHP"}


def txtcol(h):
    r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
    return "black" if 0.299 * r + 0.587 * g + 0.114 * b > 150 else "white"


def fence_of(cg: str) -> str | None:
    if "docker-" in cg:
        return "tool"
    if "glm-rep-" in cg or "glm-swe-" in cg:
        return "harness"
    return None


def read_census(path):
    """{fence: {event: summed count}} for one episode's continuous TMA census."""
    out = collections.defaultdict(lambda: collections.defaultdict(float))
    for ln in open(path, errors="replace"):
        if ln.startswith("#") or not ln.strip():
            continue
        p = ln.split(",")
        if len(p) < 5:
            continue
        f = fence_of(p[4])
        if f is None:
            continue
        try:
            out[f][p[3]] += float(p[1])
        except ValueError:
            continue
    return out


def shares(ev):
    l1 = {k: ev.get(f"topdown-{k}", 0.0) for k, _lab, _c in L1COLS}
    tot = sum(l1.values())
    return {k: 100.0 * v / tot for k, v in l1.items()} if tot > 0 else None


tasks = sorted({os.path.basename(d).replace("glm_replay_swe_", "")
                for d in glob.glob(f"{DATA}/glm_replay_swe_*")})
POOLED, SPREAD = {}, {}
for t in tasks:
    pooled = collections.defaultdict(lambda: collections.defaultdict(float))
    per_ep = collections.defaultdict(list)
    for p in sorted(glob.glob(f"{DATA}/glm_replay_swe_{t}/run_*/tma_cont.csv")):
        cen = read_census(p)
        for f, ev in cen.items():
            for k, v in ev.items():
                pooled[f][k] += v
            s = shares(ev)
            if s:
                per_ep[f].append(s)
    for f, ev in pooled.items():
        s = shares(ev)
        if s:
            POOLED[(t, f)] = s
            SPREAD[(t, f)] = {k: {"min": min(e[k] for e in per_ep[f]),
                                 "max": max(e[k] for e in per_ep[f]),
                                 "n_episodes": len(per_ep[f])}
                              for k, _lab, _c in L1COLS} if per_ep[f] else {}

# One row per (task, fence); tool first so the eye reads the two blocks separately.
rows = ([(t, "tool") for t in tasks if (t, "tool") in POOLED]
        + [(t, "harness") for t in tasks if (t, "harness") in POOLED])
fig, ax = plt.subplots(figsize=(11.4, 0.40 * len(rows) + 3.0))
Y = np.arange(len(rows))
left = np.zeros(len(rows))
for key, lab, col in L1COLS:
    v = np.array([POOLED[r][key] for r in rows])
    ax.barh(Y, v, left=left, color=col, height=0.68, label=lab, edgecolor="white", linewidth=0.7)
    for y, (l, vv) in enumerate(zip(left, v)):
        if vv >= 7:
            ax.text(l + vv / 2, y, f"{vv:.0f}", ha="center", va="center", fontsize=8,
                    color=txtcol(col), fontweight="bold")
    left += v
ax.set_yticks(Y)
ax.set_yticklabels([f"{t} · {LANG.get(t,'?')} — {f}" for t, f in rows], fontsize=8.8)
ax.invert_yaxis()
ax.set_xlim(0, 100)
ax.grid(axis="x")
n_tool = sum(1 for r in rows if r[1] == "tool")
if 0 < n_tool < len(rows):
    ax.axhline(n_tool - 0.5, color="#7a8a99", lw=1.2, ls=(0, (4, 3)), zorder=5)
    ax.text(1.012, (n_tool - 1) / 2, "TOOL", transform=ax.get_yaxis_transform(), ha="left",
            va="center", rotation=90, fontsize=8.4, color="#5a6b78", fontweight="bold",
            clip_on=False)
    ax.text(1.012, (n_tool - 0.5 + len(rows) - 0.5) / 2, "HARNESS",
            transform=ax.get_yaxis_transform(), ha="left", va="center", rotation=90,
            fontsize=8.4, color="#5a6b78", fontweight="bold", clip_on=False)
ax.set_xlabel("pipeline slots (%) — continuous PERF_METRICS census, per cgroup fence")
ax.legend(ncol=4, fontsize=9, loc="upper center", bbox_to_anchor=(0.5, -0.045), frameon=False)
ax.set_title("TMA Level 1 per fence — matched configuration (cores 4–11, SMT off, 100 ms)",
             fontsize=12.5, pad=12)
fig.text(0.99, 0.002, "SWE-agent × GLM-5.2 deterministic replays, model never called · "
                      "8 episodes pooled per task · Intel Xeon w5-3425",
         ha="right", va="bottom", fontsize=7, color="#888888")
os.makedirs(OUT, exist_ok=True)
fig.savefig(os.path.join(OUT, "agentic_tma_l1_fences.png"))
plt.close(fig)

vals = {f"{t}|{f}": {"language": LANG.get(t), "shares": POOLED[(t, f)],
                     "per_episode_range": SPREAD.get((t, f), {})}
        for t, f in rows}
# Fence medians across tasks — the one-line summary the deck quotes.
for f in ("tool", "harness"):
    sel = [POOLED[r] for r in rows if r[1] == f]
    if sel:
        vals[f"_median_{f}"] = {k: st.median([s[k] for s in sel]) for k, _lab, _c in L1COLS}
        vals[f"_n_{f}"] = len(sel)
json.dump(vals, open(os.path.join(OUT, "tma_l1_fences_values.json"), "w"), indent=1)
print(os.path.join(OUT, "agentic_tma_l1_fences.png"))
for f in ("tool", "harness"):
    if f"_median_{f}" in vals:
        m = vals[f"_median_{f}"]
        print(f"  {f:<8} n={vals[f'_n_{f}']}  " +
              "  ".join(f"{k}={m[k]:.1f}%" for k, _lab, _c in L1COLS))
