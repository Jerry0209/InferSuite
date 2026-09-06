#!/usr/bin/env python3
"""plot_paper_wall_live.py — the two LIVE-episode companions (PI request 2026-08-31) that
put tool fence, harness, and MODEL WAITING TIME in one row per task. New figures; the
replay-based iso36_cpu_work / iso36_active_wall stay as they are (replays never call the
model, so model wait exists only in live episodes).

Population: the 36 live census episodes of the revised all-resolved selection — the same
episodes and the same 0.2 s union-grid busy rule as iso36_live_overview (panel a).

  iso36_wall_split_live : STACKED — each episode's wall split into DISJOINT segments:
      tool busy → harness busy without tool → neither fence busy (= model wait + idle;
      the model round-trip dominates). Segments sum exactly to the episode wall.
  iso36_busy_wall_live  : GROUPED — tool busy, harness busy (each fence independently,
      they may overlap in time) and model wait as three bars, with the wall as a tick.

Writes: plots/paper_v1/iso36_{wall_split_live,busy_wall_live}.{png,pdf} + values JSON.
"""
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paper_style as ps  # noqa: E402

ps.apply()
REPO = os.path.expanduser("~/InferSuite")
ML = f"{REPO}/local_agents/ML_typeid"
OUT = os.environ.get("ISO36_OUT", f"{REPO}/local_agents/ML_iso36/plots/paper_v1")
SEL = f"{ML}/selection_36_count.tsv"
C_TOOL, C_HARN, C_WAIT = "#159f77", "#6a51a3", "#c9c9c9"   # locked: whitish grey = model wait
THR_TOOL, THR_HARN = 0.005, 0.02
LANGS = ["C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript"]


def cum_usage(path):
    t, u = [], []
    try:
        for ln in open(path):
            p = ln.split()
            if len(p) >= 3 and p[1] == "usage_usec":
                t.append(float(p[0])); u.append(float(p[2]))
    except OSError:
        pass
    cu, tot, prev = [], 0.0, None
    for x in u:
        if prev is not None and x > prev:
            tot += x - prev
        prev = x
        cu.append(tot)
    return np.array(t), np.array(cu) / 1e6


def episode(rd):
    tt, tu = cum_usage(f"{rd}/cpustat_scope2.tsv")   # tool
    ht, hu = cum_usage(f"{rd}/cpustat_scope1.tsv")   # harness
    if len(tt) < 10:
        return None
    t0, t1 = tt[0], tt[-1]
    wall = t1 - t0
    grid = np.arange(t0, t1, 0.2)
    tr = np.diff(np.interp(grid, tt, tu)) / 0.2
    hr = np.diff(np.interp(grid, ht, hu, left=0, right=hu[-1] if len(hu) else 0)) / 0.2 \
        if len(ht) > 1 else np.zeros(len(grid) - 1)
    tool_on, harn_on = tr > THR_TOOL, hr > THR_HARN
    n = len(tool_on)
    seg_tool = wall * float(np.mean(tool_on))
    seg_harn = wall * float(np.mean(harn_on & ~tool_on))     # disjoint: harness w/o tool
    seg_wait = wall - seg_tool - seg_harn                    # neither fence busy
    busy_tool = wall * float(np.mean(tool_on))               # independent busy times
    busy_harn = wall * float(np.mean(harn_on))
    return dict(wall=wall, seg_tool=seg_tool, seg_harn=seg_harn, seg_wait=seg_wait,
                busy_tool=busy_tool, busy_harn=busy_harn,
                wait=wall * float(np.mean(~tool_on & ~harn_on)))


mapd = dict(ln.strip().split("\t") for ln in open(f"{ML}/.replay_map.tsv") if "\t" in ln)
sel = [r for r in csv.DictReader(open(SEL), delimiter="\t") if "__" in r.get("instance", "")]
by_lang = collections.defaultdict(list)
for r in sel:
    r["disp"] = r["instance"].split("__", 1)[1]
    by_lang[r["lang"]].append(r)

rows, values = [], {}
for lang in LANGS:
    for r in by_lang[lang]:
        m = episode(f"{ML}/data/{mapd.get(r['instance'], 'MISSING')}/run_1")
        if m is None:
            continue
        rows.append((r["disp"], lang, r["label"], m))
        values[r["short"]] = {"language": lang, "cell": r["label"],
                              **{k: round(v, 1) for k, v in m.items()}}
assert len(rows) == 36, f"expected 36 live episodes, got {len(rows)}"

KEYS = ("wall", "seg_tool", "seg_harn", "seg_wait", "busy_tool", "busy_harn", "wait")
AGG = {name: {k: f([x[3][k] for x in rows]) for k in KEYS}
       for name, f in (("AVG", st.mean), ("MEDIAN", st.median))}
for name in AGG:
    values[name] = {k: round(v, 1) for k, v in AGG[name].items()}

# ---- shared y layout ----
GAP = 0.9
ys, ylab, seps, lang_mid, order = [], [], [], {}, []
y = 0.0
for lang in LANGS:
    y0 = y
    for x in [x for x in rows if x[1] == lang]:
        order.append(x); ys.append(y); ylab.append(f"{x[0]} ({x[2]})"); y += 1.0
    lang_mid[lang] = (y0 + y - 1.0) / 2
    seps.append(y - 1.0 + (GAP + 1.0) / 2)
    y += GAP
seps = seps[:-1]
y += 0.9
Y_AGG = {"AVG": y, "MEDIAN": y + 1.0}
BAND_LO, BAND_HI = y - 0.62, y + 1.62
AGG_SEP_AT = y - 0.85
Y = np.array(ys)


def frame(figsize):
    fig, ax = plt.subplots(figsize=figsize)
    ax.grid(axis="x"); ax.grid(False, axis="y")
    ax.set_ylim(Y_AGG["MEDIAN"] + 0.9, -0.7)
    ps.band(ax, BAND_LO, BAND_HI)
    ps.agg_sep(ax, AGG_SEP_AT)
    for s in seps:
        ps.lang_sep(ax, s)
    ax.tick_params(axis="y", length=0)
    return fig, ax


def finish(fig, ax, cap, step, xlabel, legend_items, stem, wall_tick=False):
    ps.exact_limits(ax, "x", 0, cap, step)
    ax.set_yticks(list(Y) + list(Y_AGG.values()))
    ax.set_yticklabels(ylab + ["AVG", "MEDIAN"], fontsize=6.4)
    for t in ax.get_yticklabels()[-2:]:
        t.set_fontweight("bold")
    for lang, mid in lang_mid.items():
        ax.text(-0.265, mid, lang, transform=ax.get_yaxis_transform(),
                ha="left", va="center", fontsize=8, fontweight="bold")
    ax.set_xlabel(xlabel)
    # paper-ready (PI 2026-09-06): no footer; layout FIRST so the legend centres on the panel
    fig.tight_layout(rect=(0.125, 0.01, 1, 0.945))
    handles = [plt.Rectangle((0, 0), 1, 1, fc=c) for _l, c in legend_items]
    labels = [l for l, _c in legend_items]
    if wall_tick:
        handles.append(plt.Line2D([0], [0], marker="|", color="#5c6b64",
                                  linestyle="none", markersize=9))
        labels.append("Episode wall")
    ps.top_legend(fig, handles, labels, y=0.985)
    ps.assert_exact(ax, "x")
    for ext in ("png", "pdf"):
        fig.savefig(f"{OUT}/{stem}.{ext}", bbox_inches="tight")
    plt.close(fig)
    print(f"{OUT}/{stem}.png / .pdf — asserts passed")


# ================= figure 1: stacked wall split =================
walls = [x[3]["wall"] for x in rows] + [AGG["AVG"]["wall"]]
cap = ps.cap_for(max(walls), 500, headroom=1.18)
fig, ax = frame((9.8, 0.20 * len(order) + 3.4))
def stack_row(yy, m, lw, fs, fw):
    l = 0.0
    for k, c in (("seg_tool", C_TOOL), ("seg_harn", C_HARN), ("seg_wait", C_WAIT)):
        ax.barh(yy, m[k], left=l, height=0.8, color=c, edgecolor="black", linewidth=lw,
                zorder=3)
        l += m[k]
    ax.text(l + cap * 0.012, yy,
            f"{m['wall']:,.0f} s  ({100 * m['seg_wait'] / m['wall']:.0f}% wait)",
            va="center", fontsize=fs, fontweight=fw, zorder=4)
for yy, x in zip(Y, order):
    stack_row(yy, x[3], 0.5, 6.2, "normal")
for name, yy in Y_AGG.items():
    stack_row(yy, AGG[name], 0.9, 6.8, "bold")
finish(fig, ax, cap, 500,
       "episode wall time (seconds) — live census episodes",
       [("Tool fence busy", C_TOOL), ("Harness busy (no tool)", C_HARN),
        ("Model wait + idle", C_WAIT)],
       "iso36_wall_split_live")

# ================= figure 2: grouped busy + wait =================
allmax = max(max(x[3]["wall"] for x in rows), AGG["AVG"]["wall"])
cap = ps.cap_for(allmax, 500, headroom=1.18)
fig, ax = frame((9.8, 0.26 * len(order) + 3.8))
def group_row(yy, m, lw, fs, fw):
    ax.barh(yy - 0.27, m["busy_tool"], height=0.26, color=C_TOOL, edgecolor="black",
            linewidth=lw, zorder=3)
    ax.barh(yy, m["busy_harn"], height=0.26, color=C_HARN, edgecolor="black",
            linewidth=lw, zorder=3)
    ax.barh(yy + 0.27, m["wait"], height=0.26, color=C_WAIT, edgecolor="black",
            linewidth=lw, zorder=3)
    ax.scatter([m["wall"]], [yy], marker="|", s=150, color="#5c6b64", zorder=4)
    ax.text(max(m["wall"], m["wait"]) + cap * 0.012, yy,
            f"wait {m['wait']:,.0f} s / {m['wall']:,.0f} s",
            va="center", fontsize=fs, fontweight=fw, zorder=4)
for yy, x in zip(Y, order):
    group_row(yy, x[3], 0.5, 6.2, "normal")
for name, yy in Y_AGG.items():
    group_row(yy, AGG[name], 0.9, 6.8, "bold")
finish(fig, ax, cap, 500,
       "time (seconds) — live census episodes",
       [("Tool fence busy", C_TOOL), ("Harness busy", C_HARN),
        ("Model wait + idle", C_WAIT)],
       "iso36_busy_wall_live", wall_tick=True)

json.dump(values, open(f"{OUT}/iso36_wall_live_values.json", "w"), indent=1)
w = [100 * x[3]["seg_wait"] / x[3]["wall"] for x in rows]
print(f"model-wait share: median {st.median(w):.0f}% (min {min(w):.0f}, max {max(w):.0f})")
