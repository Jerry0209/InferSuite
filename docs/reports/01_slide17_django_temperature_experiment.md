# Report 01 — The django temperature-0.6 experiment (deck slide 17)

**Date of study:** 2026-07-27 · **Author of record:** Tianrui (Jerry), with Claude Code
**Deck slides:** 17 (also feeds the "django @0.6" column on slides 2–5)
**Longer prose version:** [`../handwritten_notes/analysis.md`](../handwritten_notes/analysis.md), Part 5 and "The temperature question"

---

## 1. Key summary

All six verifiable django-10097 episodes across both campaigns (Mohamad's certified 40-min
campaign and our reproduction) died in greedy-decode action loops at temperature 0.0. Following
the mentor's request, we ran **two fresh django episodes at temperature 0.6** with the loop
guard armed, to test whether the task becomes solvable.

Result: **django-10097 is unsolvable in this harness configuration at any temperature — but
not for the reason anyone assumed.** Episode 1 escaped the work-loops, did ~126 turns of real,
varied work, produced the *correct* fix (its one-line regex change to
`django/core/validators.py` matches the actual upstream Django patch), and then attempted to
submit **29 times** — every attempt crashed because SWE-agent's submit tool
(`review_on_submit_m/bin/submit`) uses f-string syntax that the task container's **Python
3.5.6** cannot parse. No patch can ever leave that sandbox. The greedy-decode loops of the
temp-0 campaigns had been *masking* this harness/environment incompatibility: no temp-0
episode ever survived long enough to reach submission. The failure is therefore two-layered
(decode loops → submit-tool bug), the second layer is a previously-unreported upstream
SWE-agent bug (still present in upstream `main` at the time of the study), and it silently
disguises itself as "the model failed the task" on any leaderboard.

## 2. Methodology

### 2.1 Experiment design and key decisions

| Decision | Value | Why |
|---|---|---|
| Temperature | `SWE_TEMP=0.6` | Mentor's ask; also the value the certified SWE_clean campaign and CLAUDE.md use ("never run agents greedy") |
| Episodes | `REPEATS=2` | Mentor asked for "two more" |
| Loop guard | `LOOP_GUARD_N=12` | The certified campaign's backstop: kill an episode after 12 identical consecutive actions instead of burning to the 40-min drain cap |
| Data isolation | `TIER_PREFIX=glm-t06` | New runs land in `glm-t06_swe_django/`, physically separate from the temp-0 evidence (`glm_swe_django/`) — the temp-0 runs are measurement evidence and must never be overwritten |
| `DATA_ROOT` | set explicitly | **Critical footgun:** invoking via `measure.sh` defaults `DATA_ROOT` to `SWE_clean/data` and each episode begins with `rm -rf` of its output dir — it would destroy certified thesis runs. Always call the raw runner with `DATA_ROOT` when reproducing |
| Pre-spend balance check | 1-token real completion | Preflight's endpoint gate only calls `GET /models`, which returns 200 **even with zero balance** (learned the hard way: error 1113 killed an earlier campaign 22 s in). A `POST /chat/completions` with `max_tokens:1` is the only honest balance probe |

Exact invocation (from `local_agents/kit/`):

```bash
DATA_ROOT=$HOME/InferSuite/local_agents/superseded_40min/data \
SWE_INSTANCES="django__django-10097" REPEATS=2 SWE_TEMP=0.6 \
LOOP_GUARD_N=12 TIER_PREFIX=glm-t06 \
./run_glm_campaign.sh campaign swe
```

The runner applies the full measurement stack per episode (isolation shield + ISO-PROOF quiet
gate, litellm proxy on housekeeping cores, 10 Hz cpu.stat pollers, zero-mux windowed counter
groups, continuous TMA census, 99 Hz cgroup-scoped records). Temperature is recorded in each
episode's `metadata.json` **and** inside the banked sweagent config — verify both when
auditing (`"temperature": 0.6`).

### 2.2 Forensics — how each claim was verified

1. **Loop classification** (both runs): take the last 12 actions of the trajectory; ≥ 8
   byte-identical ⇒ looped. (The kit's validator gate E7 is the formal version.)
2. **Run 1's ending**: parsed the trajectory — 29 steps whose action is `submit`, first at
   step 126 of 185; the observation after every one contains the same
   `SyntaxError: invalid syntax` pointing at the f-string on line 24 of
   `/root/tools/review_on_submit_m/bin/submit`.
3. **Interpreter proof**: `docker run --rm swebench/sweb.eval.x86_64.django_1776_django-10097
   python3 --version` → **Python 3.5.6** (f-strings require ≥ 3.6). The tool's shebang is
   `#!/usr/bin/env python3`, so it resolves to the container's interpreter.
4. **Correctness of the agent's fix**: extracted the diff from the trajectory observations —
   the regex change to the user:pass clause of `URLValidator` in
   `django/core/validators.py`, identical in substance to the merged upstream fix; the
   agent's own reproduction suite printed "ALL TESTS PASSED".
5. **Upstream status**: `git fetch origin main` in the vendored
   `agentic/swe_agent/external/SWE-agent` showed **zero commits we lack** (our checkout,
   v1.1.0 @ `3ea751c0`, *is* upstream main) and the submit tool untouched; web + issue-tracker
   search found no existing report of this failure mode.
6. **Behavioral contrast**: burst statistics from the banked capture — run 1 did 64 heavy
   tool bursts (vs 4 in the temp-0 loops) at 78 total core-s (vs 486–743).

### 2.3 What a reproducer needs

- The vendored SWE-agent (v1.1.0, `3ea751c0`) with the `review_on_submit_m` tool bundle —
  a *fixed* submit tool would erase layer 2 of the finding.
- The GLM-5.2 endpoint + key (`~/.glm_key`); ~55 min of episode wall-time of API spend.
- The docker image above (pulled automatically).
- Expect **non-determinism**: temp 0.6 samples; even temp 0.0 is not deterministic over a
  shared serving API (Mohamad's three temp-0 django episodes ran 304/414/443 turns under
  identical settings). Reproduce the *phenomena* (loop rate ↓, submit bounces when an episode
  completes), not exact trajectories.

### 2.4 Scripts and artifacts

| Item | Location | Role |
|---|---|---|
| `run_glm_campaign.sh` | `local_agents/kit/` | campaign runner (isolation, capture, loop guard, teardown) |
| `campaign.conf` | same dir | defaults; env vars override |
| `plot_glm_results.py` + `plot_spec.json` | same dir; spec in `local_agents/superseded_40min/` | renders django@0.6 as a 5th column, `outcome: "submit-blocked"` tags the title |
| `audit_plots.py` | same dir | figure-vs-raw audit (ALL MATCH before trusting figures) |
| Raw episodes | `local_agents/superseded_40min/data/glm-t06_swe_django/run_{1,2}/` | agent.log, traj, cpustat, counter windows, tma_cont, records, metadata |
| Traj forensics | inline snippets, logic reproduced in §2.2 | submit-bounce and loop-tail analysis |

## 3. Key insights (most → least important)

1. **SWE-agent's stock submit tool cannot run on the oldest SWE-bench images** — f-strings vs
   Python 3.5.6 — so django-10097 (and by construction any pre-3.6-testbed instance whose
   agent reaches submission) is unsolvable with the stock config **at any temperature**. The
   bug is upstream-current and unreported, and it is score-relevant: on a leaderboard it is
   indistinguishable from "the model failed".
2. **The model actually solved the task.** The produced fix matches the upstream patch and
   passed the agent's own verification — the benchmark lost the answer, not the model. Framing
   matters: this is a harness bug report, not a model-capability result.
3. **Temperature 0.6 converts loops from absorbing to escapable, but does not eliminate
   them**: 0/6 temp-0 episodes ever reached submission; at 0.6 it was 1/2 completing +1/2
   looping. The loop guard bounded the failed episode to ~18 min instead of 40.
4. **Layered failures hide behind each other.** The decode-loop layer completely masked the
   submit-tool layer for two entire campaigns; only fixing layer 1 made layer 2 observable.
   Methodological corollary: "task always fails" deserves a forensic read of *how far* it got.
5. **A stuck agent has a recognizable CPU signature** (harness-dominated ~90 %, few heavy tool
   bursts, runs to the time cap) — but loop *content* differs by chance (git-heavy vs
   bash-heavy loops across runs), so a looped episode must never be presented as the task's
   profile.
6. **Definitional caveat carried on the slide:** "solved" here = produced/attempted to submit
   a patch. Formal SWE-bench resolution additionally needs the evaluation harness, which this
   kit intentionally does not run.

---

**Method update (2026-07-30).** `measure.sh` changed after this report: its plotting
interpreter `$PY` now resolves to the `infersuite-full` conda python (matplotlib/numpy left the
system interpreter). Nothing in this study's capture or analysis is affected; only the
interpreter a reproducer invokes. See report 16 §2.2 and CLAUDE.md's updated convention.

**Method update (2026-08-04).** `measure.sh` changed again after this report: the `service`
campaign dispatch was removed when the repo was narrowed to SWE-agent profiling (the service
stack, GPU-side kit, banked OpenClaw campaign, and EKS scripts left the working tree; all are
in git history). The `agents-swe` path this study used is unchanged — nothing in this study's
capture, analysis, or reproduction recipe is affected.

**Method update (2026-08-04, follow-up).** `measure.sh` changed again: `agents-oc` is now a
stub that explains the OpenClaw harness removal (the harness left the tree after its litellm
venv — which the SWE campaign shares — moved into the SWE kit). The `agents-swe` path this
study used is unchanged.
