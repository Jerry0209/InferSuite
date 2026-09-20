#!/usr/bin/env python3
"""export_dcperf_rows.py — put an external benchmark SUITE's per-window metrics into the same
long format and metric vocabulary as the SPEC and agentic rows, so one plotting path serves
every family. Generalised 2026-09-14 from DCPerf-only to any suite profiled by
kit/dcperf/run_dcperf_profile.sh (DCPerf, Renaissance, DaCapo ...).

Input : <data>/l3_study/all_windows_<workload>.csv for each <data>/<suite>_<workload>/ run dir
        (written by analyze_l3_windows.py -- the SAME derivation code the 36 tasks use)
Output: <out> with columns fence, metric, grp, col, value   (grp = <label>, col = workload)

Only the merged fence is exported ("both"), which for a single-fence benchmark is the server
fence itself -- the counterpart of the agent's merged tool+harness fence.

    export_dcperf_rows.py [--suite dcperf] [--label DCPerf] [--data local_agents/DCPerf/data]
                          [--out <data>/l3_study/<suite>_rows_long.csv]
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import statistics as st
import sys

REPO = os.path.expanduser("~/InferSuite")
ap = argparse.ArgumentParser()
ap.add_argument("--suite", default="dcperf")
ap.add_argument("--label", default=None, help="family label in the figures (default: suite, DCPerf for dcperf)")
ap.add_argument("--data", default=f"{REPO}/local_agents/DCPerf/data")
ap.add_argument("--out", default=None)
a = ap.parse_args()
LABEL = a.label or {"dcperf": "DCPerf", "renaissance": "Renaissance", "dacapo": "DaCapo", "realdata": "RealData"}.get(a.suite, a.suite)
L3 = f"{a.data}/l3_study"
OUT = a.out or f"{L3}/{a.suite}_rows_long.csv"

# (window-metric key, display label) -- identical labels to export_agg_rows_long.py's METRICS
METRICS = [
    ("IPC", "IPC"),
    ("branch_MPKI", "Branch MPKI"),
    ("branchDir_MPKI", "Branch-direction MPKI"),
    ("BTB_MPKI", "BTB MPKI (BAClears)"),
    ("DSB_pct", "DSB coverage (%)"),
    ("uopCache_MPKI", "uop-cache (DSB) MPKI"),
    ("codeRead_MPKI_L1I", "L1I MPKI (code-read)"),
    ("L1D_MPKI", "L1D-load MPKI"),
    ("L2_MPKI", "L2-load MPKI"),
    ("LLC_MPKI", "LLC MPKI"),
    ("icache_data_stall_pct", "L1I stall (% cycles)"),
    ("L1D_missrate_pct", "L1D miss rate (%)"),
    ("L2_missrate_pct", "L2-load miss rate (%)"),
    ("LLC_missrate_pct", "LLC miss rate (%)"),
    ("dram_rd_GBs", "DRAM read (GB/s)"),
    ("ctx_per_cpu_s", "Context switches (/CPU-s)"),
]
LAB = dict(METRICS)

# the suite's workloads are the run dirs that carry its prefix and are complete
wls = []
for d in sorted(glob.glob(f"{a.data}/{a.suite}_*")):
    if not os.path.isdir(d):
        continue
    wl = os.path.basename(d)[len(a.suite) + 1:]
    if os.path.exists(f"{d}/EXCLUDED"):        # a capture that failed validation; reason inside
        print(f"  excluded {a.suite}/{wl}: {open(f'{d}/EXCLUDED').read().strip()}", file=sys.stderr)
        continue
    if glob.glob(f"{d}/run_*/DONE") and os.path.exists(f"{L3}/all_windows_{wl}.csv"):
        wls.append(wl)
if not wls:
    sys.exit(f"no derived workloads for suite '{a.suite}' under {a.data} — run derive first")

os.makedirs(L3, exist_ok=True)
out = open(OUT, "w", newline="")
w = csv.writer(out)
w.writerow(["fence", "metric", "grp", "col", "value"])
n = 0
summary = {}
for wl in wls:
    vals = {}
    for r in csv.DictReader(open(f"{L3}/all_windows_{wl}.csv")):
        if r["fence"] != "both":
            continue
        lab = LAB.get(r["metric"])
        if lab is None:
            continue
        vals.setdefault(lab, []).append(float(r["value"]))
    for lab, v in vals.items():
        for x in v:
            w.writerow(["both", lab, LABEL, wl, x])
            n += 1
        summary.setdefault(wl, {})[lab] = (len(v), st.median(v))
out.close()
print(f"wrote {OUT}: {n} rows, family '{LABEL}', workloads {wls}")
for wl, m in summary.items():
    print(f"\n{wl}:")
    for _k, lab in METRICS:
        if lab in m:
            cnt, med = m[lab]
            print(f"   {lab:<28} median {med:>10.4g}   ({cnt} windows)")
