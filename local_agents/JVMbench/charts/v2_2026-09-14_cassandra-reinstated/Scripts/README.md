# Scripts — what each one does

Every `fig*.R` here is a verbatim copy of its canonical generator in
`local_agents/kit/plot/` (edit there, not here). All run from the repository root with the
`rplot` conda environment's Rscript and read the banked data trees, not this folder:

```bash
cd ~/InferSuite
RS=~/miniforge3/envs/rplot/bin/Rscript
$RS local_agents/kit/plot/plot_paper_agg_compact_server.R     # fig01
$RS local_agents/kit/plot/plot_paper_agg_groups_server.R      # fig02-05 (all four)
$RS local_agents/kit/plot/plot_paper_agg_compact_ext.R        # fig06
$RS local_agents/kit/plot/plot_paper_agg_groups_ext.R         # fig07-10 (all four)
# outputs land in local_agents/JVMbench/plots/paper_v1/; then
VERSION=v2_2026-09-14_cassandra-reinstated python3 local_agents/kit/plot/build_jvm_chart_pack.py
```

| Script | Draws | Reads | Knobs (environment variables) |
|---|---|---|---|
| `fig01_agg_compact_server.R` | the 12-panel grid with three violins (SPEC, Server, Agentic) | `spec_agentic_rows_long` + the Server suites' rows | `SERVER_MODE=votes` (default: one vote per benchmark) or `windows` (pool the 8 benchmarks' windows); `EXT_ROWS` = colon-separated rows files that form the Server set; `ADJ` = violin bandwidth multiplier; `EXT_OUT`, `EXT_STEM` output dir/stem (repo-relative) |
| `fig02–05_agg_*_server.R` | the four per-window group figures with a single Server column | same | `SERVER_MODE`, `EXT_ROWS`, `EXT_OUT` as above |
| `fig06_agg_compact_per_benchmark.R` | the grid with one diamond per external benchmark | `spec_agentic_rows_long` + dcperf/renaissance/dacapo rows | `EXT_ROWS`, `ADJ`, `EXT_OUT`, `EXT_STEM` |
| `fig07–10_agg_*_per_benchmark.R` | per-window figures with one column per external benchmark, one block per suite | same | `EXT_ROWS`, `EXT_OUT`; `VARIANT=broken_axis` cuts the frontend/memory y axes |
| `export_spec_agentic_rows.py` | — | the SPEC kit's per-window metrics and the agentic `all_windows_*.csv` | writes `agg_rows_long.csv` (= `Raw data/spec_agentic_rows_long.csv.gz`) |
| `export_suite_rows.py` | — | an external suite's `all_windows_*.csv` | `--suite --label --data --out`; writes `<suite>_rows_long.csv` (= `Raw data/<suite>_per_window_rows.csv.gz`); skips a workload with an `EXCLUDED` marker |
| `export_timeseries_rows.py` | — | the same per-window files, keeping time order | `--out DIR`; writes `Raw data/timeseries_<family>.csv.gz` |

The scripts write `*_numbers.csv` next to the figures with every displayed number; the
pack copies them into `Raw data/`. The shared look (fonts, violin outline, the inner
box/median/mean glyph, broken-axis rule) lives in `local_agents/kit/plot/theme_paper.R`.
