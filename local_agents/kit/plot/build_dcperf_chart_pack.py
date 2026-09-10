#!/usr/bin/env python3
"""build_dcperf_chart_pack.py — assemble one VERSIONED DCPerf chart pack, in the same mentor
layout every other figure version in this repo uses (see local_agents/ML_iso36/charts/README):

    local_agents/DCPerf/charts/$VERSION/
      Raw data/     one CSV per figure — every number the figure displays
      Scripts/      the generator per figure (copy; header names the canonical path)
      Figures/PDF/  -> paper
      Figures/PNG/  -> slides
      README.md

    VERSION=v1_2026-09-10_feedsim python3 local_agents/kit/plot/build_dcperf_chart_pack.py
"""
import gzip
import os
import shutil

import pandas as pd

REPO = os.path.expanduser("~/InferSuite")
DC = f"{REPO}/local_agents/DCPerf"
KP = f"{REPO}/local_agents/kit/plot"
SRC = f"{DC}/plots/paper_v1"
CH = f"{DC}/charts/" + os.environ.get("VERSION", "v1_2026-09-10_feedsim")
RAW, SCR = f"{CH}/Raw data", f"{CH}/Scripts"
FPDF, FPNG = f"{CH}/Figures/PDF", f"{CH}/Figures/PNG"
for d in (RAW, SCR, FPDF, FPNG):
    os.makedirs(d, exist_ok=True)

FIGS = [
    ("fig01", "agg_compact3", "plot_paper_agg_compact3.R",
     "12-metric SPEC vs Agentic vs DCPerf grid; violins are distributions over WORKLOADS, "
     "DCPerf is one workload so it is a marker at its vote"),
    ("fig02", "agg_ipc_3way", "plot_paper_agg_groups3.R",
     "IPC per 100 ms window: SPEC band, 36 agentic tasks by language, DCPerf column"),
    ("fig03", "agg_frontend_3way", "plot_paper_agg_groups3.R",
     "frontend metrics per window (Branch/Branch-dir/BTB/L1I/DSB MPKI, DSB coverage)"),
    ("fig04", "agg_memory_3way", "plot_paper_agg_groups3.R",
     "memory metrics per window (L1D/L2/LLC MPKI, DRAM read GB/s)"),
    ("fig05", "agg_system_3way", "plot_paper_agg_groups3.R",
     "context switches per CPU-second, log axis"),
]

for fid, name, script, _d in FIGS:
    stem = f"{SRC}/dcperf_{name}"
    if not os.path.exists(f"{stem}.png"):
        print(f"  SKIP {fid}: {stem}.png missing")
        continue
    shutil.copy(f"{stem}.pdf", f"{FPDF}/{fid}_{name}.pdf")
    shutil.copy(f"{stem}.png", f"{FPNG}/{fid}_{name}.png")
    dst = f"{SCR}/{fid}_{name}{os.path.splitext(script)[1]}"
    body = open(f"{KP}/{script}").read()
    hdr = ("#!/usr/bin/env Rscript\n"
           f"# {fid}_{name} — COPY of the canonical generator local_agents/kit/plot/{script}\n"
           "# (single source of truth; edit THERE). Runs from the repo root against the banked\n"
           "# data tree and writes into local_agents/DCPerf/plots/paper_v1/.\n"
           "# Regenerate: see this pack's README.md.\n")
    body = body.split("\n", 1)[1] if body.startswith("#!") else body
    open(dst, "w").write(hdr + body)

# raw data
shutil.copy(f"{SRC}/dcperf_agg_compact3_numbers.csv", f"{RAW}/fig01_agg_compact3.csv")
shutil.copy(f"{SRC}/dcperf_agg_3way_numbers.csv", f"{RAW}/fig02-05_agg_3way_column_medians.csv")
dcp = f"{DC}/data/l3_study/dcperf_rows_long.csv"
if os.path.exists(dcp):
    d = pd.read_csv(dcp)
    with gzip.open(f"{RAW}/dcperf_per_window_rows.csv.gz", "wt") as fh:
        d.to_csv(fh, index=False)
cal = f"{DC}/data/calibration/feedsim_calibration.csv"
if os.path.exists(cal):
    shutil.copy(cal, f"{RAW}/feedsim_operating_point_calibration.csv")

lines = [f"# DCPerf chart pack — {os.path.basename(CH)}", "",
         "Same layout as the ML_iso36 packs: one raw-data file, one script and one PDF+PNG per",
         "figure. **PDF → paper, PNG → slides.** Figures compare three workload families:",
         "SPEC CPU 2026 (26 benchmarks), the agentic 36 (SWE-bench Multilingual) and DCPerf.",
         "",
         "**Read fig01 with its unit rule in mind:** a violin is a distribution over WORKLOADS",
         "(SPEC contributes 26, the agentic family 36). DCPerf contributes one profiled",
         "benchmark, so it is drawn as a marker at its vote — the median of its steady-state",
         "windows, the same statistic every other vote uses — with a bar for its own window",
         "IQR, which is a within-workload spread and a different quantity. fig02–fig05 are the",
         "unit-consistent companions: every column there is a distribution over 100 ms windows.",
         "",
         "Method, operating point and findings: `../../README.md`.",
         "",
         "| Fig | Name | What it shows | Raw data |",
         "|---|---|---|---|"]
for fid, name, _s, desc in FIGS:
    raw = "fig01_agg_compact3.csv" if fid == "fig01" else "fig02-05_agg_3way_column_medians.csv"
    lines.append(f"| {fid} | {name} | {desc} | `Raw data/{raw}` |")
lines += ["",
          "`Raw data/dcperf_per_window_rows.csv.gz` holds every DCPerf per-window value behind",
          "these figures; `feedsim_operating_point_calibration.csv` is the QPS sweep that chose",
          "the 16 QPS operating point (highest point meeting DCPerf's own p95 ≤ 500 ms).",
          "Regenerate: run the scripts with the `rplot` env Rscript from the repo root, then",
          "rerun `local_agents/kit/plot/build_dcperf_chart_pack.py` with VERSION set."]
open(f"{CH}/README.md", "w").write("\n".join(lines) + "\n")
print("chart pack assembled at", CH)
for root, _dirs, files in os.walk(CH):
    for f in sorted(files):
        p = os.path.join(root, f)
        print(f"  {os.path.relpath(p, CH):<48} {os.path.getsize(p)/1e6:6.2f} MB")
