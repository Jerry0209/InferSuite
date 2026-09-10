#!/usr/bin/env python3
"""export_dcperf_rows.py — put DCPerf per-window metrics into the SAME long format and the
same metric vocabulary as the SPEC and agentic rows, so one plotting path serves all three.

Input : local_agents/DCPerf/data/l3_study/all_windows_<bench>.csv
        (written by analyze_l3_windows.py -- the SAME derivation code the 36 tasks use,
         invoked with L3_BASE_PREFIX=dcperf_ and a single-fence L3_FENCES map)
Output: local_agents/DCPerf/data/l3_study/dcperf_rows_long.csv
        columns: fence, metric, grp, col, value      (grp = "DCPerf", col = benchmark name)

Only the merged fence is exported ("both"), which for a single-fence DCPerf benchmark is the
server fence itself -- the counterpart of the agent's merged tool+harness fence.

    ~/miniforge3/envs/infersuite-full/bin/python3 local_agents/kit/plot/export_dcperf_rows.py
"""
from __future__ import annotations

import csv
import glob
import os
import statistics as st
import sys

REPO = os.path.expanduser("~/InferSuite")
L3 = f"{REPO}/local_agents/DCPerf/data/l3_study"

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

files = sorted(glob.glob(f"{L3}/all_windows_*.csv"))
if not files:
    sys.exit(f"no all_windows_*.csv under {L3} — run analyze_l3_windows.py first")

out = open(f"{L3}/dcperf_rows_long.csv", "w", newline="")
w = csv.writer(out)
w.writerow(["fence", "metric", "grp", "col", "value"])
n = 0
summary = {}
for f in files:
    bench = os.path.basename(f)[len("all_windows_"):-len(".csv")]
    vals = {}
    for r in csv.DictReader(open(f)):
        if r["fence"] != "both":
            continue
        lab = LAB.get(r["metric"])
        if lab is None:
            continue
        vals.setdefault(lab, []).append(float(r["value"]))
    for lab, v in vals.items():
        for x in v:
            w.writerow(["both", lab, "DCPerf", bench, x])
            n += 1
        summary.setdefault(bench, {})[lab] = (len(v), st.median(v))
out.close()
print(f"wrote {L3}/dcperf_rows_long.csv: {n} rows")
for bench, m in summary.items():
    print(f"\n{bench}:")
    for _k, lab in METRICS:
        if lab in m:
            cnt, med = m[lab]
            print(f"   {lab:<28} median {med:>10.4g}   ({cnt} windows)")
