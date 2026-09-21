# Realistic-dataset chart pack — v1_2026-09-21_realistic-datasets

Five server benchmarks profiled twice with the same instrument: as their suite ships them
(DaCapo cassandra and kafka; Renaissance neo4j-analytics, page-rank, naive-bayes) and as the
same software on a dataset of realistic size and shape (Cassandra 5 + YCSB on 20 M rows, a
Kafka 4 broker with a 21 GB retention window, a Neo4j 5 server on the 69 M-edge LiveJournal
graph, Spark PageRank on that graph, Spark Naive Bayes on the 518 k-document RCV1-v2 corpus),
plus DCPerf's video transcoder on 4K sources where profiled. Method, receipts, validation and
the write-up: `../../README.md`. Each subdirectory has its own README.

| Fig | File stem | What it shows |
|---|---|---|
| fig01 | `fig01_realdata_pairs` | 12 metrics; per metric each re-characterised workload as a pair: suite benchmark (open circle) -> same software on a realistic dataset (green), with the SPEC and agentic medians as reference lines |
| fig02 | `fig02_agg_compact_server_realistic` | the three-violin grid (SPEC 26 · Server 10 · Agentic 36) with the re-characterised suite benchmarks replaced by their realistic versions; one whole-runtime value per workload |
| fig03 | `fig03_agg_compact_server_suite` | the same grid with the ten suite benchmarks as shipped, for comparison |

**Rule for every value:** one number per workload = the metric over the workload's whole runtime
(raw counters summed over every window, ratio taken once; mentor's rule 2026-09-15). Server in the
fence, load generator outside on the housekeeping cores; nine dedicated-group passes per workload,
run-to-run repetition n = 1.
