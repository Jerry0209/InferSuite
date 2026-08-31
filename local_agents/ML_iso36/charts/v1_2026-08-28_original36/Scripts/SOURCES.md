# v1 generators (frozen)

The v1 figures were rendered by the pre-paper-style generators as of commit `6e9c4f205`
(before the 2026-08-31 paper restyle). Recover any script with:

    git show 6e9c4f205:local_agents/kit/plot/<script>

| Figure family | Generator |
|---|---|
| iso36_live_overview* | plot_iso36_live_overview.py / .R |
| iso36_cpu_work | plot_iso36_cpu_work.py |
| iso36_active_wall | plot_iso36_wall.py |
| iso36_tma_l1_* / _combined | plot_iso36_tma.py / plot_iso36_tma_combined.py |
| iso36_rows_* / iso36_rows_agg_* | plot_iso36_rows.py / plot_iso36_rows_agg.py / .R |
| iso36_agg_{ipc,frontend,memory,system}_* | plot_iso36_agg_groups.R |
| iso36_agg_compact_* | plot_iso36_agg_compact.R (pre-v2 form) |
| iso36_grid_* | plot_iso36_grid.py |

Scripts are intentionally NOT copied here: they have since evolved in place, and the
commit pin above is the exact reproducible source.
