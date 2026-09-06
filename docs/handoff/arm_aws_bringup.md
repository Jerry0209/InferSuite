# ARM / AWS Graviton bring-up handoff

**Owner:** Tianrui (Jerry) · **Written:** 2026-09-06 · **Status:** pre-bring-up (nothing run on ARM yet)

Mentor directive (Rahul, 2026-09): repeat the ML_iso36 profiling on AWS ARM boxes to get
ARM-processor insights. **Core isolation must happen the same exact way as on the x86
machine.** Bring up one task end-to-end on the cheap c7g box first, then move to the
c9g.metal-48xl. This document is the session-starter for that work: the exact x86 ground
truth to replicate (§2, verified on P7 on 2026-09-06), the ARM translation of every knob
(§3), the box logistics (§1), the bring-up contract (§4), and the mentor's two open
questions with proposed policies (§5). Unknowns are marked **[VERIFY-ON-BOX]** — do not
guess them; check and fill them in.

---

## 1. The boxes and how to reach them

| | c7g box (bring-up) | c9g box (the real one) |
|---|---|---|
| Type | c7g.\<size\> **[VERIFY-ON-BOX: `lscpu`, instance metadata]** | `c9g.metal-48xl` |
| µarch | Graviton3 (Neoverse V1) — c7g family | Graviton generation **[VERIFY-ON-BOX: `lscpu`, MIDR in `/proc/cpuinfo`]** |
| OS | Ubuntu 24.04 | Ubuntu 24.04 |
| Cost | ~$2.1/hour | **~$8.5/hour — STOP WHEN IDLE** |
| User | `ubuntu` | `ubuntu` |
| DNS (2026-09-06) | `ec2-3-142-80-65.us-east-2.compute.amazonaws.com` | `ec2-3-144-144-236.us-east-2.compute.amazonaws.com` |

`~/.ssh/config` (same PEM for both boxes; `chmod 400` it first):

```
Host agenticbox
  Hostname ec2-3-144-144-236.us-east-2.compute.amazonaws.com
  User ubuntu
  IdentityFile ~/.ssh/aws-agentic-box.pem

Host agenticbox-c7g
  Hostname ec2-3-142-80-65.us-east-2.compute.amazonaws.com
  User ubuntu
  IdentityFile ~/.ssh/aws-agentic-box.pem
```

Operational rules (from the mentor's posts):

- **Stop instance from the AWS console** when not in use — it is not a poweroff from
  inside the box. The EBS root volume persists across stop/start, so installed software
  and banked data survive.
- **The public DNS changes on every stop/start** (it survives a plain `sudo reboot`, which
  we WILL need for GRUB changes). After each console start, fetch the new DNS and update
  the `Hostname` fields above. A stale hostname is the expected first failure of every
  session.
- `sudo reboot` from inside the box is fine and is how kernel-cmdline changes take
  effect; only stop/start goes through the console. **[VERIFY-ON-BOX]** that a metal
  instance reboot returns cleanly (metal boots are slow, ~5–10 min; be patient before
  declaring it dead).
- Cost discipline: log instance start/stop times in the session log; on c9g batch the
  work so the box never idles hot.
- The GLM API key: copy `~/.glm_key` to the box manually (scp), `chmod 600`, never echo
  it, never bake it into an AMI snapshot note or this repo.

## 2. x86 ground truth — what "the same exact way" means (verified on P7, 2026-09-06)

P7 = Intel Xeon w5-3425 (12 P-cores, SMT2 → 24 logical; sibling pairs are N/N+12). All
ML_iso36 data was captured in a single boot (up since 2026-08-05) with the configuration
below. This — not the older SWE_clean nohz_full layout — is the reference configuration
to replicate.

**2.1 Boot level** (custom GRUB menuentry `Agentic Benchmark Controlled` in
`/etc/grub.d/40_custom`; live `/proc/cmdline` verified):

```
nmi_watchdog=0 transparent_hugepage=never irqaffinity=0-3,12-15 workqueue.unbound_cpus=0-3,12-15
```

(plus an inert marker `agentic_benchmark.mode=controlled`). Notes:

- `irqaffinity=` + `workqueue.unbound_cpus=` steer IRQs and unbound kernel workqueues to
  the housekeeping CPUs **at boot**, before the runtime shield exists.
- **`nohz_full`/`rcu_nocbs` are NOT in the iso36 reference boot.** They belong to
  `scripts/harden_isolation.sh --on-soft` (used for the earlier SWE_clean campaign).
  Decision for ARM: replicate the iso36 boot first (it is what the comparison data used);
  add `--on-soft` later only as a both-sides change.
- **NEVER use `isolcpus`** — measured 2026-07-14 on P7: it removes the cores from the
  scheduler's balancing domains and a 20-way pool stacked on ONE core. This applies
  unchanged on ARM.

**2.2 CPU partition** (from `local_agents/kit/campaign/campaign.conf`, re-partitioned
2026-08-05):

- Measured: `CPUS_MEASURED=4-11` — 8 **physical** cores, with their SMT siblings 16–23
  **offlined at runtime** (`echo 0 | sudo tee /sys/devices/system/cpu/cpu{16..23}/online`)
  for the duration of a campaign; re-onlined afterwards. There is no script for this step
  on P7 — it is manual, and the preflight gate is the enforcement.
- Housekeeping: `CPUS_HOUSE=0-3,12-15` — OS, sshd, dockerd, the litellm proxy, perf
  writers, the 10 Hz pollers, all IRQs. `HOUSE_IRQ_MASK=f00f` (hex mask of 0-3,12-15).
- The preflight topology gate (`run_glm_campaign.sh` ~line 643) verifies before any
  spend: house slices pinned, every measured core online, **no measured core has an
  online SMT sibling**.

**2.3 Runtime shield** (`run_glm_campaign.sh` `iso_apply`, snapshot → apply → verify →
restore; every knob is snapshotted first and restored from the snapshot, never reset to
"all CPUs" — the box is shared):

1. `performance` governor on every CPU; `intel_pstate/no_turbo=1`.
2. THP `never` (both `enabled` and `defrag`); `nmi_watchdog=0` (redundant with boot, kept).
3. `default_smp_affinity` and every `/proc/irq/*/smp_affinity` → `HOUSE_IRQ_MASK`.
4. `measured.slice` AllowedCPUs=`CPUS_MEASURED`; docker `daemon.json` gets
   `cgroup-parent: measured.slice` + docker restart (all task containers land inside the
   measured partition); `system.slice`/`user.slice` AllowedCPUs=`CPUS_HOUSE`.
5. k3s stopped + pods killed + `kubepods.slice` pinned (P7-specific; absent on AWS).
6. Stray `perf` processes killed (they hold the PMU).

**2.4 ISO-PROOF gate** (applied ≠ verified): after the shield, assert (a) effective
cpusets of system/user slices == `CPUS_HOUSE`, (b) governor == performance and
no_turbo == 1, (c) the measured cores are **actually silent** — <2% busy over 1.5 s,
settle-and-retry, ambient bound banked into the log. Abort the campaign on failure.

**2.5 Instruments that ride on this** (what the isolation exists for): 10 Hz cgroup
`cpu.stat` pollers per fence; zero-mux windowed `perf stat` groups (one group per
`WINSEC=0.1` window, shuffled rotation, banked in `windows.tsv`); continuous whole-episode
TMA from Intel `PERF_METRICS`; 99 Hz cgroup-scoped `perf record`; a partition-wide
`/proc/stat` witness.

## 3. ARM translation table — every knob, its fate on Graviton

| x86 knob | ARM/Graviton status | Action |
|---|---|---|
| GRUB cmdline via `/etc/default/grub` | Ubuntu 24.04 arm64 on EC2 boots GRUB-EFI; `GRUB_CMDLINE_LINUX_DEFAULT` + `update-grub` works normally | Add the §2.1 params (with the box's own house-CPU list) to `GRUB_CMDLINE_LINUX_DEFAULT`; `sudo reboot`; verify `/proc/cmdline`. **[VERIFY-ON-BOX]** grub is the active loader (`ls /boot/efi`, `efibootmgr`) |
| `irqaffinity=`, `workqueue.unbound_cpus=`, `transparent_hugepage=never` | Arch-neutral kernel params | Use as-is |
| `nmi_watchdog=0` | x86-ism; arm64 has no perf-NMI watchdog (`/proc/sys/kernel/nmi_watchdog` may not exist) | Keep in cmdline (inert if unsupported); make the shield's sysfs write conditional on the file existing |
| SMT sibling offlining (16–23) | **Graviton has no SMT** — 1 thread/core, `Thread(s) per core: 1` | No-op. The preflight sibling gate must PASS trivially — **[VERIFY-ON-BOX]** it handles an absent/empty `topology/thread_siblings_list` gracefully |
| `performance` governor | Graviton runs at fixed frequency; `cpufreq` sysfs is typically **absent** | Conditionalize the shield write + ISO-PROOF check on the directory existing. Fixed frequency is a measurement *advantage* — note it in the campaign metadata |
| `intel_pstate/no_turbo=1` | Does not exist on ARM (and Graviton has no turbo) | Same conditionalization |
| cgroup v2 slices, `AllowedCPUs`, docker `cgroup-parent` | Identical on Ubuntu 24.04 arm64 | Use as-is — this is the heart of the fencing and it is arch-independent |
| IRQ `smp_affinity` masks | Same interface; mask width differs with core count | Compute `HOUSE_IRQ_MASK` from the chosen house set (do not hardcode `f00f`) |
| k3s handling | Not installed on AWS boxes | Shield already tolerates absent k3s (`SKIP_K3S` path / is-active check) |
| perf binary | P7's "glob linux-tools-6.8*" rule is P7-specific | Plain `linux-tools-$(uname -r)` from Ubuntu; verify `perf stat -e cycles true` |
| PMU access | Full PMU on **.metal**. On virtualized c7g sizes, PMU exposure varies by size | **[VERIFY-ON-BOX]** first thing on c7g: `perf stat -e cycles,instructions true`. If counters are unavailable, do the isolation bring-up on c7g anyway and defer counter bring-up to the metal box |
| Zero-mux counter groups (Intel event names) | Must be re-mapped to Arm Neoverse PMU events (`BR_MIS_PRED_RETIRED`, `STALL_SLOT_FRONTEND/BACKEND`, `L1I_CACHE_REFILL`, `L2D_CACHE_REFILL`, `LL_CACHE_RD/LL_CACHE_MISS_RD`, `MEM_ACCESS`, …) | New group definition file. Neoverse cores have **6 programmable counters + fixed cycle counter** — group sizes must respect that or the zero-mux guarantee (100% enabled time, dryrun gate) breaks. Same shuffled-rotation discipline |
| Continuous TMA via `PERF_METRICS` / `topdown-*` | **Intel-only. Does not exist on ARM.** The single biggest port | Use the Arm Neoverse topdown methodology (STALL_SLOT-based L1 formulas; Arm's `topdown-tool` documents per-µarch formulas). Continuous per-fence counting via `--for-each-cgroup` works the same; the *events* change. Keep it zero-GP-counter-free is impossible — budget counters accordingly |
| 99 Hz cgroup `perf record` | Works on ARM (cycles event) | Symbol attribution: install dbgsym/`libc6-dbg` equivalents as needed |
| 10 Hz `cpu.stat` pollers, `/proc/stat` witness | Pure cgroup/procfs | Use as-is |
| Docker task images (SWE-bench Multilingual) | Images must exist for **arm64** | SWE-bench builds images locally → build natively on the box. **[VERIFY-ON-BOX]** per-task: base images and language toolchains pull/build for arm64; see §5 for the failure policy |
| litellm proxy venv (python 3.13.13 pins) | Ubuntu 24.04 ships python 3.12 | Rebuild from `litellm_venv_freeze.txt` with python3.13 (deadsnakes PPA or miniforge-arm64). If 3.13 is a fight, a 3.12 venv with the same litellm pin is acceptable for bring-up — record the deviation |
| Plotting env (`infersuite-full` conda) | Not needed on the box | **Collect on ARM, plot on P7**: sync banked data back (same layout under a new campaign dir, e.g. `local_agents/ARM_iso*/data`), keep the locked plotting pipeline at home |

**Partition sizing decision (needs a call before c9g):** c9g.metal-48xl has ~192 physical
cores; c7g tops out at 64. Mirroring x86 capacity semantics means **measured = 8 physical
cores, housekeeping = 8**, rest idle-but-pinned-away (slices pinned + `irqaffinity` +
`workqueue.unbound_cpus` to house; unused cores get no work by construction). Offlining
~176 cores is possible but unnecessary if ISO-PROOF shows the measured set silent.
Recommendation: keep 8 measured cores for comparability; a wider-partition variant is a
separate, clearly-labeled experiment. On c7g pick e.g. measured=4-11, house=0-3 +
remainder idle, so the config literally reads like P7's.

## 4. c7g bring-up contract (in order; no model spend until step 7)

1. **SSH + inventory.** `lscpu`, `/proc/cpuinfo` (MIDR → exact core), `uname -r`,
   `free -g`, `df -h`, `nproc`. Record in the session log. Confirm Ubuntu 24.04.
2. **Stack install.** docker (arm64), git, tmux, `linux-tools-$(uname -r)`,
   python3.13-or-3.12 + venv, clone InferSuite (branch `multiling-type-id`), scp
   `~/.glm_key`.
3. **PMU sanity** (before any isolation work): `perf stat -e cycles,instructions,branches true`;
   count usable programmable counters (add events until multiplexing appears);
   `perf stat --for-each-cgroup` against a toy cgroup; `perf record -F 99` on a busy loop.
   Outcome A: all works → c7g does full rehearsal. Outcome B: no PMU → c7g rehearses
   isolation + docker + episode flow only; counters wait for metal.
4. **Boot hardening.** §2.1 params with the ARM house list into
   `GRUB_CMDLINE_LINUX_DEFAULT`, `update-grub`, `sudo reboot`, verify `/proc/cmdline`.
   (This is the step that tests "god knows how reboot gets handled" — do it on the cheap
   box, note timings and any console interaction needed.)
5. **Shield port.** Run `./measure.sh agents-swe preflight` and the shield with ARM env
   overrides; fix the known x86-isms behind existence checks (`intel_pstate`, cpufreq
   governor, nmi sysfs, SMT sibling gate). Keep the edits minimal and upstream them in
   this repo — one kit, arch-aware; no fork.
6. **ISO-PROOF on ARM.** Shield applied → measured cores silent (<2% over 1.5 s bar, same
   settle-and-retry). Bank the ambient bound. This is the mentor's "test the isolation on
   the cheap box" deliverable.
7. **One task end-to-end** (mentor's bring-up bar). Suggested task: `jq-2598` (C, small,
   portable, resolved on P7) with `jekyll-8167` (Ruby, interpreted) as the fallback:
   a. build the task image natively on arm64;
   b. **pre-patch F2P check** (§5 Q2): the task's fail-to-pass tests must FAIL on ARM;
   c. deterministic **replay** of the banked P7 trajectory with pollers (+ counters if
      PMU): compare per-call exit codes and durations against the P7 `cmdlog` — divergence
      localization before any interpretation;
   d. **live episode** (litellm up on house cores, temp 0.6 — never 0.0);
   e. official **eval** on the box (swebench harness builds arm64 images locally);
   f. sync the run dir back to P7, run the derivation on it, confirm the pipeline parses
      ARM data end-to-end.
8. **Write the c7g session log** (`docs/handoff/sessions/`), including every deviation
   from this doc, then **stop the instance from the console**. Only then book c9g time.

## 5. The mentor's two questions — proposed policies

**Q1: what if a task's code base only compiles for x86?**
Detect at step 7a/7c (image build or in-episode build failure: x86 intrinsics, arch-gated
deps, prebuilt x86 binaries). Classify each of the 36: `portable` / `builds-with-deltas`
(works, different codepaths — NEON vs AVX; that *is* the ARM insight, keep it) /
`x86-only` (cannot run). For `x86-only`: do not force-port. Swap within the same
count-view cell using the ML_typeid walk-down order, with the same audit-trail convention
as the jekyll-8167 swap (selection tsv note + stratification doc "Revisions" entry). The
ARM selection is then "the 36, minus documented arch swaps" — the doc must make the two
populations' overlap explicit.

**Q2: what if the bug is not even there in ARM?**
The SWE-bench premise is that F2P tests fail pre-patch. Arch-dependent bugs (endianness,
alignment, x86-specific codepaths) may not reproduce on ARM, which silently changes what
an episode measures. Gate, per task, before profiling: run the F2P tests pre-patch on
ARM — they must fail; run PASS_TO_PASS — they must pass. A task failing this gate is
`not-evaluable-on-ARM`: treat like Q1 (document + swap). Note the study's primary
deliverable is CPU characterization of the *workload*, and the replays (deterministic,
no model) transfer even where live resolution rates drift — but only if the replayed
commands actually do the same work, which is what step 7c's cmdlog comparison checks.

## 6. What does NOT transfer (do not waste time trying)

- Intel `PERF_METRICS`/`topdown-*` events, `intel_pstate`, `no_turbo`, the P7
  perf-binary glob, SMT sibling logic (no SMT on Graviton), the `f00f` IRQ mask literal,
  k3s handling, the NVIDIA runtime in daemon.json.
- P7 figure baselines: SPEC CPU 2026 reference numbers were measured on P7. An
  ARM-vs-x86 agentic comparison is x86-agentic vs ARM-agentic **on their own machines**;
  a SPEC-on-ARM baseline would be a separate capture campaign (flag to mentor — scope
  decision, non-trivial cost).

## 7. Repo anchors

| What | Where |
|---|---|
| Boot hardening script (nohz_full soft mode; isolcpus ban rationale) | `scripts/harden_isolation.sh` |
| Partition + campaign config | `local_agents/kit/campaign/campaign.conf` |
| Shield / ISO-PROOF / preflight gates | `local_agents/kit/campaign/run_glm_campaign.sh` (iso_apply ~line 160; ISO-PROOF ~line 210; topology gate ~line 643) |
| P7 custom boot entry (reference cmdline) | `/etc/grub.d/40_custom` on P7 (not in repo) |
| iso36 protocol + task selection | `local_agents/ML_iso36/`, `local_agents/ML_typeid/selection_36_count.tsv` |
| Replay + derivation pipeline | `local_agents/kit/replay/` |
| Wiki (fencing/isolation decisions) | `docs/wiki/` (start at `index.md`) |
