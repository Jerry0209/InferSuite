# Perf & TMA conventions

| Field | Value |
|---|---|
| Owner | LLM maintained, human reviewed |
| Status | Validated |
| Last updated | 2026-08-05 |
| Sources | [CLAUDE.md](../../../CLAUDE.md), [events.md](../../../local_agents/kit/events.md), [Intel TMA](https://www.intel.com/content/www/us/en/docs/vtune-profiler/cookbook/current/top-down-microarchitecture-analysis-method.html) |

## Purpose

The load-bearing, easy-to-get-wrong rules for collecting perf counters and TMA on this workstation.
Violating any of these invalidates figures.

## The perf binary

*Fact.* The working binary is `$(ls -d /usr/lib/linux-tools-6.8*/perf | tail -1)` — **always glob**,
because package updates move it; `/usr/bin/perf` and the running-kernel symlink are broken. Local
perf needs `sudo` / `perf_event_paranoid=-1`. If counters read `<not counted>` or flaky, kill
orphaned root `perf -a` processes holding the PMU first.

## Cgroup scoping

*Fact.* Profile serving CPU with **whole-pod cgroup scope** (`perf -G` / `--for-each-cgroup`).
Process-scoped profiling misses the engine-core worker and reads ~idle. The agent fences are
cgroups for the same reason — see [agent measurement design](../architecture/measurement-design.md).

## TMA

Top-down Microarchitecture Analysis classifies every pipeline slot into four L1 buckets —
**Retiring, Bad Speculation, Frontend Bound, Backend Bound** — then drills to L2/L3. InferSuite reads
L1/L2 **continuously** from the dedicated **PERF_METRICS** MSR (zero general-purpose counters), which
is why it coexists with the windowed groups
(see [zero-mux rotation](../decisions/zero-mux-windowed-rotation.md)).

Rules:

- **Never pool runs** for TMA/signature figures — use the median run and document spread
  (see [median run, never pooled](../decisions/median-run-not-pooled.md)).
- *Inference forbidden:* high IPC / high Retiring does **not** certify useful work. The engine's
  busy-wait retires at IPC ~3.6 and looks pristine in Retiring while merely spinning.
- The L3 drill groups (`mem_bound`, `fe_l3x`, `fe_miss`) are **not** in the certified rotation —
  select them via `GORDER_OVERRIDE` on deterministic replays only.

## GPU profiling caveat

*Fact.* GPU prefill profiling requires `enable_prefix_caching=False` **and** a distinct warmup
prompt, or the measured "prefill" is a one-token cache hit and conclusions invert. GPU-TMA is
re-binned into Intel-style buckets from warp-scheduler issue slots (`agentic/inference/`).

## Plotting

*Fact.* Plot with the **system `python3`** (matplotlib is system-wide), not the project `.venv`.
Collection and plotting are decoupled: collection scripts only collect; plot afterwards from banked
data (`./measure.sh plots`).

## Related pages

- [Measurement ontology](../concepts/measurement-ontology.md) — what the counters mean.
- The counter-event reference [events.md](../../../local_agents/kit/events.md) — every
  group, where it is defined, and which figure metric it feeds.
