# ML_iso36 chart pack — v3 (paper-ready, 2026-09-06)

**This version (PI feedback 2026-09-06):** figures stripped for direct paper use — no
on-figure titles (the filename / paper caption carries them), no explanatory grey
footer/subtitle text, legends centred at the top of each figure (fig07's legend strip
unboxed and centred; fig03 gained an "Episode wall" legend entry to replace its footer);
group violins (fig09–fig12) lose the per-column median number labels and the red
"axis capped" text (the red triangle alone marks an off-scale column max; column medians
stay banked in the Raw data CSVs). fig08 (hero IPC) is carried over unchanged from v2.

Organized per the mentor's layout (2026-09-02): one raw-data file, one script and
one PDF+PNG per figure. **PDF → paper, PNG → slides.** Assembled from the two
latest generations (`../plots/paper_v1` bar family, `../plots/paper_v2` violin
family; see `../plots/MANIFEST.md` for full definitions and provenance).

Population: the revised all-resolved 36 count-view tasks (jekyll-8167 in).
`Raw data/` holds every number a figure displays. `Scripts/` are copies of the
canonical generators in `local_agents/kit/plot/` (edit there — the header of each
copy names its source); they run from the repo root against the banked data tree.
Regenerate everything: run each script with the repo's conda interpreters
(`infersuite-full` python for .py, the `rplot` env Rscript for .R), then rerun
`local_agents/kit/plot/build_chart_pack.py` to refresh this pack.

| Fig | Name | What it shows | Raw data |
|---|---|---|---|
| fig01 | live_overview | 4-panel live overview: CPU working vs stall, tool vs harness, #calls, call duration | `Raw data/fig01_live_overview.csv` |
| fig02 | wall_split_live | episode wall split into disjoint tool / harness / model-wait segments (live, stacked) | `Raw data/fig02_wall_split_live.csv` |
| fig03 | busy_wall_live | tool busy, harness busy and model wait side by side with the wall tick (live, grouped) | `Raw data/fig03_busy_wall_live.csv` |
| fig04 | cpu_work | CPU work in core-seconds by fence, stacked per task (replays, median of 9 episodes) | `Raw data/fig04_cpu_work.csv` |
| fig05 | active_wall | fence busy time in seconds, grouped, with implied tool parallelism (replays) | `Raw data/fig05_active_wall.csv` |
| fig06 | tma_l1_combined | TMA Level 1 with both fences combined (slot-weighted), MEDIAN + SPEC reference rows | `Raw data/fig06_tma_l1_combined.csv` |
| fig07 | agg_compact_merged | 12-metric SPEC-vs-Agentic violin grid, one vote per workload, merged agent fence | `Raw data/fig07_agg_compact_merged.csv` |
| fig08 | hero_ipc | IPC hero: two violins + Min/Max/Median/Mean±Std stats strip | `Raw data/fig08_hero_ipc.csv` |
| fig09 | agg_ipc_merged | IPC per-window violins: SPEC band + 36 tasks by language, merged fence | `Raw data/fig09_agg_ipc_merged.csv.gz` |
| fig10 | agg_frontend_merged | frontend metrics (Branch/Branch-dir/BTB/L1I/DSB MPKI, DSB coverage), merged fence | `Raw data/fig10_agg_frontend_merged.csv.gz` |
| fig11 | agg_memory_merged | memory metrics (L1D/L2/LLC MPKI, DRAM read GB/s), merged fence | `Raw data/fig11_agg_memory_merged.csv.gz` |
| fig12 | agg_system_merged | context switches per CPU-second (log axis), merged fence | `Raw data/fig12_agg_system_merged.csv.gz` |

Notes: fig02/fig03 share one values source (each CSV is complete on its own).
fig09–fig12 raw data are per-window rows (gzipped; R reads .csv.gz natively).
fig07/fig08 raw data are one row per workload (the per-window medians the violins
vote with). The selection-matrix figure is metadata, not measurement, and lives at
`../plots/iso36_selection_matrix.png`.
