# Execution — SPEC CPU 2026 single-core profile on AWS Graviton (ARM)

**Owner:** Tianrui (Jerry) · **Written:** 2026-11-02 · **Status:** ready to execute
**Machine:** AWS `c9gd.metal-48xl` (192 × Neoverse-V3, 2 NUMA nodes, 377 GiB, Ubuntu 24.04, kernel
`6.17.0-1017-aws`, perf 6.17), the box Jef used for the Graviton5 agentic campaign. **About $8.5/h.**
**Results branch:** `spec-arm` · **Working folder on the box:** `~/jerry-spec`
**Request:** Jef, 2026-11: profile SPEC26 (single core) and the Server set on ARM with the same
metrics as his ARM agentic data. Server: [`arm_server_profiling.md`](arm_server_profiling.md).
Shared rules: [`README.md`](README.md).

Facts below about Jef's setup come from his private repo (`agentic-benchmark`, branch `feat/arm`,
commit 9aa188f), as read on 2026-11-02. Treat every one as **verify on the box**.

## 0. Done means

* All 26 SPECrate benchmarks are built for aarch64, with the same set, ref inputs, copies = 1,
  threads = 1 and ref command index 0 as the x86 rows.
* Each benchmark is profiled **pinned to one measured core**, with one dedicated counter pass
  per metric family (Jef's method: no multiplexing, no rotation, 100 ms windows). Every pass
  is ≥ 99.999 % running, at the platform frequency, with output check passed.
* `arm/` on branch `spec-arm` holds the profiler code, the processed per-window and
  per-benchmark CSVs in Jef's figure schema, metadata, a study report and a session log.
  Raw perf JSON is archived off the box.
* Build failures and run failures caused by the architecture change are listed explicitly
  (expected: none, but say so with evidence).

## 1. First 15 minutes — look before touching

1. **Who else is here.**
   * `who`;
   * `pgrep -a perf` and `pgrep -af agentic`;
   * `docker ps`;
   * `systemctl list-units 'agentic-benchmark*'`;
   * `ps -eo user,pcpu,etime,comm --sort=-pcpu | head -20`.

   If Jef has captures or services active, **stop and ask Jerry**. Never stop, kill or
   reconfigure Jef's units, containers, cgroups or files.
2. **Inventory into the session log:**
   * `lscpu`, plus the MIDR from `/proc/cpuinfo` (expect `0x410fd841` = Neoverse-V3);
   * `uname -r`, `perf --version`, `cat /proc/cmdline`;
   * `cat /sys/devices/system/cpu/online`, `numactl -H`;
   * `cat /proc/sys/kernel/perf_event_paranoid` (AWS ships 4);
   * the `cpuset.cpus.effective` of `init.scope`, `system.slice`, `user.slice` and
     `/sys/fs/cgroup/agentic-benchmark` if present;
   * `df -h ~`, `free -g`.
3. **Boot mode.** Jef's "controlled" boot has
   `nmi_watchdog=0 transparent_hugepage=never irqaffinity=0-7 workqueue.unbound_cpus=0-7`
   (plus an `agentic_benchmark.mode=controlled` marker) on the command line. If the live
   cmdline lacks these, **ask Jerry before any reboot or GRUB change**. A metal reboot takes
   5–10 min and also affects Jef.
4. **`~/jerry-spec`.** Jerry said there is a `jerry-spec` folder meant to hold this work in
   the layout of Jef's ARM branch. Jef's repo never mentions it, so inspect it:
   `ls -la ~/jerry-spec; git -C ~/jerry-spec status; git -C ~/jerry-spec remote -v; du -sh`.
   * **Absent or empty:** `git clone https://github.com/Jerry0209/InferSuite.git -b spec-arm ~/jerry-spec`.
   * **Non-empty and not this repo:** do not delete it. Move it to
     `~/jerry-spec.pre-$(date +%F)`, clone as above, and record in the session log what it
     contained (port anything useful into `arm/`).
   * **Already a clone of InferSuite:** `git fetch && git switch spec-arm`.
5. **Push access.** `git -C ~/jerry-spec push --dry-run origin spec-arm`. If the box has no
   credentials for `Jerry0209/InferSuite`, ask Jerry for a deploy key or token. Never use
   Jef's credentials. If none arrives, finish anyway and leave
   `~/jerry-spec-results-<date>.tar.zst` for Jerry to copy off.

## 2. SPEC CPU 2026 onto the box

SPEC is licensed and the repo is public, so SPEC travels by scp/rsync, never by git. The GCS
bucket used on x86 no longer exists. The source is P7's original media,
`/home/thu/spec26-infra/spec26-orig` (version 1.0.1). Transfer it minus the redundant split
archives and the redistributable sources: about 7.5 GB, of which `cpu2026.tar.xz` is 3.8 GB
and `benchball/` 3.2 GB.

**Jerry runs one of these** (P7 has no key for the box today):

```bash
# (a) from P7, after putting the box's PEM on P7 and a Host block "agenticbox" in ~/.ssh/config
rsync -a --info=progress2 \
  --exclude 'install_archives/cpu2026.tar.xz.part*' --exclude 'redistributable_sources/' \
  /home/thu/spec26-infra/spec26-orig/ agenticbox:~/spec26-media/

# (b) from a laptop that can ssh to both (streams through, stores nothing locally)
ssh p7 "tar -C /home/thu/spec26-infra -cf - --exclude='spec26-orig/install_archives/cpu2026.tar.xz.part*' \
        --exclude='spec26-orig/redistributable_sources' spec26-orig" \
  | ssh agenticbox "mkdir -p ~/spec26-media && tar -xf - -C ~/spec26-media --strip-components=1"
```

**The ARM session:**

* If `~/spec26-media/install.sh` is missing, print command (b) for Jerry and continue with
  §3–§4 meanwhile.
* Once the media is there:
  * `cd ~/spec26-media/install_archives && sha256sum -c cpu2026.tar.xz.sha256` (it must say
    OK; md5 `33eed6c9f6a0e4e4c3e9f865a08e5706` is in `cpu2026.tar.xz.md5`);
  * `cd ~/spec26-media && ./install.sh -d ~/spec26-arm/cpu2026 -u linux-aarch64` (check
    `./install.sh -h` first; `-u` picks the prebuilt `tools/bin/linux-aarch64` toolset);
  * `cd ~/spec26-arm/cpu2026 && . ./shrc && runcpu --version`.
* Toolchain: `sudo apt-get install -y gcc-14 g++-14 gfortran-14 make` (same major version
  as x86). Record `gcc-14 -mcpu=native -Q --help=target | grep -E "mcpu|march"`. GCC 14 may
  not name the core, and that is a fact about the build worth writing down.

## 3. Build

* Config: `spec26/infra_kit/config/uarch-gcc14-aarch64.cfg` (in the repo). It is the x86
  config `uarch-gcc14.cfg` with only `-mabi=lp64` and `-g -O3 -mcpu=native` changed. Copy it
  into `$SPEC/config/` and fill in its `hw_*` fields.
* Kit: `spec26/infra_kit/scripts/` holds the x86 kit's code. Reuse these unchanged, through
  `SPEC_ROOT=~/spec26-arm/cpu2026 CFG_NAME=uarch-gcc14-aarch64 SPEC_LABEL=uarch`:
  * `build_one.sh` and `spec_env.sh` (fix the paths and the perf glob in `spec_env.sh` for
    this box);
  * `extract_cmd.py`, `clean_rundir.py`, `verify_output.py`.
* Build all 26 **before** any isolation is applied, and never while someone else is
  measuring. Builds are outside the fence. Set `BUILD_SLOTS`/`BUILD_NCPUS` to the online
  cores you may use.
* Then `runcpu --action=setup --size=refrate --tune=base --nobuild --iterations=1 <bench>`
  per benchmark (the x86 `setup_bench`), and `extract_cmd.py` to get `speccmds_all.txt` +
  `env.sh`. Run **line 0** (`cmd_index.tsv` is index 0 everywhere).
* A build or setup failure that comes from the architecture (x86 intrinsics, inline asm,
  an `-m64` assumption) goes in the session log and the report as an **architecture
  failure**, with the error line. Do not patch benchmark sources (that would make it a
  different benchmark). Expected: all 26 build, because SPEC ships an aarch64 example config
  with the same PORTABILITY flags.

## 4. Isolation — Jef's 8 + 8 layout

Jef's controlled profile, as read from his repo:

| Knob | Value |
|---|---|
| Online CPUs | 0–15. Cores 16–191 are offlined at runtime (`/sys/devices/system/cpu/cpuN/online=0`) |
| Housekeeping | 0–7: `init.scope`, `system.slice`, `user.slice` (and `kubepods.slice` if present) get `systemctl set-property --runtime AllowedCPUs=0-7` |
| Measured | 8–15, all on NUMA node 0. Jef's parent cgroup `/sys/fs/cgroup/agentic-benchmark` has cpuset 8–15 |
| Boot | `irqaffinity=0-7 workqueue.unbound_cpus=0-7 nmi_watchdog=0 transparent_hugepage=never`; **no** `isolcpus`/`nohz_full`/`rcu_nocbs` |
| Frequency | no cpufreq driver; platform-fixed **3.3 GHz**, witnessed per run as `cpu_cycles / cnt_cycles × 1 GHz` (cnt = 1 GHz generic timer) |
| PMU | `armv8_pmuv3_0`: 1 cycle counter + 6 programmable; `PMMIR.SLOTS = 10`; no SPE; perf 6.17 has no V3 event table (sysfs aliases + reviewed raw codes) |
| perf access | `perf_event_paranoid` is 4 on AWS; Jef's host policy writes −1 for benchmark boots. Use `sudo perf` and do not change the sysctl permanently |

Implement our own `arm/kit/arm_shield.sh` with `apply | verify | restore`. **Do not call or
edit Jef's scripts or units**: they belong to his private repo.

1. **Snapshot first:** online state of every CPU, `AllowedCPUs` and **effective** cpusets of
   the slices, IRQ affinities, THP. Restore from the snapshot, never to "all CPUs". This was
   an x86 bug: an empty systemd `AllowedCPUs` was restored as "all CPUs" and widened other
   users' slices (`spec26/infra_kit/docs/spec26_profile_validation.md` §1.5).
2. If Jef's controlled layout is **already live** (cores 16–191 offline, slices on 0–7),
   adopt it, note that in metadata, and change nothing that it covers.
3. Our fence: a transient scope `systemd-run --scope --slice=jerry-measured.slice
   -p AllowedCPUs=8` (for SPEC: **one core, CPU 8**), or a cgroup under a slice of our own
   pinned to 8–15. Never put our work inside Jef's `agentic-benchmark` cgroup tree.
4. **ISO-PROOF** (applied ≠ verified):
   * slices' effective cpusets = 0–7;
   * CPUs 16–191 offline (or, if Jerry decides to leave them online, show that they are idle);
   * measured cores 8–15 < 2 % busy over 1.5 s, with settle-and-retry;
   * no foreign `perf`;
   * a 2 s quiet window machine-wide.

   Abort if it fails. Bank the ambient busy % in metadata.
5. A **witness** during capture: `/proc/stat` per CPU and the top foreign tasks every 2 s. An
   episode overlapped by foreign work is set aside and re-run (up to 3 tries), as in
   `spec26/infra_kit/scripts/llc_dram_crosscheck.sh`.
6. **Restore** on any exit (trap), then verify that it came back.

SPEC is single-copy, single-thread. On x86 the fence allowed 8 cores and the benchmark was
free to migrate. On ARM, per Jerry, it is **pinned to one core**. Note this difference in the
report; it removes migrations from the ARM data.

## 5. The profiler — Jef's families and formulas, reimplemented

Write `arm/kit/arm_profile.py` (our code). Per pass:

```bash
sudo perf stat -j -I 100 -C 8 -o <pass>.json \
     -e '{armv8_pmuv3_0/event=…/,…}' -G <fence cgroup, repeated once per event> \
     -e task-clock,context-switches,cpu-migrations,page-faults -G <fence ×4>   # "environment", every pass
```

* The workload must already be **inside** the fence cgroup before it execs. Start it as
  `sh -c 'echo $$ > <cg>/cgroup.procs && exec taskset -c 8 <cmd>'`, or use `systemd-run
  --scope`. Jef hit a defect where a probe moved into the cgroup after it forked, leaving the
  work outside.
* **One family per run**: the benchmark runs once per family. SPEC is deterministic, so
  `inst_retired` totals must agree across passes within 0.5 %. That is a free determinism
  gate; enforce it.

Families (events verbatim from Jef's plan; raw codes as `armv8_pmuv3_0/event=0x…/`):

| Tier | Family | Events (cycles counter + ≤ 6) |
|---|---|---|
| 1 | anchor | cpu_cycles, inst_retired, stall_slot_frontend, stall_slot_backend, op_retired, op_spec, br_mis_pred |
| 1 | frequency | cpu_cycles, cnt_cycles, inst_retired, bus_cycles |
| 1 | branch | inst_retired, br_retired, br_mis_pred_retired, br_mis_pred, br_immed_retired, br_return_retired |
| 1 | branch-types | inst_retired, br_immed_mis_pred_retired `0x8111`, br_ind_mis_pred_retired `0x8113`, br_return_mis_pred_retired `0x8115`, br_indirect_spec `0x7a`, br_return_spec `0x79` |
| 1 | cache-l1 | inst_retired, l1d_cache, l1d_cache_refill, l1d_cache_lmiss_rd, l1i_cache, l1i_cache_refill |
| 1 | cache-l2-ll | inst_retired, l2d_cache, l2d_cache_refill, l3d_cache_refill, ll_cache_rd, ll_cache_miss_rd |
| 1 | bandwidth | cpu_cycles, inst_retired, ll_cache_miss_rd, bus_access, mem_access, remote_access |
| 1 | tlb-data | inst_retired, l1d_tlb, l1d_tlb_refill, l2d_tlb, l2d_tlb_refill, dtlb_walk |
| 1 | tlb-code | inst_retired, l1i_tlb, l1i_tlb_refill, itlb_walk, l1i_cache_lmiss, l1i_cache_refill |
| 2 | frontend-stalls | cpu_cycles, stall, stall_frontend, stall_slot_frontend, l1i_cache_lmiss, br_mis_pred |
| 2 | frontend-supply-mem | cpu_cycles, stall_frontend, stall_frontend_membound `0x8158`, stall_frontend_l1i `0x8159`, stall_frontend_mem `0x815b`, stall_frontend_tlb `0x815c` |
| 2 | frontend-supply-core | cpu_cycles, stall_frontend, stall_frontend_cpubound `0x8160`, stall_frontend_flow `0x8161`, stall_frontend_flush `0x8162` |
| 2 | backend | cpu_cycles, stall_backend, stall_backend_mem, stall_slot_backend, l1d_cache_lmiss_rd, l2d_cache_lmiss_rd |
| 2 | execution | inst_spec, inst_retired, op_spec, op_retired, exc_taken, br_mis_pred |

**Tier 1 covers Jerry's list. Run it for all 26 first, then tier 2.** Jef qualified the
raw-code families on core 8 only and never collected them in his campaign. Qualify them here
before use (below).

Formulas (Jef's registry; `instructions` = inst_retired, `cycles` = cpu_cycles, slots = 10):

```
IPC                      = instructions / cycles
Frontend-bound (%)       = 100 * (stall_slot_frontend / (10*cycles) - 4*br_mis_pred/cycles)
Backend-bound (%)        = 100 * stall_slot_backend / (10*cycles)
Retiring (%)             = 100 * (op_retired/op_spec) * (1 - (stall_slot_frontend+stall_slot_backend)/(10*cycles))
Bad-speculation (%)      = 100 * ((1 - op_retired/op_spec) * (1 - (stall_slot_frontend+stall_slot_backend)/(10*cycles)) + 4*br_mis_pred/cycles)
Branch MPKI              = 1000 * br_mis_pred_retired / instructions
Branch-direction MPKI    = 1000 * br_immed_mis_pred_retired / instructions
Target-mispredict MPKI   = 1000 * (br_ind_mis_pred_retired + br_return_mis_pred_retired) / instructions   # Jef's partial stand-in for x86 "BTB MPKI (BAClears)"
L1I MPKI = 1000*l1i_cache_refill/inst   L1D MPKI = 1000*l1d_cache_refill/inst   L2 MPKI = 1000*l2d_cache_refill/inst
LLC MPKI                 = 1000 * ll_cache_miss_rd / instructions
DRAM read (GB/s)         = 64 * ll_cache_miss_rd / window_seconds / 1e9        # core-side proxy; no CMN/uncore PMU used
L1D-TLB MPKI = 1000*l1d_tlb_refill/inst   L2-TLB MPKI = 1000*l2d_tlb_refill/inst
DTLB-walk MPKI = 1000*dtlb_walk/inst      ITLB-walk MPKI = 1000*itlb_walk/inst   L1I-TLB MPKI = 1000*l1i_tlb_refill/inst
Frontend-stall (% cycles) = 100 * stall_frontend / cycles
frontend_{mem,l1i,l2i,tlb,core,flow,flush}_bound = 100 * stall_frontend_{membound,l1i,mem,tlb,cpubound,flow,flush} / stall_frontend
Context switches (/CPU-s) = context-switches / (task-clock seconds); windows with task-clock < 2 ms dropped
```

* **No ARM counterpart:** x86 DSB/uop-cache coverage and MPKI. Jef found no macro-op-cache
  event on Neoverse-V3. Check `perf list` and `/sys/bus/event_source/devices/armv8_pmuv3_0/events/`
  on the box before concluding. If none exists, report "no Arm counterpart", using Jef's
  parity labels (exact / analogue / partial / none).
* Arm cache and TLB events count speculative accesses, stores included. "DRAM read" is an
  LL-miss proxy, and what "last level" is on Graviton is unverified. Both caveats go in the
  report.

**Qualification gate** (per boot, before production): for each family, count 1.5 s on CPU 8
with a pinned busy probe already inside the fence. Every row must be `pcnt-running ≥ 99.999`,
with no `<not counted>` and perf exit 0. **Gate on `pcnt-running` directly.** Jef's
per-window check reads fields (`enabled`/`running`) that perf 6.17 `-j` output does not have,
so it can never fire. Bank the qualification JSON.

**Per-pass validity:** every window has full `pcnt-running`; the frequency pass is within
±100 MHz of 3.3 GHz; the benchmark exit status is 0; the SPEC output check passed (or is
"unavailable" for vpr/gem5/marian, as on x86); `inst_retired` matches across passes within
0.5 %; the witness is clean. Note: perf 6.17 prints `task-clock` in nanoseconds with an empty
unit.

## 6. Run order and cost

1. Smoke with `736.ocio_r` (shortest on x86, 10 s) on all tier-1 families. Check that every
   gate evaluates, the CSVs come out, and isolation restores.
2. Tier 1 × 26: about 47 min per full sweep on x86 (Graviton5 will differ), 9 sweeps, so
   **~7 h**. Resumable DONE markers per ⟨benchmark, family⟩; run under `tmux`.
3. Tier 2 × 26 (5 more sweeps, ~4 h) only after tier 1 is processed and pushed.
4. When work is finished or blocked on a human, say so clearly: the box bills hourly.

## 7. Data layout (mimics Jef's ARM branch) and outputs

```
arm/                         (in ~/jerry-spec, branch spec-arm)
  README.md                  what is here, how produced, caveats
  config/host.toml           CPUs online/house/measured, frequency, kernel, perf, boot cmdline (as observed)
  config/profiling_plan.toml families → events (aliases + raw codes), formulas, parity labels
  kit/                       arm_shield.sh, arm_profile.py, qualify.py, export.py  (our code)
  data/raw/                  GIT-IGNORED: perf -j -I JSON per ⟨benchmark, family⟩, qualification receipts, witness
  data/interim/              GIT-IGNORED: run logs, SPEC output-check logs
  data/processed/spec26/     COMMITTED: spec26_arm_windows.csv.gz, spec26_arm_votes.csv, episodes.csv (metadata + gates)
  reports/figures/data/      COMMITTED: figure-ready CSVs in Jef's schemas
```

* **Figure schemas (Jef's):**
  * per-window SPEC rows: `benchmark,suite,win,metric,value`, suite `SPEC-int`/`SPEC-fp`, as
    in his `reports/figures/data/spec26_compact_windows.csv`;
  * per-benchmark vote = mean of its windows. Also report the whole-run ratio of sums: they
    differ for phased programs, and the gap is a finding.
* **Metric strings exactly as his figures spell them**: `IPC`, `Branch MPKI`,
  `Branch-direction MPKI`, `L1I MPKI`, `L1D-load MPKI`, `L2-load MPKI`, `LLC MPKI`,
  `DRAM read (GB/s)`, `Context switches (/CPU-s)`, `Frontend-bound (%)`,
  `Frontend-stall (% cycles)`, … Keep a `metric_parity.csv` (metric, x86 name, label).
* Add `arm/data/raw/` and `arm/data/interim/` to `.gitignore`. Archive raw data as
  `arm_spec26_raw_<date>.tar.zst` and tell Jerry its path (it must leave the box before the
  instance is terminated). Commit it only if it is < 100 MB.
* Comparison to x86: `spec26/infra_kit/x86_results/<bench>/metrics.json` has the x86 values.
  Read `spec26/infra_kit/docs/spec26_profile_validation.md` first: x86 `LLC_MPKI` counts
  retired demand loads only and x86 `DRAM_read_GBs` is not DRAM traffic, so neither is the
  same quantity as the ARM proxy.

## 8. Document and push

1. Session log from the first action (`/handoff`). Record every deviation from this doc,
   instance start/stop times if known, and the architecture-failure list.
2. Study report (`/study-report`) in the fixed format: key summary, decisions, hazards with
   numbers, reproduction recipe, scripts table, insights.
3. Commit on `spec-arm`:
   * no Claude attribution lines;
   * nothing ≥ 100 MB;
   * no SPEC files, and nothing copied from Jef's repo.

   Push (`/report-check-commit` does the checks). Then cherry-pick the `arm/kit/` commit onto
   `dcperf-arm` for the Server run.
4. Restore isolation, verify, and tell Jerry the box can be stopped.
