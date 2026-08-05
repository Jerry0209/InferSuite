# Decision: zero-multiplexing windowed rotation

| Field | Value |
|---|---|
| Owner | LLM maintained, human reviewed |
| Status | Validated |
| Last updated | 2026-08-05 |
| Sources | [CLAUDE.md](../../../CLAUDE.md), [run_glm_campaign.sh](../../../local_agents/kit/campaign/run_glm_campaign.sh), [windows.tsv](../../../local_agents/SWE_clean/data) |

## Context

PMU general-purpose counters are scarce. The naive way to count ~48 events is to let the kernel
**multiplex** them onto the available counters and scale by enabled time.

## Decision

Count in **windows**: 8 groups of ~6 events, **one group per window**, so every event in a group is
counted for 100% of that window's time — **zero multiplexing**. Rotate groups, **shuffle** the
order every cycle, and bank the realized order in `windows.tsv`. Ratios are episode sums, and every
ratio uses a **co-counted denominator** (instructions from the event's own windows).

## Alternatives rejected

- **Kernel multiplexing + scaling.** *Fact:* the scaling assumes the workload looks the same in
  every time slice. Agent workloads are bursty and phased; errors reach tens of percent. A dryrun
  gate requires every group to report 100% enabled time.
- **Fixed rotation order.** *Fact:* a fixed order phase-locks with the agent loop — systematic
  sampling without a random start biases which phases a group sees. Hence the per-cycle shuffle.
- **Cross-group denominators.** *Fact:* dividing one group's event by instructions summed over ALL
  groups' windows inflated denominators ~8×. Every ratio must be co-counted.

## Consequences

- Continuous TMA (PERF_METRICS MSR, zero GP counters) can run alongside without contention — see
  [agent measurement design](../architecture/measurement-design.md).
- A dedicated-group replay probe (`GORDER_OVERRIDE`) bounds rotation-sampling error against a
  continuous capture.
- *Limitation:* rotation still samples phases; the replay probe is how that residual is quantified.

## Related pages

- [Perf & TMA conventions](../profiling/perf-tma-conventions.md)
- [Measurement ontology](../concepts/measurement-ontology.md) (window, episode-sum ratio)
