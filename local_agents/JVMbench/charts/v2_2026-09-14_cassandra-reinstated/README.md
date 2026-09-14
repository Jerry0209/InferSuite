# Multi-suite chart pack — v2_2026-09-14_cassandra-reinstated

SPEC CPU 2026 (26 benchmarks) · **Server** = the JVM server set requested by the mentor on
2026-09-14 (Renaissance finagle-http, finagle-chirper, page-rank, naive-bayes, neo4j-analytics;
DaCapo Chopin cassandra, tomcat, kafka) · Agentic 36 (SWE-bench Multilingual). DCPerf's two
benchmarks appear only in the per-benchmark companions (fig06–fig10), since the Server set
was defined as the JVM suites.

One PDF (paper) + one PNG (slides) per figure. Each subdirectory has its own README:
[`Figures/`](Figures/README.md) how to read them · [`Raw data/`](Raw%20data/README.md) what
every file holds · [`Scripts/`](Scripts/README.md) what every script does and how to run it.
Method, isolation, run counts and findings: `../../README.md`.

| Fig | File stem | What it shows |
|---|---|---|
| fig01 | `fig01_agg_compact_server` | 12-metric grid, THREE violins per panel: SPEC (26), Server (8 JVM benchmarks), Agentic (36); one vote per workload |
| fig02 | `fig02_agg_ipc_server` | IPC: SPEC-int, SPEC-fp, Server columns (one vote per benchmark) then one column per agentic task (its 100 ms windows) |
| fig03 | `fig03_agg_frontend_server` | frontend metrics, same columns as fig02 |
| fig04 | `fig04_agg_memory_server` | memory metrics, same columns as fig02 |
| fig05 | `fig05_agg_system_server` | context switches per CPU-second (log axis), same columns as fig02 |
| fig06 | `fig06_agg_compact_per_benchmark` | the same grid with SPEC and Agentic violins and ONE MARKER per external benchmark (DCPerf 2, Renaissance 5, DaCapo 3) so you can see which benchmark sits where |
| fig07 | `fig07_agg_ipc_per_benchmark` | IPC with one per-window column per external benchmark, grouped by suite, after the agentic tasks |
| fig08 | `fig08_agg_frontend_per_benchmark` | frontend metrics, per-benchmark columns |
| fig09 | `fig09_agg_memory_per_benchmark` | memory metrics, per-benchmark columns |
| fig10 | `fig10_agg_system_per_benchmark` | context switches per CPU-second, per-benchmark columns |

**The unit rule, which every figure here follows.** A *vote* is one number per workload: the
median of that workload's 100 ms windows for the metric. A violin in the compact grid is a
distribution over votes — SPEC 26, Server 8, Agentic 36 — never a pool of windows, because
pooling weights each workload by how long it ran (SPEC spans 70 to 2 658 windows per
benchmark). In the per-window figures the three reference columns (SPEC-int, SPEC-fp, Server)
are distributions over benchmark votes, while each agentic column is that task's own windows.
`Raw data/` carries the per-window rows in time order so any other aggregation can be tried.

**Runs behind a vote.** One profiling run per counter group per workload: SPEC 1 execution
per benchmark (11 groups rotating inside it), the agentic 36, DCPerf, Renaissance and DaCapo
9 runs each (one dedicated group per run). A metric's vote is the median over the windows of
the single run that carried its counters; run-to-run repetition is n = 1 in every family.
Details: `../../README.md` §7 and `../../../DCPerf/README.md` §7.8.
