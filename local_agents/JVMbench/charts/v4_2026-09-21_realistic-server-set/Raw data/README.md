# Raw data — what every file is

All CSVs are UTF-8, comma-separated, header row first; `.gz` files are gzip and read
directly by pandas (`pd.read_csv(path)`) or R (`read.csv(gzfile(path))`).

## The values the violins are drawn over

| File | Schema | What a row is |
|---|---|---|
| `runtime_votes.csv` | `family, subgroup, workload, metric, value, windows, runs` | **one row per workload and metric: the metric over the workload's whole runtime** (counters summed over all its windows, ratio taken once). `family` = spec26 / agentic36 / dcperf / renaissance / dacapo; `subgroup` = SPEC-int or SPEC-fp, the task's language, or the suite; `windows` = how many 100 ms windows carried that metric's counters; `runs` = profiling runs summed (SPEC 1, all others 9). This is the input of every violin and marker in fig01 and fig06 and of the SPEC / Server columns in the per-window figures. |

## The per-window inputs (agentic columns, marker IQR bars, and the older median rule)

| File | Rows | Schema | What a row is |
|---|---|---|---|
| `spec_agentic_rows_long.csv.gz` | SPEC + agentic | `fence, metric, grp, col, value` | SPEC (`grp` = `SPEC-int`/`SPEC-fp`): **one row per benchmark**, `value` = that benchmark's median over its windows (26 rows per metric per fence). Agentic (`grp` = language, `col` = task): **one row per 100 ms window**. Three `fence` values: `tool` (sandbox container), `harness` (agent process), `both` (their sum at the raw-count level) — every figure uses `both`. 16 metrics; the figures show 12. |
| `renaissance_per_window_rows.csv.gz` | 5 benchmarks | same schema | one row per 100 ms window, `grp` = `Renaissance`, `col` = benchmark, `fence` = `both` (the whole JVM) |
| `dacapo_per_window_rows.csv.gz` | 3 benchmarks | same schema | as above, `grp` = `DaCapo` (cassandra, tomcat, kafka) |
| `dcperf_per_window_rows.csv.gz` | 2 benchmarks | same schema | as above, `grp` = `DCPerf` (feedsim, video_transcode); used by fig06–fig10 only |

`value` is always co-counted inside its window: MPKI = misses / instructions of that same
window × 1000; DSB coverage = DSB uops / all uops; DRAM read GB/s = offcore data reads × 64 B /
window time; context switches / CPU-s = switches / the fence's task-clock seconds. A metric
appears only in windows whose counter group carried it (IPC and Branch MPKI: `fpbr`;
branch-direction / BTB / uop-cache: `fe_miss`; L1I: `fe_lat`; DSB: `fe`; L1D/L2/LLC: `cache`;
DRAM: `dram_bw`; context switches: `priv`), so per-metric row counts differ.

## The same measurements in time order (for other aggregations)

`timeseries_<family>.csv.gz`, one per family, schema
`family, workload, run, group, win, t_rel_s, dur_s, tag, metric, value`:

- `run` — which profiling run the window came from (`run_1`…`run_9`; SPEC has one run);
- `group` — the counter group live in that window (decides which metrics it carries);
- `win` — window index inside the run, capture order; `t_rel_s` — seconds since that run's
  first window; `dur_s` — the window's own counting time (≈ 0.1 s);
- `tag` — agentic only: what the tool fence was executing at that moment (2 Hz command
  tagger: `idle`, `harness`, a compiler, a test runner, …); blank for the other families;
- `metric`, `value` — as above, fence `both` only.

| File | Workloads | Rows |
|---|---|---|
| `timeseries_agentic36.csv.gz` | agentic36 | 421584 |
| `timeseries_dacapo.csv.gz` | dacapo | 72120 |
| `timeseries_dcperf.csv.gz` | dcperf | 64242 |
| `timeseries_realdata.csv.gz` | realdata | 142410 |
| `timeseries_renaissance.csv.gz` | renaissance | 120844 |
| `timeseries_spec26.csv.gz` | spec26 | 52936 |

These are what to use to try a different aggregation. Three that have been discussed:
(1) **one vote per workload** (what the figures do) keeps across-workload variation and
drops within-workload variation; (2) **pooling every window** keeps within-workload
variation but weights each workload by its window count — SPEC spans 70 to 2 658 windows
per benchmark, the agentic tasks 115 to 2 269, so the pooled shape is mostly the longest
runs; (3) **equal-weight pooling** — weight each window by 1 / (windows of its workload), or
resample the same number of windows from every workload — keeps within-workload shape
without the runtime bias. The Server suites' captures are fixed-length (~1 500 windows per
metric each), so for them (2) and (3) coincide; `SERVER_MODE=windows` in the scripts draws
that variant.

## Every number that is drawn

| File | What |
|---|---|
| `multi_server_compact_numbers.csv` | fig01: per (metric, side) the n / min / max / median / mean / sd of the per-workload values; plus one row per Server benchmark (`side` = `Server:DCPerf`, `Server:Renaissance` or `Server:DaCapo`, `workload` = benchmark) giving its whole-runtime value (`median`) and its window IQR (`min` = p25, `max` = p75) |
| `multi_server_numbers.csv` | fig02–05: per (metric, column) the median, mean and n of the points in that column |
| `multi_agg_compact_numbers.csv` | fig06: as for fig01, with one row per external benchmark marker (`side` = suite) |
| `multi_agg_numbers.csv` | fig07–10: per (metric, column) median, mean, n |

## Provenance

Per-window values come from `analyze_l3_windows.py` (agentic, DCPerf, JVM: the same
derivation code) and from the SPEC kit's `spec_common.py`. Captures: measured cores 4–11,
SMT siblings offline, 3.2 GHz pinned, one counter group per 100 ms window with zero
multiplexing — `../../README.md` §6 has the full isolation table. Run counts per workload:
`../../README.md` §7.
