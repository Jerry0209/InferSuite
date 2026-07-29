# Measurement ontology

| Field | Value |
|---|---|
| Owner | LLM maintained, human reviewed |
| Status | Implemented |
| Last updated | 2026-07-29 |
| Sources | [CLAUDE.md](../../../CLAUDE.md), [analysis.md](../../handwritten_notes/analysis.md), [Intel TMA](https://www.intel.com/content/www/us/en/docs/vtune-profiler/cookbook/current/top-down-microarchitecture-analysis-method.html) |

## Purpose

The ontology gives stable names to the things InferSuite measures, so that a *call*, a *burst*, a
*fence*, a *window*, and an *episode* are never treated as interchangeable. It also fixes the
meaning of the one phrase every figure depends on — "CPU usage (cores)".

## Core relationships

```text
Campaign  (SWE_clean | OC_clean | service_iso)
  -> Episode            one task run (SWE instance / OC task / service tier-recording)
       -> Fence         a measured cgroup slice: harness | tool | litellm(*)
       -> Instrument x4 run simultaneously per episode (see measurement design)
       -> Turn          agent step (SWE: from harness activations, validated vs step count;
                         OC: from transcript per-message timestamps, NOT harness activity)

Fence
  -> Burst              contiguous fence CPU above a detection floor
       -> heavy         burst classification (peak > 0.3 cores)
  -> Call               an action in the agent's log (maps to bursts, not 1:1)

Instrument
  -> cpu.stat poller    10 Hz, exact kernel accounting  -> core-seconds, timelines, bursts
  -> windowed perf stat 8 groups, one per window, zero-mux, shuffled -> episode-sum ratios
  -> continuous TMA     PERF_METRICS MSR, whole episode  -> TMA L1/L2
  -> perf record        99 Hz cgroup-scoped -> what program/symbol/CPU (never rates)
  -> partition witness  /proc/stat, partition-wide       -> residual bound (gate E11)
```

(*) The litellm proxy runs on the **housekeeping** cores, not the measured partition — see
[measurement design](../architecture/measurement-design.md). Measured-partition capacity claims are
tool + harness only.

## Entity definitions

| Entity | Identity | Meaning |
|---|---|---|
| Campaign | Campaign name + data dir | A hardened capture matrix. Thesis scope: `SWE_clean`, `OC_clean` (agents, GLM under nohz_full), `service_iso` (36-cell k3s service). |
| Episode | Run dir (`glm_swe_*/run_N`) | One task executed once under one configuration. |
| Fence | cgroup path | A measured CPU slice. SWE: host harness process + per-task docker sandbox. OC: agent vs toolexec sub-cgroups split by process lineage. |
| Turn | Ordinal step | An agent step. Derivation differs per harness (see relationships) — a locked lesson, not a detail. |
| Call | Action in the agent log | One logged action. Maps onto bursts but not one-to-one. |
| Burst | Contiguous fence CPU run | Fence CPU above a tiny floor (tool 0.005 / harness 0.02 cores), gaps < 0.4 s merged. |
| Window | perf-stat window | One time slice counting exactly one event group (zero multiplexing). |

## Vocabulary (locked)

| Term | Definition |
|---|---|
| **CPU usage (cores)** | An occupancy rate in core-equivalents (spin included): core-seconds per second. Exact *average* concurrency; a **lower bound** on peak concurrency; **silent on distinct cores** (the per-CPU lanes data answers that). |
| **core** | A logical CPU (hardware thread). The workstation (w5-3425) has 12 physical P-cores × 2 SMT = 24 logical CPUs (0–23). Measured partition = 10 physical / 20 logical; housekeeping = 2 physical / 4 logical. |
| **OS share** | The kernel/privileged share of CPU time. Say "OS share", never bare "kernel". |
| **heavy** | A burst whose peak exceeds 0.3 cores. |
| **amounts vs shares** | Amounts are in **core-seconds**; shares are **% of CPU time**. No bare "CPUs"/"CPU-s" axis labels. |

## Cross-figure conventions

Colors carry meaning across every figure: **whitish grey = GPU / model wait**, **green = tool
fence**, **purple = harness**, **orange = litellm proxy**. On-figure titles are short; definitions
live in MANIFESTs and here, not in figure footers.

## Evidence-level cautions

- *Fact.* The engine's ~2 busy cores are a CUDA busy-wait, not work: IPC ~3.6, ~99% uop-cache,
  zero FP, ~85% of samples in event-sync/time-polling; the idle control drops to ~0.02 cores.
  **Inference forbidden:** high IPC/retiring does **not** certify useful work anywhere in this study.
- *Limitation.* Kernel threads (writeback/irq) belong to no cgroup, so fence totals are **lower
  bounds**; the partition witness + gate E11 bound that residual on new runs.

## Related pages

- [Measurement design](../architecture/measurement-design.md) — the four instruments and the fences.
- [Perf & TMA conventions](../profiling/perf-tma-conventions.md) — how the counters are collected.
- Decisions that turn on this vocabulary:
  [zero-mux rotation](../decisions/zero-mux-windowed-rotation.md),
  [lineage fencing](../decisions/lineage-fork-exec-fencing.md),
  [median run, never pooled](../decisions/median-run-not-pooled.md).
