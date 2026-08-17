# InferSuite documentation

Entry point for the repo's documentation. Start here; each item says what it is and when
you'd read it.

## Microarchitectural study reports — `reports/`

Reproducibility-grade write-ups of the agent-CPU studies — one per study, covering the
full 28-slide team deck section by section, plus one report per per-window metric group.
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
| 24–25 | [13 — multilingual language axis](reports/13_slides24-25_multilingual_language_axis.md) | JS + C++ via SWE-bench Multilingual: instruction-supply pressure generalizes; harness is language-independent |
| 21 | [03 — tool-call boundary marking](reports/03_slide21_tool_call_boundary_marking.md) | Method audit: cgroup wall + ordinal anchor join |
| 19–25 | [15 — cross-task attribution](reports/15_slides19-25_cross_task_attribution.md) | Why the tasks differ at all: which program owns each fence (BLAS kernels, source build, cc1plus, jest/V8) and how that explains every metric gap; two churn mechanisms rejected; three shipped defects fixed |
| 26–27 | [16 — nine-language expansion](reports/16_slides26-27_multilingual_expansion.md) | 9 languages / 12 workloads, gated (ownership 92–99 %); composition reproduces ~1 %, magnitude 5.33× episode noise; six silent defects fixed |
| 28 | [17 — ⟨language, type⟩ sampling frame](reports/17_slide28_language_type_sampling_frame.md) | 300 instances inventoried + classified; mechanism-type nested in language (9/9 cells covered); next campaign samples the behavioural axis |
| 1–25 | [14 — instrument-to-figure reference](reports/14_slides1-25_instrument_to_figure_reference.md) | Which instrument produced each deck number, exact vs heuristic, code site of every constant; JS-tagger gap; published slide links |
| own deck | [18 — SPEC CPU 2026 baseline](reports/18_spec26_cpu2026_baseline.md) | Traditional-workload baseline on the same instrument: method validated, and the two families separate on instruction supply (L1I 11.96×, kernel 23.18×), not on data (DRAM 0.07×) |
| own deck | [19 — SPEC vs agentic headline comparison](reports/19_spec_vs_agentic_headline_comparison.md) | Twelve metrics on the matched configuration: separation is instruction supply + kernel time (L1I 15.31×, kernel 28.04×), never the memory ladder (AMAT 0.99×, DRAM 0.79×) |
| own deck | [20 — TMA profile & bad speculation](reports/20_tma_profile_bad_speculation_radar.md) | TMA radar incl. bad speculation (15.4 % vs 10.0 %); prices the retired SMT caveat — IPC +18.8 %, TMA shape unchanged |
| own deck | [21 — the agent's position in the SPEC distribution](reports/21_agent_position_in_spec_distribution.md) | Ranks not ratios: L1I p77, MITE p65, DSB p27 — the agent is in SPEC's tail; only kernel time leaves the suite (p96) |
| — (feeds the P7 selection) | [22 — type identification over SWE-bench Multilingual](reports/22_multiling_typeid_sweep.md) | 285 classification-only live episodes, zero failures: behaviour collapses to search-led (E/B lead 0), PHP/Ruby carry the only co-dominant structure, magnitude nests by mechanism — the measured frame for the ≤30 P7 representatives |

Companion material elsewhere in the repo:

- [`handwritten_notes/`](handwritten_notes/) — the running working notes: `analysis.md` (the
  prose analysis, Parts 1–7), `reproduce.md`, `metrics.md`, `further_check.md`.
- `../local_agents/kit/events.md` — every perf event the kit measures, the derived
  metric each feeds, and the exact formulas.
- `../local_agents/kit/README.md` — the campaign kit itself (stages, knobs, fences).

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
