# Execution — Server set front-end footprint on x86 (P7)

**Owner:** Tianrui (Jerry) · **Written:** 2026-11-02 · **Status:** ready to execute, **after**
[`x86_spec_footprint.md`](x86_spec_footprint.md) has committed and validated the analyzer
**Machine:** P7 · **Results branch:** `dcperf`
**Request:** Rahul, 2026-11 (see the method contract [`frontend_footprint_method.md`](frontend_footprint_method.md), which governs).

## 0. Done means

* The **realistic Server set** (10 workloads, `in_realistic_server_set = 1` in
  `local_agents/RealData/data/l3_study/workload_index.csv`, the set the latest Server violins
  use) has one clean LBR footprint pass each:
  * suite benchmarks: tomcat (DaCapo), feedsim (DCPerf), finagle-chirper and finagle-http
    (Renaissance);
  * realistic datasets: cassandra-ycsb20m, kafka-20g, naivebayes-rcv1, neo4j-livejournal,
    pagerank-livejournal, video-4k.
* Each pass ran under the same shield, the same steady-state gate and the same capture length
  as that workload's existing counter passes, with the client outside the fence exactly as
  before.
* The analyzer (same commit as SPEC) summaries are in `local_agents/frontend_footprint_x86/`
  on `dcperf`. A study report and a session log are written and pushed.
* Optional, after the above: the 6 toy suite versions (cassandra, kafka, video_transcode,
  naive-bayes, neo4j-analytics, page-rank), so the suite-vs-realistic pair figure gets
  footprint rows too.

## 1. Blocking checks

Everything in §1 of `x86_spec_footprint.md` applies here unchanged: ≥ 60 GB free disk, the
box free of Jef's captures, quiet gate, no foreign `perf`. In addition:

* `git switch dcperf && git pull`, then cherry-pick the analyzer commit from `spec-x86`
  (`local_agents/kit/frontend_footprint/`) if it is not on `dcperf` yet. Record its SHA.
* Read:
  * `local_agents/RealData/README.md` §1 (fence vs client placement, liveness check, D4
    steady-state gate) and the per-workload sections;
  * `local_agents/DCPerf/README.md` §2, §8, §9 (orchestrator, self-sufficient isolation,
    clock pin);
  * `local_agents/JVMbench/README.md` §2 and §6.
* The infra trees must be intact: `~/dcperf-infra`, `~/realdata-infra` (datasets, servers,
  YCSB, Spark), `~/jvmbench-infra`. Check each dataset path from the per-workload table below
  before starting.

## 2. Implementation — one extra pass type in the existing orchestrator

`local_agents/kit/dcperf/run_dcperf_profile.sh` already runs one dedicated pass per counter
group, over the workload's steady state:

```
apply_isolation → bench_start (server in the measured scope, client on house cores, liveness check)
  → start_pollers + start_tma_cont → cycle_stats for CAPTURE_S → stop → bench_stop → restore_isolation
```

Add a pseudo-group **`lbr`**. When `g = lbr`, instead of `start_tma_cont` and
`GORDER=$g cycle_stats …`, run the contract's capture on `$CG` (the server fence from
`.server_cg`) for `CAPTURE_S` seconds, from the house cores:

```bash
taskset -c "$CPUS_HOUSE" $PERF record -z -m 512M --threads -e br_inst_retired.near_taken -c 20011 \
        -j any,save_type -a -C "$CPUS_MEASURED" --cgroup="$CG" -o "$OUT/lbr.data" -- sleep "$CAPTURE_S"
taskset -c "$CPUS_HOUSE" $PERF stat -x, -a -C "$CPUS_MEASURED" --for-each-cgroup="$CG" \
        -e instructions,br_inst_retired.near_taken -o "$OUT/exact_counts.csv" -- sleep "$CAPTURE_S"
```

* Keep everything else identical: `apply_isolation`, the foreign-perf guard, SMT offlining,
  the clock pin, `bench_start`/`bench_stop`, the 10 Hz pollers (for D4 and occupancy), and the
  client receipt.
* Use `DATA_ROOT=$REPO/local_agents/<DCPerf|JVMbench|RealData>/data/frontend_footprint` so
  footprint passes never mix with counter passes.
* Mark a pass DONE only if:
  * `lbr.data` has samples and lost records are < 1 %;
  * the client receipt shows the workload served (throughput comparable to the existing
    passes' receipts);
  * D4 drift < 25 %.
* **Data volume:** a multi-threaded server on 8 cores samples up to ~100 k LBR stacks/s, so
  `CAPTURE_S` of 300 means tens of GB raw. With `-z` it is a few GB.
  * Run the analyzer right after each pass and delete `lbr.data` once the summary verifies.
  * If `perf record` reports lost records ≥ 1 % in the smoke run, try `--threads` (if not
    already used) and a bigger `-m`. If it still loses, record the rate and decide with
    Jerry. **Do not silently change the period**: it is fixed by the contract for all three
    families.
* **Capture length = the workload's existing `CAPTURE_S`** (read it from the counter passes'
  `metadata.json`), so "whole execution" means the same steady-state window that every other
  Server metric used. Record it. Unique counts grow with window length, so this is a
  comparability rule, not a detail.

Smoke on **feedsim** (DCPerf; native C++, the best-documented workload), then **tomcat**
(in-process JVM, JIT code addresses), before the realistic set.

## 3. The workloads

Per-workload launch details (module, dataset path, client, capture) are in the table below. It
was filled from the RealData/DCPerf/JVMbench READMEs and kit on 2026-11-02. If a path is
missing on disk, stop and report; do not re-download a dataset silently (sizes and versions are
part of the method).

Run each command from `~/InferSuite` with **`PROF_GROUPS=lbr`** and a **fresh `DATA_ROOT`**.
Never point `DATA_ROOT` at the banked counter data: a pass's position in `PROF_GROUPS` decides
its `run_N`, and a group mismatch runs `rm -rf run_N` (`run_dcperf_profile.sh` ~lines
137–155). A lone `lbr` group would delete the banked `run_1`.

| Workload | Entry (env for `bash local_agents/kit/dcperf/run_dcperf_profile.sh`; wrap in `timeout 7200`, video `10800`) | Fence (4–11) ∣ outside (house) | `CAPTURE_S` | Fresh `DATA_ROOT` | Inputs on P7 |
|---|---|---|---|---|---|
| feedsim | `BENCH=feedsim FEEDSIM_QPS=16 CAPTURE_S=300` | LeafNodeRank ∣ run.sh, search_qps.sh, DriverNodeRank | 300 | `local_agents/DCPerf/data/frontend_footprint` | graph generated at start-up (`graph_scale=21`, 3.5 GB resident); build in `~/dcperf-infra/DCPerf` |
| tomcat | `SUITE=dacapo BENCH=dacapo WORKLOAD=tomcat CAPTURE_S=180 D_ITERS=80` | whole JVM (clients in-process) ∣ – | 180 | `local_agents/JVMbench/data/frontend_footprint` | `~/jvmbench-infra/dacapo-23.11-MR2-chopin.jar` + its data tree |
| finagle-chirper | `SUITE=renaissance BENCH=renaissance WORKLOAD=finagle-chirper CAPTURE_S=180` | whole JVM ∣ – | 180 | same as tomcat | `~/jvmbench-infra/renaissance-gpl-0.16.1.jar` |
| finagle-http | `SUITE=renaissance BENCH=renaissance WORKLOAD=finagle-http CAPTURE_S=180` | whole JVM ∣ – | 180 | same | same jar |
| cassandra-ycsb20m | `SUITE=realdata BENCH=cassandra WORKLOAD=cassandra-ycsb20m CAPTURE_S=180 CAS_WARMUP_S=120` | `cassandra -f -R` ∣ YCSB workload A, 24 threads | 180 | `local_agents/RealData/data/frontend_footprint` | store in `~/realdata-infra/cassandra` (now 29 GB) |
| kafka-20g | `SUITE=realdata BENCH=kafka WORKLOAD=kafka-20g CAPTURE_S=180 KAFKA_WARMUP_S=90` | broker ∣ 3 producers + 6 consumers | 180 | same | `~/realdata-infra/kafka` (21 GB retention window) |
| naivebayes-rcv1 | `SUITE=realdata BENCH=spark WORKLOAD=naivebayes-rcv1 CAPTURE_S=180` | `spark-shell` JVM, `local[8]` ∣ – | 180 | same | `~/realdata-infra/datasets/rcv1/rcv1_test.multiclass` (777 MB) |
| neo4j-livejournal | `SUITE=realdata BENCH=neo4j WORKLOAD=neo4j-livejournal CAPTURE_S=180 NEO_WARMUP_S=150` | `neo4j console` ∣ `neo4j_client.py` (5 procs × 5 sessions) | 180 | same | store under `~/realdata-infra/neo4j` (2.9 GB) |
| pagerank-livejournal | `SUITE=realdata BENCH=spark WORKLOAD=pagerank-livejournal CAPTURE_S=180` | `spark-shell` JVM ∣ – | 180 | same | `~/realdata-infra/datasets/livejournal/soc-LiveJournal1.txt` (1.08 GB) |
| video-4k | `SUITE=realdata BENCH=video_transcode WORKLOAD=video-4k VT_CUTS=$HOME/realdata-infra/datasets/video4k VT_LEVELS=6:6 CAPTURE_S=180` | `run.sh` + every `ffmpeg` ∣ – | 180 | same | two 4K y4m (11.1 GB) + ~16 GB scratch for `resized_clips` |

Known traps (all hit on x86 before, most already handled in the modules):

* **video:** `VT_LEVELS` must be set explicitly (module default `6:9`, the captures used
  `6:6`). `VT_CUTS` swaps `datasets/cuts` for a symlink and restores it afterwards. Check
  that it was restored.
* **FeedSim:** delete `/tmp/feedsim_log.txt` before the run (root creates it;
  `fs.protected_regular`).
* **JDKs:** upgraded on 2026-10-27 (21.0.12.1 / 17.0.20.1; the captures used 21.0.12+8 /
  17.0.20+8). Record `java -version` in metadata. A minor bump, but it is a difference.
* **Stores:** the Cassandra and Neo4j stores are in their post-campaign state (Cassandra
  carries nine passes of updates; x86 throughput drifted 86 k → 57 k ops/s across the
  passes). Reuse them as they are, and record their size and state. A rebuild only on
  Jerry's say-so: disk and hours.
* **Disk:** video-4k alone needs ~16 GB of scratch on top of the `lbr.data` budget.
* **`pkill -f` can match the caller's own command line.** "Device or resource busy" errors
  from governors of offline CPUs 16–23 are harmless.

The optional suite versions use the same orchestrator:
`SUITE=dacapo BENCH=dacapo WORKLOAD={cassandra,kafka}`,
`SUITE=renaissance BENCH=renaissance WORKLOAD={naive-bayes,neo4j-analytics,page-rank}` (all
`CAPTURE_S=180`), and `BENCH=video_transcode CAPTURE_S=180 VT_LEVELS=6:6` for the 1080p
`video_transcode`.

## 4. Analyze, aggregate, hand over

* Same analyzer, same rules. Note that multi-process workloads are exactly where the
  canonical-address rule matters: Kafka's broker forks nothing, but video-4k spawns many
  `ffmpeg` processes and DCPerf's feedsim fence holds one process.
* `local_agents/frontend_footprint_x86/`:
  * `<workload>/summary.json`;
  * `frontend_footprint_rows_long.csv` (`workload,family,subgroup,metric,value,analyzer_sha,period,capture_s`;
    family/subgroup as in `workload_index.csv`);
  * `gates.csv`;
  * `MANIFEST.md`.
* The combined violin (Agentic vs SPEC vs Server, one figure per metric, same style as
  `plot_paper_agg_compact_server.R`) needs Jef's agentic rows in the same schema. Write the
  plotting script now so that it runs as soon as his CSV arrives, and render SPEC + Server
  for a sanity check.

## 5. Document, push, restore

Session log (`/handoff`), study report (`/study-report`; or a section in the SPEC footprint
report if the same session wrote it, with populations named), commit on `dcperf` with no Claude
attribution, push (`/report-check-commit`). Verify the machine is restored: house cpusets,
SMT siblings back online, clock policy, no `perf`, no leftover scopes or clients.
