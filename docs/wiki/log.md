# Wiki log

## [2026-09-21] observation | Suite server benchmarks measure their toy datasets, not the software

Five server benchmarks re-profiled on realistic datasets with the same instrument
(`local_agents/RealData/README.md`). Data-bound workloads (Cassandra, PageRank, Naive Bayes)
moved on the memory axes — Naive Bayes on RCV1: L1D misses 25×, LLC 43×, DRAM 26 GB/s, IPC
3.27 → 1.40 — while serving workloads run as real servers with clients outside the fence
(Neo4j, Kafka) moved on the front end and the OS (Neo4j branch MPKI 4×, BTB 36×, context
switches 28×; Kafka L1I 3×, switches 5×) and got lighter on memory. The realistic Server set
sits further from the agentic profile than the suite set on every axis; the agentic family's
single distinctive axis (branch-direction misprediction) is unchanged. Rule for this project:
a suite benchmark's memory-side signature is a property of its dataset size; do not read it as
a property of the software.

## [2026-09-20] observation | Server-benchmark data footprints are cache-sized except FeedSim

Measured live-heap-after-GC / cgroup peak for the ten server benchmarks
(`local_agents/kit/dcperf/measure_footprint.sh`): FeedSim 3.5 GB resident; the JVM servers
20–190 MB (finagle-http 20, tomcat 20, chirper 30, neo4j 110, cassandra 160 on 10 MB of rows,
kafka 190); Spark jobs 0.3–1.8 GB on tiny or replicated inputs; video = 2 s 1080p shots. The
memory side of the JVM-server signature therefore reflects dataset size, not the software; the
instruction-side signature does not scale with data. Re-characterisation plan in
`local_agents/JVMbench/README.md` §10.

## [2026-09-15] decision | Per-workload statistic = the metric over the workload's whole runtime

Mentor's rule for every workload-level violin: one value per workload, computed by summing the
raw counters over the workload's entire measured runtime and taking the ratio once (IPC = total
instructions / total cycles), with co-counted denominators. Not the median of per-window values
(equal weight to busy and idle windows, loses between-window information), not a pool of windows
(weights workloads by runtime). Implemented for all four families by
[export_runtime_votes.py](../../local_agents/kit/plot/export_runtime_votes.py) on top of the SPEC
comparison kit's loader; the multi-suite figures follow it (`VOTE=runtime`). Consequence:
busy-weighted values (cassandra branch MPKI 1.7 vs 3.3 under medians; SPEC context switches
4.5/CPU-s vs 0). The single-axis agentic finding (branch-direction misprediction) holds under
both rules. Source: `local_agents/JVMbench/README.md` §9.

## [2026-09-14] update | A duty-cycled workload broke the steady-state gate (median vs mean)

`validate_dcperf.py` gate D4 compared per-sample MEDIANS of the 10 Hz fence-load series and
normalised by the first fifth's value. DaCapo `cassandra` is ~50 % idle at 100 ms granularity, so
its median was 0.03 cores and a 0.01 → 0.65 core difference read as 4 627 % drift; the benchmark
was wrongly excluded from every multi-suite figure. Rewritten to smooth to 10 s, compare means,
normalise by the larger side, and add an absolute idle floor; verified against synthetic
steady / duty-cycled / dying / decaying / idle / ramping series. Generalisable rule for this
project: **a relative drift test needs an absolute floor, and a median measures duty cycle, not
drift.** Consequence for findings: with cassandra reinstated the agentic family is no longer the
lowest-DRAM workload, and the surviving distinction is single-axis (highest branch-direction
misprediction). Source: `local_agents/JVMbench/README.md` §8.

## [2026-09-14] update | Applied clock vs realised clock (C-state ramp on wake-heavy workloads)

Added an Observation to the [isolation setup runbook](operations/isolation-setup-runbook.md)
Step 3: the realised unhalted clock measured from the banked `priv` counters
([realised_clock.py](../../local_agents/kit/validate/realised_clock.py)) equals the 3.2 GHz
pin (3.18–3.19) for SPEC, DCPerf and compute-bound JVM benchmarks, but drops to 2.6–2.9 GHz
for wake-heavy JVM servers and correlates with the per-window context-switch rate — the
uncontrolled C-states, not a DVFS fault. Plotted metrics are unaffected; throughput claims must
use the realised clock. Source: `local_agents/DCPerf/README.md` §9.

## [2026-09-14] update | Isolation shield made self-sufficient

Updated [isolation setup runbook](operations/isolation-setup-runbook.md) and
[isolation & hardening](operations/isolation-hardening.md): the runtime shield in
[run_glm_campaign.sh](../../local_agents/kit/campaign/run_glm_campaign.sh) now owns every knob it
used to inherit from the co-tenant stack (housekeeping partition via effective-cpuset snapshot,
unbound workqueue cpumask, `init.scope`, fixed clock on the measured cores), ISO-PROOF verifies
them and scans for foreign resident tasks, and the DCPerf orchestrator offlines/restores SMT
siblings itself. Motivation: the co-tenant will release the cores. Verified by the
`isolation-test` stage on 2026-09-14 (all knobs restored bit-for-bit).

## [2026-08-05] ingest | Isolation setup runbook — SMT, DVFS, core isolation

Added [isolation setup runbook](operations/isolation-setup-runbook.md), the procedural companion to
the existing conceptual [isolation & hardening](operations/isolation-hardening.md) page. Compiled
from the two campaign kits' `apply_isolation()`/`restore_isolation()`
([run_glm_campaign.sh](../../local_agents/kit/campaign/run_glm_campaign.sh) and the SPEC CPU 2026
sibling kit at `~/spec26-infra/infra/scripts/run_spec_campaign.sh`),
[harden_isolation.sh](../../scripts/harden_isolation.sh), and live w5-3425 state read on this date.

Three layers documented in application order — GRUB cmdline, per-boot SMT/DVFS, per-campaign
runtime shield — each with verification commands and a teardown. Records the full table of files
modified at each layer.

Facts worth flagging that this compile surfaced: SMT is off on the measured cores by **offlining
siblings 16-23**, not via `smt/control` or BIOS, so `lscpu` and `/sys/devices/system/cpu/smt/control`
both still report SMT on — only a per-core `thread_siblings_list` check is honest, which is why the
kits bank `smt` and `smt_host` separately in `metadata.json`. Governor alone does not pin frequency
on this HWP part; `scaling_min_freq == scaling_max_freq` is required. Layers 1-2 on the current host
are owned by a co-tenant `agentic-benchmark` systemd stack, whose apply script is not readable — the
resulting state is confirmed, the mechanism is inferred from its world-readable profile config.
C-states remain uncontrolled (`intel_idle`, C1/C1E/C6 all enabled), logged as a limitation.

## [2026-07-29] ingest | Instantiate the LLM Wiki for InferSuite

Adopted the [LLM Wiki framework](../raw/llm-wiki.md) as the governing knowledge-base pattern,
mimicking the `docs/` organization of `JekxDevil/agentic-benchmark` (branch `feat/runtime`). Created
the three layers: `docs/raw/` (governing framework + [SHA256SUMS](../raw/SHA256SUMS), checksum
verified byte-for-byte against the template repo), `docs/wiki/` (this tree), and reused the existing
`docs/reports/` as the generated study-output layer. Wrote the [schema](schema.md), this log, and
the [index](index.md). Nothing existing was moved; `docs/reports/` and the two skills are unchanged.

## [2026-07-29] decision | Wiki is additive, CLAUDE.md stays canonical

Chose the additive instantiation: `docs/reports/` study reports keep their location and their
`study-report` + `report-check-commit` machinery; the wiki holds only cross-cutting knowledge
(ontology, architecture, decisions, profiling, operations). `CLAUDE.md` remains the canonical schema
— no competing `AGENTS.md` was added — and it now carries a short pointer to the wiki. Adopted the
template's status vocabulary (Proposed/Approved/Implemented/Validated/Superseded) and evidence
language (Fact/Decision/Hypothesis/Observation/Inference/Limitation).

## [2026-07-29] ingest | Seed core pages from existing repo knowledge

Compiled six knowledge pages from `CLAUDE.md`, `docs/handwritten_notes/analysis.md`, and
`local_agents/scripts/glm/events.md` — no new research, just consolidation of scattered knowledge:
[measurement ontology](concepts/measurement-ontology.md),
[agent measurement design](architecture/measurement-design.md),
[service data path](architecture/service-data-path.md),
[zero-mux rotation](decisions/zero-mux-windowed-rotation.md),
[lineage fencing](decisions/lineage-fork-exec-fencing.md),
[median run never pooled](decisions/median-run-not-pooled.md),
[perf & TMA conventions](profiling/perf-tma-conventions.md), and
[isolation & hardening](operations/isolation-hardening.md). Registered all in the index.

## [2026-08-04] update | Repo narrowed to SWE-agent profiling

At the user's request the service stack (`src/`, `deploy/`, `local_service/` incl. `data_iso`,
`benchmark_queries/`, `fastapi_runtime_assets/`, root deploy scripts), the GPU-side kit
(`agentic/inference/`), the banked OpenClaw campaign (`local_agents/OC_clean`), and the dead
EKS scripts were removed from the working tree — all fully committed beforehand, so every path
is recoverable from git history. Marked
[service data path](architecture/service-data-path.md) Historical and updated its source
links; `measure.sh`, `scripts/sync_plots.sh`, `CLAUDE.md`, and `docs/PLOTTING_GUIDE.md` were
updated in the same commit. The OpenClaw *harness* stays in tree (`agentic/openclaw/` — its
litellm venv is a hard dependency of the SWE campaign kit).

## [2026-08-04] update | litellm venv moved into the SWE kit; OpenClaw harness removed

Follow-up to the narrowing: the litellm proxy venv the SWE campaign launches (python 3.13.13,
litellm 1.89.4) moved from `agentic/openclaw/.venv_litellm` to
`local_agents/scripts/glm/.venv_litellm` (same bits — moved, shebangs/activate paths
rewritten; exact pins committed as `litellm_venv_freeze.txt`; `agents-swe preflight` passes).
With the dependency gone, `agentic/openclaw/` was removed (its `external/WildClawBench`
checkout was already absent, so no OC capture was runnable anyway); `measure.sh agents-oc` is
now a stub that explains the restore path. Method-update notes appended to reports
01–04/07–09/12.

## [2026-08-05] update | Kit reorganized into pipeline-stage subdirs; OC code paths removed

The measurement kit moved from the flat `local_agents/scripts/glm/` to `local_agents/kit/`
with four stage subdirs: `campaign/` (runner + config + litellm venv, rebuilt from the freeze
file), `replay/` (deterministic replays, per-window derivation, behaviour probes), `plot/`
(all plotters; the three `cmp_*` scripts merged into `cmp_allruns.py --view
{shares,absolute,tma}`), `validate/` (gates E1–E11 + figure audit). Basenames unchanged, so
bare-name citations still resolve; full-path citations updated across reports/wiki/guides.
The dead OpenClaw code paths left the tree (oc_episode + loop guard in the runner, both
watchers, three OC plotters, `my_api_glm.json`), along with `gen_manifest.py`,
`plot_thread_lanes.py`, and the pre-GLM `agentic/swe_agent` top-level scripts (GLM-era eval
evidence preserved in `agentic/swe_agent/evals/`). The frozen `glm_plots/` views moved to
`archive/glm_softiso_long_campaigns/glm_plots/`. Pages touched: measurement-design,
lineage-fork-exec-fencing (marked historical), zero-mux-windowed-rotation,
isolation-hardening, perf-tma-conventions.
