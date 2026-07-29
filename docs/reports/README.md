# Microarchitectural study reports

One report per study from **deck slide 17 onward**, written for reproducibility: each has
(1) a key summary, (2) the methodology with every load-bearing decision and the scripts
used, (3) insights ordered by importance. The deck referenced throughout is the published
team readout ("Agent CPU profiling — GLM-5.2 SWE-agent", 23 slides); the running prose
companion is the repo-root `analysis.md`.

| Report | Deck slides | Study |
|---|---|---|
| [01_slide17_django_temperature_experiment.md](01_slide17_django_temperature_experiment.md) | 17 | Two django episodes at temperature 0.6 → the layered failure: decode loops were masking a stock SWE-agent submit-tool crash on Python-3.5 task containers (unsolvable at any temperature; previously unreported upstream) |
| [02_slide18_tma_level2_drill.md](02_slide18_tma_level2_drill.md) | 18 | TMA Level-2 split from the banked continuous census (no new capture): scikit = core-bound not DRAM; astropy/sympy = fetch-latency ≈ fetch-bandwidth; astropy's L1I pressure time-resolved to the test suite |
| [03_slide21_tool_call_boundary_marking.md](03_slide21_tool_call_boundary_marking.md) | 21 | Method audit: how tool/agent-call boundaries are marked — cgroup wall (spatial, exact) + ordinal anchor join (temporal, heuristic-with-diagnostics) |
| [04_slides19-23_per_window_distributions_tma_l3.md](04_slides19-23_per_window_distributions_tma_l3.md) | 19–20, 22–23 | Per-window distribution study: dedicated-group deterministic replays, 2-s windows, 2 Hz command tagger, three new counter groups (TMA L3 + BTB/µop-cache/branch-direction), CSV-first outputs, cross-task grids and per-task galleries |

Context that predates slide 17 (not duplicated here): campaign reproduction and comparison
methodology in `analysis.md` Parts 1–4, the counter-event reference in
`local_agents/scripts/glm/events.md`, and the certified campaign kit's own
`local_agents/scripts/glm/README.md`.

Reading order for a newcomer: 03 (what a "tool call" even is in this data) → 02 → 04 → 01.
