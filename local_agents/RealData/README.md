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
| `video-4k` | DCPerf VideoTranscodeBench on six 2 s 1080p shots | the same runner on two Netflix 4K sequences from Xiph (Boat 301 frames, FoodMarket 601 frames, 4096×2160 @60) | **profiled 2026-09-21, 9/9 passes, validated** |

**The four server workloads that were NOT re-characterised, and why.**

| Workload | Why it stays as it is |
|---|---|
| DCPerf **FeedSim** | already realistic: it generates a 2²¹-vertex ranking graph at start-up and holds **3.5 GB resident**, the one benchmark whose data footprint Meta calibrated against production. Nothing to replace. |
| Renaissance **finagle-http** | has no dataset by design: 12 000 small HTTP requests per iteration against a server that stores nothing. Its footprint is instruction-side (L1I 52 MPKI), which does not grow with data. |
| Renaissance **finagle-chirper** | a microblog simulation whose entire corpus is a 486 KB tweet-text file; the load is request handling, not data. |
| DaCapo **tomcat** | serves Tomcat's bundled sample web applications, 14 MB of static content. Again a request tier. |

For these three request tiers a "realistic dataset" does not exist — what would make them realistic
is a real application behind the server and a real request mix, which is a different benchmark
rather than a bigger input. That is a separate study, not a dataset swap, so it was left out.

**What "9/9 passes" means.** The PMU cannot count all the events at once, so each workload is
profiled **nine times, once per counter group** (`fpbr`, `cache`, `mlp`, `fe`, `fe_lat`,
`core_ports`, `dram_bw`, `priv`, `fe_miss`) — the same nine the agentic 36, SPEC, DCPerf and the
JVM suites use. Each pass is a fresh server, its own warm-up, and 180 s of 100 ms counter windows
(~1 500 windows). "9/9 passes" is therefore *all nine counter groups captured completely*, which
is what validation gate D1 checks; a metric comes from the single pass whose group carried its
counters. Run-to-run repetition is still n = 1 (`../JVMbench/README.md` §7).

**Where the datasets come from.**

| Dataset | Source | Size |
|---|---|---|
| SNAP `soc-LiveJournal1` (Neo4j, PageRank) | Stanford Network Analysis Project, `snap.stanford.edu/data/soc-LiveJournal1.html` — a 2006 crawl of the LiveJournal friendship graph | 260 MB gzip → 1.03 GB edge list → 2.9 GB Neo4j store |
| RCV1-v2 (Naive Bayes) | the LIBSVM multiclass collection at `csie.ntu.edu.tw/~cjlin/libsvmtools/datasets`, itself the Reuters Corpus Volume 1 news archive | 292 MB bzip2 → 777 MB libsvm |
| Netflix 4K sequences (video) | Xiph's freely licensed video collection, `media.xiph.org/video/derf` — the *El Fuente* and *Chimera* sets DCPerf names, in the copies that need no CDVL registration | 3.7 GB (Boat) + 7.4 GB (FoodMarket) |
| YCSB rows (Cassandra) | **generated**, by YCSB 0.17's own CoreWorkload loader — the schema DaCapo's benchmark uses, at 2 000× its row count | 20 M × 1 KB → 21 GB store |
| Kafka records (Kafka) | **generated**, by Kafka's own `kafka-producer-perf-test` | 20 M × 1 KB → 21 GB retention window |

The two generated ones are generated because there is no public "real" dataset for them: a
key-value store's and a broker's realism is in the *shape and volume* of the traffic (row size,
key distribution, retention window, ingest rate), not in the byte content, and both generators
are the ones their own projects ship.

Data is banked under `data/<suite>_<workload>/run_1..9` (gitignored, irreplaceable) with the
same layout as every other campaign; derived rows in `data/l3_study/`. Infrastructure (servers,
datasets, client venv) lives outside the repository in `~/realdata-infra/`, the same
arrangement as the SPEC, DCPerf and JVM suites.

## 0. The two JVM suites these benchmarks come from

Background for a reader who meets `finagle-chirper` or `dacapo kafka` for the first time (PI's
summary, 2026-09-21). Both are open-source benchmark suites for measuring the performance of the
**Java Virtual Machine** — JIT compilers, garbage collectors, runtimes — and the hardware under
it, using real Java/Scala applications rather than synthetic kernels. Papers often use them
together because they lean in different directions: Renaissance toward concurrency and
data-parallel work, DaCapo-Chopin toward large server and enterprise applications with latency
reporting.

**Renaissance** was introduced at PLDI 2019 by researchers from Charles University, Oracle Labs
and USI Lugano, and has about 25 benchmarks. Its motivation was that older suites
under-represented modern JVM workloads, so it emphasises concurrency, parallelism and
functional-style code: Spark analytics, Akka actors, Finagle RPC services, Scala collections,
Neo4j graph queries, fork/join and STM programs. It is widely used in JIT-compiler research, for
example evaluating GraalVM. The five we profile (official names in brackets):

| Group | Benchmark | What it does | Re-characterised here |
|---|---|---|---|
| web | `finagle-http` | a Finagle HTTP server (Twitter's RPC framework on Netty) handles many small concurrent client requests — typical async request/response server work | no (no dataset by design) |
| web | `finagle-chirper` | a simulated microblogging service on Finagle, master node plus cache nodes; clients post "chirps" and fetch feeds. Stresses RPC, futures and shared state | no (486 KB of tweet text) |
| spark | `page-rank` | iterative PageRank over a graph using Spark RDDs: data-parallel, shuffle-heavy, allocation-intensive | **yes** → §5 |
| spark | `naive-bayes` | trains a multinomial Naive Bayes classifier with Spark MLlib; vectorised math and aggregation | **yes** → §6 |
| database | `neo4j-analytics` | analytical Cypher queries against an *embedded* Neo4j movie database; pointer chasing and query execution | **yes** → §2 |

**DaCapo** is the long-standing academic JVM suite, first released in 2006 by Blackburn et al.,
with releases named after composers. **Chopin** (23.11, November 2023) was the first major update
since *Bach* in 2009 and has about 22 benchmarks built from large, current open-source
applications — Cassandra, Kafka, Tomcat, Spring, H2, Lucene, Eclipse. Chopin adds three things:
**latency metrics** for request-based workloads alongside total execution time, **documented
minimum heap sizes** for fair GC comparisons, and **per-benchmark characterisation statistics**
(allocation rate, IPC, cache behaviour) to help pick representative subsets.

| Benchmark | What it does | Re-characterised here |
|---|---|---|
| `cassandra` | an Apache Cassandra NoSQL server driven by a YCSB workload (reads and updates): storage engine plus networking stack | **yes** → §3 |
| `tomcat` | an Apache Tomcat servlet container serving its sample web apps (servlets and JSP): a classic web-server workload | no (14 MB of sample content) |
| `kafka` | an Apache Kafka broker with producer/consumer clients streaming messages: log-structured I/O and messaging | **yes** → §4 |

In Chopin all three are request-based and latency-sensitive, and report per-request latency
distributions as well as total execution time, which is what makes them useful as "server-like"
comparison points at all.

**Why they still needed re-characterising.** The suites' *software* is real; their *inputs* are
not sized like production (`../JVMbench/README.md` §10). And all five JVM-suite server benchmarks
run their load generators as threads **inside the measured JVM**, so a capture of the suite
benchmark mixes client and server work. Both problems are what this study fixes, one workload at
a time, by running the same software as a standalone server on a realistic dataset with the
client outside the fence.

## 1. Method, shared by every workload here

- **Server in the fence.** The server process is launched as
  `measured.slice/realdata-<workload>-rN.scope` with `taskset` to the measured cores 4–11,
  through `run_dcperf_profile.sh` with `SUITE=realdata BENCH=<module>` — the same orchestrator,
  isolation shield, foreign-`perf` guard and counter rotation as DCPerf and the JVM suites.
  Concretely, what is inside the fence and what is outside it, per workload:

  | Workload | Inside the fence (measured cores 4–11) | Outside (housekeeping cores 0–3, 12–15) |
  |---|---|---|
  | neo4j-livejournal | `neo4j console` — the whole Neo4j JVM, including its bolt server threads | `neo4j_client.py` (5 processes × 5 sessions) |
  | cassandra-ycsb20m | `cassandra -f -R` — the whole Cassandra JVM | YCSB `bin/ycsb.sh run` (24 threads) |
  | kafka-20g | `kafka-server-start.sh` — the broker JVM | 3 producer + 6 consumer perf-test JVMs |
  | pagerank-livejournal, naivebayes-rcv1 | the whole `spark-shell` JVM (`local[8]`: driver and executors in one process) | nothing — a batch job has no client |
  | video-4k | DCPerf's `run.sh` and every `ffmpeg` it spawns | nothing — a batch |
  | *(reference: feedsim)* | `LeafNodeRank` | `run.sh`, `search_qps.sh`, `DriverNodeRank` |

  In every case the collectors themselves (`perf`, the 10 Hz pollers, the TMA reader) also run
  on the housekeeping cores, so they never appear in the fence's counts.

  **How it is done in code.** Two mechanisms, both in the module's `bench_start`:
  `sudo systemd-run --collect --scope --slice=measured.slice --unit="$UNIT" -- taskset -c
  "$CPUS_MEASURED" <server>` puts the server and every child it forks into one cgroup under
  `measured.slice` (which the isolation shield has pinned to cores 4–11) *and* pins its
  affinity; the client is started as a plain background process with `taskset -c "$CPUS_HOUSE"`,
  inheriting `user.slice`, which the same shield has pinned to the housekeeping cores. The
  cgroup path is written to `.server_cg` and is exactly what `perf stat --for-each-cgroup`
  counts, so a metric can only include work done by the server.
- **Client outside.** The load generator runs on the housekeeping cores (0–3, 12–15) in
  `user.slice`, where the litellm proxy sits during agent campaigns and the FeedSim driver sat.
  This is what the suite benchmarks could not offer: their clients are threads inside the
  measured JVM, so their context-switch and instruction-supply numbers include client work.
- **Steady state.** Server up → client starts → a warm-up (page cache, JIT) → **a liveness
  check on the fence** → capture. The check reads the fence cgroup's `cpu.stat` over 10 s and
  requires at least 1 core of CPU time (0.5 for the Kafka broker, whose data path is kernel
  zero-copy, and "at least half the encoder pool for 8 consecutive seconds" for the video
  batch). It is a floor that catches a server which came up but is not serving — it is *not*
  the steady-state criterion, which is gate **D4** after the fact: D4 smooths the 10 Hz load
  series into 10 s means and fails the capture if the first fifth and the last fifth differ by
  more than 25 %. In practice the real servers ran far above the floor (Neo4j 3.8, Cassandra
  6.2, Spark 6.7–7.7, video 8.0 cores) and D4 drift was 0.2–5.3 %. The client outlives the capture by 60 s and writes its own
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

## 6b. video-4k

**Input.** Two Netflix 4K test sequences from Xiph's freely licensed collection (the set DCPerf
names, obtained without the CDVL registration the original *El Fuente* cuts need): *Boat*
(301 frames, 3.7 GB raw) and *FoodMarket* (601 frames, 7.4 GB raw), 4096×2160 at 60 fps,
8-bit 4:2:0 — against the six 51-frame 1080p shots the earlier capture used. The runner is
DCPerf's own, unchanged (`VT_CUTS` only points its `datasets/cuts` at the new directory): it
downscales each source into the 720p → 144p ladder and encodes every rung and the source with
SVT-AV1 at preset 6, eight encoders in parallel. Because the downscale of 4K sources saturates
the cores for a while on its own, the module now waits for the runner's encode-stage marker
before judging steady state.

**Validation:** D1–D5 and D7 pass, mean load 7.97 cores, D4 drift 0.2 %, residual ≤ 2.6 %.
The batch is dominated by the 4K and 1080p encodes (minutes each), so a 180 s window sits
inside them.

**Toy versus realistic** (whole-runtime values):

| Metric | six 2 s 1080p shots | two 4K sequences | ratio |
|---|---|---|---|
| IPC | 2.62 | 2.46 | 0.94× |
| Branch MPKI | 2.27 | 1.37 | 0.60× |
| Branch-direction MPKI | 2.20 | 1.33 | 0.60× |
| BTB MPKI (BAClears) | 0.050 | 0.031 | 0.62× |
| L1I MPKI (code-read) | 11.9 | 7.6 | 0.64× |
| uop-cache (DSB) MPKI | 53 | 43 | 0.80× |
| DSB coverage (%) | 57 | 64 | — |
| L1D-load MPKI | 4.7 | 5.4 | 1.1× |
| L2-load MPKI | 0.17 | 0.47 | 2.8× |
| LLC MPKI | 0.09 | 0.40 | 4.6× |
| DRAM read (GB/s) | 4.7 | 8.0 | 1.7× |
| Context switches (/CPU-s) | 320 | 71 | 0.22× |

The same shape as the other data-bound workloads, milder: a 4K frame's reference and
reconstruction buffers no longer fit the L2, so L2 and LLC misses rise 3–5× and DRAM traffic
1.7×, while the front end gets *easier* — the short 1080p batch was dominated by its tiny
low-resolution rungs (144p–540p), where per-block control flow outweighs pixel work; on 4K
frames the encoder spends its time in long straight-line kernels, branch misses fall by 40 %
and context switches by 78 %. The encoder was never the problem; the two-second shots were.

## 7. What the six re-characterisations say together

Six of the ten server benchmarks have now been profiled twice with the same instrument: as
the suite ships them, and with the same software on a dataset of realistic size and shape
(`plots/paper_v1/realdata_pairs.png`, values in `realdata_pairs_numbers.csv`). Every one of
them moved, and they moved in two distinct ways.

**Data-bound workloads moved on the memory axes.** Cassandra, PageRank, Naive Bayes and the
video encoder are computations over their data, and the toy datasets fit the caches: L2/LLC
miss rates and DRAM traffic rose by 2–5× (Cassandra, PageRank, video) to 25–80× (Naive
Bayes), IPC fell by 6 % to a half, and four of the six realistic versions now read 8–26 GB/s
from DRAM, more than any suite benchmark except FeedSim. The suite versions were measuring
the cache hierarchy's ability to hold a toy, not the algorithm.

**Serving workloads moved on the front end and the OS.** Neo4j and Kafka, re-run as real
servers with clients outside the fence, changed less in their memory numbers and more in
instruction supply and context switching: the Neo4j server mispredicts 4×, misses the BTB 36×
and switches 28× as often as the in-process movie-graph benchmark; the Kafka broker misses
the L1I 3× as often and switches 5× as often as DaCapo's producer burst, while its memory side
got *lighter* because the payload bytes never touch its user-space code. Here the toy was
measuring the wrong process — the in-process client — as much as the wrong dataset.

**The Server family as a whole moves away from the agentic profile.** Replacing the five suite
benchmarks by their realistic versions (`SERVER_SET=realistic` in the three-violin grid,
`multi_server_compact_realistic.png`) shifts the Server medians: IPC 1.88 → 1.56, L1I
14 → 20 MPKI, DRAM 5.2 → 7.6 GB/s, context switches 2 900 → 12 900 per CPU-second. On every
one of those axes the agentic 36 sits on the *other* side (IPC 1.90, L1I 12.8, DRAM 1.05,
549 switches), so the distance between "server" and "agent" grows when the servers are real.

**Which axes move most when the Server family becomes realistic.** fig02 and fig03 are the same
grid with the same SPEC and Agentic violins; only the Server violin differs, by exactly the six
swapped workloads. Comparing the two Server medians ranks the axes (ratio = realistic ÷ suite;
the last two columns are the other two families for scale):

| Metric | Server, suite set | Server, realistic set | ratio | agentic | SPEC |
|---|---|---|---|---|---|
| **Context switches (/CPU-s)** | 2 934 | **12 900** | **4.4×** | 1 012 | 4.5 |
| **LLC MPKI** | 0.111 | **0.234** | **2.1×** | 0.182 | 0.100 |
| **DRAM read (GB/s)** | 5.21 | **7.82** | **1.5×** | 1.05 | 1.68 |
| L1I MPKI (code-read) | 14.0 | 19.9 | 1.4× | 12.8 | 0.98 |
| BTB MPKI (BAClears) | 0.54 | 0.77 | 1.4× | 0.64 | 0.015 |
| L1D-load MPKI | 6.50 | 8.55 | 1.3× | 4.27 | 6.71 |
| **IPC** | 1.88 | **1.56** | **0.83×** | 1.90 | 2.41 |
| uop-cache (DSB) MPKI | 51.8 | 47.2 | 0.91× | 39.3 | 11.1 |
| Branch-direction MPKI | 1.33 | 1.43 | 1.07× | 3.36 | 1.04 |
| L2-load MPKI | 0.579 | 0.615 | 1.06× | 0.496 | 0.693 |
| DSB coverage (%) | 60.1 | 61.9 | 1.03× | 70.9 | 92.5 |
| Branch MPKI | 1.51 | 1.51 | 1.00× | 3.99 | 1.18 |

The PI's reading of the two figures — that IPC, LLC, DRAM read and context switches change most —
is right on three of the four and right in spirit on the fourth. Context switches, LLC misses and
DRAM traffic are the three largest moves by magnitude (4.4×, 2.1×, 1.5×). IPC moves less in
magnitude (0.83×, seventh by ratio) but it is the one number that unambiguously gets *worse* and
it moves the whole violin, which is why it reads as a large change: the realistic Server median
drops from 1.88 to 1.56, from just below the agentic 1.90 to clearly below it. Two axes barely
move at all — branch MPKI and DSB coverage — which is the useful negative result: **dataset size
changes how a server touches memory and how often it is interrupted, not how predictable its
branches are**. That is also why the agentic family keeps the branch axis to itself.

A word on "worse": higher DRAM bandwidth or more context switches are not defects, they are what
a real server does. The honest statement is that the suite versions understated how
memory-resident and how OS-involved these servers are, by factors of 1.5 to 4.4.

**The agentic finding is unchanged.** Ranking the agentic median against SPEC and the ten
server values under either set, it is first on exactly one metric — branch-direction
misprediction, 3.36 MPKI against FeedSim's 3.32 — and between 2nd and 10th on the other
eleven. The realistic servers push the agentic family further *down* the memory rankings
(L1D 9th → 10th, L2 8th → 10th, LLC 4th → 6th), which sharpens the earlier statement: what is
distinctive about an agent is not that it is instruction-hungry or memory-heavy, both of which
real servers do more of, but that its branches are the least predictable of any workload
measured while it touches almost no data.

**Caveats that stay.** One profiling run per counter group per workload, n = 1 run-to-run
(`../JVMbench/README.md` §7). The Neo4j operating point is client-limited by the Python driver
(the server ran at 3.8 of 8 cores); Cassandra's throughput fell by a third across its nine
passes as the store accumulated updates; Kafka's broker runs at 0.7 cores because a broker's
data path is kernel zero-copy, and 15 % of the partition's busy time is unfenced loopback
network work. All stores are memory-resident (21 GB Cassandra, 2.9 GB Neo4j, 21 GB Kafka window
against 62 GB RAM) — realistic in shape and far beyond any cache, but not the disk-bound regime
of a node holding terabytes. The larger graph the mentor named, `twitter-2010` (1.5 B edges),
would need more disk than this box has free and is the natural next point for Neo4j and
PageRank if the memory side is to be pushed further.

## 8. Figures and files

**How to read fig01 (the pair figure).** In each panel a workload is one row: the **open circle**
is the suite benchmark as shipped, the **green circle** the same software on the realistic
dataset, and the line between them is a **connector with an arrowhead at the realistic end** — it
shows which way and how far the workload moved. It is not an error bar, a range or a
distribution; each end is a single number, that workload's metric over its whole runtime. The two
**dashed vertical lines** are the median of the 26 SPEC per-benchmark values (blue) and of the 36
agentic per-task values (red) — the same whole-runtime statistic as every circle, taken across the
workloads of those families, and the same numbers the SPEC and Agentic violins are centred on in
fig02 and fig03. They are drawn so a reader can see where a server sits relative to the two
families in the main comparison, and whether the dataset swap moved it across one of them: it
does, Cassandra crosses the agentic DRAM line and Naive Bayes crosses both on the cache metrics.

### CSVs for replotting (for Jeferson, 2026-09-21)

Everything drawn in this study is in git as plain CSV, so the figures can be rebuilt from
another machine with no access to the raw captures. All paths are inside
`charts/v1_2026-09-21_realistic-datasets/Raw data/`:

| File | Rows | What it is |
|---|---|---|
| `runtime_votes.csv` | 1 248 | **the master table**: `family, subgroup, workload, metric, value, windows, runs` — one whole-runtime value per workload and metric, 78 workloads × 16 metrics, all six families (SPEC 26, agentic 36, DCPerf 2, Renaissance 5, DaCapo 3, RealData 6) |
| `workload_index.csv` | 78 | **how to group them**: `workload, family, subgroup, side, in_suite_server_set, in_realistic_server_set, pairs_with, pair_role, dataset`. Join on `workload` |
| `server_set_shift.csv` | 12 | per metric: Server median under the suite set, under the realistic set, their ratio, and the SPEC and agentic medians (the §7 table) |
| `realdata_pairs_numbers.csv` | 72 | fig01 exactly: per (workload, metric) the `toy` and `real` values, `spec` and `agentic` medians, and `ratio` |
| `multi_server_compact_realistic_numbers.csv`, `multi_server_compact_numbers.csv` | — | fig02 / fig03 exactly: per (metric, side) n / min / max / median / mean / sd, plus one row per Server benchmark |
| `realdata_per_window_rows.csv.gz`, `timeseries_realdata.csv.gz` | 142 410 each | the per-window values behind the realistic workloads, the second in time order — only needed for a *different* aggregation |

**Recipe for the three violins**, with no aggregation step required, because the values are
already per workload:

```python
import pandas as pd
v = pd.read_csv("runtime_votes.csv")
ix = pd.read_csv("workload_index.csv")
d = v.merge(ix[["workload", "side", "in_realistic_server_set"]], on="workload")
ipc = d[d.metric == "IPC"]
spec    = ipc[ipc.side == "SPEC"].value                                   # 26 points
agentic = ipc[ipc.side == "Agentic"].value                                # 36 points
server  = ipc[(ipc.side == "Server") & (ipc.in_realistic_server_set == 1)].value   # 10 points
# swap in_realistic_server_set -> in_suite_server_set for the suite version of the Server violin
```

The pair figure is the same join with `pairs_with` and `pair_role`, or simply
`realdata_pairs_numbers.csv`, which already has both ends of every pair on one row.
`local_agents/kit/plot/export_server_set_shift.py` regenerates the index and the shift table
from `runtime_votes.csv` alone, so they cannot drift from the master.

| Figure | What |
|---|---|
| `plots/paper_v1/realdata_pairs.{png,pdf}` | 12 metrics; per metric the six workloads as toy → realistic pairs with SPEC and agentic medians as reference lines (`realdata_pairs_numbers.csv` has every value and ratio) |
| `../JVMbench/plots/paper_v1/multi_server_compact_realistic.{png,pdf}` | the three-violin grid (SPEC · Server · Agentic) with the six suite benchmarks replaced by their realistic versions; the suite-set version is `multi_server_compact` |
| `charts/v1_2026-09-21_realistic-datasets/` | the chart pack (figures, every number, scripts, READMEs in every subfolder); the multi-suite pack `../JVMbench/charts/v4_2026-09-21_realistic-server-set/` carries the realistic-set grid as fig01b |

| What | Where |
|---|---|
| Orchestrator (shared) | `local_agents/kit/dcperf/run_dcperf_profile.sh` with `SUITE=realdata BENCH=<module> WORKLOAD=<name>` |
| Modules | `bench_neo4j.sh` + `neo4j_client.py`, `bench_cassandra.sh`, `bench_kafka.sh`, `bench_spark.sh` + `spark/{pagerank,naivebayes}.scala`, `bench_video_transcode.sh` (`VT_CUTS`) |
| One-time builds | `setup_neo4j_livejournal.sh`, `setup_cassandra_ycsb.sh`, `setup_kafka.sh` |
| Captures (gitignored) | `data/realdata_<workload>/run_1..9`; derived rows `data/l3_study/` |
| Infrastructure (outside the repo) | `~/realdata-infra/`: `neo4j/` (5.26.12 + store), `cassandra/` (5.0.9 + 21 GB store), `kafka/` (4.3.1 + 20 GB log), `spark/` (3.5.9), `ycsb/` (0.17), `venv/` (Python driver), `datasets/` (LiveJournal CSV + edge list, RCV1, 4K clips), `downloads/` |
| Validation / derivation | `validate_dcperf.py` and `derive_dcperf.sh` with `SUITE=realdata DATA=local_agents/RealData/data` |
