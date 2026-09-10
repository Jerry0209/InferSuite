# Session 2026-09-10 — DCPerf bring-up: FeedSim profiled with the iso36 instrument stack

**Goal:** answer the mentor's brief — pick one DCPerf benchmark that is representative of the
suite and likely to behave unlike both SPEC and the agentic 36, profile it with *the same
method* as those 36 tasks, validate it, and produce v3-paper-style figures comparing all three
families. Then extend toward the rest of the suite.
**Machine state at start:** P7, branch `multiling-type-id` (clean), Ubuntu 24.04.4, ~48 GB free
disk, SMT siblings 16–23 **online** (no campaign running), langfuse containers up under
`system.slice`, no foreign `perf`. Baseline slice cpusets already pinned to the housekeeping
partition (the box's normal boot state).

## Decisions
| # | Decision | Why | Made by |
|---|---|---|---|
| 1 | Profile **FeedSim** first | representative of the fleet's dominant *latency-SLA serving* regime, which neither SPEC nor the agentic 36 has; deliberately manufactures instruction-cache pressure (`ICacheBuster` in 24 parts, `--min_icache_iterations=1600000`, 56 MB server binary), making it the sharpest test of this thesis's front-end claim; and its two-binary structure (server + load generator) maps onto our fence model with nothing invented | Claude |
| 2 | The other five are **not** runnable on P7 as-is | SparkBench needs NVMe-over-TCP storage nodes + a custom kernel; TaoBench is CentOS-only for the server, wants a 10–50 Gbps client network and an `iommu=pt` GRUB change; Mediawiki needs HHVM-3.30 (pre-noble libs); VideoTranscodeBench's dataset is behind a manual CDVL registration | Claude — **needs mentor scope call** |
| 3 | Reuse the agent kit as **code**, not as a pattern | `run_dcperf_profile.sh` sources `run_glm_campaign.sh noop` and calls `apply_isolation`, ISO-PROOF, `GRP[]`, `cycle_stats`, `start_pollers`, `start_tma_cont`; metrics come from the same `derive()` in `analyze_l3_windows.py`. Any divergence in method would invalidate the comparison | Claude |
| 4 | Server in the measured fence, **load generator on housekeeping cores** | `DriverNodeRank` is the client, not the workload under test — the same role litellm plays in agent campaigns, and the same placement | Claude |
| 5 | DCPerf's `run.sh` is **patched, not rewritten** (two edits, generator kept in-kit) | keeps every DCPerf flag, thread count, graph scale and jemalloc setting verbatim; only process *placement* changes | Claude |
| 6 | **Fixed-QPS operating point (16 QPS), not DCPerf's QPS search** | DCPerf asks for CPU boost on; our contract fixes the clock for comparability, and its README warns the search may not converge without boost. Swept 4/8/12/16/20 QPS under the real isolation and took the highest point meeting DCPerf's own p95 ≤ 500 ms SLA (479 ms; 20 QPS fails at 689 ms) | Claude |
| 7 | Thread pools passed explicitly (`-t 8 -c 6 -s 4`) | `run.sh` sizes them from `nproc` and `smt/active`; on a split partition both misread the machine (it would have used 2 ranking threads for 8 cores). The values are DCPerf's own non-SMT formula for 8 cores | Claude |
| 8 | `SKIP_DOCKER=1` for DCPerf runs | FeedSim runs no containers, so the daemon.json cgroup-parent swap is a no-op — and restarting dockerd nine times would bounce unrelated containers on a shared box | Claude |
| 9 | DCPerf is drawn as a **marker, not a violin** | a violin is a distribution over workloads (SPEC 26, agentic 36); DCPerf currently has one. Its marker is its vote — median of its windows, the same statistic — with a bar for its own window IQR, labelled as the different quantity it is. `DCPERF_VIOLIN=1` switches when more benchmarks land | Claude |

## What changed
- **New kit** `local_agents/kit/dcperf/`: `run_dcperf_profile.sh` (9-pass sweep, topology gate,
  foreign-perf guard), `bench_feedsim.sh`, `patch_run_sh.py`, `calibrate_feedsim.sh`,
  `derive_dcperf.sh`, `validate_dcperf.py` (gates D1–D7).
- **Two backward-compatible kit changes** (both verified behaviour-preserving):
  `run_glm_campaign.sh` gained a `noop` stage (so other kits can source it) and a
  `SKIP_DOCKER` guard; `analyze_l3_windows.py` gained `L3_BASE_PREFIX` / `L3_FENCES`
  overrides and a fence-count-agnostic `both` merge. **Regression check: re-deriving an iso36
  task produced a byte-identical CSV.**
- **New plotting**: `export_dcperf_rows.py`, `plot_paper_agg_compact3.R` (three-family
  12-panel grid), `plot_paper_agg_groups3.R` (per-window companion, unit-consistent),
  `summarize_three_families.py` (the README's table, computed not typed).
- **Docs**: `docs/handoff/dcperf_bringup.md` (suite overview, feasibility table, install
  recipe, traps), `local_agents/DCPerf/README.md` (task choice, method, three-way differences).
- **DCPerf checkout** at `~/dcperf-infra/DCPerf` (outside the repo, like `~/spec26-infra`).
- **Captures (gitignored)**: `local_agents/DCPerf/data/dcperf_feedsim/run_1..9`,
  `data/calibration/`.

## Traps hit
- DCPerf's Ubuntu compatibility patches are gated on a literal `Ubuntu 22.04` string, so on
  noble they are skipped and the pinned old folly fails to build. One-line fix; every apt
  package name in the installer does resolve on 24.04.
- `fs.protected_regular` blocks **root** from `O_CREAT`-ing a file it does not own in a sticky
  world-writable directory: pre-creating `/tmp/feedsim_log.txt` as our user made the
  root-run benchmark die instantly. The phase log must be created by the benchmark.
- Benchpress runs as root and leaves the DCPerf tree root-owned — the patched-runner generator
  needs `sudo`.

## Machine state left
SMT siblings 16–23 were **offlined** to match the iso36 topology. **They must be brought back
online** when profiling is finished:
`for c in 16 17 18 19 20 21 22 23; do echo 1 | sudo tee /sys/devices/system/cpu/cpu$c/online; done`
Isolation is applied and restored per pass by the kit's own trap.

## Open / next
- Results, validation output and figures: see `local_agents/DCPerf/README.md` §4.
- Remaining five benchmarks: DjangoBench is the next feasible candidate; VideoTranscodeBench
  needs a manual dataset download; Mediawiki needs a CentOS/22.04 container; TaoBench and
  SparkBench need hardware this box does not have (mentor scope call).
