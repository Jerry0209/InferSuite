# Raw data — what every file is

| File | What a row is |
|---|---|
| `realdata_pairs_numbers.csv` | fig01: one row per (workload, metric): `toy` and `real` whole-runtime values, `spec` and `agentic` medians, `ratio` = real / toy |
| `multi_server_compact_realistic_numbers.csv` | fig02: per (metric, side) n / min / max / median / mean / sd of the per-workload values; one row per Server benchmark (`side` = `Server:<suite>` or `Server:RealData`) with its value (`median`) and, for suite benchmarks, its window IQR |
| `multi_server_compact_numbers.csv` | fig03: the same for the suite Server set |
| `runtime_votes.csv` | every whole-runtime value of every workload in every family (`family` = spec26 / agentic36 / dcperf / renaissance / dacapo / realdata; `windows` and `runs` behind each) — the input of every figure |
| `realdata_per_window_rows.csv.gz` | the realistic workloads' per-window values (`fence, metric, grp, col, value`; fence `both` = the whole server) |
| `timeseries_realdata.csv.gz` | the same in time order (`run, group, win, t_rel_s, dur_s, metric, value`) for other aggregations |

Values are co-counted inside each window; a metric exists only in windows whose counter group
carried it (IPC/branch MPKI: fpbr; branch-direction/BTB/uop-cache: fe_miss; L1I: fe_lat; DSB: fe;
L1D/L2/LLC: cache; DRAM: dram_bw; context switches: priv). Captures: measured cores 4–11, SMT
siblings offline, 3.2 GHz pinned, 100 ms windows, zero multiplexing (`../../README.md` §1).
