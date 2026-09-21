#!/usr/bin/env python3
"""build_realdata_chart_pack.py — assemble one VERSIONED chart pack for the realistic-dataset
study (local_agents/RealData), mentor layout with a README in every subdirectory:

    local_agents/RealData/charts/$VERSION/{README.md, Figures/{PDF,PNG,README.md},
                                           Raw data/README.md, Scripts/README.md}

    VERSION=v1_2026-09-21_realistic-datasets python3 local_agents/kit/plot/build_realdata_chart_pack.py

Figures are not regenerated here; run the R scripts first (see Scripts/README.md).
"""
import gzip
import os
import shutil

REPO = os.path.expanduser("~/InferSuite")
RD = f"{REPO}/local_agents/RealData"
KP = f"{REPO}/local_agents/kit/plot"
VERSION = os.environ.get("VERSION", "v1_2026-09-21_realistic-datasets")
CH = f"{RD}/charts/{VERSION}"
RAW, SCR, FPDF, FPNG = f"{CH}/Raw data", f"{CH}/Scripts", f"{CH}/Figures/PDF", f"{CH}/Figures/PNG"
for d in (RAW, SCR, FPDF, FPNG):
    os.makedirs(d, exist_ok=True)

FIGS = [
    ("fig01", "realdata_pairs", "plot_paper_realdata_pairs.R", f"{RD}/plots/paper_v1/realdata_pairs",
     "12 metrics; per metric each re-characterised workload as a pair: suite benchmark (open circle) -> same software on a realistic dataset (green), with the SPEC and agentic medians as reference lines"),
    ("fig02", "agg_compact_server_realistic", "plot_paper_agg_compact_server.R",
     f"{REPO}/local_agents/JVMbench/plots/paper_v1/multi_server_compact_realistic",
     "the three-violin grid (SPEC 26 · Server 10 · Agentic 36) with the re-characterised suite benchmarks replaced by their realistic versions; one whole-runtime value per workload"),
    ("fig03", "agg_compact_server_suite", "plot_paper_agg_compact_server.R",
     f"{REPO}/local_agents/JVMbench/plots/paper_v1/multi_server_compact",
     "the same grid with the ten suite benchmarks as shipped, for comparison"),
]
present = []
for fid, name, script, stem, desc in FIGS:
    if not os.path.exists(f"{stem}.png"):
        print(f"  SKIP {fid}: {stem}.png missing"); continue
    shutil.copy(f"{stem}.pdf", f"{FPDF}/{fid}_{name}.pdf")
    shutil.copy(f"{stem}.png", f"{FPNG}/{fid}_{name}.png")
    body = open(f"{KP}/{script}").read()
    hdr = (f"#!/usr/bin/env Rscript\n# {fid}_{name} — COPY of the canonical generator local_agents/kit/plot/{script}\n"
           "# (single source of truth; edit THERE). Runs from the repo root against the banked data trees.\n")
    body = body.split("\n", 1)[1] if body.startswith("#!") else body
    open(f"{SCR}/{fid}_{name}.R", "w").write(hdr + body)
    present.append((fid, name, script, stem, desc))

# raw data: every value drawn + the per-window rows of the realistic workloads, in time order too
for f in (f"{RD}/plots/paper_v1/realdata_pairs_numbers.csv",
          f"{REPO}/local_agents/JVMbench/plots/paper_v1/multi_server_compact_realistic_numbers.csv",
          f"{REPO}/local_agents/JVMbench/plots/paper_v1/multi_server_compact_numbers.csv",
          f"{REPO}/local_agents/JVMbench/data/l3_study/runtime_votes.csv"):
    if os.path.exists(f):
        shutil.copy(f, f"{RAW}/{os.path.basename(f)}")
rows = f"{RD}/data/l3_study/realdata_rows_long.csv"
if os.path.exists(rows):
    with open(rows, "rb") as src, gzip.open(f"{RAW}/realdata_per_window_rows.csv.gz", "wb") as dst:
        shutil.copyfileobj(src, dst)
ts = f"{REPO}/local_agents/JVMbench/data/l3_study/timeseries/timeseries_realdata.csv.gz"
if os.path.exists(ts):
    shutil.copy(ts, f"{RAW}/timeseries_realdata.csv.gz")
for f in ("export_runtime_votes.py", "export_timeseries_rows.py"):
    shutil.copy(f"{KP}/{f}", f"{SCR}/{f}")

open(f"{CH}/README.md", "w").write("\n".join([
    f"# Realistic-dataset chart pack — {VERSION}", "",
    "Five server benchmarks profiled twice with the same instrument: as their suite ships them",
    "(DaCapo cassandra and kafka; Renaissance neo4j-analytics, page-rank, naive-bayes) and as the",
    "same software on a dataset of realistic size and shape (Cassandra 5 + YCSB on 20 M rows, a",
    "Kafka 4 broker with a 21 GB retention window, a Neo4j 5 server on the 69 M-edge LiveJournal",
    "graph, Spark PageRank on that graph, Spark Naive Bayes on the 518 k-document RCV1-v2 corpus),",
    "plus DCPerf's video transcoder on 4K sources where profiled. Method, receipts, validation and",
    "the write-up: `../../README.md`. Each subdirectory has its own README.", "",
    "| Fig | File stem | What it shows |", "|---|---|---|"]
    + [f"| {fid} | `{fid}_{name}` | {desc} |" for fid, name, _s, _st, desc in present]
    + ["", "**Rule for every value:** one number per workload = the metric over the workload's whole runtime",
       "(raw counters summed over every window, ratio taken once; mentor's rule 2026-09-15). Server in the",
       "fence, load generator outside on the housekeeping cores; nine dedicated-group passes per workload,",
       "run-to-run repetition n = 1.", ""]))
open(f"{CH}/Figures/README.md", "w").write("\n".join([
    "# Figures — how to read them", "",
    "PDF for the paper, PNG (300 dpi) for slides. fig01: in every panel the open circle is the suite",
    "benchmark's value and the green circle the same software on the realistic dataset; the segment",
    "joins the pair and points at the realistic value. Dashed vertical lines: SPEC median (blue, 26",
    "benchmarks) and agentic median (red, 36 tasks). A pair that crosses a line has changed which side",
    "of that reference it sits on. fig02/fig03: violins over per-workload values (white box = IQR,",
    "black bar = median, white diamond = mean); fig02 uses the realistic versions in the Server set,",
    "fig03 the suite versions, so the two Server violins differ by exactly the five (six with video)",
    "re-characterised workloads.", ""]))
open(f"{RAW}/README.md", "w").write("\n".join([
    "# Raw data — what every file is", "",
    "| File | What a row is |", "|---|---|",
    "| `realdata_pairs_numbers.csv` | fig01: one row per (workload, metric): `toy` and `real` whole-runtime values, `spec` and `agentic` medians, `ratio` = real / toy |",
    "| `multi_server_compact_realistic_numbers.csv` | fig02: per (metric, side) n / min / max / median / mean / sd of the per-workload values; one row per Server benchmark (`side` = `Server:<suite>` or `Server:RealData`) with its value (`median`) and, for suite benchmarks, its window IQR |",
    "| `multi_server_compact_numbers.csv` | fig03: the same for the suite Server set |",
    "| `runtime_votes.csv` | every whole-runtime value of every workload in every family (`family` = spec26 / agentic36 / dcperf / renaissance / dacapo / realdata; `windows` and `runs` behind each) — the input of every figure |",
    "| `realdata_per_window_rows.csv.gz` | the realistic workloads' per-window values (`fence, metric, grp, col, value`; fence `both` = the whole server) |",
    "| `timeseries_realdata.csv.gz` | the same in time order (`run, group, win, t_rel_s, dur_s, metric, value`) for other aggregations |", "",
    "Values are co-counted inside each window; a metric exists only in windows whose counter group",
    "carried it (IPC/branch MPKI: fpbr; branch-direction/BTB/uop-cache: fe_miss; L1I: fe_lat; DSB: fe;",
    "L1D/L2/LLC: cache; DRAM: dram_bw; context switches: priv). Captures: measured cores 4–11, SMT",
    "siblings offline, 3.2 GHz pinned, 100 ms windows, zero multiplexing (`../../README.md` §1).", ""]))
open(f"{SCR}/README.md", "w").write("\n".join([
    "# Scripts — what each one does", "",
    "Verbatim copies of the canonical generators in `local_agents/kit/plot/` (edit there). Run from the",
    "repository root with the `rplot` conda environment's Rscript:", "",
    "```bash", "cd ~/InferSuite", "RS=~/miniforge3/envs/rplot/bin/Rscript",
    "PY=~/miniforge3/envs/infersuite-full/bin/python3",
    "$PY local_agents/kit/plot/export_runtime_votes.py                       # runtime_votes.csv, all families",
    "$RS local_agents/kit/plot/plot_paper_realdata_pairs.R                   # fig01",
    "SERVER_SET=realistic $RS local_agents/kit/plot/plot_paper_agg_compact_server.R   # fig02",
    "$RS local_agents/kit/plot/plot_paper_agg_compact_server.R               # fig03",
    f"VERSION={VERSION} python3 local_agents/kit/plot/build_realdata_chart_pack.py", "```", "",
    "| Script | Draws | Knobs |", "|---|---|---|",
    "| `fig01_realdata_pairs.R` | the toy → realistic pair grid | `RUNTIME_VOTES` (values file), `EXT_OUT` (output dir, repo-relative); pairs are listed at the top of the script |",
    "| `fig02/fig03_agg_compact_server_*.R` | the three-violin grid | `SERVER_SET=realistic` or `suite`; `VOTE=runtime` or `median`; `SERVER_MODE=votes` or `windows`; `EXT_ROWS`, `RUNTIME_VOTES`, `ADJ`, `EXT_OUT`, `EXT_STEM` |",
    "| `export_runtime_votes.py` | — | writes one whole-runtime value per workload and metric through the SPEC comparison kit's loader |",
    "| `export_timeseries_rows.py` | — | writes the per-window rows of every family in time order |", ""]))
print("pack builder written; assembled at", CH, "with", len(present), "figures")
