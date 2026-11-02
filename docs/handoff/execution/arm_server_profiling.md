# Execution — Server set (realistic datasets) on AWS Graviton (ARM)

**Owner:** Tianrui (Jerry) · **Written:** 2026-11-02 · **Status:** ready to execute, **after**
[`arm_spec_profiling.md`](arm_spec_profiling.md) has brought up the box, the shield and the
profiler
**Machine:** AWS `c9gd.metal-48xl` (Neoverse-V3), same box and same rules as the SPEC doc.
**About $8.5/h.**
**Results branch:** `dcperf-arm` · **Working folder:** `~/jerry-spec-dcperf`, a `git worktree` of
`~/jerry-spec` on `dcperf-arm`: `git -C ~/jerry-spec worktree add ~/jerry-spec-dcperf dcperf-arm`
**Request:** Jef, 2026-11: the Server set on ARM, **with the same realistic datasets as on
x86**, profiled with his ARM metric families. List every workload that fails to run because
of the architecture change.

## 0. Done means

* The 10 workloads of the **realistic Server set** (the set of the latest x86 Server violins,
  `in_realistic_server_set = 1` in `local_agents/RealData/data/l3_study/workload_index.csv`)
  each have tier-1 family passes on ARM, captured like x86:
  * same server/client split, with the server in the fence on the 8 measured cores (8–15)
    and the client on the housekeeping cores (0–7);
  * same dataset, warm-up, liveness check and D4 steady-state gate, and same capture length.
* An **architecture-failure table**: workload → `ran` / `ran-with-deltas` (works, different
  code path or library build, e.g. a missing native library falls back to pure Java) /
  `failed` (with the exact error and what was tried).
* `arm/` on `dcperf-arm`:
  * the processed per-window and per-workload CSVs in Jef's server schema;
  * metadata and gates;
  * the dataset provenance table (source URL, size, checksum, on-box path);
  * a study report and a session log.
* Optional, after the above: the 6 toy suite versions, for the suite-vs-realistic pair.

## 1. Before starting

* `arm_spec_profiling.md` §1 (look before touching, inventory, boot mode, push access) and §4
  (shield, ISO-PROOF, witness, restore) apply verbatim. Reuse `arm/kit/` from `spec-arm`:
  cherry-pick its commit onto `dcperf-arm`.
* Read on this branch:
  * `local_agents/RealData/README.md` (§1 method: what is inside and outside the fence, the
    liveness check, the D4 gate; then each workload's section);
  * `local_agents/DCPerf/README.md` §2, §8, §9;
  * `local_agents/JVMbench/README.md` §2, §6, §9.

  These are the x86 ground truth you are reproducing.
* The x86 orchestrator is `local_agents/kit/dcperf/run_dcperf_profile.sh` with one module per
  workload (`bench_*.sh`). It sources the x86 agent campaign runner (Intel counter groups,
  Intel TMA, x86 shield). **Do not run it unchanged on ARM.** Port the modules' `bench_start`,
  `bench_stop` and `bench_preflight` (server launch, client launch, liveness, receipts: all
  architecture-neutral shell) onto `arm/kit/` (shield + profiler).
  * Replace `CPUS_MEASURED=4-11` → `8-15` and `CPUS_HOUSE=0-3,12-15` → `0-7`.
  * Replace the counter loop with one pass per Jef family (`arm/kit/arm_profile.py`).
  * Keep `CAPTURE_S` per workload equal to x86's.
* Disk: datasets, stores and scratch need roughly **120 GB**: Cassandra store ≈ 30 GB, Kafka
  retention ≈ 30 GB, video-4k 11 GB input + 16 GB scratch, the DaCapo zip and data ≈ 20 GB
  until pruned to the three workloads, Spark/Neo4j inputs < 10 GB. Check `df -h ~` before
  downloading. The root EBS volume may need growing (ask Jerry).

## 2. Per-pass procedure (each workload × each family)

1. Quiet gate → `arm_shield.sh apply` → ISO-PROOF.
2. `bench_start`:
   * server under `systemd-run --scope --slice=<our measured slice> -p AllowedCPUs=8-15 --
     taskset -c 8-15 <server>`;
   * client with `taskset -c 0-7`;
   * warm-up, then the liveness check (fence ≥ 1 core over 10 s; 0.5 for the Kafka broker;
     "half the encoder pool for 8 consecutive seconds" for video).
3. `perf stat -j -I 100 -C 8-15 -G <fence> …` for the family plus the environment pass, for
   `CAPTURE_S`.
4. `bench_stop` (the client outlives the capture by 60 s and writes its per-second receipt).
5. Restore, verify, then 20 s settle.

**Per-pass validity:**
* every window is ≥ 99.999 % running;
* the frequency pass is at 3.3 GHz ± 100 MHz;
* D4 drift < 25 %;
* the receipt shows the workload served;
* the witness is clean.

Tier 1 first (anchor, frequency, branch, branch-types, cache-l1, cache-l2-ll, bandwidth,
tlb-data, tlb-code), tier 2 after (`arm_spec_profiling.md` §5 has the event lists and
formulas). Resumable DONE markers per ⟨workload, family⟩.

Cost: x86 needed about 5–10 min per pass (start + warm-up + `CAPTURE_S` + stop). 10 workloads
× 9 tier-1 families is **~10–15 h of box time**, plus dataset preparation. Batch it, and do
the downloads and builds while nothing is being measured.

## 3. Workloads, datasets and ARM porting notes

Ground truth = what ran on x86 (versions, flags, datasets), extracted on 2026-11-02 from the
READMEs, kit, run metadata and install logs. Checksums of the x86 inputs are in
`docs/handoff/execution/server_inputs_sha256.txt`. Verify every re-download against them (or
record why it differs, e.g. a repackaged tarball). `dlcdn.apache.org` keeps only current
releases, so use `https://archive.apache.org/dist/…` for these exact versions.

| Workload | Software (x86 version) → ARM install | Dataset → source, size | Fence ∣ client | Gate → `CAPTURE_S` |
|---|---|---|---|---|
| tomcat | DaCapo 23.11-MR2 Chopin (Tomcat 10.1.11), OpenJDK 21 → `openjdk-21-jdk-headless` (arm64) + `https://download.dacapobench.org/chopin/dacapo-23.11-MR2-chopin.zip` (6.3 GB zip; only the cassandra/tomcat/kafka data is needed) | web apps inside the DaCapo zip, 14 MB | whole JVM ∣ – | JVM rule (≥ 1 core over a 10 s moving mean, then 45 s JIT hold) → 180 |
| feedsim | DCPerf @`9308c3e`, built from source (folly `cc3f054`, fbthrift `773f9a8`, …, GCC 13.3, `-O3`) → `git clone https://github.com/facebookresearch/DCPerf.git; git checkout 9308c3e`; DCPerf ships `install_feedsim_aarch64_ubuntu.sh` (same "Ubuntu 22.04" literal check as x86: patch it to also match 24.04); `./benchpress_cli.py install feedsim_autoscale` | generated at start-up, `graph_scale=21` (3.5 GB resident) | LeafNodeRank ∣ `run.sh`, `search_qps.sh`, DriverNodeRank | 90 s start + 120 s warm-up → **300** |
| finagle-chirper | Renaissance 0.16.1 → `https://github.com/renaissance-benchmarks/renaissance/releases/download/v0.16.1/renaissance-gpl-0.16.1.jar` | 486 KB CSV inside the jar | whole JVM ∣ – | JVM rule → 180 |
| finagle-http | same jar | none (synthetic requests) | whole JVM ∣ – | JVM rule → 180 |
| cassandra-ycsb20m | Cassandra 5.0.9 on OpenJDK 17, YCSB 0.17.0 on JDK 21 → `archive.apache.org/dist/cassandra/5.0.9/apache-cassandra-5.0.9-bin.tar.gz`, `github.com/brianfrankcooper/YCSB/releases/download/0.17.0/ycsb-cassandra-binding-0.17.0.tar.gz` | **generated**: `RECORDS=20000000 bash local_agents/kit/dcperf/setup_cassandra_ycsb.sh` → 20 M × 1 KB, 21 GB store (≈ 30 GB disk) | `cassandra -f -R` (heap 8 G) ∣ YCSB workload A, 24 threads | 120 s + ≥ 1 core → 180 |
| kafka-20g | Kafka 2.13-4.3.1 KRaft on JDK 21 → `archive.apache.org/dist/kafka/4.3.1/kafka_2.13-4.3.1.tgz` | **generated**: `setup_kafka.sh` (12 partitions, 21 GB retention window; ≈ 30 GB disk) | broker (heap 6 G) ∣ 3 producer + 6 consumer perf-test JVMs | 90 s + ≥ 0.5 core → 180 |
| naivebayes-rcv1 | Spark 3.5.9-hadoop3 on JDK 21 → `archive.apache.org/dist/spark/spark-3.5.9/spark-3.5.9-bin-hadoop3.tgz` | RCV1-v2 test split, `https://www.csie.ntu.edu.tw/~cjlin/libsvmtools/datasets/multiclass/rcv1_test.multiclass.bz2` (292 MB → 777 MB) | `spark-shell --master local[8] --driver-memory 24g …` ∣ – | load marker + JVM rule → 180 |
| neo4j-livejournal | Neo4j Community 5.26.12 on JDK 21; client Python 3.13 + `neo4j` 6.3.1 → `https://dist.neo4j.org/neo4j-community-5.26.12-unix.tar.gz`; store by `setup_neo4j_livejournal.sh` | SNAP soc-LiveJournal1, `https://snap.stanford.edu/data/soc-LiveJournal1.txt.gz` (248 MB → 1.08 GB → 2.9 GB store) | `neo4j console` ∣ `neo4j_client.py --procs 5 --sessions 5 --p-short 0.80 --p-long 0.12` | 150 s + ≥ 1 core → 180 |
| pagerank-livejournal | Spark 3.5.9 (as above) | the same LiveJournal edge list | `spark-shell` JVM ∣ – | load marker + JVM rule → 180 |
| video-4k | DCPerf video bench (ffmpeg n7.0.1, SVT-AV1 v3.0.1, built by the benchpress installer with clang 18) → same installer on arm64 | Xiph Netflix 4K: `https://media.xiph.org/video/derf/y4m/ElFuente/Netflix_{Boat,FoodMarket}_4096x2160_60fps_8bit_420.y4m` (3.7 + 7.4 GiB) + ~16 GB scratch | `run.sh --encoder svt --levels 6:6 --procs 8 --parallelism 1` + every `ffmpeg` ∣ – | "Running M" marker + ≥ 4 cores for 8 s → 180 |

ARM porting decisions to make **explicitly and record** (each one changes what is measured):

1. **JDK paths.** `-amd64` JDK paths are hard-coded in `bench_cassandra.sh` (15–16),
   `bench_neo4j.sh` (18), `bench_kafka.sh` (16), `bench_spark.sh` (10),
   `setup_neo4j_livejournal.sh` (9), `setup_kafka.sh` (14) and `setup_cassandra_ycsb.sh` (13
   and 72, the latter not overridable). Make them `-arm64`/auto-detected **in our port**.
2. **Host-scaled JVM defaults.** On x86 the suite JVMs (Renaissance, DaCapo) ran with no heap
   flags, so G1 ergonomics gave a 1000 MB initial and 15,944 MB max heap (25 % of 62 GB). On a
   377 GiB box ergonomics would pick ~94 GB. **Pin `-Xms1000m -Xmx15944m`** to match x86 (the
   x86 `bench_jvm_common.sh` has no flags hook: add one in our port). Cassandra's GC threads
   come from `/proc/cpuinfo`: pin `ParallelGCThreads=ConcGCThreads=16` as on x86.
3. **jemalloc for Cassandra.** On x86 it was LD_PRELOADed from FeedSim's build in
   `/usr/local/lib`. Set `CASSANDRA_LIBJEMALLOC` explicitly (FeedSim's build or `libjemalloc2`),
   and record which.
4. **Native libraries.** netty epoll/tcnative, snappy, lz4-java, zstd-jni, JNA, RocksDB and
   jffi all have aarch64 builds. SIGAR (Cassandra, DaCapo cassandra) is x86-only: a warning,
   not fatal → `ran-with-deltas`. Spark's leveldbjni is unused in local mode.
5. **FeedSim tuning.** DCPerf's own ARM job uses `icache_iterations=400000`
   (`benchpress/config/jobs.yml` 348–362) against x86's 1,600,000. **Keep 1,600,000**
   (like-for-like work), and say so. Re-calibrate the operating point with
   `calibrate_feedsim.sh` using the same rule that gave 16 QPS on x86 (p95 ≈ 479 ms), and
   record the ARM QPS. Keep the pool sizes `-t 8 -c 6 -s 4` and
   `MALLOC_CONF=narenas:20,dirty_decay_ms:5000`.
6. **Video SIMD.** On aarch64 the installer compiles with
   `-march=armv9-a -mtune=neoverse-v2 -msve-vector-bits=128`. Check that the SVE vector length
   on Neoverse-V3 is 128 bits (`/proc/sys/abi/sve_default_vector_length`) before trusting the
   build. NEON/SVE vs AVX code paths differ by nature, so record it as `ran-with-deltas`.
7. **Neo4j client.** Install the aarch64 `neo4j-rust-ext` wheel if available. Without it the
   client is pure Python and slower. On x86 the load was client-limited (house ~80 % busy,
   server 3.8 cores), so record house-core busy % and server cores for comparison.
8. **Neo4j config.** `setup_neo4j_livejournal.sh` overwrites `neo4j.conf` with 14 keys (heap
   8 g, page cache 12 g, auth off), dropping Neo4j's stock JVM flags. Every x86 pass logged the
   page-cache "DirectByteBuffer … fallback mode" warning. Reproduce the same config: same
   warning, same behaviour.
9. **NUMA.** Measured 8–15 and house 0–7 are all on node 0. The kernel allocates locally;
   record `numastat` for the fence at the end of a pass.

Traps x86 already hit:
* YCSB silently lost 12 % of keys during the load until insert retries were on (the setup
  script has them now, with a completeness check).
* Kafka without a retention window fills the disk.
* Spark's carriage-return progress bars break `^`-anchored greps.
* `find` needs `-L` through the video cuts symlink.
* `pkill -f` can match its own caller.
* A shell in the house slice cannot `taskset` onto measured cores: the process must enter the
  measured scope first.

## 4. Outputs (Jef-style layout, same as the SPEC doc §7)

```
arm/                                 (in ~/jerry-spec-dcperf, branch dcperf-arm)
  config/host.toml, config/profiling_plan.toml
  kit/                               shared with spec-arm (cherry-picked), plus bench modules ported from local_agents/kit/dcperf/
  data/raw/, data/interim/           GIT-IGNORED (archive off the box)
  data/processed/server/             COMMITTED: server_arm_windows.csv.gz, server_arm_votes.csv, passes.csv, receipts/
  reports/figures/data/              COMMITTED: figure-ready CSVs
  datasets.csv                       COMMITTED: workload, dataset, source URL, bytes, sha256, on-box path
  arch_failures.csv                  COMMITTED: workload, status, error, attempts
```

* Server figure schema (Jef's): `suite,category,workload,metric,value`, as in his
  `server_windows.csv`. suite = DCPerf / DaCapo / Renaissance / RealData; the metric strings
  are exactly his.
* Per-workload value: the **whole-runtime rule** used for the x86 Server votes
  (`local_agents/JVMbench/README.md` §9). Also produce Jef's mean-of-windows vote and say
  which one each figure uses.

## 5. Document and push

Session log, study report, commit on `dcperf-arm` (no Claude attribution, nothing ≥ 100 MB, no
datasets, nothing from Jef's repo), push. Archive raw data and tell Jerry its path. Restore the
box and say clearly that it can be stopped.
