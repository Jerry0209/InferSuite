#!/usr/bin/env python3
"""export_agg_rows_long.py — long-format export behind the aggregated per-window rows
figure (ggplot rendering): one row per (fence, metric, column, window-value).

Columns: SPEC-int / SPEC-fp (ONE value per benchmark = the median of its windows for that
metric — the suite box is over per-benchmark medians, one vote each), Python (scikit-learn,
astropy, sympy per-window from the matched SWE_iso8 replays), and the 36 count-view picks
per-window. 16 metrics (the 18 minus MLP and AMAT, dropped by mentor request 2026-08-27).

Output: local_agents/ML_iso36/data/l3_study/agg_rows_long.csv (derived, gitignored data).

    /home/thu/miniforge3/envs/infersuite-full/bin/python local_agents/kit/plot/export_agg_rows_long.py
"""
from __future__ import annotations

import collections
import csv
import os
import statistics as st
import sys

REPO = os.path.expanduser("~/InferSuite")
L3 = f"{REPO}/local_agents/ML_iso36/data/l3_study"
PYL3 = f"{REPO}/local_agents/SWE_iso8/data/l3_study"
SEL = f"{REPO}/local_agents/ML_typeid/selection_36_count.tsv"
sys.path.insert(0, f"{REPO}/spec26/kit/plot")
from spec_common import episodes as spec_episodes, windows as spec_windows  # noqa: E402

LANGS = ["C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript"]
PYTASKS = ["scikit-learn", "astropy", "sympy"]
# (agent window key, SPEC window key, display label)
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

sel = [r for r in csv.DictReader(open(SEL), delimiter="\t") if "__" in r.get("instance", "")]
by_lang = collections.defaultdict(list)
for r in sel:
    r["disp"] = r["instance"].split("__", 1)[1]
    by_lang[r["lang"]].append(r)

out = open(f"{L3}/agg_rows_long.csv", "w", newline="")
w = csv.writer(out)
w.writerow(["fence", "metric", "grp", "col", "value"])
n = 0

print("SPEC per-benchmark window-medians ...")
SPEC = spec_episodes()
for e in SPEC:
    rows = spec_windows(e["dir"])
    g = "SPEC-fp" if e["fp"] else "SPEC-int"
    for _ak, sk, lab in METRICS:
        v = [r[sk] for r in rows if sk in r and r[sk] is not None]
        if len(v) >= 5:
            for fence in ("tool", "harness"):
                w.writerow([fence, lab, g, g, round(st.median(v), 5)]); n += 1

def dump_windows(path, grp, col):
    global n
    if not os.path.exists(path):
        return
    for r in csv.DictReader(open(path)):
        for ak, _sk, lab in METRICS:
            if r["metric"] == ak and r["fence"] in ("tool", "harness"):
                w.writerow([r["fence"], lab, grp, col, r["value"]]); n += 1
                break

print("Python per-window ...")
for t in PYTASKS:
    dump_windows(f"{PYL3}/all_windows_{t}.csv", "Python", t)
print("36 picks per-window ...")
for lang in LANGS:
    for r in by_lang[lang]:
        dump_windows(f"{L3}/all_windows_{r['short']}.csv", lang, r["disp"])
out.close()
print(f"wrote {L3}/agg_rows_long.csv: {n} rows")
