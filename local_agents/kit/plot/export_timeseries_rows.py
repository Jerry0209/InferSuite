#!/usr/bin/env python3
"""export_timeseries_rows.py — the per-window measurements of EVERY family in time order, one
gzipped CSV per family, for anyone who wants to try an aggregation other than ours.

The rows_long files the figures read (agg_rows_long.csv, <suite>_rows_long.csv) drop the
window's position in time. This export keeps it. Uniform schema across the four families:

    family      spec26 | agentic36 | dcperf | renaissance | dacapo
    workload    benchmark or task name as it appears in the figures
    run         run_N -- the profiling run the window came from (SPEC: the single episode)
    group       the counter group live in that window (decides which metrics it carries)
    win         window index inside the run, in capture order
    t_rel_s     seconds since the FIRST window of that run (0 = start of capture)
    dur_s       the window's own counting time (perf's "seconds time elapsed"), ~0.1
    tag         agentic only: what the tool fence was doing (2 Hz command tagger); blank else
    metric      display label, same vocabulary as the figures
    value       the metric in that window (co-counted: numerator and denominator from the
                same window), fence "both" = the whole workload

One row per (window, metric). A window carries only the metrics its counter group can
produce, so rows per window differ by group (fpbr -> IPC + Branch MPKI, priv -> context
switches, ...). Sizes: agentic ~600 k rows, SPEC ~60 k, JVM ~150 k, DCPerf ~50 k.

    PY=~/miniforge3/envs/infersuite-full/bin/python3
    $PY local_agents/kit/plot/export_timeseries_rows.py [--out DIR]
"""
from __future__ import annotations

import argparse
import csv
import glob
import gzip
import os
import sys

REPO = os.path.expanduser("~/InferSuite")
sys.path.insert(0, f"{REPO}/spec26/kit/plot")

# (agent/kit window key, SPEC window key, display label) -- the figures' vocabulary
METRICS = [
    ("IPC", "IPC", "IPC"),
    ("branch_MPKI", "brMPKI", "Branch MPKI"),
    ("branchDir_MPKI", "branchDir_MPKI", "Branch-direction MPKI"),
    ("BTB_MPKI", "baclears_MPKI", "BTB MPKI (BAClears)"),
    ("DSB_pct", "DSB_pct", "DSB coverage (%)"),
    ("uopCache_MPKI", "dsb_miss_MPKI", "uop-cache (DSB) MPKI"),
    ("codeRead_MPKI_L1I", "L1I_MPKI", "L1I MPKI (code-read)"),
    ("L1D_MPKI", "L1D_MPKI", "L1D-load MPKI"),
    ("L2_MPKI", "L2_MPKI", "L2-load MPKI"),
    ("LLC_MPKI", "LLC_MPKI", "LLC MPKI"),
    ("icache_data_stall_pct", "icache_data_stall_pct", "L1I stall (% cycles)"),
    ("L1D_missrate_pct", "L1D_missrate_pct", "L1D miss rate (%)"),
    ("L2_missrate_pct", "L2_missrate_pct", "L2-load miss rate (%)"),
    ("LLC_missrate_pct", "LLC_missrate_pct", "LLC miss rate (%)"),
    ("dram_rd_GBs", "DRAM_read_GBs", "DRAM read (GB/s)"),
    ("ctx_per_cpu_s", "ctx_per_cpu_s", "Context switches (/CPU-s)"),
]
AK = {a: lab for a, _s, lab in METRICS}
SK = {s: lab for _a, s, lab in METRICS}
HEADER = ["family", "workload", "run", "group", "win", "t_rel_s", "dur_s", "tag", "metric", "value"]


def kit_windows(path: str, family: str, workload: str, w):
    """all_windows_<x>.csv (analyze_l3_windows.py) -> rows; t_rel per run from that run's first window."""
    rows = [r for r in csv.DictReader(open(path)) if r["fence"] == "both" and r["metric"] in AK]
    t0 = {}
    for r in rows:
        t0[r["run"]] = min(t0.get(r["run"], float("inf")), float(r["t0"]))
    n = 0
    for r in sorted(rows, key=lambda r: (r["run"], int(r["win"]))):
        w.writerow([family, workload, r["run"], r["group"], int(r["win"]),
                    round(float(r["t0"]) - t0[r["run"]], 3), r["dur"],
                    r.get("tag", "") if family == "agentic36" else "",
                    AK[r["metric"]], r["value"]])
        n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=f"{REPO}/local_agents/JVMbench/data/l3_study/timeseries")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    def opener(family):
        p = f"{a.out}/timeseries_{family}.csv.gz"
        fh = gzip.open(p, "wt", newline="")
        w = csv.writer(fh)
        w.writerow(HEADER)
        return p, fh, w

    # ---- SPEC CPU 2026: one episode per benchmark, groups rotating inside it
    from spec_common import episodes, windows  # noqa: E402
    p, fh, w = opener("spec26")
    n = 0
    for e in episodes():
        bench = os.path.basename(e["dir"].rstrip("/"))
        for r in windows(e["dir"]):
            if r.get("t") is None:
                continue
            for sk, lab in SK.items():
                if r.get(sk) is not None:
                    w.writerow(["spec26", bench, "run_1", r["group"], r["win"], round(r["t"], 3),
                                round(r.get("elapsed", 0.0), 4), "", lab, r[sk]])
                    n += 1
    fh.close()
    print(f"{p}: {n} rows")

    # ---- agentic 36: the count-view picks, nine dedicated-group replays each
    sel = [r for r in csv.DictReader(open(f"{REPO}/local_agents/ML_typeid/selection_36_count.tsv"), delimiter="\t")
           if "__" in r.get("instance", "")]
    p, fh, w = opener("agentic36")
    n = 0
    for r in sel:
        disp = r["instance"].split("__", 1)[1]
        path = f"{REPO}/local_agents/ML_iso36/data/l3_study/all_windows_{r['short']}.csv"
        if os.path.exists(path):
            n += kit_windows(path, "agentic36", disp, w)
    fh.close()
    print(f"{p}: {n} rows")

    # ---- external suites profiled with kit/dcperf: nine dedicated-group runs each
    for family, data in (("dcperf", f"{REPO}/local_agents/DCPerf/data"),
                         ("renaissance", f"{REPO}/local_agents/JVMbench/data"),
                         ("dacapo", f"{REPO}/local_agents/JVMbench/data"),
                         ("realdata", f"{REPO}/local_agents/RealData/data")):
        p, fh, w = opener(family)
        n = 0
        for d in sorted(glob.glob(f"{data}/{family}_*")):
            wl = os.path.basename(d)[len(family) + 1:]
            if os.path.exists(f"{d}/EXCLUDED") or not glob.glob(f"{d}/run_*/DONE"):
                continue
            path = f"{data}/l3_study/all_windows_{wl}.csv"
            if os.path.exists(path):
                n += kit_windows(path, family, wl, w)
        fh.close()
        print(f"{p}: {n} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
