#!/usr/bin/env python3
"""build_jvm_chart_pack.py — assemble one VERSIONED chart pack for the multi-suite figures
(SPEC · agentic 36 · DCPerf · Renaissance · DaCapo), same mentor layout as every other pack:

    local_agents/JVMbench/charts/$VERSION/{Raw data,Scripts,Figures/{PDF,PNG},README.md}

    VERSION=v1_2026-09-14_jvm-suites python3 local_agents/kit/plot/build_jvm_chart_pack.py
"""
import gzip
import os
import shutil

import pandas as pd

REPO = os.path.expanduser("~/InferSuite")
JV = f"{REPO}/local_agents/JVMbench"
KP = f"{REPO}/local_agents/kit/plot"
SRC = f"{JV}/plots/paper_v1"
CH = f"{JV}/charts/" + os.environ.get("VERSION", "v1_2026-09-14_jvm-suites")
RAW, SCR = f"{CH}/Raw data", f"{CH}/Scripts"
FPDF, FPNG = f"{CH}/Figures/PDF", f"{CH}/Figures/PNG"
for d in (RAW, SCR, FPDF, FPNG):
    os.makedirs(d, exist_ok=True)

FIGS = [
    ("fig01", "agg_compact", "plot_paper_agg_compact_ext.R",
     "12-metric grid: SPEC and agentic violins (one vote per workload), one marker per external benchmark grouped by suite"),
    ("fig02", "agg_ipc", "plot_paper_agg_groups_ext.R", "IPC per 100 ms window, one column per benchmark, one block per suite"),
    ("fig03", "agg_frontend", "plot_paper_agg_groups_ext.R", "frontend metrics per window"),
    ("fig04", "agg_memory", "plot_paper_agg_groups_ext.R", "memory metrics per window"),
    ("fig05", "agg_system", "plot_paper_agg_groups_ext.R", "context switches per CPU-second, log axis"),
]
for fid, name, script, _d in FIGS:
    stem = f"{SRC}/multi_{name}"
    if not os.path.exists(f"{stem}.png"):
        print(f"  SKIP {fid}: {stem}.png missing"); continue
    shutil.copy(f"{stem}.pdf", f"{FPDF}/{fid}_{name}.pdf")
    shutil.copy(f"{stem}.png", f"{FPNG}/{fid}_{name}.png")
    body = open(f"{KP}/{script}").read()
    hdr = ("#!/usr/bin/env Rscript\n"
           f"# {fid}_{name} — COPY of the canonical generator local_agents/kit/plot/{script}\n"
           "# (single source of truth; edit THERE). Runs from the repo root against the banked\n"
           "# data trees and writes into local_agents/JVMbench/plots/paper_v1/.\n")
    body = body.split("\n", 1)[1] if body.startswith("#!") else body
    open(f"{SCR}/{fid}_{name}.R", "w").write(hdr + body)

for f in ("multi_agg_compact_numbers.csv", "multi_agg_numbers.csv"):
    if os.path.exists(f"{SRC}/{f}"):
        shutil.copy(f"{SRC}/{f}", f"{RAW}/{f}")
for suite, path in (("dcperf", f"{REPO}/local_agents/DCPerf/data/l3_study/dcperf_rows_long.csv"),
                    ("renaissance", f"{JV}/data/l3_study/renaissance_rows_long.csv"),
                    ("dacapo", f"{JV}/data/l3_study/dacapo_rows_long.csv")):
    if os.path.exists(path):
        with gzip.open(f"{RAW}/{suite}_per_window_rows.csv.gz", "wt") as fh:
            pd.read_csv(path).to_csv(fh, index=False)

lines = [f"# Multi-suite chart pack — {os.path.basename(CH)}", "",
         "SPEC CPU 2026 · agentic 36 (SWE-bench Multilingual) · DCPerf · Renaissance · DaCapo Chopin.",
         "Same layout as every other pack: one raw-data file, one script, one PDF (paper) + PNG",
         "(slides) per figure. Unit rule for fig01: violins are distributions over WORKLOADS (SPEC 26,",
         "agentic 36, one vote each); each external benchmark is ONE marker at its vote (median of its",
         "windows), grouped under its suite, with a bar for its own window IQR. fig02–fig05 are the",
         "per-window companions (one column per benchmark). Method and findings: `../../README.md`.", "",
         "| Fig | Name | What it shows |", "|---|---|---|"]
lines += [f"| {fid} | {name} | {desc} |" for fid, name, _s, desc in FIGS]
lines += ["", "`Raw data/*_per_window_rows.csv.gz` hold every external per-window value; the two",
          "`*_numbers.csv` files hold every displayed vote and column median."]
open(f"{CH}/README.md", "w").write("\n".join(lines) + "\n")
print("chart pack assembled at", CH)
