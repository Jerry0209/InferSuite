# Report 05 — Featured reproduction results (deck slides 1–6)

**Date of study:** 2026-07-24 · **Author of record:** Tianrui (Jerry), with Claude Code
**Deck slides:** 1 (framing) – 6 (takeaways): wall-clock split, CPU work, timelines, tool-call
structure for one featured episode per task
**Longer prose version:** [`../handwritten_notes/analysis.md`](../handwritten_notes/analysis.md), Part 1
(+ Part 5 for the django@0.6 column) · django@0.6 experiment itself: Report 01 · boundary/burst
definitions: Report 03

---

## 1. Key summary

The question behind slides 1–6: what do Mohamad's headline figures look like when the
superseded 40-minute campaign (GLM-5.2 driving SWE-agent on scikit-learn / astropy / sympy /
django, temperature 0.0, 3 episodes each, isolated 20-core partition) is re-captured from
scratch — and how is "one representative episode per task" selected, rendered, and proven
faithful? Method in one sentence: a 5-entry `plot_spec.json` names one clean (or honestly
tagged) run per task, the certified spec-driven plotters render the four featured figures and
bank every displayed number in `values_dump.json`, and `audit_plots.py` independently recomputes
each number from the raw captures (verdict: ALL MATCH). Headline: elapsed time is model-wait
everywhere (74–94 % of wall), but CPU work is task-dependent — scikit-learn burns 1,449 core-s
at ~100 % tools while sympy inverts to 53 % harness — and a stuck agent has a recognizable CPU
signature (django's temp-0 loop: 486 core-s at 89 % harness, 383 calls of which only 4 are
heavy).

## 2. Methodology

### 2.1 Load-bearing decisions

| Decision | Value | Why |
|---|---|---|
| Never pool runs; feature ONE episode per task | spec `resolved`: scikit-learn r1, astropy r2, sympy r2, django r2, django@0.6 r1 | CLAUDE.md's locked rule (median/representative run, spread documented separately): pooling blends episodes that differ 2–3× and makes single-episode figures uninterpretable. Run-to-run spread is shown on the all-24-runs slides (7–12), not here. |
| Clean-vs-looped classification | looped = ≥ 8 of the last 12 actions identical (heuristic; validator gate E7 is the formal version) | temp-0 loops are real measurements of a *failure mode*, not of the task; featuring one would misrepresent the task profile. The clean run is featured where one exists. |
| django featured anyway, tagged | django r2 "(looped)", django@0.6 r1 "(submit-blocked)" | no clean django episode exists anywhere (Part 5 / Report 01 shows why); dropping the task would hide the finding, so the honest representative is shown with its outcome in the title. |
| Outcome tags rendered into figure titles | plotter `DISPLAY` map: `name (outcome)` unless outcome = "resolved", driven by the spec's `outcome` dict | figures are self-labeling — a looped episode can never be mistaken for a task profile once the PNG leaves the repo. |
| Side campaign gets its own data root | `DATA_ROOT=local_agents/superseded_40min/data` (kit default is `local_agents/data`) | keeps the reproduction physically separate from the certified thesis tree (`SWE_clean`) — otherwise one wrong `DATA_ROOT`/cleanup (`rm -rf`) can clobber thesis evidence. |
| Spec-driven plotting, certified defaults untouched | `PLOT_SPEC=<json>` overrides data/out/resolved/outcome only when set | both campaigns (his and ours) render through the *same* plotting code, so no observed difference can come from plotting changes; without `PLOT_SPEC` the certified behavior is bit-identical. |
| Audit before trust | `audit_plots.py` must end "ALL MATCH — figures faithfully represent the data" | repo convention: an OK line is not proof — every displayed number is independently recomputed from raw captures (per-number OK/FAIL with tolerance) before any figure is shown. |
| Collection and plotting decoupled | plot afterwards from banked data, with the `infersuite-full` conda env's `python3` | plotting never perturbs a capture; matplotlib lives in that env on this machine, not in the project `.venv`. |

### 2.2 What the featured figures show, and how the numbers were verified

Featured-episode numbers (from `values_dump.json`, audit-covered; shares as % of wall):

| Featured episode | wall (min) | wait / tools / harness (% wall) | CPU work (core-s) | calls (heavy · internal) | tool-active % of wall |
|---|---|---|---|---|---|
| scikit-learn r1 | 7.9 | 74 / 23 / 3 | 1,449 — 99.5 % tools | 67 (26 · 26) | 22.8 |
| astropy r2 | 36.7 | 89 / 9 / 2 | 265 — 88 % tools | 130 (58 · 12) | 9.3 |
| sympy r2 | 25.5 | 78 / 11 / 11 | 234 — 53 % harness | 238 (157 · 63) | 10.9 |
| django r2 (looped) | 40.8 | 74 / 5 / 21 | 486 — 89 % harness | 383 (4 · 2) | 5.1 |
| django@0.6 r1 (submit-blocked) | 36.5 | 94 / 3 / 4 | 78 — 58 % harness | 185 (64 · 57) | 3.0 |

Timelines (slide 4): scikit-learn's test bursts saturate the full 20-core partition; astropy is
spiky (peak ≈ 17 tool cores); sympy never exceeds ≈ 1 core on either fence; the django loop is a
solid 41-minute harness wall (up to ~6 cores) with tools flatlined.

Exact vs heuristic layers: fence core-seconds and the 10 Hz activity series are **exact** kernel
cgroup accounting; "calls" come from the trajectory, and "bursts"/"heavy" are the locked
heuristic vocabulary (floors 0.005 / 0.02 cores, gaps < 0.4 s merged, heavy = peak > 0.3 cores)
— definitions and the call↔burst join are audited in Report 03. The loop tag itself is a
heuristic text rule (above), backed by gate E7.

Verification: `plot_glm_results.py` writes `values_dump.json` with every displayed number;
`audit_plots.py` re-derives each from the raw per-run captures (`cpustat_scope*.tsv`, traj,
`windows.tsv`, `tma_cont.csv`) and prints per-number `plotted= recomputed= tol=` lines — this
featured set reports ALL MATCH. The wall-share chips were additionally re-derived by hand from
`tool_active_s` / `harn_active_s` / `wall_min` and agree after rounding.

Known hazards / limitations (stated, not fixed):
- astropy has a single clean episode — no dispersion band behind its featured run.
- Loop rate was luck, not settings (7/12 re-run episodes vs Mohamad's ~5/12); featured-run
  choices would differ on a fresh capture and `plot_spec.json` must be re-edited after
  re-classifying loops.
- The django@0.6 column comes from a different temperature (0.6, loop guard N = 12, ISO-PROOF
  quiet at 0.7 %, banked under a separate `glm-t06` config) — comparable in method, not a sixth
  temp-0 task; see Report 01.
- This campaign is *not* thesis scope (superseded 40-min reproduction); the thesis campaigns
  are `SWE_clean`/`OC_clean`.

### 2.3 Reproduction recipe

```bash
# Figures only — banked data, no capture, no spend
conda activate infersuite-full          # python3 that has matplotlib (never the project .venv)
cd ~/InferSuite/local_agents/scripts/glm
export PLOT_SPEC=$HOME/InferSuite/local_agents/superseded_40min/plot_spec.json
python3 plot_glm_results.py             # glm_time_split/cpu_work/timeline/tool_calls (+ rest) + values_dump.json
python3 plot_call_structure.py; python3 plot_internal_tools.py; python3 plot_calls_vs_bursts.py
python3 audit_plots.py                  # must end: ALL MATCH — figures faithfully represent the data

# Full re-capture (real API spend, ~2.5–4 h for 12 temp-0 episodes; single episode ~10–40 min)
DATA_ROOT=$HOME/InferSuite/local_agents/superseded_40min/data \
SWE_INSTANCES="scikit-learn__scikit-learn-25232 astropy__astropy-14096 sympy__sympy-14248 django__django-10097" \
  ./run_glm_campaign.sh campaign swe    # stages preflight→dryrun→smoke must have passed first
```

What should reproduce on a fresh capture: the shares, shapes, per-step costs, and CPU
composition. What will not: absolute minutes/core-seconds (2–3× episode-to-episode spread) and
the specific clean/looped outcomes — judge by shares and structure, never one episode's raw
numbers.

### 2.4 Scripts and artifacts (all in `local_agents/scripts/glm/` except the spec/dump)

| Item | Location | Role |
|---|---|---|
| `run_glm_campaign.sh` | kit dir | staged capture: isolation + ISO-PROOF gate, fences, four instruments, teardown |
| `plot_spec.json` | `local_agents/superseded_40min/` | featured-run selection (5 entries), outcome tags, data/out roots |
| `plot_glm_results.py` | kit dir | main spec-driven plotter (12 figures incl. the four featured ones) → `values_dump.json` |
| `plot_call_structure.py` | kit dir | per-class call-structure companion (`glm_call_structure.png`) |
| `plot_internal_tools.py` | kit dir | trajectory-anchored per-call CPU attribution (`glm_internal_tools.png`; method in Report 03) |
| `plot_calls_vs_bursts.py` | kit dir | calls-vs-bursts accounting (`glm_calls_vs_bursts.png`) |
| `audit_plots.py` | kit dir | recomputes every displayed number from raw → "ALL MATCH" |
| `values_dump.json` | `local_agents/superseded_40min/plots/` | every displayed number, banked next to the figures |

## 3. Key insights (most → least important)

1. **Elapsed time is model-wait everywhere; CPU work is not.** Wait is 74–94 % of wall in all
   five featured episodes, yet the core-second split flips per task (scikit-learn ~100 % tools
   → sympy 53 % harness). The two views tell opposite stories — always report both.
2. **A stuck agent has a distinct CPU signature**: django's temp-0 loop burned 486 core-s at
   89 % harness across 383 calls with only 4 heavy bursts and a continuous 41-minute harness
   wall — real cost with nothing to show for it, and instantly recognizable on a timeline.
3. **Task personality lives in the tool fence**: scikit-learn's three test bursts saturate all
   20 cores (1,449 core-s, 26 of 67 calls heavy); astropy spikes to ≈ 17 cores; sympy never
   exceeds ≈ 1 core — a trickle of 238 shallow calls.
4. **Temperature 0.6 turned django's cost profile into real work** — 78 core-s (≈ 6× cheaper
   than the 486–743 core-s loops) with 64 heavy bursts vs 4 — but the episode is
   "(submit-blocked)", not solved: the harness's submit tool crashes in this task's container
   (Report 01).
5. **Featured single episodes are only honest with the tagging + audit machinery around them**:
   outcome tags in every title via the spec-driven `DISPLAY` map, and no figure trusted before
   `audit_plots.py` reports ALL MATCH.
6. **A featured episode is one draw from a wide distribution** — absolutes swing 2–3× between
   attempts in the *same* campaign, so cross-campaign judgments belong to the all-24-runs
   comparison (deck slides 7–12), not to these five panels.
