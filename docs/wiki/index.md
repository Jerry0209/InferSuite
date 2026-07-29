# InferSuite wiki

| Field | Value |
|---|---|
| Owner | LLM maintained, human reviewed |
| Status | Active |
| Last updated | 2026-07-29 |
| Schema | [Wiki schema](schema.md) |

The persistent, compounding knowledge base for InferSuite. Cross-cutting knowledge lives here;
per-study methodology lives in [`docs/reports/`](../reports/README.md); the durable rules and the
"issues we ran into" list live in [`CLAUDE.md`](../../CLAUDE.md). Start with the ontology, then the
architecture, then the decisions that shaped it.

## Start here

1. [Measurement ontology](concepts/measurement-ontology.md): stable names for campaign, episode,
   fence, burst, call, window — and the locked meaning of "CPU usage (cores)".

2. [Agent measurement design](architecture/measurement-design.md): fences-are-cgroups and the four
   instruments that run simultaneously per episode.

3. [Service data path](architecture/service-data-path.md): the RAG + semantic-cache + vLLM request
   path, and which stages the CPU measurements attribute.

## Decisions

1. [Zero-multiplexing windowed rotation](decisions/zero-mux-windowed-rotation.md): why counting is
   windowed, shuffled, and co-counted rather than kernel-multiplexed.

2. [Lineage fork/exec fencing](decisions/lineage-fork-exec-fencing.md): why OpenClaw fences are
   split by process lineage, not process name.

3. [Median run per cell, never pooled](decisions/median-run-not-pooled.md): why figures use the
   median run with documented spread instead of pooling attempts.

## Profiling

1. [Perf & TMA conventions](profiling/perf-tma-conventions.md): the perf binary, cgroup scoping,
   continuous TMA, the high-IPC-is-not-work caution, and the GPU prefill caveat.

## Operations

1. [Isolation & hardening](operations/isolation-hardening.md): nohz_full (never isolcpus), runtime
   cpuset split, and the ISO-PROOF silence gate.

## Studies (per-study methodology)

The reproducibility study reports are indexed separately and written by the
[`study-report`](../../.claude/skills/study-report/SKILL.md) skill:
[`docs/reports/`](../reports/README.md) — one report per study of the team deck.

## Maintenance

1. [Wiki schema](schema.md): the operating rules — three layers, page conventions, ingest/query/lint,
   and evidence language.

2. [Wiki log](log.md): append-only history of ingests, decisions, and lint passes.
