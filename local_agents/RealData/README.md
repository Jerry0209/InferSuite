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
| `cassandra-ycsb20m` | DaCapo `cassandra` (10 000 rows) | YCSB CoreWorkload A on 20 000 000 × 1 KB rows (≈ 20 GB) | store loading |
| Spark PageRank / Naive Bayes | Renaissance `page-rank` (7.6 M-edge crawl), `naive-bayes` (replicated sample) | LiveJournal graph; RCV1-v2 corpus | planned |
| Kafka | DaCapo `kafka` (1 M-message bursts) | sustained produce/consume against a 20 GB log | planned |
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
