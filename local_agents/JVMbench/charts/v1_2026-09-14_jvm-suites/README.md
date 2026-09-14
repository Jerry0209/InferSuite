# Multi-suite chart pack — v1_2026-09-14_jvm-suites

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
