# Report 11 — Per-window metric group: memory hierarchy (deck slides 19–23)

**Date of study:** 2026-07-28 · **Author of record:** Tianrui (Jerry), with Claude Code
**Deck slides:** 19–23 (memory rows of the per-window study: slide-20 TMA-L3 verdict, slide-22
grid columns L1D/L2/LLC MPKI · AMAT · MLP, slide-23 harness mirror + galleries)
**Longer prose version:** [`../handwritten_notes/analysis.md`](../handwritten_notes/analysis.md), Part 6 · **Capture method:** Report 04 ·
**Group companions:** Reports 09 (frontend supply), 10 (branch/spec), 12 (core/system)

---

## 1. Key summary

Question: for the CPU cycles the agent's tool and harness fences actually burn, where in the
memory hierarchy do they wait — and is "memory-bound" ever DRAM? Method (Report 04's capture,
summarized): deterministic replays of the featured episodes with one counter group dedicated
per pass (`GORDER_OVERRIDE`, zero multiplexing), 2-s windows, a 2 Hz command tagger, all
values banked to `all_windows_<task>.csv` before plotting; this report reads five of the
eleven groups (`cache`, `mlp`, `dram_bw`, `mem_bound`, `fe_l3x`). Headline: **no tool fence is
DRAM-latency-bound**. scikit-learn's exact TMA-L3 memory ladder (pytest-window medians) is
**L1-bound 14.4 % of cycles, L2 0.02 %, L3 0.3 %, DRAM 0.0 %, store 0.09 %** — while the same
windows keep ≥ 4 offcore reads in flight **62 %** of cycles at **MLP ≈ 3.3**: heavy streaming,
fully prefetched/overlapped, never a stall source. This settles the ambiguity Report 02's
Level-2 split left open ("memory-bound 6 %" — which level?). LLC MPKI is ≈ 0 everywhere
(≤ 0.15), AMAT sits at its 5-cycle model floor (tool medians 5.01–5.51), and sympy is the only
task with visible DRAM reach (DRAM-bound 4.7 %).

## 2. Methodology

### 2.1 The metric set — formula, semantics, honest label (each carries its Why)

All events are counted per fence via perf cgroup scoping in dedicated-group passes (exact,
zero-mux); every ratio uses co-counted denominators from the same window. The *labels* below
are the load-bearing decisions — mixing the two ladder semantics inverts conclusions (§2.2).

| Metric | Events → formula (`analyze_l3_windows.py::derive`) | Honest label / why this form |
|---|---|---|
| `L1D_MPKI` | `mem_load_retired.{l2_hit,l3_hit,l3_miss}` summed ×1000/instructions | **hit-based ladder, retired loads only** — event *rate*; excludes prefetches, stores, code reads. Chosen because retired-load hit levels are the unambiguous "where did loads land" census |
| `L2_MPKI` / `LLC_MPKI` | ×1000·(l3_hit+l3_miss)/I ; ×1000·l3_miss/I | same ladder, next rungs |
| `AMAT_cyc` | (5·l1 + 15·l2 + 50·l3 + 250·l3_miss)/Σloads | **fixed-latency MODEL** (5/15/50/250 cyc assumed), not measured latency; floor = 5.0 when all loads hit L1. Kept because it collapses the ladder to one comparable number |
| `MLP` | `l1d_pend_miss.pending` / `…pending_cycles` | average outstanding L1D misses *while ≥ 1 is outstanding* — overlap witness for the occupancy story |
| `tma_{l1,l2,l3,dram}_bound_pct` | `exe_activity.bound_on_loads`, `memory_activity.stalls_{l1d,l2,l3}_miss`; l1 = max(bol−s_l1d,0)/C, l2 = max(s_l1d−s_l2,0)/C, l3 = max(s_l2−s_l3,0)/C, dram = s_l3/C | **exact TMA-L3 memory ladder, perf's own SPR formulas** — *stall-cycle attribution* (% of cycles), the only rows that say what the pipeline waited on |
| `tma_store_bound_pct` | `exe_activity.bound_on_stores`/C (from `fe_l3x` group) | stall attribution, store side |
| `dram_bw_bound_pct` | `offcore_requests_outstanding.data_rd,cmask=4`/C | **OCCUPANCY, not stall** — % of cycles with ≥ 4 offcore data reads in flight; high values with DRAM-bound ≈ 0 mean prefetched streaming, not a bottleneck |
| `dram_read_occ_pct` | `…cycles_with_data_rd`/C | occupancy at depth ≥ 1 — the companion that separates "deep queue" from "any traffic" |

Shared decisions (why): per-window **medians by fence and tag**, never pooled means (locked
convention: pooling runs/windows lets one phase swamp the statistic); windows with
< 5×10⁵ fence instructions dropped, AMAT additionally requires > 10⁴ retired loads and MLP
> 10⁴ pending-cycles (unstable ratios otherwise) — hence per-metric `n` differs slightly, as
each metric lives in its own pass and its own windows survive the floors.

### 2.2 Verification and hazards

- **Naming-discipline hazard (the one to record):** the hit-ladder MPKIs must never be
  presented as TMA L\*-Bound. They have different semantics — miss-event *rates* over retired
  loads vs stall-*cycle* attribution — and they diverge exactly where it matters: scikit's
  pytest windows have **L1D MPKI 0.14** (essentially every load hits L1) yet **L1-bound
  14.4 % of cycles** — the pipeline stalls on loads that *hit* L1 (supply latency/pressure),
  which no MPKI can show. Conversely sympy's L2 MPKI 0.78 looks tiny while its
  L2-bound is 2.38 % of cycles. One table column name decides whether the reader concludes
  "no memory problem" or "L1-supply-bound".
- **Ladders don't numerically nest across levels/captures:** Report 02's Level-2 memory-bound
  (6.1 % for scikit, slot-based, continuous PERF_METRICS census) and this L3 ladder
  (cycle-based GP-counter formulas, replay windows) are different bases; the verdict used here
  is the *ranking inside* the L3 ladder, not L2↔L3 arithmetic.
- **Occupancy ≠ stall, cross-checked:** the 62 % ≥ 4-deep read occupancy against DRAM-bound
  0.0 % is not a contradiction but the finding — verified coherent by MLP ≈ 3.3 (misses that
  do occur are overlapped) and by the retired-load ladder (L1D MPKI 0.14: the streams are
  prefetch traffic, invisible to retired-load misses *and* to stalls).
- **Two-sided agreement:** ladder MPKIs (cache group) and stall ladder (mem_bound group) come
  from different passes over the identical replayed trajectory and tell one consistent story
  per task — the same style of independent cross-check the kit requires elsewhere.
- Capture-level hazards (ISO-PROOF vs teardown drain, self-interference, bash `GROUPS` trap)
  are Report 04 §2.2; boundary/tag semantics are Report 03.

### 2.3 Reproduction recipe

```bash
cd local_agents/scripts/glm
# capture (only if CSVs absent) — Report 04 §2.3; the memory subset alone:
PROF_GROUPS="cache mlp dram_bw mem_bound fe_l3x" SHORT=scikit-learn SRC=1 \
DATA_ROOT=$HOME/InferSuite/local_agents/superseded_40min/data ./replay_l3_profile.sh
# (astropy: SHORT=astropy SRC=2 ; sympy: SHORT=sympy SRC=2 — deterministic, no API cost)

# CSVs + figures from banked passes (system python3):
python3 analyze_l3_windows.py <DATA_ROOT> scikit-learn --plot
python3 cross_task_grid.py && python3 build_metric_gallery.py
```

Recompute any number in this report from the banked CSVs (no plotting needed):

```python
import pandas as pd
d = pd.read_csv("local_agents/superseded_40min/data/l3_study/all_windows_scikit-learn.csv")
m = d[(d.metric=="tma_l1_bound_pct") & (d.fence=="tool")]
print(m.value.median(), m.groupby("tag").value.median())   # 14.39 overall; pytest 14.39
```

### 2.4 Scripts and artifacts (same set as Report 09; all scripts in `local_agents/scripts/glm/`)

| Item | Location / role |
|---|---|
| `run_glm_campaign.sh` | `GRP` table: `cache`, `mlp`, `dram_bw` (certified rotation), `mem_bound`, `fe_l3x` (added for TMA-L3); replay-one stage |
| `replay_l3_profile.sh` | dedicated-group pass orchestrator (skip/retry, tagger) |
| `analyze_l3_windows.py` | `derive()` holds every formula above; emits CSVs + box/tag/timeline figures |
| `cross_task_grid.py`, `build_metric_gallery.py` | slide-22/23 grids; per-task HTML galleries (~400 figures) |
| `events.md` | event → metric → formula reference (incl. the AMAT model line) |
| `all_windows_<task>.csv`, `tma_intervals_<task>.csv`, `plots/` | `local_agents/superseded_40min/data/l3_study/` — the banked source of every number here |

## 3. Key insights (most → least important)

1. **The TMA-L3 memory ladder verdict (scikit-learn tool fence, pytest-window medians):
   L1-bound 14.39 %, L2 0.02 %, L3 0.27 %, DRAM 0.00 %, store 0.09 % of cycles.** The
   backend's memory component is almost purely L1 data supply — Report 02's "memory-bound
   6 %, core-bound 28 %" ambiguity is settled by direct measurement: OpenBLAS never waits on
   main memory.
2. **High bandwidth utilization with zero latency stall = prefetched, overlapped streaming.**
   The same pytest windows hold ≥ 4 offcore reads in flight 61.8 % of cycles (≥ 1 read:
   82.1 %) at MLP 3.29, yet DRAM-bound is 0.00 % and retired-load L1D MPKI is 0.14. The
   occupancy metric measures traffic, not suffering — labeling it "bandwidth-bound" without
   the stall ladder would have inverted the conclusion.
3. **Event rates and stall attribution are different instruments (the naming hazard as a
   finding):** scikit combines the *lowest* miss rates of the three tasks with the *highest*
   L1-bound share (14.39 % vs astropy 8.89, sympy 7.68) — stalls on L1 *hits*. MPKI columns
   answer "where do loads land", TMA columns answer "what does the pipeline wait on"; only
   together do they identify L1-supply as the limit.
4. **sympy is the only task with visible DRAM reach:** tool DRAM-bound median 4.69 % (p75
   5.87) vs astropy 1.62 % and scikit 0.00 % — consistent with its deepest hit ladder
   (below) and its L3-bound 7.29 % (scikit 0.30, astropy 3.68).
5. **The load-hit ladder per task (tool medians, L1D/L2/LLC MPKI):** scikit
   0.15/0.01/0.00 · astropy 6.71/0.35/0.05 · sympy 8.01/0.81/0.15. **LLC MPKI ≈ 0
   everywhere** — the working sets fit on-chip — and AMAT stays near its 5.0 model floor
   (5.01/5.33/5.51), i.e. the fixed-latency model confirms misses are too rare to move
   average load cost.
6. **Store-bound is negligible in every tool fence** (medians 0.09/0.16/0.63 % of cycles;
   harness ≤ 2.03 %) — writes never bound these workloads.
7. **Per-tag structure mirrors the group's task shapes** (Report 04's fingerprint): scikit
   bimodal — pytest streams (L1D MPKI 0.14, ≥ 4-deep occupancy 61.8 %) vs python-other
   (2.36, 17.0 %); sympy tag-invariant (L1D MPKI 7.99/8.16/8.00 across pytest/shell/python) —
   interpreter churn is the workload; astropy's DRAM tail sits in shell windows
   (DRAM-bound 5.11 % vs 0.79 % python-other).
8. **The harness fence is tight and task-independent on the load side** (L1-bound median
   4.04–4.53 %, L1D MPKI 1.66–2.60, AMAT 5.21–5.83 across tasks) — but DRAM-bound is its
   one wide metric (medians 9.32/7.91/17.99 %, sympy p75 22.26): the CPython agent process
   reaches memory deeper than most tool windows. Read with care — harness window counts are
   small for scikit (n = 19) and the occupancy caveat applies unchanged.
