# Session 2026-11-03 — SPEC CPU 2026 single-core profile on AWS Graviton (ARM)

**Goal:** execute `docs/handoff/execution/arm_spec_profiling.md` end to end on branch `spec-arm`.
**Machine state at start (2026-11-03 00:02 UTC, uptime 2:51):** AWS `c9gd.metal-48xl`,
192 × Neoverse-V3 (MIDR `0x410fd841`), 2 NUMA nodes (0–95, 96–191), 377 GiB, kernel
`6.17.0-1017-aws`, perf 6.17.13 (`/usr/bin/perf`), gcc 13.3.0 default. Only user on the box:
`ubuntu` pts/0 (Jerry, this session). No `perf`, no docker containers, no `agentic*`
process; `agentic-benchmark-host-policy.service` is loaded **active (exited)** — Jef's
boot-scoped oneshot, not a capture; left untouched. `~/agentic-benchmark` (Jef's) present,
not read, not touched. `~/jerry-spec` existed and was **empty** → cloned (§1.4 rule "absent
or empty"). `~/spec26-media` already present (6.5 GB, `install.sh` + `install_archives/`),
so no transfer was needed.
**Live kernel cmdline:** `BOOT_IMAGE=/vmlinuz-6.17.0-1017-aws root=PARTUUID=… ro console=tty1
console=ttyS0 nvme_core.io_timeout=4294967295 panic=-1` — **not** Jef's controlled boot (no
`irqaffinity`, `workqueue.unbound_cpus`, `nmi_watchdog=0`, `transparent_hugepage=never`).
**Live knobs:** CPUs 0–191 online; `init.scope`/`system.slice`/`user.slice` effective cpuset
0–191 (AllowedCPUs empty); no `/sys/fs/cgroup/agentic-benchmark`; `perf_event_paranoid` = 4,
`kptr_restrict` = 1; `nmi_watchdog` = 0 (already); THP `madvise`; workqueue cpumask and IRQ
default affinity = all CPUs; no cpufreq driver; PMUs: `armv8_pmuv3_0` only (no SPE device).
`df -h ~`: 387 G, 214 G free. `free -g`: 377 total, 366 free.
**Push access:** `git push --dry-run origin spec-arm` over SSH (key `~/.ssh/id_ed25519`,
authenticates as Jerry0209) → OK. Repo-local git identity set to `Jerry0209
<mr.htianrui@gmail.com>` (global `~/.gitconfig` is shared and was not edited).

## Decisions
| # | Decision | Why | Made by |
|---|---|---|---|
| 1 | Clone `spec-arm` into the empty `~/jerry-spec`; push URL set to SSH | §1.4 rule; the box's key authenticates as Jerry0209, HTTPS has no credentials | Claude |
| 2 | Isolation via **runtime equivalents** of Jef's controlled boot, no reboot/GRUB: IRQ affinity → 0–7 (`/proc/irq/*/smp_affinity_list`, managed IRQs left as the kernel pins them), workqueue cpumask → 0–7, THP → `never`; `nmi_watchdog` already 0 | Every boot knob except the IRQ *default* is settable at runtime and restorable from a snapshot; a metal reboot costs 5–10 min and affects Jef | **Jerry** (asked 2026-11-03 00:08) |
| 3 | Offline CPUs 16–191 for the captures (Jef's 8 + 8 layout: online 0–15), restore after with a trap and verify | Same layout as Jef's ARM agentic data | **Jerry** |
| 4 | Tooling: gcc/g++/gfortran 14.2.0 (`14.2.0-4ubuntu2~24.04.1`) from the Ubuntu archive. `gcc-14 -mcpu=native -Q --help=target`: `-mcpu=` **empty** (GCC 14 does not name Neoverse-V3), `-march=armv8-a+rng+flagm+lse+dotprod+rdma+crc+fp16fml+rcpc+i8mm+bf16+sve2-aes+sve2-bitperm+sve2-sha3+sb+pauth`, `-mtune=` empty — the build is generic tuning + detected features | Same major version as x86; fact about the build | Claude |
| 5 | SPEC media: `~/spec26-media` (v1.0.1) already on the box; `sha256sum -c cpu2026.tar.xz.sha256` OK, hash `ba6b6359…2959` = P7's. Installed `./install.sh -f -d ~/spec26-arm/cpu2026 -u linux-aarch64` (1 m 43 s); `runcpu (9ba4d1e3)`, tools `linux-aarch64`, CPU2026 1.0.1 | §2 | Claude |
| 6 | Config `uarch-gcc14-aarch64.cfg`: only `hw_*`/`sw_os002` filled from `lscpu` (64 KB L1I + 64 KB L1D, 2 MB L2 per core, 192 MB L3 in 2 instances); copied into `$SPEC/config/`. `spec_env.sh`: perf glob falls back to `command -v perf` (P7 behaviour unchanged) | §3 | Claude |
| 7 | PMU check: 73 sysfs aliases on `armv8_pmuv3_0`, `caps/slots` = 10; **no macro-op/uop-cache event** in sysfs or `perf list` (the only `perf list` hits for mop/op_cache are `semop` tracepoints) → x86 DSB coverage/MPKI parity = **none**. All 12 raw codes of Jef's plan (`0x8111 0x8113 0x8115 0x7a 0x79 0x8158 0x8159 0x815b 0x815c 0x8160 0x8161 0x8162`) open and count at 100 % running (50 ms on CPU 0) | §5 | Claude |
| 8 | Launch: perf forks the workload (`perf stat … -- sh -c 'echo $$ > <cg>/cgroup.procs && exec setpriv … taskset -c 8 …'`), so the child is inside the fence before exec and counters are enabled before exec. The x86 runner instead started perf after a `systemd-run --scope` already ran the benchmark, leaving its first tens of ms uncounted | Jef's moved-after-fork defect; the 0.5 % `inst_retired` determinism gate needs whole-run counts | Claude |
| 9 | Fence = our own top-level cgroup `/sys/fs/cgroup/jerry-measured` (cpuset 8–15, **mems 0**) with leaf `spec` (cpuset **8**), created by `arm/kit/arm_shield.sh apply`, removed by `restore`. Not a systemd scope | perf must be armed on the cgroup **before** the workload starts; a transient scope only exists once its process does. mems 0 keeps every page on the measured core's node. Never inside Jef's `agentic-benchmark` tree | Claude |
| 10 | Every family gets `cpu_cycles` (dedicated cycle counter, free); tier-2 families lacking `inst_retired` get it in their free 6th slot. No programmable counter is taken from Jef's events | Per-pass frequency witness (cycles / task-clock) and a determinism gate that covers every pass | Claude |
| 11 | Witness per pass = `spec26/infra_kit/scripts/quiet_gate.py witness` (foreign tasks, 2 s; dirty if any task > 10 % or total > 40 %, the x86 thresholds) + a per-CPU `/proc/stat` sampler for CPUs 0–15 (dirty if any of 9–15 > 10 % in a 2 s sample). Dirty → pass re-run, ≤ 3 attempts | Doc §4.5; reuse of the x86 kit's architecture-neutral witness | Claude |
| 12 | Benchmark env = `env -i` + HOME/USER/LOGNAME/PATH/`LANG=C.UTF-8` + SPEC's own `env.sh`; stack limit inherited (8 MB, as x86) | Reproducible environment; x86 ran with the user's sudo env | Claude |
| 13 | Qualification is a subcommand (`arm_profile.py qualify`), not a separate `qualify.py` | Same code path as production (same perf command builder and parser) | Claude |
| 15 | Stop `irqbalance` while the shield is up, restart on restore | Needed for the approved runtime IRQ affinity (decision 2) to hold at all; system daemon, not another user's process; restorable | Claude |
| 16 | Commit the ARM kit despite the checker's 11 pre-existing `[freshness]` warnings (agentic reports 01–15 vs `measure.sh`, `run_glm_campaign.sh`, `analyze_l3_windows.py`, `localize_traj.py`, none touched here) | Code off the box early; warnings unrelated to this work | **Jerry** (override, 2026-11-03 ~07:51) |
| 14 | Metric spelling: `L1D-load MPKI` = 1000·`l1d_cache_refill`/inst and `L2-load MPKI` = 1000·`l2d_cache_refill`/inst (Jef's figure names for the doc's L1D/L2 MPKI formulas), parity *analogue* (Arm counts speculative accesses incl. stores). Full parity table in `arm/config/profiling_plan.toml` | Doc §5 + §7 | Claude |

## What changed
- 07:41 qualification PASSED, 14/14 families (`arm/data/raw/qualification/20261103T074118/`): min pcnt-running 100.0, cycles/task-clock 3.3000 GHz, cnt_cycles/task-clock 1.0000 GHz (timer is 1 GHz: two clocks agree).
- 07:47–07:49 smoke `736.ocio_r` × 9 tier-1 families: 9/9 VALID (7.0–7.1 s each, output pass, 70 windows, witness clean, CPU 8 ≈ 99 % busy, siblings 9–15 0.0 %), inst_retired spread **0.096 %**; export to scratch produced all 7 CSVs; FE+BE+Ret+BadSpec = 100.0 %. Restore verified 07:49. (First smoke attempt: every pass INVALID `bench_rc` — relative `--out` path, `run.sh` cd's into the run dir before writing `bench.rc`; fixed by resolving `--out`; gate caught it, no data affected.)
- 07:49:44 **tier 1 × 26 started** in tmux `armspec` (`run --shield --families tier1`, log `arm/data/interim/tier1.log`).
- 13:36:07 **tier 1 done: 234/234 ⟨benchmark, family⟩ VALID** (9 families × 26; ~38.5 min per family sweep, 5 h 46 min total), every pass 3.300 GHz, no multiplexing; determinism 26/26 OK (max inst_retired spread 0.201 %, 721.gcc_r). 3 passes INVALID `witness`, each re-run VALID at a2: 721.gcc_r/anchor (my own session process 20 % on housekeeping), 765.roms_r/frequency and 765.roms_r/tlb-data (one 100 ms row with an 11 % foreign task on housekeeping; the second coincides with my 12:43 status check). In all three CPU 8 was ≥ 99.9 % the workload and siblings 9–15 0.0 %; the gate is deliberately conservative. Restore verified 13:36 (online 0-191, slices eff 0-191, irqbalance active). Exported → `arm/data/processed/spec26/`, `arm/reports/figures/data/` (tier-2 metrics empty until tier 2).
- 00:13:02 → 00:25:10 UTC: all **26/26 benchmarks built BUILD-OK** (gcc-14, `uarch-gcc14-aarch64`, 26 slots × `make -j6`, 12 min wall). No architecture build failure.
- **00:25 → 07:34 UTC: stalled on the Claude account's 5-hour usage limit** (both subagents and the main session stopped; resumed when Jerry said "try again"). Nothing was running on the box meanwhile and no isolation was applied; ~7 h of instance time (~$60) was idle.
- New (uncommitted yet): `arm/README.md`, `arm/config/{host.toml,profiling_plan.toml}`, `arm/kit/{arm_shield.sh,arm_profile.py}`; `spec26/infra_kit/config/uarch-gcc14-aarch64.cfg` hw fields; `spec26/infra_kit/scripts/spec_env.sh` perf fallback; `.gitignore` (arm raw/interim).

## Defects found
- **`irqbalance` undid the IRQ shield within ~10 s** (07:37 apply): ENA NIC queues `enP2p4s0-TxRx-*` (2–3 per CPU) and PCIe `bwctrl` IRQs (7 per CPU) became effective on every measured core 8–15, while the first ISO-PROOF still said `iso_proof: true` (it only counted IRQs outside house, it did not gate). Would have shipped: network/PCIe interrupts on CPU 8 during every pass, under a "proven" shield. Fix: `apply` stops `irqbalance` (state snapshotted, restarted by `restore`), ISO-PROOF fails on any IRQ effective on 8–15 that is not one of the kernel-managed IRQs that refused the move (208 refused; on 8–15 only per-CPU `nvme*q*` queues remain).
- **Snapshot parser lost an empty field → restore set the slices to `AllowedCPUs=0-191`** instead of empty. Tab is IFS whitespace, so `read` collapsed the empty AllowedCPUs column and shifted the effective set into it; the restore's own check caught the mismatch (eff column then empty). Fixed with a `|` delimiter; snapshot corrected from the session-start values and re-restored.
- **systemd does not rewrite `cpuset.cpus` when `AllowedCPUs` is reset to empty**, and the kernel refuses an empty write (ENOSPC) — tested on a throwaway unit (`AllowedCPUs=0-3` → reset → raw and effective stayed `0-3`). Would have shipped: after every campaign, `init.scope`/`system.slice`/`user.slice` (everyone's work, Jef's included) left confined to **CPUs 0–7** until reboot — the x86 §1.5 bug in reverse. Fix: restore writes the snapshot's raw value, or when it was empty, the snapshot's **effective** set. Residue (cosmetic, resets at reboot): raw `cpuset.cpus` of the three slices reads `0-191` (was empty); effective identical; `/run/systemd/system.control/{system,user}.slice.d/50-AllowedCPUs.conf` hold an empty `AllowedCPUs=`. Round trip apply → restore re-verified ~07:39.
- **perf 6.17 `perf stat … -- <cmd>` returns 0 whatever the workload's exit status** (probe: `sh -c 'exit 3'` → perf rc 0). A runner gating on perf's rc would have passed crashed benchmarks. `arm_profile.py` banks the benchmark's own status (`bench.rc`, written by `run.sh`).

## Architecture failures (build/setup/run)
- **Build: none.** 26/26 `BUILD-OK`, every log `Build errors for intrate|fprate: None`; all 30 base binaries `ELF 64-bit LSB pie executable, ARM aarch64`, with debug_info. Slowest builds 766.femflow_r 728 s, 723.llvm_r 543 s, 735.gem5_r 456 s. Only ordinary `-W` diagnostics (e.g. llvm `MachineModuleInfo.cpp:240:51: 'this' pointer is null [-Wnonnull]`).
- **Setup: none.** 26/26 refrate run dirs (`run_base_refrate_uarch.0000/speccmds.cmd`), commands extracted to `arm/data/interim/spec/cmds/<bench>/` (n_cmds 1–10; index 0 runs). Note: 723.llvm_r's index-0 line contains `-mcpu=pwr9`: that is SPEC's input (the benchmarked `opt` emits POWER9 code), not a build flag.

## Open threads
