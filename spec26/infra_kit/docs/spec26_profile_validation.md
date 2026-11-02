# SPEC CPU 2026 profile: validation findings and known issues

**Scope:** the 26 SPECrate episodes in `infra/data/` (SPEC CPU 2026 v1.0.1, refrate, copies=1,
ref command index 0, Xeon w5-3425 cores 4-11 with SMT siblings offline, 3.2 GHz turbo off,
GCC 14.2 `-O3 -march=native`, 100 ms windows, 11-group shuffled rotation plus continuous TMA).
**Checked:** 2026-10-26, against published measurements on similar cores, and by re-running six
benchmarks against this machine's memory controllers (§3).
**Figures:** interactive report with per-benchmark charts at
<https://claude.ai/artifact/1pFkFkyhQEUQEPo34q8TMS> (shared within the organization).

## TL;DR

The raw counters and the fence are sound. TMA, branch and L1 metrics match independent
measurements wherever the input and core family match. **Two derived metrics are mislabelled
and must not be quoted under their current names: `LLC_MPKI` and `DRAM_read_GBs`.** Measured
against the memory controllers, `LLC_MPKI` sees 0.09–26% of the DRAM reads, and
`DRAM_read_GBs` is off by 0.23× to 24× (§3). Most remaining gaps against published numbers
come from running only the first ref input. For nest that was measured directly: averaging all
three inputs moves the L3-miss gap to Zen 5 from 18× to 1.9× (§3.1).

| # | Issue | Severity | What it affects | Fix |
|---|---|---|---|---|
| 1 | `LLC_MPKI` counts only retired demand loads that miss L3 | **High** | every LLC claim; the deck's "lbm reads 0.01 LLC MPKI" | rename, add a wide LLC-miss metric (§1.1) |
| 2 | `DRAM_read_GBs` is L2→uncore read bandwidth: includes L3 hits, excludes store misses and writebacks | **High** | every bandwidth claim; the deck's "DRAM bandwidth is an FP phenomenon" | rename, measure DRAM at the memory controller (§1.2) |
| 3 | LLC and DRAM groups are live 1 window in 11, so low-MPKI values are noise | Medium | `LLC_MPKI`, `DRAM_read_GBs` on short or low-miss benchmarks | longer counting, report intervals (§1.3) |
| 4 | Isolation fences cores, not the shared L3 and memory controllers | Medium | all LLC/DRAM numbers | whole-machine quiet gate (added), CAT (§1.4) |
| 5 | `restore_isolation` widens the house cpusets to all CPUs on this box | Medium (ops) | other users after every campaign run | snapshot effective cpusets (§1.5) |
| 6 | Only ref command index 0 runs; 18 of 26 benchmarks have several | Medium (comparisons) | any comparison with published per-benchmark numbers | label the input, or run all (§1.6) |
| 7 | abc, ocio and flightdm got 6–8 windows per group | Low | their windowed metrics | longer command line or repeats (§1.7) |

## 1. Issues

### 1.1 `LLC_MPKI` sees only retired demand loads

`LLC_MPKI = mem_load_retired.l3_miss / instructions` (`scripts/extract_metrics.py:209`). A load
is counted only if it retired, missed L3, and was the first request for that line. Hardware
prefetches, L3 prefetches, store misses (RFO), code fetches, and loads that found their line
already in flight (fill-buffer hits) are all left out. "LLC MPKI" in papers and vendor tools
usually includes some of these. So the same benchmark spans orders of magnitude depending on
definition.

- **782.lbm_r:** 0.013 MPKI. The memory controller reads 20.5 lines and writes 12.4 lines per
  1000 instructions on the same work (§3), so the demand counter sees 0.09% of the DRAM reads.
  The prefetchers get there first: lbm's loads hit lines that are already in L1/L2 or in
  flight. The counter is not blind by construction. In a sequential read stream at full
  single-core bandwidth, 73% of lines still register a demand L3 miss.
- **Same definition, different core:** our streaming FP codes read 5–17× more than Lion Cove's
  identical counter (fotonik3d 18.0 vs 1.36, roms 3.9 vs 0.46, femflow 0.17 vs 0.01). Lion
  Cove books those loads as fill-buffer hits instead (fotonik3d 67, roms 64 per 1000 inst).
  Whether a late prefetch shows up as an "L3 miss" depends on prefetch timing on each core.
  Our counts are internally consistent (fotonik3d spends 53% of cycles stalled on L3
  misses), so this is not a counting error, but the number is not portable.
- On the re-run, `longest_lat_cache.miss` accounts for 93–96% of the DRAM reads of lbm,
  fotonik3d and roms (§3).

**Fix:** call it "retired demand-load L3 MPKI". For "LLC misses", use
`longest_lat_cache.miss` (all core-originated reads, RFOs and L1/L2 prefetches that miss L3)
plus `ocr.hwpf_l3.l3_miss` (L3-only prefetches). The group `x_llc` in
`scripts/llc_dram_crosscheck.sh` fits the 4 general-purpose counters.

### 1.2 `DRAM_read_GBs` is not DRAM bandwidth

`DRAM_read_GBs = offcore_requests.data_rd × 64 B / s`. Per Intel's event description, this
counts demand and L2-prefetch data reads leaving L2, page walks included. It therefore
**includes L3 hits** and **excludes RFOs and writebacks**.

- Where L2 misses mostly hit L3, it reports L3 traffic: 98.7% of marian's and omnetpp's
  demand L2-miss loads hit L3, as do 94% of nest's. Their 9.8, 2.7 and 4.6 GB/s compare with 0.6,
  0.1 and 0.3 GB/s of DRAM read+write measured on Zen 5. marian also read 9.8, 4.7 and 3.1
  GB/s in the three campaigns, because L3 hit traffic depends on what else is resident.
- On streaming codes it misses the store half. lbm's 4.3 GB/s is reads only. Its stores add a
  similar RFO read stream plus writebacks; Zen 5 measures 22.8 GB/s read+write.
- The calibration kernel in §3 shows it directly. A pure store stream drives 12.9 GB/s of DRAM
  reads (the RFOs) and 12.8 GB/s of writes at the memory controller, while
  `offcore_requests.data_rd` reads 0.05 GB/s.
- Measured on the re-run (§3), the metric over-reports omnetpp 24×, marian 8–11× and nest
  2–4×, and under-reports lbm (0.23×) and fotonik3d (0.66×).

**Fix:** call it "L2-miss data-read bandwidth (L3 + DRAM)". For DRAM, count
`unc_m_cas_count.rd` / `unc_m_cas_count.wr` (× 64 B). These are uncore events: system-wide
only, not cgroup-scoped. They need a quiet machine (§1.4), an idle baseline, and the capture
stack's own traffic to subtract: 0.28 GB/s of reads and 0.12 GB/s of writes on this box,
measured on an empty fence. That floor is larger than omnetpp's real traffic.
A per-core alternative is `ocr.reads_to_core.l3_miss` (reads incl. RFO and prefetch) plus
`ocr.hwpf_l3.l3_miss`. Neither counts writebacks.

### 1.3 Low-MPKI LLC and DRAM values are mostly sampling noise

The `cache` and `dram_bw` groups are each live in 1 window out of 11. A 30 s run gives them
about 3 s of counting, often spread over a few hundred misses.

- The 95% bootstrap interval of `LLC_MPKI` is wider than ±40% for gcc, llvm, cppcheck, abc,
  vpr, gem5, gmsh and cpython.
- Between the two complete 100 ms campaigns (`data/` vs `data_100ms_dirtyrundirs/`),
  `LLC_MPKI` changed by a median of 12%. The worst cases: vpr 2.37×, ns3 2.28×, gmsh 1.8×,
  lbm 1.57×, abc 0.38× and cpython 0.1×. Every other metric repeats to within a few percent
  (IPC median 0.2%, TMA within 0.9 points).

**Fix:** for memory metrics, run a dedicated pass with fewer groups (the cross-check uses 5).
Alternatively, keep rotating until the bootstrap interval is under ±10%. Do not rank
benchmarks below ~0.1 MPKI.

### 1.4 The L3 and memory controllers are not isolated

`apply_isolation` fences cores: slices pinned, IRQs on house cores, and ISO-PROOF checks that
the measured cores are silent. The 30 MB L3 and the memory controllers are still shared with
the house cores, where other users run. This happened during the cross-check on 2026-10-26.
Another user's ~650%-CPU job started on the house cores seconds after the shield went up.
ISO-PROOF had passed and stayed true, because the measured cores were silent, while the
memory controllers saw 1–5 GB/s of foreign traffic.

**Fix (added):** `scripts/quiet_gate.py` blocks until no other user's process is busy anywhere
on the machine. It also runs as a witness during capture, and any episode whose idle baseline
or run overlapped foreign work is set aside and re-run. For the main campaign, consider resctrl
CAT (give cores 4-11 dedicated L3 ways; the CPU supports `cat_l3`) or at least log
`llc_occupancy` of the house group.

### 1.5 `restore_isolation` widens the house cpusets (ops bug)

On this boot, `system.slice`, `user.slice` and `init.scope` are confined to 0-3,12-15, but
`systemctl show -p AllowedCPUs` reads empty for all three. The split is set outside systemd's
property, most likely by the agentic benchmark's boot services
(`agentic-benchmark-runtime-controls.service`). `apply_isolation` snapshots that empty
value, and `restore_isolation` turns an empty snapshot into "all online CPUs". After any
`episode`/`campaign` run, the three units end up on 0-15, and other users' work can land on
cores 4-11. It does not affect captured data (restore runs after capture). It does change the
machine for everyone else, and for the next agentic run.

Observed 2026-10-26 14:46 and repaired by hand with
`systemctl set-property --runtime <unit> AllowedCPUs=0-3,12-15`. That is runtime-only and
resets at reboot. `llc_dram_crosscheck.sh` now records the effective cpusets before the shield
and re-applies any that the restore changed.
**Fix in `run_spec_campaign.sh`:** when `AllowedCPUs` is empty, snapshot
`/sys/fs/cgroup/<unit>/cpuset.cpus.effective` instead.

### 1.6 Only the first ref input runs

`SPEC_CMD_INDEX=0`. 18 of 26 benchmarks list several ref command lines, and they are different
workloads; for example, omnetpp's ten are ten network configurations. Published per-benchmark
numbers usually time-weight all inputs or profile the last one (Chips and Cheese). This
explains the largest non-memory deviations: stockfish, omnetpp, abc (bad speculation 48.6% vs
23.2%), nest, ocio, and cpython (whose ~0 branch MPKI is real for its first input). The single-input
benchmarks are 707, 709, 722, 749, 750, 765, 766 and 782.

Measured for nest (§3.1): its three inputs are three different programs as far as the memory
system is concerned. Input 0 (cuba_stdp, the one the campaign ran) misses L3 3.4 times per 1000
instructions and moves 2.4 GB/s of DRAM traffic. Input 2 (ArtificialSynchrony) misses 0.010
times and moves 0.04 GB/s, and it is 67% of nest's instructions. On input 2, the input Chips and
Cheese profiled, our IPC is 4.10 against Lion Cove's 3.60 and the memory-bound share is 2.8%
against 4.6%. On input 0 the campaign reported 1.81 and 23%.

**Fix:** write the input into every label (e.g. "706.stockfish_r [1to6_classical]"), or run
all command lines and time-weight them before comparing with literature.

### 1.7 Thin samples

abc (729), ocio (736) and flightdm (748) completed only 6–8 windows per group; gem5 (735) and
zstd (777) got 14–19. Their TMA (continuous) is fine. Their windowed metrics rest on under
a second of counting per group.

## 2. What checked out

- **Fence and instruction totals:** within ±3% of an independent i9-14900K run (Raptor Cove,
  same core family) on the same input: lbm 1640 vs 1670 B, roms 1330 vs 1318 B, gmsh 205 vs
  205 B. fotonik3d and femflow are ~10% lower, as expected for AVX-512 vs AVX2 code. The clock derived from slots
  reads 3.1 GHz (3.2 nominal); µops per instruction is 0.8–1.16.
- **TMA:** where the input and core family match, it agrees within about 3–5 points.
  llvm transformsplus: frontend-bound 40.4% vs ~40%, bad speculation 16.2% vs 19.2% on
  Raptor Cove. fotonik3d is 55% memory-bound vs 57% on Lion Cove, roms 43% vs 45%.
  Repeat runs move less than 0.9 points.
- **Branch MPKI:** median ratio 1.00× vs the same-input i9-14900K run; 14 of 17 are within ±15%
  (omnetpp 2.16 vs 2.16, gcc 4.69 vs 4.68).
- **L1I MPKI:** cactus 93 vs 83 (i9-14900K) and 82 (Xeon 8468).
- **Explained TMA deviations (not bugs):**
  - **709 cactus:** 37% frontend-bound vs 1% on Lion Cove. Lion Cove has a 64 KB L1I; Zen 5,
    with 32 KB like ours, shows 51%.
  - **782 lbm:** 8.5% memory-bound and 45% core-bound, vs 59% and 11% on Lion Cove. This GCC
    build left lbm scalar (no vector FP retired) and the core runs at 3.2 GHz. The Zen 5 run
    from Chips and Cheese shows the same split.
  - **729 abc and 710 omnetpp:** different input from the reference.
  - **767 nest:** different input from the reference. Re-run on Lion Cove's input it matches
    (§1.6): IPC 4.10 vs 3.60, memory-bound 2.8% vs 4.6%, L1D MPKI 26.7 vs 28.4. Retiring is
    68.6% vs 45.1%, the 6- vs 8-wide effect at that IPC. Bad speculation is 1.7% vs 11.0% and is
    not explained.

## 3. On-machine cross-check (2026-10-26)

Six benchmarks were re-run under the campaign's own fence, shield and 100 ms shuffled
rotation, with five groups: the original `cache` and `dram_bw`, plus `x_llc`, `x_ocr1` and
`x_ocr2` (definitions in `scripts/llc_dram_crosscheck.sh`). The memory controllers'
`unc_m_cas_count.rd/wr` ran system-wide for the whole session.

- **Quiet machine:** each step waited for 60–180 s with no other user's process busy, and a
  witness logged foreign CPU every 2 s. marian was redone once, after another user's agent
  session spiked to 50% CPU during it. The first session attempt was abandoned before any
  benchmark ran: a ~650%-CPU job started on the house cores seconds after the gate released.
- **Isolation:** the campaign's own shield, applied once per session. ISO-PROOF passed each
  time (measured cores 0.0% busy), and the shield was restored afterwards with the house
  cpusets preserved (§1.5).
- **Subtractions:** each episode subtracts the idle DRAM rate from the 15 s before it, then the
  capture stack's own 0.28 GB/s read and 0.12 GB/s write (an empty-fence control episode).
- **Data:** `data_llc_xcheck/` (`xcheck_summary.json`; `_session.aborted.1` and
  `*.contaminated.*` are the set-aside attempts).

**Calibration (GB/s).** The instruments match hand-computable traffic within 1%. All five
groups ran with zero multiplexing.

| known-traffic kernel (10 s, inside the fence) | kernel-reported | DRAM read (IMC) | DRAM write (IMC) | `ocr.reads_to_core.l3_miss` | `offcore_requests.data_rd` (= `DRAM_read_GBs`) |
|---|---|---|---|---|---|
| sequential read | 13.5 | 13.5 | 0.005 | 13.4 | 13.6 |
| sequential store | 12.9 | 12.9 | 12.8 | 12.8 | 0.050 |

**The re-runs reproduce the campaign:** instructions within 0.8%, IPC within 0.8%, and
`LLC_MPKI` within 2% on fotonik3d and roms. The near-zero values move more (omnetpp −9%,
nest +9%, lbm 0.013 → 0.019).

**LLC, per 1000 instructions** (DRAM lines are memory-controller counts minus idle and stack):

| benchmark | instructions (G) campaign / re-run | `LLC_MPKI` campaign / re-run | fill-buffer hits | all core L3 misses | DRAM read lines | DRAM write lines | `LLC_MPKI` ÷ DRAM reads | all L3 misses ÷ DRAM reads |
|---|---|---|---|---|---|---|---|---|
| 782.lbm_r | 1640 / 1640 | 0.013 / 0.019 | 2.80 | 19.4 | 20.5 | 12.4 | 0.09% | 95% |
| 749.fotonik3d_r | 599 / 599 | 18.0 / 18.2 | 82.2 | 68.1 | 71.3 | 40.2 | 26% | 96% |
| 765.roms_r | 1330 / 1330 | 3.94 / 3.87 | 69.1 | 22.3 | 24.0 | 6.05 | 16% | 93% |
| 767.nest_r | 171 / 170 | 0.30 / 0.32 | 7.97 | 3.57 | 4.21 | 2.71 | 7.7% | 85% |
| 772.marian_r | 430 / 429 | 0.11 / 0.11 | 47.6 | 0.82 | 1.12 | 0.59 | 9.6% | 73% |
| 710.omnetpp_r | 326 / 325 | 0.043 / 0.039 | 10.5 | 0.11 | 0.19 | 0.11 | 21% | 61% |

- `LLC_MPKI` sees 0.09% (lbm) to 26% (fotonik3d) of the lines actually read from DRAM.
- `longest_lat_cache.miss` sees 93–96% on the streaming codes. On the low-traffic codes it
  sees 61–85%, where the stack subtraction is a large part of what remains.
- `ocr.hwpf_l3.l3_miss` (L3-only prefetches) read 0 in every run, calibration included, so
  `longest_lat_cache.miss` alone is a sufficient LLC-miss metric here.

**Bandwidth, GB/s** (Zen 5 column for orientation only: different core, clock and compiler;
§3.1 compares properly and covers nest's other inputs):

| benchmark | `DRAM_read_GBs` campaign / re-run | DRAM read | DRAM write | metric ÷ (read + write) | Zen 5 read + write |
|---|---|---|---|---|---|
| 782.lbm_r | 4.30 / 4.29 | 11.6 | 7.02 | 0.23× | 22.8 |
| 749.fotonik3d_r | 11.3 / 11.6 | 11.2 | 6.32 | 0.66× | 41.1 |
| 765.roms_r | 11.3 / 11.2 | 6.20 | 1.57 | 1.44× | 14.0 |
| 767.nest_r | 4.61 / 8.88 | 1.47 | 0.95 | 3.67× | 0.3 |
| 772.marian_r | 9.84 / 7.24 | 0.58 | 0.30 | 8.19× | 0.6 |
| 710.omnetpp_r | 2.67 / 2.66 | 0.070 | 0.041 | 24.1× | 0.1 |

- Where L2 misses hit L3 (omnetpp, marian, nest), the metric reports L3 traffic, and it
  wanders between runs: nest 4.6 → 8.9, marian 9.8 → 7.2. On streaming codes it misses the
  store side.
- omnetpp's real 0.11 GB/s and marian's 0.88 GB/s are close to the 0.1 and 0.6 GB/s measured
  on Zen 5.

**Deck lines to correct:**

- "782.lbm_r reads 0.01 LLC MPKI while streaming 4.3 GB/s from DRAM". lbm misses L3 19.4
  times per 1000 instructions (all requests) and moves 18.6 GB/s to and from DRAM: 11.6 GB/s
  of reads and 7.0 GB/s of writes.
- "DRAM read bandwidth is an FP phenomenon … 6 of 12 FP exceed 4 GB/s". marian (0.88 GB/s
  real) and nest (2.4 GB/s real) only qualify through L3 hits. The streaming FP codes do move
  a lot of DRAM traffic: lbm 18.6, fotonik3d 17.5 and roms 7.8 GB/s read+write. palm was not
  re-run.

### 3.1 Against published numbers

No one has published SPEC CPU 2026 L3 or DRAM measurements on Sapphire Rapids (Li et al.'s
Xeon 8468 paper reports front-end numbers only). The only source with both L3 misses and DRAM
bandwidth is Kashyap et al. on Zen 5 (EPYC 9755). Their setup differs:

- GCC 15.2 `-march=znver5 -flto` against our GCC 14.2 `-march=native`;
- AMD uProf, system-wide samples every 2 s, with no L3-miss definition given;
- one row per benchmark, without saying which ref inputs ran;
- up to 4.1 GHz (whether boost was on is not stated), against our 3.2 GHz with turbo off.

Misses per instruction is the fairer comparison, because it does not depend on clock speed.
Our column is `longest_lat_cache.miss`: all core requests that miss L3, prefetches included.
Kashyap et al. do not define theirs.

| benchmark | L3 misses per 1000 inst, ours | Zen 5 | ours ÷ Zen 5 | DRAM read + write GB/s, ours | Zen 5 | ours ÷ Zen 5 |
|---|---|---|---|---|---|---|
| 782.lbm_r | 19.4 | 17.8 | 1.09 | 18.6 | 22.8 | 0.82 |
| 765.roms_r | 22.3 | 27.2 | 0.82 | 7.77 | 14.0 | 0.56 |
| 710.omnetpp_r | 0.11 | 0.1 | 1.1 | 0.11 | 0.1 | 1.1 |
| 749.fotonik3d_r | 68.1 | 44.2 | 1.54 | 17.5 | 41.1 | 0.43 |
| 772.marian_r | 0.82 | 0.4 | 2.0 | 0.88 | 0.6 | 1.5 |
| 767.nest_r, input 0 only | 3.57 | 0.2 | 18 | 2.42 | 0.3 | 8.1 |
| 767.nest_r, all 3 inputs | 0.38 | 0.2 | 1.9 | 0.55 | 0.3 | 1.8 |

- **lbm, roms and omnetpp agree within about 20% per instruction.** That is about as close as two
  different cores and compilers get; a different vector width alone moved fotonik3d's
  instruction count by ~10% (§2).
- **Our GB/s is lower on lbm and fotonik3d mostly for a hardware reason.** In calibration, a
  single-thread sequential read on this machine reached 13.5 GB/s and a store stream 25.7 GB/s
  read + write. lbm and fotonik3d already read 11.6 and 11.2 GB/s, so one core here at 3.2 GHz
  has little headroom: Zen 5's 41 GB/s on fotonik3d is out of reach, and lbm's 0.82× is a small
  gap. roms is not near that limit. Its traffic per instruction is within 12–18% of Zen 5's, so its lower GB/s fits a
  faster Zen 5 core.
- **fotonik3d's 1.5× is not explained.** It has a single input, and our three counters agree
  with each other and with the memory controllers (96%), so the number is right for our build.
  What remains is a different instruction count from the other compiler, or a narrower uProf
  definition. Neither can be checked without their instruction count.
- **nest's gap was the input.** Measured on 2026-10-26 in a second isolated session
  (`data_llc_xcheck_nest/`, calibration again within 1%, all three episodes clean on the witness
  and on SPEC's output check):

  | input | instructions (G) | IPC | L3 misses per 1000 inst | DRAM read lines per 1000 inst | DRAM read + write GB/s | `DRAM_read_GBs` |
  |---|---|---|---|---|---|---|
  | 0 cuba_stdp (campaign) | 171 | 1.81 | 3.43 | 4.18 | 2.43 | 4.34 |
  | 1 structural_plasticity_benchmark | 390 | 3.03 | 0.12 | 0.36 | 0.27 | 3.64 |
  | 2 ArtificialSynchrony | 1152 | 4.10 | 0.010 | 0.034 | 0.036 | 0.026 |
  | all three (by instructions, by time) | 1713 | — | 0.38 | 0.52 | 0.55 | — |

  The input-0 repeat reproduces the first re-run: 3.43 vs 3.57 L3 misses and 2.43 vs 2.42 GB/s.
  The leftover 1.9× is on small numbers (0.38 vs 0.2), about the size of marian's gap, and it
  depends on how each run weights the three inputs. It is not explained further.
  `DRAM_read_GBs` read 4.34, 3.64 and 0.026 on the three inputs, against 2.43, 0.27 and 0.036
  GB/s of real traffic: 13× too high on input 1.
- **marian's 2× is untested.** It also has several inputs, and the absolute numbers are
  small (0.4 vs 0.8 misses per 1000 instructions). Running its other inputs the same way would
  settle it (`./scripts/llc_dram_crosscheck.sh 772.marian_r@1 …`).
- **Precision on the low-traffic codes.** The capture stack's own traffic measured 0.40 GB/s in
  the first session and 0.34 GB/s in the second. That 0.06 GB/s drift is half of omnetpp's
  0.11 GB/s and larger than nest input 2's 0.036, so those rows are good to an order of
  magnitude, not to 20%.

## 4. Reproduce

```bash
cd ~/spec26-infra/infra
./scripts/llc_dram_crosscheck.sh                 # default: lbm fotonik3d roms marian omnetpp nest
./scripts/llc_dram_crosscheck.sh 722.palm_r       # any list of benchmarks
./scripts/llc_dram_crosscheck.sh --control-only   # calibration + capture-stack control only
python3 scripts/xcheck_report.py                  # -> data_llc_xcheck/xcheck_summary.json + tables

# other ref inputs: "<bench>@<k>" runs command line k; use a fresh DATA_ROOT
DATA_ROOT=$PWD/data_llc_xcheck_nest ./scripts/llc_dram_crosscheck.sh 767.nest_r@0 767.nest_r@1 767.nest_r@2
python3 scripts/xcheck_report.py data_llc_xcheck_nest
```

`llc_dram_crosscheck.sh` sources `run_spec_campaign.sh`, so the fence, shield, shuffled rotation
and gates are the campaign's own. On top of them it:

- waits for 180 s of whole-machine quiet;
- counts `unc_m_cas_count.rd/wr` system-wide for the session;
- calibrates against known-traffic kernels (`scripts/xcheck_calib.c`);
- measures the capture stack's own DRAM traffic on an empty fence;
- rotates `cache dram_bw x_llc x_ocr1 x_ocr2` at 100 ms;
- takes a 15 s idle baseline before each episode, and re-runs any calibration or episode that
  overlapped foreign work;
- re-applies the pre-run effective cpusets after the campaign's `restore_isolation` (§1.5).

Each invocation writes a new `_session*` directory; `xcheck_report.py` stitches them by time.

New files: `scripts/llc_dram_crosscheck.sh`, `scripts/quiet_gate.py`, `scripts/xcheck_calib.c`,
`scripts/xcheck_report.py`, `data_llc_xcheck/`, `data_llc_xcheck_nest/`, `logs/llc_dram_crosscheck.log`. Nothing in
`data/`, `run_spec_campaign.sh` or `extract_metrics.py` was changed. Note that `kit_rev` hashes
every `scripts/*.sh` and `*.py`, so future campaign episodes will record a new `kit_rev`.
Sourcing the runner also appends one `partition:` line to `logs/campaign.log` per invocation.

## 5. References

- Chips and Cheese, *Evaluating SPEC CPU2026* — Core Ultra 9 285K (Lion Cove), TMA and per-benchmark
  cache metrics, last ref input: <https://chipsandcheese.com/p/evaluating-spec-cpu2026>
- Jia Je, SPEC CPU 2026 workload analysis, i9-14900K, per-input instruction counts and branch MPKI:
  [INT rate](https://jia.je/software/2026/05/22/spec-cpu-2026-workload-analysis-int-rate-en/),
  [FP rate](https://jia.je/software/2026/05/29/spec-cpu-2026-workload-analysis-fp-rate-en/)
- SPEC CPU 2026 characterization paper (EPYC 9755, top-down shares): <https://arxiv.org/html/2605.01575v1>
- Kashyap et al. (EPYC 9755, uProf L3 MPKI and DRAM bandwidth; system-wide 2 s samples, ref inputs
  and L3-miss definition not stated): <https://arxiv.org/html/2609.01527v1>
- Li et al. (Xeon 8468, L1I MPKI): <https://arxiv.org/html/2605.03713v4>
- Navarro-Torres et al. 2019 (CPU2017 on Skylake-SP, IMC counts for 519.lbm): <https://pmc.ncbi.nlm.nih.gov/articles/PMC6675054/>
- SPEC 782.lbm_r documentation: <https://www.spec.org/cpu2026/Docs/benchmarks/782.lbm_r.html>
- Sapphire Rapids event descriptions (perf JSON): <https://lkml.rescloud.iu.edu/2305.2/02656.html>, and `perf list -v` on this box
