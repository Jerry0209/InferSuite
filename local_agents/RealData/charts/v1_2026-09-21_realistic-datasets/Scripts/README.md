# Scripts — what each one does

Verbatim copies of the canonical generators in `local_agents/kit/plot/` (edit there). Run from the
repository root with the `rplot` conda environment's Rscript:

```bash
cd ~/InferSuite
RS=~/miniforge3/envs/rplot/bin/Rscript
PY=~/miniforge3/envs/infersuite-full/bin/python3
$PY local_agents/kit/plot/export_runtime_votes.py                       # runtime_votes.csv, all families
$RS local_agents/kit/plot/plot_paper_realdata_pairs.R                   # fig01
SERVER_SET=realistic $RS local_agents/kit/plot/plot_paper_agg_compact_server.R   # fig02
$RS local_agents/kit/plot/plot_paper_agg_compact_server.R               # fig03
VERSION=v1_2026-09-21_realistic-datasets python3 local_agents/kit/plot/build_realdata_chart_pack.py
```

| Script | Draws | Knobs |
|---|---|---|
| `fig01_realdata_pairs.R` | the toy → realistic pair grid | `RUNTIME_VOTES` (values file), `EXT_OUT` (output dir, repo-relative); pairs are listed at the top of the script |
| `fig02/fig03_agg_compact_server_*.R` | the three-violin grid | `SERVER_SET=realistic` or `suite`; `VOTE=runtime` or `median`; `SERVER_MODE=votes` or `windows`; `EXT_ROWS`, `RUNTIME_VOTES`, `ADJ`, `EXT_OUT`, `EXT_STEM` |
| `export_runtime_votes.py` | — | writes one whole-runtime value per workload and metric through the SPEC comparison kit's loader |
| `export_timeseries_rows.py` | — | writes the per-window rows of every family in time order |
