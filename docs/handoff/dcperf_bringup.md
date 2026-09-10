# DCPerf bring-up handoff

**Owner:** Tianrui (Jerry) · **Written:** 2026-09-10 · **Branch:** `dcperf` · **Status:** FeedSim brought up on P7; five benchmarks not yet attempted

Mentor directive (2026-09): profile one DCPerf benchmark end-to-end, validate it, then extend
to the whole suite. This page is the session-starter for that work — what DCPerf is, which of
its benchmarks can actually run in our measurement environment, how it is installed here, and
the traps. The *study* (why FeedSim was picked, how it is profiled, how it compares with SPEC
and the agentic 36) lives next to the data in
[`local_agents/DCPerf/README.md`](../../local_agents/DCPerf/README.md).

---

## 1. What DCPerf is

[facebookresearch/DCPerf](https://github.com/facebookresearch/DCPerf) is Meta's open
datacenter benchmark suite: a set of full application workloads chosen to stand in for the
big consumers of Meta's fleet, rather than the compute kernels a CPU suite like SPEC uses.
It is driven by **Benchpress** (`./benchpress_cli.py`), which installs and runs each
benchmark from a YAML job definition.

Its relevance to this thesis: DCPerf exists because SPEC does not represent datacenter
workloads — the same claim this study makes about agentic workloads. It is therefore the
natural third population for our comparison, and a far more demanding reference than SPEC.

| Benchmark | Meta workload represented | Stack |
|---|---|---|
| **FeedSim** | Object aggregation, ranking / inference | C++, Folly, FBThrift, libevent, jemalloc |
| **Mediawiki** | Web serving (Facebook) | PHP/Hack on HHVM-3.30, MySQL, Memcached, Nginx, Siege |
| **TaoBench** | Caching, look-through cache | C++, Memcached, Memtier, Folly |
| **DjangoBench** | Web serving (Instagram) | Python, Django, uWSGI, Cassandra, Memcached |
| **SparkBench** | Data analytics, query engine | Java/SQL, Apache Spark, OpenJDK |
| **VideoTranscodeBench** | Video processing | C++, ffmpeg, SVT-AV1, libaom, x264 |

`WDLBench` also ships in the repo but is a micro-benchmark set ("widely distributed functions"
— zstd, openssl, folly primitives), not a fleet workload; it is out of scope for the
workload-level comparison.

**Official support:** CentOS Stream 8/9 or **Ubuntu 22.04**, x86_64 or aarch64, run as root,
`ulimit -n` ≥ 65536. P7 is **Ubuntu 24.04**, which is outside that set — see §4.

## 2. Feasibility on P7 (this is the table that decides what you can run)

P7 constraints that drive everything: Ubuntu 24.04 (noble), a single host, ~46 GB free disk,
and a measurement partition of 8 physical cores. Assessed 2026-09-10 from the DCPerf sources.

| Benchmark | Single host? | Runs on noble? | Verdict |
|---|---|---|---|
| **FeedSim** | **Yes** — server and load generator are designed to share a host | Builds from source; needed one 1-line fix (§4) | ✅ **running** |
| VideoTranscodeBench | Yes | Likely (ffmpeg/SVT-AV1 build) | ⚠️ blocked on data: the El Fuente clips come from CDVL behind a **free registration**, so the download cannot be automated |
| DjangoBench | Yes (standalone role) | Plausible; Cassandra + pinned Python are the risk | ⚠️ next candidate |
| Mediawiki | Yes | **HHVM-3.30** ships prebuilt for CentOS / Ubuntu 22.04 only and wants `libicudata.so.60` + gflags 2.1.2, both pre-noble | ⚠️ needs a container or 22.04 box |
| TaoBench | Standalone mode exists, but 3 machines are recommended, plus 10–50 Gbps NIC | Server documented for **CentOS Stream 8/9 only**; also wants `iommu=pt` on the kernel cmdline (a GRUB change → needs explicit user sign-off) | ❌ not on P7 as-is |
| SparkBench | **No** — requires separate storage nodes over **NVMe-over-TCP** and a kernel built with the nvme-tcp options | Needs a custom kernel | ❌ infeasible here |

Practical reading: **FeedSim** is profiled and validated. **VideoTranscodeBench** is the next
cheapest, needing only a substitute dataset. **DjangoBench** is harder than the table suggests
(see below). TaoBench and SparkBench need infrastructure this box does not have — if the
mentor wants all six, those two are the scope/hardware question to raise, and the AWS boxes in
[`arm_aws_bringup.md`](arm_aws_bringup.md) are a natural home for TaoBench (multi-instance,
CentOS-friendly) once that work starts.

### DjangoBench: harder than it looks (checked 2026-09-10)

Its Ubuntu installer wants `python3.10-dev` / `python3.10-venv`, and on noble `python3.10` has
**no apt candidate at all** (noble ships 3.12). Worse, the workload pins 2019-era packages —
`cassandra-driver 3.19.0`, `django-cassandra-engine 1.5.5` — whose C extensions are very
unlikely to build against Python 3.12/3.13. Getting it running on the host therefore means
either a deadsnakes PPA (a persistent change to the host's apt sources) or a private 3.10
toolchain, plus dependency archaeology. Use the container route instead.

### The container route (recommended for every OS-gated benchmark)

**We already profile containerised workloads.** The agent campaigns' tool fence *is* a docker
container living in `measured.slice`, measured with `perf --for-each-cgroup` on the container's
cgroup. So running a DCPerf benchmark inside an `ubuntu:22.04` or CentOS Stream 9 image needs
no new measurement machinery — only the existing docker path:

- run the DCPerf install and the workload inside a supported-OS image;
- leave `SKIP_DOCKER` unset so `apply_isolation` puts containers under `measured.slice`
  (the DCPerf kit sets `SKIP_DOCKER=1` only because FeedSim is a native process);
- fence the container's cgroup exactly as the tool fence is fenced.

This unblocks **Mediawiki** (HHVM-3.30 has prebuilt Ubuntu 22.04 binaries) and **DjangoBench**
(python3.10 is native to 22.04) without touching the host. The one design question it raises
is fence separation: DjangoBench's standalone role runs Cassandra, uWSGI and siege together,
so the server and the load generator must be split into separate containers (or separate
sub-cgroups) to keep the "server measured, client on housekeeping cores" discipline that makes
these numbers comparable with FeedSim and the agentic 36.

## 3. Install and run recipe (as used here)

DCPerf is kept **outside this repo**, as a sibling tree, the same arrangement as the SPEC
capture kit (`~/spec26-infra`):

```bash
mkdir -p ~/dcperf-infra && cd ~/dcperf-infra
git clone --depth 1 https://github.com/facebookresearch/DCPerf.git
cd DCPerf
sudo apt-get install -y python3-tabulate python3-click python3-yaml python3-pandas
sudo ./benchpress_cli.py list                     # job catalogue
sudo ./benchpress_cli.py install feedsim_autoscale
```

Benchpress installs into `benchmarks/<name>/` inside the DCPerf tree, and must run as root.
Stock execution would then be `sudo ./benchpress_cli.py run feedsim_autoscale` — **we do not
use that path for profiling**, because it gives us no control over process placement; see
the study README for how the run is driven instead.

## 4. Traps hit on P7 (fix these before you lose an afternoon)

- **The Ubuntu compatibility patches are gated on a literal version string.** FeedSim pins an
  old folly/rsocket and carries `patches/ubuntu-22-compatibility/*.diff` to make them build
  with a modern compiler, but the installer applies them only under
  `grep -i 'Ubuntu 22.04' /etc/os-release`. On 24.04 that test fails, the patches are skipped,
  and the folly build breaks. Fix (the only edit needed to install FeedSim on noble):

  ```bash
  sed -i "s/if grep -i 'Ubuntu 22.04' \/etc\/os-release/if grep -iE 'Ubuntu (22|24)\\\\.04' \/etc\/os-release/" \
    packages/feedsim/install_feedsim_x86_64_ubuntu.sh
  ```

  Every apt package name in that installer does resolve on noble — the version gate was the
  only blocker. GCC 13.3 built the patched folly, fbthrift, wangle and Boost 1.71 cleanly.
- **The installer builds its own CMake 3.14.5 and OpenSSL 1.1.1b** from source and ignores the
  system ones. Expect a long first install (tens of minutes) and several GB under
  `benchmarks/feedsim/third_party/`. Watch free disk.
- **Benchpress needs root**, and it writes inside the DCPerf tree, so the tree ends up
  root-owned. Read it with `sudo` or `ls` as needed.
- **`nproc` decides FeedSim's thread counts** at the top of `run.sh`, and `nproc` honours the
  caller's CPU affinity. Whatever affinity the launching shell has therefore silently sets the
  workload's shape — pin deliberately and record it.
- **CPU boost:** FeedSim's README recommends turning boost ON, warning that the QPS search may
  not converge otherwise. Our measurement contract fixes frequency (`no_turbo=1`). We
  therefore run a **fixed-QPS** experiment instead of the search — see the study README. Any
  QPS number produced here is *not* a DCPerf leaderboard score and must never be quoted as one.

## 5. What is in this repo

| What | Where |
|---|---|
| Profiling kit (sweep orchestrator, bench modules, run.sh patcher) | `local_agents/kit/dcperf/` |
| Study doc: task choice, method, SPEC/agentic comparison | `local_agents/DCPerf/README.md` |
| Banked per-window data | `local_agents/DCPerf/data/` (gitignored) |
| Figures + versioned chart packs | `local_agents/DCPerf/plots/`, `local_agents/ML_iso36/charts/` |
| DCPerf checkout (not in git) | `~/dcperf-infra/DCPerf` |
