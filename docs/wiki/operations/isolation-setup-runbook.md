# Isolation setup runbook — SMT, DVFS, core isolation

| Field | Value |
|---|---|
| Owner | LLM maintained, human reviewed |
| Status | Implemented |
| Last updated | 2026-08-05 |
| Sources | [harden_isolation.sh](../../../scripts/harden_isolation.sh), [run_glm_campaign.sh](../../../local_agents/kit/campaign/run_glm_campaign.sh), [campaign.conf](../../../local_agents/kit/campaign/campaign.conf), `~/spec26-infra/infra/scripts/run_spec_campaign.sh` (SPEC CPU 2026 sibling kit, outside this repo), live `Intel Xeon w5-3425` state read 2026-08-05 |

## Purpose

Step-by-step procedure to bring a measurement host into the isolation state the InferSuite and
SPEC CPU 2026 campaigns run under: **SMT off on the measured cores, DVFS pinned, cores fenced away
from OS work.** Written to be handed to a colleague on a machine that has none of it yet.

The companion page [Isolation & hardening](isolation-hardening.md) explains *why* the design is
what it is. This page is the *how*. Read that one first if you are deciding policy; read this one
if you are typing commands.

*Limitation.* Every value in the worked example was read back from the live w5-3425 on 2026-08-05,
and every command below is the one that produces it. The full sequence has **not** been replayed
from a clean retail boot in one pass — steps 1–3 were established on this host by an external
systemd stack (see [Who applies what on the current host](#who-applies-what-on-the-current-host)).
Treat step timings and reboot counts as guidance, not as a validated transcript.

## Three layers, in order

| Layer | Survives reboot? | Applied by | What it buys |
|---|---|---|---|
| 1. Boot / GRUB | Yes (it *is* the boot) | `harden_isolation.sh` + `/etc/default/grub` | IRQ + workqueue steering, THP off, NMI watchdog off |
| 2. SMT + DVFS | No — re-apply each boot | manual, or a boot-time systemd unit | One thread per measured core; fixed frequency |
| 3. Runtime shield | No — per campaign | the kit, automatically | cpuset fence, IRQ affinity, k3s, ISO-PROOF |

Do them in this order. Layer 3 is applied and restored by the campaign scripts themselves and you
normally never type it by hand — it is documented here so you can verify it and so you can debug a
failing ISO-PROOF.

---

## Step 0 — Decide the partition

Everything downstream is derived from two CPU sets. Write them down before touching anything.

| Set | Meaning |
|---|---|
| `CPUS_MEASURED` | Where the workload runs. Nothing else may touch these. |
| `CPUS_HOUSE` | Housekeeping: the OS, IRQs, the profiler, the proxy, your shell. |

Rules:

1. They must not overlap, and every CPU named must be online.
2. The measured set must be **uniform**: all SMT-free, or all SMT-live. A mixed set blends two
   microarchitectural conditions into one profile and the SPEC kit refuses to start
   (`FATAL: measured set has SMT-live cores ... alongside SMT-free ones`).
3. Keep at least 2 physical cores for house. IRQs, `perf`, and the pollers all live there.

Read your topology first — **sibling pairing is not always `N`/`N+1`**:

```bash
lscpu -e=CPU,CORE,SOCKET,ONLINE
cat /sys/devices/system/cpu/cpu0/topology/thread_siblings_list
```

Worked example, Xeon w5-3425 (12 P-cores, siblings are `N` / `N+12`):

```
CPUS_MEASURED = 4-11        # 8 physical cores, siblings 16-23 offlined => SMT-free
CPUS_HOUSE    = 0-3,12-15   # 4 physical cores + their live siblings
```

Derive the IRQ affinity mask from the house set — never hand-write the hex:

```bash
python3 -c 'm=0
for p in "0-3,12-15".split(","):
    a,_,b=p.partition("-")
    m |= sum(1<<c for c in range(int(a), int(b or a)+1))
print(f"{m:x}")'
# -> f00f
```

---

## Step 1 — Boot-time isolation (GRUB)

### 1a. The cmdline parameters

Target cmdline for the worked example:

```
nmi_watchdog=0 transparent_hugepage=never irqaffinity=0-3,12-15 workqueue.unbound_cpus=0-3,12-15
```

| Parameter | Effect |
|---|---|
| `irqaffinity=<house>` | Kernel steers device IRQs to house cores from the first boot second |
| `workqueue.unbound_cpus=<house>` | Unbound kernel workqueues run on house cores |
| `nmi_watchdog=0` | Removes the per-CPU NMI perf event that would otherwise hold a counter |
| `transparent_hugepage=never` | Removes khugepaged compaction as a source of run-to-run variance |

Edit `/etc/default/grub`, append to `GRUB_CMDLINE_LINUX_DEFAULT`, then:

```bash
sudo cp /etc/default/grub /etc/default/grub.bak
sudo update-grub
```

**Do not reboot without asking the machine's owner.** On a shared host, confirm first.

### 1b. Optional: tickless measured cores

`sudo scripts/harden_isolation.sh --on-soft` adds `nohz_full=<measured>` and `rcu_nocbs=<measured>`
and runs `update-grub` for you. It backs up `/etc/default/grub` to `.pre-isoharden.bak` on first
use and is reversible with `--off`.

> *Decision.* **Never use `isolcpus`.** Measured 2026-07-14: it removes the cores from the
> scheduler's load-balancing domains, and a 20-way pool confined to the measured cpuset stacked
> entirely onto **one** core (cpu16 at 100 %, 19 idle). `--on` still offers it; use `--on-soft`.
> See [Isolation & hardening](isolation-hardening.md).

*Observation.* The current w5-3425 boot has **no** `nohz_full`/`rcu_nocbs` — the measured cores
still take their local timer tick. Both kits' preflight warns about this rather than failing; it is
a stated condition of the banked data, not a defect.

### 1c. Verify after reboot

```bash
cat /proc/cmdline
cat /sys/devices/virtual/workqueue/cpumask     # -> 00f00f
cat /proc/sys/kernel/nmi_watchdog              # -> 0
cat /sys/kernel/mm/transparent_hugepage/enabled # -> always madvise [never]
cat /sys/devices/system/cpu/nohz_full          # -> (null) unless you did 1b
```

---

## Step 2 — Turn SMT off on the measured cores

Two ways. They are **not** equivalent, and the difference bites.

### Option A — offline the siblings (what this host does)

```bash
# Siblings of measured cores 4-11 are 16-23 on this topology. CHECK YOUR OWN.
for c in $(seq 16 23); do echo 0 | sudo tee /sys/devices/system/cpu/cpu$c/online >/dev/null; done
```

- Logical CPU numbering is **preserved** — `4-11` still means the same physical cores.
- Only the cores you chose become SMT-free. Cores 0–3 keep their live siblings 12–15, which is
  what you want for house cores.
- Not persistent: **re-apply on every boot.**

> **Gotcha — `lscpu` and `smt/control` will lie to you.** After this,
> `/sys/devices/system/cpu/smt/control` still reads `on`, `smt/active` still reads `1`, and `lscpu`
> still reports `Thread(s) per core: 2`, because *some* core still has two live threads. The only
> honest check is per-core, over the measured set:
>
> ```bash
> cat /sys/devices/system/cpu/offline    # -> 16-23
> for c in $(seq 4 11); do
>   echo "cpu$c siblings: $(cat /sys/devices/system/cpu/cpu$c/topology/thread_siblings_list)"
> done                                    # each must list exactly one ONLINE cpu
> ```
>
> Both kits do exactly this and record two separate fields in `metadata.json`: `smt` (the verdict
> over the measured cores — what the profile is actually about) and `smt_host` (what `lscpu` says).

### Option B — disable SMT globally

```bash
echo off | sudo tee /sys/devices/system/cpu/smt/control     # or disable it in BIOS
```

- All siblings go offline: 24 logical CPUs → 12.
- **Renumbering.** In BIOS the logical CPUs are renumbered `0-23` → `0-11`, so a partition written
  as `2-11,14-23` silently becomes wrong. This is why `campaign.conf` carries
  `PARTITION_PROFILE=auto` with one partition per SMT state, and why the kit refuses to start when
  the configured set names offline CPUs.
- Via `smt/control` the numbering is preserved (the high CPUs just go offline); via BIOS it is not.

*Decision, current campaigns.* The w5-3425 is shared, so it runs Option A with a half-offline
split: measured cores 4–11 SMT-free for the SPEC campaign, house cores 0–3 keeping siblings 12–15.
`campaign.conf` pins `PARTITION_PROFILE=pinned` rather than letting auto-detect pick the SMT-ON
profile off `lscpu`'s misleading summary.

---

## Step 3 — Pin DVFS

Three knobs. Governor alone is **not** enough on an HWP part — `performance` still lets the
frequency float up to turbo and back.

```bash
# 3a. governor
for c in $(seq 4 11); do
  echo performance | sudo tee /sys/devices/system/cpu/cpu$c/cpufreq/scaling_governor >/dev/null
done

# 3b. clamp min == max to the base frequency (3.2 GHz here; read your own base clock)
for c in $(seq 4 11); do
  echo 3200000 | sudo tee /sys/devices/system/cpu/cpu$c/cpufreq/scaling_max_freq >/dev/null
  echo 3200000 | sudo tee /sys/devices/system/cpu/cpu$c/cpufreq/scaling_min_freq >/dev/null
done

# 3c. turbo off, machine-wide
echo 1 | sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo >/dev/null
```

Verify — `scaling_cur_freq` must equal both bounds under load and at idle:

```bash
cat /sys/devices/system/cpu/cpu4/cpufreq/{scaling_governor,scaling_min_freq,scaling_max_freq,scaling_cur_freq}
# performance / 3200000 / 3200000 / 3200000
cat /sys/devices/system/cpu/intel_pstate/no_turbo   # -> 1
```

Notes:

- `/sys/devices/system/cpu/cpuN/cpufreq/` is a symlink into `/sys/devices/system/cpu/cpufreq/policyN/`.
  Writing either path is the same write.
- **Pin only the measured cores.** House cores are deliberately left floating (`scaling_min_freq`
  800000 on this host) so housekeeping does not burn power at 3.2 GHz.
- **Offline CPUs keep a `cpufreq/` directory that rejects writes with `EBUSY`.** Always loop over
  `/sys/devices/system/cpu/online`, never a `cpu*` glob, or real failures drown in noise.
- *Limitation.* C-states are **not** disabled on this host (`intel_idle` with POLL/C1/C1E/C6 all
  enabled). Deep-C-state exit latency remains a variance source. Not currently controlled.

---

## Step 4 — Runtime shield (the kit does this)

You do not type this. `apply_isolation()` in the campaign script applies it at the start of every
run and `restore_isolation()` puts everything back from an `EXIT` trap that also catches Ctrl-C.
It is listed so you can verify it and debug it.

```bash
# cpuset fence — measured.slice is TOP-LEVEL; cpusets are hierarchical, so the fence
# cannot live under system.slice once that is pinned to the house cores.
sudo systemctl set-property --runtime measured.slice AllowedCPUs=4-11
sudo systemctl set-property --runtime system.slice   AllowedCPUs=0-3,12-15
sudo systemctl set-property --runtime user.slice     AllowedCPUs=0-3,12-15

# every IRQ onto the house mask
echo f00f | sudo tee /proc/irq/default_smp_affinity >/dev/null
for f in /proc/irq/*/smp_affinity; do echo f00f | sudo tee "$f" >/dev/null 2>&1; done

# THP + NMI watchdog, in case the boot layer is absent
echo never | sudo tee /sys/kernel/mm/transparent_hugepage/{enabled,defrag} >/dev/null
echo 0     | sudo tee /proc/sys/kernel/nmi_watchdog >/dev/null
```

> **k3s pods escape slice shields.** Stopping `k3s` leaves the pods alive under `kubepods.slice`,
> whose cpuset is the full machine — outside the fence. The kit stops k3s, runs
> `/usr/local/bin/k3s-killall.sh`, *and* pins `kubepods.slice`, then restarts k3s on teardown.

The workload is placed on the measured cores by a transient scope, and every instrument
(`perf record`, `perf stat`, the 10 Hz pollers) is `taskset`-ed onto the house cores so the
profiler's own overhead never lands in the measured partition:

```bash
sudo systemd-run --collect --scope --slice=measured.slice --unit=<unit> \
     -p AllowedCPUs=4-11 -p CPUAccounting=yes -p MemoryAccounting=yes -- <workload>
```

One adjacent prerequisite, or preflight fails: `sudo sysctl kernel.perf_event_paranoid=-1`.

---

## Step 5 — Prove it (ISO-PROOF)

*Applied is not verified.* Run the kit's own gate rather than eyeballing:

```bash
./run_glm_campaign.sh preflight        # InferSuite kit
./run_spec_campaign.sh isolation-test  # SPEC kit: apply, verify, revert, re-verify
```

What it checks, and what you should check by hand if you are doing this manually:

1. **Effective** cpusets, not requested ones —
   `cat /sys/fs/cgroup/{system,user,measured}.slice/cpuset.cpus.effective`.
2. Governor `performance` and `no_turbo=1` on a measured CPU — recorded as `firmware-fixed` if the
   interface is absent, never silently passed.
3. **Actual silence**: >2.0 % non-idle on *any* measured core over a 1.5 s window fails. Retried up
   to 8 times with a 4 s settle. The measured ambient bound is banked into `metadata.json`, not
   just a pass/fail verdict.
4. No other user's `perf` holding **hardware** counters. On a shared box, coordinate — never
   `pkill` someone else's capture.

---

## Step 6 — Teardown

Layer 3 restores itself. Layer 2 you undo by hand (or by rebooting, since it never persisted):

```bash
for c in $(seq 16 23); do echo 1 | sudo tee /sys/devices/system/cpu/cpu$c/online >/dev/null; done
for c in $(seq 4 11); do
  echo 800000 | sudo tee /sys/devices/system/cpu/cpu$c/cpufreq/scaling_min_freq >/dev/null
  echo powersave | sudo tee /sys/devices/system/cpu/cpu$c/cpufreq/scaling_governor >/dev/null
done
echo 0 | sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo >/dev/null
```

Layer 1: `sudo scripts/harden_isolation.sh --off` (or restore `/etc/default/grub.bak`),
`sudo update-grub`, reboot.

---

## Every file this touches

Copy this table when someone asks "what did you change on my machine?".

### Layer 1 — persistent

| File | Value |
|---|---|
| `/etc/default/grub` (`GRUB_CMDLINE_LINUX_DEFAULT`) | `nmi_watchdog=0 transparent_hugepage=never irqaffinity=<house> workqueue.unbound_cpus=<house>` (+ `nohz_full`/`rcu_nocbs` if hardened) |

### Layer 2 — per boot

| File | Value |
|---|---|
| `/sys/devices/system/cpu/cpu{16..23}/online` | `0` — SMT off on measured cores |
| `/sys/devices/system/cpu/cpu{4..11}/cpufreq/scaling_governor` | `performance` |
| `/sys/devices/system/cpu/cpu{4..11}/cpufreq/scaling_max_freq` | `3200000` |
| `/sys/devices/system/cpu/cpu{4..11}/cpufreq/scaling_min_freq` | `3200000` |
| `/sys/devices/system/cpu/intel_pstate/no_turbo` | `1` |

### Layer 3 — per campaign, snapshotted and restored

| File | Value |
|---|---|
| `/sys/fs/cgroup/measured.slice/cpuset.cpus` | `4-11` (via `systemctl set-property --runtime`) |
| `/sys/fs/cgroup/{system,user}.slice/cpuset.cpus` | `0-3,12-15` |
| `/sys/fs/cgroup/kubepods.slice/cpuset.cpus` | `0-3,12-15` |
| `/proc/irq/default_smp_affinity` | `f00f` |
| `/proc/irq/*/smp_affinity` (every IRQ) | `f00f` |
| `/sys/kernel/mm/transparent_hugepage/enabled` | `never` |
| `/sys/kernel/mm/transparent_hugepage/defrag` | `never` |
| `/proc/sys/kernel/nmi_watchdog` | `0` |
| `/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor` | `performance` (all online CPUs) |
| `/sys/devices/system/cpu/intel_pstate/no_turbo` | `1` |

Every layer-3 value is snapshotted into the kit's `.state/` directory **before** any mutation —
`gov_cpuN` per CPU, `no_turbo`, `thp`, `thp_defrag`, `nmi`, `irq_default`, `irq_N` per IRQ,
`cpuset_*` per slice, `k3s` — and the `iso_applied` marker is written first, so a crash mid-apply
still restores cleanly on the next run.

> *Fact, learned the hard way 2026-08-05.* Two restore bugs to avoid if you write your own kit.
> **(1)** Snapshot the governor **per CPU**. Reading `cpu0` and writing that one value back
> everywhere flattened a per-core policy — cpu0 was `powersave` while the workload cores were
> `performance`, and the single-value restore silently downgraded them. **(2)** Snapshot the slice
> cpusets. Restoring them to "all online CPUs" destroyed an operator's existing `0-3,12-15` split
> and let OS work back onto the measured cores.

---

## Who applies what on the current host

On this w5-3425, layers 1–3 are **not** all yours. Two systemd units from a co-tenant
`agentic-benchmark` stack own layers 1 and 2:

| Unit | Does |
|---|---|
| `agentic-benchmark-runtime-controls.service` | Offlines CPUs 16–23 (`online_cpus = "0-15"`, `idle_siblings = "16-23"`), gated on `agentic_benchmark.mode=controlled` in the cmdline |
| `agentic-benchmark-host-policy.service` | Pins governor + `scaling_{min,max}_freq` = 3200000 on `frequency_cpus = 4-11,16-23`, sets `no_turbo=1` |

Its profile config is world-readable at `/opt/agentic-benchmark/current/config/host/active.toml`;
the runtime-controls script itself lives under another user's home and is not readable, so the
offlining mechanism above is inferred from that config plus the observed live state — the *state*
is confirmed, the *script* was not read.

Practical consequence for a colleague reproducing this: on a machine without that stack, run steps
2 and 3 by hand (or install them as your own boot unit). Do not assume a reboot restores them.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `FATAL: partition names CPUs that are not online` | Config written for SMT-ON, siblings now offline | Set `CPUS_MEASURED`/`CPUS_HOUSE` explicitly, or `PARTITION_PROFILE=auto` |
| `FATAL: measured set has SMT-live cores alongside SMT-free ones` | Measured set spans both conditions | Narrow to one or the other — never profile the blend |
| Write to `scaling_governor` fails, `EBUSY` | Aimed at an offline CPU | Loop over `/sys/devices/system/cpu/online` |
| `ISO-PROOF FAIL: ... cpuset` | Requested ≠ effective — a parent slice is narrower | `measured.slice` must be top-level, not nested |
| `ISO-PROOF FAIL: measured cores not quiet` after 8 tries | Something escaped the fence — usually k3s pods | Check `kubepods.slice` cpuset; `k3s-killall.sh` |
| `lscpu` says SMT on but you offlined siblings | Expected — some core still has 2 live threads | Check `thread_siblings_list` per measured core |
| Frequency drifts under load | Governor set, `min`/`max` not clamped | Step 3b — HWP floats under `performance` alone |
| `perf_event_paranoid` preflight failure | Default is 2 | `sudo sysctl kernel.perf_event_paranoid=-1` |

---

## Checklist

```
[ ] 0. Partition chosen; sets disjoint, measured set uniform, >=2 house cores
[ ] 0. IRQ mask derived from house set (not hand-written)
[ ] 1. GRUB cmdline set; owner consented to reboot; verified in /proc/cmdline
[ ] 2. Siblings of measured cores offline; verified per-core, NOT via lscpu
[ ] 3. Governor performance + min == max + no_turbo=1 on measured cores only
[ ] 3. scaling_cur_freq == both bounds, at idle and under load
[ ] 4. perf_event_paranoid = -1
[ ] 5. ISO-PROOF passes: effective cpusets, knobs, measured silence, no foreign perf
[ ] 5. metadata.json records smt, smt_host, governor, no_turbo, iso_proof ambient
```

## Related pages

- [Isolation & hardening](isolation-hardening.md) — the design rationale and the ISO-PROOF concept.
- [Agent measurement design](../architecture/measurement-design.md) — the housekeeping/measured split.
- [Perf & TMA conventions](../profiling/perf-tma-conventions.md) — what runs inside the fence.
