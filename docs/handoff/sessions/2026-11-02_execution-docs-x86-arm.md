# Session 2026-11-02 — Execution docs for SPEC + Server on x86 (footprint) and ARM (profiling)

**Goal:** turn two requests into four executable docs and per-machine prompts:
(1) Jef — profile SPEC CPU 2026 (single core) and the Server set (realistic datasets) on the
AWS Graviton box, the way Jef profiled agentic work there; (2) Rahul — instruction footprint,
unique taken branches and weighted average targets per taken branch on x86, for SPEC26 and
Server (Jef does agentic). Branches: `spec-x86`, `dcperf` (existing), `spec-arm`, `dcperf-arm`.
**Machine state at start:** P7, branch `dcperf` clean at `ed433c9ff`; partition 4–11 measured /
0–3,12–15 house; **root filesystem 100 % used, 8.6 GB free**; perf now
`/usr/lib/linux-tools-6.8.0-147/perf` (6.8.12). No capture was run in this session (only
1-second LBR/PT probes on house core 1).

## Decisions
| # | Decision | Why | Made by |
|---|---|---|---|
| 1 | Rahul's metrics are measured by **LBR sampling** (`br_inst_retired.near_taken`, `-c 20011`, `-j any,save_type`, user + kernel, fence cgroup), with the unique counts reported as sampled lower bounds | Exact traces are not viable: Intel PT whole-run is ~50–150 GB per SPEC benchmark with hours of decode, and JIT needs jitdump; DBI distorts servers and cannot follow containerised agentic processes. LBR is the only instrument that works identically on all three families. Probed on P7: Arch-LBR depth 32, `-j any,save_type` works, perf script ~110 k samples/s | Claude (flag to Jerry/Jef) |
| 2 | Same period and analyzer commit for SPEC, Server and Agentic, written as a contract (`docs/handoff/execution/frontend_footprint_method.md`) to be shared with Jef | Unique counts depend on sampling density, so families are comparable only at identical detection probability | Claude |
| 3 | Validation gates V1 (synthetic truth), V2 (exact PT cross-check on short programs → LBR recall), V3 (period ×4 sensitivity), V4 (hygiene) before quoting numbers | Makes "lower bound" quantitative; protects against analyzer bugs | Claude |
| 4 | Server set to re-run = the **realistic Server set** (tomcat, feedsim, finagle-chirper, finagle-http + cassandra-ycsb20m, kafka-20g, naivebayes-rcv1, neo4j-livejournal, pagerank-livejournal, video-4k), per `workload_index.csv` `in_realistic_server_set` | It is the set the latest figures use (`SERVER_SET=realistic`), and the user asked for the realistic datasets | user + Claude |
| 5 | SPEC on ARM: same 26 benchmarks, ref, copies = 1, threads = 1, **ref command index 0**, pinned to **one** measured core; config `uarch-gcc14-aarch64.cfg` = x86 twin with `-mabi=lp64` + `-mcpu=native` | Comparability with the x86 rows (index 0 everywhere); the user asked for single-core profiling | user + Claude |
| 6 | SPEC media reaches ARM either by cloning the lab's private GitLab mirror `git@gitlab.ethz.ch:safari/spec26.git` on the box through `ssh -A` (preferred; P7's `spec26-orig` is a clone of it), or by rsync/tar from P7 excluding `.git/`, `*.tar.xz.part*` and `redistributable_sources` (6.5 GB); P7's `cpu2026.tar.xz` sha256 checked OK. The GCS bucket the download script used is gone (HTTP 404) | Only remaining sources; no key of Jerry's is left on the shared box | Claude |
| 7 | The SPEC capture kit (code only) is versioned into `spec26/infra_kit/` on `spec-x86`/`spec-arm`, with the x86 per-benchmark metrics and the LLC/DRAM cross-check summaries | The ARM box cannot reach P7's disk; data must not be lost | Claude |
| 8 | No code or data from Jef's private repo goes into InferSuite (public repo, HTTP 200 unauthenticated) — reimplement from his method | Licensing/ownership | Claude |
| 9 | ARM profiling mirrors Jef's Graviton5 method as read from his `feat/arm` (9aa188f): c9gd.metal-48xl, online 0–15, house 0–7, measured 8–15, platform-fixed 3.3 GHz witnessed by `cpu_cycles/cnt_cycles`, one dedicated pass per family (≤ cycles + 6 events), 100 ms windows, gate on `pcnt-running ≥ 99.999` | Comparability with his ARM agentic data; his own per-window mux check reads fields perf 6.17 `-j` does not emit, so we gate on `pcnt-running` directly | user + Claude |
| 10 | ARM families split into tier 1 (anchor, frequency, branch, branch-types, cache-l1, cache-l2-ll, bandwidth, tlb-data, tlb-code — covers Jerry's metric list) and tier 2 (frontend-stalls, frontend-supply-mem/core, backend, execution); tier 1 first | Box time is ~$8.5/h; tier 1 alone is ~7 h for SPEC and ~10–15 h for Server | Claude |
| 11 | ARM Server port pins x86-equivalent JVM sizing (`-Xms1000m -Xmx15944m` for the suite JVMs, Cassandra GC threads 16) and keeps FeedSim `icache_iterations=1600000` (DCPerf's ARM job uses 400000) | Host-scaled defaults on a 377 GiB box would change the workload; like-for-like work across architectures | Claude (flag to Jerry) |

## What changed
- New: `docs/handoff/execution/{README.md, frontend_footprint_method.md, x86_spec_footprint.md,
  x86_server_footprint.md, arm_spec_profiling.md, arm_server_profiling.md}`.
- `docs/handoff/README.md`: pointer row to the execution docs.
- `spec26/infra_kit/` (branches `spec-x86`, `spec-arm` only): kit snapshot + aarch64 config.
- `docs/handoff/execution/server_inputs_sha256.txt`: sha256 of every Server-set input on P7
  (none had been recorded at download time).

## Defects found
- P7 root filesystem is full (8.6 GB free). Any LBR/PT capture would truncate. Blocking check
  written into both x86 docs (≥ 60 GB free required).
- `download_spec26_aria2.sh` points at a GCS bucket that no longer exists (404).
- The first version of the ARM doc's transfer command (commit `fd8f4e8ff`) did not exclude
  `spec26-orig/.git/` and would have shipped a 7.2 GB git pack on top of the 6.5 GB media.
  Fixed in the follow-up commit.
- `local_agents/DCPerf/README.md` §4/§7.5 call the 1080p video cuts "100-frame"; the files are
  51 frames (F25:1, 158,630,766 B each). Not fixed here (README of another study); noted for
  the next DCPerf edit.
- Jef's ARM per-window validity check (`validate_measurement`, `minimum_scale 0.999`) reads
  `enabled`/`running` fields that perf 6.17 `-j` output does not have, so it can never fire.
  Not ours to fix; our ARM profiler gates on `pcnt-running`.

## Open threads
- Jerry: free disk on P7 before running the x86 docs.
- Jerry → Jef: confirm the footprint contract (period 20011, LBR, analyzer) before either side
  captures.
- Jerry: start the Graviton instance and give the ARM session SSH access; run the SPEC media
  transfer command from P7 (in `arm_spec_profiling.md` §2).
