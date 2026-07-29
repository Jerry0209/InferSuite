# Report 10 — Per-window metric group: branches & speculation (deck slides 19–23)

**Date of study:** 2026-07-28 · **Author of record:** Tianrui (Jerry), with Claude Code
**Deck slides:** 19–23 (cross-task grids, harness grid, per-task galleries)
**Longer prose version:** [`../handwritten_notes/analysis.md`](../handwritten_notes/analysis.md), Parts 4 + 6 · **Capture method:** Report 04 ·
**Sibling metric-group reports:** 09 (frontend supply; same artifact set), 11–12

---

## 1. Key summary

This report reads out the **branches & speculation** metric group of the per-window study:
per-2-second-window branch-mispredict MPKIs (total, direction, indirect), a BTB-miss *proxy*
(BAClears), and the resteer-cycle cost, per fence and per command tag, and relates them to the
census TMA bad-speculation shares. Capture method (one paragraph; full detail in Report 04):
deterministic replays of the featured episodes with **one counter group dedicated per pass**
(`GORDER_OVERRIDE`, zero multiplexing, strictly serialized), 2-s windows, and a host-side 2 Hz
command tagger; all values land in `all_windows_<task>.csv` before any plotting. Because the
certified rotation's generic `branch-misses` cannot separate *direction* from *target*
mispredicts, a new counter group (`fe_miss`) was added and one extra replay pass per task run.

Headline (tool-fence per-window medians): **sympy has the worst and most direction-dominated
branch behavior** — 5.23 total MPKI of which 3.76 is conditional (72 %), with the highest BTB
proxy (0.44 median, 0.61 window mean); **astropy is intermediate** (3.25 / 1.62 / 1.05) and
carries the largest *indirect* share; **scikit-learn is near-clean** (0.03 median) except in
command-startup windows (p75 1.53). Resteer-cycle cost is ≈ equal for astropy/sympy (7.15 /
8.12 % of cycles) vs ≈ 0 for scikit (0.06 %) — mispredict cost shows up mostly as *wasted
slots* (census mispredict slot shares 14.1 / 18.0 % vs scikit 0.6 %), not as refetch bubbles.

## 2. Methodology

### 2.1 Metrics and load-bearing decisions

Metric definitions (formulas in `analyze_l3_windows.py:88,112,136–139`; events in `events.md`
and `run_glm_campaign.sh:58–60`):

| Metric | Event (group) | Status |
|---|---|---|
| `branch_MPKI` | `branch-misses` ÷ co-counted kI (`fpbr`) | exact count — *all* retired mispredicted branches |
| `branchDir_MPKI` | `br_misp_retired.cond` (`fe_miss`) | exact — direction (conditional) mispredicts |
| `branchInd_MPKI` | `br_misp_retired.indirect` (`fe_miss`) | exact — indirect-target mispredicts |
| `BTB_MPKI` | `baclears.any` (`fe_miss`) | **BTB-miss PROXY**: counts front-end re-steers after the branch-address calculator overrides the BTB (miss / unknown branch), not BTB lookups |
| `branch_resteer_pct` | `int_misc.clear_resteer_cycles` ÷ cycles (`fe_lat`) | exact cycle count; *attribution to branches is heuristic* — includes machine-clear resteers |

| Decision | Why |
|---|---|
| **Add `branchDir_MPKI`/`branchInd_MPKI` via a new group** (`GRP[fe_miss] = cycles, instructions, baclears.any, frontend_retired.any_dsb_miss, br_misp_retired.cond, br_misp_retired.indirect`) | the certified `fpbr` group's generic `branch-misses` counts all mispredicts but cannot separate *direction* (data-dependent control flow the predictor can't learn) from *target/indirect* (dispatch tables, virtual calls) — different causes, different fixes |
| One extra serialized replay pass per task (pass 11/11 → `run_11`); group selectable only via `GORDER_OVERRIDE`, certified rotation untouched | zero-mux requires ≤ 4 GP events per pass; the live-campaign rotation stays certified as-is |
| Dry-verify the new group 100 %-enabled before use | multiplexing is invalid on bursty agent loads (tens of % error) |
| Every MPKI uses instructions co-counted in its own group's windows | cross-group denominators diluted ratios ~8× in an earlier bug |
| Accept `clear_resteer_cycles` as branch refetch cost | census splits bad-spec: mispredict slots 18.0 % of sympy's ≈ 19 % bad-spec — machine clears are a minor contaminant |
| Report per-window **medians per tag**; relate slot cost to the census TMA, not to resteers alone | medians resist startup spikes; slots (bad-spec) and cycles (resteers) are different currencies and must both be shown |

Window→command tags are the heuristic 2 Hz priority tagger of Report 04 (§2.1 D5); fence
membership is exact kernel cgroup accounting (Report 03). Census TMA bad-spec/mispredict
shares come from the continuous PERF_METRICS capture (Report 02 / `analysis.md` Part 4).

### 2.2 Verification and hazards

1. **Zero-mux verified in the banked data**: `group_fe_miss_wNNN.txt` window files carry no
   multiplexing-scale annotation (spot-checked `run_11` on all tasks); the dry-run gate
   requires 100 % enabled time.
2. **Cross-group consistency check (passed)**: sympy direction + indirect = 3.76 + 1.51 =
   5.27 vs the *independent* `fpbr`-pass total 5.23 — two different replays and counter sets
   agree within 1 %. astropy sums to 2.67 of 3.25 (82 %): the remainder is mispredicted
   returns/calls (not in cond|indirect) plus pass-to-pass variation — expected, not a defect.
3. **ISO-PROOF abort/retry**: the scikit `fe_miss` pass first failed the quiet gate (measured
   core at 2.0 % busy; `l3prof_femiss.log`) and was re-run — the wrapper skips completed
   passes, so only the failed pass repeated. Banked `run_11/l3group.txt` confirms `fe_miss`.
4. **Aggregation reconciliation**: deck slide 22's "BTB ≈ 0.6" is the sympy window *mean*
   (0.61); the median is 0.44 (p75 0.91). `analysis.md` Part 6's scikit branch "0.2" matches
   the instruction-weighted aggregate (0.27), not the window median (0.03) — scikit's
   distribution is extremely skewed, so the aggregation must always be named.
5. Windows with < 5×10⁵ fence instructions are dropped (unstable ratios; Report 04 D6).
6. Scope caveat: one replay pass per (task, group) — per-window spread is across *windows*,
   not across runs; the certified "median run per cell" rule does not apply here.

### 2.3 Reproduction recipe

```bash
cd local_agents/scripts/glm
# the branch-specific extra pass only (~4–5 min per task, no API cost); full 11-group
# sweep and analysis: Report 04 §2.3
PROF_GROUPS="fe_miss" SHORT=scikit-learn SRC=1 \
DATA_ROOT=$HOME/InferSuite/local_agents/superseded_40min/data ./replay_l3_profile.sh
# astropy: SHORT=astropy SRC=2 ; sympy: SHORT=sympy SRC=2. Re-run to sweep ISO-PROOF aborts.
python3 analyze_l3_windows.py <DATA_ROOT> <task> --plot   # rebuilds all_windows_<task>.csv
```

Stats quoted here recompute from the CSVs (metrics `branch_MPKI`, `branchDir_MPKI`,
`branchInd_MPKI`, `BTB_MPKI`, `branch_resteer_pct`; filter `fence`, group by `tag`, take
medians). During capture, run nothing else — or pin to housekeeping (`taskset -c 0,1,12,13`).

### 2.4 Scripts and artifacts

| Item | Location | Role |
|---|---|---|
| `run_glm_campaign.sh` | `local_agents/scripts/glm/` | `GRP[fe_miss]` definition (:58–60); replay-one stage |
| `replay_l3_profile.sh` | same dir | pass orchestrator (skip/retry, tagger) |
| `analyze_l3_windows.py` | same dir | metric formulas (:88, :112, :136–139) → CSVs + figures |
| `cross_task_grid.py`, `build_metric_gallery.py` | same dir | slide-22/23 grids; per-task HTML galleries |
| `events.md` | same dir | event → metric → formula reference (`fpbr` :25, `fe_lat` :29) |
| `all_windows_<task>.csv` | `local_agents/superseded_40min/data/l3_study/` | source of truth (14,591 rows across tasks) |
| Galleries (3 × task) | URLs on deck slide 23 | box + timeline views for every metric incl. this group |

## 3. Key insights (most → least important)

1. **sympy has the worst and most direction-dominated branch behavior**: 5.23 total MPKI
   (median tool window), of which conditional-direction mispredicts are 3.76 (72 %), plus the
   highest BTB proxy (0.44 median / 0.61 mean / p75 0.91 MPKI). This is the counter-level
   cause of its census bad-speculation of ≈ 18–19 % of slots: CAS/symbolic dispatch is
   data-dependent control flow the predictor cannot learn — a *direction* problem, not a
   branch-target problem.
2. **Mispredict cost lands in wasted slots more than in refetch**: astropy/sympy pay 14.1 /
   18.0 % of slots to mispredicts (census) but only 7.15 / 8.12 % of cycles to
   clear-resteers — and the resteer cost is ≈ equal on the two tasks despite sympy's 1.6×
   higher MPKI (front-end refetch per mispredict is cheaper for sympy; the slot kill is not).
   scikit shows ≈ 0 on both sides (0.6 % slots, 0.06 % resteer cycles).
3. **scikit-learn is near-clean except startup windows**: median 0.03 branch MPKI but
   p75 1.53 — the mass above the median is entirely `python-other` startup windows (1.57 MPKI,
   1.69 % resteers) while pytest/OpenBLAS windows predict essentially perfectly (0.03 MPKI,
   0.06 % resteers). Hot numeric loops are the branch predictor's best case.
4. **Indirect mispredicts are small everywhere** (medians ≤ 1.51 MPKI: sympy 1.51, astropy
   1.05, scikit 0.00), **but astropy's indirect share is the largest** (1.05 of 3.25 ≈ 32 %),
   and in astropy's pytest windows indirect *exceeds* direction (1.58 vs 1.14 MPKI) — the one
   place where dispatch-table targets, not data-dependent directions, lead the mispredicts.
5. **Per-tag, shell/startup windows are the worst branch citizens on every task** (branch MPKI:
   astropy shell 6.76, sympy shell 6.79; BTB proxy 1.26 / 1.17 — cold predictor and BTB state),
   while pytest is the calmest heavy tag (astropy 2.55, sympy 4.16 vs their `python-other`
   1.64 / 5.42). Long test runs warm the predictor; short commands never do.
6. **The harness fence is tight per-window and near-identical for astropy/sympy** (branch
   median 1.00 / 0.94, direction 0.85 / 0.86, IQRs within ≈ 0.15) — the per-window echo of the
   task-independent harness TMA bar. Caveat: the scikit replay's harness windows sit higher
   (1.94 MPKI, 6.82 % resteers) on only n = 19–20 windows of a ≈ 2-minute replay, where
   startup/orchestration dominates the harness's few busy windows.
7. **The direction/indirect split validates the zero-mux method itself**: two independent
   passes (fe_miss vs fpbr, different GP counters, different replays of the same trajectory)
   reproduce sympy's total to within 1 % — the windowed dedicated-group design measures the
   workload, not the pass.
