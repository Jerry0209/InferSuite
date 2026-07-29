# InferSuite documentation

Entry point for the repo's documentation. Start here; each item says what it is and when
you'd read it.

## Microarchitectural study reports — `reports/`

Reproducibility-grade write-ups of the agent-CPU studies (one per study, from the team
deck's slide 17 onward). Each report: key summary → methodology with every load-bearing
decision and the scripts used → insights ranked by importance.
Full index and reading order: **[reports/README.md](reports/README.md)**.

| Report | Study in one line |
|---|---|
| [01 — django temperature experiment](reports/01_slide17_django_temperature_experiment.md) | Temp-0.6 episodes revealed a layered failure: greedy-decode loops were masking a stock SWE-agent submit-tool crash on Python-3.5 task containers — the task is unsolvable at any temperature, and the bug is upstream-unreported |
| [02 — TMA Level-2 drill](reports/02_slide18_tma_level2_drill.md) | The banked continuous census already contains Level 2: scikit-learn is core-bound (not DRAM); astropy/sympy split frontend evenly between fetch-latency and fetch-bandwidth |
| [03 — tool-call boundary marking](reports/03_slide21_tool_call_boundary_marking.md) | Method audit: the tool/harness boundary is a kernel cgroup wall (exact); per-call time attribution is an ordinal anchor join (heuristic, with printed diagnostics) |
| [04 — per-window distributions & TMA L3](reports/04_slides19-23_per_window_distributions_tma_l3.md) | Dedicated-group deterministic replays at 2-s windows with live command tagging: distribution shapes per task, the L3 memory-ladder verdict, and three new counters (BTB / µop-cache / branch-direction) |

Companion material elsewhere in the repo:

- `../analysis.md` — the running prose analysis (campaign reproduction, comparisons,
  temperature discussion; Parts 1–7).
- `../local_agents/scripts/glm/events.md` — every perf event the kit measures, the derived
  metric each feeds, and the exact formulas.
- `../local_agents/scripts/glm/README.md` — the campaign kit itself (stages, knobs, fences).

## Campaign & handover documents

- **[AGENTS_HANDOVER.md](AGENTS_HANDOVER.md)** — file-by-file tour and reading order for the
  agent measurement campaigns (what is tracked where, the records tarball, post-clone steps).
- **[workload_conformance_review.md](workload_conformance_review.md)** — review of workload
  conformance for the measured campaigns.

## Diagrams

- `architecture.png` — service architecture overview.
- `service_pipeline.png` / `service_pipeline_fenced.png` — the service data path, plain and
  with measurement fences drawn.
- `agent_pipeline_draft.png` — agent-campaign measurement pipeline (draft).
- `infersuite_logo.png` — project logo.
