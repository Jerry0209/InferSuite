# Multi-suite chart pack — v3_2026-09-15_runtime-votes

SPEC CPU 2026 (26 benchmarks) · **Server** = DCPerf FeedSim and VideoTranscodeBench,
Renaissance finagle-http, finagle-chirper, page-rank, naive-bayes, neo4j-analytics, DaCapo
Chopin cassandra, tomcat, kafka (10; the mentor's set, DCPerf confirmed in it 2026-09-15) ·
Agentic 36 (SWE-bench Multilingual). fig06–fig10 are the per-benchmark companions that show
which server benchmark sits where.

One PDF (paper) + one PNG (slides) per figure. Each subdirectory has its own README:
[`Figures/`](Figures/README.md) how to read them · [`Raw data/`](Raw%20data/README.md) what
every file holds · [`Scripts/`](Scripts/README.md) what every script does and how to run it.
Method, isolation, run counts and findings: `../../README.md`.

| Fig | File stem | What it shows |
|---|---|---|
| fig01 | `fig01_agg_compact_server` | 12-metric grid, THREE violins per panel: SPEC (26), Server (10: DCPerf 2 + Renaissance 5 + DaCapo 3), Agentic (36); one whole-runtime value per workload |
| fig02 | `fig02_agg_ipc_server` | IPC: SPEC-int, SPEC-fp, Server columns (one whole-runtime value per benchmark) then one column per agentic task (its 100 ms windows) |
| fig03 | `fig03_agg_frontend_server` | frontend metrics, same columns as fig02 |
| fig04 | `fig04_agg_memory_server` | memory metrics, same columns as fig02 |
| fig05 | `fig05_agg_system_server` | context switches per CPU-second (log axis), same columns as fig02 |
| fig06 | `fig06_agg_compact_per_benchmark` | the same grid with SPEC and Agentic violins and ONE MARKER per external benchmark (DCPerf 2, Renaissance 5, DaCapo 3) so you can see which benchmark sits where |
| fig07 | `fig07_agg_ipc_per_benchmark` | IPC with one per-window column per external benchmark, grouped by suite, after the agentic tasks |
| fig08 | `fig08_agg_frontend_per_benchmark` | frontend metrics, per-benchmark columns |
| fig09 | `fig09_agg_memory_per_benchmark` | memory metrics, per-benchmark columns |
| fig10 | `fig10_agg_system_per_benchmark` | context switches per CPU-second, per-benchmark columns |

**The rule every figure here follows (mentor, 2026-09-15).** One number per workload, computed
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
`Raw data/timeseries_*.csv.gz` the per-window rows in time order.

**Runs behind a vote.** One profiling run per counter group per workload: SPEC 1 execution
per benchmark (11 groups rotating inside it), the agentic 36, DCPerf, Renaissance and DaCapo
9 runs each (one dedicated group per run). A metric's vote is the median over the windows of
the single run that carried its counters; run-to-run repetition is n = 1 in every family.
Details: `../../README.md` §7 and `../../../DCPerf/README.md` §7.8.
