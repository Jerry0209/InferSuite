#!/usr/bin/env python3
"""spec_common.py — shared loading + style for every SPEC CPU 2026 figure.

Where the data is
-----------------
The SPEC capture kit and its banked windows live OUTSIDE this repo, in the sibling tree
`~/spec26-infra/infra` (26 episode directories under `data/`, ~1.4 GB of raw perf window
files). Only the derived figures and this plotting code are tracked here — the same split
the agentic campaigns use (`local_agents/*/data` is gitignored).

    SPEC_DATA   episode root            default ~/spec26-infra/infra/data
    SPEC_PLOTS  thesis figure output    default <repo>/spec26/plots
    SPEC_WIN    per-window figure output default ~/spec26-infra/infra/plots/windows

Two levels of metric are exposed and they must not be confused:

  episode()      whole-episode SUM ratios, straight out of the capture kit's own
                 extract_metrics.py (metrics.json). Numerator and co-counted denominator
                 are each summed over the whole episode; this is the number that goes in
                 a table or a cross-benchmark bar.

  windows()      per-window ratios: numerator and denominator both taken from the SAME
                 100 ms window file. This is the distribution layer (box plots, timelines)
                 and its median is NOT the episode value — a mean of ratios is not the
                 ratio of sums. Both are correct; they answer different questions.

Per-window metrics are only defined for the counter group that was live in that window
(exactly one group per window, by design — see campaign.conf). IPC is the exception: cycles
and instructions are in every group, so IPC has a value in every window.
"""
from __future__ import annotations

import json
import os
import re
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
SPEC_INFRA = os.path.expanduser("~/spec26-infra/infra")
DATA = os.environ.get("SPEC_DATA", os.path.join(SPEC_INFRA, "data"))
OUT = os.environ.get("SPEC_PLOTS", os.path.join(REPO, "spec26", "plots"))
WINOUT = os.environ.get("SPEC_WIN", os.path.join(SPEC_INFRA, "plots", "windows"))
# PRIMARY agentic side (2026-08-07): the re-capture on the SPEC configuration — cores 4-11
# SMT-off, 100 ms windows, same partition, same window length. That retires the SMT and
# window-size caveats instead of carrying them in prose.
COMPARISON = os.environ.get("SPEC_COMPARISON", os.path.join(SPEC_INFRA, "comparison_iso8.json"))
# LEGACY agentic side: SMT-ON on 20 logical CPUs at 2 s / 5 s windows. Kept because the pair
# MEASURES what the old caveat was worth (IPC 1.59 -> 1.89 SMT-off, +18.8 %).
COMPARISON_LEGACY = os.environ.get("SPEC_COMPARISON_LEGACY",
                                   os.path.join(SPEC_INFRA, "comparison.json"))

# ---------------- style: identical family to local_agents/kit/plot/plot_glm_results.py ----------
plt.rcParams.update({
    "font.family": "serif", "font.serif": ["DejaVu Serif"], "mathtext.fontset": "dejavuserif",
    "font.size": 11, "figure.dpi": 150, "savefig.dpi": 300, "savefig.bbox": "tight",
    "axes.grid": True, "grid.color": "#cccccc", "grid.linewidth": 0.5, "grid.alpha": 0.6,
    "axes.axisbelow": True,
})
# TMA colours are the thesis palette, unchanged, so a SPEC TMA bar is directly readable
# against an agentic one.
L1COLS = [("retiring", "Retiring", "#009E73"), ("fe_bound", "Frontend-bound", "#0072B2"),
          ("bad_spec", "Bad speculation", "#D55E00"), ("be_bound", "Backend-bound", "#E69F00")]
UOPCOLS = [("DSB_pct", "DSB (uop cache)", "#0072B2"), ("MITE_pct", "MITE (decode)", "#E69F00"),
           ("MS_pct", "Microcode", "#D55E00"), ("LSD_pct", "LSD (loop)", "#999999")]
C_SPEC, C_AGENT = "#1b6ca8", "#159f77"      # the two workload families, used everywhere
C_INT, C_FP = "#6a51a3", "#d95f02"          # SPEC integer vs floating-point benchmarks

STAMP = ("Intel Xeon w5-3425 (Sapphire Rapids, 6-wide) · SPEC CPU 2026 v1.0.1, ref inputs, "
         "1 copy on 1 isolated SMT-free core (measured 4–11) @ fixed clock, no turbo · "
         "100 ms windows, shuffled 11-group rotation, zero multiplexing")


def stamp(fig, text: str = STAMP):
    fig.text(0.99, 0.002, text, ha="right", va="bottom", fontsize=7, color="#888888")


def txtcol(hexcol: str) -> str:
    r, g, b = (int(hexcol[i:i + 2], 16) for i in (1, 3, 5))
    return "black" if 0.299 * r + 0.587 * g + 0.114 * b > 150 else "white"


def save(fig, name: str, out: str | None = None):
    d = out or OUT
    os.makedirs(d, exist_ok=True)
    stamp(fig)
    p = os.path.join(d, name)
    fig.savefig(p)
    plt.close(fig)
    print(f"  {p}")
    return p


# ---------------- benchmark identity ------------------------------------------------------------
# SPEC's own suite split, read off the installed benchsets (benchspec/CPU/fprate.bset), not
# guessed from names: 14 intrate + 12 fprate = the 26 captured (999.specrand_r, in both sets,
# is a validation harness and was not run). The integer/FP axis is the first thing anyone asks
# of a SPEC figure, and it is a property of the suite, not something inferred from the counters.
FP_BENCH = {"709.cactus_r", "722.palm_r", "731.astcenc_r", "736.ocio_r", "737.gmsh_r",
            "748.flightdm_r", "749.fotonik3d_r", "765.roms_r", "766.femflow_r", "767.nest_r",
            "782.lbm_r", "772.marian_r"}


def short(b: str) -> str:
    """706.stockfish_r -> stockfish. FILENAMES ONLY.

    Figures always carry the full SPEC name (`7xx.workload_r`, the form spec.org publishes),
    because that is the identifier a reader can look up; the bare stem is ambiguous across
    suites and versions. This helper survives only to keep per-window PNG filenames short.
    """
    return re.sub(r"^\d+\.", "", b).removesuffix("_r")


def is_fp(b: str) -> bool:
    return b in FP_BENCH


# ---------------- categorical (INT then FP) ordering --------------------------------------------
# The suite splits into SPECrate integer and SPECrate floating-point, and the two categories have
# genuinely different microarchitectural profiles — integer codes stress branch prediction and
# instruction supply, FP codes stress the memory system. A figure ordered by measured value mixes
# them and hides that; a figure ordered by category shows it before a single number is read.
# Within a category, order by the SPEC number (which is also alphabetical-by-label order).
def cat_sorted(eps: list[dict]) -> list[dict]:
    """INT block first, then FP; each block ordered by SPEC benchmark number."""
    return sorted(eps, key=lambda e: (bool(e["fp"]), e["benchmark"]))


def n_int(eps: list[dict]) -> int:
    return sum(1 for e in eps if not e["fp"])


def cat_divider(ax, eps: list[dict], axis: str = "y", offset: float = 0.0, label: bool = True):
    """Draw the INT|FP boundary on an axis whose ticks are cat_sorted(eps).

    `offset` is the coordinate of the first row: 0 for bar charts drawn at np.arange(n),
    1 for boxplots whose positions start at 1. Assumes the axis is already inverted for
    horizontal bars (top = first row), which is how every figure here draws them.
    """
    k = n_int(eps)
    if k == 0 or k == len(eps):
        return
    b = k - 0.5 + offset
    line = ax.axhline if axis == "y" else ax.axvline
    line(b, color="#7a8a99", lw=1.1, ls=(0, (4, 3)), zorder=5)
    if not label:
        return
    # Outside the right spine, not inside it: a bar that reaches 100 % would otherwise sit
    # under the label. clip_on=False is what lets it live past the axes edge.
    txt = dict(fontsize=8.4, color="#5a6b78", fontweight="bold", zorder=6, clip_on=False)
    if axis == "y":
        ax.text(1.014, (offset - 0.5 + b) / 2, "INT", transform=ax.get_yaxis_transform(),
                ha="left", va="center", rotation=90, **txt)
        ax.text(1.014, (b + len(eps) - 0.5 + offset) / 2, "FP",
                transform=ax.get_yaxis_transform(), ha="left", va="center", rotation=90, **txt)


# ---------------- level 1: whole-episode metrics -------------------------------------------------
def episodes(data: str = DATA) -> list[dict]:
    """Every episode's metrics.json, ordered by benchmark number. Fails loudly on a missing
    one: a silently short suite is how a 26-benchmark claim becomes a 24-benchmark figure."""
    out = []
    for name in sorted(os.listdir(data)):
        d = os.path.join(data, name)
        p = os.path.join(d, "metrics.json")
        if not os.path.isdir(d):
            continue
        if not os.path.exists(p):
            print(f"  ! {name}: no metrics.json (run extract_metrics.py)", file=sys.stderr)
            continue
        m = json.load(open(p))
        m["dir"] = d
        m["short"] = short(m["benchmark"])
        m["fp"] = is_fp(m["benchmark"])
        mp = os.path.join(d, "metadata.json")
        m["meta"] = json.load(open(mp)) if os.path.exists(mp) else {}
        out.append(m)
    return out


def comparison() -> dict:
    """The SPEC-vs-agentic table produced by ~/spec26-infra/infra/scripts/compare_spec_agentic.py.

    Both sides in that file are computed by ONE implementation (the capture kit's
    extract_metrics.py) over the shared eight counter groups only, so a difference here is a
    difference between workloads, not between two people's idea of what brMPKI means.
    """
    return json.load(open(COMPARISON))


def comparison_legacy() -> dict | None:
    """The pre-2026-08-07 agentic capture (SMT-ON, 20 logical CPUs, 2 s/5 s windows).

    Same SPEC side, same code, different agentic CONFIGURATION — so the difference between
    this and comparison() is the configuration, and nothing else.
    """
    if not os.path.exists(COMPARISON_LEGACY):
        return None
    return json.load(open(COMPARISON_LEGACY))


def is_replay(r: dict) -> bool:
    """Deterministic replay (trajectory re-executed, model never called) vs a LIVE episode.

    Provenance, not group count. Splitting on group count alone was wrong and shipped a wrong
    figure on 2026-08-06: three LIVE episodes (glm_swe_babel run_2/4/5) also dedicate a whole
    episode to one group via GORDER_OVERRIDE — they are the kit's method probes — so a
    "dedicated-group replay" population selected by group count silently contained three
    model-in-the-loop episodes. It moved the DRAM row materially (0.52x -> 0.92x).
    """
    return "glm_replay_swe_" in (r.get("dir") or "") or r.get("name", "").startswith("glm_replay_")


def agentic_split(c: dict) -> tuple[list[dict], list[dict]]:
    """Split the agentic side by INSTRUMENT, because the two kinds are not interchangeable.

    rotation  — 8 counter groups shuffled across the episode, exactly SPEC's instrument, so one
                episode yields a full metric card. n=7: six live episodes plus one replay
                anchor (glm_replay_swe_django/run_1, the live-vs-replay agreement check).
    replay    — one dedicated group for a whole DETERMINISTIC REPLAY episode: that group is
                live at 100 % duty and no model call sits inside the measured interval. Each
                supplies one metric family, so the population is read per metric, never as a
                whole.

    LIVE single-group probes are returned in NEITHER population — they share the replay's
    instrument but not its determinism, and they are method probes rather than measurements
    (see local_agents/SWE_clean/plots/MANIFEST.md). Excluding them is why `rot` + `rep` does
    not equal the loaded episode count.
    """
    rot = [r for r in c["agentic"] if len(r["groups"]) == 8]
    rep = [r for r in c["agentic"] if len(r["groups"]) == 1 and is_replay(r)]
    return rot, rep


# ---------------- level 2: per-window metrics ----------------------------------------------------
UNITS = {"msec", "usec", "nsec", "sec", "MiB", "KiB", "GiB", "B", "%"}
LINE = re.compile(r"^\s+([\d.,]+|<not counted>|<not supported>)\s+(\S+)(?:\s+(\S+))?")
ELAPSED = re.compile(r"^\s+([\d.]+)\s+seconds time elapsed")


def parse_window(path: str) -> tuple[dict[str, float], float]:
    """{event: count} plus perf's OWN elapsed time for that window.

    The elapsed time matters: a 100 ms window is 100 ms nominal but perf reports the interval
    it actually counted (0.1015–0.1035 s in this campaign). Rates like DRAM GB/s divide by the
    reported interval, never by the nominal one.
    """
    vals: dict[str, float] = {}
    el = 0.0
    with open(path, errors="replace") as f:
        for line in f:
            m = ELAPSED.match(line)
            if m:
                el = float(m.group(1))
                continue
            if "<not counted>" in line or "<not supported>" in line:
                continue
            m = LINE.match(line)
            if not m:
                continue
            raw, t2, t3 = m.groups()
            try:
                v = float(raw.replace(",", ""))
            except ValueError:
                continue
            ev = t3 if t2 in UNITS else t2
            if not ev or ev.startswith("#"):
                continue
            vals[ev] = vals.get(ev, 0.0) + v
    return vals, el


# metric -> (group it needs, unit label, "hi is bad?" is not encoded — figures decide)
WINDOW_METRICS: dict[str, tuple[str, str]] = {
    "IPC": ("*", "insn / cycle"),
    "brMPKI": ("fpbr", "mispredicts / 1000 insn"),
    "vecFP_pct": ("fpbr", "% of FP ops that are packed"),
    "L1D_MPKI": ("cache", "L1D load misses / 1000 insn"),
    "L2_MPKI": ("cache", "L2 load misses / 1000 insn"),
    "LLC_MPKI": ("cache", "demand-load L3 misses / 1000 insn"),
    "AMAT_cyc": ("cache", "cycles (fixed-latency model)"),
    "MLP": ("mlp", "outstanding L1D misses"),
    "DSB_pct": ("fe", "% of delivered uops"),
    "MITE_pct": ("fe", "% of delivered uops"),
    "MS_pct": ("fe", "% of delivered uops"),
    "LSD_pct": ("fe", "% of delivered uops"),
    "L1I_MPKI": ("fe_lat", "L2 code reads / 1000 insn"),
    "icache_data_stall_pct": ("fe_lat", "% of cycles"),
    "icache_tag_stall_pct": ("fe_lat", "% of cycles"),
    "resteer_pct": ("fe_lat", "% of cycles"),
    "ports_0_pct": ("core_ports", "% of cycles"),
    "ports_1_pct": ("core_ports", "% of cycles"),
    "ports_2_pct": ("core_ports", "% of cycles"),
    "div_active_pct": ("core_ports", "% of cycles"),
    "DRAM_read_GBs": ("dram_bw", "GB/s"),
    "dram_read_occ_pct": ("dram_bw", "% of cycles with a read outstanding"),
    "kernel_pct": ("priv", "% of cycles"),
    "ctx_switch_PKI": ("priv", "context switches / 1000 insn"),
    "pagefault_PKI": ("priv", "page faults / 1000 insn"),
    "bound_on_loads_pct": ("mem_bound", "% of cycles"),
    "stalls_l1d_miss_pct": ("mem_bound", "% of cycles"),
    "stalls_l2_miss_pct": ("mem_bound", "% of cycles"),
    "stalls_l3_miss_pct": ("mem_bound", "% of cycles"),
    "dsb2mite_penalty_pct": ("fe_l3x", "% of cycles"),
    "ms_switches_PKI": ("fe_l3x", "MS entries / 1000 insn"),
    "bound_on_stores_pct": ("fe_l3x", "% of cycles"),
    "itlb_walk_pct": ("fe_l3x", "% of cycles"),
    "baclears_MPKI": ("fe_miss", "BACLEARs / 1000 insn"),
    "dsb_miss_MPKI": ("fe_miss", "DSB misses / 1000 insn"),
    "misp_indirect_pct": ("fe_miss", "% of mispredicts that are indirect"),
}
# Gallery order: instruction supply -> branches -> memory ladder -> execution -> system.
GALLERY_ORDER = [
    "IPC",
    "DSB_pct", "MITE_pct", "MS_pct", "LSD_pct", "dsb_miss_MPKI", "dsb2mite_penalty_pct",
    "ms_switches_PKI",
    "L1I_MPKI", "icache_data_stall_pct", "icache_tag_stall_pct", "itlb_walk_pct",
    "brMPKI", "baclears_MPKI", "misp_indirect_pct", "resteer_pct",
    "L1D_MPKI", "L2_MPKI", "LLC_MPKI", "AMAT_cyc", "MLP",
    "bound_on_loads_pct", "stalls_l1d_miss_pct", "stalls_l2_miss_pct", "stalls_l3_miss_pct",
    "bound_on_stores_pct", "DRAM_read_GBs", "dram_read_occ_pct",
    "ports_0_pct", "ports_1_pct", "ports_2_pct", "div_active_pct", "vecFP_pct",
    "kernel_pct", "ctx_switch_PKI", "pagefault_PKI",
]


def _window_metrics(g: str, v: dict[str, float], el: float) -> dict[str, float]:
    """Derive every metric this ONE window can support. Same formulas as the episode-level
    extract_metrics.py, with both numerator and denominator taken from this window."""
    I = v.get("instructions") or v.get("instructions:u", 0.0) + v.get("instructions:k", 0.0)
    C = v.get("cycles") or v.get("cycles:u", 0.0) + v.get("cycles:k", 0.0)
    out: dict[str, float] = {}
    if I and C:
        out["IPC"] = I / C
    kpi = (lambda x: 1000.0 * x / I) if I else (lambda x: None)
    pct = (lambda x: 100.0 * x / C) if C else (lambda x: None)

    if g == "fpbr":
        if I and "branch-misses" in v:
            out["brMPKI"] = kpi(v["branch-misses"])
        sc = v.get("fp_arith_inst_retired.scalar", 0.0)
        pk = v.get("fp_arith_inst_retired.vector", 0.0)
        if sc + pk > 0:
            out["vecFP_pct"] = 100.0 * pk / (sc + pk)
    elif g == "cache":
        l1 = v.get("mem_load_retired.l1_hit", 0.0)
        l2 = v.get("mem_load_retired.l2_hit", 0.0)
        l3 = v.get("mem_load_retired.l3_hit", 0.0)
        lm = v.get("mem_load_retired.l3_miss", 0.0)
        if I and "mem_load_retired.l2_hit" in v:
            out["L1D_MPKI"] = kpi(l2 + l3 + lm)
        if I and "mem_load_retired.l3_hit" in v:
            out["L2_MPKI"] = kpi(l3 + lm)
        if I and "mem_load_retired.l3_miss" in v:
            out["LLC_MPKI"] = kpi(lm)
        loads = l1 + l2 + l3 + lm
        if loads and "mem_load_retired.l1_hit" in v:
            out["AMAT_cyc"] = (5 * l1 + 15 * l2 + 50 * l3 + 250 * lm) / loads
            # miss RATES (per-access %), same ladder as the agentic per-window layer
            out["L1D_missrate_pct"] = 100.0 * (l2 + l3 + lm) / loads
            if l2 + l3 + lm > 1e3:
                out["L2_missrate_pct"] = 100.0 * (l3 + lm) / (l2 + l3 + lm)
            if l3 + lm > 1e3:
                out["LLC_missrate_pct"] = 100.0 * lm / (l3 + lm)
    elif g == "mlp":
        pc = v.get("l1d_pend_miss.pending_cycles", 0.0)
        if pc:
            out["MLP"] = v.get("l1d_pend_miss.pending", 0.0) / pc
    elif g == "fe":
        ut = sum(v.get(k, 0.0) for k in ("idq.dsb_uops", "idq.mite_uops", "idq.ms_uops", "lsd.uops"))
        if ut:
            out["DSB_pct"] = 100.0 * v.get("idq.dsb_uops", 0.0) / ut
            out["MITE_pct"] = 100.0 * v.get("idq.mite_uops", 0.0) / ut
            out["MS_pct"] = 100.0 * v.get("idq.ms_uops", 0.0) / ut
            out["LSD_pct"] = 100.0 * v.get("lsd.uops", 0.0) / ut
    elif g == "fe_lat":
        if I and "l2_rqsts.all_code_rd" in v:
            out["L1I_MPKI"] = kpi(v["l2_rqsts.all_code_rd"])
        if C:
            for ev, k in (("icache_data.stalls", "icache_data_stall_pct"),
                          ("icache_tag.stalls", "icache_tag_stall_pct"),
                          ("int_misc.clear_resteer_cycles", "resteer_pct")):
                if ev in v:
                    out[k] = pct(v[ev])
    elif g == "core_ports":
        if C:
            for ev, k in (("exe_activity.exe_bound_0_ports", "ports_0_pct"),
                          ("exe_activity.1_ports_util", "ports_1_pct"),
                          ("exe_activity.2_ports_util", "ports_2_pct"),
                          ("arith.div_active", "div_active_pct")):
                if ev in v:
                    out[k] = pct(v[ev])
    elif g == "dram_bw":
        if el and "offcore_requests.data_rd" in v:
            out["DRAM_read_GBs"] = v["offcore_requests.data_rd"] * 64.0 / el / 1e9
        if C and "offcore_requests_outstanding.cycles_with_data_rd" in v:
            out["dram_read_occ_pct"] = pct(v["offcore_requests_outstanding.cycles_with_data_rd"])
    elif g == "priv":
        ck, cu = v.get("cycles:k", 0.0), v.get("cycles:u", 0.0)
        if ck + cu:
            out["kernel_pct"] = 100.0 * ck / (ck + cu)
        if I:
            if "context-switches" in v:
                out["ctx_switch_PKI"] = kpi(v["context-switches"])
            if "page-faults" in v:
                out["pagefault_PKI"] = kpi(v["page-faults"])
        # per busy CPU-second (task-clock is msec) — the agentic campaign's ctx rate
        tk = v.get("task-clock", 0.0)
        if tk > 10 and "context-switches" in v:
            out["ctx_per_cpu_s"] = v["context-switches"] / (tk / 1e3)
    elif g == "mem_bound":
        if C:
            for ev, k in (("exe_activity.bound_on_loads", "bound_on_loads_pct"),
                          ("memory_activity.stalls_l1d_miss", "stalls_l1d_miss_pct"),
                          ("memory_activity.stalls_l2_miss", "stalls_l2_miss_pct"),
                          ("memory_activity.stalls_l3_miss", "stalls_l3_miss_pct")):
                if ev in v:
                    out[k] = pct(v[ev])
    elif g == "fe_l3x":
        if C:
            for ev, k in (("dsb2mite_switches.penalty_cycles", "dsb2mite_penalty_pct"),
                          ("exe_activity.bound_on_stores", "bound_on_stores_pct"),
                          ("itlb_misses.walk_active", "itlb_walk_pct")):
                if ev in v:
                    out[k] = pct(v[ev])
        if I and "idq.ms_switches" in v:
            out["ms_switches_PKI"] = kpi(v["idq.ms_switches"])
    elif g == "fe_miss":
        if I:
            if "baclears.any" in v:
                out["baclears_MPKI"] = kpi(v["baclears.any"])
            if "frontend_retired.any_dsb_miss" in v:
                out["dsb_miss_MPKI"] = kpi(v["frontend_retired.any_dsb_miss"])
            if "br_misp_retired.cond" in v:
                out["branchDir_MPKI"] = kpi(v["br_misp_retired.cond"])
        mc, mi = v.get("br_misp_retired.cond", 0.0), v.get("br_misp_retired.indirect", 0.0)
        if mc + mi:
            out["misp_indirect_pct"] = 100.0 * mi / (mc + mi)
    return {k: x for k, x in out.items() if x is not None}


def windows(d: str, cache: bool = True) -> list[dict]:
    """Per-window metric rows for one episode: [{win, group, t, elapsed, <metrics>}, ...].

    `t` is seconds since the episode's first window, taken from windows.tsv (the realized
    rotation order is banked there, so nothing is reconstructed from filenames).
    Cached as windows_metrics.json inside the episode dir — re-parsing 22k perf text files
    for every figure is minutes of pure I/O.
    """
    cp = os.path.join(d, "windows_metrics.json")
    if cache and os.path.exists(cp) and os.path.getmtime(cp) > os.path.getmtime(__file__):
        return json.load(open(cp))

    tstart: dict[str, float] = {}
    wt = os.path.join(d, "windows.tsv")
    t0 = None
    if os.path.exists(wt):
        for ln in open(wt):
            p = ln.rstrip("\n").split("\t")
            if len(p) < 3 or p[0] == "win":
                continue
            try:
                ts = float(p[2])
            except ValueError:
                continue
            tstart[f"{p[1]}_w{p[0]}"] = ts
            t0 = ts if t0 is None else min(t0, ts)

    rows = []
    for fn in sorted(os.listdir(d)):
        m = re.match(r"^group_(.+)_w(\d+)\.txt$", fn)
        if not m:
            continue
        g, w = m.group(1), m.group(2)
        v, el = parse_window(os.path.join(d, fn))
        if not v:
            continue
        # cyc/insn are kept raw (not as "metrics"): the instrument figure needs the episode's
        # windowed cycle total to cross-check slots/cycle against the core's issue width.
        r = {"win": int(w), "group": g, "elapsed": el,
             "cyc": v.get("cycles") or (v.get("cycles:u", 0.0) + v.get("cycles:k", 0.0)),
             "insn": v.get("instructions") or (v.get("instructions:u", 0.0)
                                               + v.get("instructions:k", 0.0))}
        ts = tstart.get(f"{g}_w{w}")
        r["t"] = (ts - t0) if (ts is not None and t0 is not None) else None
        r.update(_window_metrics(g, v, el))
        rows.append(r)
    rows.sort(key=lambda r: r["win"])
    if cache:
        try:
            json.dump(rows, open(cp, "w"))
        except OSError:
            pass
    return rows


def series(rows: list[dict], metric: str) -> tuple[np.ndarray, np.ndarray]:
    """(t, value) for one metric, over exactly the windows where it was measured."""
    t = [r["t"] for r in rows if metric in r and r.get("t") is not None]
    v = [r[metric] for r in rows if metric in r and r.get("t") is not None]
    return np.asarray(t, float), np.asarray(v, float)


def duty(rows: list[dict], d: str) -> float | None:
    """Fraction of the episode with counters actually installed.

    Perf's own "seconds time elapsed" summed over every window, divided by the span the
    windows cover. It must NOT be computed from windows.tsv timestamps alone: those are
    taken before launching and after reaping perf, so they include the ~20 ms per-window
    setup gap and sum to ~100 % by construction.
    """
    counted = sum(r.get("elapsed", 0.0) for r in rows)
    lo = hi = None
    wt = os.path.join(d, "windows.tsv")
    if not os.path.exists(wt):
        return None
    for ln in open(wt):
        p = ln.rstrip("\n").split("\t")
        if len(p) < 4 or p[0] == "win":
            continue
        try:
            s, e = float(p[2]), float(p[3])
        except ValueError:
            continue
        lo = s if lo is None else min(lo, s)
        hi = e if hi is None else max(hi, e)
    if lo is None or hi is None or hi <= lo or not counted:
        return None
    return min(1.0, counted / (hi - lo))


def window_budget(ep: dict) -> dict | None:
    """Where an episode's wall time went, and why it does not buy wall/WINSEC windows.

    A 100 ms window does NOT occupy 100 ms of wall clock. perf has to be torn down and
    re-armed between windows (a fixed ~22 ms), so the window PITCH is ~122 ms; on top of
    that each episode has a lead-in before the first window is armed and a teardown after
    the benchmark exits (flush the continuous TMA census, stop the pollers and the 99 Hz
    record, stop the scope) during which no window is running.

        windows = (wall - lead_in - teardown) / pitch

    Short episodes pay the fixed teardown out of a small budget, so they land furthest from
    the naive wall/WINSEC figure: 729.abc_r gets 86 windows where wall/0.1 would suggest 117.
    """
    p = os.path.join(ep["dir"], "windows.tsv")
    if not os.path.exists(p):
        return None
    ts = []
    for ln in open(p):
        f = ln.rstrip("\n").split("\t")
        if len(f) < 4 or f[0] == "win":
            continue
        try:
            ts.append((float(f[2]), float(f[3])))
        except ValueError:
            continue
    meta = ep.get("meta") or {}
    if not ts or not meta.get("ts_start"):
        return None
    lo, hi, n = min(a for a, _ in ts), max(b for _, b in ts), len(ts)
    winsec = float(meta.get("winsec") or 0.1)
    return {"wall_s": ep["wall_s"], "lead_in_s": lo - meta["ts_start"],
            "teardown_s": meta["ts_end"] - hi, "windowing_s": hi - lo,
            "pitch_s": (hi - lo) / n, "windows": n,
            "naive_windows": ep["wall_s"] / winsec,
            "pct_of_naive": 100.0 * n / (ep["wall_s"] / winsec)}


def slots_per_cycle(ep: dict, rows: list[dict]) -> float | None:
    """Cross-instrument check: continuous-TMA slots against windowed cycles.

    The two instruments never share a counter. TMA sees the whole episode; the windowed
    groups see only their duty cycle, so the windowed cycle total is scaled back to
    whole-episode equivalent before dividing. On this Golden Cove core the answer must be
    the issue width, 6.
    """
    slots = (ep.get("tma") or {}).get("slots") or 0.0
    cyc = sum(r.get("cyc", 0.0) for r in rows)
    dc = duty(rows, ep["dir"])
    if not slots or not cyc or not dc:
        return None
    return slots / (cyc / dc)
