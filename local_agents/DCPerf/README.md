# DCPerf on P7 — task choice, profiling method, and how it differs from SPEC and the agentic 36

**Branch:** `dcperf` · **Started:** 2026-09-10 · **Profiled so far:** FeedSim (1 of 6)

Suite-level bring-up notes (install recipe, per-benchmark feasibility, traps) live in
[`docs/handoff/dcperf_bringup.md`](../../docs/handoff/dcperf_bringup.md). This document is the
study: which benchmark was picked and why, exactly how it is profiled, and what separates it
from the two populations we already have.

---

## 1. Why FeedSim was chosen first

The mentor's brief asked for a benchmark that is **representative within DCPerf** and likely to
show a **different pattern from both SPEC and the agentic 36**. FeedSim was picked on three
independent grounds.

**It represents the biggest slice of a social-network fleet.** DCPerf maps FeedSim to "object
aggregation, ranking / inference" — the feed-ranking tier. It is a *latency-critical serving*
workload driven to a service-level objective, which is the operational regime most of Meta's
fleet lives in, and the regime neither of our existing populations has: SPEC runs to
completion as fast as it can, and an agent episode is bursty and mostly waiting on a model.

**Its microarchitectural design is deliberately unlike SPEC.** FeedSim does not merely happen
to have a large instruction footprint — it *manufactures* one. The build compiles an
`ICacheBuster` translation unit split into 24 parts into `libicachebuster.a`, and the server is
launched with `--min_icache_iterations=1600000`; the resulting `LeafNodeRank` binary is 56 MB.
DCPerf built this in because production ranking services are front-end bound in a way SPEC's
compute kernels never are. That makes FeedSim the sharpest available test of this thesis's
central claim, which is also about front-end pressure — and it lets us ask a question SPEC
cannot answer: *when the agentic workload looks front-end bound, does it look front-end bound
in the same way a real datacenter service does?*

**It is the only DCPerf benchmark that maps cleanly onto our measurement model** — and, as it
turns out, the only one that runs here at all without new hardware (see the feasibility table
in the bring-up doc: SparkBench needs NVMe-over-TCP storage nodes and a custom kernel,
TaoBench wants CentOS plus a 10–50 Gbps client network, Mediawiki needs HHVM-3.30 which
predates our OS, and VideoTranscodeBench's dataset sits behind a manual registration).
FeedSim ships as two separate binaries — `LeafNodeRank`, the server under test, and
`DriverNodeRank`, the closed-loop load generator — so the split we already use for agent
campaigns transfers exactly: **the workload goes in the measured cgroup fence, the load
generator runs on the housekeeping cores**, which is precisely where the litellm proxy runs
and for the same reason. It is the client, not the thing being measured.

A note on what FeedSim is *not*: it is one workload, not a population. Every figure treats it
that way (§5).

## 2. How it is profiled

The instrument stack is **the same code** the 36 tasks were measured with, not a
reimplementation. `local_agents/kit/dcperf/run_dcperf_profile.sh` sources the agent campaign
runner in a functions-only mode (`run_glm_campaign.sh noop`) and calls its functions directly:

| Reused unchanged | What it does |
|---|---|
| `apply_isolation` / `restore_isolation` | cpuset split, `performance` governor, `no_turbo=1`, THP `never`, all IRQs to the housekeeping cores, snapshot-and-restore |
| ISO-PROOF gate | refuses to start unless the measured cores are provably silent (<2% busy) with the slices actually pinned |
| `GRP[...]` | the nine zero-multiplexing counter groups |
| `cycle_stats` | the shuffled per-window `perf stat --for-each-cgroup` rotation at `WINSEC=0.1` |
| `start_pollers`, `start_tma_cont` | 10 Hz cgroup `cpu.stat` per fence, partition-wide `/proc/stat` witness, continuous PERF_METRICS TMA |
| `analyze_l3_windows.py` | the metric derivations — *literally the same function*, reached by a new `L3_FENCES` / `L3_BASE_PREFIX` override rather than a copy |

One pass per counter group, nine passes, strictly serialised because the PMU is a shared
resource; the same foreign-`perf` guard used by the agent replays refuses to run alongside a
colleague's collectors. The machine is put in the identical topology the 36 tasks were captured
on — measured cores 4–11 with SMT siblings 16–23 offlined — and a topology gate verifies it
before any pass.

**Placement.** DCPerf's `run.sh` is not rewritten. `patch_run_sh.py` regenerates an
instrumented copy with exactly two edits, so every DCPerf flag, thread count, graph scale and
jemalloc setting is used verbatim and only *where the processes run* changes:

1. the control shell pins itself to the housekeeping cores, taking `search_qps.sh` and
   `DriverNodeRank` with it;
2. `LeafNodeRank` is launched into its own systemd scope under `measured.slice` — the same
   mechanism the agent harness gets — with an explicit `taskset` to the measured cores.

**Operating point.** DCPerf defines FeedSim's score as the maximum QPS holding p95 ≤ 500 ms,
and its README asks for CPU boost to be on. Our contract fixes the clock for cross-workload
comparability, so instead of running DCPerf's search we swept fixed QPS points under the exact
isolation used for profiling and took the highest SLA-compliant one
(`calibrate_feedsim.sh`, banked in `data/calibration/`):

| requested QPS | achieved | p95 (ms) | p99 (ms) | SLA p95 ≤ 500 |
|---|---|---|---|---|
| 4 | 4.00 | 405.5 | 407.0 | pass |
| 8 | 7.94 | 405.5 | 407.0 | pass |
| 12 | 11.88 | 427.6 | 755.1 | pass |
| **16** | **15.82** | **479.2** | 489.9 | **pass — operating point** |
| 20 | 19.70 | 688.9 | 825.6 | fail |

Every profiling pass runs at 16 QPS. **This is not a DCPerf score and must never be quoted as
one** — it is an operating point measured on 8 fixed-frequency cores, chosen so the workload
sits in the same SLA-bounded regime DCPerf intends.

**Steady state.** A pass captures counters only inside the fixed-QPS phase: the server is given
its 90 s start-up, `search_qps.sh` runs its warm-up load test, and windowing begins after the
"after warmup" phase marker plus the driver's own ramp. The 10 Hz poller runs across the whole
capture so the steady state can be *checked* rather than assumed.

**Deviations from stock DCPerf**, all deliberate and all recorded in run metadata:
`no_turbo=1` instead of boost-on; a fixed-QPS point instead of the QPS search;
thread pools passed explicitly (`-t 8 -c 6 -s 4`) because `run.sh` sizes them from `nproc` and
`/sys/devices/system/cpu/smt/active`, and on a split partition both misread our machine —
the values passed are DCPerf's own non-SMT formula evaluated for 8 cores; and the docker
cgroup-parent swap is skipped, since FeedSim runs no containers.

## 3. What is structurally different about these three workloads

Before any counter is read, the three populations differ in ways that determine what the
numbers can mean.

| | SPEC CPU 2026 | Agentic 36 (SWE-bench Multilingual) | DCPerf FeedSim |
|---|---|---|---|
| Kind of work | compute kernel, run to completion | an LLM agent repairing a real repository | a ranking service answering requests |
| Driver | none — runs as fast as it can | the model, over an API | a closed-loop load generator at fixed QPS |
| Success criterion | time to finish | did the patch pass the hidden tests | p95 latency under 500 ms |
| Process structure | one long-lived pinned process | a harness plus hundreds of short-lived tool processes (compilers, test runners) in a container | one long-lived multithreaded server |
| Code under measurement | the benchmark's own kernel | mostly *third-party* code the agent chose to run | the service's own binary |
| Where the wall time goes | computing | ~85% waiting on the model | serving, bounded by the SLA |
| Instruction footprint | small by construction | large and constantly changing (new process images) | large **by construction** (ICacheBuster) |
| Fences | single process | tool + harness, merged | server only |
| Off-fence helper | none | litellm proxy, housekeeping cores | load generator, housekeeping cores |

The interesting axis is the **mechanism** behind front-end pressure. The agentic workload gets
it from *churn* — new process images, cold caches, 549 context switches per CPU-second. FeedSim
gets it from *footprint* in steady state — one warm process whose code simply does not fit.
SPEC has neither. That is the comparison these figures are built to make, and it is why a
DCPerf point next to the two violins is worth more than another benchmark on the same axis.

## 4. Results

Nine dedicated-group passes, ~2 500 counter windows each (22 642 windows total), all at the
16 QPS operating point. **Validation passes all seven gates** (`validate_dcperf.py`): nine of
nine groups complete; zero multiplexed counters in any window; steady state to within **2.8%**
drift across every capture (median server load 3.43 of 8 cores); the unfenced residual on the
measured partition bounded at **2.5%** of partition busy time; all twelve displayed metrics
derived from the groups that own them.

The service-level gate (D6) is worth stating on its own, because it answers the obvious
objection to profiling a latency-critical workload: **does the measurement break the thing it
measures?** A confirmation run at the same operating point, with the full capture stack live
(windowed counters, 10 Hz pollers, continuous TMA), achieved **15.96 of 16 requested QPS at
p95 = 472 ms** — inside DCPerf's own 500 ms objective, and indistinguishable from the 479 ms
measured during calibration with no counters running. The instrumentation does not perturb the
workload's service level.

Votes are formed identically for all three families: one value per workload, equal to the
median of that workload's 100 ms windows on the merged fence.

| Metric | SPEC | Agentic 36 | DCPerf feedsim | Agentic/SPEC | feedsim/SPEC |
|---|---|---|---|---|---|
| IPC | 2.185 | 1.749 | 1.725 | 0.8 | 0.79 |
| Branch MPKI | 0.8473 | 4.301 | 4.865 | 5.08 | 5.74 |
| Branch-direction MPKI | 0.8249 | 3.597 | 3.379 | 4.36 | 4.1 |
| BTB MPKI (BAClears) | 0.007845 | 0.7746 | 1.635 | 98.7 | 208 |
| L1I MPKI (code-read) | 0.8454 | 15.63 | 5.995 | 18.5 | 7.09 |
| uop-cache (DSB) MPKI | 9.279 | 46.91 | 18.02 | 5.06 | 1.94 |
| DSB coverage (%) | 93.9 | 66.12 | 82.17 | 0.704 | 0.875 |
| L1D-load MPKI | 8.129 | 4.839 | 11.73 | 0.595 | 1.44 |
| L2-load MPKI | 0.3344 | 0.5454 | 4.238 | 1.63 | 12.7 |
| LLC MPKI | 0.0429 | 0.1439 | 0.4793 | 3.35 | 11.2 |
| DRAM read (GB/s) | 1.517 | 0.4567 | 11.5 | 0.301 | 7.59 |
| Context switches (/CPU-s) | 0 | 549.4 | 190.9 | ∞ | ∞ |

Read down the ratio columns and three separate stories appear.

**Some gaps we attribute to agentic workloads are really "contemporary workload vs SPEC"
gaps.** On IPC, branch misprediction, branch direction, BTB pressure and context switching,
FeedSim sits with the agentic 36, not with SPEC — and on BTB it is the most extreme of the
three (1.64 MPKI, **208× SPEC**, more than double the agentic figure). Branch MPKI is 5.7×
SPEC for FeedSim and 5.1× for the agent. These axes separate SPEC from modern software in
general; they are not evidence of anything specifically agentic, and the thesis should stop
short of claiming they are.

**But the agentic instruction-fetch signature is not reproduced by a real datacenter
service.** FeedSim is purpose-built to stress instruction supply — a 56 MB server binary with
an `ICacheBuster` unit compiled in 24 parts and a knob asking for 1.6 M i-cache iterations —
and it still shows **2.6× less** L1I code-read pressure than the agent (6.0 vs 15.6 MPKI),
2.6× less uop-cache miss pressure (18.0 vs 46.9), better uop-cache coverage (82% vs 66%), and
**2.9× fewer** context switches per CPU-second (191 vs 549). The agentic front end is under
more pressure than that of a workload engineered to put it under pressure. This is the finding
that survives the previous paragraph, and it is the strongest argument yet that agentic
workloads are not covered by existing suites.

**FeedSim occupies a third corner that neither of the others touches: memory bandwidth.** It
reads **11.5 GB/s** against SPEC's 1.52 and the agent's 0.46 — twenty-five times the agentic
figure — with L2-load MPKI 12.7× SPEC and LLC MPKI 11.2× SPEC. The agentic workload is the
*least* memory-intensive of the three; FeedSim is the most, by a wide margin. (This metric
counts offcore data reads, demand plus prefetch, at 64 B each; the ~3.4× gap against the
retired-load L2 miss count is hardware prefetch, as expected for graph aggregation. The same
formula is applied to all three families, so the comparison is like-for-like.)

**Synthesis.** The three workloads sit in three different corners: SPEC is compute-dense with
a small footprint and no OS interaction; FeedSim is memory-bandwidth-bound with heavy branch
and BTB pressure; the agentic workload is instruction-fetch-bound with heavy OS interaction
and almost no memory traffic. Profiling DCPerf *instead of* agentic workloads would miss the
instruction-fetch and context-switch extremes; profiling SPEC misses both. That is the case
for treating agentic work as its own benchmark class.

**Caveats, stated plainly.**
- **DCPerf here is n = 1.** FeedSim's memory intensity may be its own character — it walks a
  two-million-node graph — rather than a property of the suite. The remaining benchmarks are
  what would turn this single point into a population; until then the DCPerf column is a data
  point, not a distribution, and the figures draw it that way.
- The operating point is 8 physical cores at fixed frequency and 16 QPS. A different core
  count, QPS or a boost-enabled clock would move the absolute numbers; the fixed clock is what
  makes the three families comparable at all.
- The nine sweep passes are torn down when their capture window closes, so they do not
  themselves write a results row; the SLA receipt above comes from the dedicated confirmation
  run (`data/confirm/`). Teardown now waits for the experiment to finish, so future passes
  carry their own receipts.

## 5. How DCPerf is drawn in the figures

A violin is a distribution **over workloads**: SPEC contributes 26 benchmarks, the agentic
family 36 tasks, one vote each. DCPerf currently contributes **one** profiled benchmark, so it
has no across-workload distribution and is not drawn as a violin. It appears as a marker at its
vote — the median of its steady-state windows, the same statistic every SPEC and agentic vote
uses — with a thin bar showing the p25–p75 of its own windows, which is explicitly a
*within*-workload spread and a different quantity from the violins. When more DCPerf
benchmarks are profiled, `DCPERF_VIOLIN=1` switches it to a real violin.

## 6. Files

| What | Where |
|---|---|
| Sweep orchestrator | `local_agents/kit/dcperf/run_dcperf_profile.sh` |
| FeedSim module + `run.sh` patcher | `local_agents/kit/dcperf/bench_feedsim.sh`, `patch_run_sh.py` |
| Operating-point calibration | `local_agents/kit/dcperf/calibrate_feedsim.sh` |
| Metric export (shared vocabulary) | `local_agents/kit/plot/export_dcperf_rows.py` |
| Three-family figure | `local_agents/kit/plot/plot_paper_agg_compact3.R` |
| Per-window capture (gitignored) | `local_agents/DCPerf/data/dcperf_feedsim/run_1..9` |
| Figures | `local_agents/DCPerf/plots/paper_v1/` |
