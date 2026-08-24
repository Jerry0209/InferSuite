#!/usr/bin/env python3
"""plot_wall_cpu_12t.py — deck slides 1-2 (wall-clock split, CPU work) rebuilt across all
twelve tasks and ten languages.

WHICH DATA, AND WHY IT IS NOT THE MATCHED RE-CAPTURE
----------------------------------------------------
The matched-configuration capture (SWE_iso8: cores 4-11 SMT off, 100 ms windows) is made of
deterministic REPLAYS, and a replay never calls the model. Its inference share is zero by
construction, so the wall-clock split simply cannot be drawn from it — the grey segment that
dominates slide 1 exists only in a live episode.

That is not a loss, because the wall-clock split does not depend on the re-captured
configuration at all: it is wall time plus cgroup cpu.stat accounting, with no PMU counter
anywhere in it. SMT and window length change what the COUNTERS see, not how long the agent
waited. So these two figures are rebuilt from the LIVE episodes, and what is new is the
POPULATION: 12 tasks in 10 languages instead of the 5 the deck currently shows.

The CPU-work figure additionally carries the matched replays as a second panel, because there
core-seconds ARE directly comparable and the replay is the population every microarchitecture
slide now uses.

    /home/thu/miniforge3/envs/infersuite-full/bin/python local_agents/kit/plot/plot_wall_cpu_12t.py
"""
from __future__ import annotations

import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

R = os.path.expanduser("~/InferSuite/local_agents")
OUT = os.path.expanduser("~/InferSuite/local_agents/SWE_iso8/plots")

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["DejaVu Serif"], "mathtext.fontset": "dejavuserif",
    "font.size": 11, "figure.dpi": 150, "savefig.dpi": 300, "savefig.bbox": "tight",
    "axes.grid": True, "grid.color": "#cccccc", "grid.linewidth": 0.5, "grid.alpha": 0.6,
    "axes.axisbelow": True,
})
C_TOOL, C_HARN, C_WAIT = "#159f77", "#6a51a3", "#c9c9c9"
# Burst thresholds: ONE definition shared with plot_glm_results.py. A fence counts as active
# above these rates; below them it is a poller artefact, not work.
THR_TOOL, THR_HARN = 0.005, 0.02

# task -> (live tree, language). Live episodes are the only place model wait exists.
TASKS = [
    ("scikit-learn", "superseded_40min", "Python", "scikit"),
    ("astropy", "superseded_40min", "Python", "astropy"),
    ("sympy", "SWE_clean", "Python", "sympy"),
    ("babel", "SWE_clean", "JavaScript", "babel"),
    ("vuejs", "ML_multiling", "TypeScript", "vue"),
    ("fmtlib", "SWE_clean", "C++", "fmt"),
    ("jqlang", "ML_multiling", "C", "jq"),
    ("prometheus", "ML_multiling", "Go", "promth"),
    ("google", "ML_multiling", "Java", "gson"),
    ("tokio-rs", "ML_multiling", "Rust", "tokio"),
    ("rubocop", "ML_multiling", "Ruby", "rubocop"),
    ("php-cs-fixer", "ML_multiling", "PHP", "cs-fixer"),
]


def cpustat(rd, i):
    out = []
    try:
        for ln in open(f"{rd}/cpustat_scope{i}.tsv"):
            p = ln.split()
            if len(p) >= 3 and p[1] == "usage_usec" and float(p[2]) >= 0:
                out.append((float(p[0]), float(p[2])))
    except OSError:
        pass
    return out


def series_full(rd, i):
    """(t0, t1, rate, core_seconds) with EXACT usec deltas — the poll interval is ~0.1021 s,
    so integrating as rate x 0.1 undercounts ~2 %."""
    s = cpustat(rd, i)
    return [(t0, t1, max(u1 - u0, 0.0) / 1e6 / max(t1 - t0, 1e-9), max(u1 - u0, 0.0) / 1e6)
            for (t0, u0), (t1, u1) in zip(s, s[1:])]


def active_wall(rd, i, thr):
    return sum(t1 - t0 for t0, t1, r, _cs in series_full(rd, i) if r > thr)


def core_s(rd, i):
    s = cpustat(rd, i)
    return (s[-1][1] - s[0][1]) / 1e6 if len(s) > 1 else 0.0


def wall_of(rd):
    s = cpustat(rd, 2) or cpustat(rd, 1)
    return (s[-1][0] - s[0][0]) if len(s) > 1 else 0.0


LIVE, VALUES = [], {}
for short, tree, lang, disp in TASKS:
    rd = f"{R}/{tree}/data/glm_swe_{short}/run_1"
    if not os.path.isdir(rd):
        print(f"  ! {short}: no live run_1 under {tree}")
        continue
    wall = wall_of(rd)
    if wall <= 0:
        continue
    tool_s = active_wall(rd, 2, THR_TOOL)
    harn_s = active_wall(rd, 1, THR_HARN)
    wait = max(0.0, wall - tool_s - harn_s)
    cs = [core_s(rd, i) for i in (1, 2, 3)]      # harness, tool, proxy
    LIVE.append(dict(short=short, disp=disp, lang=lang, tree=tree, wall=wall,
                     tool_s=tool_s, harn_s=harn_s, wait=wait, cs=cs))
    VALUES[short] = {"language": lang, "tree": tree, "wall_s": wall,
                     "tool_active_s": tool_s, "harness_active_s": harn_s, "model_wait_s": wait,
                     "core_s_harness": cs[0], "core_s_tool": cs[1], "core_s_proxy": cs[2]}

# ================= Figure 1: wall-clock split, 12 donuts ========================================
ncol = 6
nrow = int(np.ceil(len(LIVE) / ncol))
fig, axes = plt.subplots(nrow, ncol, figsize=(3.1 * ncol, 3.5 * nrow))
axes = np.atleast_1d(axes).ravel()
for ax, e in zip(axes, LIVE):
    parts = [e["wait"], e["tool_s"], e["harn_s"]]
    shares = [100 * p / e["wall"] for p in parts]
    # counterclock=False so the wedge order matches the clockwise angle walk below; with the
    # default (counterclockwise) the percentages land on the wrong wedges.
    w, _t = ax.pie(parts, colors=[C_WAIT, C_TOOL, C_HARN], startangle=90, counterclock=False,
                   wedgeprops=dict(width=0.42, edgecolor="white", linewidth=1.4))
    ang = 90.0
    for p, sh, col in zip(parts, shares, [C_WAIT, C_TOOL, C_HARN]):
        frac = p / e["wall"]
        mid = np.deg2rad(ang - 360 * frac / 2)
        ang -= 360 * frac
        if sh >= 4:
            ax.text(0.79 * np.cos(mid), 0.79 * np.sin(mid), f"{sh:.0f}%", ha="center",
                    va="center", fontsize=9.5,
                    color="#333" if col == C_WAIT else "white", fontweight="bold")
    ax.text(0, 0.06, f"{e['wall']/60:.0f} min", ha="center", va="center", fontsize=12.5,
            fontweight="bold")
    ax.text(0, -0.22, f"{e['disp']}\n({e['lang']})", ha="center", va="center", fontsize=9.5,
            color="#444")
    ax.set(aspect="equal")
    ax.axis("off")
for ax in axes[len(LIVE):]:
    ax.axis("off")
fig.legend(handles=[Patch(color=C_WAIT, label="Inference (model round-trip; CPU waits)"),
                    Patch(color=C_TOOL, label="Tool execution"),
                    Patch(color=C_HARN, label="Agent harness")],
           ncol=3, frameon=False, fontsize=11, loc="lower center", bbox_to_anchor=(0.5, 0.028))
fig.suptitle("Wall-clock time split — 12 tasks, 10 languages (live episodes)",
             fontsize=13.5, y=0.99)
fig.text(0.5, 0.004, "live episodes only — a deterministic replay never calls the model, so it "
                     "has no inference share · wall time + cgroup cpu.stat, no PMU counter",
         ha="center", va="bottom", fontsize=8.5, color="#888888")
fig.tight_layout(rect=(0, 0.085, 1, 0.955))
os.makedirs(OUT, exist_ok=True)
fig.savefig(f"{OUT}/agentic_wall_split_12t.png")
plt.close(fig)
print(f"{OUT}/agentic_wall_split_12t.png")

# ================= Figure 2: CPU work in core-seconds ===========================================
fig, (ax, axr) = plt.subplots(1, 2, figsize=(15.4, 6.4), gridspec_kw={"width_ratios": [1.25, 1]})
Y = np.arange(len(LIVE))
harn = np.array([e["cs"][0] for e in LIVE])
tool = np.array([e["cs"][1] for e in LIVE])
prox = np.array([e["cs"][2] for e in LIVE])
ax.barh(Y, tool, color=C_TOOL, height=0.66, label="Tool execution")
ax.barh(Y, harn, left=tool, color=C_HARN, height=0.66, label="Agent harness")
ax.barh(Y, prox, left=tool + harn, color="#cf6a1f", height=0.66, label="litellm proxy")
for y, e in enumerate(LIVE):
    tot = sum(e["cs"])
    ax.text(tot * 1.01 + 4, y, f"{tot:,.0f} core-s   ({100*e['cs'][1]/tot:.0f}% tools)",
            va="center", fontsize=8.4)
ax.set_yticks(Y)
ax.set_yticklabels([f"{e['disp']} · {e['lang']}" for e in LIVE], fontsize=9)
ax.invert_yaxis()
ax.set_xlim(0, max(sum(e["cs"]) for e in LIVE) * 1.42)
ax.set_xlabel("CPU work (core-seconds) — live episode")
ax.legend(fontsize=9, frameon=False, loc="lower right")
ax.set_title("Where the CPU work goes, live", fontsize=11.5)

# right: the matched-configuration replays — same fences, no model in the loop
ISO = f"{R}/SWE_iso8/data"
rep = []
for short, _tree, lang, disp in TASKS:
    rd = f"{ISO}/glm_replay_swe_{short}/run_1"
    if not os.path.isdir(rd):
        continue
    h, t = core_s(rd, 1), core_s(rd, 2)
    if h + t <= 0:
        continue
    rep.append((disp, lang, h, t))
    VALUES.setdefault(short, {}).update(matched_core_s_harness=h, matched_core_s_tool=t)
Yr = np.arange(len(rep))
axr.barh(Yr, [r[3] for r in rep], color=C_TOOL, height=0.66, label="Tool execution")
axr.barh(Yr, [r[2] for r in rep], left=[r[3] for r in rep], color=C_HARN, height=0.66,
         label="Agent harness")
for y, r in enumerate(rep):
    tot = r[2] + r[3]
    axr.text(tot * 1.01 + 2, y, f"{tot:,.0f}   ({100*r[3]/tot:.0f}% tools)", va="center",
             fontsize=8.4)
axr.set_yticks(Yr)
axr.set_yticklabels([f"{d} · {l}" for d, l, _h, _t in rep], fontsize=9)
axr.invert_yaxis()
axr.set_xlim(0, max(r[2] + r[3] for r in rep) * 1.45)
axr.set_xlabel("CPU work (core-seconds) — matched-config replay")
axr.legend(fontsize=9, frameon=False, loc="lower right")
axr.set_title("The same work with the model removed", fontsize=11.5)
fig.suptitle("CPU work by fence — 12 tasks, 10 languages", fontsize=13.5, y=1.0)
fig.text(0.99, 0.002, "left: live episodes (litellm proxy shown; it is negligible everywhere) · "
                      "right: deterministic replays at cores 4–11 SMT off, 100 ms windows",
         ha="right", va="bottom", fontsize=7.5, color="#888888")
fig.tight_layout(rect=(0, 0.02, 1, 0.95))
fig.savefig(f"{OUT}/agentic_cpu_work_12t.png")
plt.close(fig)
print(f"{OUT}/agentic_cpu_work_12t.png")

json.dump(VALUES, open(f"{OUT}/wall_cpu_12t_values.json", "w"), indent=1)
waits = [100 * e["wait"] / e["wall"] for e in LIVE]
print(f"  live: {len(LIVE)} tasks · model wait {min(waits):.0f}-{max(waits):.0f}% of wall "
      f"(median {sorted(waits)[len(waits)//2]:.0f}%)")
