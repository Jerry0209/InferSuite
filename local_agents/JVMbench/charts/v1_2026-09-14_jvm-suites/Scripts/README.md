# Scripts — what each one does (v1, superseded)

Every `fig*.R` here is a verbatim copy of its canonical generator in `local_agents/kit/plot/`
(edit there, not here). All run from the repository root with the `rplot` conda environment's
Rscript and read the banked data trees, not this folder:

```bash
cd ~/InferSuite
RS=~/miniforge3/envs/rplot/bin/Rscript
$RS local_agents/kit/plot/plot_paper_agg_compact_ext.R     # fig01
$RS local_agents/kit/plot/plot_paper_agg_groups_ext.R      # fig02-05 (all four)
# outputs land in local_agents/JVMbench/plots/paper_v1/
```

| Script | Draws | Reads | Knobs (environment variables) |
|---|---|---|---|
| `fig01_agg_compact.R` | the 12-panel grid: SPEC and Agentic violins (one vote per workload), one diamond per external benchmark grouped by suite | `Raw data/spec_agentic_rows_long` + the three `*_per_window_rows` files | `EXT_ROWS` = colon-separated rows files (which suites appear); `ADJ` = violin bandwidth multiplier; `EXT_OUT`, `EXT_STEM` = output dir / stem, repo-relative |
| `fig02_agg_ipc.R`, `fig03_agg_frontend.R`, `fig04_agg_memory.R`, `fig05_agg_system.R` | the four per-window group figures: SPEC-int, SPEC-fp, one column per agentic task by language, then one column per external benchmark in a block per suite (one script, four outputs) | same | `EXT_ROWS`, `EXT_OUT`; `VARIANT=broken_axis` cuts the frontend/memory y axes |

Re-running these today reproduces the v2 figures, not these: cassandra is no longer excluded
and the rows files have been regenerated. The shared look (fonts, violin outline, the inner
box / median / mean glyph, the broken-axis rule) lives in `local_agents/kit/plot/theme_paper.R`.
