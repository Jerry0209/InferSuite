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
**Restored to baseline by the kit itself** after the last pass (checked 11:25): 24 CPUs online,
`powersave`, `no_turbo=0`, clock policy `800000-3200000`, `system.slice`/`user.slice`
`0-3,12-15`, `init.scope` `0-23`, workqueue mask `003003`, IRQ default `00f00f`, no `perf`, no
`iso_applied` flag. Disk 30 GB free (DaCapo data tree pruned to the three used benchmarks).

## JVM sweep outcome (05:33–11:20, ~5 h 50 min)
| Benchmark | Passes | Validation | Note |
|---|---|---|---|
| renaissance/finagle-http | 9/9 | PASS | 6.7 cores; ctx 41 000/CPU-s, L1I 52.7 MPKI, DSB coverage 13% |
| renaissance/finagle-chirper | 9/9 | PASS | 6.5 cores |
| renaissance/page-rank | 9/9 | PASS | 3.0 cores; Spark, compute-dense |
| renaissance/naive-bayes | 9/9 | PASS | 7.6 cores; IPC 3.6, the highest measured |
| renaissance/neo4j-analytics | 9/9 | PASS | 2.1 cores |
| dacapo/cassandra | 9/9 | PASS (after the gate fix) | first reported FAIL D4 and excluded; the gate was wrong, not the run — see the addendum below |
| dacapo/tomcat | 9/9 | PASS | 0.9 cores; ctx 37 000/CPU-s |
| dacapo/kafka | 9/9 | PASS | 0.5 cores; **D5 residual 17.8%** (loopback softirq is unfenced kernel work) — lower bound |

Findings (full text in `local_agents/JVMbench/README.md` §3, addendum in `DCPerf/README.md`
§4): JIT-compiled servers are the instruction-supply and context-switch extremes, not the
agent; what remains distinctive of the agentic 36 across all twelve workloads is the highest
branch-*direction* misprediction (3.60 MPKI) and **that alone** — a prediction pathology, versus
the servers' capacity pathology. (Revised in the second addendum: the companion "lowest memory
traffic" claim was an artifact of cassandra's wrongful exclusion.)

## Open / next
- Renaissance + DaCapo sweep outcomes and the multi-suite figures: see the end of this log.
- The four blocked DCPerf benchmarks are unchanged (container route documented).

## Addendum (later on 2026-09-14): the isolation, written down per capture; applied vs realised clock
- PI asked for the exact isolation — cores, SMT, clock — in the write-ups. Added
  `local_agents/DCPerf/README.md` §9 (full table with an evidence column) and
  `local_agents/JVMbench/README.md` §6 (same configuration, JVM numbers), with pointers from
  each README's method section. Every value was read back from the machine or the banked data.
- New evidence used: the `/proc/stat` witness in every run directory lists `cpu0`–`cpu15` only,
  which proves from the data that the SMT siblings 16–23 were offline during the 2026-09-10
  DCPerf captures (then a manual, gate-verified step) as well as the 2026-09-14 ones.
- New tool `local_agents/kit/validate/realised_clock.py`: unhalted cycles per fence
  CPU-second from the `priv` pass. Result: SPEC (26), DCPerf (2) and the compute-bound JVM
  benchmarks realise 3.18–3.19 GHz on both capture days (so the 09-10 passes without the
  explicit min = max write ran at the same clock); wake-heavy servers realise less (tomcat 2.81,
  cassandra 2.63, finagle-http 2.91; the agentic rubocop task 2.88) and the window clock falls
  with the window's switch rate (Spearman −0.75 to −0.99). Inference: post-idle ramp
  (C-states are not restricted in any capture). Plotted metrics unaffected; noted as a rule for
  throughput claims; C-state restriction NOT applied (would break comparability) — mentor call.
- The 2026-09-14 FeedSim recheck run was in the session scratchpad; copied to
  `local_agents/DCPerf/data/recheck_2026-09-14/` (gitignored data tree) so §8's evidence
  survives the session.
- Reviewer question (mentor, via chat): are all metrics aggregated the same way? Answer from
  the code: yes for fig01 — every metric is a per-window value, one vote per workload (median
  of its windows; SPEC enters as one window-median per benchmark), violin over workloads. In
  fig02–05 every agentic/DCPerf/JVM column is one workload's windows, while the two SPEC
  columns are distributions over benchmark medians (14 / 12). The two pack READMEs and
  `DCPerf/README.md` §5 said "every column is a distribution over windows" — corrected.
- ISO-PROOF bookkeeping over the whole DCPerf/JVM period (campaign.log from the first FeedSim
  profiling shield): 98 shield applications, 0 failures; one shield (05:08, before the recheck) needed five
  quiet samples, worst passing sample 2.0 %; all other samples ≤ 1 %.

## Addendum 2 (evening 2026-09-14): cassandra was never broken — the steady-state gate was
- PI asked what was actually wrong with cassandra. Re-reading the evidence: nothing.
- **Gate defect.** D4 took the MEDIAN of the 10 Hz load samples over the first and last fifth of
  a capture and divided by the first. Cassandra is duty-cycled at 100 ms granularity (~4 cores or
  idle, about half the samples idle), so its median is 0.03 cores and a 0.01 → 0.65 core
  difference read as 4 627 % drift. Its 10 s means were flat at ~2 cores for the whole capture.
  Two mistakes: a median measures duty cycle, not drift; and a percentage of a near-zero
  denominator is meaningless.
- **The NPE flood was teardown.** First client error lands 0.3 s AFTER the last capture window
  closes, in all nine passes, each at its own end time — our `systemctl stop` of the scope. No
  window contains post-failure data. Every pass did 27 iterations at 34 400–34 900 req/s; the
  earlier 40-iteration smoke run completed clean at 36 400 req/s.
- **Fix** in `kit/dcperf/validate_dcperf.py`: 10 s smoothing, compare MEANS, normalise by the
  larger side (bounded at 100 %), plus an absolute idle floor of 0.10 cores. Validated against
  six synthetic series (steady and duty-cycled PASS; dies-halfway, decaying, idle and ramping
  FAIL). All ten captures pass; cassandra's worst drift 10.5 %, mean load 1.93 cores.
- **Consequences.** Cassandra reinstated in every figure; chart pack
  `v2_2026-09-14_cassandra-reinstated`. It is the front-end extreme of the study (L1I 70.8 MPKI,
  DSB 11 %, IPC 0.91) and the context-switch extreme (49 000/CPU-s). Its DRAM read of
  0.0185 GB/s **retired the "agentic = lowest memory traffic" half** of the previous finding;
  the agentic family ranks 11th of 12 on DRAM. The surviving claim is single-axis: highest
  branch-direction misprediction, 3.60 MPKI, first of 12, everything else 5th–11th.
- Lesson worth keeping: a relative test needs an absolute floor, and a robust statistic (the
  median) can still be the wrong statistic for the question.
