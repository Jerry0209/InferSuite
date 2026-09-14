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
`analyze_l3_windows.py` derivation and the same validator gates. Which cores, what happens to
their SMT siblings and what clock they run at is tabulated in §6.

JVM-specific mechanics (`bench_jvm_common.sh`, `bench_renaissance.sh`, `bench_dacapo.sh`):

- **Launch.** One `systemd-run --scope` under `measured.slice`, `taskset` to the measured
  cores, `java -jar` with the suite's own harness. Renaissance is run with `-t SECONDS` so it
  repeats its operation for at least the capture window plus warm-up; DaCapo with `-n 80`
  iterations, more than the window needs, and the scope is stopped afterwards.
- **Steady state.** JVM start-up and JIT warm-up are a variable-length ramp, so the module waits
  until the fence's CPU rate, averaged over a 10 s moving window, reaches one core, then holds
  a further 45 s before windowing begins. A moving *mean* rather than "every second busy"
  because DaCapo's iterations have a lightly-loaded reload gap between them (cassandra:
  ~2.4 s in every ~7.9 s) that a per-second rule mistakes for the benchmark ending. The 10 Hz poller covers the whole capture and the validator's
  steady-state gate (D4) measures the drift afterwards rather than trusting the hold.
- **JDK 21.** Renaissance runs unmodified. DaCapo Chopin refuses to start `cassandra` on JDK 17+
  unless `-Djava.security.manager=allow` is passed — its own exit message names the flag — so
  the module passes it for every DaCapo benchmark.
- **Deviations from the suites' stock runs:** none in workload parameters. Both suites are run
  with their default sizes; only the number of repetitions is chosen to outlast the capture.
- **Mentor's rule applied:** a benchmark whose first pass cannot reach steady state is
  abandoned, not debugged (`ABORT` in the sweep log).

## 3. Results

Seven of the eight benchmarks profiled cleanly (nine counter passes each, ~1 500 windows per
pass) and pass every validation gate. **DaCapo `cassandra` is excluded**: its capture failed the
steady-state gate (median fence load 0.03 cores) because the run degraded into a ~40% duty
cycle with client `NullPointerException`s once the embedded session dropped, so its per-window
medians describe an idle JVM. Per the mentor's rule it was not debugged; the capture is kept
with the reason on disk (`data/dacapo_cassandra/EXCLUDED`).

Votes are one per workload — the median of that workload's windows — exactly as for SPEC, the
agentic 36 and DCPerf. Columns are suites' benchmarks; SPEC and Agentic are their family
medians. Ratios to SPEC and every vote are in `plots/paper_v1/multi_agg_compact_numbers.csv`.

| Metric | SPEC | Agentic | FeedSim | Video | chirper | fin-http | naive-bayes | neo4j | page-rank | kafka | tomcat |
|---|---|---|---|---|---|---|---|---|---|---|---|
| IPC | 2.185 | 1.749 | 1.725 | 2.62 | 1.954 | 1.423 | 3.601 | 3.297 | 2.09 | 1.358 | 1.333 |
| Branch MPKI | 0.8473 | 4.301 | 4.865 | 2.265 | 1.26 | 0.5337 | 0.3084 | 0.4054 | 1.127 | 0.5275 | 2.525 |
| Branch-direction MPKI | 0.8249 | 3.597 | 3.379 | 2.186 | 1.043 | 0.3222 | 0.274 | 0.3936 | 1.106 | 0.4268 | 2.265 |
| BTB MPKI (BAClears) | 0.007845 | 0.7746 | 1.635 | 0.0477 | 0.668 | 1.699 | 0.0342 | 0.0135 | 0.0233 | 0.2433 | 2.283 |
| L1I MPKI (code-read) | 0.8454 | 15.63 | 5.995 | 12.03 | 25.46 | 52.69 | 0.7955 | 5.512 | 0.4434 | 18.44 | 43.79 |
| uop-cache (DSB) MPKI | 9.279 | 46.91 | 18.02 | 54.1 | 51.77 | 113.3 | 7.075 | 38.68 | 5.607 | 65.08 | 76.84 |
| DSB coverage (%) | 93.9 | 66.12 | 82.17 | 56.67 | 60.13 | 13.31 | 91.95 | 63.1 | 96.15 | 43.69 | 37.55 |
| L1D-load MPKI | 8.129 | 4.839 | 11.73 | 4.601 | 9.044 | 12.8 | 0.9983 | 1.085 | 1.838 | 6.23 | 7.068 |
| L2-load MPKI | 0.3344 | 0.5454 | 4.238 | 0.1511 | 0.5229 | 0.6123 | 0.1045 | 0.311 | 0.7694 | 0.6274 | 0.3948 |
| LLC MPKI | 0.0429 | 0.1439 | 0.4793 | 0.0663 | 0.0618 | 0.0133 | 0.07565 | 0.1185 | 0.3806 | 0.297 | 0.0284 |
| DRAM read (GB/s) | 1.517 | 0.4567 | 11.5 | 3.802 | 6.681 | 6.613 | 8.89 | 1.643 | 4.081 | 0.738 | 0.5676 |
| Context switches (/CPU-s) | 0 | 549.4 | 190.9 | 159 | 8415 | 4.1e+04 | 180 | 440 | 106.2 | 3853 | 3.695e+04 |

Fence load during capture (median cores of 8): fin-http 6.7, chirper 6.5, naive-bayes 7.6,
page-rank 3.0, neo4j 2.1, **tomcat 0.9, kafka 0.5** — DaCapo's default sizes do not saturate the
partition; per-instruction metrics remain valid, the workload is simply light.

### What the mentor's list adds

**The instruction-supply extreme is the JIT-compiled server, not the agent.** `finagle-http`
misses the L1I 3.4× as often as the agentic median (52.7 vs 15.6 MPKI), `tomcat` 2.8×, and
their uop-cache coverage collapses to 13% and 38% against the agent's 66%. This is the second
time a new family has moved this conclusion: FeedSim alone made the agent look unique on
instruction supply, video transcoding matched it, and JVM servers now sit far beyond it.

**Context switching: the agent is mid-pack among servers.** 549 switches per CPU-second looked
extreme next to SPEC's zero; `finagle-http` and `tomcat` run at ~40 000, `finagle-chirper` at
8 400, `kafka` at 3 900. Caveat that cuts the other way: those JVMs carry their load-generating
client threads *inside* the fence, whereas the agent's model proxy is excluded — so the
comparison, if anything, flatters the agent.

**What still singles the agentic workload out is branch *direction* — and memory silence.**
Its branch-direction MPKI of 3.6 is the highest of all twelve workloads measured (FeedSim 3.4
is the only neighbour; every JVM server is at 0.3–2.3, `finagle-http` at 0.32 predicts better
than SPEC), while its DRAM traffic, 0.46 GB/s, is the lowest. The mechanism reads naturally:
servers run hot loops the predictor learns even though their *footprint* thrashes the caches
(a capacity pathology); an agent runs unfamiliar code briefly — compilers, test runners,
package managers, a new process image every few seconds — so the predictor never trains (a
prediction pathology). Same symptom, "front-end bound", two different diseases.

**Rahul's Spark and Neo4j picks are the compute corner, not the serving corner.** `naive-bayes`
and `neo4j-analytics` post the highest IPC of anything measured (3.6, 3.3), SPEC-grade branch
behaviour, and 92–96% uop-cache coverage on the Spark pair; they behave like SPEC with more
memory bandwidth. Useful as a reference, but not evidence about serving.

### Caveats
- **In-fence clients** (all five web/database JVM benchmarks): context-switch and
  instruction-supply figures include the client threads. They are consistent with each other,
  not with FeedSim, where the client was excluded by construction.
- **kafka's unfenced residual is 17.8%** (gate D5; every other workload ≤ 2.5%). At 0.46 cores
  of fence load, the loopback network stack's kernel work — softirq that belongs to no cgroup —
  is a visible share of what ran on the measured cores; kafka's fence totals are lower bounds.
- One run per benchmark, JDK 21, eight fixed-frequency cores; no run-to-run repeats yet.

## 4. Figures

`plots/paper_v1/multi_agg_compact` is the 12-panel grid over every family profiled so far;
each external benchmark is one marker at its vote, grouped under its suite (see the unit rule in
`../DCPerf/README.md` §5 and §7.7). `plots/paper_v1/multi_agg_{ipc,frontend,memory,system}`
are the per-window companions with one column per benchmark (each column a distribution over
that benchmark's windows; only the two SPEC columns are distributions over benchmark medians). Chart packs live under `charts/`.

## 5. Files

| What | Where |
|---|---|
| Sweep driver (the mentor's list, in order) | `local_agents/kit/dcperf/sweep_jvm_suites.sh` |
| Modules | `local_agents/kit/dcperf/bench_{jvm_common,renaissance,dacapo}.sh` |
| Captures (gitignored) | `local_agents/JVMbench/data/{renaissance,dacapo}_<benchmark>/run_1..9` |
| Derived rows | `local_agents/JVMbench/data/l3_study/{renaissance,dacapo}_rows_long.csv` |
| Suites (outside the repo) | `~/jvmbench-infra/` — `renaissance-gpl-0.16.1.jar`, `dacapo-23.11-MR2-chopin.jar` + data tree pruned to the three benchmarks used |

## 6. The isolation applied — cores, SMT, clock

Identical to every DCPerf and agentic capture; the full table with its evidence column is
`../DCPerf/README.md` §9. The configuration, in one place:

| What | Applied to every JVM pass (2026-09-14) |
|---|---|
| Machine | Intel Xeon w5-3425, 12 physical cores / 24 hardware threads, kernel 6.17.0-1030-oem, `intel_pstate` (HWP active), `intel_idle` |
| Measured cores | logical CPUs **4–11** = 8 physical cores, one hardware thread each; the single JVM runs in `measured.slice/<suite>-<bench>-rN.scope` with `taskset` to 4–11 |
| Housekeeping cores | logical CPUs **0–3, 12–15** (physical cores 0–3, both threads): `system.slice`, `user.slice`, `init.scope`, every IRQ (`0xf00f`), the unbound workqueues (`0xf00f`), the perf writers and pollers |
| SMT | hardware threads **16–23** (siblings of 4–11) **offlined by the orchestrator at sweep start**, restored on exit — logged for all eight sweeps (`SMT siblings offlined: 16 … 23`); the `/proc/stat` witness in every run directory lists `cpu0`–`cpu15` only, which proves it from the data |
| Clock | governor `performance` on all CPUs, `no_turbo=1` (4.4 GHz turbo off), measured cores pinned to the **base 3.2 GHz** (`scaling_min_freq = scaling_max_freq = 3200000` kHz), verified per core by ISO-PROOF before each pass |
| Idle states | not restricted (C1/C1E/C6 enabled), as in the SPEC, agentic and DCPerf captures |
| Memory / OS | THP `never`, NMI watchdog off, no containers, k3s off; no `nohz_full` / `isolcpus` in this boot |
| Gate | ISO-PROOF before each of the 72 passes: cpusets, clock, workqueue/IRQ masks, foreign-resident scan, then < 2 % busy on the measured cores; every sweep shield logged `PROVEN quiet`, no failure in the whole JVM period |
| PMU | our `perf` only (foreign-perf guard), one counter group per 100 ms window, zero multiplexing, continuous TMA |

**Realised clock.** The pin is a request; `cycles:u + cycles:k` over `task-clock` from the
`priv` pass is what the cores did during the fence's own CPU time
(`local_agents/kit/validate/realised_clock.py`):

| Benchmark | realised GHz | ctx switches / CPU-s |
|---|---|---|
| page-rank / neo4j-analytics / naive-bayes | 3.19 / 3.19 / 3.18 | 227 / 621 / 817 |
| kafka / finagle-chirper | 3.13 / 3.13 | 5 051 / 9 278 |
| finagle-http | 2.91 | 40 575 |
| tomcat | 2.81 | 33 713 |
| cassandra (excluded) | 2.63 | 47 050 |
| *reference: SPEC 26 / DCPerf 2 / agentic 36* | *3.18–3.19 / 3.19 / median 3.17 (min 2.88)* | |

The compute-bound benchmarks realise the pin to within 0.5 %; the wake-heavy servers do not,
and within each of them the window clock falls as the window's switch rate rises
(Spearman −0.97 tomcat, −0.91 cassandra, −0.75 kafka). Inference, not a measured mechanism: a
core woken from C1E/C6 tens of thousands of times a second spends part of its scheduled time
below the pinned clock while it wakes. It is a property of these workloads under settings
identical to every other family (the agentic rubocop task shows the same at 2.88 GHz), and it
does not touch the plotted metrics — IPC uses unhalted cycles, MPKI are per instruction,
switches are per CPU-second. It must be remembered for any throughput or cycles-per-second
claim, and disabling C-states to remove it would break comparability with the SPEC and agentic
captures (taken with C6 enabled), so it was not done.

## 7. How many profiling runs stand behind each benchmark

**Nine — one per counter group — and no metric averages over repeated runs.** The PMU cannot
count every event at once, so a *run* is one JVM execution with one counter group live; the
metric derived from that group comes from that run alone. Eight benchmarks × 9 groups = 72 runs
in the sweep, of which 63 are kept (cassandra's 9 are excluded, §3).

| Counter group | Metrics it produces | Windows per benchmark |
|---|---|---|
| `fpbr` | IPC, Branch MPKI | ~1 530 |
| `fe_miss` | Branch-direction MPKI, BTB MPKI, uop-cache (DSB) MPKI | ~1 512 |
| `fe_lat` | L1I MPKI (code-read) | ~1 513 |
| `fe` | DSB coverage (%) | ~1 514 |
| `cache` | L1D-load / L2-load / LLC MPKI | ~1 511 |
| `dram_bw` | DRAM read (GB/s) | ~1 534 |
| `priv` | Context switches (/CPU-s) | ~1 544 |

Across the seven kept benchmarks the per-metric window count runs 1 481 to 1 552; the excluded
cassandra capture is the outlier at 759 for its worst metric, a consequence of the ~40 % duty
cycle that failed gate D4. A benchmark's vote for a metric is the median over that single run's
windows, with the denominator co-counted in the same window.

This matches every other family: SPEC is one execution per benchmark with the groups rotating
inside it, the agentic 36 are nine dedicated-group replays of one recorded trajectory each, and
DCPerf is nine executions per benchmark. Run-to-run repetition is **n = 1 throughout** — the
violins show spread across workloads, the per-window figures spread across windows inside one
run, and neither is a reproducibility measurement. Full table and reasoning:
`../DCPerf/README.md` §7.8.
