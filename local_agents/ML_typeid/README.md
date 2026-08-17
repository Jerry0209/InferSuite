# ML_typeid — first-live-run type identification over SWE-bench Multilingual

**Branch `multiling-type-id`, started 2026-08-10.** One cheap live episode per remaining
Multilingual instance (285 of 300 — the other 15 were consumed by the earlier campaigns and
probes), run on the local machine (`bz-network-ws02`, i7-14700 hybrid, 28 logical CPUs), to
classify every task and pick ≤30 ⟨language, type⟩ representatives for real profiling on the
P7 workstation. **Nothing captured here is a rate measurement**; this campaign buys labels.

Prior art this builds on (read first): `../ML_multiling/sampling_frame/` — the static
taxonomy (mechanism = a total function of repo, hence of language), the behavioural
classifier, and the July verdicts: realized behaviour collapsed to search-led on all 16
measured episodes (static priors 1/10), and magnitude has no static signal (5.33× seed
noise). This sweep turns those 16-episode claims into ~285-episode measurements and buys
the realized magnitude/viability data the frame explicitly lacks.

## Why no isolation on this machine — recorded reasoning

The P7 stack (nohz_full, cpuset shield, ISO-PROOF, zero-mux perf, TMA) exists to make
counter *rates* valid. This campaign collects no counters. What must be exact — fence
*attribution* — comes from cgroup membership, and `cpu.stat` accounting is exact kernel
bookkeeping on any CPU under any contention. Magnitudes are used only as coarse bins and
get re-judged by the P7 layer-3 stop gate (`taxonomy_spec.json` STEP 5) before any
profiling minutes are spent. The one machine effect that could matter is *behavioural*
(slower machine → command timeouts → different action mix): the frozen SWE-agent config is
identical, and episodes are flagged if drain/timeout fires. Do NOT reuse P7 partition
configs here; the TYPEID mode neutralizes them (taskset to the full online range).

## Instruments per episode (TYPEID light mode, `run_glm_campaign.sh typeid-one`)

| stream | file | what it is |
|---|---|---|
| trajectory | `traj/<inst>/<inst>.traj` | SWE-agent's own log: actions, observations, `info.model_stats`, exit status |
| harness/tool/proxy fences | `cpustat_scope{1,2,3}.tsv` | 10 Hz `cpu.stat` (exact kernel accounting; scope2 = task container = tool fence) |
| process witness | `cmdlog.tsv` | 2 Hz argv of the tool cgroup (`epoch\tpid\targv`) — a witness of *what ran*, never a rate |
| token usage | `proxy_usage.jsonl` | one JSONL row per model call from the litellm callback (`usage_logger.py`), host epoch clock |
| harness log | `agent.log` | liveness, STEP markers, loop-guard input |
| derived | `episode_summary.json`, `tokens_steps.tsv` | written by `typeid_classify.py episode` |

`DONE` requires traj + tool cpustat + cmdlog (`typeid_episode_ok`) — a lesson from the
workstation migration that silently lost two banked `.traj` files. Sync data off this
machine with `rsync -c`.

## The classification record (per task)

- **mechanism** — B/A/J/I/N, static repo lookup (from `task_inventory.csv`), plus a
  *witness*: fraction of cmdlog ticks showing the language's toolchain processes
  (`mechanism-not-witnessed` flag = the gin failure mode: class A, warm cache, no compile).
- **realized behaviour** — S/E/T/B/M via `behavior_classify.py` rules imported unchanged
  (10-point MARGIN, view=S). `support` = classified-action count; low support flags the label.
- **magnitude bin** — tool-fence core-s, bootstrap-corrected (apt/dpkg lineage interval in
  the first 300 s subtracted — 15% of gin's fence was image setup). Bins `below-floor` (<10),
  `measurable`, `large` (>60) are **PROVISIONAL this-machine values** (`TYPEID_FLOOR`/
  `TYPEID_LARGE`); calibrate by re-running 2–3 banked instances here and comparing to their
  P7 fences before quoting any bin in prose.
- **viability flags** — E7 mirrors (longest identical-action run ≥12; unique fraction <40%),
  starvation (steps <5 or zero received tokens), drain, call/step mismatch.

Everything lands in `typing_ledger.tsv` (append-only, one row per attempt) and the
per-episode `episode_summary.json`.

## Running it

```bash
./measure.sh typeid preflight          # env checks, no spend
./measure.sh typeid one <instance_id>  # one episode
./measure.sh typeid sweep              # the resumable sweep (LIMIT=n for a bounded batch)
./measure.sh typeid matrix             # <language, realized-type> matrix + progress
touch local_agents/ML_typeid/STOP      # clean stop between episodes
```

Sweep behaviour (`typeid_sweep.sh`): language-interleaved order (matrix fills evenly),
image pull with 3 retries, image removed after each episode (`KEEP_IMAGES=1` to keep),
disk floor `MIN_FREE_GB=40` with swebench-image GC, **hard abort on two consecutive starved
episodes** (credit-exhaustion signature — check the GLM balance, don't debug the harness).
Logs: `sweep.log` + `logs/<short>.log`. Wall estimate: 15–25 min/episode ⇒ roughly 3–5
days serialized for ~285; API spend is the dominant cost.

## Selection of the ≤30 (after the sweep)

Credit cells by realized labels (`credits()` co-dominance). One representative per
populated ⟨language, realized-type⟩ cell; remaining slots per the sampling-frame logic:
second repo per language (language-level claims need ≥2 repos), within-repo scope-contrast
pairs, magnitude-spread coverage. Within a cell: median corrected fence, E7-clean,
`measurable`+ bin, witness present, prefer non-W-CONFOUND repos; record a runner-up. Every
pick is a **prior**: the P7 live episode + layer-3 gate is the verdict.

## Machine/bootstrap deviations (recorded, 2026-08-10)

- SWE-agent cloned at the banked hash `3ea751c0` (v1.1.0) with swe-rex 1.4.0; harness venv
  python **3.12.3** (old workstation version unrecorded).
- litellm venv rebuilt from `litellm_venv_freeze.txt` under python **3.13.15** (pin was
  3.13.13; patch-level drift).
- Proxy runs `litellm_glm_typeid.yaml` = certified config + `usage_logger` callback; the
  certified `litellm_glm.yaml` is untouched.
