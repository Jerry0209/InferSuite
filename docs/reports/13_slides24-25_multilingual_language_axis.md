# Report 13 — Multilingual per-window study: the language axis (deck slides 24–25)

**Date of study:** 2026-07-29 · **Author of record:** Tianrui (Jerry), with Claude Code
**Deck slides:** 24 (tool fence, 5-task language grid), 25 (harness fence + per-language timelines)
**Method baseline:** Report 04 (capture) · **Boundary/tagging audit:** Report 03 ·
**Metric families:** Reports 09–12 · **Cross-campaign reproducibility:** Report 08

---

## 1. Key summary

Every per-window result so far came from Python tasks, leaving open whether the
instruction-supply story was a CPython artifact. This study extends the identical per-window
method along the **language** axis using **SWE-bench Multilingual** instances:
**babel (JavaScript**, V8/Node) and **fmt (C++**, gcc/clang). Both are already banked with
trajectories in the certified SWE_clean campaign, so deterministic replay profiled them at
**zero API cost** — 22 dedicated-group passes (11 per language), 4,356 window-metric rows.

**The instruction-supply pressure is not a Python artifact.** babel carries the *highest* L1I
pressure measured anywhere in the study (median 20.8 code-read MPKI, 7.5 % of cycles stalled
on iCache) and fmt is comparable to the Python interpreters (16.1 MPKI, 5.3 %). Both also
reach main memory more than any Python task (TMA DRAM-bound 7.6 % and 5.6 % vs 0.0–4.7 %),
and both mispredict like the interpreters (branch MPKI 4.7 / 4.5, direction-dominated).
scikit-learn remains the lone outlier — the only vector-FP workload (60 %) and the only task
with near-zero L1I pressure. The harness fence stays tight and **language-independent**
(IPC 2.81–2.95, DSB 83–85 %, L1I ≈ 3–4 MPKI) whether it drives a Python, JavaScript or C++
repair: what the language changes lives entirely inside the tool fence. One blocking
environment bug had to be fixed first (§2.2) — replaying another workstation's trajectory
fails until its embedded tool-bundle paths are localized.

## 2. Methodology

### 2.1 Design decisions

Capture method is Report 04's unchanged (dedicated-group deterministic replays via
`GORDER_OVERRIDE`, `WINSEC=2`, 2 Hz host-side command tagger, zero multiplexing, 11 counter
groups). Decisions specific to this study:

| Decision | Value | Why |
|---|---|---|
| Language instances | babel-15445 (JavaScript), fmt-3248 (C++) | The only SWE-bench **Multilingual** instances with banked trajectories in this repo (certified SWE_clean). Real multilingual benchmark tasks, not proxies |
| Data source campaign | `local_agents/SWE_clean/data` (certified) | Their trajectories exist nowhere else. The 3 Python tasks stay on `superseded_40min` — mixing is acceptable **because** per-window microarch shares are the layer proven to reproduce across campaigns (Report 08: TMA within 1–5 pt), and every figure states the provenance in its footer |
| Featured source runs | babel run_1, fmtlib run_1 | Both are the certified `plot_spec.json` featured runs (clean, swebench-RESOLVED) — so the replayed command stream is the one the thesis figures already describe |
| Trajectory localization | `localize_traj.py` → `*.local.traj`, passed via `TRAJ_OVERRIDE` | **Mandatory** for foreign trajectories (§2.2). Writes a *copy*: the banked `.traj` is measurement evidence and is never mutated |
| Same 11 groups, same `WINSEC` | unchanged from Reports 04/09–12 | Any metric difference must be attributable to the workload, not to instrumentation |
| Cost | 0 API tokens, ~2 h wall (incl. sweeps) | Replays call no model; both docker images were already local |

### 2.2 Verification and hazards

**Hazard 1 — foreign trajectories cannot be replayed as-is (new finding, blocking).** All
babel passes died ~3 s in with `ERROR: no sandbox for replay`. The real error is in the
replay's own `agent.log`:

```
PermissionError: [Errno 13] Permission denied:
  '/home/mohamad/llm-service-kernel-latest/agentic/swe_agent/external/SWE-agent/tools/registry'
```

A `.traj` embeds the **absolute tool-bundle paths** of the machine that recorded it (here
three: `registry`, `edit_anthropic`, `review_on_submit_m` under `replay_config`).
`sweagent run-replay` validates those paths at startup, so a trajectory recorded on another
workstation aborts before the sandbox launches. The Python tasks never hit this because their
trajectories came from this machine's own campaign. Fix (all in-repo): `localize_traj.py`
rewrites the foreign repo-root prefix into a `*.local.traj` copy and validates the JSON;
`TRAJ_OVERRIDE` in `run_glm_campaign.sh` selects it explicitly, and the default glob now
excludes `*.local.traj` so it cannot non-deterministically pick either file. Verified by a
single-pass smoke test (`REPLAY RUNNING` → `EPISODE-OK`, 21 windows) before committing to the
full campaign. **Any cross-machine replay needs this** — worth knowing before reproducing.

**Hazard 2 — ISO-PROOF vs docker teardown drain** (as in Report 04 §2.2): 6 of 22 passes
aborted because the previous sandbox's teardown was still draining at the quiet-check instant.
Re-running the wrapper skips completed passes (`l3group.txt` + `DONE`) and recaptures only the
failures; a two-round sweep brought both languages to **11/11**. Nothing dirty enters the
data — the gate refuses to capture rather than capturing noise.

**Validity checks:** window floors (< 5×10⁵ fence instructions dropped) unchanged; per-pass
window counts differ by language and are reported with every median (babel ≈ 20/pass — a
~40 s replay; fmtlib ≈ 65–101/pass — C++ compilation is genuinely long-running). Command tags
are the independent live-process mechanism, and they behaved as the workloads predict:
fmtlib's dominant class is **`compile` (49 of 66 windows)** — the first task in the study
where compilation dominates — while babel's work arrives as short `shell`-driven bursts
(17 of 20 windows). **Read babel's `shell` share with the tagger caveat** (Report 14 §2.3):
`tag_of()` has no `node`/`jest`/`yarn`/`npm` rule and `TAG_PRIORITY` ranks `shell` above
`other`, so babel's four jest invocations are labelled `shell` rather than a test class. Its
*absence of compile* is a real workload property; its absence of a test class is a labelling
artifact. Metric values per window are unaffected.

**Known limitations:** (a) one clean run per language, so no per-language dispersion band;
(b) cross-campaign provenance (stated on every figure) — the shares are comparable, absolute
wall/core-seconds across campaigns are not (Report 06); (c) window ≠ call (Report 04 D3);
(d) `codeRead_MPKI_L1I` remains an L1I-pressure **proxy**, `AMAT` a fixed-latency model,
`dram_bw_bound` an occupancy not a stall.

### 2.3 Reproduction recipe

```bash
cd local_agents/kit
DR=$HOME/InferSuite/local_agents/SWE_clean/data
G="fe_lat fe fpbr cache mlp core_ports dram_bw mem_bound fe_l3x priv fe_miss"

# 1. localize the foreign trajectory (prints the path to replay; banked .traj untouched)
python3 localize_traj.py $DR/glm_swe_babel/run_1/traj/babel__babel-15445/babel__babel-15445.traj

# 2. capture 11 dedicated-group passes (~35 min/language, no API cost)
TRAJ_OVERRIDE=$DR/glm_swe_babel/run_1/traj/babel__babel-15445/babel__babel-15445.local.traj \
PROF_GROUPS="$G" SHORT=babel SRC=1 DATA_ROOT=$DR ./replay_l3_profile.sh
#   fmtlib: SHORT=fmtlib, TRAJ_OVERRIDE=.../fmtlib__fmt-3248.local.traj
#   re-run the same command to sweep ISO-PROOF-aborted passes (completed ones are skipped)

# 3. analyze + figures + the 5-task language grid + galleries
python3 analyze_l3_windows.py $DR babel  --plot     # and fmtlib
python3 cross_task_grid.py                          # auto-includes any language whose CSV exists
python3 build_metric_gallery.py --plots $DR/l3_study/plots --out <dir> babel fmtlib
```

Data layout per pass is Report 04's, under `SWE_clean/data/glm_replay_swe_<task>/run_N/`.
Fence naming for parsers: harness cgroup contains `glm-rep`, tool contains `docker-`.

### 2.4 Scripts and artifacts

| Item | Location | Role |
|---|---|---|
| `localize_traj.py` | `local_agents/kit/` | **new**: rewrites foreign tool-bundle paths into a `*.local.traj` copy |
| `run_glm_campaign.sh` (`TRAJ_OVERRIDE`, `replay-one`) | same dir | **extended**: explicit trajectory selection; glob excludes localized copies |
| `replay_l3_profile.sh` | same dir | pass orchestrator (passes `TRAJ_OVERRIDE` through) |
| `analyze_l3_windows.py` | same dir | windows × counters × tags → CSVs + per-metric figures (both fences) |
| `cross_task_grid.py` | same dir | **extended**: 5-task language axis, per-task data roots, provenance footer, `GRID_OUT` |
| `build_metric_gallery.py` | same dir | per-language galleries (33 metrics × 4 views: tool box, harness box, tool timeline, harness timeline) |
| Raw passes | `local_agents/SWE_clean/data/glm_replay_swe_{babel,fmtlib}/run_1..11/` | 11 groups each; `l3group.txt` names the group per run |
| CSVs | `local_agents/SWE_clean/data/l3_study/all_windows_{babel,fmtlib}.csv` (1,306 + 3,050 rows), `tma_intervals_*.csv` | all values, plot-agnostic |
| Figures | `.../l3_study/plots/` (262 files) + `superseded_40min/.../plots/cross_task_grid_{tool,harness}.png` | per-language + 5-task grids |
| Galleries | published artifacts (linked on deck slide 25) | browsable per-metric sets |

## 3. Key insights (most → least important)

1. **Instruction-supply pressure generalizes across languages — it is not a CPython
   artifact.** babel (JavaScript/V8) has the highest L1I pressure *of the tasks in this report*
   (20.8 MPKI, 7.5 % iCache stall cycles, µop-cache 61.5 MPKI) and fmt (C++) is comparable to
   the Python interpreters (16.1 MPKI, 5.3 %, 47.1). Only scikit-learn escapes it (1.1 MPKI,
   0.04 %). The earlier "large, fragmented hot-code footprint" story is therefore a property
   of *agent tool workloads* broadly, not of one interpreter.
   **Superseded as the maximum (2026-07-29):** the Rust language pilot (tokio, `ML_multiling`)
   is worse than every task here — L1I code-read **30.7** MPKI, µop-cache **83.9** MPKI, DSB
   coverage **43.5 %** (lowest measured), legacy decode **53.1 %** (highest). So the claim
   "babel is the highest" holds only within slides 24–25; the generalization it supports is
   *strengthened*, since the extreme now belongs to an ahead-of-time optimising compiler rather
   than to any interpreter or JIT.
2. **The harness fence is language-independent, per-window.** Across all five tasks the
   harness sits at IPC 2.81–2.95, DSB 83–85 %, L1I ≈ 3–4 MPKI, branch ≈ 1.0–1.4 MPKI. This
   extends the earlier task-independence result (Report 08) to a *language* axis: the agent
   program's microarchitectural profile belongs to the agent, and only the tool fence changes.
3. **The multilingual tasks reach main memory more than any Python task**: TMA DRAM-bound
   7.6 % (JS) and 5.6 % (C++) of cycles vs 0.0 % (scikit), 1.6 % (astropy), 4.7 % (sympy) —
   with LLC MPKI still small (0.18 / 0.14), i.e. fewer but costlier misses on the critical
   path rather than bulk streaming.
4. **JavaScript is the branch-predictor stress case**: babel carries the highest BTB-miss
   proxy in the study (BAClears 1.56 MPKI vs 0.69 C++ and 0.2–0.6 Python) at branch
   MPKI 4.67 (direction-dominated: cond 4.03). Consistent with V8's polymorphic dispatch and
   inline-cache churn — a hypothesis this data supports but does not prove.
   **Quantified and re-tagged (Report 15):** the JS attribution is now measured, not assumed —
   **77–78 % of babel's tool-fence instructions** are in windows running jest/node/yarn (two
   independent methods agree), and the extended tagger puts the elevation in the right rows
   (`tests(js)` ≈ 1.6, `node-other` 1.75, vs `compile` 0.75 and `git` 0.2). Two candidate
   mechanisms (concurrent-PID and exec-rate churn) were tested and **rejected**, so the gap
   stays descriptive. Caveat sharpened: babel's fence is the smallest measured (190 Ginstr/pass,
   20 windows) and its IQR overlaps fmt's, so "babel > fmt" is **not** resolved.
5. **C++ is the first compile-dominated task**: the live tagger assigns `compile` to 49 of
   66 windows (IPC 1.86) versus `shell` 12 (IPC 1.44) — the per-command structure the language
   axis was expected to expose, and a workload class absent from the Python tasks. Weighted by
   instructions this is 97 % `compile` in **every** pass (Report 15), making fmt the clean
   language-axis case. babel's composition was mislabelled until the tagger gained JS rules;
   it is now `tests(js)` 77 % / shell 12 % / git 8 % (was shell 80 % / git 16 %).
6. **Deterministic replay makes the language axis nearly free** — 22 passes, 0 API tokens,
   using trajectories already banked. Extending to more of SWE-bench Multilingual (Ruby, Go,
   Java, PHP, Rust) needs only live episodes to produce trajectories once; the profiling
   afterwards is free and repeatable.
7. **Foreign trajectories are not portable without localization** (§2.2) — a reproducibility
   trap that silently presents as "no sandbox". Now fixed in-repo and documented; it also
   implies that *any* archived campaign from another machine is replayable here, which widens
   what can be profiled at zero cost.
