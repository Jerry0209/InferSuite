# DCPerf on P7 — task choice, profiling method, and how it differs from SPEC and the agentic 36

**Branch:** `dcperf` · **Started:** 2026-09-10 · **Profiled so far:** FeedSim, VideoTranscodeBench (2 of 6)

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

**It was the cleanest fit for our measurement model, and the only one that ran here without
new hardware or a substituted dataset.** FeedSim ships as two separate binaries —
`LeafNodeRank`, the server under test, and `DriverNodeRank`, the closed-loop load generator —
so the split we already use for agent campaigns transfers exactly: **the workload goes in the
measured cgroup fence, the load generator runs on the housekeeping cores**, which is precisely
where the litellm proxy runs and for the same reason. It is the client, not the thing being
measured.

An earlier draft of this section claimed FeedSim was *the only* benchmark that maps onto the
fence model. That was wrong and is corrected in §7.1: every DCPerf benchmark is mechanically
fenceable. What separates them is how much supporting cast has to be pulled out of the measured
fence, and whether pulling it out distorts the workload. FeedSim scores well on both, which is
a real reason to profile it first, but a weaker claim than the original one.

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

Two DCPerf benchmarks are profiled: **FeedSim** (latency-critical ranking service, 16 QPS,
~2 500 windows per counter group) and **VideoTranscodeBench** (SVT-AV1 batch encode at
DCPerf's default `--runtime medium` preset, ~1 500 windows per group). Both pass every
applicable validation gate: nine of nine groups, zero multiplexed counters, steady state
within 2.8% / 4.3% drift, unfenced residual ≤ 2.5% / 2.7% of partition busy, all twelve
displayed metrics derived. FeedSim additionally holds its service-level objective *while
being profiled* — a confirmation run with the full capture stack live achieved **15.96 of 16
QPS at p95 = 472 ms**, against 479 ms measured with no counters running, so the
instrumentation does not perturb the workload it measures. VideoTranscodeBench is a batch
workload with no latency objective, and the gate records that rather than warning about a
missing receipt.

Votes are formed identically for all four columns: one value per workload, equal to the median
of that workload's 100 ms windows on the merged fence.

| Metric | SPEC | Agentic 36 | DCPerf feedsim | DCPerf video_transcode | Agentic/SPEC | feedsim/SPEC | video_transcode/SPEC |
|---|---|---|---|---|---|---|---|
| IPC | 2.185 | 1.749 | 1.725 | 2.62 | 0.8 | 0.79 | 1.2 |
| Branch MPKI | 0.8473 | 4.301 | 4.865 | 2.265 | 5.08 | 5.74 | 2.67 |
| Branch-direction MPKI | 0.8249 | 3.597 | 3.379 | 2.186 | 4.36 | 4.1 | 2.65 |
| BTB MPKI (BAClears) | 0.007845 | 0.7746 | 1.635 | 0.0477 | 98.7 | 208 | 6.08 |
| L1I MPKI (code-read) | 0.8454 | 15.63 | 5.995 | 12.03 | 18.5 | 7.09 | 14.2 |
| uop-cache (DSB) MPKI | 9.279 | 46.91 | 18.02 | 54.1 | 5.06 | 1.94 | 5.83 |
| DSB coverage (%) | 93.9 | 66.12 | 82.17 | 56.67 | 0.704 | 0.875 | 0.604 |
| L1D-load MPKI | 8.129 | 4.839 | 11.73 | 4.601 | 0.595 | 1.44 | 0.566 |
| L2-load MPKI | 0.3344 | 0.5454 | 4.238 | 0.1511 | 1.63 | 12.7 | 0.452 |
| LLC MPKI | 0.0429 | 0.1439 | 0.4793 | 0.0663 | 3.35 | 11.2 | 1.55 |
| DRAM read (GB/s) | 1.517 | 0.4567 | 11.5 | 3.802 | 0.301 | 7.59 | 2.51 |
| Context switches (/CPU-s) | 0 | 549.4 | 190.9 | 159 | ∞ | ∞ | ∞ |

### The second benchmark corrected a conclusion drawn from the first

With FeedSim alone it looked as though instruction-supply pressure was the agentic workload's
signature: FeedSim is purpose-built to stress instruction fetch — a 56 MB binary with an
`ICacheBuster` unit compiled in 24 parts — and still showed 2.6× less L1I pressure than the
agent. **VideoTranscodeBench does not support that reading.** It reaches an L1I code-read
MPKI of 12.0 against the agent's 15.6, and it is *worse* than the agent on both uop-cache
axes: 54.1 vs 46.9 misses per thousand instructions, and 56.7% vs 66.1% DSB coverage — the
worst instruction-supply behaviour of all four families. Large unrolled SIMD encode kernels
overflow the uop cache just as thoroughly as an agent's churning process images do.

So "agentic workloads are uniquely hard on instruction supply" is **not** supported. This is
the n = 1 caveat from the first pass doing its job, and it is worth stating plainly rather
than quietly dropping.

### What actually distinguishes the four families

The honest reading is that each occupies a different corner, and the agentic corner is defined
by a *combination* rather than by any single extreme:

- **SPEC** — compute-dense, tiny instruction footprint, essentially no OS interaction
  (context switches round to zero) and modest memory traffic.
- **VideoTranscodeBench** — the highest IPC of the four (2.62) and near-SPEC branch behaviour
  (BTB 0.048 MPKI, 6× SPEC where the others are 99× and 208×), combined with the *worst*
  uop-cache behaviour. Front-end pressure from **capacity**, not from unpredictability:
  straight-line vector code that is large but eminently predictable.
- **FeedSim** — the memory corner. 11.5 GB/s of offcore reads against SPEC's 1.52 and the
  agent's 0.46, L2-load MPKI 12.7× SPEC, LLC MPKI 11.2× SPEC, plus the highest BTB pressure
  of all four (208× SPEC). Branchy and bandwidth-hungry.
- **Agentic 36** — the only family that is simultaneously instruction-hungry (highest L1I
  MPKI, 15.6), branch-hostile (Branch MPKI 4.3, BTB 99× SPEC), OS-dominated (549 context
  switches per CPU-second, 2.9–3.5× either DCPerf benchmark) **and** memory-light (0.46 GB/s,
  the lowest of the four). Nothing else combines those.

Two consequences follow. First, **DCPerf is not one point**: its two benchmarks sit at
opposite ends of the memory axis (11.5 vs 3.8 GB/s) and of the branch axis (208× vs 6× SPEC),
so "compare against DCPerf" is not a single comparison. Second, **neither DCPerf benchmark
lands in the agentic corner** — profiling datacenter workloads instead of agentic ones would
still miss the context-switch extreme and the branch-plus-instruction-fetch combination, and
profiling SPEC misses nearly everything. That remains the case for treating agentic work as
its own benchmark class, but it now rests on the combination rather than on any single metric.

**Caveats.**
- DCPerf here is **n = 2 of 6**. The four remaining benchmarks are blocked on infrastructure
  or OS support (§ the bring-up doc); a third and fourth point could move these conclusions
  again, exactly as the second moved the first.
- VideoTranscodeBench runs on a **substituted dataset**: DCPerf specifies Netflix "El Fuente"
  shots from CDVL, whose download requires a manual free registration and cannot be scripted,
  so six 100-frame 1080p shots cut from freely-redistributable Xiph sequences
  (`park_joy`, `in_to_tree`) stand in. Encoder, preset, parallelism and pool size are
  DCPerf's. Encode *times* are therefore not comparable with published DCPerf numbers; the
  microarchitectural character of AV1 encoding, which is what this study reads, is preserved.
- Both benchmarks run on 8 physical cores at fixed frequency. FeedSim additionally runs at a
  fixed 16 QPS rather than DCPerf's boost-enabled QPS search. The fixed clock is what makes
  the four families comparable at all.
- The nine sweep passes are torn down when their capture window closes, so the SLA receipt
  comes from the dedicated confirmation run (`data/confirm/`). Teardown now waits for the
  experiment to finish, so future passes carry their own receipts.

## 5. How DCPerf is drawn in the figures

A violin is a distribution **over workloads**: SPEC contributes 26 benchmarks, the agentic
family 36 tasks, one vote each. DCPerf contributes **two** profiled benchmarks — far too few
for a distribution — so each gets its own column drawn as a marker at its vote: the median of
its steady-state windows, the same statistic every SPEC and agentic vote uses. The thin bar is
the p25–p75 of that benchmark's own windows, which is explicitly a *within*-workload spread and
a different quantity from the violins; it is labelled that way in the key. Giving each
benchmark its own column rather than pooling them is deliberate — the two sit at opposite ends
of the memory and branch axes, and pooling would invent a "DCPerf average" that describes
neither. `DCPERF_VIOLIN=1` switches to a real violin once there are enough benchmarks to
justify one.

`fig02`–`fig05` are the unit-consistent companions: every column there is a distribution over
100 ms windows, so a DCPerf benchmark sits beside SPEC and the 36 tasks without any change of
meaning.

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

## 7. Notes and clarifications

Answers to questions raised in review (2026-09-10). Recorded here because each one is a
load-bearing assumption behind the numbers above.

### 7.1 What "fits the fence model" means, and how the six benchmarks differ

A **fence is a cgroup**. Counters are attributed with `perf stat --for-each-cgroup` and CPU
time by polling each cgroup's `cpu.stat` at 10 Hz, so measuring a workload means placing
exactly that workload's processes in one cgroup pinned to the measured cores.

The half that matters more is the *exclusion*: anything that is **not** the workload under
test must run on the housekeeping cores. In the agent campaigns that is the litellm proxy — it
relays model calls but is not the agent working. For a client/server benchmark the load
generator plays the same role. Leaving the client on the measured cores commits two errors at
once: its CPU work is counted as though it were the server's, and it steals cores from the
server being characterised.

**Mechanically, all six DCPerf benchmarks can be fenced.** They start their components as
ordinary child processes tracked by pidfiles, not as systemd units, so cgroup inheritance
covers every descendant and nothing escapes into `system.slice` the way k3s pods once did on
this box. The real gradient is how much supporting cast must be pulled out, and whether doing
so changes the workload:

| Benchmark | What must leave the measured fence | Risk |
|---|---|---|
| VideoTranscodeBench | nothing — there is no client | none; the whole batch is the workload |
| FeedSim | `DriverNodeRank` only | low; the driver is light enough for the housekeeping cores |
| TaoBench | the memtier clients | DCPerf says clients want their own machines and 10–20 Gbps; on 8 shared cores the client may become the bottleneck, so the server is never properly loaded |
| DjangoBench | Cassandra, memcached, siege | Cassandra is a JVM database DCPerf recommends running on a separate machine; starved on housekeeping cores it would make the measured Django server wait on it |
| Mediawiki | nginx, MySQL, memcached, siege | same shape, plus a judgment call: is MySQL part of "web serving" or infrastructure? |
| SparkBench | storage is remote by design | an infrastructure problem, not a fencing one |

So the distinction is not *fits* versus *does not fit*. It is how obvious the line is between
the workload and its supporting cast, and whether that cast survives on eight shared cores
without distorting what is being measured.

### 7.2 What the "n = 1 caveat" was

With a single DCPerf benchmark profiled, every result had two explanations that could not be
told apart: it might be a property of datacenter workloads generally, or a property of FeedSim
alone. FeedSim walks a two-million-node graph, so its heavy memory traffic plausibly belonged
to it rather than to the suite. The caveat was written into the first version of §4 and then
tested by profiling a second benchmark. **It was the right worry**: VideoTranscodeBench reads
3.8 GB/s against FeedSim's 11.5, and it overturned the instruction-supply conclusion outright.

### 7.3 Why TaoBench and SparkBench need hardware this box does not have

- **TaoBench.** DCPerf supports the server on **CentOS Stream 8 or 9 only**, and requires
  `iommu=pt` on the kernel command line — without it "the system will be soft locked up in
  network I/O". That is an OS we do not run plus a GRUB change needing explicit sign-off.
  A single-host mode does exist, so the three-machine / 10–20 Gbps guidance is about avoiding a
  client bottleneck rather than a hard block. The OS and the boot parameter are the hard blocks.
- **SparkBench.** It models a data warehouse in which the dataset lives on **separate storage
  nodes reached over NVMe-over-TCP**. DCPerf asks for a kernel built with the nvme-tcp options
  (`CONFIG_NVME_TCP` and friends) and at least one storage node beside the compute node. We
  have one machine and a stock kernel.

### 7.4 Why DjangoBench and Mediawiki are container problems, not dead ends

Both blockers are **purely userspace**, which is exactly what a container fixes:

- **Mediawiki** needs HHVM-3.30, the last HHVM that ran PHP (2018). Prebuilt binaries exist
  only for CentOS and Ubuntu 22.04, and it wants `libicudata.so.60` and gflags 2.1.2 — neither
  present on Ubuntu 24.04.
- **DjangoBench** needs `python3.10`, which has **no apt candidate** on 24.04, and pins
  `cassandra-driver 3.19.0` / `django-cassandra-engine 1.5.5` from 2019, whose C extensions are
  very unlikely to build against Python 3.12/3.13.

A container shares the host kernel and supplies its own userspace, so a 22.04 image provides
those libraries. Our measurement reads cgroups, and **a container is a cgroup** — this repo
already does it, since the agent tool fence is a docker container inside `measured.slice`. Leave
`SKIP_DOCKER` unset so `apply_isolation` puts containers under that slice. The one extra design
step is DjangoBench's standalone role, which runs Cassandra, uWSGI and siege together: they must
be split across separate containers to keep the server measured and the client on housekeeping
cores (see §7.1).

### 7.5 What was and was not modified in DCPerf

**The dataset was not modified.** DCPerf ships `datasets/cuts` **empty on purpose** and instructs
the user to register at CDVL and download the El Fuente clips themselves. That empty directory
was filled with substitutes: two freely redistributable Xiph 1080p sequences (`park_joy`,
`in_to_tree`), cut into six 100-frame shots with ffmpeg. Encoder, preset, parallelism and pool
size are DCPerf's defaults, untouched.

**Two DCPerf files were modified**, both deliberately and both reproducible:

1. One line in `install_feedsim_x86_64_ubuntu.sh`, changing a literal `Ubuntu 22.04` string
   match so the shipped compatibility patches also apply on 24.04. Without it the pinned old
   folly does not build.
2. A **generated copy** of FeedSim's `run.sh` (`run_infersuite.sh`, produced by
   `patch_run_sh.py` on every preflight) carrying two edits that change only *where* the two
   processes run. No workload parameter is touched.

### 7.6 A latent issue found in the agent campaign kit

`restore_isolation` **widens this box's housekeeping partition**, and it affects agent
campaigns too, not just DCPerf.

The box normally keeps `system.slice` and `user.slice` on cores `0-3,12-15`, leaving `4-11`
clear. The kit snapshots that state before applying isolation by reading each slice's systemd
`AllowedCPUs` property. **On this box that property is empty**, because the boot-time
restriction is established some other way, so the documented fallback fires on restore and sets
`AllowedCPUs` to *all online CPUs*. Both slices therefore end up wider than they started.

**Measurements are not affected**: every pass re-applies the shield, and the ISO-PROOF gate
refuses to capture unless the measured cores are provably silent. The exposure is *between*
campaigns on a shared box — with the partition widened, another user's processes can be
scheduled onto cores 4–11, which are meant to be reserved.

**Fix (not yet applied, since it touches the shared campaign kit):** when the systemd property
is empty, snapshot the effective cpuset from `/sys/fs/cgroup/<slice>/cpuset.cpus.effective`
instead of falling back to all-online. The partition was restored by hand after this session
with `systemctl set-property --runtime <slice> AllowedCPUs=0-3,12-15`.
