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
| `pagerank-livejournal` | Renaissance `page-rank` (SNAP web-BerkStan, 7.6 M edges) | the same RDD PageRank on SNAP LiveJournal, 69 M edges | **profiled 2026-09-21, 9/9 passes, validated** |
| `naivebayes-rcv1` | Renaissance `naive-bayes` (a 100-row sample copied 8 000×) | Spark ML multinomial Naive Bayes on RCV1-v2, 518 571 Reuters documents × 47 236 features | **profiled 2026-09-21, 9/9 passes, validated** |
| `kafka-20g` | DaCapo `kafka` (1 M-message bursts on an empty broker) | Kafka 4.3 KRaft broker with a 21 GB retention window, 120 MB/s sustained ingest, six consumers reading the backlog | **profiled 2026-09-21, 9/9 passes, validated** |
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

## 4. kafka-20g

**Dataset and regime.** Apache Kafka 4.3.1 (KRaft combined mode, JDK 21, heap 6 GB),
standalone on loopback, one topic with 12 partitions pre-filled with **20 000 000 × 1 KB
records (20 GB)** by `setup_kafka.sh`, and a **retention window of 1.75 GB per partition
(21 GB)** in 512 MB segments with a 10 s retention check. That last part is what makes a
sustained run possible: the first smoke pass, without retention and at 205 MB/s, grew the log
by 40 GB in four minutes and briefly filled the disk. With the window the log oscillates between
21 and 28 GB whatever the ingest, which is also the regime a production broker lives in — a
fixed retention window, continuous ingest, consumers reading a backlog that is always older
than the page cache of what was just written.

**Clients** (housekeeping cores, `kafka-producer-perf-test` / `kafka-consumer-perf-test` from
the same distribution): three producers at 40 000 records/s each (**120 MB/s ingest**, acks=1,
128 KB batches, no compression) and **six consumer groups** each starting from the earliest
offset, i.e. reading the 21 GB backlog and then following the head. Steady state: the
consumers catch up within the 90 s warm-up, after which the broker serves 120 MB/s in and
6 × 115 ≈ 690 MB/s out. DaCapo's benchmark, by contrast, produces one-million-message bursts
into an empty broker from in-process threads with no consumer at all.

**Receipts** (identical in all nine passes): 120 000 records/s in, 682–700 MB/s out, producer
p99 5–7 ms.

**Validation:** D1–D5 and D7 pass. The broker runs at only **0.66 cores** — a broker is
I/O-bound by design, its data path is kernel zero-copy (`sendfile`) — and the unfenced residual
is 15.4 % of the partition's busy time, the loopback network stack's softirq work that no cgroup
owns, exactly as with DaCapo kafka (17.8 %). The steady-state gate's floor was set at 0.5 cores
for this module for that reason; D4 drift is 3.1 %.

**Toy versus realistic** (whole-runtime values):

| Metric | DaCapo kafka (bursts, client in-process) | 21 GB broker (sustained, clients outside) | ratio |
|---|---|---|---|
| IPC | 1.42 | 1.21 | 0.85× |
| Branch MPKI | 1.89 | 1.15 | 0.61× |
| Branch-direction MPKI | 1.65 | 0.82 | 0.50× |
| BTB MPKI (BAClears) | 0.36 | 0.86 | 2.4× |
| L1I MPKI (code-read) | 16.2 | 49.4 | 3.0× |
| uop-cache (DSB) MPKI | 52 | 98 | 1.9× |
| DSB coverage (%) | 60 | 21 | — |
| L1D-load MPKI | 5.8 | 9.4 | 1.6× |
| L2-load MPKI | 0.64 | 0.50 | 0.78× |
| LLC MPKI | 0.30 | 0.10 | 0.35× |
| DRAM read (GB/s) | 1.0 | 0.9 | 0.87× |
| Context switches (/CPU-s) | 5 050 | 26 700 | 5.3× |

The opposite of Cassandra. A real broker's own CPU work is almost entirely **request
handling**: network threads, protocol parsing, index lookups, offset bookkeeping for six
consumer groups — a huge, poorly cached instruction footprint (L1I 49 MPKI, uop-cache coverage
21 %, the worst of every server measured except cassandra's toy version) and 27 000 context
switches per CPU-second. The payload bytes never touch its user-space data path, so its memory
side is *lighter* than the toy's, whose in-process producer threads were building and copying
the messages inside the measured JVM. DaCapo's kafka measured a producer library; this measures
a broker.

## 5. pagerank-livejournal

**Input.** The SNAP LiveJournal edge list already downloaded for Neo4j (1.03 GB of text,
68 993 773 directed edges, 4 308 452 vertices with out-links), read straight from the file.
Renaissance's page-rank runs the same algorithm on SNAP web-BerkStan (7.6 M edges, 20 MB
zipped), 9× fewer edges.

**Job.** `kit/dcperf/spark/pagerank.scala` run by Spark 3.5.9's shell (`local[8]`, driver
24 GB) inside the fence — one JVM, no client, exactly the Renaissance arrangement. The
algorithm is the RDD join formulation of Spark's own PageRank example, which is also what
Renaissance's benchmark runs: `links.join(ranks)` → contributions → `reduceByKey` → damping,
three iterations per pass, passes looped until the capture is over. The one-off load (parse,
`groupByKey`, cache: 10.5 s) precedes the capture; the module waits for the script's
"graph loaded" marker before applying the JVM steady-state rule. `distinct()` was dropped
from the load because SNAP edge lists carry no duplicate edges and the extra full shuffle
doubled the load stage. Each three-iteration pass takes 43 s; every capture window holds five.

**Validation:** D1–D5 and D7 pass, mean load **7.7 cores** (the busiest workload in the
study), D4 drift 1.4 %, unfenced residual ≤ 2.6 %.

**Toy versus realistic** (whole-runtime values):

| Metric | Renaissance page-rank (7.6 M edges) | LiveJournal (69 M edges) | ratio |
|---|---|---|---|
| IPC | 2.15 | 1.70 | 0.79× |
| Branch MPKI | 1.31 | 1.54 | 1.2× |
| Branch-direction MPKI | 1.29 | 1.54 | 1.2× |
| BTB MPKI (BAClears) | 0.034 | 0.012 | 0.35× |
| L1I MPKI (code-read) | 1.09 | 0.46 | 0.42× |
| uop-cache (DSB) MPKI | 8.1 | 4.5 | 0.56× |
| DSB coverage (%) | 95 | 97 | — |
| L1D-load MPKI | 1.94 | 2.60 | 1.3× |
| L2-load MPKI | 0.69 | 1.13 | 1.6× |
| LLC MPKI | 0.39 | 0.80 | 2.1× |
| DRAM read (GB/s) | 5.7 | 11.1 | 1.9× |
| Context switches (/CPU-s) | 227 | 74 | 0.33× |

The direction one expects from a graph that no longer fits anywhere: the LLC miss rate
doubles, DRAM read bandwidth doubles to 11.1 GB/s (level with FeedSim and the realistic
Cassandra), and IPC drops by a fifth. The instruction side, already the cleanest of the
servers, gets cleaner still — a longer-running loop lets the JIT settle and the uop cache
covers 97 % of the stream. Both versions are compute-plus-bandwidth kernels; the real one is
simply further into the memory-bound regime, which is where a production PageRank lives.

## 6. naivebayes-rcv1

**Input.** RCV1-v2, the Reuters news corpus in the LIBSVM multiclass collection: the
518 571-document test split, 47 236 tf-idf features, 53 topics, 777 MB of sparse libsvm text.
Renaissance's naive-bayes trains the same Spark ML estimator on Spark's 100-row, 692-feature
`sample_libsvm_data.txt` replicated 8 000 times — 800 000 rows of the same 100 dense vectors.

**Job.** `kit/dcperf/spark/naivebayes.scala` in Spark 3.5.9's shell (`local[8]`, driver
24 GB) inside the fence: the corpus is loaded and cached once (4.6 s), then
`NaiveBayes(multinomial).fit` plus a full `transform` for the training accuracy (0.822) are
looped for the capture; a pass takes about 2.8 s, so every capture holds about 65. The
"corpus loaded" marker gates the capture as for PageRank.

**Validation:** D1–D5 and D7 pass, mean load 6.7 cores, D4 drift 1.9 %, unfenced residual
≤ 2.7 %.

**Toy versus realistic** (whole-runtime values):

| Metric | Renaissance naive-bayes (replicated sample) | RCV1-v2 (518 k documents) | ratio |
|---|---|---|---|
| IPC | 3.27 | 1.40 | 0.43× |
| Branch MPKI | 0.42 | 1.47 | 3.5× |
| Branch-direction MPKI | 0.37 | 1.44 | 3.9× |
| BTB MPKI (BAClears) | 0.045 | 0.11 | 2.4× |
| L1I MPKI (code-read) | 1.6 | 2.9 | 1.8× |
| uop-cache (DSB) MPKI | 9.8 | 12.6 | 1.3× |
| DSB coverage (%) | 89 | 90 | — |
| L1D-load MPKI | 1.06 | 26.3 | **25×** |
| L2-load MPKI | 0.13 | 10.4 | **81×** |
| LLC MPKI | 0.09 | 3.95 | **43×** |
| DRAM read (GB/s) | 9.9 | 26.1 | 2.6× |
| Context switches (/CPU-s) | 817 | 355 | 0.43× |

The most dramatic change in the study, and the easiest to explain. Eight thousand copies of
the same hundred dense vectors are a cache-resident kernel: the working set is one sample's
worth of features, the accesses are sequential, IPC is 3.3 and the LLC miss rate is nine per
hundred thousand instructions. A real corpus is sparse — 47 000 features, a few hundred
non-zero per document, scattered across the feature axis — so every document's update touches
the class-conditional weight table at random offsets. The data-cache ladder collapses at every
level (L1D 25×, L2 81×, LLC 43× the miss rate), DRAM read bandwidth reaches **26 GB/s, the
highest of every workload measured**, and IPC falls by more than half. Branch behaviour
deteriorates too (3.5–3.9×), the data-dependent loops over sparse rows being far less
predictable than dense fixed-length ones. Nothing about the software changed; the suite
benchmark was measuring the cache, not the algorithm.
