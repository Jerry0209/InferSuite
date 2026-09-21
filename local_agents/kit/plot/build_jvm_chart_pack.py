#!/usr/bin/env python3
"""build_jvm_chart_pack.py — assemble one VERSIONED chart pack for the multi-suite figures
(SPEC · agentic 36 · the JVM server suites · DCPerf), mentor layout, with a README in EVERY
subdirectory so a reader (or their agent) can tell what each file is without asking:

    local_agents/JVMbench/charts/$VERSION/
        README.md              what the pack is, figure index, unit rule, what changed
        Figures/{PDF,PNG}/     one PDF (paper) + one PNG (slides) per figure
        Figures/README.md      how to read each figure
        Raw data/              every input the scripts read + every displayed number
        Raw data/README.md     file-by-file: schema, what a row is, how to interpret
        Scripts/               a copy of each generator (canonical source: kit/plot/)
        Scripts/README.md      script-by-script: what it draws, inputs, env knobs, how to run

    VERSION=v3_2026-09-15_runtime-votes python3 local_agents/kit/plot/build_jvm_chart_pack.py

Figures are NOT regenerated here (the R scripts write plots/paper_v1/; this copies them), so
run the generators first. Never rebuild a version that has been circulated -- make a new one.
"""
import gzip
import os
import shutil

import pandas as pd

REPO = os.path.expanduser("~/InferSuite")
JV = f"{REPO}/local_agents/JVMbench"
KP = f"{REPO}/local_agents/kit/plot"
SRC = f"{JV}/plots/paper_v1"
VERSION = os.environ.get("VERSION", "v4_2026-09-21_realistic-server-set")
CH = f"{JV}/charts/{VERSION}"
RAW, SCR = f"{CH}/Raw data", f"{CH}/Scripts"
FPDF, FPNG = f"{CH}/Figures/PDF", f"{CH}/Figures/PNG"
for d in (RAW, SCR, FPDF, FPNG):
    os.makedirs(d, exist_ok=True)

# (fig id, pack name, generator script, source stem in plots/paper_v1, one-line description)
FIGS = [
    ("fig01", "agg_compact_server", "plot_paper_agg_compact_server.R", "multi_server_compact",
     "12-metric grid, THREE violins per panel: SPEC (26), Server (10: DCPerf 2 + Renaissance 5 + DaCapo 3), Agentic (36); one whole-runtime value per workload"),
    ("fig02", "agg_ipc_server", "plot_paper_agg_groups_server.R", "multi_server_ipc",
     "IPC: SPEC-int, SPEC-fp, Server columns (one whole-runtime value per benchmark) then one column per agentic task (its 100 ms windows)"),
    ("fig03", "agg_frontend_server", "plot_paper_agg_groups_server.R", "multi_server_frontend",
     "frontend metrics, same columns as fig02"),
    ("fig04", "agg_memory_server", "plot_paper_agg_groups_server.R", "multi_server_memory",
     "memory metrics, same columns as fig02"),
    ("fig05", "agg_system_server", "plot_paper_agg_groups_server.R", "multi_server_system",
     "context switches per CPU-second (log axis), same columns as fig02"),
    ("fig01b", "agg_compact_server_realistic", "plot_paper_agg_compact_server.R", "multi_server_compact_realistic",
     "fig01 with the suite benchmarks that were re-characterised on realistic datasets (cassandra, kafka, neo4j, page-rank, naive-bayes, video) replaced by those versions; see local_agents/RealData/README.md"),
    ("fig06", "agg_compact_per_benchmark", "plot_paper_agg_compact_ext.R", "multi_agg_compact",
     "the same grid with SPEC and Agentic violins and ONE MARKER per external benchmark (DCPerf 2, Renaissance 5, DaCapo 3) so you can see which benchmark sits where"),
    ("fig07", "agg_ipc_per_benchmark", "plot_paper_agg_groups_ext.R", "multi_agg_ipc",
     "IPC with one per-window column per external benchmark, grouped by suite, after the agentic tasks"),
    ("fig08", "agg_frontend_per_benchmark", "plot_paper_agg_groups_ext.R", "multi_agg_frontend",
     "frontend metrics, per-benchmark columns"),
    ("fig09", "agg_memory_per_benchmark", "plot_paper_agg_groups_ext.R", "multi_agg_memory",
     "memory metrics, per-benchmark columns"),
    ("fig10", "agg_system_per_benchmark", "plot_paper_agg_groups_ext.R", "multi_agg_system",
     "context switches per CPU-second, per-benchmark columns"),
]
present = []
for fid, name, script, stem, desc in FIGS:
    if not os.path.exists(f"{SRC}/{stem}.png"):
        print(f"  SKIP {fid}: {SRC}/{stem}.png missing"); continue
    shutil.copy(f"{SRC}/{stem}.pdf", f"{FPDF}/{fid}_{name}.pdf")
    shutil.copy(f"{SRC}/{stem}.png", f"{FPNG}/{fid}_{name}.png")
    body = open(f"{KP}/{script}").read()
    hdr = ("#!/usr/bin/env Rscript\n"
           f"# {fid}_{name} — COPY of the canonical generator local_agents/kit/plot/{script}\n"
           "# (single source of truth; edit THERE). Runs from the repo root against the banked\n"
           "# data trees and writes into local_agents/JVMbench/plots/paper_v1/.\n")
    body = body.split("\n", 1)[1] if body.startswith("#!") else body
    open(f"{SCR}/{fid}_{name}.R", "w").write(hdr + body)
    present.append((fid, name, script, stem, desc))

# ---- Raw data: every input the scripts read, plus every displayed number -------------------
for f in ("multi_server_compact_numbers.csv", "multi_server_compact_realistic_numbers.csv", "multi_server_numbers.csv",
          "multi_agg_compact_numbers.csv", "multi_agg_numbers.csv"):
    if os.path.exists(f"{SRC}/{f}"):
        shutil.copy(f"{SRC}/{f}", f"{RAW}/{f}")
RV = f"{JV}/data/l3_study/runtime_votes.csv"
if os.path.exists(RV):
    shutil.copy(RV, f"{RAW}/runtime_votes.csv")
for f in ("workload_index.csv", "server_set_shift.csv"):
    src = f"{REPO}/local_agents/RealData/data/l3_study/{f}"
    if os.path.exists(src):
        shutil.copy(src, f"{RAW}/{f}")
with open(f"{REPO}/local_agents/ML_iso36/data/l3_study/agg_rows_long.csv", "rb") as src, \
        gzip.open(f"{RAW}/spec_agentic_rows_long.csv.gz", "wb") as dst:
    shutil.copyfileobj(src, dst)
for suite, path in (("dcperf", f"{REPO}/local_agents/DCPerf/data/l3_study/dcperf_rows_long.csv"),
                    ("renaissance", f"{JV}/data/l3_study/renaissance_rows_long.csv"),
                    ("dacapo", f"{JV}/data/l3_study/dacapo_rows_long.csv")):
    if os.path.exists(path):
        with gzip.open(f"{RAW}/{suite}_per_window_rows.csv.gz", "wt") as fh:
            pd.read_csv(path).to_csv(fh, index=False)
TS = f"{JV}/data/l3_study/timeseries"
ts_files = []
if os.path.isdir(TS):
    for f in sorted(os.listdir(TS)):
        if f.startswith("timeseries_") and f.endswith(".csv.gz"):
            shutil.copy(f"{TS}/{f}", f"{RAW}/{f}"); ts_files.append(f)
shutil.copy(f"{KP}/export_timeseries_rows.py", f"{SCR}/export_timeseries_rows.py")
shutil.copy(f"{KP}/export_runtime_votes.py", f"{SCR}/export_runtime_votes.py")
shutil.copy(f"{KP}/export_server_set_shift.py", f"{SCR}/export_server_set_shift.py")
shutil.copy(f"{KP}/export_dcperf_rows.py", f"{SCR}/export_suite_rows.py")
shutil.copy(f"{KP}/export_agg_rows_long.py", f"{SCR}/export_spec_agentic_rows.py")

# ---- READMEs -------------------------------------------------------------------------------
UNIT = """**The rule every figure here follows (mentor, 2026-09-15).** One number per workload, computed
over the workload's **whole runtime**: the raw counters are summed over every window the
workload was measured in and the ratio is taken once — IPC = total instructions / total
cycles, branch MPKI = 1000 × total mispredictions / total instructions, DRAM GB/s = total bytes
/ total seconds, context switches = total switches / total task-clock. Neither the median of
per-window values (which weights every 100 ms equally, busy or idle) nor a pool of windows
(which weights each workload by how long it ran). A violin in the compact grid is then a
distribution over those per-workload values — SPEC 26, Server 10, Agentic 36. In the per-window
figures the three reference columns (SPEC-int, SPEC-fp, Server) hold those same per-benchmark
values, while each agentic column is that task's own 100 ms windows. All four families go
through one implementation (`Scripts/export_runtime_votes.py`, built on the SPEC comparison
kit's loader); denominators are co-counted, i.e. summed over exactly the windows in which the
numerator's counter was live. `Raw data/runtime_votes.csv` holds every value drawn;
`Raw data/timeseries_*.csv.gz` the per-window rows in time order."""

top = [f"# Multi-suite chart pack — {VERSION}", "",
       "SPEC CPU 2026 (26 benchmarks) · **Server** = DCPerf FeedSim and VideoTranscodeBench,",
       "Renaissance finagle-http, finagle-chirper, page-rank, naive-bayes, neo4j-analytics, DaCapo",
       "Chopin cassandra, tomcat, kafka (10; the mentor's set, DCPerf confirmed in it 2026-09-15) ·",
       "Agentic 36 (SWE-bench Multilingual). fig06–fig10 are the per-benchmark companions that show",
       "which server benchmark sits where.", "",
       "One PDF (paper) + one PNG (slides) per figure. Each subdirectory has its own README:",
       "[`Figures/`](Figures/README.md) how to read them · [`Raw data/`](Raw%20data/README.md) what",
       "every file holds · [`Scripts/`](Scripts/README.md) what every script does and how to run it.",
       "Method, isolation, run counts and findings: `../../README.md`.", "",
       "| Fig | File stem | What it shows |", "|---|---|---|"]
top += [f"| {fid} | `{fid}_{name}` | {desc} |" for fid, name, _s, _st, desc in present]
top += ["", UNIT, "",
        "**Runs behind a vote.** One profiling run per counter group per workload: SPEC 1 execution",
        "per benchmark (11 groups rotating inside it), the agentic 36, DCPerf, Renaissance and DaCapo",
        "9 runs each (one dedicated group per run). A metric's vote is the median over the windows of",
        "the single run that carried its counters; run-to-run repetition is n = 1 in every family.",
        "Details: `../../README.md` §7 and `../../../DCPerf/README.md` §7.8.", ""]
open(f"{CH}/README.md", "w").write("\n".join(top))

figs_md = ["# Figures — how to read them", "",
           "PDF for the paper, PNG (300 dpi) for slides; identical content. Colours: SPEC blue,",
           "Server green, Agentic red; in the per-benchmark companions DCPerf is green, Renaissance",
           "gold, DaCapo purple, and each agentic language keeps its own colour.", "",
           "**Inside every violin:** white box = 25th–75th percentile of the points the violin is",
           "drawn over, black bar = their median, white diamond = their mean. The `med` label under",
           "each violin in the compact grid is that median.", "",
           "**Broken axes** (`∕∕` marks): a panel whose largest value is more than 3× its 95th",
           "percentile is cut; the upper strip shows the outliers as grey dots, the lower part keeps a",
           "readable scale. Nothing is dropped. **Red triangles** at the top of a per-window column:",
           "that column's maximum lies above the cap; the statistics inside the violin still use the",
           "full data.", "",
           "| Fig | What one point is | What the shape means |", "|---|---|---|",
           "| fig01 | one workload's vote (median over its windows) | how the metric varies ACROSS workloads within a family |",
           "| fig02–05, SPEC-int / SPEC-fp / Server columns | one benchmark's vote | across-benchmark spread of the reference group |",
           "| fig02–05, agentic columns | one 100 ms window of that task | how the metric varies OVER TIME within one task |",
           "| fig06 | SPEC/Agentic: a vote; external suites: one diamond per benchmark at its vote, bar = its window IQR | per-benchmark placement |",
           "| fig07–10 external columns | one 100 ms window of that benchmark | within-benchmark time variation |", "",
           "The Server violin in fig01 is drawn over 8 votes; that is few for a kernel density, so",
           "read its width as a rough envelope and take the exact eight values from",
           "`../Raw data/multi_server_compact_numbers.csv` (rows `Server:Renaissance`, `Server:DaCapo`).", ""]
open(f"{CH}/Figures/README.md", "w").write("\n".join(figs_md))

raw_md = ["# Raw data — what every file is", "",
          "All CSVs are UTF-8, comma-separated, header row first; `.gz` files are gzip and read",
          "directly by pandas (`pd.read_csv(path)`) or R (`read.csv(gzfile(path))`).", "",
          "## The values the violins are drawn over", "",
          "| File | Schema | What a row is |", "|---|---|---|",
          "| `runtime_votes.csv` | `family, subgroup, workload, metric, value, windows, runs` | **one row per workload and metric: the metric over the workload's whole runtime** (counters summed over all its windows, ratio taken once). `family` = spec26 / agentic36 / dcperf / renaissance / dacapo; `subgroup` = SPEC-int or SPEC-fp, the task's language, or the suite; `windows` = how many 100 ms windows carried that metric's counters; `runs` = profiling runs summed (SPEC 1, all others 9). This is the input of every violin and marker in fig01 and fig06 and of the SPEC / Server columns in the per-window figures. |", "",
          "## The per-window inputs (agentic columns, marker IQR bars, and the older median rule)", "",
          "| File | Rows | Schema | What a row is |", "|---|---|---|---|",
          "| `spec_agentic_rows_long.csv.gz` | SPEC + agentic | `fence, metric, grp, col, value` | SPEC (`grp` = `SPEC-int`/`SPEC-fp`): **one row per benchmark**, `value` = that benchmark's median over its windows (26 rows per metric per fence). Agentic (`grp` = language, `col` = task): **one row per 100 ms window**. Three `fence` values: `tool` (sandbox container), `harness` (agent process), `both` (their sum at the raw-count level) — every figure uses `both`. 16 metrics; the figures show 12. |",
          "| `renaissance_per_window_rows.csv.gz` | 5 benchmarks | same schema | one row per 100 ms window, `grp` = `Renaissance`, `col` = benchmark, `fence` = `both` (the whole JVM) |",
          "| `dacapo_per_window_rows.csv.gz` | 3 benchmarks | same schema | as above, `grp` = `DaCapo` (cassandra, tomcat, kafka) |",
          "| `dcperf_per_window_rows.csv.gz` | 2 benchmarks | same schema | as above, `grp` = `DCPerf` (feedsim, video_transcode); used by fig06–fig10 only |", "",
          "`value` is always co-counted inside its window: MPKI = misses / instructions of that same",
          "window × 1000; DSB coverage = DSB uops / all uops; DRAM read GB/s = offcore data reads × 64 B /",
          "window time; context switches / CPU-s = switches / the fence's task-clock seconds. A metric",
          "appears only in windows whose counter group carried it (IPC and Branch MPKI: `fpbr`;",
          "branch-direction / BTB / uop-cache: `fe_miss`; L1I: `fe_lat`; DSB: `fe`; L1D/L2/LLC: `cache`;",
          "DRAM: `dram_bw`; context switches: `priv`), so per-metric row counts differ.", "",
          "## The same measurements in time order (for other aggregations)", "",
          "`timeseries_<family>.csv.gz`, one per family, schema",
          "`family, workload, run, group, win, t_rel_s, dur_s, tag, metric, value`:", "",
          "- `run` — which profiling run the window came from (`run_1`…`run_9`; SPEC has one run);",
          "- `group` — the counter group live in that window (decides which metrics it carries);",
          "- `win` — window index inside the run, capture order; `t_rel_s` — seconds since that run's",
          "  first window; `dur_s` — the window's own counting time (≈ 0.1 s);",
          "- `tag` — agentic only: what the tool fence was executing at that moment (2 Hz command",
          "  tagger: `idle`, `harness`, a compiler, a test runner, …); blank for the other families;",
          "- `metric`, `value` — as above, fence `both` only.", "",
          "| File | Workloads | Rows |", "|---|---|---|"]
for f in ts_files:
    try:
        n = sum(1 for _ in gzip.open(f"{RAW}/{f}", "rt")) - 1
    except OSError:
        n = "?"
    raw_md.append(f"| `{f}` | {f[len('timeseries_'):-len('.csv.gz')]} | {n} |")
raw_md += ["",
           "These are what to use to try a different aggregation. Three that have been discussed:",
           "(1) **one vote per workload** (what the figures do) keeps across-workload variation and",
           "drops within-workload variation; (2) **pooling every window** keeps within-workload",
           "variation but weights each workload by its window count — SPEC spans 70 to 2 658 windows",
           "per benchmark, the agentic tasks 115 to 2 269, so the pooled shape is mostly the longest",
           "runs; (3) **equal-weight pooling** — weight each window by 1 / (windows of its workload), or",
           "resample the same number of windows from every workload — keeps within-workload shape",
           "without the runtime bias. The Server suites' captures are fixed-length (~1 500 windows per",
           "metric each), so for them (2) and (3) coincide; `SERVER_MODE=windows` in the scripts draws",
           "that variant.", "",
           "## Every number that is drawn", "",
           "| File | What |", "|---|---|",
           "| `multi_server_compact_numbers.csv` | fig01: per (metric, side) the n / min / max / median / mean / sd of the per-workload values; plus one row per Server benchmark (`side` = `Server:DCPerf`, `Server:Renaissance` or `Server:DaCapo`, `workload` = benchmark) giving its whole-runtime value (`median`) and its window IQR (`min` = p25, `max` = p75) |",
           "| `multi_server_numbers.csv` | fig02–05: per (metric, column) the median, mean and n of the points in that column |",
           "| `multi_agg_compact_numbers.csv` | fig06: as for fig01, with one row per external benchmark marker (`side` = suite) |",
           "| `multi_agg_numbers.csv` | fig07–10: per (metric, column) median, mean, n |", "",
           "## Provenance", "",
           "Per-window values come from `analyze_l3_windows.py` (agentic, DCPerf, JVM: the same",
           "derivation code) and from the SPEC kit's `spec_common.py`. Captures: measured cores 4–11,",
           "SMT siblings offline, 3.2 GHz pinned, one counter group per 100 ms window with zero",
           "multiplexing — `../../README.md` §6 has the full isolation table. Run counts per workload:",
           "`../../README.md` §7.", ""]
open(f"{RAW}/README.md", "w").write("\n".join(raw_md))

scr_md = ["# Scripts — what each one does", "",
          "Every `fig*.R` here is a verbatim copy of its canonical generator in",
          "`local_agents/kit/plot/` (edit there, not here). All run from the repository root with the",
          "`rplot` conda environment's Rscript and read the banked data trees, not this folder:", "",
          "```bash",
          "cd ~/InferSuite",
          "RS=~/miniforge3/envs/rplot/bin/Rscript",
          "$PY=~/miniforge3/envs/infersuite-full/bin/python3",
          "$PY local_agents/kit/plot/export_runtime_votes.py             # runtime_votes.csv (all families)",
          f"$RS local_agents/kit/plot/plot_paper_agg_compact_server.R     # fig01",
          f"$RS local_agents/kit/plot/plot_paper_agg_groups_server.R      # fig02-05 (all four)",
          f"$RS local_agents/kit/plot/plot_paper_agg_compact_ext.R        # fig06",
          f"$RS local_agents/kit/plot/plot_paper_agg_groups_ext.R         # fig07-10 (all four)",
          "# outputs land in local_agents/JVMbench/plots/paper_v1/; then",
          f"VERSION={VERSION} python3 local_agents/kit/plot/build_jvm_chart_pack.py",
          "```", "",
          "| Script | Draws | Reads | Knobs (environment variables) |", "|---|---|---|---|",
          "| `fig01_agg_compact_server.R` | the 12-panel grid with three violins (SPEC, Server, Agentic) | `runtime_votes.csv` (the values) + the Server suites' per-window rows (window IQRs for the numbers file) | `VOTE=runtime` (default: whole-runtime value per workload) or `median` (median of its windows, the pre-2026-09-15 rule); `SERVER_MODE=votes` (default) or `windows` (pool the server benchmarks' windows); `EXT_ROWS` = colon-separated rows files that form the Server set; `RUNTIME_VOTES` = path of the votes file; `ADJ` = violin bandwidth multiplier; `EXT_OUT`, `EXT_STEM` output dir/stem (repo-relative) |",
          "| `fig02–05_agg_*_server.R` | the four per-window group figures with a single Server column | `runtime_votes.csv` for the SPEC and Server columns, `spec_agentic_rows_long` for the agentic columns | `VOTE`, `SERVER_MODE`, `EXT_ROWS`, `RUNTIME_VOTES`, `EXT_OUT` as above |",
          "| `fig06_agg_compact_per_benchmark.R` | the grid with one diamond per external benchmark | `runtime_votes.csv` + the per-window rows (marker IQR bars) | `VOTE`, `EXT_ROWS`, `RUNTIME_VOTES`, `ADJ`, `EXT_OUT`, `EXT_STEM` |",
          "| `fig07–10_agg_*_per_benchmark.R` | per-window figures with one column per external benchmark, one block per suite | `runtime_votes.csv` for the SPEC columns, per-window rows for every other column | `VOTE`, `EXT_ROWS`, `EXT_OUT`; `VARIANT=broken_axis` cuts the frontend/memory y axes |",
          "| `export_runtime_votes.py` | — | every family's raw window files, through the SPEC comparison kit's `extract_metrics.py` (one implementation for all four) | `--out DIR`; writes `runtime_votes.csv`: one whole-runtime value per workload and metric |",
          "| `export_spec_agentic_rows.py` | — | the SPEC kit's per-window metrics and the agentic `all_windows_*.csv` | writes `agg_rows_long.csv` (= `Raw data/spec_agentic_rows_long.csv.gz`) |",
          "| `export_suite_rows.py` | — | an external suite's `all_windows_*.csv` | `--suite --label --data --out`; writes `<suite>_rows_long.csv` (= `Raw data/<suite>_per_window_rows.csv.gz`); skips a workload with an `EXCLUDED` marker |",
          "| `export_timeseries_rows.py` | — | the same per-window files, keeping time order | `--out DIR`; writes `Raw data/timeseries_<family>.csv.gz` |", "",
          "The scripts write `*_numbers.csv` next to the figures with every displayed number; the",
          "pack copies them into `Raw data/`. The shared look (fonts, violin outline, the inner",
          "box/median/mean glyph, broken-axis rule) lives in `local_agents/kit/plot/theme_paper.R`.", ""]
open(f"{SCR}/README.md", "w").write("\n".join(scr_md))
print("chart pack assembled at", CH, "with", len(present), "figures and", len(ts_files), "time-series files")
