# perf events reference — GLM SWE/OC campaign kit

What `run_glm_campaign.sh` measures, where each event is defined, and which figure metric it
feeds. Authoritative source: the `GRP[...]` and `TMA_EVENTS` definitions in
`run_glm_campaign.sh` (lines 45–60); derived-metric formulas in `plot_glm_results.py::met()`.

The kit runs perf **three ways**, on three different counter mechanisms:

| Instrument | perf mode | Counter hardware | Duty cycle | Purpose |
|---|---|---|---|---|
| **8 windowed groups** | `perf stat -a --for-each-cgroup` | general-purpose (GP) PMU | time-shared (1 group/window) | exact rates: MPKI, IPC, FP, ports, DRAM BW |
| **TMA census** | `perf stat -I 10000` | PERF_METRICS MSR + fixed slots | continuous (100%) | top-down buckets L1 + L2 |
| **records** | `perf record -F 99 -g` | statistical sampling | 99 Hz | what program/library/function (never rates) |

---

## 1. The 8 windowed counter groups (GP counters)

Defined at `run_glm_campaign.sh:45–54`; rotation order at `:58`
(`GORDER=fpbr cache mlp fe fe_lat core_ports dram_bw priv`, **shuffled each cycle**).
Every group also carries `cycles,instructions` so each has its own co-counted denominator.

| Group | Line | Raw events | Feeds (figure metric) |
|---|---|---|---|
| `fpbr` | 45 | `fp_arith_inst_retired.scalar`, `…​.vector`, `branches`, `branch-misses` | IPC, **Branch MPKI**, vector-FP share |
| `cache` | 46 | `mem_load_retired.{l1_hit,l2_hit,l3_hit,l3_miss}` | **L1D-load MPKI**, **LLC MPKI**, **AMAT** |
| `mlp` | 47 | `l1d_pend_miss.pending`, `…​.pending_cycles` | **MLP** (memory-level parallelism) |
| `fe` | 48 | `idq.{dsb_uops,mite_uops,ms_uops}`, `lsd.uops` | **DSB coverage %**, MITE/MS/LSD shares |
| `fe_lat` | 49 | `icache_data.stalls`, `icache_tag.stalls`, `int_misc.clear_resteer_cycles`, `l2_rqsts.all_code_rd` | **L1I MPKI**; fetch-latency children (iCache/iTLB/resteer) |
| `core_ports` | 50 | `exe_activity.{1_ports_util,2_ports_util,exe_bound_0_ports}`, `arith.div_active` | core-bound drill: port utilization, divider |
| `dram_bw` | 51 | `offcore_requests_outstanding.data_rd` (cmask=4), `…​.cycles_with_data_rd`, `offcore_requests.data_rd` | DRAM bandwidth / occupancy |
| `priv` | 54 | `task-clock`, `context-switches`, `cpu-migrations`, `page-faults`, `cycles:u`, `cycles:k`, `instructions:u`, `instructions:k` | user-vs-kernel split, scheduling |

### Derived-metric formulas (`plot_glm_results.py::met()`), signature heatmap columns

```
IPC        = instructions / cycles
Branch MPKI= 1000 · branch-misses            / coI(branch-misses)
DSB %      = 100  · idq.dsb_uops             / (dsb+mite+ms+lsd)
L1I MPKI   = 1000 · l2_rqsts.all_code_rd     / coI(l2_rqsts.all_code_rd)   # code read at L2 = L1I miss
L1D MPKI   = 1000 · (l2_hit+l3_hit+l3_miss)  / coI(mem_load_retired.l2_hit)
LLC MPKI   = 1000 · l3_miss                  / coI(mem_load_retired.l3_miss)
AMAT (cyc) = (5·l1 + 15·l2 + 50·l3 + 250·lm) / (l1+l2+l3+lm)              # fixed latency model
MLP        = l1d_pend_miss.pending / l1d_pend_miss.pending_cycles
vecFP %    = 100 · packed / (packed + scalar)
```

`coI(event)` = instructions summed **only over the windows where that event was counted**
(co-counted denominator). This is mandatory: dividing a one-group numerator by all-groups
instructions understates the ratio ~8× (bug found 2026-07-15, comment at `met()`).

---

## 2. TMA_EVENTS — the continuous top-down census (fixed / PERF_METRICS)

Defined at `run_glm_campaign.sh:60`, launched by `start_tma_cont()` (`:255–264`) → `tma_cont.csv`.

```
TMA_EVENTS = slots,
             topdown-retiring, topdown-bad-spec, topdown-fe-bound, topdown-be-bound,   # Level 1
             topdown-heavy-ops, topdown-br-mispredict, topdown-fetch-lat, topdown-mem-bound  # Level 2
```

- **Level 1** (4 buckets): Retiring, Bad-speculation, Frontend-bound, Backend-bound → `glm_tma_l1.png`.
- **Level 2** (4 direct sub-events; the siblings are computed as remainders):
  - `heavy-ops`  → Retiring split into light / heavy (heavy = vector/FMA)
  - `br-mispredict` → Bad-spec split into branch-mispredict / machine-clears
  - `fetch-lat`  → Frontend split into fetch-**latency** / fetch-**bandwidth**
  - `mem-bound`  → Backend split into **memory**-bound / **core**-bound
  - → `glm_tma_l2.png`, and the dumped `tma_l2_tool` / `tma_l2_harness` arrays
    (order: light, heavy, fetch-lat, fetch-bw, mispredict, clears, memory, core).

---

## 3. perf record — attribution only (statistical)

`run_glm_campaign.sh:250` — `perf record -e task-clock -a --cgroup=<fence> -g -F 99` →
`rec_scope{1,2,3}.data`. Turned by `mk_tables()` / `gen_lanes_leaf.sh` into
`scope*_{dso,comm}.txt` (library / program / symbol tables). **Sampling — never used for rates.**

---

## 4. Why two mechanisms? (the answer to "how are the 8 groups counted?")

**The 8 groups are time-shared; TMA runs continuously — because they use different counter hardware.**

- A CPU thread has only ~**8 general-purpose PMU counters**. Each of the 8 groups is sized to
  fit that budget, so **exactly one group is loaded per window** and counted at **100% enabled
  time** (no multiplexing). One 10 s window = one group; the next window = the next group in the
  shuffled `GORDER`; over an N-window episode each group gets ≈ N/8 windows. Per-metric values
  are **episode-sum ratios** over just that group's windows (hence `coI`).
  - *Rotation, not simultaneity:* `fe_lat` and `dram_bw` are never live in the same instant.
  - *Shuffled* each cycle so no group phase-locks to the agent's loop (systematic-sampling bias).
  - `--for-each-cgroup` means within a window, all fences (harness/tool/litellm) are counted
    **at once** — the split across fences is simultaneous; the split across *event groups* is
    what's time-shared.

- **TMA_EVENTS use the dedicated PERF_METRICS register + the fixed `slots` counter** — **zero GP
  counters**. So the top-down census coexists with whichever windowed group is active and runs
  the **whole episode at 100% duty** (the `-I 10000` is just a 10 s *read* interval; the events
  stay installed between reads). This is why TMA is a continuous whole-episode census while the
  detailed groups are a rotation.

### 8 groups vs TMA_EVENTS — the difference in one line

| | 8 windowed groups | TMA_EVENTS |
|---|---|---|
| Counter type | general-purpose PMU | PERF_METRICS MSR + fixed slots |
| Duty | 1 group per window, rotated (time-shared) | continuous, whole episode |
| Gives | **raw microarch events** → MPKI, IPC, FP, DSB, ports, DRAM BW | **top-down slot attribution** → L1+L2 buckets |
| Granularity | the *causes* (e.g. `icache_data.stalls`, `l2_rqsts.all_code_rd`) | the *bucket %* (e.g. `fetch-lat` share of slots) |

They are complementary, not redundant: `fe_lat`'s raw `l2_rqsts.all_code_rd` gives **L1I MPKI**
(an event rate), while TMA's `topdown-fetch-lat` gives **fetch-latency's share of pipeline
slots** — the raw group explains *what* the top-down bucket is made of.

The dry-run gate (`stage_dryrun`) verifies both: every windowed group reports 100% enabled time
(zero multiplexing) **and** the TMA census coexists with the groups at 100% — before any capture.

---

## Not part of this campaign

`local_agents/scripts/swe_live_two_view.sh` is a **separate, unused** experiment: SWE-agent
driven by a locally k3s-served Coder-7B (not GLM-5.2 via the litellm proxy). It has its own
7-group layout (`fp1/fp2`, `tma1/tma2`, 199 Hz records) and is referenced by nothing in the
certified or superseded campaigns. Ignore it for the SWE analysis.
