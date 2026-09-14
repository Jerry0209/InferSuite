# Session 2026-09-14 — Self-sufficient isolation, readable glyphs, and the JVM server suites

**Goal:** (1) make the measurement isolation independent of the co-tenant's setup, because he
will release the cores he holds; prove it works; re-check the two DCPerf captures. (2) Make
medians and means readable in the per-window figures. (3) Profile the mentor's "easier and
simpler server benchmarks" — Renaissance (finagle-http, finagle-chirper, page-rank,
naive-bayes, neo4j-analytics) and DaCapo Chopin (cassandra, tomcat, kafka) — with the same
isolation, method and figures as DCPerf. Mentor's rule: whatever works on first shot.
**Machine state at start:** P7 idle, branch `dcperf`, 24 CPUs online, powersave, housekeeping
partition `0-3,12-15` (restored by hand on 2026-09-10), co-tenant units
`agentic-benchmark-{host-policy,runtime-controls}` active, workqueue mask `0x3003`, disk 36 GB.

## Decisions
| # | Decision | Why | Made by |
|---|---|---|---|
| 1 | The shield owns every knob it used to inherit: effective-cpuset snapshot (with an `UNRESTRICTED` marker restored to *possible* CPUs), unbound workqueue cpumask, `init.scope`, explicit clock pin `scaling_min=max=base_frequency` on measured cores; ISO-PROOF verifies each and scans for foreign resident tasks; SMT siblings offlined/restored by the orchestrator | the housekeeping partition, the `0x3003` workqueue mask and the IRQ affinity were the co-tenant's boot entry and runtime writes; the live clock policy showed his unit does **not** pin `scaling_min_freq` (800 MHz) — the 3.2 GHz was held only by `performance`+`no_turbo`. None of that survives his release | user asked; Claude designed |
| 2 | The two DCPerf captures **stand**; no re-profiling | ISO-PROOF passed every pass, D5 witness residual ≤ 2.5 % / 2.7 %, the borrowed knobs were provably in place throughout, and a recheck pass under the hardened shield reproduces FeedSim (IPC −0.4 %, load +1 %, SLA identical) | Claude |
| 3 | Inner glyph switched to white IQR box / black median bar / white diamond mean (`paper_inner_box`) in the per-window figures | the thick black IQR bar hid its tiny white median square in 40-column panels; matches Jef's figures as the PI asked | user |
| 4 | Renaissance and DaCapo run as ONE JVM = ONE fence, no client to relocate | both suites run the embedded server and its clients in-process; that is what makes them "easier" | Claude |
| 5 | Steady state for JVM workloads = fence busy ≥ 1 core for 8 s, then a 45 s JIT hold; validator D4 checks drift afterwards | JVM start + JIT warm-up is a variable ramp; the poller-based check is what the video module already used | Claude |
| 6 | One orchestrator for all suites (`SUITE`/`WORKLOAD`), one exporter (`--suite`), multi-suite figure scripts (`*_ext.R`) with a marker per benchmark grouped by suite | same code path = same method; one column per external benchmark would make the compact grid unreadable at 10+ benchmarks | Claude |

## What changed
- `local_agents/kit/campaign/run_glm_campaign.sh`: hardened shield (see decision 1);
  `isolation-test` verifies the new knobs. **Verified**: stage passed, every knob restored
  bit-for-bit (`wq 003003, irq 00f00f, slices 0-3,12-15, init 0-23, powersave, no_turbo 0`).
- `local_agents/kit/dcperf/run_dcperf_profile.sh`: `SUITE`/`WORKLOAD`, start-time foreign-perf
  guard, automatic SMT offline + trap restore. Modules `bench_jvm_common.sh`,
  `bench_renaissance.sh`, `bench_dacapo.sh`; `sweep_jvm_suites.sh` runs the whole list.
- `export_dcperf_rows.py --suite/--label/--data`, `derive_dcperf.sh` honours `SUITE`/`DATA`;
  `plot_paper_agg_compact_ext.R`, `plot_paper_agg_groups_ext.R` (multi-suite figures).
- `theme_paper.R`: `paper_inner_box`; DCPerf chart pack `v3_2026-09-14_glyph`.
- Wiki: isolation runbook + hardening page updated, log entry added.
- Study doc: `local_agents/DCPerf/README.md` §8 (what/why/evidence/verdict).
- Infra (outside repo): `~/jvmbench-infra/` — `renaissance-gpl-0.16.1.jar` (438 MB) and
  `dacapo-23.11-MR2-chopin.jar` + its data tree (14 GB; only cassandra/tomcat/kafka needed).

## Traps hit
- The co-tenant's unit was documented (from its config) as pinning the measured cores'
  `scaling_{min,max}_freq`; the live state disagrees (`min=800000`). Read state, not config.
- `du` on the 6.3 GB DaCapo zip + 14 GB extraction dropped disk to 15 GB; the zip is deleted.

## Machine state left
JVM SWEEP STATUS PLACEHOLDER

## Open / next
- Renaissance + DaCapo sweep outcomes and the multi-suite figures: see the end of this log.
- The four blocked DCPerf benchmarks are unchanged (container route documented).
