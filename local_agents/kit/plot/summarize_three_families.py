#!/usr/bin/env python3
"""summarize_three_families.py — the SPEC / Agentic / DCPerf comparison table, computed from
the banked per-window data so every number in the study README is reproducible.

Votes are formed identically for all three families: one value per WORKLOAD, equal to the
median of that workload's 100 ms windows on the merged fence. The family figure is then the
median over its workloads' votes (for DCPerf with a single benchmark, that IS its vote).

    ~/miniforge3/envs/infersuite-full/bin/python3 local_agents/kit/plot/summarize_three_families.py [--md]
"""
from __future__ import annotations

import collections
import csv
import os
import statistics as st
import sys

REPO = os.path.expanduser("~/InferSuite")
AGG = f"{REPO}/local_agents/ML_iso36/data/l3_study/agg_rows_long.csv"
DCP = f"{REPO}/local_agents/DCPerf/data/l3_study/dcperf_rows_long.csv"
LANGS = ["C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript"]
METRICS = ["IPC", "Branch MPKI", "Branch-direction MPKI", "BTB MPKI (BAClears)",
           "L1I MPKI (code-read)", "uop-cache (DSB) MPKI", "DSB coverage (%)",
           "L1D-load MPKI", "L2-load MPKI", "LLC MPKI", "DRAM read (GB/s)",
           "Context switches (/CPU-s)"]
MD = "--md" in sys.argv

spec = collections.defaultdict(list)
ag = collections.defaultdict(lambda: collections.defaultdict(list))
for r in csv.DictReader(open(AGG)):
    if r["fence"] != "both" or r["metric"] not in METRICS:
        continue
    v = float(r["value"])
    if r["grp"] in ("SPEC-int", "SPEC-fp"):
        spec[r["metric"]].append(v)          # already one value per benchmark
    elif r["grp"] in LANGS:
        ag[r["metric"]][r["col"]].append(v)  # per-window; median = the task's vote

dc = collections.defaultdict(lambda: collections.defaultdict(list))
if os.path.exists(DCP):
    for r in csv.DictReader(open(DCP)):
        if r["fence"] == "both" and r["metric"] in METRICS:
            dc[r["metric"]][r["col"]].append(float(r["value"]))

benches = sorted({b for m in dc for b in dc[m]})
hdr = ["Metric", "SPEC", "Agentic 36"] + [f"DCPerf {b}" for b in benches] + \
      ["Agentic/SPEC"] + [f"{b}/SPEC" for b in benches]
rows = []
for m in METRICS:
    s = st.median(spec[m]) if spec[m] else float("nan")
    a = st.median([st.median(v) for v in ag[m].values()]) if ag[m] else float("nan")
    ds = [st.median(dc[m][b]) for b in benches if b in dc[m]]
    def rat(x):
        if s == 0:
            return "n/a" if x == 0 else "∞"
        return f"{x / s:.3g}"
    def f(x):
        return f"{x:.4g}"
    rows.append([m, f(s), f(a)] + [f(x) for x in ds] + [rat(a)] + [rat(x) for x in ds])

if MD:
    print("| " + " | ".join(hdr) + " |")
    print("|" + "|".join("---" for _ in hdr) + "|")
    for r in rows:
        print("| " + " | ".join(r) + " |")
else:
    wds = [max(len(hdr[i]), max((len(r[i]) for r in rows), default=0)) for i in range(len(hdr))]
    print("  ".join(h.ljust(wds[i]) for i, h in enumerate(hdr)))
    for r in rows:
        print("  ".join(c.ljust(wds[i]) for i, c in enumerate(r)))
n_ag = len(ag["IPC"]) if ag["IPC"] else 0
print(f"\nvotes: SPEC {len(spec['IPC'])} benchmarks · Agentic {n_ag} tasks · "
      f"DCPerf {len(benches)} benchmark(s) [{', '.join(benches)}]", file=sys.stderr)
