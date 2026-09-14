# Multi-suite chart pack — v2_2026-09-14_cassandra-reinstated

SPEC CPU 2026 · agentic 36 (SWE-bench Multilingual) · DCPerf · Renaissance · DaCapo Chopin.
Same layout as every other pack: one raw-data file, one script, one PDF (paper) + PNG
(slides) per figure. Unit rule for fig01: violins are distributions over WORKLOADS (SPEC 26,
agentic 36, one vote each); each external benchmark is ONE marker at its vote (median of its
windows), grouped under its suite, with a bar for its own window IQR. fig02–fig05 are the
per-window companions (one column per benchmark). Method and findings: `../../README.md`.

| Fig | Name | What it shows |
|---|---|---|
| fig01 | agg_compact | 12-metric grid: SPEC and agentic violins (one vote per workload), one marker per external benchmark grouped by suite |
| fig02 | agg_ipc | IPC per 100 ms window, one column per benchmark, one block per suite |
| fig03 | agg_frontend | frontend metrics per window |
| fig04 | agg_memory | memory metrics per window |
| fig05 | agg_system | context switches per CPU-second, log axis |

`Raw data/*_per_window_rows.csv.gz` hold every external per-window value; the two
`*_numbers.csv` files hold every displayed vote and column median.

**What changed from v1.** DaCapo `cassandra` is included. In v1 it was excluded on a
steady-state gate failure that turned out to be a defect in the gate, not in the benchmark
(the gate compared per-sample medians of a duty-cycled workload and divided by a near-zero
denominator). The gate was rewritten, all ten captures pass it, and cassandra is reinstated
in every panel. It is the front-end and context-switch extreme of the whole study, and its
DRAM traffic of 0.0185 GB/s is the lowest measured — which retired the earlier claim that the
agentic family was the memory-quiet extreme. Full account: `../../README.md` §8.
