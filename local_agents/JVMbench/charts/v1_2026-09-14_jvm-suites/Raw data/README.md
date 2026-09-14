# Raw data — what every file is (v1, superseded)

All CSVs are UTF-8, comma-separated, header row first; `.gz` files are gzip and read directly
by pandas (`pd.read_csv(path)`) or R (`read.csv(gzfile(path))`). Time-ordered per-window rows
for every family (`timeseries_<family>.csv.gz`) are in the v2 pack's `Raw data/`.

## The exact inputs the figure scripts read

| File | Rows | Schema | What a row is |
|---|---|---|---|
| `spec_agentic_rows_long.csv.gz` | SPEC + agentic | `fence, metric, grp, col, value` | SPEC (`grp` = `SPEC-int`/`SPEC-fp`): **one row per benchmark**, `value` = that benchmark's median over its windows (26 rows per metric per fence). Agentic (`grp` = language, `col` = task): **one row per 100 ms window**. Three `fence` values: `tool` (sandbox container), `harness` (agent process), `both` (their sum at the raw-count level) — every figure uses `both`. 16 metrics; the figures show 12. Added 2026-09-14 so the pack is self-contained; the figures were drawn from this same file. |
| `renaissance_per_window_rows.csv.gz` | 5 benchmarks | same schema | one row per 100 ms window, `grp` = `Renaissance`, `col` = benchmark, `fence` = `both` (the whole JVM) |
| `dacapo_per_window_rows.csv.gz` | 2 benchmarks | same schema | as above, `grp` = `DaCapo` — **tomcat and kafka only**; cassandra was excluded when v1 was built (wrongly, see `../../../README.md` §8) |
| `dcperf_per_window_rows.csv.gz` | 2 benchmarks | same schema | as above, `grp` = `DCPerf` (feedsim, video_transcode) |

`value` is always co-counted inside its window: MPKI = misses / instructions of that same
window × 1000; DSB coverage = DSB uops / all uops; DRAM read GB/s = offcore data reads × 64 B /
window time; context switches / CPU-s = switches / the fence's task-clock seconds. A metric
appears only in windows whose counter group carried it (IPC and Branch MPKI: `fpbr`;
branch-direction / BTB / uop-cache: `fe_miss`; L1I: `fe_lat`; DSB: `fe`; L1D/L2/LLC: `cache`;
DRAM: `dram_bw`; context switches: `priv`), so per-metric row counts differ.

## Every number that is drawn

| File | What |
|---|---|
| `multi_agg_compact_numbers.csv` | fig01: per (metric, side) the n / min / max / median / mean / sd of the votes; plus one row per external benchmark marker (`side` = suite, `workload` = benchmark) giving its vote (`median`) and window IQR (`min` = p25, `max` = p75) |
| `multi_agg_numbers.csv` | fig02–05: per (metric, column) the median, mean and n of the points in that column |

## Provenance

Per-window values come from `analyze_l3_windows.py` (agentic, DCPerf, JVM: the same derivation
code) and from the SPEC kit's `spec_common.py`. Captures: measured cores 4–11, SMT siblings
offline, 3.2 GHz pinned, one counter group per 100 ms window with zero multiplexing —
`../../../README.md` §6 has the full isolation table; run counts per workload in §7.
