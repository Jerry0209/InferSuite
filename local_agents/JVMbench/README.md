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

All eight benchmarks profiled cleanly (nine counter passes each, ~1 500 windows per pass) and
pass every validation gate.

> **Correction, later on 2026-09-14.** `cassandra` was first reported as excluded on a
> steady-state failure. That was **our gate's defect, not the benchmark's**, and the capture has
> been reinstated. See [§8](#8-the-cassandra-false-alarm-and-the-gate-fix) for the evidence and
> the fix; every figure and number below includes cassandra.

Values are one per workload, **computed over the workload's whole runtime** (the mentor's rule,
2026-09-15, §9): the raw counters are summed over every window and the ratio is taken once —
IPC = total instructions / total cycles, MPKI = 1000 × total events / total co-counted
instructions, and so on. Columns are the ten server benchmarks; SPEC and Agentic are their
family medians of 26 and 36 such values. Every value is in
`plots/paper_v1/multi_server_compact_numbers.csv` and `data/l3_study/runtime_votes.csv`.

| Metric | SPEC | Agentic | FeedSim | Video | chirper | fin-http | naive-bayes | neo4j | page-rank | cassandra | kafka | tomcat |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| IPC | 2.413 | 1.904 | 1.82 | 2.619 | 1.93 | 1.423 | 3.272 | 3.265 | 2.149 | 1.046 | 1.422 | 1.373 |
| Branch MPKI | 1.176 | 3.994 | 4.685 | 2.271 | 1.333 | 0.5785 | 0.4222 | 0.4283 | 1.306 | 1.679 | 1.887 | 2.829 |
| Branch-direction MPKI | 1.036 | 3.356 | 3.324 | 2.198 | 1.105 | 0.3639 | 0.369 | 0.4174 | 1.293 | 1.371 | 1.645 | 2.467 |
| BTB MPKI (BAClears) | 0.01521 | 0.6409 | 1.406 | 0.04953 | 0.7227 | 1.698 | 0.04461 | 0.02002 | 0.03441 | 1.738 | 0.3614 | 2.101 |
| L1I MPKI (code-read) | 0.9834 | 12.79 | 5.667 | 11.86 | 25.5 | 52.25 | 1.578 | 5.435 | 1.087 | 61.91 | 16.21 | 38.92 |
| uop-cache (DSB) MPKI | 11.1 | 39.33 | 16.79 | 53.17 | 51.77 | 112.2 | 9.842 | 34.27 | 8.084 | 101.4 | 51.82 | 68.96 |
| DSB coverage (%) | 92.51 | 70.91 | 82.49 | 57.11 | 60.19 | 14.42 | 88.74 | 68.18 | 94.69 | 20.77 | 59.93 | 46.23 |
| L1D-load MPKI | 6.709 | 4.273 | 11.68 | 4.721 | 8.992 | 12.71 | 1.061 | 1.087 | 1.935 | 11.79 | 5.799 | 7.199 |
| L2-load MPKI | 0.6927 | 0.4964 | 4.217 | 0.1666 | 0.5406 | 0.6175 | 0.1291 | 0.292 | 0.6903 | 0.7898 | 0.6407 | 0.4161 |
| LLC MPKI | 0.1001 | 0.1824 | 0.4804 | 0.08751 | 0.07329 | 0.01798 | 0.09248 | 0.1311 | 0.3867 | 0.129 | 0.2983 | 0.03946 |
| DRAM read (GB/s) | 1.683 | 1.053 | 11.67 | 4.694 | 7.679 | 7.594 | 9.944 | 2.226 | 5.717 | 2.009 | 1.009 | 0.7429 |
| Context switches (/CPU-s) | 4.545 | 1012 | 193.7 | 319.9 | 9278 | 4.058e+04 | 817.3 | 620.7 | 227.4 | 4.713e+04 | 5051 | 3.371e+04 |

Fence load during capture (**mean** cores of 8, the statistic that survives a duty cycle):
naive-bayes 6.5, fin-http 6.6, chirper 6.3, page-rank 3.6, neo4j 2.4, **cassandra 1.9, tomcat 1.0,
kafka 0.6** — DaCapo's default sizes do not saturate the partition; per-instruction metrics remain
valid, the workload is simply light. Cassandra also runs a ~50 % duty cycle at 100 ms granularity
(bursts of ~4 cores between sub-second gaps), which is what misled the first steady-state gate
(§8); its **median** 100 ms sample is 0.06 cores while its 10 s means are flat at ~2.

### What the mentor's list adds

**The instruction-supply extreme is the JIT-compiled server, not the agent.** `cassandra` misses
the L1I 4.8× as often as the agentic median (61.9 vs 12.8 MPKI), `finagle-http` 4.1×, `tomcat`
3.0×, and their uop-cache coverage collapses to 21%, 14% and 46% against the agent's 71%. This is
the second time a new family has moved this conclusion: FeedSim alone made the agent look unique
on instruction supply, video transcoding matched it, and JVM servers now sit far beyond it.

**Context switching: the agent is mid-pack among servers.** 1 012 switches per CPU-second looked
extreme next to SPEC's 4.5; `cassandra` runs at 47 000, `finagle-http` at 40 600, `tomcat` at
33 700, `finagle-chirper` at 9 300, `kafka` at 5 100. Caveat that cuts the other way: those JVMs carry their load-generating
client threads *inside* the fence, whereas the agent's model proxy is excluded — so the
comparison, if anything, flatters the agent.

**What still singles the agentic workload out is branch *direction*, and nothing else.** Rank the
agentic median against the other eleven workload-level values on each of the sixteen derived
metrics and it comes first on exactly one: branch-direction misprediction, 3.36 MPKI (FeedSim
3.32 is the only neighbour; `tomcat` 2.47, `kafka` 1.65, `cassandra` 1.37, every other JVM
server 0.36–1.3, and `finagle-http` at 0.36 predicts better than SPEC). On every other axis it
ranks 4th to 10th of 12 — derived first under the window-median rule, re-derived under the
whole-runtime rule (§9), the same single axis under both. The mechanism reads naturally: servers run hot loops the predictor learns even though their
*footprint* thrashes the caches (a capacity pathology); an agent runs unfamiliar code briefly —
compilers, test runners, package managers, a new process image every few seconds — so the
predictor never trains (a prediction pathology). Same symptom, "front-end bound", two different
diseases.

**Memory silence did not survive cassandra.** Before the cassandra correction the agentic family
also held the lowest DRAM traffic and the finding was stated as a *combination* of branch
hostility and memory quiet. Under whole-runtime values the agentic 1.05 GB/s ranks 10th of 12:
`tomcat` 0.74 and `kafka` 1.01 read less, `cassandra` 2.0 more. The single-axis claim above is what the twelve workloads support.

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
- **cassandra is duty-cycled**, roughly 50 % idle at 100 ms granularity, and its mean fence load
  of 1.9 cores is flat across the capture. Under the whole-runtime rule its values are naturally
  busy-weighted (an idle window adds almost nothing to either sum); under the older window-median
  rule they were the median of the busy windows, which is why its branch MPKI read 3.3 then and
  1.7 now.

> **Data footprint (2026-09-20).** Every JVM server benchmark here except the two Spark jobs
> works on 20–190 MB of live data, inside or at the edge of the 30 MB L3; only FeedSim carries
> a production-sized (3.5 GB) working set. §10 has the audit and the re-characterisation plan.

## 4. Figures

Two layouts, both in the current chart pack `charts/v3_2026-09-15_runtime-votes/` (every
subdirectory of a pack has its own README). Every per-workload value in them follows the
whole-runtime rule of §9.

- **Three-violin layout (mentor's request): fig01–fig05.** `plots/paper_v1/multi_server_compact`
  is the 12-panel grid with SPEC (26), **Server** (10) and Agentic (36) violins, where Server is
  DCPerf FeedSim and VideoTranscodeBench, Renaissance finagle-http, finagle-chirper, page-rank,
  naive-bayes, neo4j-analytics and DaCapo cassandra, tomcat, kafka — one value each.
  `multi_server_{ipc,frontend,memory,system}` are the per-window companions with columns
  SPEC-int, SPEC-fp, Server, then one column per agentic task; the three reference columns hold
  the per-benchmark whole-runtime values, the agentic columns that task's 100 ms windows.
  `SERVER_MODE=windows` pools the ten benchmarks' windows into the Server column instead.
- **Per-benchmark layout: fig06–fig10.** `multi_agg_compact` keeps SPEC and Agentic violins and
  draws one diamond per server benchmark at its whole-runtime value with a bar for its window
  IQR, so the reader can see which benchmark sits where; `multi_agg_{ipc,frontend,memory,system}`
  give each server benchmark its own per-window column.

Run counts behind every value: §7. The pack's `Raw data/` carries `runtime_votes.csv` (every
value drawn), the per-window rows the scripts read, and time-ordered per-window rows for all
families (`timeseries_<family>.csv.gz`). `v2_2026-09-14_cassandra-reinstated/` is the same
pair of layouts under the previous window-median rule, kept for provenance.

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
| cassandra | 2.63 | 47 050 |
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
in the sweep, all 72 kept (cassandra's nine were briefly excluded and are reinstated, §8).

| Counter group | Metrics it produces | Windows per benchmark |
|---|---|---|
| `fpbr` | IPC, Branch MPKI | ~1 530 |
| `fe_miss` | Branch-direction MPKI, BTB MPKI, uop-cache (DSB) MPKI | ~1 512 |
| `fe_lat` | L1I MPKI (code-read) | ~1 513 |
| `fe` | DSB coverage (%) | ~1 514 |
| `cache` | L1D-load / L2-load / LLC MPKI | ~1 511 |
| `dram_bw` | DRAM read (GB/s) | ~1 534 |
| `priv` | Context switches (/CPU-s) | ~1 544 |

Across the eight benchmarks the per-metric window count runs 1 481 to 1 552, except cassandra's
context-switch metric at 759: its `priv` pass spends half of every 100 ms below the analyzer's
activity floor because the workload is duty-cycled, so the idle half is dropped. A benchmark's value for a metric is computed over that single run's windows — counters summed,
ratio taken once (§9) — with the denominator co-counted over the same windows.

This matches every other family: SPEC is one execution per benchmark with the groups rotating
inside it, the agentic 36 are nine dedicated-group replays of one recorded trajectory each, and
DCPerf is nine executions per benchmark. Run-to-run repetition is **n = 1 throughout** — the
violins show spread across workloads, the per-window figures spread across windows inside one
run, and neither is a reproducibility measurement. Full table and reasoning:
`../DCPerf/README.md` §7.8.

## 8. The cassandra false alarm, and the gate fix

`cassandra` was reported excluded on 2026-09-14, on a steady-state gate failure, and reinstated
the same day. The benchmark was never broken. Recording it because the defect was in our
instrument and because the wrong verdict was written into three files before anyone checked it.

**What the gate did.** D4 asks whether the workload is doing the same amount of work at the end
of a capture as at the start. It took the **median** of the 10 Hz CPU-load samples over the first
fifth of the capture and over the last fifth, and compared them as a percentage of the first.

**Why that fails here.** DaCapo cassandra is duty-cycled at 100 ms granularity: in any given
sample it is either running at about four cores or idle, and roughly half the samples are idle.
Its median sample is therefore 0.03 cores, and a first-to-last difference of 0.01 → 0.65 cores
was reported as **4 627 % drift**. Two separate mistakes compound there. A median asks where the
middle sample fell, which is a statement about duty cycle, not about drift. And a percentage of a
near-zero denominator carries no information at all.

**What the data actually shows.** Averaged over 10 s the load is flat for the whole capture:

```
2.4 1.7 1.7 1.9 2.4 2.0 1.7 1.7 2.4 2.2 1.6 1.7 2.1 2.4 1.7 1.7 1.9 2.2   (cores, run 1)
```

Every pass completed 27 iterations at 34 400–34 900 requests per second before the capture ended.
The earlier smoke run completed all 40 of its iterations at 36 400 per second and exited normally;
it was logged as a failure only because it finished before the steady-state detector could arm,
which is why the sweep used `-n 80`.

**The client exceptions were teardown.** The log fills with YCSB `NullPointerException`s, which
the first reading took as the database collapsing. They begin **0.3 s after the last capture
window closes**, in all nine passes, each at its own end time — that is us stopping the systemd
scope. No counter window contains post-failure data.

| Pass | Last window closes | First client error | Margin |
|---|---|---|---|
| run_1 | 09:10:13.099 | 09:10:13.424 | +0.3 s |
| run_9 | 09:51:52.036 | 09:51:52.356 | +0.3 s |

**The fix** (`local_agents/kit/dcperf/validate_dcperf.py`): D4 now smooths the load series into
10 s means, compares the **mean** of the first fifth against the mean of the last fifth,
normalises by the larger of the two so the statistic is bounded at 100 %, and adds an absolute
idle floor of 0.10 cores — because "alive but no longer working", the failure the gate exists to
catch, is an absolute condition, not a relative one. Verified against synthetic series so the fix
is not merely "make cassandra pass":

| Series | Verdict |
|---|---|
| steady 2 cores | PASS |
| duty-cycled 4 cores / idle (the cassandra shape) | PASS |
| dies halfway | FAIL, 100 % drift |
| decays 2.0 → 0.5 cores | FAIL, 67 % drift |
| alive but idle at 0.03 cores | FAIL, idle floor |
| ramps 1 → 3 cores | FAIL, 59 % drift |

All ten captures, DCPerf and JVM, pass the rewritten gate; cassandra's worst drift is 10.5 % with
a mean load of 1.93 cores.

**What it cost.** One benchmark wrongly dropped from every figure for eight hours, and a
published finding that turned out to depend on the missing point: with cassandra present the
agentic family is no longer the lowest-DRAM workload (§3). The lesson worth keeping is that a
relative test needs an absolute floor, and that a robust statistic can still be the wrong one.

## 9. The aggregation rule (mentor, 2026-09-15)

**Rule.** One number per workload, computed over the workload's whole runtime: sum the raw
counters over every window the workload was measured in, then take the ratio once. For
`727.cppcheck_r`, 10 B instructions over the run in 6 B cycles is IPC 1.67 — one value, and the
SPEC violin is the 26 such values. Not the median of per-window values (which weights every
100 ms equally, busy or idle, and throws away the between-window information), and not a pool
of all windows (which weights a workload by how long it ran). This replaces the window-median
rule used until 2026-09-14 (`../DCPerf/README.md` §7.7 records that rule and why pooling was
rejected; both objections stand, the mentor's rule answers both).

**Implementation.** `local_agents/kit/plot/export_runtime_votes.py` runs the SPEC comparison
kit's own loader (`~/spec26-infra/infra/scripts/extract_metrics.py`: `load_episode` sums every
event over its group's windows with co-counted denominators, `metrics` takes the ratios) over
all four families, so SPEC, the agentic 36, DCPerf and the JVM suites go through one
implementation. Checked: its agentic values equal the banked `comparison_iso36.json` to the
last digit. Output `data/l3_study/runtime_votes.csv`; every figure script takes
`VOTE=runtime` (default) or `VOTE=median` (the old rule, for comparison).

Three details worth knowing:

- **Which windows count.** SPEC: the single episode, restricted to the nine counter groups the
  other families rotate (as the banked comparison does). Agentic, DCPerf, JVM: all nine
  dedicated-group runs are summed, so each metric comes from the run that carried its group and
  IPC pools the eight runs that counted plain cycles and instructions (`priv` counts only the
  user/kernel split). For the agentic tasks the nine runs are nine replays of one trajectory.
- **Busy-weighting is the intended semantics.** A duty-cycled workload's idle windows add almost
  nothing to either sum, so the value describes the work it did. This is why `cassandra`'s
  branch MPKI is 1.7 here and was 3.3 under the median rule, and why SPEC's context switches
  are 4.5 per CPU-second here and rounded to 0 there.
- **What did not change.** The per-window figures still show each agentic task's windows (the
  within-workload variation the mentor wants kept visible); only the per-workload reference
  values moved. The findings in §3 were re-derived under the new rule and the single-axis
  conclusion holds; the DRAM ordering shifted (`cassandra` is no longer the floor, `tomcat` is).

**Not yet refreshed:** the DCPerf-only pack (`../DCPerf/charts/`) and the ML_iso36 paper pack
still use window medians for their per-workload votes; their headline SPEC-vs-agent numbers
(`comparison_iso36.json`) were whole-runtime all along.

## 10. Data footprint audit — what each server benchmark actually works on (mentor question, 2026-09-20)

**Question.** For each server workload: what dataset does it use, how big is it, and is it like
the real thing? If any ran on a small dataset, re-characterise it with a realistic one.

**Method.** Two sources, both banked in `data/footprint_2026-09-20/`. *Static:* the
benchmark's own configuration (Renaissance `benchmarks.properties` and the resources inside its
jars, DaCapo's `.cnf` size definitions and `dat/` trees, DCPerf's `run.sh` and dataset
directory). *Measured:* each benchmark run briefly on the measured cores inside a
memory-accounted systemd scope (`kit/dcperf/measure_footprint.sh`, no perf, no isolation
change) reading the cgroup's `memory.peak`, and for the JVMs the **live heap after garbage
collection** from a GC log — the honest data-footprint number for a JVM, because the resident
size mostly reflects how far the collector let the heap grow. Third, the banked profiling
numbers themselves: a workload whose LLC misses are ~0.1 per thousand instructions and whose
DRAM traffic is ≤ 2 GB/s is telling you its working set fits the 30 MB L3.

**Machine reference:** L1d 48 KB and L2 2 MB per core, L3 30 MB shared, 62 GB RAM.

| Benchmark | What the data is | On disk | Live in memory (measured) | Working set sits in | LLC MPKI / DRAM GB/s (profiled) |
|---|---|---|---|---|---|
| **FeedSim** (DCPerf) | synthetic ranking graph generated at start-up, `graph_scale=21` (2²¹ vertices, 2 M subset), 2 000 objects per request — Meta's production-derived proxy | none (generated) | **3.5 GB steady, 4.8 GB peak** (native, RSS) | DRAM | 0.48 / 11.7 |
| **VideoTranscodeBench** (DCPerf) | six 2-second, 51-frame 1080p shots cut from Xiph `in_to_tree` and `park_joy`, downscaled to 8 resolutions = 48 clips, encoded at several quality points; DCPerf specifies Netflix *El Fuente* (4K) | 908 MB raw y4m | 1.4 GB per SVT-AV1 encode (1080p) | DRAM | 0.09 / 4.7 |
| **finagle-http** | no dataset: 12 000 small HTTP requests × 8 clients per iteration, in-process | 0 | 20 MB | L3 | 0.02 / 7.6 |
| **finagle-chirper** | simulated microblog: 5 000 users, 1 250 requests, tweet text drawn from a 486 KB CSV | 0.5 MB | 30 MB | L3 | 0.07 / 7.7 |
| **page-rank** | SNAP *web-BerkStan* (685 k pages, 7.6 M links, a 2002 crawl), 2 iterations | 20 MB zip (~110 MB text) | 330 MB median, 1.1 GB max | DRAM | 0.39 / 5.7 |
| **naive-bayes** | Spark's 100-row `sample_libsvm_data.txt` (105 KB) replicated 8 000× | 0.1 MB | 1.3 GB median, 1.8 GB max | DRAM | 0.09 / 9.9 |
| **neo4j-analytics** | a movie graph, 70 MB of JSON (32 MB vertices + 38 MB edges); 150 short, 1 long, 12 mutating queries per iteration | 70 MB | 110 MB median (2.3 GB while loading) | L3 / DRAM edge | 0.13 / 2.2 |
| **cassandra** (DaCapo `default`) | YCSB CoreWorkload: **10 000 records × 1 KB**, 200 000 operations per iteration, 50/50 read/update, zipfian | ~10 MB of rows | 160 MB (Cassandra's own structures dominate) | L3 | 0.13 / 2.0 |
| cassandra (DaCapo `large`, not profiled) | 100 000 records, 2 M operations | ~100 MB | 650 MB median, 0.9 GB max | DRAM | — |
| **tomcat** (DaCapo) | Tomcat's bundled sample web applications; 80 000 requests per iteration from 8 clients | 14 MB tree | 20 MB | L3 | 0.04 / 0.7 |
| **kafka** (DaCapo) | Trogdor produce bench: 1 M messages per iteration to 2 topics × 10 partitions at 200 k msg/s, default Trogdor payload | 112 KB config | 190 MB | L3 / DRAM edge | 0.30 / 1.0 |

The DRAM column is offcore read bandwidth over the whole capture; for the two Finagle servers
and naive-bayes it is allocation and GC traffic on a small live set, not a large working set —
their LLC miss rates say so.

**Verdicts.**

- **Realistic by construction:** FeedSim. It carries a multi-gigabyte resident graph and is
  the one benchmark whose data footprint Meta calibrated to production. Keep as is.
- **Real content, unrealistic scale:** VideoTranscodeBench (two-second 1080p shots where the
  specification asks for 4K *El Fuente*), page-rank (a real but 7.6 M-edge crawl; production
  graphs are 10²–10³× larger), neo4j-analytics (a 70 MB movie graph).
- **Not realistic:** cassandra (10 MB of rows against a database built for terabytes; even
  DaCapo's `large` is 100 MB), naive-bayes (a toy sample copied 8 000 times), kafka (one-million
  message bursts on an otherwise empty broker; production brokers stream against hundreds of
  gigabytes of log).
- **Small by nature, not by mistake:** finagle-http, finagle-chirper, tomcat. These are
  request-serving tiers; their design has no dataset, and their footprint is instruction-side
  (which is exactly what the profiling found: L1I 25–52 MPKI, uop-cache coverage 14–60 %). A
  "realistic dataset" for them means a realistic request mix and a real application behind the
  server, not more bytes; that is a different benchmark, not a bigger input.

**Consequence for the findings so far.** The JVM server signature reported in §3 — instruction
supply and context switches as the extremes, memory traffic small — was measured on working
sets that fit or nearly fit the L3. For cassandra, neo4j and kafka the memory side of the
signature is therefore a property of the dataset size, not of the software, and must not be
read as "databases are memory-light". The instruction-side signature is much less exposed to
this: code footprint does not grow with the data.

**Plan for the re-characterisation** (in priority order; disk today 135 GB free, all sizes
fit with margin):

| # | Workload | Realistic dataset | Size | How | Effort |
|---|---|---|---|---|---|
| 1 | Neo4j | SNAP `soc-LiveJournal1` (4.8 M nodes, 69 M edges; store ≈ 10–15 GB) first; SNAP `twitter-2010` (42 M nodes, 1.47 B edges, ≈ 25 GB text, store > 100 GB) is the mentor's example but exceeds comfortable disk and needs hours of import — second step if wanted; LDBC SNB SF10 is the alternative with a standard query set | 1–25 GB raw | standalone Neo4j 5 server in the fence, `neo4j-admin import`, a query driver (k-hop neighbourhoods, shortest paths, PageRank via GDS) on the housekeeping cores; same nine-pass capture | 1–2 days |
| 2 | Cassandra | YCSB 0.17 (the version DaCapo bundles) with **20 M records × 1 KB = 20 GB**, workloads A (50/50) and C (read-only), zipfian | 20 GB | standalone Cassandra 5 in the fence, YCSB client on the housekeeping cores (the DaCapo harness keeps the client in-fence and is limited to 100 k rows) | 1 day |
| 3 | page-rank, naive-bayes | Spark jobs on real inputs: PageRank on `soc-LiveJournal1` (reuse from #1) or `twitter-2010`; Naive Bayes on a real corpus (RCV1-v2, ≈ 800 k documents, ≈ 1 GB libsvm) | 1–25 GB | `spark-submit` of the Renaissance benchmark classes' own algorithms with a file input, in the fence | 0.5 day |
| 4 | Kafka | `kafka-producer-perf-test` / consumer at **20 M × 1 KB messages** (20 GB log, beyond the page cache's comfort), sustained rather than burst | 20 GB | standalone Kafka 3.3 in the fence, producer/consumer on the housekeeping cores | 0.5 day |
| 5 | Video | 4K sources: *El Fuente* / *Chimera* need a CDVL registration (the PI's action), or Xiph's freely licensed Netflix 4K test sequences (`media.xiph.org/video/derf`: Aerial, Boat, FoodMarket …) | 5–20 GB | drop the clips into `datasets/cuts/`, rerun the existing module; encodes take minutes per clip at 4K, so capture length is no longer a constraint | 0.5 day |
| — | finagle-http, finagle-chirper, tomcat, FeedSim | no change | | | |

Each item is a new benchmark harness (server in the fence, client outside, same nine-pass
capture and validation), not a parameter change to the suite benchmark, because Renaissance
and DaCapo hard-wire their inputs. The first two are the ones whose current numbers are least
defensible and whose realistic versions are most likely to change the picture.
