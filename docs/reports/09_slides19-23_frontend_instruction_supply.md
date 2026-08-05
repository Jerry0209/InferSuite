# Report 09 — Per-window metric group: frontend instruction supply (deck slides 19–23)

**Date of study:** 2026-07-28 · **Author of record:** Tianrui (Jerry), with Claude Code
**Deck slides:** 19–23 (per-window studies + per-task metric galleries)
**Longer prose version:** [`../handwritten_notes/analysis.md`](../handwritten_notes/analysis.md), Part 6 · **Capture method:** Report 04 · **Boundary/tagging audit:** Report 03

---

## 1. Key summary

This report documents one metric family of the per-window distribution study: **instruction
supply** — how each task's code reaches the pipeline (L1I pressure, iCache/iTLB stalls, µop-cache
vs legacy-decoder delivery, decoder-switch penalties, microcode-sequencer involvement). The
capture is exactly Report 04's (dedicated-group deterministic replays, 2-s windows, 2 Hz command
tagger, zero multiplexing); here only the family-specific layers are added: which four counter
groups carry it, the exact derivations, and what the distributions show. Headline: instruction
supply is the axis that most cleanly separates the three tasks' tool fences — µop-cache MPKI
**62.6 (astropy) / 52.8 (sympy) / 19.6 (scikit-learn)** with DSB delivery share the mirror image
(**55.6 / 59.4 / 85.7 %**), DSB→MITE switch penalties **6.9 / 6.5 / 1.1 % of cycles**, and iTLB
ruled out everywhere (walk-active median ≤ 0.45 % of cycles). astropy's L1I pain is
command-structured (pytest 23.3 MPKI vs 7.9 in other-python windows); sympy's is uniform across
every tag (overall IQR 18.4–22.8 MPKI); scikit's is near-zero except command-startup spikes.
The harness fence is tight and task-independent on every delivery metric.

## 2. Methodology

### 2.1 Design decisions specific to this family

Capture method (not re-derived here — Report 04 §2.1): `sweagent run-replay` re-executes a
featured live trajectory with no model calls; each pass dedicates ONE counter group via
`GORDER_OVERRIDE` (zero multiplexing, 100 %-enabled verified), `WINSEC=2`, and a host-side 2 Hz
poll of the tool cgroup tags each window with the most specific foreground command. This family
consumes **12 of the study's 33 passes** (4 groups × 3 tasks).

| Decision | Value | Why |
|---|---|---|
| Counter groups carrying the family | `fe_lat`, `fe` (certified-rotation members), `fe_l3x`, `fe_miss` (study-added, `GORDER_OVERRIDE`-only) | `fe_lat`/`fe` reuse the certified kit unchanged; `fe_l3x`/`fe_miss` (added 2026-07-28, `run_glm_campaign.sh` GRP table :57/:60) complete the TMA-L3 frontend children and the µop-cache/BTB/mispredict split without touching the certified rotation |
| Group sizing | each ≤ 4 GP events + `cycles,instructions` | fits the ~8-GP-counter budget so every window counts at 100 % enabled time; every ratio gets a co-counted denominator (`events.md` §1) |
| Two iTLB views | `icache_tag.stalls` (perf's `tma_itlb_misses` numerator) AND `itlb_misses.walk_active` | a "ruled out" verdict needs both the superset (tag-lookup stall cycles, includes STLB-hit latency) and the subset (hardware page-walk-active cycles) to be small |
| Two DSB views | IDQ delivery share (`fe`) AND retirement-based miss rate (`fe_miss`) | independent hardware paths (delivery-slot occupancy vs precise retired-instruction event); agreement is the internal cross-check |
| L1I metric formula | identical to the certified signature heatmap's "L1I MPKI" column | per-window values stay comparable to the episode-sum certified numbers (`events.md`: code read arriving at L2 = L1I miss) |
| Validity floors | window dropped if < 5×10⁵ fence instructions; IDQ shares additionally need > 10⁵ IDQ uops | ratios on near-idle windows are noise (`analyze_l3_windows.py::derive()` guards) |

**Derivations** (`analyze_l3_windows.py::derive()`, :102–139) and honest labels — proxy vs
exact matters here:

| Metric | Formula | Label |
|---|---|---|
| `codeRead_MPKI_L1I` | 1000·`l2_rqsts.all_code_rd`/instr | **L1I-pressure proxy**: all code reads reaching L2 (demand + prefetch), not a retired-miss count |
| `icache_data_stall_pct` | 100·`icache_data.stalls`/cycles | counted stall cycles on L1I data fetch |
| `itlb_tag_stall_pct` | 100·`icache_tag.stalls`/cycles | counted; perf's `tma_itlb_misses` numerator |
| `itlb_walk_pct` | 100·`itlb_misses.walk_active`/cycles | counted; page-walk-active cycles only (subset of iTLB cost) |
| `DSB_pct`/`MITE_pct`/`MS_pct` | 100·`idq.{dsb,mite,ms}_uops`/(dsb+mite+ms+lsd) | **delivery-share, not cycle cost**; LSD share is the remainder |
| `uopCache_MPKI` | 1000·`frontend_retired.any_dsb_miss`/instr | retired instructions whose fetch missed the DSB (precise) |
| `tma_dsb_switches_pct` | 100·`dsb2mite_switches.penalty_cycles`/cycles | cycle cost of DSB→MITE switches (perf's TMA numerator) |
| `ms_switches_PKI` | 1000·`idq.ms_switches`/instr | event rate (switches into microcode), not a cycle cost |

Window↔command tagging is heuristic (priority tagger, Report 04 D5); fence membership and all
counts are exact kernel/cgroup accounting (Report 03). LCP remains the one un-captured
fetch-latency child (Report 04 D4). A window is not a call (quantified in Report 04 D3).

### 2.2 Verification and hazards

- **Cross-group agreement**: three independent groups rank the tasks identically —
  `fe_lat`'s iCache stalls (5.29 / 5.57 / 0.04 % cyc for astropy/sympy/scikit tool medians),
  `fe`'s DSB share (55.6 / 59.4 / 85.7 %), and `fe_miss`'s µop-cache MPKI (62.6 / 52.8 / 19.6).
  No single-counter artifact can produce that concordance.
- **Consistency with the episode-level record**: the family explains Report 02's TMA-L2 verdict
  (astropy/sympy frontend split ≈ evenly fetch-latency/fetch-bandwidth; scikit core-bound) by
  naming the L3 children: iCache stalls + DSB switches, not iTLB.
- Sample sizes per metric (digest of the CSVs): tool fence n = 56–58 (scikit) / 107–114
  (astropy) / 111–114 (sympy) windows; harness n = 19–20 / 47–48 / 104–107. The scikit harness
  sample is small and its IQRs wider — its harness medians are quoted with that caveat.
- Operational hazards (ISO-PROOF vs teardown drain, self-interference at gate instants, the
  `GROUPS` bash-reserved-variable trap, matplotlib 3.11 API) are Report 04 §2.2; nothing new
  was hit for this family.

### 2.3 Reproduction recipe

```bash
cd local_agents/kit
# capture: only the four frontend groups (per task ~4 dedicated replay passes, no API cost;
# completed passes are skipped, re-run to sweep ISO-PROOF aborts)
PROF_GROUPS="fe_lat fe fe_l3x fe_miss" SHORT=scikit-learn SRC=1 \
DATA_ROOT=$HOME/InferSuite/local_agents/superseded_40min/data ./replay_l3_profile.sh
# (astropy: SHORT=astropy SRC=2 ; sympy: SHORT=sympy SRC=2)

# analysis: long-format CSVs + box/timeline figures for both fences
python3 analyze_l3_windows.py $HOME/InferSuite/local_agents/superseded_40min/data scikit-learn --plot
python3 cross_task_grid.py          # cross-task grids (tool + harness)
python3 build_metric_gallery.py     # self-contained per-task HTML gallery
```

Numbers in this report are per-task tool/harness medians (+IQR) and per-tag medians computed
from `local_agents/superseded_40min/data/l3_study/all_windows_<task>.csv` (2,497 / 5,030 /
7,064 data rows for scikit-learn / astropy / sympy). Expect phenomena and rankings to
reproduce, not exact values (replays re-execute real commands on live hardware).

### 2.4 Scripts and artifacts (scripts in `local_agents/kit/`; data under `local_agents/superseded_40min/data/l3_study/`)

| Item | Location | Role |
|---|---|---|
| `run_glm_campaign.sh` | GRP table :48–60 | event lists for `fe`, `fe_lat`, `fe_l3x`, `fe_miss`; replay stage |
| `replay_l3_profile.sh` | same dir | pass orchestrator (dedicated group + tagger + skip/retry) |
| `analyze_l3_windows.py` | `derive()` :102–139 | formulas above; CSVs; `box_/hbox_/timeline_/htimeline_` figures |
| `cross_task_grid.py` | same dir | `plots/cross_task_grid_{tool,harness}.png` |
| `build_metric_gallery.py` | same dir | `gallery_<task>.html` (published; URLs in deck slide 23) |
| `events.md` | same dir | event → metric → formula reference; co-counted-denominator rule |
| family figures | `l3_study/plots/` | 10 metrics × 3 tasks × 4 views (tool/harness box + timeline) = 120 of the study's ~400 figures |

## 3. Key insights (most → least important)

1. **The frontend problem is the µop cache, and it is two different diseases.** Tool-fence
   µop-cache MPKI: astropy 62.6, sympy 52.8, scikit 19.6; DSB delivery share is the inverse
   (55.6 / 59.4 / 85.7 %, with MITE picking up 41.4 / 39.2 / 11.6 %). astropy's pressure is
   **command-structured** — pytest windows at 23.3 code-read MPKI vs 7.9 in other-python
   windows (test-suite instruction footprint); sympy's is **uniform** — every tag sits at
   18.5–26.3 MPKI, overall IQR 18.4–22.8 (interpreter churn is the workload itself). Same
   symptom, different remediation targets.
2. **DSB→MITE switching is a first-order cycle cost on the Python-heavy tasks**: switch
   penalties are 6.9 % (astropy) / 6.5 % (sympy) of cycles — the same magnitude as their
   iCache data stalls (5.3 / 5.6 %) — vs 1.1 % on scikit. On astropy's pytest windows the
   measured fetch-latency children stack as iCache 6.9 % + DSB switches 6.8 % of cycles.
3. **iTLB is ruled out on both views, everywhere**: tag-lookup stalls ≤ 1.3 % of cycles at the
   task median (worst tag: astropy pytest 2.1 %) and walk-active ≤ 0.45 % median (worst tag
   0.70 %). Instruction-TLB is off the suspect list for the fetch-latency bound on all three
   tasks.
4. **scikit-learn's instruction supply is a solved problem except at command startup**: median
   code-read 1.08 MPKI, pytest windows 0.85 (hot OpenBLAS loops fit L1I), iCache stalls
   0.04 % of cycles — but python-other (startup) windows jump to 4.8 MPKI median with spikes
   to 16–30 (`analysis.md` Part 6). Its low episode average is pytest-weighted, not
   mix-representative.
5. **The harness fence is tight and task-independent on every delivery metric** — µop-cache
   MPKI 17.4 / 13.7 / 13.8 (scikit/astropy/sympy), DSB share 79.6 / 85.3 / 86.7 %, DSB-switch
   penalties 6.0 / 5.5 / 5.0 % of cycles, MS switches ≈ 1.0 PKI everywhere. Per-window
   confirmation that the agent program's frontend profile belongs to the agent, not the task
   (caveat: scikit harness n = 19–20 windows, wider IQRs; its code-read median 6.4 MPKI vs
   2.5 / 1.7 reflects that small, different-phase sample).
6. **On astropy/sympy the harness out-delivers the tools**: harness DSB share (85.3 / 86.7 %)
   exceeds every tool-side tag on those tasks — the "plumbing" is more frontend-friendly than
   the payload it launches.
7. **Microcode involvement is small everywhere but patterned**: scikit's tool fence has the
   highest MS delivery share (2.3 % vs 1.2 / 1.5 %) and switch rate (7.9 PKI); python-other
   startup windows carry ~18 MS switches/KI on both scikit and astropy — microcode churn is
   largely a process-startup phenomenon, never a dominant cost.

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

**Method update (2026-08-04, litellm venv relocation).** `run_glm_campaign.sh` changed after
this report: the litellm proxy is now launched from `local_agents/kit/campaign/.venv_litellm`
(the identical venv, moved out of the removed `agentic/openclaw/` tree; exact pins recorded in
`litellm_venv_freeze.txt`, verified by preflight). The proxy's role, cgroup fencing, and CPU
placement are byte-for-byte unchanged — nothing in this study's data or analysis is affected.
