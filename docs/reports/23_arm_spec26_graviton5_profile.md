# Report 23 — SPEC CPU 2026 single-core profile on AWS Graviton5 (Neoverse-V3)

**Date of study:** 2026-11-03 · **Author of record:** Tianrui (Jerry), with Claude Code
**Deck slides:** none. Feeds Jef's ARM figure schemas (`arm/reports/figures/data/`); the ARM counterpart of report 18
**Procedure:** [`execution/arm_spec_profiling.md`](../handoff/execution/arm_spec_profiling.md) · **Session log:** [`sessions/2026-11-03_arm-spec26-profiling.md`](../handoff/sessions/2026-11-03_arm-spec26-profiling.md) · **Tree:** [`arm/README.md`](../../arm/README.md), branch `spec-arm`

---

## 1. Key summary

Jef asked for a SPEC CPU 2026 baseline for his Graviton5 agentic data: the same box, the same metric families and the same formulas. We ran the 26 SPECrate benchmarks (ref input, 1 copy, 1 thread, ref command index 0, the same set as the x86 rows) built with GCC 14.2 for aarch64. Each benchmark ran **14 times** on **one pinned Neoverse-V3 core**, once per counter family. Each run was a single `perf stat` pass of the cycle counter plus up to 6 events, with no multiplexing, 100 ms windows, and counting filtered to our own fence cgroup. **All 364 ⟨benchmark, family⟩ passes are valid** (234 in tier 1, 130 in tier 2). Getting there took 368 attempts: the witness rejected 4, and each re-run passed. Every benchmark's 14 instruction totals agree within **0.201 %** (worst: 721.gcc_r). Frequency was 3.2998–3.3000 GHz. There were **zero** architecture build or run failures.

**The profile.** Neoverse-V3 runs SPEC backend-bound: the backend is the largest stall bucket in 20/26 benchmarks (all 12 FP, 8/14 integer), at a median of 39.5 % of slots. The suites differ mainly on speculation: bad speculation has a median of 11.4 % on integer and 0.36 % on FP. IPC spans 1.90–4.71 (median 3.33).

**Against x86** (Golden Cove, same SPEC set): IPC is higher on 25/26. ISA instruction counts differ, though (estimated 0.69–2.01× per run), so the IPC ratio is not a speed ratio. The TMA L1 analogues rank the benchmarks alike (Spearman 0.54–0.90) but differ in level, because Arm has 10 slots per cycle and Golden Cove has 6.

**One finding changes how ARM frontend numbers must be read.** The slot-based `Frontend-bound (%)` and the whole-cycle `Frontend-stall (% cycles)` disagree, worst on FP. For example, 782.lbm_r is 15.5 % frontend-bound but frontend-stalled for only 0.06 % of cycles. The cycle measure is the one that orders benchmarks the way x86's `fe_bound` does (ρ 0.84, against 0.54 for the slot measure).

## 2. Methodology

### 2.1 Capture, decision by decision

| # | Decision | Value | Why |
|---|---|---|---|
| D1 | Workload | 26 SPECrate, `refrate`, copies 1, threads 1, **command index 0** | Identical to the x86 rows (report 18 D1–D3), so every ARM row has an x86 partner. Benchmarks list 1–10 ref lines; 8 have only one. |
| D2 | Build | gcc/g++/gfortran **14.2.0**, `-g -O3 -mcpu=native`, `uarch-gcc14-aarch64.cfg` (the x86 cfg with only `-mabi=lp64` and the OPTIMIZE line changed) | Same compiler major as x86. GCC 14 does not name Neoverse-V3: `-mcpu=` comes out empty and `-march=armv8-a+…+sve2-…`. The binaries therefore have **generic tuning + detected features**, which is a fact about this build. |
| D3 | Isolation (**Jerry**) | Jef's 8+8 layout **at runtime**, no reboot: CPUs 16–191 offline; init/system/user slices → 0–7; IRQs + workqueue mask → 0–7; THP `never`; `irqbalance` stopped. Snapshot first, restore on any exit, ISO-PROOF before **every** pass | A metal reboot costs 5–10 min and affects Jef. Every boot knob except the default IRQ mask has a runtime equivalent. This is the layout of Jef's ARM agentic data. |
| D4 | Fence | Own cgroup `/sys/fs/cgroup/jerry-measured` (cpuset 8–15, **mems 0**), leaf `spec` = **CPU 8** only, plus `taskset -c 8` | perf must be armed on the cgroup before the workload exists, which a transient systemd scope cannot provide. mems 0 keeps every page on the core's node. Never inside Jef's `agentic-benchmark` tree. **Pinned to one core** (per Jerry), whereas x86 allowed migration across an 8-core fence. |
| D5 | Launch | perf forks `sh -c 'echo $$ > leaf/cgroup.procs && exec setpriv … env -i … taskset -c 8 bash run.sh'` | The child is fenced before exec, so counters see the first instruction. The x86 runner started perf after the scope existed and lost the first tens of ms. The determinism gate needs whole-run counts. `env -i` plus SPEC's per-benchmark environment file gives a reproducible environment. |
| D6 | Counting | One `perf stat -j -I 100 -C 8 -G <fence>` pass per family: cycle counter + ≤ 6 events, **14 families** (9 tier-1 sweeps of 26 benchmarks, then 5 tier-2 sweeps) | Jef's method: no multiplexing, no rotation. Tier 1 is Jerry's list. Tier 2 holds Jef's raw-code frontend events, which he qualified but never collected, so they ran only after tier 1 was banked. |
| D7 | Free extras | `cpu_cycles` in every family (dedicated counter); `inst_retired` in the free 6th slot of the tier-2 families | Gives a frequency witness and determinism coverage on every pass without taking a counter from Jef's events. |
| D8 | Per-pass gates | Every active window `pcnt-running ≥ 99.999`; `cpu_cycles/cnt_cycles` within ±0.1 GHz of 3.3; the **benchmark's own** exit status (`bench.rc`); SPEC output check passes (or is *unavailable* for vpr/gem5/marian, as on x86); witness clean; per-benchmark `inst_retired` spread ≤ 0.5 % across all passes | perf 6.17 returns 0 even when the workload crashes. Jef's mux check reads fields that `perf stat -j` 6.17 does not emit, so it could never fire. We gate on `pcnt-running` directly. |
| D9 | Witness | `quiet_gate.py witness` every 2 s (dirty if any foreign task is > 10 % or the total > 40 %), plus a `/proc/stat` sampler on CPUs 0–15 (dirty if any of 9–15 is > 10 %). A dirty pass is re-run, ≤ 3 attempts | These are the x86 kit's thresholds, reused unchanged. |
| D10 | Qualification | `arm_profile.py qualify` once per boot: each family counts 1.5 s on CPU 8 against a fenced busy probe | Uses the same perf command builder and parser as production. |
| D11 | Metrics | 28 metrics from Jef's formulas (`config/profiling_plan.toml`), each evaluated per window over **one pass's co-counted events**. Windows with < 2 ms of fence task-clock are dropped. The **vote** (window mean, Jef's schema) and the **ratio of sums** are both exported, with `gap_pct` | They differ for phased programs, and the gap is a finding (insight 8). |
| D12 | Cross-ISA | ARM ratio of sums against x86 `metrics.json` episode values, with a parity label (exact / analogue / partial / none) on every metric (`metric_parity.csv`) | x86 episode metrics are ratios of sums (report 18). The label travels with every cross-ISA number. |

### 2.2 Verification, hazards and defects

**Gates, recomputed from `episodes.csv` / `determinism.csv`** (364 accepted passes):
- Counting:
  - min `pcnt-running` 100.0, 0 multiplexed windows.
  - Window coverage (active windows × 0.1 s ÷ pass wall) is **0.990–1.000** (median 0.999), against x86's 83.3 % duty.
  - Only 8 of 245,497 active windows fell under the 2 ms task-clock floor.
- Clock: cycles/task-clock 3.29984–3.29996 GHz on every pass; cycles/`cnt_cycles` 3.2999998–3.3000000 on the 26 frequency passes.
- Exit and output:
  - `bench_rc` and `perf_rc` were 0 on all 364 passes.
  - Output check: 322 pass. 42 are *unavailable* (vpr, gem5 and marian × 14), so for those only exit status 0 is proven.
- Isolation: ISO-PROOF measured-core busy was 0.0 % before every pass.
  - Sibling cores 9–15: max 0.5 %.
  - CPU 8: mean busy 99.0–99.99 % (median 99.91 %).
- Determinism: 26/26 OK with 14 passes each.
  - Max spread **0.201 %** (721.gcc_r, worst family `branch-types`, +0.121 % from median), then 714.cpython_r 0.182 %.
  - Median 0.016 %.
- Exporter consistency: the votes recompute exactly from `spec26_arm_windows.csv.gz` (0/728 mismatches), and `spec26_arm_vs_x86.csv` matches both the votes and x86 `metrics.json` (0 mismatches).

**Witness rejections (4 of 368 attempts; each re-run was VALID at `a2`):**

| Pass | Worst foreign task | CPU 8 busy | Siblings 9–15 |
|---|---|---|---|
| 721.gcc_r / anchor | 20.0 % (total 20.5 %) | 99.93 % | 0.0 % |
| 765.roms_r / frequency | 11.0 % | 99.98 % | 0.0 % |
| 765.roms_r / tlb-data | 11.0 % | 99.98 % | 0.0 % |
| 707.ntest_r / execution | 15.0 % | 99.97 % | 0.0 % |

All four foreign tasks ran on the housekeeping cores. Accepted passes peaked at exactly 10.0 % (the threshold is > 10 %). The re-runs cost 10.6 min of benchmark time.

**Defects found and fixed, each of which would have shipped:**
- **`irqbalance` undid the IRQ shield within ~10 s.** NIC queues (2–3 per CPU) and PCIe `bwctrl` IRQs (7 per CPU) landed on cores 8–15, while ISO-PROOF still said `true`. The fix stops irqbalance (snapshotted and restarted on restore). ISO-PROOF now fails on any non-managed IRQ effective on 8–15. 208 kernel-managed IRQs refuse the move; on 8–15 only per-CPU `nvme*q*` queues remain.
- **Snapshot parser lost an empty field.** Tab is IFS whitespace, so the empty `AllowedCPUs` collapsed and restore set the slices to `0-191`. Fixed with a `|` delimiter.
- **systemd does not rewrite `cpuset.cpus` when `AllowedCPUs` is reset to empty**, and the kernel refuses an empty write. Without a fix, every campaign would have left everyone's slices, Jef's included, on CPUs 0–7 until reboot (the x86 §1.5 bug in reverse). Restore now writes the snapshot's raw value, or its *effective* set when the raw value was empty.
- **perf 6.17 returns 0 for a failing workload** (`sh -c 'exit 3'` → rc 0), so the gate uses `bench.rc`.
- **Relative `--out`.** The generated per-pass run script changes into the run dir before writing `bench.rc`, so with a relative `--out` every smoke pass was INVALID. The gate caught it and no data was affected.
- **Not a check:** the smoke log's "FE + BE + Ret + BadSpec = 100.0 %" is an algebraic identity of the four formulas (the `4·br_mis_pred` and `op_retired/op_spec` terms cancel). It holds whatever the counts are.

**Known limitations.**
- (a) The `backend` and `execution` families were counted and gated, but `profiling_plan.toml` defines no metric on them. Their counts live only in the raw archive and the determinism gate.
- (b) Arm cache and TLB events count speculative accesses with stores included. `L1D-load MPKI` / `L2-load MPKI` are Jef's names for refills of all access types.
- (c) `LLC MPKI` and `DRAM read (GB/s)` are core-side proxies with no uncore PMU, and what "last level" is on Graviton5 is unverified. The x86 counterparts are different quantities again ([`spec26_profile_validation.md`](../../spec26/infra_kit/docs/spec26_profile_validation.md) §1.1–1.2): partial parity, never quoted as DRAM.
- (d) There is no macro-op or µop-cache event (73 sysfs aliases checked), so the 6 x86 DSB/MITE/MS/LSD metrics have no ARM row.
- (e) THP was `never` during capture, so TLB metrics hold for that setting.
- (f) Only command index 0 runs (as on x86; report 18 caveats apply).
- (g) Frequency was 3.3 GHz here and 3.2 GHz on x86.
- (h) Pinning did not change x86 in practice: x86's own `cpu-migrations` counter is **0 in all 26** `metrics.json` (counted windows only, and `mean_cores` is 1.000). It still separates the two by construction.
- (i) The x86 comparison uses one machine per ISA, with different SMT-off cores, slot widths (6 vs 10) and cache sizes. Only rank and shape statements are robust.

**Session-log claims re-checked.**
- These reproduce from the CSVs: 234/234 + 130/130 valid, 4 witness re-runs (CPU 8 ≥ 99.93 % in all four, not just the three tier-1 ones), 0.201 % on 721.gcc_r, and 3.300 GHz.
- These reproduce from the raw receipts: qualification 14/14 and smoke 9/9 (spread 0.096 %).
- The frontend cross-check (core + mem = 98.1–102.6 %; children up to 10 and 55 points short) is on **window means**. On ratios of sums it is 97.9–103.0 %, 10.4 and 52.2.
- One minor timing disagreement: tier 2 ran 13:37:31 → 16:47:48 = **38.1 min per sweep**, not "~37.5". Benchmark wall per sweep was 34.1–37.6 min across all 14 families.

### 2.3 Reproduction recipe

Cost: about $8.5/h for the box. Build takes 12 min. Tier 1 took 5 h 46 min and tier 2 took 3 h 10 min (~38 min per family sweep). There is no API cost. Before starting, check the box is free (`who; pgrep -a -x perf`), and never touch another user's processes or cgroups.

```bash
sudo apt-get install -y gcc-14 g++-14 gfortran-14 make
(cd ~/spec26-media/install_archives && sha256sum -c cpu2026.tar.xz.sha256)   # ba6b6359…2959
(cd ~/spec26-media && ./install.sh -f -d ~/spec26-arm/cpu2026 -u linux-aarch64)
cp spec26/infra_kit/config/uarch-gcc14-aarch64.cfg ~/spec26-arm/cpu2026/config/   # fill hw_* from lscpu
export SPEC_ROOT=~/spec26-arm/cpu2026 CFG_NAME=uarch-gcc14-aarch64 SPEC_LABEL=uarch SPEC_SIZE=refrate
BUILD_SLOTS=26 BUILD_NCPUS=6 spec26/infra_kit/scripts/build_one.sh <bench>    # x26, BEFORE any isolation
runcpu --config=$CFG_NAME --action=setup --size=refrate --tune=base --nobuild --iterations=1 <bench>
python3 spec26/infra_kit/scripts/extract_cmd.py <run_base_refrate_uarch.0000> arm/data/interim/spec/cmds/<bench>
arm/kit/arm_shield.sh apply && arm/kit/arm_shield.sh verify && python3 arm/kit/arm_profile.py qualify
python3 arm/kit/arm_profile.py run --families tier1 --bench 736.ocio_r && arm/kit/arm_shield.sh restore  # smoke
tmux new -s armspec 'python3 arm/kit/arm_profile.py run --shield --families tier1 2>&1 | tee -a arm/data/interim/tier1.log'
#   then the same with --families tier2 (resumable: DONE marker per <bench, family>)
python3 arm/kit/export.py --selftest && python3 arm/kit/export.py
```

The raw passes are in `arm/data/arm_spec26_raw_20261103.tar.zst` (25 MB; `tar -I zstd -xf` from `arm/data/`): 368 pass dirs with perf JSON, meta, witness, procstat and the per-pass run script. Re-running `export.py` on it regenerates every CSV.

What should reproduce: instruction totals to < 0.25 %, and cycle-normalised metrics closely (insight 8). Per-instruction rates on phased benchmarks are less stable.

### 2.4 Scripts and artifacts

| Item | Location | Role |
|---|---|---|
| Shield | [`arm/kit/arm_shield.sh`](../../arm/kit/arm_shield.sh) | `apply / verify / restore / status`: runtime 8+8 layout, snapshot restore, ISO-PROOF |
| Profiler | [`arm/kit/arm_profile.py`](../../arm/kit/arm_profile.py) | `qualify / run / check / summary`: fenced launch, one pass per family, gates, witness, retries |
| Exporter | [`arm/kit/export.py`](../../arm/kit/export.py) | Raw passes → windows, votes + ratio of sums, episodes, determinism, x86 join (`--selftest`) |
| Plan | [`arm/config/profiling_plan.toml`](../../arm/config/profiling_plan.toml) | Families → events (aliases + 12 raw codes), formulas, parity labels, suites |
| Host | [`arm/config/host.toml`](../../arm/config/host.toml) | The box as observed: CPUs, caches, kernel, perf, PMU, cmdline |
| Reused x86 kit | `spec26/infra_kit/scripts/{build_one.sh,spec_env.sh,extract_cmd.py,clean_rundir.py,verify_output.py,quiet_gate.py}` | Build, setup, run-dir hygiene, specdiff, witness |
| Processed data | `arm/data/processed/spec26/` | `spec26_arm_windows.csv.gz` (572,851 rows), `spec26_arm_votes.csv` (728), `episodes.csv` (368 attempts), `determinism.csv` |
| Figure data | `arm/reports/figures/data/` | `spec26_arm_votes.csv`, `spec26_arm_vs_x86.csv`, `metric_parity.csv` (Jef's schemas) |
| x86 side | `spec26/infra_kit/x86_results/<bench>/metrics.json` | x86 episode metrics, read-only |

## 3. Key insights (most → least important)

1. **Neoverse-V3 runs SPEC26 backend-bound, and the two suites split on speculation, not on throughput.**
   - Backend-bound is the largest stall bucket in **20/26** benchmarks: all 12 FP and 8/14 integer.
   - Medians: FP backend 46.3 % vs integer 32.1 %; bad speculation integer **11.4 %** vs FP **0.36 %**. Branch MPKI shows the same split: 1.88 vs 0.052, a 36× gap. 8/14 integer benchmarks lose > 10 % of slots to bad speculation, against 2/12 FP (gmsh 16.1 %, astcenc 11.7 %).
   - The frontend is an integer story. Five benchmarks lead with it: cpython 42.3 %, llvm 36.6 %, cppcheck 35.2 %, ns3 33.9 %, and gem5 at 28.9 % (tied with its backend at 28.8 %). abc is the only one led by bad speculation (37.1 %).
   - The most backend-bound are nest 59.5 %, fotonik3d 56.4 %, lbm 53.8 %, omnetpp 53.7 %, ocio 53.0 % and roms 52.0 %.
   - IPC spans 1.90 (abc) to 4.71 (cpython) and does **not** separate the suites (median 3.15 integer vs 3.43 FP).
2. **On ARM, read frontend starvation from `Frontend-stall (% cycles)`, not from the slot-based `Frontend-bound (%)`.**
   - Frontend-stall is below 1 % of cycles on 8 benchmarks whose Frontend-bound reads 9.4–24.4 %: lbm 0.06 vs 15.5, fotonik3d 0.09 vs 16.7, sealcrypto 0.25 vs 24.2, roms 0.35 vs 15.8, plus marian, palm, femflow and ocio.
   - By the event definitions, that slot loss happens in cycles where the frontend delivered some ops but fewer than the 10 slots. The data shows this is not starvation; it does not show why.
   - The two measures rank the 26 benchmarks almost independently (Spearman 0.30). Against x86 `fe_bound`, Frontend-stall ranks at **0.84** and Frontend-bound at 0.54.
   - Median Frontend-stall is 6.8 % on integer and 0.95 % on FP. The maxima are llvm 25.9 %, gcc 20.1 %, cpython 17.1 % and ns3 15.4 %.
3. **IPC is "exact" parity, but the cross-ISA IPC ratio is not a speed ratio.**
   - ARM IPC is higher on **25/26** (median 3.33 vs 2.43, ratio 1.36×). The range runs from 0.99× (sealcrypto) to **3.20×** (fotonik3d), with roms at 2.56×. Those two are x86's two most backend-bound benchmarks (79.9 %, 70.1 %).
   - The two ISAs retire different instruction counts for the same run. *Estimated* ARM/x86 instructions: median 1.01, range 0.69 (sealcrypto) to **2.01** (femflow). The ratio is high on FP: cactus 1.86, roms 1.71, fotonik3d 1.64, ocio 1.45.
   - *Estimated* CPU time ARM/x86: median **0.73**, with ARM shorter on 25/26. femflow is the exception at **1.50×** despite a 1.30× IPC ratio.
   - How the estimates were made:
     - ARM side: anchor-pass `inst_retired`, and `cpu_cycles` ÷ 3.3 GHz.
     - x86 side: cycles = continuous-TMA slots ÷ 6 (report 18: 6.00–6.02 slots per cycle), × windowed IPC for instructions, ÷ 3.2 GHz for time.
     - Sanity check: x86 wall exceeds that CPU time by 0.8–5.5 s (lead-in and teardown), and ARM wall exceeds its CPU time by 0.05–0.17 s.
4. **The TMA L1 shape transfers across ISAs; the levels do not** (analogue parity).
   - Spearman ARM vs x86 per bucket: bad speculation **0.90**, retiring 0.81, backend 0.72, frontend 0.54. The largest non-retiring bucket agrees on 19/26.
   - In level, ARM reads more backend-bound on 21/26 (median 39.5 vs 26.7 %) and *less* retiring on 21/26 (32.8 vs 36.0 %), even though its IPC is higher on 25/26.
   - That combination is expected when the denominator is 10 slots per cycle against Golden Cove's 6. Compare the shapes, never the percentages.
5. **Instruction supply singles out the same benchmarks as on x86, at far lower miss rates.**
   - L1I MPKI > 1 on 9 benchmarks: cactus 15.3, gem5 13.8, llvm 12.9, cpython 8.86, gcc 8.40, ns3 7.63, flightdm 7.33, omnetpp 1.97, palm 1.82.
   - `frontend_l1i_bound` follows them (cactus 81 %, gem5 61 %, cpython 54 %, flightdm 50 % of frontend stalls; ρ 0.78).
   - Against x86 `L1I_MPKI` (analogue), ARM is lower on **26/26** (median 0.27×) with the same ordering (ρ 0.93). That is consistent with ARM's 64 KB L1I, but not proven by it.
6. **Branches: Neoverse-V3 mispredicts direction, almost never target, and less often than Golden Cove.**
   - In the 15 benchmarks with Branch MPKI > 0.1, immediate-branch mispredicts are **95–100 %** of all mispredicts (median 99.5 %). Target mispredicts reach at most 0.142 MPKI (llvm).
   - Branch MPKI (exact parity) ranks the benchmarks like x86 at **ρ 0.975**, and ARM is lower on 21/26 (median 0.77×).
   - Per run, after correcting for instruction counts, 13/14 integer benchmarks mispredict less on ARM (0.30–0.95×). cpython is the exception, at negligible rates (0.010 vs 0.002 MPKI).
7. **The frontend breakdown partitions its parent, but `flow + flush` leave much of `frontend_core_bound` unattributed.**
   - Figures here are window means; on ratios of sums they are 97.9–103.0 %, 10.4, median 15.5 and max 52.2.
   - core + mem = 98.1–102.6 % of `stall_frontend` per benchmark, even though they come from separate passes.
   - The memory children (l1i + l2i + tlb) fall at most 10.4 points short of `frontend_mem_bound` (cppcheck).
   - The core children leave a median **14.8 points (~25 % of core-bound)**, up to **55.1 points** on cppcheck, to events Neoverse-V3 does not expose.
   - Flush dominates on the branchy codes: nest 82.6 %, zstd 80.3 %, abc 77.7 %, stockfish 76.7 % (ρ 0.53 with bad speculation).
   - The children are shares of `stall_frontend`. lbm's `frontend_l2i_bound` of 55.5 % is a share of 0.06 % of cycles, so weight by Frontend-stall before reading them.
8. **The window-mean vs ratio-of-sums gap is structural: negligible for per-cycle metrics, large for per-instruction ones.**
   - IPC, the TMA buckets and Frontend-stall have a median gap of 0.04 % and stay within 1.3 %. The exceptions are bad-speculation values below 0.4 %, up to +4.2 % on fotonik3d's 0.03 %. 100 ms windows at a fixed 3.3 GHz on a ≥ 99 %-busy core carry equal cycles, so a window mean is a ratio of sums.
   - Per-instruction metrics gap > 5 % in **169/312** rows. The window mean is higher in 257/312, because high-MPKI phases retire fewer instructions. For example, gmsh Branch MPKI is 5.65 vs 2.85 and its L2 is 6.89 vs 3.31, across windows with IPC 1.00–4.70.
   - Children of `stall_frontend` are worst: cactus `frontend_l2i_bound` is 27.6 vs 1.7.
   - Use the ratio of sums for MPKI and for every cross-ISA number. That is x86's convention; the vote exists only because Jef's schema asks for it.
9. **The memory ladder falls off after L2, and the cross-ISA L2/LLC/DRAM gaps are definitional** (analogue/partial parity).
   - L2-load MPKI is high on the streaming FP codes: fotonik3d 46.5, roms 32.7, lbm 27.4, nest 22.7. Yet LLC MPKI is only 0.2–9 % of it, and the DRAM proxy peaks at 1.54 GB/s (lbm; median 0.032).
   - This data cannot tell whether the 192 MB L3 absorbs that traffic or the LL event misses prefetches.
   - Against x86, ARM L2 MPKI is higher on 26/26 (median 5.6×) and its DRAM proxy is lower on 26/26 (median 0.026×). Both are definition gaps (speculative refills incl. stores vs retired loads; core LL-miss vs L2→uncore reads). Do not quote either as a microarchitectural difference.
10. **The witness is strict by design, and the data is as deterministic as SPEC gets.**
    - Every rejected pass had CPU 8 at ≥ 99.93 % workload and siblings at 0.0 %. The rejections were for an 11–20 % foreign task on the housekeeping cores. The gate guards the shared box rather than an observed contamination, at a cost of 10.6 min.
    - 14 independent passes per benchmark agree to a median 0.016 % in instructions, which is what licenses joining families measured in different runs into one profile.
11. **Context switches are a floor, not a workload signal.**
    - 4.87–7.52 per CPU-second on ARM, against an x86 median of 4.54, with a rank correlation of **−0.31** (exact parity).
    - With one pinned process per core and no migrations on either side, nothing workload-driven remains to measure.
