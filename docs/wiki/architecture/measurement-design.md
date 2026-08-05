# Agent measurement design

| Field | Value |
|---|---|
| Owner | LLM maintained, human reviewed |
| Status | Validated |
| Last updated | 2026-07-29 |
| Sources | [CLAUDE.md](../../../CLAUDE.md), [run_glm_campaign.sh](../../../local_agents/scripts/glm/run_glm_campaign.sh), [validate_glm_agents.py](../../../local_agents/scripts/glm/validate_glm_agents.py) |

## Purpose

This is the part of InferSuite that takes longest to reconstruct from code alone: how the CPU work
of an agent episode is partitioned into measured slices, and which instruments observe each slice.
It answers "what does the CPU do DURING inference vs OUTSIDE inference" for the agentic workloads.

## Fences are cgroups

The measured slices ("fences") are Linux cgroups, not process-name filters (*Decision*, see
[lineage fencing](../decisions/lineage-fork-exec-fencing.md)).

- **SWE-agent.** A Python harness process on the host is one measured slice; every tool action runs
  inside a per-task **docker sandbox container** (a second measured slice); a **litellm proxy**
  relays model calls to the GLM API and runs on the **housekeeping** cores (user slice), *outside*
  the measured partition.
- **OpenClaw.** ONE container holds the Node gateway and every tool it spawns — no container
  boundary exists. `oc_lineage_watcher.py` splits **agent** vs **toolexec** sub-cgroups by process
  lineage via the kernel's netlink proc connector: a fork by the gateway stays agent-side; the
  moment it `exec`s a program it becomes a tool root (name-blind; cgroup inheritance carries all
  descendants).

*Limitation.* litellm on the housekeeping cores means measured-partition capacity claims are
tool + harness only. Kernel threads belong to no cgroup, so fence totals are lower bounds.

## Four instruments run simultaneously per episode

1. **10 Hz cgroup `cpu.stat` pollers** (one per fence) — exact, always-on kernel accounting. Behind
   every core-second / timeline / burst figure.
2. **Windowed `perf stat` counting** — 8 groups of ~6 events, ONE group per window, **zero
   multiplexing**, **shuffled** rotation each cycle, episode-sum ratios
   (*Decision*, see [zero-mux rotation](../decisions/zero-mux-windowed-rotation.md)).
3. **Continuous whole-episode TMA L1/L2** — from the dedicated **PERF_METRICS** hardware (zero GP
   counters), so it coexists with the windowed groups without contention.
4. **99 Hz cgroup-scoped `perf record`** — statistical, used only for what-program / symbol / CPU
   attribution, **never** for rates.

A fifth **partition-wide `/proc/stat` poller** (the *residual witness*) banks everything on the
partition so validator gate **E11** can bound unfenced kernel work.

## From raw counters to a trusted figure

```text
plot_spec.json           (names the featured runs per campaign)
  -> plotters            (plot_glm_results.py -> values_dump.json: every displayed number)
  -> audit_plots.py      (independently recomputes each plotted number from raw; must say ALL MATCH)
  -> sync_plots.sh       (curated top-level plots/ view)
  -> (only after chat approval) thesis figure/ tree
```

Validation is proof-based: gates **E1–E11** in `validate_glm_agents.py` plus the figure audit. An
"OK" line is not proof — a run is trusted only on observed evidence plus an independent cross-check
(two subsystems agreeing). See [measurement ontology](../concepts/measurement-ontology.md) for the
vocabulary and [perf & TMA conventions](../profiling/perf-tma-conventions.md) for collection rules.

## Related pages

- [Service data path](service-data-path.md) — the non-agent (service) subject.
- [Median run, never pooled](../decisions/median-run-not-pooled.md) — how runs are aggregated.
- Study reports applying this design: [`docs/reports/`](../../reports/README.md).
