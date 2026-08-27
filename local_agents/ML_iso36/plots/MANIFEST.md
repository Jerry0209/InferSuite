# ML_iso36 figure manifest

Data: `local_agents/ML_iso36/data` — **36 tasks × 9 dedicated-group replay passes = 324
episodes**, 273,005 windows of 100 ms, captured 2026-08-21→22 on measured cores 4–11 (SMT
off), ISO-PROOF-gated, model never called. Sweep: 14.5 h wall, zero failed passes, zero
multiplexed and zero not-supported windows (audited over every window file), 324/324
episodes carry the continuous TMA census. Selection: `../../ML_typeid/selection_36_count.tsv`
(count-view, 4 per language; see `docs/multi_full_stratification.md` "Selection (36 of 300)").
Regenerate everything with `../derive_and_plot.sh`; the SPEC comparison with
`SPEC_COMPARISON_OUT=~/spec26-infra/infra/comparison_iso36.json python3
~/spec26-infra/infra/scripts/compare_spec_agentic.py data local_agents/ML_iso36/data/*/run_*/`.

Every number a figure displays is banked beside it (`iso36_tma_values.json`,
`iso36_grid_values.json`), so a reader can check a bar without reading pixels.

| Figure | What it shows | Population |
|---|---|---|
| `iso36_selection_matrix.png` | the 36 picks placed on the count-view type matrix; shade = cell population, '+' = majority top-up | selection metadata (no measurement) |
| `iso36_tma_l1_{tool,harness}.png` | TMA Level 1 per fence, one panel per language (4 tasks each), SPEC CPU 2026 medians (INT / FP) as the closing panel | census counts pooled over each task's 9 episodes; per-episode spread banked |
| `iso36_live_overview.{png,pdf}` | 4-panel paper figure over the LIVE census episodes of the revised 36 (0 excluded): (a) CPU working vs stall — % of episode wall with ≥1 fence above the burst floors (0.2 s union grid) vs the rest (dominated by model wait); (b) tool vs harness fence core-second split; (c) # tool calls — every trajectory action incl. failed/errored and the final submit, no model-only turns; (d) median tool-call duration (execution_time) | AVG bar = unweighted per-task mean (panel d: mean of medians, no median-of-medians); headline: working 14.6% / stall 85.4%, tool 78.6% / harness 21.4%, 105 calls avg, median call 0.12 s. Values + rule: `iso36_live_overview_values.json` |
| `../../SWE_iso8/plots/live_vs_replay/lvr_*.png` (12) | live-vs-replay validation (mentor request 2026-08-27): per metric, the LIVE per-window distribution (violin, box inside — rotation, 2 s, SMT-on) beside the dedicated-replay distribution (100 ms, SMT-off); TMA panels carry one replay violin per episode. The 36 picks have no live counters by design (typeid light mode), so the validation rides the 12 same-trajectory SWE_iso8 pairs | replay/live TMA median ratios: retiring 1.00, bad-spec 0.96, frontend 0.86, backend 1.12; AMAT 0.96, MLP 1.04; IPC 1.22 = the measured SMT effect. DRAM GB/s excluded (wall-rate metric diluted by in-window model wait at 2 s). Values: `live_vs_replay_values.json`; gallery artifact + deck slide 43 |
| `iso36_tma_l1_combined.png` | TMA Level 1 with the tool AND harness fences combined — census counts summed across both fences (slot-weighted by construction: each fence contributes in proportion to the pipeline slots it issued), one bar per task grouped by language, SPEC-int/SPEC-fp medians closing; right margin shows each task's tool-slot share | values + tool-slot shares banked in `iso36_tma_combined_values.json`. Combined frontend-bound median 30% (21–37%). Deck slide 42 |
| `iso36_rows_{tool,harness}.png` | **the final chart format (mentor spec 2026-08-25)**: 18 metrics, one full-width row each; groups SPEC-int (14 benchmarks) → SPEC-fp (12) → 9 languages × 4 tasks; every column is that workload's per-window box; one color per language, two neutral greys for SPEC | per-window on BOTH sides (100 ms); SPEC per-window derivations extended in `spec26/kit/plot/spec_common.py` (miss rates, branch-direction MPKI, ctx/CPU-s) so all 18 metrics exist there; featured on deck slides 39–40 |
| `iso36_cpu_work.png` | CPU work in core-seconds by fence (tool vs harness, the deck-wide green/purple), one stacked bar per task grouped by language; total + % tools annotated | per-fence MEDIAN over each task's 9 replay episodes (runs never pooled; min–max banked in `iso36_cpu_work_values.json`); reset-safe cpu.stat accounting; no inference or litellm wedge — replays never call the model. Deck slide 39 |
| `iso36_active_wall.png` | the SECONDS companion to `iso36_cpu_work.png`: per-fence busy time (10 Hz intervals above the burst floors, tool 0.005 / harness 0.02 cores) as GROUPED bars — never stacked, the fences overlap in time — with the episode wall as a tick and the tool bar annotated with implied parallelism (core-s ÷ busy-s) | per-fence median over the 9 replay episodes; spread + parallelism banked in `iso36_active_wall_values.json`. Core-seconds read as work, busy seconds as time; they diverge exactly where builds parallelize (median ×1.2, up to ×3.6). Deck slide 40 |
| `iso36_agg_{ipc,frontend,memory,system}_{tool,harness}.{png,pdf}` (8 pictures) | the aggregated comparison SPLIT INTO GROUP PICTURES (mentor 2026-08-28): ipc = IPC; frontend = Branch MPKI, Branch-direction MPKI, BTB MPKI, L1I MPKI, DSB MPKI (uop-cache miss), DSB hit rate — exact order; memory = L1D/L2/LLC-load MPKI + DRAM read GB/s; system = context switches. Miss rates and L1I stall deliberately omitted per the mentor. Each metric chart carries a black bounding box and generous spacing; % axes clamped at 100 | same columns/violin+box+mean/outlier caps as the all-in-one figures (which stay banked, NOT replaced); rendered with the real Roboto Condensed (installed from hrbrthemes' bundled faces 2026-08-28); `plot_iso36_agg_groups.R` |
| `iso36_rows_agg_gg_{tool,harness}.{png,pdf}` | the 2026-08-27 house-style revision of the aggregated view: **16 metrics** (MLP + AMAT dropped), violin + box with median bar AND mean diamond per column; SPEC-int/SPEC-fp as suite violins over per-benchmark window-medians; outlier panels **axis-capped** (stats on full data; red triangle + note names each off-scale max): default cap 1.15× the largest column p97; for BTB MPKI and the load-MPKI ladder (L1D/L2/LLC), where whole columns are the outlier, the cap keys off the 90th percentile of the columns' p95s (×1.2) so outlier columns cannot set the axis | rendered via the skillhub ggplot house style (`plot_iso36_rows_agg.R`, `iso36_style.R`); long data exported by `export_agg_rows_long.py`; summary stats in `iso36_rows_agg_gg_numbers.csv`. Deck slide 47 |
| `iso36_rows_agg_{tool,harness}.png` | the aggregated companion (mentor follow-up 2026-08-25): SPEC collapsed to TWO boxes (SPEC-int, SPEC-fp — each a box over per-benchmark window-MEDIANS, one vote per benchmark), plus a **Python group** (scikit-learn, astropy, sympy from the matched-configuration SWE_iso8 replays; 4th slot reserved), then the 9 language groups | Python covers 15/18 metrics — the fe_miss trio was never captured for Python and carries a "to be measured" mark (no new profiling; box in use). Deck slide 42 |
| `iso36_grid_{tool,harness}.png` | the earlier compact 18-panel grid: 9 language clusters of 4 boxes colored by count-cell type (B/T/S/M); grey SPEC box closes every panel | agent boxes = per-window values (whis 5–95); SPEC box = 26 per-benchmark **episode** values (labelled; deliberately not per-window). Kept banked; superseded on the deck by `iso36_rows_*` |

## Metric definitions

The 16 = `cross_task_grid.py` `PANELS16` (the mentor's 4×4). Three of them — branch-direction
MPKI (`br_misp_retired.cond`), BTB MPKI (`baclears.any`), µop-cache MPKI
(`frontend_retired.any_dsb_miss`) — come from the **fe_miss** group, first captured on the
agent side by this campaign (pass 9). The two additions: **DRAM read bandwidth** = 64 B ×
`offcore_requests.data_rd` / window wall seconds (dram_bw group, same model as SPEC's
`DRAM_read_GBs`); **context switches per CPU-second** = `context-switches` / task-clock
(priv group, co-counted per window; task-clock-normalized so fence concurrency does not
distort the rate — on SPEC's single pinned process it equals per-wall-second).
Per-window derivations: `kit/replay/analyze_l3_windows.py`. Episode cards and the
SPEC-vs-agent table: the one shared implementation `~/spec26-infra/infra/scripts/
extract_metrics.py` → `comparison_iso36.json` (24 rows; each metric rests on the 36 replays
that ran its group, IPC on all 288 shared-group episodes).

## Headline numbers (comparison_iso36.json, medians, agent/SPEC)

Separating: context switches **223×** (1,012 vs 4.5 /CPU-s) · BTB MPKI **44×** · kernel
**29×** · L1I MPKI **12.7×** · microcode **10.8×** · L1I stalls **8.8×** · MITE **3.7×** ·
µop-cache miss **3.5×** · branch MPKI **3.3×** · branch-direction **3.2×**.
Not separating: AMAT **1.0×** · MLP **1.0×** · L2 miss rate **1.3×** — and SPEC-heavier:
L1D MPKI **0.6×** · DRAM read **0.6×** · L2 MPKI **0.7×** · IPC 1.88 vs 2.41.
The 12-task report-19 asymmetry (instruction supply + system time separate the workloads,
the memory ladder does not) holds at 36 tasks / 9 languages, and the three newly-captured
frontend counters land on the separating side.

## Standing caveats

- **Configuration is matched** (both sides cores 4–11 SMT off, 100 ms windows), so no SMT or
  window-length caveat is carried. **Contention is not retired**: SPEC runs one copy per
  core; the agent runs a harness process plus a container full of concurrent processes.
- The grid's SPEC box is a suite spread of episode values, not per-window distributions —
  stated in the figure title; the asymmetry is deliberate (26 benchmarks × episode value is
  the honest suite reference; pooling windows across benchmarks would not be).
- `vecFP_pct` ratio in the comparison JSON is an artifact (agent median 0.00); read the
  medians, not the ratio.
- TMA panels pool census counts across a task's 9 episodes (group-independent instrument,
  duration-weighted); the per-episode min–max is banked in `iso36_tma_values.json`.
- Small-fence picks (several PHP/Ruby/search cells, 5–54 core-s) are represented by design —
  the count-view cell exists, so it is profiled; their per-window boxes rest on fewer busy
  windows (n is banked per box).
