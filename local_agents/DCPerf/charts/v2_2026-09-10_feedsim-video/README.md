# DCPerf chart pack — v2_2026-09-10_feedsim-video

Same layout as the ML_iso36 packs: one raw-data file, one script and one PDF+PNG per
figure. **PDF → paper, PNG → slides.** Figures compare three workload families:
SPEC CPU 2026 (26 benchmarks), the agentic 36 (SWE-bench Multilingual) and DCPerf.

**Read fig01 with its unit rule in mind:** a violin is a distribution over WORKLOADS
(SPEC contributes 26, the agentic family 36). DCPerf contributes one profiled
benchmark, so it is drawn as a marker at its vote — the median of its steady-state
windows, the same statistic every other vote uses — with a bar for its own window
IQR, which is a within-workload spread and a different quantity. fig02–fig05 are the
unit-consistent companions: every column there is a distribution over 100 ms windows.

Method, operating point and findings: `../../README.md`.

| Fig | Name | What it shows | Raw data |
|---|---|---|---|
| fig01 | agg_compact3 | 12-metric SPEC vs Agentic vs DCPerf grid; violins are distributions over WORKLOADS, DCPerf is one workload so it is a marker at its vote | `Raw data/fig01_agg_compact3.csv` |
| fig02 | agg_ipc_3way | IPC per 100 ms window: SPEC band, 36 agentic tasks by language, DCPerf column | `Raw data/fig02-05_agg_3way_column_medians.csv` |
| fig03 | agg_frontend_3way | frontend metrics per window (Branch/Branch-dir/BTB/L1I/DSB MPKI, DSB coverage) | `Raw data/fig02-05_agg_3way_column_medians.csv` |
| fig04 | agg_memory_3way | memory metrics per window (L1D/L2/LLC MPKI, DRAM read GB/s) | `Raw data/fig02-05_agg_3way_column_medians.csv` |
| fig05 | agg_system_3way | context switches per CPU-second, log axis | `Raw data/fig02-05_agg_3way_column_medians.csv` |

`Raw data/dcperf_per_window_rows.csv.gz` holds every DCPerf per-window value behind
these figures; `feedsim_operating_point_calibration.csv` is the QPS sweep that chose
the 16 QPS operating point (highest point meeting DCPerf's own p95 ≤ 500 ms).
Regenerate: run the scripts with the `rplot` env Rscript from the repo root, then
rerun `local_agents/kit/plot/build_dcperf_chart_pack.py` with VERSION set.
