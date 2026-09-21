# Server workloads on realistic datasets — re-characterisation (RealData)

**Why this study exists.** The data footprint audit (`../JVMbench/README.md` §10, 2026-09-20)
found that nine of the ten server benchmarks profiled so far work on cache-sized data: DaCapo
cassandra on 10 MB of rows, Renaissance neo4j-analytics on a 70 MB movie graph, naive-bayes on a
105 KB sample copied 8 000 times, and so on. The mentor asked for the same characterisation on
datasets of realistic size. This directory holds those re-characterisations: one standalone
server per workload, loaded with a real or realistically sized dataset, profiled with the
identical instrument stack (nine dedicated-group passes, ISO-PROOF, 100 ms windows, D1–D7
validation) and, unlike the suite benchmarks, with the **client outside the fence** on the
housekeeping cores — the FeedSim arrangement.

| Workload | Toy version it replaces | Realistic dataset | Status |
|---|---|---|---|
| `neo4j-livejournal` | Renaissance `neo4j-analytics` (70 MB movie graph, in-process queries) | SNAP soc-LiveJournal1: 4 847 571 users, 68 993 773 follow edges, 2.9 GB Neo4j store | **profiled 2026-09-20/21, 9/9 passes, validated** |
| `cassandra-ycsb20m` | DaCapo `cassandra` (10 000 rows) | YCSB CoreWorkload A on 20 000 000 × 1 KB rows, 21 GB store | **profiled 2026-09-21, 9/9 passes, validated** |
| Spark PageRank / Naive Bayes | Renaissance `page-rank` (7.6 M-edge crawl), `naive-bayes` (replicated sample) | LiveJournal graph; RCV1-v2 corpus | planned |
| `kafka-20g` | DaCapo `kafka` (1 M-message bursts on an empty broker) | Kafka 4.3 KRaft broker with a 20 GB retention window, 120 MB/s sustained ingest, six consumers reading the backlog | profiling |
| Video | DCPerf VideoTranscodeBench on 2 s 1080p shots | 4K sources | planned |

Data is banked under `data/<suite>_<workload>/run_1..9` (gitignored, irreplaceable) with the
same layout as every other campaign; derived rows in `data/l3_study/`. Infrastructure (servers,
datasets, client venv) lives outside the repository in `~/realdata-infra/`, the same
arrangement as the SPEC, DCPerf and JVM suites.

## 1. Method, shared by every workload here

- **Server in the fence.** The database/broker JVM is launched as
  `measured.slice/realdata-<workload>-rN.scope` with `taskset` to the measured cores 4–11,
  through `run_dcperf_profile.sh` with `SUITE=realdata BENCH=<module>` — the same orchestrator,
  isolation shield, foreign-`perf` guard and counter rotation as DCPerf and the JVM suites.
- **Client outside.** The load generator runs on the housekeeping cores (0–3, 12–15) in
  `user.slice`, where the litellm proxy sits during agent campaigns and the FeedSim driver sat.
  This is what the suite benchmarks could not offer: their clients are threads inside the
  measured JVM, so their context-switch and instruction-supply numbers include client work.
- **Steady state.** Server up → client starts → a warm-up (page cache, JIT) → the fence must be
  busy (≥ 1 core over 10 s) → capture. The client outlives the capture by 60 s and writes its own
  per-second throughput and latency, summarised into `<workload>_receipt.json` per pass — the
  workload's own receipt, checked alongside the counters.
- **Isolation, capture, derivation, validation:** identical to `../JVMbench/README.md` §2 and
  §6 (cores 4–11, SMT siblings offline, 3.2 GHz pinned, `analyze_l3_windows.py`, gates D1–D7).
- **Per-workload value** for the figures: the whole-runtime rule (`../JVMbench/README.md` §9),
  computed by `export_runtime_votes.py` for family `realdata`.

## 2. neo4j-livejournal

**Dataset.** SNAP `soc-LiveJournal1` (Stanford Network Analysis Project): the LiveJournal
social network's directed friendship graph, 4 847 571 users and 68 993 773 edges, ids
contiguous. Downloaded as a 260 MB gzip edge list, converted to import CSVs
(`setup_neo4j_livejournal.sh`) and bulk-imported with `neo4j-admin database import` as
`(:User {id})-[:FOLLOWS]->(:User)`, plus an index on `User(id)`. Store: **2.9 GB** — 100× the
30 MB L3, 40× the toy benchmark's 70 MB. This is the smaller of the two graphs the mentor
named; `twitter-2010` (42 M nodes, 1.47 B edges) is 20× larger again and would need > 100 GB
of store and hours of import — the next step if a larger point is wanted.

**Server.** Neo4j Community 5.26.12 on JDK 21, standalone, heap 8 GB, page cache 12 GB (the
whole store fits, so after warm-up the workload is memory-resident, not disk-bound), bolt on
loopback, auth off, query logging off. Started fresh for every pass.

**Client** (`neo4j_client.py`, official Python driver 6.3 with its Rust packstream extension,
auto-commit statements): closed loop, 5 processes × 5 sessions, no think time, ids drawn
uniformly. Mix modelled on Renaissance neo4j-analytics' short / long / mutating structure
applied to a social graph:

| Class | Share | Query |
|---|---|---|
| short | 80 % | 1-hop degree of a user (40 % of shorts); 2-hop friends-of-friends count, bounded to 5 000 paths (60 %) |
| long | 12 % | bounded shortest path ≤ 4 hops between two users (50 %); 3-hop reach count bounded to 20 000 paths (50 %) |
| mutating | 8 % | add a FOLLOWS edge between two users / delete one edge of a user |

The mix was weighted toward traversals after the first smoke pass, where a 1-hop/2-hop mix
cost the Python client 2.6× the server's CPU per request and left the server at 2.7 of 8
cores; with this mix the server runs at 3.7–3.9 cores. The client still saturates the
housekeeping cores (≈ 80 % busy), so the operating point is client-limited — a Java client
would push the server harder; the collectors' window yield (≈ 78 %) was unaffected.

**Receipts** (capture window, per pass): 10 800–11 200 queries/s, short p95 4.0–4.2 ms,
long p95 6.5–6.7 ms, mutating p95 3.7–8.5 ms, zero errors in all nine passes.

**Validation:** D1–D5 and D7 pass on all nine passes; D6 n/a (no SLA defined). D5's
unfenced residual is 9.5 % of partition busy time (worst group), the loopback network stack's
softirq work that no cgroup owns — the same effect kafka showed at 17.8 %; fence totals are
lower bounds.

**Toy versus realistic** (whole-runtime values, `data/l3_study/` and `runtime_votes.csv`):

| Metric | Renaissance neo4j-analytics | LiveJournal server | ratio |
|---|---|---|---|
| IPC | 3.27 | 2.15 | 0.66× |
| Branch MPKI | 0.43 | 1.65 | 3.9× |
| Branch-direction MPKI | 0.42 | 1.42 | 3.4× |
| BTB MPKI (BAClears) | 0.020 | 0.73 | 36× |
| L1I MPKI (code-read) | 5.4 | 14.3 | 2.6× |
| uop-cache (DSB) MPKI | 34.3 | 26.9 | 0.79× |
| DSB coverage (%) | 68 | 76 | — |
| L1D-load MPKI | 1.09 | 3.94 | 3.6× |
| L2-load MPKI | 0.29 | 0.61 | 2.1× |
| LLC MPKI | 0.13 | 0.19 | 1.4× |
| DRAM read (GB/s) | 2.2 | 4.3 | 1.9× |
| Context switches (/CPU-s) | 621 | 17 250 | 28× |

The toy benchmark was a compute kernel: SPEC-grade branch behaviour, IPC 3.3, the third-highest
of anything measured. The real server on the real graph mispredicts four times as often, misses
the BTB 36 times as often, misses L1D four times as often, reads twice the DRAM bandwidth and
context-switches 28 times as often (a network-serving process instead of an in-process loop).
Its signature has moved from the SPEC corner to the middle of the server group: L1I 14.3 MPKI
sits between tomcat (39) and kafka (16), branch-direction 1.42 next to kafka (1.65), and its
IPC of 2.15 is now below the agentic median (1.90 is the agentic median; 2.15 is above it but
far from 3.27). Whether the memory side changes further with the 20× larger `twitter-2010`
graph is the obvious next question.

## 3. cassandra-ycsb20m

**Dataset.** The YCSB CoreWorkload schema DaCapo's benchmark uses — one `usertable` row of ten
100-byte fields per key — but **20 000 000 rows instead of 10 000**: a **21 GB** store in one
compacted SSTable (20.08 M partitions by the node's own estimate), 700× the L3 and a third of
the machine's RAM, loaded by YCSB 0.17 (the version DaCapo bundles) in four minutes at
79 000 inserts/s. A load-time trap worth recording: YCSB kills a client thread on any insert
error unless retries are enabled, and six write timeouts during the first load silently dropped
12 % of the key space (17.58 M of 20 M inserts); the setup script now enables retries and
refuses to finish unless every row was inserted.

**Server.** Apache Cassandra 5.0.9 on JDK 17 (the JDK the release supports), standalone
single node on loopback, heap 8 GB, defaults otherwise; started fresh for every pass on the
same store. Because the store (21 GB) is smaller than RAM (62 GB), reads are served from the
page cache after warm-up, so this is the memory-resident regime, not the disk-bound one a
production node with terabytes would be in.

**Client.** YCSB 0.17 `cassandra-cql` on the housekeeping cores, **workload A** (50 % read /
50 % update, zipfian request distribution, consistency ONE), 24 threads, closed loop — the same
workload definition DaCapo runs, with the client outside the fence. It needs only ≈ 30 % of the
housekeeping cores, so unlike the Python Neo4j client it is not the bottleneck.

**Receipts** (per pass): 86 000 → 57 000 operations/s, read p95 0.51 → 0.88 ms, update p95
0.41 → 0.56 ms, zero errors, zero not-found. The **decline across passes** is real: every pass
adds 180 s of updates to the same store, so later passes run against more memtable flushes,
more SSTables and background compaction, and their operating point is lower. Within a pass the
load is steady (D4 drift ≤ 5.3 %); across passes it moved by a third. Per-instruction metrics
are insensitive to that; anything per second is not, and the nine counter groups saw slightly
different throughputs. A per-pass restore of the compacted store (21 GB copy) would remove it
and is the obvious refinement.

**Validation:** D1–D5 and D7 pass on all nine passes (server load 6.2 cores mean, unfenced
residual ≤ 4.0 %).

**Toy versus realistic** (whole-runtime values):

| Metric | DaCapo cassandra (10 k rows, client in-process) | YCSB 20 M rows (client outside) | ratio |
|---|---|---|---|
| IPC | 1.05 | 1.28 | 1.2× |
| Branch MPKI | 1.68 | 2.04 | 1.2× |
| Branch-direction MPKI | 1.37 | 2.15 | 1.6× |
| BTB MPKI (BAClears) | 1.74 | 0.81 | 0.46× |
| L1I MPKI (code-read) | 61.9 | 37.4 | 0.60× |
| uop-cache (DSB) MPKI | 101 | 73 | 0.72× |
| DSB coverage (%) | 21 | 39 | — |
| L1D-load MPKI | 11.8 | 8.1 | 0.69× |
| L2-load MPKI | 0.79 | 0.95 | 1.2× |
| LLC MPKI | 0.13 | 0.28 | 2.2× |
| DRAM read (GB/s) | 2.0 | 11.1 | 5.5× |
| Context switches (/CPU-s) | 47 100 | 16 500 | 0.35× |

Two effects, in opposite directions. The **memory side grows with the data**: DRAM read
bandwidth rises 5.5× to 11.1 GB/s, now level with FeedSim (11.7) as the most memory-hungry
server measured, and LLC misses double — the toy's 10 MB of rows lived in the L3, the real
store does not. The **instruction side eases**: L1I misses, uop-cache misses and context
switches all fall because DaCapo's version runs its YCSB client threads inside the measured
JVM, and those threads, not the database, were a large part of its front-end and switch
signature. The real database is *less* instruction-bound and *more* memory-bound than the toy
made it look, which is the direction one would expect and the reason the mentor asked.
