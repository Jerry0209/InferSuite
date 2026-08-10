# Measurement kit — SWE-agent × GLM-5.2 campaigns

The one kit behind every agent measurement in this repo: **SWE-agent driven live by GLM-5.2**
(z.ai, thinking enabled), harness and tool CPU fenced into separate cgroups, full microarch
suite, repeats with dispersion checks, runtime isolation.

Reorganized 2026-08-05 from the flat `local_agents/scripts/glm/` into pipeline stages; the
OpenClaw code paths (oc_episode, lineage watchers, OC plotters) were removed the same day —
restore from git history for an OC revival.

## Layout (by pipeline stage)

| Subdir | Stage | Contents |
|---|---|---|
| `campaign/` | Capture & planning | `run_glm_campaign.sh` — the heart: staged runner (preflight → dryrun → smoke → campaign → validate) with isolation shield + ISO-PROOF gate, 8 zero-mux counter groups in shuffled rotation, continuous TMA, 10 Hz fence pollers + partition witness, 99 Hz records, loop guard, teardown-on-any-exit. Plus `campaign.conf` (single config source), `litellm_glm.yaml` + gitignored `.venv_litellm/` (proxy venv; exact pins in `litellm_venv_freeze.txt`, rebuild with `python3.13 -m venv .venv_litellm && .venv_litellm/bin/pip install -r litellm_venv_freeze.txt`), `multiling_inventory.py` (300-instance sampling-frame inventory), gitignored `.state/` (gate markers). |
| `replay/` | Deterministic replays & per-window derivation | `replay_l3_profile.sh` (dedicated-group replay passes, `GORDER_OVERRIDE`), `localize_traj.py` (foreign-trajectory path fix), `analyze_l3_windows.py` (2-s windows + 2 Hz command tagger), `attribute_windows.py` (cross-task attribution), `dump_all_metrics.py`, `extract_tma_perrun.py`, `gen_lanes_leaf.sh` (per-CPU lanes + leaf tables from records), `behavior_campaign.sh` + `behavior_classify.py` (behavioural falsification probes). |
| `plot/` | Figures & deck (banked data only) | `plot_glm_results.py` (main set; writes `values_dump.json` with every displayed number), `plot_call_structure.py`, `plot_internal_tools.py`, `plot_calls_vs_bursts.py`, `plot_exploratory.py`, `plot_harness_scaling.py` (cross-campaign turns^~2.7 law), `cross_task_grid.py`, `build_metric_gallery.py`, `cmp_allruns.py --view {shares,absolute,tma}` (reproduction-vs-certified comparison), `build_deck.py`, `draw_agent_pipeline.py`. |
| `validate/` | Proof gates | `validate_glm_agents.py` (gates E1–E11: window integrity, isolation, cpu.stat-vs-PMU agreement, action uniqueness, burst census, TMA census, partition residual), `audit_plots.py` (independently recomputes every dumped value from raw data; must report ALL MATCH before figures are trusted). |

`events.md` (counter-group reference) stays at the kit root.

## Quick start

Always via the repo-root entry point:

```bash
./measure.sh agents-swe preflight      # fail-fast checks, no spend
./measure.sh agents-swe dryrun         # zero-multiplexing gate (8 groups vs dummy load)
./measure.sh agents-swe smoke          # proxy path: chat + tool-call (~2 requests)
./measure.sh agents-swe campaign       # SWE phase (SWE_INSTANCES x REPEATS)
./measure.sh agents-swe validate       # 3-layer validation over banked data
./measure.sh plots                     # regenerate figures (PLOT_SPEC-driven, no capture)
```

Single-episode smokes (`smoke-swe`, `smoke-django`, direct on the runner) run the FULL
campaign path for one episode; resume markers mean nothing is wasted. Ctrl-C at any point is
safe: INT/TERM route into the EXIT trap, so isolation is always restored.

Future rerun with another model: `MODEL_ID=<id> GLM_ENDPOINT=<url> KEYFILE=~/.other_key
TIER_PREFIX=<name> campaign/run_glm_campaign.sh all` — nothing else to edit.

## What is measured, where

| Scope | Cgroup | Contains |
|---|---|---|
| SWE harness | `measured.slice/glm-swe-*.scope` | sweagent python (model calls, parsing, orchestration) |
| SWE tool | `measured.slice/docker-<sweb>.scope` | the SWE-bench sandbox: every executed command/test |
| proxy | litellm scope (housekeeping CPUs) | model round-trip bookkeeping |

Per episode (`<DATA_ROOT>/glm_<wl>_<cfg>/run_<n>/`): `group_<g>_w<NNN>.txt` (zero-mux counter
windows), `windows.tsv` (epoch bracket + realized shuffled order), `tma_cont.csv` (continuous
whole-episode TMA), `rec_scopeN.data` + `scopeN_{dso,comm,ksym,leaf}.txt` (99 Hz records +
derived tables), `cpustat_scopeN.tsv` (10 Hz cpu.stat timeline), `procstat_partition.tsv`
(residual witness), `agent.log`, `metadata.json` (provenance), `traj/` (SWE), `DONE`.

## Isolation (runtime-only, restored by trap on ANY exit)

- CPUs 4-11 = measured partition (`measured.slice`, docker cgroup-parent switched to it) with
  their SMT siblings 16-23 offline; CPUs 0-3,12-15 = housekeeping (system.slice + user.slice
  shielded there, IRQs steered there, proxy/pollers/perf writers pinned there). Re-partitioned
  2026-08-05 (boot); the preflight topology gate verifies slices, online state, and
  no-online-SMT-sibling before any spend. (The certified campaigns ran the older
  2-11,14-23 / 0-1,12-13 split with SMT on — capacity numbers aren't directly comparable.)
- performance governor + no_turbo=1 (fixed ~base clock), THP never, NMI watchdog off
  (frees a GP counter), k3s stopped, stale perf killed.
- Hard guarantee about kernel per-cpu threads requires isolcpus (reboot) — deliberately NOT
  used; residual is <1% and outside the measured cgroups anyway (documented in Methods).

## Measurement rules

- **cgroups, never PIDs** (tool processes are children of containerd, invisible to PID-attach).
- Same-window decomposition: one `perf stat --for-each-cgroup=<all scopes>` per window.
- **Zero multiplexing**: each group fits the GP counters; the continuous TMA census uses
  PERF_METRICS only (0 GP counters). Validator rejects any window with a scaling annotation
  or `<not counted>`.
- Windows cycle for the WHOLE episode → N windows/group/run; medians + dispersion, never
  single-window numbers.
- (OpenClaw fencing — the lineage fork/exec rule and its E4 purity gate — is documented in
  `docs/wiki/decisions/lineage-fork-exec-fencing.md`; the code left the tree 2026-08-05.)

## Gotchas (inherited from the repo's history)

- perf binary: `/usr/lib/linux-tools-6.8*/perf` (`/usr/bin/perf` is broken on this box).
- sweagent run-batch silently skips instances with existing trajectories → output dirs are
  per-run (`runs/glm_live/<inst>_r<N>`) and wiped before launch.
- Kill stale root `perf -a` before capturing (PMU-holding orphans → `<not counted>`).
- litellm cost tracking does not know glm-5.2 → sweagent cost limits set to 0 (unlimited);
  episode wall is bounded by SWE_DRAIN_S instead.
- The GLM key was pasted in a chat transcript once → rotate after the campaign.
