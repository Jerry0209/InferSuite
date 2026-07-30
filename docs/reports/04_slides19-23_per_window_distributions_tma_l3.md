# Report 04 — Per-window distributions & TMA Level 3 (deck slides 19–20, 22–23)

**Date of study:** 2026-07-28 · **Author of record:** Tianrui (Jerry), with Claude Code
**Deck slides:** 19 (method + scikit flagships), 20 (TMA-L3 memory verdict), 22 (12-metric
cross-task grid), 23 (harness fence + call durations + gallery links)
**Longer prose version:** [`../handwritten_notes/analysis.md`](../handwritten_notes/analysis.md), Part 6 · **Boundary/tagging audit:** Report 03

---

## 1. Key summary

The certified signature numbers are episode-sum averages; the mentor asked for
**distributions** — every metric per window, tagged by the command executing, presented as
box plots and tag-colored timelines, with *all values collected first* so plotting choices
come later. We built that as a new capture mode on top of the kit: **deterministic replays**
(no model, no API cost) with **one counter group dedicated per pass** (`GORDER_OVERRIDE`,
zero multiplexing), **2-second windows**, and a **2 Hz host-side command tagger**. Three
counter groups were added to the kit to complete TMA Level 3 and the mentor's metric list
(`mem_bound`, `fe_l3x`, `fe_miss`). Result: **33 passes** (11 groups × 3 tasks),
**14,591 window-metric rows** in long-format CSVs, ~400 audit-ready figures, three published
per-task galleries, and several findings the averages had hidden — most prominently the
three distribution shapes (scikit bimodal / astropy wide / sympy tight), the L3 memory-ladder
verdict (**L1-bound 14.4 %, DRAM-bound 0.0 %** for scikit against 62 % DRAM occupancy at
MLP 3.3), and the new-counter readings (µop-cache MPKI 63/54/20; sympy's branch problem is
direction-dominated with the highest BTB pressure).

## 2. Methodology

### 2.1 The capture design, decision by decision

**D1 — Replays, not live episodes.** `sweagent run-replay` re-executes the recorded
trajectory of a featured live episode in a fresh sandbox with the model never called.
Commands genuinely re-execute (real microarchitecture), only the *choice* of commands is
frozen — so passes are deterministic, comparable to each other, and free. An 8-minute live
scikit episode (74 % model-wait) compresses to ≈ 2 min of pure execution; astropy/sympy
replays run ≈ 4 min. Source episodes: scikit-learn live run_1, astropy live run_2, sympy
live run_2 (the featured clean runs).

**D2 — One dedicated group per pass** (`GORDER_OVERRIDE=<group>`): every 2-s window of a
pass measures the *same* group ⇒ a continuous per-window series per metric (~57 windows
for scikit, ~110 for astropy/sympy) instead of a 1-in-11 rotation sample. Cost: passes must
be **strictly serialized** — GP counters are shared hardware; two concurrent `perf stat`
sessions would multiplex and void the zero-mux guarantee.

**D3 — `WINSEC=2`.** Trade-off: the certified 10-s windows blend phases (the
"average hides structure" problem); much shorter windows retire too few instructions for
stable ratios and inflate per-window perf-startup overhead. 2 s keeps most windows
single-command *where the CPU is* while giving ~10⁹ instructions per busy window.
**Known limitation (mentor-probed, quantified):** a window is *not* a call. scikit's
median call is 0.14 s (75 % of calls ≤ 0.5 s) — short calls share windows. The rescue is
the duration long tail: the 3 calls > 2 s (the pytest runs, 27–29 s each) carry **83 % of
tool wall-time and 95.5 % of tool instructions**, and each spans ~14 clean single-command
windows. Windows resolve *phases* (where the CPU is); per-call cost of sub-second calls is
Report 03's anchor-join territory, not this method's.

**D4 — Three new counter groups** (added to `run_glm_campaign.sh`'s `GRP` table; selected
only via `GORDER_OVERRIDE`, certified rotation untouched). Events chosen to match perf's
own SPR TMA formulas (`perf list --details tma_*`), each group ≤ 4 GP + fixed counters and
dry-verified 100 %-enabled before use:

| Group | Events (beyond cycles,instructions) | Gives |
|---|---|---|
| `mem_bound` | `exe_activity.bound_on_loads`, `memory_activity.stalls_{l1d,l2,l3}_miss` | exact TMA-L3 memory ladder: L1/L2/L3/DRAM-bound |
| `fe_l3x` | `dsb2mite_switches.penalty_cycles`, `idq.ms_switches`, `exe_activity.bound_on_stores`, `itlb_misses.walk_active` | DSB-switch & MS-switch stalls, store-bound, iTLB walks |
| `fe_miss` | `baclears.any`, `frontend_retired.any_dsb_miss`, `br_misp_retired.cond`, `br_misp_retired.indirect` | BTB MPKI, µop-cache MPKI, branch-direction vs indirect mispredicts |

L3 ladder formulas (perf's own): l1_bound = max(bound_on_loads − stalls_l1d, 0)/cycles;
l2_bound = (stalls_l1d − stalls_l2)/cycles; l3_bound = (stalls_l2 − stalls_l3)/cycles;
dram_bound = stalls_l3/cycles; store_bound = bound_on_stores/cycles. LCP is the one
un-captured L3 child.

**D5 — The command tagger.** A host-side loop polls
`/sys/fs/cgroup/<tool_cg>/cgroup.procs` at 2 Hz and logs `(epoch, pid, argv)` →
`cmdlog.tsv`, pinned to the housekeeping cores (zero pollution of measured fences; running
*inside* the container via `docker exec` would have landed the poll cost in the tool
fence). At analysis time each window takes the **most specific foreground tag** present:
`tests(pytest) > compile > pkg/build > git > python-other > shell > other > agent-tool`.
Priority (not majority) is essential: the SWE-ReX server and session shell appear in
*every* poll and a majority rule tags everything "mixed" (first attempt failed exactly
that way).

**D6 — All values first.** The analyzer emits long-format CSVs before any plotting:
`all_windows_<task>.csv` (one row per pass × window × fence × metric: task, group, run,
win, t0, dur, fence, instructions, tag, metric, value), `tma_intervals_<task>.csv`
(per-10-s TMA L1+L2 shares per fence from the census), `call_durations_<task>.csv`
(per-call `execution_time` by class). Windows with < 5×10⁵ fence instructions are dropped
(unstable ratios); the plotters are pure CSV consumers.

### 2.2 Operational hazards (learned, then engineered around)

1. **ISO-PROOF vs teardown drain:** each pass applies full isolation and requires the
   measured cores silent for 1 s. Docker/containerd teardown of the previous sandbox can
   take 15–25 s, so back-to-back passes failed the gate in an alternating pattern.
   Fix: 30 s settle between passes; failed passes simply re-run (the wrapper skips
   completed ones via `l3group.txt` + `DONE`).
2. **Self-interference:** any analysis/plotting run on the free cores while a pass sits at
   its ISO-PROOF instant aborts that pass (happened twice: an unpinned analyzer, and a
   verification stress pinned to a *measured* core). Rule: during capture chains, run
   nothing — or pin strictly to housekeeping (`taskset -c 0,1,12,13`) and accept residual
   risk at gate instants.
3. **Bash trap:** `GROUPS` is a reserved bash variable (assignments silently ignored) —
   the first wrapper run iterated over the user's group IDs. Renamed to `PROF_GROUPS`;
   wrapper now fail-fasts on unknown group names.
4. **matplotlib 3.11 API:** `boxplot(labels=…)` → `tick_labels=…`.

### 2.3 Reproduction recipe

```bash
cd local_agents/scripts/glm
# capture: 11 dedicated-group passes for one task (~35-50 min, no API cost)
PROF_GROUPS="fe_lat fe fpbr cache mlp core_ports dram_bw mem_bound fe_l3x priv fe_miss" \
SHORT=scikit-learn SRC=1 \
DATA_ROOT=$HOME/InferSuite/local_agents/superseded_40min/data ./replay_l3_profile.sh
# (astropy: SHORT=astropy SRC=2 ; sympy: SHORT=sympy SRC=2. Re-run the same command to
#  sweep any ISO-PROOF-aborted passes; completed passes are skipped.)

# analysis: CSVs + every box/timeline figure (pin to housekeeping if captures may run)
python3 analyze_l3_windows.py <DATA_ROOT> scikit-learn --plot
python3 cross_task_grid.py          # 12-panel tool+harness grids + call-duration panel
python3 build_metric_gallery.py     # self-contained HTML gallery per task
```

Data layout per pass: `glm_replay_swe_<task>/run_N/` with `l3group.txt` (which group N
carries), `windows.tsv` (epoch brackets), `group_<g>_wNNN.txt` (exact per-fence counts),
`cmdlog.tsv` (tag stream), `tma_cont.csv`, `cpustat_scope*.tsv`, `rec_scope*.data`
(records stay local per repo policy), `metadata.json`. Fence naming for parsers:
harness cgroup contains `glm-rep`, tool contains `docker-`.

### 2.4 Scripts used (all in `local_agents/scripts/glm/` unless noted)

| Script | Role |
|---|---|
| `replay_l3_profile.sh` | pass orchestrator: per-group replay + tagger + skip/retry logic |
| `run_glm_campaign.sh` | `replay-one` stage (fences/pollers/census/records/teardown); `GRP` table incl. the three new groups |
| `analyze_l3_windows.py` | windows × counters × tags → CSVs; box/timeline figures for both fences; call-duration extraction |
| `cross_task_grid.py` | cross-task 12-panel grids (tool + harness) + call-duration panel |
| `build_metric_gallery.py` | per-task self-contained HTML galleries (33 metrics × 4 views: tool box, harness box, tool timeline, harness timeline) |
| `dump_all_metrics.py` | episode-level (not per-window) all-metrics CSV — complementary view |
| `events.md` | event → metric → formula reference for every counter group |
| deck builder (`build_deck.py`) | session scratchpad only — presentation, not data; galleries/deck are published artifacts |

Published artifacts: main deck + three per-task galleries (URLs in the deck's slide 23).

## 3. Key insights (most → least important)

1. **Distribution shape is a workload fingerprint the averages destroyed.** scikit-learn is
   *bimodal* (pytest at IPC 0.62 vs everything else 1.1–2.0 — the "0.64 average" was just
   pytest's weight); astropy is *wide* (its L1I pain is specifically pytest: 23.3 vs 7.9
   MPKI); sympy is *tight* (≈19 MPKI, ≈5.6 % iCache stall in every tag — the interpreter
   churn is the workload itself).
2. **TMA L3 memory verdict (scikit): L1-bound 14.4 % of cycles, L2 0.02 %, L3 0.3 %,
   DRAM-bound 0.0 %, store 0.1 %** — while DRAM read occupancy is 62 % of cycles at
   MLP ≈ 3.3. OpenBLAS streams heavily but never stalls on memory: the backend limit is
   execution ports + L1 data supply. This settles, by direct measurement, the question the
   L2 split left open.
3. **New counters localize the frontend problem to the µop cache**: µop-cache (DSB) MPKI
   ≈ 63 (astropy) / 54 (sympy) / ~20 (scikit); DSB-switch penalties ≈ 7 % of cycles for
   astropy/sympy. sympy's branch problem is **direction**-dominated (conditional 3.7 of
   5.2 total MPKI) with the highest BTB pressure (BAClears ≈ 0.6 MPKI); astropy's
   mispredicts are fewer and its footprint pain larger.
4. **iTLB is ruled out everywhere** (walk-active ≤ 0.7 % of cycles) — removes one standing
   hypothesis for the fetch-latency bound.
5. **The harness fence is tight and task-independent per-window** — the per-window
   confirmation of the episode-level result that the agent program's microarchitectural
   profile belongs to the agent, not the task.
6. **Call-duration long tail defines what windows can resolve**: median call 0.14 s, but
   3 calls own 83 % of wall and ~95 % of instructions. Per-window analysis is a *phase*
   lens; per-call cost of sub-second calls needs the anchor join (Report 03). Both are
   needed; neither substitutes.
7. **Deterministic replays make microarchitectural studies cheap and repeatable** — 33
   passes, zero API tokens, identical command streams per pass — and the dedicated-group
   trick converts the kit's rotation sampling into continuous per-metric coverage.
8. **Live-process tagging beats log-text tagging for time-resolved work**, but only with
   priority (not majority) tag selection, host-side polling, and housekeeping pinning —
   each of which was a corrected failure, not a first guess.

---

**Method update (2026-07-30).** `run_glm_campaign.sh` changed after this report was written,
in ways that do not alter this study's banked data but do alter the harness a reproducer runs:
the dry-run numpy workloads now resolve a numpy-capable interpreter (`dry_python()`; bare
`python3` no longer has numpy on this workstation), the ISO-PROOF quiet check settles-and-retries
up to 8×4 s (2.0 %/core threshold unchanged — the single sample used to land in the
cpuset-migration drain), and episode liveness keys on the highest `STEP N` seen rather than the
literal "STEP 2" banner (which SWE-agent does not always emit). Evidence and rationale:
report 16 §2.2. The method as described in this report is what was in force when this study's
data was captured.
