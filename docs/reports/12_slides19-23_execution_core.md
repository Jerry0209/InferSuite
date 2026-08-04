# Report 12 — Per-window metric group: execution core & system (deck slides 19–23)

**Date of study:** 2026-07-28 · **Author of record:** Tianrui (Jerry), with Claude Code
**Deck slides:** 19–23 (per-window study slides + the three per-task galleries; execution-core
panels of the 12-metric grids)
**Longer prose version:** [`../handwritten_notes/analysis.md`](../handwritten_notes/analysis.md), Parts 4 + 6 · **Capture method:** Report 04 ·
**Companion metric-group reports:** 09–11 (frontend supply, branch/speculation, memory)

---

## 1. Key summary

This report covers the **execution-core and system** slice of the per-window study: IPC,
the dispatch-width ("ports") cycle profile, divider activity, scalar-vs-vector FP mix, and
kernel-mode share — per 2-second window, per fence, tagged by the command executing. Capture
is Report 04's: deterministic replays of the three featured episodes, one counter group
dedicated per pass (`GORDER_OVERRIDE`, zero multiplexing), 2 s windows, 2 Hz host-side
command tagger, all values banked to `all_windows_<task>.csv` before plotting. Headlines:
scikit-learn's IPC is **bimodal** (pytest windows 0.61 vs everything else ≥ 1.1) and its
pytest windows spend ≈ 71 % of cycles at ≤ 2-port dispatch width (0-ports 27.0 / 1-port
27.8 / 2-ports 16.5 % of cycles) — the cycle-level face of the census's BE·core 28.3 % of
slots — while **vecFP ≈ 60 %** marks those same windows as the OpenBLAS/FMA phase (astropy
0.13 %, sympy 0.00 % median: a one-metric task classifier). The divider is negligible
everywhere (median ≤ 0.08 % of cycles). Kernel share is phase-structured: compute phases run
almost entirely in user mode (pytest windows 2.7–9.6 % kernel) while command-startup windows
are kernel-heavy (astropy python-other 63.7 %). One caveat is load-bearing enough to headline:
the ports events are a **raw execution-width cycle profile, not a core-bound decomposition**
(§2.2).

## 2. Methodology

Capture, tagging, and CSV schema are Report 04's (replays × dedicated groups × 2 s windows ×
2 Hz tagger); this report only reads the banked CSVs plus one raw pass. Everything below is
specific to the execution-core/system metrics.

### 2.1 Metrics, events, and decisions

| Decision | Value | Why |
|---|---|---|
| IPC source | `instructions/cycles` co-counted in the `fpbr` group's own windows | co-counted denominators — the kit's rule against cross-group ratio dilution |
| Ports profile | `exe_activity.exe_bound_0_ports / 1_ports_util / 2_ports_util` + `arith.div_active`, each as % of the window's cycles (`core_ports` group) | the measured "core-bound children" candidates; % cycles is the exact-count analogue of the TMA drill |
| Ports presented **un-nested** (never under BE·core) | locked by the `PANELS3` note in `plot_glm_results.py` | these events count ALL cycles at that dispatch width regardless of what TMA blames the cycle on (§2.2) |
| vecFP_pct | `100·vector/(scalar+vector)` from `fp_arith_inst_retired.{scalar,vector}` (`fpbr` group), only when scalar+vector > 10⁴ | share of retired FP ops that are vector — the SIMD/FMA fingerprint; the gate keeps the ratio stable (harness windows never pass it → no harness vecFP rows exist) |
| kernel_pct | `100·cycles:k/(cycles:k+cycles:u)` per fence-window (`priv` group), gate k+u > 10⁵ | exact privilege-split cycle accounting = the "OS share" per phase |
| Window admission | fence instructions ≥ 5×10⁵ per window | Report 04's stability gate |
| Median/quartiles per tag, never pooled means | study convention | distributions are the point; means re-hide the bimodality |

Group event lists are in `run_glm_campaign.sh` (`GRP[fpbr]`, `GRP[core_ports]`,
`GRP[priv]`); derivations in `analyze_l3_windows.py::derive()`.

### 2.2 Honest labels, verification, and one pipeline gap

- **The ports caveat (critical).** The ports-utilization events count **all** cycles with
  exactly N ports busy, whatever TMA blames the cycle on — a raw execution-width cycle
  profile, **not** children of the core-bound parent. The reconciliation of 2026-07-15 made
  this concrete: the three children sum to 19–29 % of cycles while the TMA core-bound parent
  is 7–8 % of slots on the same fences. The kit's episode-sum figure therefore titles the
  panel "cycle profile, not parent-nested" (`plot_glm_results.py`, `PANELS3`); this report
  keeps that framing for the per-window data. Do not present ports numbers as a core-bound
  decomposition.
- **Exact vs heuristic.** Counted cycles/instructions per fence-window are exact
  (kernel-cgroup-scoped, zero-mux); kernel_pct's privilege split is exact hardware counting.
  The command *tag* on each window is the heuristic layer (2 Hz poll + priority rule,
  audited in Reports 03/04). Small-n tags are quoted with their n (scikit pkg/build n=2,
  shell n=3).
- **IPC is not usefulness.** Locked study rule (also on deck slide 15): high IPC/retiring
  does not certify useful work; §3.2 is this report's demonstration.
- **kernel_pct pipeline gap (found during this report).** The `priv` passes exist and are
  DONE (`run_10` of each task), and `analyze_l3_windows.py` has the kernel_pct derivation
  (≈ line 140) — but the CSVs contain **zero** priv rows: the analyzer's shared gate reads
  the *unsuffixed* `instructions`/`cycles` events, which the priv group does not emit (it
  counts `:u`/`:k` variants only), so every priv window is dropped as "too little activity".
  The kernel numbers in §3 were recomputed directly from the banked raw
  `run_10/group_priv_w*.txt` files with the analyzer's own formula and equivalent gates
  (`instructions:u+:k ≥ 5×10⁵`, `cycles:k+:u > 10⁵`) and the analyzer's own tagging
  functions. Until the gate is fixed, `all_windows_<task>.csv` cannot be the kernel_pct
  source; the raw pass files are.
- **Cross-checks.** Per-tag medians recomputed independently from the CSVs match
  `analysis.md` Part 6's quoted values (pytest IPC 0.61-vs-"0.62", pkg/build 1.92-vs-"1.9");
  the scikit ports/vecFP story agrees with two independent instruments — the continuous TMA
  census (BE·core 28.3 %, Ret·heavy 22.1 % of slots; Report 02) and the episode-sum
  signature (Part 4).

### 2.3 Reproduction recipe

```bash
cd local_agents/scripts/glm
# capture only the three groups this report uses (~10 min/task, no API cost; see Report 04
# for the full 11-group sweep, serialization, and ISO-PROOF retry behavior)
PROF_GROUPS="core_ports fpbr priv" SHORT=scikit-learn SRC=1 \
DATA_ROOT=$HOME/InferSuite/local_agents/superseded_40min/data ./replay_l3_profile.sh
# (astropy: SHORT=astropy SRC=2 ; sympy: SHORT=sympy SRC=2)

python3 analyze_l3_windows.py <DATA_ROOT> scikit-learn --plot   # CSVs + box/timeline figures
python3 cross_task_grid.py && python3 build_metric_gallery.py   # grids + per-task galleries
```

kernel_pct until the analyzer gate is fixed: parse
`<DATA_ROOT>/glm_replay_swe_<task>/run_*/group_priv_w*.txt` (the run whose `l3group.txt`
reads `priv`), sum `cycles:k`/`cycles:u` per fence per window (fence match: harness cgroup
contains `glm-rep`, tool contains `docker-`), apply the gates above, and tag windows from
that run's `cmdlog.tsv` with `analyze_l3_windows.py`'s `tag_of`/`tag_for`. Deterministic
replays: phenomena and medians reproduce; exact window counts may shift by ±a few windows.

### 2.4 Scripts and artifacts

| Item | Location | Role |
|---|---|---|
| `replay_l3_profile.sh` / `run_glm_campaign.sh` | `local_agents/scripts/glm/` | pass orchestration; `GRP` table (`fpbr`, `core_ports`, `priv` event lists) |
| `analyze_l3_windows.py` | same dir | metric derivations incl. IPC/ports/vecFP/kernel; CSVs; box/timeline figures |
| `cross_task_grid.py`, `build_metric_gallery.py` | same dir | 12-metric grids; per-task HTML galleries |
| `plot_glm_results.py` | same dir | episode-sum L3/L4 drill; the locked `PANELS3` ports caveat |
| `all_windows_<task>.csv` | `local_agents/superseded_40min/data/l3_study/` | source of truth for IPC/ports/divider/vecFP rows |
| `run_10/group_priv_w*.txt` + `cmdlog.tsv` | `…/data/glm_replay_swe_<task>/` | kernel_pct source (see §2.2 gap) |

Galleries, grids, and CSV set are the same artifact family as Report 09 (frontend-supply
metrics) — one gallery per task, four views per metric (tool and harness distributions, then
each fence's over-the-episode timeline).

## 3. Key insights (most → least important)

1. **scikit-learn's backend limit, seen at cycle level: ≈ 71 % of pytest-window cycles sit at
   ≤ 2-port dispatch width** (sum of medians: 0-ports 26.96, 1-port 27.84, 2-ports 16.45 %
   of cycles; whole tool fence 26.63/27.71/16.43). This is the per-window face of the
   census's BE·core 28.3 % of slots with memory-bound only 6.1 % (Part 4 / Report 02):
   OpenBLAS is throttled by execution ports and dependency chains, not DRAM. Astropy/sympy
   barely register 0-port binding (medians 1.90/1.80 %) — their cycles are lost in the
   frontend instead (Reports 09/10). Caveat from §2.2 always applies: this is a width
   profile, not a core-bound decomposition (children 19–29 % cyc vs parent 7–8 % slots).
2. **IPC anti-correlates with the "useful work" intuition — the study rule demonstrated.**
   scikit's *dense vector work* is the LOW-IPC mode: pytest windows at median 0.61 with
   vecFP ≈ 60 % (few, heavy, port-bound FMA µops), while interpreter-dominated tags retire
   many cheap instructions fast (scikit pkg/build 1.92 (n=2), python-other 1.10; astropy
   pytest 1.77, compile 2.11; sympy pytest 1.97; harness up to 3.18). IPC never certifies
   usefulness in this study — high IPC here mostly means "CPython churning".
3. **Distribution shapes (IPC): scikit bimodal, the others tight-ish.** scikit tool fence
   p25 = 0.60 / p75 = 1.11 around a median of 0.62 — two modes, not spread; astropy
   1.53–2.19 and sympy 1.46–1.94 quartile bands with all tags inside 1.4–2.1. The famous
   "scikit IPC = 0.64" episode average is just pytest's instruction weight (Part 6).
4. **vecFP is a one-metric workload classifier.** Median share of retired FP ops that are
   vector: scikit tool 59.95 % (pytest 60.12, python-other 0.86) vs astropy 0.13 % and
   sympy 0.00 %. Only scikit's test suite touches SIMD/FMA — consistent with its
   Ret·heavy 22.1 % of slots in the census. The harness never emits a vecFP row (below the
   10⁴ FP-op gate in every window): the agent program does effectively no FP.
5. **Kernel share is phase-structured, not a constant tax.** Tool-fence medians: scikit
   9.0 %, astropy 11.6 %, sympy 14.3 % of cycles in kernel mode — but the spread is the
   story (astropy p25 1.7 / p75 48.4): long compute phases are user-mode (pytest windows:
   astropy 2.7 %, scikit 8.8 %, sympy 9.6 %) while short-command/startup windows are
   kernel-heavy (astropy python-other 63.7 %, shell 29.1 %; scikit python-other 41.1 %;
   sympy shell 24.8 %) — fork/exec/page-fault process management, the mirror of Report 04's
   L1I-startup spikes. Harness kernel share is modest and stable: 6.8/9.8/8.1 %.
6. **The harness's execution-core profile is task-independent, per-window.** Median IPC
   2.76/3.18/2.74 (scikit/astropy/sympy; episode-level signature said 2.4–2.9 across both
   campaigns), 0-port binding ≈ 1 %, kernel ≈ 7–10 % — the execution-core confirmation of
   the "harness is one program" result (Report 04, insight 5).
7. **The divider is ruled out everywhere**: `arith.div_active` median ≤ 0.08 % of cycles on
   every task and fence; worst single window 1.72 % (astropy). No division story exists in
   these workloads.
8. **A dead derivation is a silent data gap**: kernel_pct was captured, derivable, and
   absent — the analyzer's shared instruction gate keyed on an event name the priv group
   doesn't emit (§2.2). Gate checks must key on the events each group actually counts;
   until fixed, kernel numbers come from the raw pass files.

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

---

**Method update (2026-07-30, evening).** `plot_glm_results.py` changed after this report: the
harness-anatomy figure's cost-dynamics row had a hardcoded 1×4 sub-grid and crashed on specs
with 5+ tasks — silently, because every preceding figure (including all of this report's) had
already been written. The grid now scales with the task count. No figure this report documents
changes in content; the fix exists so the mentor-requested 5- and 6-task cross-campaign
variants (`local_agents/cross_campaign/`, report 14) render completely.

---

**Method update (2026-07-30, late).** `analyze_l3_windows.py` gained cache **miss-rate**
metrics (and `cross_task_grid.py` a `GRID_LAYOUT=16` rearranged grid) on the mentor's request —
additive only; every number this report documents is unchanged. Details: report 11's note.

**Method update (2026-08-04, litellm venv relocation).** `run_glm_campaign.sh` changed after
this report: the litellm proxy is now launched from `local_agents/scripts/glm/.venv_litellm`
(the identical venv, moved out of the removed `agentic/openclaw/` tree; exact pins recorded in
`litellm_venv_freeze.txt`, verified by preflight). The proxy's role, cgroup fencing, and CPU
placement are byte-for-byte unchanged — nothing in this study's data or analysis is affected.
