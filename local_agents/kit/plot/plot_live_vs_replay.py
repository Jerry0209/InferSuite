#!/usr/bin/env python3
"""plot_live_vs_replay.py — live-vs-replay validation figures (mentor request 2026-08-27):
one figure per task; each metric a sub-figure whose LEFTMOST element is the LIVE episode's
per-window distribution as a violin (box inside), followed by the replay distribution(s).

POPULATION — why these 12 tasks and not the 36. The 36 count-view picks were live-run on
the ws02 census machine deliberately WITHOUT counters (typeid light mode), so no live
per-window metrics exist for them. The tasks where a same-trajectory live/replay pair with
live counters exists are the SWE_iso8 twelve: live P7 episodes with the shuffled zero-mux
rotation (2 s windows) whose recorded trajectories were later replayed dedicated-group
(100 ms). Same actions, same repos, two instruments — the correct validation pair.

Bars per sub-figure (tool fence):
  GP metrics    : live violin+box (rotation windows of that metric's group) | replay
                  violin+box (the dedicated pass carrying that group).
  TMA L1 buckets: live violin (10 s census intervals) | one replay violin per episode (8) —
                  the multi-bar comparison that answers "does replay TMA equal live TMA".

Known, measured differences carried as caveats, not surprises: live is SMT-ON at 2 s
windows, replay SMT-OFF at 100 ms (config effect measured 2026-08-07: IPC +18.8 %, TMA
shape moves ~1 pt); window length changes distribution WIDTH by construction — medians are
the comparable layer, annotated per panel. fe_miss metrics exist on neither side here
(the group entered the rotation with ML_iso36) and are omitted.

    /home/thu/miniforge3/envs/infersuite-full/bin/python local_agents/kit/plot/plot_live_vs_replay.py
"""
from __future__ import annotations

import collections
import csv
import glob
import json
import os
import re
import statistics as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: no qa
import numpy as np

REPO = os.path.expanduser("~/InferSuite")
ISO = f"{REPO}/local_agents/SWE_iso8/data"
L3 = f"{ISO}/l3_study"
OUT = f"{REPO}/local_agents/SWE_iso8/plots/live_vs_replay"

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["DejaVu Serif"], "mathtext.fontset": "dejavuserif",
    "font.size": 10, "figure.dpi": 130, "savefig.dpi": 180, "savefig.bbox": "tight",
    "axes.grid": True, "grid.color": "#d8d8d8", "grid.linewidth": 0.5, "grid.alpha": 0.6,
    "axes.axisbelow": True,
})
C_LIVE, C_REP = "#cf6a1f", "#159f77"

# task -> (live tree, language)
TASKS = [
    ("scikit-learn", "superseded_40min", "Python"), ("astropy", "superseded_40min", "Python"),
    ("sympy", "superseded_40min", "Python"), ("babel", "SWE_clean", "JavaScript"),
    ("fmtlib", "SWE_clean", "C++"), ("vuejs", "ML_multiling", "TypeScript"),
    ("google", "ML_multiling", "Java"), ("tokio-rs", "ML_multiling", "Rust"),
    ("jqlang", "ML_multiling", "C"), ("rubocop", "ML_multiling", "Ruby"),
    ("php-cs-fixer", "ML_multiling", "PHP"), ("prometheus", "ML_multiling", "Go"),
]

# metric -> panel title (the 18-list minus the fe_miss trio, unavailable on both sides here)
PANELS = [
    ("IPC", "IPC"), ("branch_MPKI", "Branch MPKI"), ("DSB_pct", "DSB coverage (%)"),
    ("uop_gap", None),  # placeholder removed below
]
PANELS = [
    ("IPC", "IPC"),
    ("branch_MPKI", "Branch MPKI"),
    ("DSB_pct", "DSB coverage (%)"),
    ("codeRead_MPKI_L1I", "L1I MPKI (code-read)"),
    ("L1D_MPKI", "L1D-load MPKI"),
    ("L2_MPKI", "L2-load MPKI"),
    ("LLC_MPKI", "LLC MPKI"),
    ("icache_data_stall_pct", "L1I stall (% cycles)"),
    ("L1D_missrate_pct", "L1D miss rate (%)"),
    ("L2_missrate_pct", "L2-load miss rate (%)"),
    ("LLC_missrate_pct", "LLC miss rate (%)"),
    ("AMAT_cyc", "AMAT (cycles)"),
    ("MLP", "MLP"),
    # dram_rd_GBs is deliberately ABSENT: it is a per-wall-second rate, and a live 2-5 s
    # window contains model-wait idle that dilutes the rate ~10-50x relative to a 100 ms
    # replay window. Counter-ratio metrics are immune (numerator and denominator both
    # accumulate only while the fence runs); wall-rate metrics are not comparable across
    # window lengths and are excluded rather than shown misleadingly.
    ("kernel_pct", "kernel (% cycles)"),
    ("ctx_per_cpu_s", "ctx switches (/CPU-s)"),
]
TMA = [("retiring", "TMA retiring (%)"), ("fe_bound", "TMA frontend-bound (%)"),
       ("bad_spec", "TMA bad-spec (%)"), ("be_bound", "TMA backend-bound (%)")]

# ---- live rotation window parsing (same formulas as analyze_l3_windows.derive) ----
EVRE = re.compile(r"\s*([\d,]+|<not counted>|<not supported>)\s+([\w.:/,=-]+)\s+(\S+)")


def counts_tool(path):
    d = {}
    for ln in open(path, errors="replace"):
        if " msec " in ln and "task-clock" in ln and "<not" not in ln:
            p = ln.split()
            if len(p) > 3 and "docker-" in p[3]:
                try:
                    d["task-clock"] = d.get("task-clock", 0.0) + float(p[0].replace(",", ""))
                except ValueError:
                    pass
            continue
        m = EVRE.match(ln)
        if not m or m.group(1).startswith("<"):
            continue
        if "docker-" in m.group(3):
            d[m.group(2)] = d.get(m.group(2), 0.0) + float(m.group(1).replace(",", ""))
    return d


def derive(group, d, dur):
    I = d.get("instructions", 0); C = d.get("cycles", 0)
    if group == "priv":
        I = d.get("instructions:u", 0) + d.get("instructions:k", 0)
        C = d.get("cycles:u", 0) + d.get("cycles:k", 0)
    g = lambda e: d.get(e, 0.0)
    out = {}
    if I < 5e5 or C <= 0:
        return out
    if group == "fpbr":
        out["IPC"] = I / C
        out["branch_MPKI"] = 1000 * g("branch-misses") / I
    elif group == "cache":
        l1, l2 = g("mem_load_retired.l1_hit"), g("mem_load_retired.l2_hit")
        l3, lm = g("mem_load_retired.l3_hit"), g("mem_load_retired.l3_miss")
        loads = l1 + l2 + l3 + lm
        out["L1D_MPKI"] = 1000 * (l2 + l3 + lm) / I
        out["L2_MPKI"] = 1000 * (l3 + lm) / I
        out["LLC_MPKI"] = 1000 * lm / I
        if loads > 1e4:
            out["AMAT_cyc"] = (5 * l1 + 15 * l2 + 50 * l3 + 250 * lm) / loads
            out["L1D_missrate_pct"] = 100 * (l2 + l3 + lm) / loads
            if (l2 + l3 + lm) > 1e3:
                out["L2_missrate_pct"] = 100 * (l3 + lm) / (l2 + l3 + lm)
            if (l3 + lm) > 1e3:
                out["LLC_missrate_pct"] = 100 * lm / (l3 + lm)
    elif group == "mlp":
        pc = g("l1d_pend_miss.pending_cycles")
        if pc > 1e4:
            out["MLP"] = g("l1d_pend_miss.pending") / pc
    elif group == "fe":
        ut = sum(g(k) for k in ("idq.dsb_uops", "idq.mite_uops", "idq.ms_uops", "lsd.uops"))
        if ut > 1e5:
            out["DSB_pct"] = 100 * g("idq.dsb_uops") / ut
    elif group == "fe_lat":
        out["codeRead_MPKI_L1I"] = 1000 * g("l2_rqsts.all_code_rd") / I
        out["icache_data_stall_pct"] = 100 * g("icache_data.stalls") / C
    elif group == "dram_bw":
        if dur:
            out["dram_rd_GBs"] = g("offcore_requests.data_rd") * 64 / dur / 1e9
    elif group == "priv":
        ck, cu = g("cycles:k"), g("cycles:u")
        if ck + cu > 1e5:
            out["kernel_pct"] = 100 * ck / (ck + cu)
        tk = g("task-clock")
        if tk > 10:
            out["ctx_per_cpu_s"] = g("context-switches") / (tk / 1e3)
    if "IPC" not in out and I and C:
        out["IPC"] = I / C
    return out


def live_windows(rd):
    rows = collections.defaultdict(list)          # metric -> values
    wt = f"{rd}/windows.tsv"
    if not os.path.exists(wt):
        return rows
    for ln in list(open(wt))[1:]:
        p = ln.split()
        if len(p) < 4:
            continue
        w, grp, a, b = p[0], p[1], float(p[2]), float(p[3])
        f = f"{rd}/group_{grp}_w{w}.txt"
        if not os.path.exists(f):
            continue
        for k, v in derive(grp, counts_tool(f), b - a).items():
            rows[k].append(v)
    return rows


def tma_intervals(path, fence_tag):
    """per-10s-interval TMA L1 shares for one fence from a tma_cont.csv."""
    acc = collections.defaultdict(lambda: collections.defaultdict(float))
    for ln in open(path, errors="replace"):
        if ln.startswith("#") or not ln.strip():
            continue
        p = ln.split(",")
        if len(p) < 5 or fence_tag not in p[4]:
            continue
        try:
            acc[p[0]][p[3]] += float(p[1])
        except ValueError:
            continue
    out = collections.defaultdict(list)
    for _t, d in acc.items():
        l1 = {k: d.get(f"topdown-{k}", 0.0) for k in ("retiring", "bad-spec", "fe-bound", "be-bound")}
        s = sum(l1.values())
        if s < 1e6:
            continue
        out["retiring"].append(100 * l1["retiring"] / s)
        out["bad_spec"].append(100 * l1["bad-spec"] / s)
        out["fe_bound"].append(100 * l1["fe-bound"] / s)
        out["be_bound"].append(100 * l1["be-bound"] / s)
    return out


def violin(ax, pos, vals, color, width=0.8):
    if len(vals) < 3:
        return False
    vp = ax.violinplot([vals], positions=[pos], widths=width, showextrema=False)
    for b in vp["bodies"]:
        b.set_facecolor(color); b.set_alpha(0.55); b.set_edgecolor("none")
    ax.boxplot([vals], positions=[pos], widths=width * 0.28, whis=(5, 95), showfliers=False,
               patch_artist=True,
               boxprops=dict(facecolor="white", edgecolor="#444", lw=0.8),
               medianprops=dict(color="#111", lw=1.2),
               whiskerprops=dict(color="#666", lw=0.7), capprops=dict(color="#666", lw=0.7))
    return True


os.makedirs(OUT, exist_ok=True)
values = {}
summary = collections.defaultdict(list)
for short, tree, lang in TASKS:
    live_rd = f"{REPO}/local_agents/{tree}/data/glm_swe_{short}/run_1"
    lw = live_windows(live_rd)
    ltma = tma_intervals(f"{live_rd}/tma_cont.csv", "docker-") if os.path.exists(f"{live_rd}/tma_cont.csv") else {}
    rep_rows = list(csv.DictReader(open(f"{L3}/all_windows_{short}.csv")))
    rtma_runs = []
    for p in sorted(glob.glob(f"{ISO}/glm_replay_swe_{short}/run_*/tma_cont.csv")):
        rtma_runs.append(tma_intervals(p, "docker-"))

    def rvals(metric, run=None):
        return [float(r["value"]) for r in rep_rows
                if r["metric"] == metric and r["fence"] == "tool" and (run is None or r["run"] == run)]

    panels = [(m, t) for m, t in PANELS if len(lw.get(m, [])) >= 3 or len(rvals(m)) >= 3] + TMA
    ncol = 4
    nrow = (len(panels) + ncol - 1) // ncol
    fig, axes = plt.subplots(nrow, ncol, figsize=(16, 3.0 * nrow))
    axes = np.array(axes).flatten()
    tv = {}
    for ax, (m, title) in zip(axes, panels):
        is_tma = m in [k for k, _ in TMA]
        lv = ltma.get(m, []) if is_tma else lw.get(m, [])
        pos, ticks = 0, []
        ok = violin(ax, 0, lv, C_LIVE)
        ticks.append(f"live\n({len(lv)}w)" if ok else "live\n(n/a)")
        if is_tma:
            for i, rt in enumerate(rtma_runs):
                vv = rt.get(m, [])
                if violin(ax, i + 1, vv, C_REP, width=0.7):
                    pass
                ticks.append(f"r{i+1}")
            pos = len(rtma_runs)
            med_r = st.median([x for rt in rtma_runs for x in rt.get(m, [])] or [float("nan")])
        else:
            rv = rvals(m)
            violin(ax, 1, rv, C_REP)
            ticks.append(f"replay\n({len(rv)}w)")
            pos = 1
            med_r = st.median(rv) if rv else float("nan")
        med_l = st.median(lv) if lv else float("nan")
        ax.set_xticks(range(pos + 1))
        ax.set_xticklabels(ticks, fontsize=6.6)
        ax.set_title(title or m, fontsize=9.5)
        ax.tick_params(labelsize=7.5)
        if med_l == med_l and med_r == med_r:
            ax.text(0.98, 0.96, f"med {med_l:.3g} → {med_r:.3g}", transform=ax.transAxes,
                    ha="right", va="top", fontsize=7.2, color="#444")
            tv[m] = {"live_median": med_l, "replay_median": med_r,
                     "n_live": len(lv), "n_replay": None if is_tma or m == "IPC" else len(rvals(m))}
            if med_l:
                summary[m].append(med_r / med_l)
    for ax in axes[len(panels):]:
        ax.axis("off")
    fig.suptitle(f"Live vs replay, same trajectory — {short} ({lang}) · tool fence · "
                 f"orange = live (rotation, 2 s, SMT-on) · green = replay (dedicated, 100 ms, SMT-off)",
                 fontsize=12, y=1.0)
    fig.text(0.99, 0.002, "violin = distribution, box = IQR/median inside · window length changes spread "
                          "by construction — medians are the comparable layer · SMT config effect measured: "
                          "IPC +18.8%, TMA shape ~1 pt (report 20)",
             ha="right", va="bottom", fontsize=7, color="#888888")
    fig.tight_layout(rect=(0, 0.01, 1, 0.975))
    p = f"{OUT}/lvr_{short}.png"
    fig.savefig(p)
    plt.close(fig)
    values[short] = tv
    print(p)

json.dump(values, open(f"{OUT}/live_vs_replay_values.json", "w"), indent=1)
print("\nreplay/live median ratio across tasks (median [min..max], n tasks):")
for m, rr in sorted(summary.items()):
    print(f"  {m:<22} {st.median(rr):5.2f}  [{min(rr):.2f}..{max(rr):.2f}]  n={len(rr)}")
