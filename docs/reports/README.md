# Microarchitectural study reports

One report per study of the team deck ("Agent CPU profiling — GLM-5.2 SWE-agent", 25
slides), written for reproducibility: each has (1) a key summary, (2) the methodology with
every load-bearing decision and the scripts used, (3) insights ordered by importance. The
running prose companion is [`../handwritten_notes/analysis.md`](../handwritten_notes/analysis.md);
the counter-event reference is `local_agents/scripts/glm/events.md`. Reports are numbered by
creation; the table below is ordered by deck slide.

| Deck slides | Report | Study |
|---|---|---|
| 1–6 | [05 — featured reproduction results](05_slides1-6_featured_reproduction.md) | How one representative episode per task is selected (never pooled), rendered into the wall-clock / CPU-work / timeline / tool-call figures, and audited (ALL MATCH) |
| 7–12 | [06 — run-to-run variance](06_slides7-12_run_to_run_variance.md) | All 24 episodes of both campaigns side by side: shares and shapes reproduce; absolute wall/core-s are 2–3× draws; within-campaign variance ≥ between-campaign difference |
| 13 | [07 — inside the fences](07_slide13_inside_the_fences.md) | CPU attribution inside each fence: tool CPU by agent-call class (trajectory-anchored), harness CPU by library (perf DSO shares — time-shares, not miss-shares) |
| 14–16 | [08 — TMA L1 & signatures](08_slides14-16_tma_l1_signatures.md) | Microarchitecture-level reproducibility: TMA L1 side by side, signature heatmaps on hardware-anchored absolute scales, TMA for every run — the tightest-reproducing layer of the study |
| 17 | [01 — django temperature experiment](01_slide17_django_temperature_experiment.md) | Temp-0.6 episodes revealed a layered failure: decode loops were masking a stock SWE-agent submit-tool crash on Python-3.5 task containers (unsolvable at any temperature; upstream-unreported) |
| 18 | [02 — TMA Level-2 drill](02_slide18_tma_level2_drill.md) | The banked continuous census already contains Level 2: scikit-learn core-bound (not DRAM); astropy/sympy split frontend evenly between fetch-latency and fetch-bandwidth |
| 19–23 | [04 — per-window distributions & TMA L3](04_slides19-23_per_window_distributions_tma_l3.md) | The capture method: dedicated-group deterministic replays, 2-s windows, 2 Hz command tagger, three new counter groups, CSV-first outputs, cross-task grids and galleries |
| 19–23 | [09 — frontend instruction supply](09_slides19-23_frontend_instruction_supply.md) | Metric group: L1I pressure, iCache/iTLB stalls, DSB vs MITE delivery, µop-cache misses, decoder-switch penalties — the axis that most cleanly separates the tasks |
| 19–23 | [10 — branches & speculation](10_slides19-23_branches_speculation.md) | Metric group: all/direction/indirect mispredicts, BTB-miss proxy (BAClears), resteer cycles, TMA bad-speculation — sympy worst and direction-dominated |
| 19–23 | [11 — memory hierarchy](11_slides19-23_memory_hierarchy.md) | Metric group: L1D/L2/LLC ladder, AMAT (fixed-latency model), MLP, exact TMA-L3 memory ladder, DRAM occupancy vs stall — L1-bound, DRAM stall ≈ 0 |
| 19–23 | [12 — execution core & system](12_slides19-23_execution_core.md) | Metric group: IPC distributions, ports-utilization cycle profile (not parent-nested — caveat), divider, vector-FP share, kernel share |
| 24–25 | [13 — multilingual language axis](13_slides24-25_multilingual_language_axis.md) | SWE-bench Multilingual (babel JS, fmt C++) profiled by the same per-window method at zero API cost: instruction-supply pressure is not a CPython artifact; the harness is language-independent |
| 21 | [03 — tool-call boundary marking](03_slide21_tool_call_boundary_marking.md) | Method audit: cgroup wall (spatial, exact) + ordinal anchor join (temporal, heuristic-with-diagnostics); underpins 07, 09–12 |
| 1–25 | [14 — instrument-to-figure reference](14_slides1-25_instrument_to_figure_reference.md) | Cross-cutting: which instrument produced each deck number, exact vs heuristic layer, and the code site of every constant — plus the JS command-tagger gap that qualifies babel's tag mix on 24–25, and the published slide links |

**Reading order for a newcomer:** 14 (which instrument produced what) → 03 (what a "tool call"
is in this data) → 05 → 06 → 07 → 08 → 02 → 04 → 09/10/11/12 (any order) → 13 → 01.

**Numbering note:** 01–04 were written first (slides 17+); 05–12 filled in the earlier deck
sections and the per-window metric groups; 13 covers the multilingual extension; 14 is the
cross-cutting instrument reference spanning the whole deck. File numbers are stable
identifiers — do not renumber.
