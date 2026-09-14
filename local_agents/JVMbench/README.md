# Renaissance and DaCapo Chopin on P7 — the mentor's "easier server benchmarks"

**Branch:** `dcperf` · **Started:** 2026-09-14 · **Suites:** Renaissance 0.16.1, DaCapo 23.11-MR2 Chopin · **JDK:** OpenJDK 21.0.12

The mentor's steer (2026-09-14): stop spending effort on DCPerf's infrastructure-heavy
benchmarks and profile server workloads that run on one machine out of the box. His list:

| Suite | Category | Benchmark | What it exercises |
|---|---|---|---|
| Renaissance | web | `finagle-http` | Finagle HTTP server + in-process clients (Twitter's RPC stack on Netty) |
| Renaissance | web | `finagle-chirper` | a Twitter-like microblog service on Finagle, with feed generation |
| Renaissance | apache-spark | `page-rank` | PageRank over a graph in an in-process Spark |
| Renaissance | apache-spark | `naive-bayes` | Naive-Bayes classifier training in Spark |
| Renaissance | database | `neo4j-analytics` | graph queries against an embedded Neo4j |
| DaCapo Chopin | server | `cassandra` | an embedded Cassandra node driven by YCSB |
| DaCapo Chopin | server | `tomcat` | embedded Tomcat serving a web application |
| DaCapo Chopin | server | `kafka` | an embedded Kafka broker with producers and consumers |

DCPerf's own study (task choice, method, findings) is in
[`../DCPerf/README.md`](../DCPerf/README.md); these suites are profiled with the same kit and
land in the same figures.

## 1. Why these are the easy ones — and what that buys and costs

Every benchmark above runs **inside a single JVM**: the server, its data and its clients are
all in-process. For our fence discipline that is the simplest possible case — the JVM is the
workload, one cgroup covers it, and there is no load generator to keep off the measured
partition (compare FeedSim, where the driver had to be pinned to the housekeeping cores, or
DjangoBench, whose database and client would each need their own container).

The cost of that convenience is a caveat that has to travel with every number: **the client
is inside the fence.** In `finagle-http`, the request generators share the JVM, the heap and
the measured cores with the server they load. What we characterise is therefore "a server and
its clients on eight cores", not a server alone — a different quantity from FeedSim, where the
client's CPU was excluded by construction. The suites are consistent *with each other* on this,
and the figures say which is which.

## 2. How they are profiled

Identical to DCPerf: `local_agents/kit/dcperf/run_dcperf_profile.sh` with `SUITE=renaissance`
or `SUITE=dacapo`, nine dedicated-group passes per benchmark, the self-sufficient isolation
shield with automatic SMT-sibling handling, ISO-PROOF before every pass, the same
`analyze_l3_windows.py` derivation and the same validator gates.

JVM-specific mechanics (`bench_jvm_common.sh`, `bench_renaissance.sh`, `bench_dacapo.sh`):

- **Launch.** One `systemd-run --scope` under `measured.slice`, `taskset` to the measured
  cores, `java -jar` with the suite's own harness. Renaissance is run with `-t SECONDS` so it
  repeats its operation for at least the capture window plus warm-up; DaCapo with `-n 80`
  iterations, more than the window needs, and the scope is stopped afterwards.
- **Steady state.** JVM start-up and JIT warm-up are a variable-length ramp, so the module waits
  until the fence has been busy for eight consecutive seconds, then holds a further 45 s
  before windowing begins. The 10 Hz poller covers the whole capture and the validator's
  steady-state gate (D4) measures the drift afterwards rather than trusting the hold.
- **JDK 21.** Renaissance runs unmodified. DaCapo Chopin refuses to start `cassandra` on JDK 17+
  unless `-Djava.security.manager=allow` is passed — its own exit message names the flag — so
  the module passes it for every DaCapo benchmark.
- **Deviations from the suites' stock runs:** none in workload parameters. Both suites are run
  with their default sizes; only the number of repetitions is chosen to outlast the capture.
- **Mentor's rule applied:** a benchmark whose first pass cannot reach steady state is
  abandoned, not debugged (`ABORT` in the sweep log).

## 3. Results

RESULTS_PLACEHOLDER

## 4. Figures

`plots/paper_v1/multi_agg_compact` is the 12-panel grid over every family profiled so far;
each external benchmark is one marker at its vote, grouped under its suite (see the unit rule in
`../DCPerf/README.md` §5 and §7.7). `plots/paper_v1/multi_agg_{ipc,frontend,memory,system}`
are the per-window companions with one column per benchmark. Chart packs live under `charts/`.

## 5. Files

| What | Where |
|---|---|
| Sweep driver (the mentor's list, in order) | `local_agents/kit/dcperf/sweep_jvm_suites.sh` |
| Modules | `local_agents/kit/dcperf/bench_{jvm_common,renaissance,dacapo}.sh` |
| Captures (gitignored) | `local_agents/JVMbench/data/{renaissance,dacapo}_<benchmark>/run_1..9` |
| Derived rows | `local_agents/JVMbench/data/l3_study/{renaissance,dacapo}_rows_long.csv` |
| Suites (outside the repo) | `~/jvmbench-infra/` — `renaissance-gpl-0.16.1.jar`, `dacapo-23.11-MR2-chopin.jar` + data tree pruned to the three benchmarks used |
