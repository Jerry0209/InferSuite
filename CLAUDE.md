# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

InferSuite: a Master's-thesis measurement suite that characterizes what the CPU does during
**agentic LLM workloads** — agent harness vs tool execution vs model wait — in wall-clock time
and CPU core-seconds, measured with cgroup fences, zero-mux perf counting, and continuous TMA.
The active subject is **SWE-agent x GLM-5.2 on SWE-bench (+ Multilingual)**.

**REPO NARROWED 2026-08-04** (user decision, this chat): the Service stack (`src/`, `deploy/`,
`local_service/` incl. `data_iso`, `benchmark_queries/`, `fastapi_runtime_assets/`, root
`setup.sh`/`deploy.sh`/`Dockerfile.service`), the GPU-side profiling (`agentic/inference/`),
the banked OpenClaw campaign (`local_agents/OC_clean`), the OpenClaw harness
(`agentic/openclaw`, removed in a follow-up the same day after relocating its litellm venv —
see below), and the dead EKS scripts were removed
from the working tree. **Everything is recoverable from git history** (`git log --follow`, or
`git checkout <pre-removal-commit> -- <path>`); the service/GPU study reports stay as frozen
snapshots of that work. A follow-up cleanup 2026-08-05 also deleted the frozen figure views
(`plots/{service,gpu,engine}`, `plots/agents/{oc_clean,h100,local,local_api}`), the dead
`results/` symlink tree, and the service-era `scripts/` (all verified on GitHub @ 8d87e0ee
first); `plots/` now holds only the live `agents/swe_clean` view and `scripts/` keeps only
`harden_isolation.sh`, `sync_plots.sh`, `draw_agent_pipeline.py`. Do not resurrect the removed
trees without the user asking.

**THESIS SCOPE:** the thesis uses ONLY the isolated campaigns — the hardened agent campaign
`local_agents/SWE_clean` (GLM-5.2 under nohz_full boot, ISO-PROOF gate, shuffled zero-mux
rotation, continuous TMA), plus the multilingual per-window extension in
`local_agents/ML_multiling` and the reproduced Python tasks in `local_agents/superseded_40min`
(both gitignored data — irreplaceable, never delete). The superseded soft-isolated campaigns
live at `archive/glm_softiso_long_campaigns/{SWE_long,OC_long}` (still read by the
cross-campaign harness-scaling figure). Older H100 / EKS / exploratory artifacts live in
`archive/` — do not resurrect them into the main tree. The thesis itself is a separate repo at
`~/thesis/InferSuite_thesis` (LaTeX; approved figures are copied into its `figure/` trees; its
`figure/oc_clean` and `figure/service_iso` trees predate the 2026-08-04 narrowing). The AWS
account from the EKS era has been fully torn down. If `HANDOFF.md` exists at the repo root it
is the current session-state document — read it first when resuming thesis work (it is
gitignored; never commit it).

## Knowledge wiki

`docs/wiki/` is the persistent, LLM-maintained knowledge base (an instance of the LLM-Wiki
framework, `docs/raw/llm-wiki.md`) — cross-cutting knowledge consolidated from this file and the
handwritten notes into interlinked pages: measurement ontology, agent/service architecture, the
load-bearing decisions (the "issues we ran into" list, as decision pages), and profiling/operations
conventions. Start at `docs/wiki/index.md`; the operating rules are `docs/wiki/schema.md`. Three
layers: `docs/raw/` (immutable sources) → `docs/wiki/` (the wiki) → `docs/reports/` (per-study
outputs, written by `study-report`). Maintain it with the `wiki` skill (ingest/query/lint); the
`report-check-commit` skill lints the wiki as its commit gate. This section is a pointer — the wiki
holds the detail, and `CLAUDE.md` remains the canonical schema.

## Commands

All measurement campaigns go through one entry point (it dispatches to the per-campaign kits;
nothing is reimplemented in it):

```bash
./measure.sh agents-swe preflight      # env checks, no spend, no state change
./measure.sh agents-swe campaign       # SWE-agent x GLM-5.2 capture (SWE_clean)
./measure.sh plots [set]               # regenerate figures from banked data (no capture)
./measure.sh validate [set]            # run validators over banked data
./measure.sh help
```

Stages run in order the first time: `preflight → dryrun → smoke → campaign → validate`.
Per-campaign knobs are env vars with certified defaults, e.g.
`SWE_INSTANCES=… SWE_DRAIN_S=… ./measure.sh agents-swe campaign`, `OC_TASKS=…`.
`SWE_TEMP` defaults to 0.6 — temp 0.0 makes agents
degenerate (truncated narration, quits after 1–2 turns); never run agent campaigns greedy.
The GLM API key lives at `~/.glm_key` — never print or echo it.

Figure-vs-data audit and the exploratory figure sets (not covered by `measure.sh plots`):

```bash
PLOT_SPEC=local_agents/SWE_clean/plot_spec.json python3 local_agents/scripts/glm/audit_plots.py
PLOT_SPEC=local_agents/SWE_clean/plot_spec.json python3 local_agents/scripts/glm/plot_exploratory.py
python3 local_agents/scripts/glm/plot_harness_scaling.py       # cross-campaign turns^~2.7 law
```

Optional boot-time isolation before a campaign: `sudo scripts/harden_isolation.sh --on` + reboot
(revert with `--off`). NEVER use isolcpus — it breaks scheduler load-balancing and stacks every
thread on one core; the script's nohz_full+rcu_nocbs mode is the correct one. Runtime isolation
(cpuset split, governor, no-turbo) is applied, verified by the ISO-PROOF gate, and restored by
the kits automatically. Never reboot or apply GRUB changes without explicit user confirmation.

There is no test suite or linter; validation is the campaign validator
(`local_agents/scripts/glm/validate_glm_agents.py`)
plus the figure audit (`audit_plots.py` independently recomputes every plotted number from raw
data and must report ALL MATCH before figures are trusted).

Git: never add Claude attribution to commits (no Co-Authored-By or "Generated with" trailers),
in this repo or the thesis repo. Do not commit Claude session artifacts (HANDOFF.md etc.).

## Architecture

**Campaign kits** (the code `measure.sh` dispatches to):
- `local_agents/scripts/glm/` — GLM-5.2 agent campaigns: `run_glm_campaign.sh` (staged runner
  for SWE, OC, and deterministic replays: isolation shield + ISO-PROOF gate, capture stack,
  loop guard, teardown), `oc_lineage_watcher.py`, `validate_glm_agents.py` (gates E1–E11),
  plotters (`plot_glm_results.py` — writes `values_dump.json` with every displayed number —
  plus `plot_exploratory.py`, `plot_harness_scaling.py`, `plot_internal_tools.py`, …),
  `audit_plots.py`, `gen_lanes_leaf.sh` (derives per-CPU lanes + leaf tables from records).
- `agentic/swe_agent/` — the SWE-agent harness the campaigns drive (unmodified; all
  measurement is external to it). The litellm proxy the campaign launches on the
  housekeeping cores lives at `local_agents/scripts/glm/.venv_litellm` (gitignored venv;
  python 3.13.13, litellm 1.89.4 — exact pins in
  `local_agents/scripts/glm/litellm_venv_freeze.txt`, rebuild with
  `python3.13 -m venv .venv_litellm && .venv_litellm/bin/pip install -r litellm_venv_freeze.txt`).
  It was moved 2026-08-04 out of `agentic/openclaw/` before that harness was removed.
(The service data path, its deploy stack, the GPU-side profiling kit, and the OpenClaw
harness were removed 2026-08-04 — see the narrowing note at the top; git history has them.)

**Agent measurement design** (the part that takes longest to reconstruct from code alone):
- **Fences are cgroups.** SWE-agent: a Python harness process on the host (measured slice);
  every tool action executes inside a per-task docker sandbox container (measured slice); a
  litellm proxy relays model calls to the GLM API (user slice → it runs on the HOUSEKEEPING
  cores, not the measured partition). OpenClaw: ONE container holds the Node gateway and every
  tool it spawns — no container boundary exists, so `oc_lineage_watcher.py` splits agent vs
  toolexec sub-cgroups by process lineage via the kernel's netlink proc connector: a fork by
  the gateway stays agent-side; the moment it execs a program it becomes a tool root
  (name-blind; cgroup inheritance carries all its descendants).
- **Four instruments run simultaneously per episode**: (1) 10 Hz cgroup `cpu.stat` pollers per
  fence — exact, always-on kernel accounting behind every core-second/timeline/burst figure;
  (2) windowed `perf stat` counting — 8 groups of ~6 events, ONE group per window, zero
  multiplexing, SHUFFLED rotation each cycle, episode-sum ratios; (3) continuous whole-episode
  TMA L1/L2 from the dedicated PERF_METRICS hardware (zero GP counters); (4) 99 Hz
  cgroup-scoped `perf record` — statistical, used only for what-program/symbol/CPU attribution,
  never for rates. A fifth partition-wide `/proc/stat` poller (the residual witness) banks
  everything-on-the-partition so validator gate E11 can bound unfenced kernel work.
- **Vocabulary**: a *call* is an action in the agent's log; a *burst* is contiguous fence CPU
  above a tiny detection floor (tool 0.005 / harness 0.02 cores, gaps <0.4 s merged); *heavy*
  is a burst classification (peak >0.3 cores). "CPU usage (cores)" is an occupancy rate in
  core-equivalents (spin included): exact average concurrency, a lower bound on peak
  concurrency, silent on distinct cores (the per-CPU lanes data answers that).

**Data and figures**: each campaign banks data next to its kit
(`local_agents/SWE_clean/data`, `local_agents/ML_multiling/data`,
`local_agents/superseded_40min/data`), with figures alongside (`plots/`, exploratory sets under
`plots*/extra/`, plus a `plot_spec.json` per agent campaign naming the featured runs). Top-level
`plots/` is a curated *view* synced from the source by `scripts/sync_plots.sh` — never edit
figures there; regenerate at the source and re-sync (the `results/` data view was deleted
2026-08-05). Each figure set has a MANIFEST documenting
definitions. Pipeline: plot_spec → plotters → values_dump.json → audit_plots (ALL MATCH) →
sync_plots → (only after approval in chat) copy into the thesis repo's `figure/` tree.

## Measurement conventions (locked — violating these invalidates figures)

- **Plot with the `infersuite-full` conda python**
  (`~/miniforge3/envs/infersuite-full/bin/python3`), not the project `.venv` and not bare
  `python3` — matplotlib/numpy no longer exist in the system interpreter (moved 2026-07; the old
  "system python3" rule silently broke the plotters and the dryrun gate's numpy workloads).
  `measure.sh` resolves this via `$PY`; standalone plotter invocations must use the env path.
  Collection and plotting are decoupled: collection scripts only collect; plot afterwards from
  banked data (`./measure.sh plots`).
- **perf on this workstation**: the working binary is
  `ls -d /usr/lib/linux-tools-6.8*/perf | tail -1` (package updates move it — always glob;
  `/usr/bin/perf` and the running-kernel symlink are broken). Local perf needs `sudo` /
  `perf_event_paranoid=-1`. If counters read `<not counted>` or flaky, kill orphaned root
  `perf -a` processes holding the PMU first.
- **cgroup scoping**: profile serving CPU with whole-pod cgroup scope (`perf -G` /
  `--for-each-cgroup`); process-scoped profiling misses the engine-core worker and reads ~idle.
- **TMA/signature figures**: never pool runs — use the median run per cell and document spread.
- **Figure vocabulary**: "CPU usage (cores)" = core-seconds per second; amounts in
  core-seconds; shares as % of CPU time; "core" = logical CPU; say "OS share", not "kernel";
  no bare "CPUs"/"CPU-s" axis labels. On-figure titles are SHORT — the caption/MANIFEST carries
  the description; definitions go in MANIFESTs, not figure footers. Cross-figure colors:
  whitish grey = GPU/model wait, green = tool fence, purple = harness, orange = litellm proxy.
- **Validation is proof-based**: an OK line is not proof — require observed evidence plus an
  independent cross-check (two subsystems agreeing) before declaring a run valid.
- **Thesis figures**: show plots in chat for approval first; edit the thesis only when told.
  Thesis prose is CODE-FREE — no code identifiers, counter/event names, or tool names in LaTeX.
- GPU prefill profiling requires `enable_prefix_caching=False` + a distinct warmup prompt,
  or the measured "prefill" is a one-token cache hit and conclusions invert.

## Issues we ran into (so you don't rediscover them)

- **PMU multiplexing is invalid for bursty agent workloads** — the kernel's scaling assumes the
  workload looks the same in every time slice; errors reach tens of percent on phased loads.
  Hence the zero-mux windowed rotation, and a dryrun gate requiring every group to report 100%
  enabled time.
- **A fixed rotation order phase-locks with the agent loop** — systematic sampling without a
  random start biases which phases a group sees. The rotation is shuffled every cycle and the
  realized order is banked (`windows.tsv`).
- **Cross-group ratio dilution** — dividing one group's event by instructions summed over ALL
  groups' windows inflated denominators ~8×. Every ratio must use co-counted denominators
  (instructions from the event's own windows). A dedicated-group replay probe
  (`GORDER_OVERRIDE`) exists to bound rotation-sampling error against a continuous capture.
- **Name-based OC fencing fails both ways** — spawned node tools carry the gateway's process
  name (fully misattributed) and short-lived processes die between polls. Only the lineage
  fork+exec rule works; pre-move residency is corrected at plot time and gate E4 checks fence
  purity against the lineage log.
- **OC turn boundaries cannot come from harness activity** — the Node gateway has continuous
  background CPU, so activation-clustering over-segments episodes (~5× too many "turns"). SWE
  turns derived from harness activations are validated against the logged step count; OC turns
  must come from the transcript's per-message timestamps.
- **Perf-record lane samples are on a different clock** than the epoch-stamped cpu.stat series —
  align by cross-correlating the two activity profiles, not by first-sample offsets.
- **The engine's ~2 busy cores are a CUDA busy-wait, not work** — IPC ~3.6, ~99% uop-cache,
  zero FP, ~85% of samples in event-sync/time-polling; the idle control drops to ~0.02 cores.
  High IPC/retiring does NOT certify useful work anywhere in this study.
- **API credit starvation looks like a model failure** — exhausted GLM credits show as EMPTY
  assistant turns (no content, zero token usage) in the transcript; the watchers report
  empty-turn counts. Park such episodes as rejected; don't debug the harness.
- **litellm lives on the housekeeping cores** — measured-partition capacity claims are
  tool+harness only. Kernel threads (writeback/irq) belong to no cgroup, so fence totals are
  lower bounds; the partition witness + gate E11 measure that residual on new runs (earlier
  campaigns predate the witness and carry only the pre-episode quiet-check bound).
- **k3s pods escape runtime shields** — leftover pods sit outside the system/user slices; the
  shield pins their slice explicitly and ISO-PROOF verifies effective cpusets, then requires
  the measured cores to be actually silent before any capture starts.
- **Greedy decoding breaks agents** — temperature 0.0 makes the model emit truncated narration
  and stop before the tool call, or lock into identical-action loops. Keep temp ~0.6; the loop
  guard (identical-action run length) is the backstop, and an action-uniqueness gate (E7)
  catches degenerate episodes after the fact.
