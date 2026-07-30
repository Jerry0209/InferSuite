# Report 14 — Instrument-to-figure reference: how each deck number is measured (deck slides 1–28)

**Date of study:** 2026-07-29 · **Author of record:** Tianrui (Jerry), with Claude Code
**Deck slides:** 1–28, cross-cutting — this report answers "how do you know that?" for any
figure on the deck and names the code site of every constant behind it
**Per-study detail:** Reports 05 (1–6) · 06 (7–12) · 07 (13) · 08 (14–16) · 01 (17) · 02 (18) ·
04 + 09–12 (19–23) · 03 (21) · 13 (24–25) · 16 (26–27) · 17 (28)
**Longer prose version:** [`../handwritten_notes/analysis.md`](../handwritten_notes/analysis.md), Parts 1–7

---

## 1. Key summary

The question behind this report is the one asked from the floor: *point at any number on the
deck — which instrument produced it, is it exact or inferred, and where is the rule written
down?* Method in one sentence: for every figure family, trace the displayed number back to one
of the four per-episode instruments (plus the 2 Hz command tagger used by the per-window
study), and record the code site of each constant it depends on, so no definition has to be
re-derived from a chat session.

Headline: **exactly two layers are exact.** Kernel cgroup `cpu.stat` accounting produces every
core-second, timeline, and burst; the PERF_METRICS slot census produces every TMA bucket. Every
statement about *which command* owns CPU is text classification of the agent's own logged
action string, attached to the CPU timeline by an ordinal anchor join — heuristic by
construction, with named diagnostics. A new finding is documented here: the per-window command
tagger had **no JavaScript bucket**, and `TAG_PRIORITY` ranks `shell` above `other`, so babel's
jest runs were labelled `shell`. On slides 24–25 the missing *compile* bar is a true property of
the workload; the missing *test* bar was a labelling artifact (§2.3) — **fixed in Report 15**,
along with a plotter that silently dropped any tag absent from its colour dict and an axis label
that truncated "JavaScript" to "Java".

## 2. Methodology

### 2.1 Instrument → figure map

Deck numbering drifts as slides are added; the stable identifier is the on-slide eyebrow label.
As of 2026-07-30 the deck is 28 slides and the numbering below matches
[`README.md`](README.md). Slides 26–28 (nine-language axis, composition-vs-magnitude,
⟨language, type⟩ sampling frame) are documented in Reports 16 and 17; their instruments are the
same per-window stack as 19–25, plus the ownership+adequacy gate in `attribute_windows.py`.

| Deck slides | What the figure shows | Instrument | Layer | Code site |
|---|---|---|---|---|
| 1–2 | wall-clock split; CPU work in core-seconds incl. litellm — since 2026-07-30 the wall-clock slide shows BOTH campaigns' donut rows side by side (superseded_40min + SWE_clean incl. babel/fmt), never merged into one figure | 10 Hz `cpu.stat` pollers, three cgroup scopes | **exact** (wait = residual) | `run_glm_campaign.sh:226-238`; `plot_glm_results.py:343-430` |
| 3 | orchestration timelines (cores vs time) | same 10 Hz series, no floor/merge/width-floor | **exact** | `plot_glm_results.py:432-471` |
| 4, 12 | calls, bursts, heavy bursts, burst duration, turns | trajectory + bursts derived from the 10 Hz series | mixed (energy exact, classes/edges heuristic) | `plot_glm_results.py:171-175, 260-270, 509-540`; `cmp_allruns_absolute.py:33-46` |
| 13 | tool CPU by agent-call class; harness CPU by library | ordinal anchor join; 99 Hz cgroup-scoped `perf record` | heuristic; statistical | `plot_internal_tools.py:33-101`; `run_glm_campaign.sh:279-297` |
| 14–16, 18 | TMA Level 1 and Level 2 per fence | continuous PERF_METRICS census, whole episode | **exact** (hardware slot accounting) | `run_glm_campaign.sh:69, 265-272`; `plot_glm_results.py:303-318` |
| 19–28 | per-2 s-window metric distributions, tagged by command | windowed zero-mux counter groups + 2 Hz command sampler | counters exact, tags heuristic | `analyze_l3_windows.py` `tag_of`/`_progs` (basename matching since 2026-07-30) |
| 26 | ownership + adequacy gate per task | 2 Hz argv poll ∩ per-window instructions | heuristic (presence-based; lower bound for short-lived compilers) | `attribute_windows.py` (`probe`; task registry last extended 2026-07-30 evening with the behavioural-probe task `phpoffice-bT`, report 17 §2.4) |
| 21 | the boundary rule itself (method audit) | — | — | Report 03 |

### 2.2 Definitions and constants — where each rule lives

- **Fences are cgroups, never PIDs.** Harness = the transient systemd scope wrapping
  `sweagent run-batch` (`run_glm_campaign.sh:463-478`, path *constructed* from the unit name);
  tool = the sandbox container's cgroup resolved through the kernel
  (`docker inspect .State.Pid` → `/proc/<pid>/cgroup`, `cg_of_container`); proxy = litellm in
  its own user scope pinned to the housekeeping CPUs (`:429-445`). Membership is inherited
  through fork **and** exec, so every spawned compiler/test process is fenced whatever its
  name. Scope order is fixed everywhere: **1 = harness, 2 = tool, 3 = proxy**.
- **Wall-clock split.** Tool and harness wedges are `active_wall()` — the sum of *true* sample
  intervals above the detection floor (poll interval is ~0.1021 s, not 0.1; assuming 0.1
  undercounts ~2 %). "Inference" is the residual `wall − tool_s − harn_s`, so simultaneous
  fence activity is subtracted twice; `cmp_allruns_absolute.py:73` clamps this explicitly.
  litellm has no wall wedge (it runs inside the waits, off-partition) but a real core-second
  figure.
- **Agent turns** come from the harness log, never from CPU activity: the count of `"STEP "`
  markers in `agent.log` (`plot_glm_results.py:95-110`). OC has no such marker and continuous
  background CPU, so its turns come from assistant messages in `transcript/chat.jsonl`.
- **Bursts.** Contiguous fence activity above the floor (tool 0.005 / harness 0.02 cores), gaps
  < 0.4 s merged, ≤ 0.001 core-s dust dropped, **heavy = peak > 0.3 cores**
  (`plot_glm_results.py:171-175`). The 0.4 s = four consecutive sub-floor samples: above
  intra-command scheduling dips, far below a model round-trip, so calls never merge. Burst
  *energy* is the exact sum of `usage_usec` deltas — the merge changes counts and durations
  only; edges quantise to the 0.1 s grid and "peak" is a 0.1 s average, so sub-100 ms spikes
  can fall below the heavy line.
- **Agent-call classes** (slide 13) are text classification of the trajectory action string:
  `INTERNAL_PREFIXES` → `internal`; `BUILD_TEST_PAT` (pytest, runtests, make, gcc, cc1, jest,
  npm/yarn, node…) → `build/tests`; leading `git` → `git`; else `other bash`
  (`plot_internal_tools.py:33-47`). The campaign config enables only the bundles `registry`,
  `edit_anthropic`, `review_on_submit_m` (`config/default.yaml:41-44`), so windowed/search
  prefixes never occur — sympy run_1 actions are 273 `cd`, 112 `str_replace_editor`,
  2 `submit`, 1 `find`, 1 `rm`. SWE-agent's own tools execute *inside* the sandbox
  (uploaded to `/root/tools/<bundle>/bin`, put on `PATH` by
  `sweagent/tools/tools.py:266-312`), which is precisely why the fence cannot separate them
  and this classification exists.
- **`perf` DSO tables** (slide 13, lower row) come from `perf script -F comm,period,ip,sym,dso`
  over the 99 Hz cgroup-scoped record, crediting each sample's `period` to its leaf-frame DSO
  (`run_glm_campaign.sh:279-297` → `scopeN_dso.txt` as `pct% path`). The axis is **share of
  sampled weight, not core-seconds**: `perf record` is used for what-program/symbol/CPU
  attribution and never for rates.
- **TMA** is captured continuously for the whole episode by a dedicated instrument —
  `perf stat -I 10000 -x, -a -e "$TMA_EVENTS" --for-each-cgroup=…` → `tma_cont.csv`
  (`run_glm_campaign.sh:265-272`), events at `:69`. It lives in PERF_METRICS, costs **zero
  general-purpose counters**, and therefore never joins the 8-group windowed rotation. The
  hardware itself classifies every issue slot as retiring / bad-speculation / frontend-bound /
  backend-bound; L2 children (`heavy-ops`, `br-mispredict`, `fetch-lat`, `mem-bound`) are
  counted directly and their siblings are remainders (fetch-**bandwidth** = FE − fetch-lat,
  core-bound = BE − mem-bound). Plotted percentages are `event / Σ(four L1 counts)`
  (`plot_glm_results.py:303-318`) — a **slot-weighted episode average**, so busy periods
  dominate and idle time contributes nothing. Per-fence attribution is done by the kernel: the
  cgroup is a filter on the PMU, enabled/disabled at context switch, and the cgroup is a
  *column* in the CSV alongside a `100.00` enabled-time column (the zero-multiplexing proof).
- **Per-window command tags** (slides 19–25) come from the 2 Hz host-side sampler
  (`cmdlog.tsv`) through `tag_of()` (`analyze_l3_windows.py:30-40`): `tests(pytest)`,
  `compile` (`cc1|gcc|g++|ld|cythonize|build_ext`), `pkg/build` (`pip|setup.py|ninja|make`),
  `git`, `agent-tool`, `shell`, `python-other`, `other`. A window takes the highest-priority
  tag observed in it (`TAG_PRIORITY`, `:56-58`) so persistent plumbing (swerex server, session
  shell) cannot dilute the foreground command.

### 2.3 Verification, hazards, and the command-tagger gap

- **Turn count cross-check.** sympy SWE_clean run_1: 389 `STEP` markers = 389 trajectory
  entries — the log-derived turn count and the harness's own record agree exactly.
- **Zero multiplexing is proven per row**, not assumed: every `tma_cont.csv` line carries
  `100.00` in the enabled-% column.
- **fmtlib's compile work reaches the tag axis by two different sample forms.** The agent's own
  loop appears directly (`g++ -std=c++17 -I include reproduce.cpp build/libfmt.a -o reproduce`,
  and its `cc1plus` child under `/usr/lib/gcc/…`), while build-system compiles appear as
  `/bin/sh -c cd /testbed/build/test/gtest && /usr/bin/c++ …` — whose *driver* line matches no
  compile pattern (`c++` is neither `gcc` nor `g++`) and tags `shell`. Its `cc1plus` child does
  tag `compile`, and window priority (compile > shell) resolves the window correctly. Sample
  counts, replay run_1: compile 469, pkg/build 808, shell 713, other 642, agent-tool 520,
  git 8 → window level, tool fence: **compile 1626**, shell 388, pkg/build 103, git 33.
- **The babel/JavaScript gap (new, load-bearing for slides 24–25).** babel's tool-fence windows
  are shell 534 / git 114 / python-other 14 and *nothing else* — no compile, no test class.
  Three causes, only the first about the workload: (1) JS is not compiled and the image ships
  babel pre-built, so no compiler binary ever runs — `compile` and `pkg/build` genuinely cannot
  match; (2) `tag_of()` has **no rule for `node`/`jest`/`yarn`/`npm`**, unlike
  `plot_internal_tools.classify()` whose `BUILD_TEST_PAT` does list them — so real test runs
  (`cd /testbed && BABEL_ENV=test node_modules/.bin/jest packages/babel-generator`) fall through
  to `other`; (3) `TAG_PRIORITY` ranks `shell` above `other` and the session `bash` is sampled
  in nearly every window, so those windows surface as `shell`. Magnitude bound so this is not
  over-read: babel ran jest 4 times at 1.3–1.6 s (12 sampler hits ≈ 6 s of jest in the episode)
  out of 94 steps that are otherwise `cat`/`grep`/`sed`/`find`, and its tool fence totals
  **37.9 core-s vs fmtlib's 270.5 core-s** (live run_1 each). The distribution values per tag
  are unaffected; what is affected is the *reading* of babel's tag composition. Report 13 §3.5
  now carries a pointer to this caveat. Optional fix, not applied: add
  `\bjest\b|\byarn\b|\bnpm\b|\bnode\b` → a JS-test tag ranked above `shell`, then regenerate the
  L3 window CSVs — the replays are deterministic, so this costs no API spend.
- **Honest labels carried forward.** `perf record` shares are time-shares, not miss-shares;
  "L1I MPKI" is a code-read/L1I-pressure proxy; the ports events are a raw execution-width
  cycle profile, not a core-bound decomposition; high IPC/retiring never certifies useful work.

### 2.4 Reproduction recipe

```bash
# 1. Fence/burst/turn numbers behind slides 1-4, 12 (banked data, no capture, no spend)
conda activate infersuite-full          # python3 with matplotlib; never the project .venv
cd ~/InferSuite/local_agents/scripts/glm
python3 plot_glm_results.py             # -> figures + values_dump.json (every displayed number)
python3 audit_plots.py                  # must end: ALL MATCH

# 2. Turn count vs trajectory length (the cross-check quoted in 2.3)
D=~/InferSuite/local_agents/SWE_clean/data/glm_swe_sympy/run_1
grep -c 'STEP ' $D/agent.log            # 389
python3 -c "import json,glob;print(len(json.load(open(glob.glob('$D/traj/**/*.traj',recursive=True)[0]))['trajectory']))"

# 3. Per-fence TMA rows, with the cgroup column and the zero-mux proof
head -12 $D/../../glm_swe_sympy/run_1/tma_cont.csv   # time,count,,event,cgroup,enabled_ns,pct

# 4. Window-tag composition per task (the babel/fmtlib evidence in 2.3)
python3 -c "
import csv,collections
for t in ('fmtlib','babel'):
    r=list(csv.DictReader(open(f'../../SWE_clean/data/l3_study/all_windows_{t}.csv')))
    print(t, collections.Counter((x['fence'],x['tag']) for x in r).most_common(6))"

# 5. Sample-level tag histogram + the commands behind each tag.
#    analyze_l3_windows.py parses sys.argv at import time, so copy tag_of()
#    (analyze_l3_windows.py:30-40) into a scratch script and run it over
#    local_agents/SWE_clean/data/glm_replay_swe_{babel,fmtlib}/run_1/cmdlog.tsv
#    (schema: epoch \t pid \t argv). Expected: fmtlib compile 469 / pkg-build 808 /
#    shell 713; babel has zero compile and its jest lines fall through to 'other'.
```

What reproduces on a fresh capture: shares, shapes, tag composition, TMA buckets. What does
not: absolute minutes/core-seconds (2–3× episode-to-episode) and the specific trajectories.

### 2.5 Scripts, artifacts, and published slide links

| Item | Location | Role |
|---|---|---|
| `run_glm_campaign.sh` | `local_agents/scripts/glm/` | fences, ISO-PROOF gate, all four instruments, DSO/leaf tables, teardown |
| `plot_glm_results.py` | same dir | burst vocabulary, wall/CPU/timeline/call figures, TMA normalisation → `values_dump.json` |
| `plot_internal_tools.py` | same dir | agent-call classes + the ordinal anchor join (slide 13, upper row) |
| `cmp_allruns_absolute.py`, `cmp_allruns_shares.py`, `cmp_tma_allruns.py` | same dir | all-runs comparison figures (slides 8–13, 16) |
| `analyze_l3_windows.py` | same dir | 2 Hz command tagger, per-window counters → `all_windows_<task>.csv` |
| `audit_plots.py` | same dir | recomputes every displayed number from raw captures → ALL MATCH |
| `cmdlog.tsv`, `tma_cont.csv`, `cpustat_scope{1,2,3}.tsv`, `scopeN_dso.txt`, `agent.log`, `traj/` | per run dir | the banked evidence every number in this report was read from |

Published Claude artifacts (live slide links; private unless shared):

| Artifact | Link | Covers |
|---|---|---|
| Agent CPU profiling — GLM-5.2 SWE-agent (the deck, **28 slides**) | https://claude.ai/code/artifact/e93ebcb7-015d-4f40-8f83-62fe21777e62 | slides 1–28 (26–28 added 2026-07-30: nine-language axis, composition-vs-magnitude, sampling frame — reports 16/17) |
| Per-window gallery — scikit-learn | https://claude.ai/code/artifact/c12b01c1-7ac7-4f2e-8729-b1c90f5ef63b | slides 19–23 backing detail |
| Per-window gallery — astropy | https://claude.ai/code/artifact/3b68efd2-f9f0-49ad-b047-20ac27bb3c68 | slides 19–23 backing detail |
| Per-window gallery — sympy | https://claude.ai/code/artifact/704ab3b2-3b63-4c57-b087-88dcdcf968ff | slides 19–23 backing detail |
| Per-window gallery — babel (JS) | https://claude.ai/code/artifact/18a013a4-5013-4f95-9d11-9b214ed7ffbe | slides 24–25 backing detail |
| Per-window gallery — fmtlib (C++) | https://claude.ai/code/artifact/f84723fc-9fdb-424d-8728-8fa29bf3a5e6 | slides 24–25 backing detail |
| Per-window gallery — tokio (Rust) | https://claude.ai/code/artifact/ee3c3c29-b2d0-48f0-9e84-2215435d1c85 | slide 26 backing detail |
| Per-window gallery — jq (C) | https://claude.ai/code/artifact/9a6d9546-5589-4fd4-aa8d-534397b9034c | slide 26 backing detail |
| Per-window gallery — prometheus (Go) | https://claude.ai/code/artifact/43bdccbb-e539-4a97-9758-99f4c75e4f1a | slide 26 backing detail |
| Per-window gallery — gson (Java) | https://claude.ai/code/artifact/024cd36f-e98c-45c7-8595-ece33bc8c891 | slide 26 backing detail |
| Per-window gallery — rubocop (Ruby) | https://claude.ai/code/artifact/1135e8b0-7ebf-48e9-a839-60da45099c00 | slide 26 backing detail |
| Per-window gallery — vue (TypeScript) | https://claude.ai/code/artifact/5e03855b-62db-4d1a-9522-145fff53bd2c | slide 26 backing detail |
| Per-window gallery — php-cs-fixer (PHP) | https://claude.ai/code/artifact/e6a80616-9410-446f-b1d7-fc1eeac751b2 | slide 26 backing detail |

Related (not a deck): weekly status page —
https://claude.ai/code/artifact/7a9d155c-11f6-4e97-9d21-f60f677caca9

## 3. Key insights (most → least important)

1. **Two exact layers carry the whole study; everything else is inference with guards.** Kernel
   `cpu.stat` (core-seconds, timelines, bursts) and the PERF_METRICS slot census (TMA) are
   exact. Class attribution, burst edges, and window tags are heuristic layers stacked on top —
   each with a named constant, a code site, and a diagnostic. Any claim of the form "command X
   did Y" inherits the heuristic layer's uncertainty; any claim of the form "this fence spent
   N core-seconds" does not.
2. **Cgroups are the design, not an implementation detail.** They simultaneously provide the
   accounting (`cpu.stat`), the isolation (`cpuset`), and the PMU filter (`--for-each-cgroup`,
   `--cgroup=`), and their fork+exec inheritance is what makes name-blind fencing possible.
   Every per-fence number on the deck exists because of that one mechanism.
3. **The command tagger was Python/C-centric and silently mislabelled JavaScript — now fixed.**
   babel's jest runs landed in `shell` because there was no JS rule and `shell` outranks
   `other`. The absent compile bar on slides 24–25 is real; the absent test bar was not.
   **Resolved in Report 15:** `tag_of()` gained per-language test-runner, compiler, and
   package-manager rules (all ranked above `shell`), re-derived free from banked `cmdlog.tsv`;
   babel becomes `tests(js)` 77 %, the four other tasks are byte-identical, and regenerating
   `all_windows_babel.csv` changed 0 of 1306 values. The claim that "the metric distributions
   themselves stand" is now measured: **78.2 %** of babel's fence instructions occur in windows
   where jest/node/yarn was observed in the raw argv, independent of any tag.
4. **Turn counts must come from the harness's own log.** 389 STEP markers = 389 trajectory
   entries on sympy run_1; deriving turns from CPU activity over-segments (≈5× on OC, whose
   gateway is never idle).
5. **`perf record` answers "what program", never "how fast".** DSO shares are period-weighted
   sample shares; the harness's 76.8 % CPython / 10.1 % `_json` / 2.8 % tiktoken profile is an
   attribution result, and pairing it with the exact cgroup core-seconds is what makes the
   harness story quantitative.
6. **The burst constants change counts, not energy.** The 0.4 s merge and 0.005/0.02 floors
   move burst counts and durations; the core-seconds inside a burst are the exact `usage_usec`
   delta either way. That separation is why the same locked vocabulary can be reused across
   every campaign without invalidating the amounts.
