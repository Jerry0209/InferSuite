# InferSuite documentation

Entry point for the repo's documentation. Start here; each item says what it is and when
you'd read it.

## Microarchitectural study reports — `reports/`

Reproducibility-grade write-ups of the agent-CPU studies — one per study, covering the
full 23-slide team deck section by section, plus one report per per-window metric group.
Each report: key summary → methodology with every load-bearing
decision and the scripts used → insights ranked by importance.
Full index and reading order: **[reports/README.md](reports/README.md)**.

| Deck slides | Report | Study in one line |
|---|---|---|
| 1–6 | [05 — featured reproduction](reports/05_slides1-6_featured_reproduction.md) | Representative-episode selection, figure pipeline, and the ALL-MATCH audit |
| 7–12 | [06 — run-to-run variance](reports/06_slides7-12_run_to_run_variance.md) | All 24 episodes: shares/shapes reproduce, absolutes are 2–3× draws |
| 13 | [07 — inside the fences](reports/07_slide13_inside_the_fences.md) | Tool CPU by agent-call class; harness CPU by library (time-shares, not miss-shares) |
| 14–16 | [08 — TMA L1 & signatures](reports/08_slides14-16_tma_l1_signatures.md) | Microarch reproducibility: TMA buckets and hardware-anchored signature heatmaps |
| 17 | [01 — django temperature experiment](reports/01_slide17_django_temperature_experiment.md) | Decode loops were masking an upstream SWE-agent submit-tool crash on Python-3.5 containers |
| 18 | [02 — TMA Level-2 drill](reports/02_slide18_tma_level2_drill.md) | scikit-learn core-bound not DRAM; astropy/sympy fetch-latency ≈ fetch-bandwidth |
| 19–23 | [04 — per-window method](reports/04_slides19-23_per_window_distributions_tma_l3.md) | Dedicated-group deterministic replays, 2-s windows, live command tagging, TMA L3 |
| 19–23 | [09 — frontend instruction supply](reports/09_slides19-23_frontend_instruction_supply.md) | L1I/iTLB/DSB/µop-cache metric family — the cleanest task separator |
| 19–23 | [10 — branches & speculation](reports/10_slides19-23_branches_speculation.md) | Mispredict direction/indirect split, BTB proxy, resteers |
| 19–23 | [11 — memory hierarchy](reports/11_slides19-23_memory_hierarchy.md) | Cache ladder, AMAT model, MLP, exact TMA-L3 memory ladder, DRAM occupancy-vs-stall |
| 19–23 | [12 — execution core & system](reports/12_slides19-23_execution_core.md) | IPC distributions, ports cycle profile, vector-FP, kernel share |
| 21 | [03 — tool-call boundary marking](reports/03_slide21_tool_call_boundary_marking.md) | Method audit: cgroup wall + ordinal anchor join |

Companion material elsewhere in the repo:

- [`handwritten_notes/`](handwritten_notes/) — the running working notes: `analysis.md` (the
  prose analysis, Parts 1–7), `reproduce.md`, `metrics.md`, `further_check.md`.
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
