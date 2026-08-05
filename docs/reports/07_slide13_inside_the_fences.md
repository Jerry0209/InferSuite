# Report 07 — Inside the fences: what is actually heavy (deck slide 13)

**Date of study:** 2026-07-24 · **Author of record:** Tianrui (Jerry), with Claude Code
**Deck slides:** 13 (fence-internal attribution; feeds the TMA interpretation on slides 14–16)
**Longer prose version:** [`../handwritten_notes/analysis.md`](../handwritten_notes/analysis.md), Part 3 · **Boundary/anchor-join audit:** Report 03

---

## 1. Key summary

Slides 2–12 established *how much* CPU each fence burns; slide 13 asks *what that CPU
actually is*, for the featured runs of both campaigns (Mohamad's certified 40-min campaign
vs the re-run). Two independent instruments answer at two depths. **Tool fence, by
agent-call class** (trajectory-anchored ordinal join, attribution coverage 100 %):
build/test commands are **70–99 %** of tool CPU on every clean task in both campaigns —
per-campaign shares from the banked class tables: scikit-learn 99 %/99 %, astropy
93 %/73 %, sympy 71 %/78 % (Mohamad/new). One level deeper via the 99 Hz records:
scikit-learn's tool-fence time is **86.98 % OpenBLAS** (`libopenblasp-r0.3.28.so`) with the
Python interpreter at 1.28 % — the "tool work" is matrix arithmetic, not Python.
**Harness fence, by library** (perf-record DSO time-shares): **73–87 % Python
interpreter**, then tiktoken (2.8–6.2 % where visible) and JSON/pydantic parsing
(3.0–10.7 %) — near-identical structure in both campaigns. And the two django loops,
identical in symptom, differ completely in content: Mohamad's loop repeated `git`
(141.8 of 143.1 core-s, 99 % of a real tool-fence load), ours repeated a trivial shell
command (15.7 core-s total tool fence — the loop's cost lands harness-side).

## 2. Methodology

### 2.1 Design decisions

| Decision | Why |
|---|---|
| **Two independent instruments**: trajectory-anchored call classes (top panels) vs 99 Hz record DSO tables (bottom panels + OpenBLAS drill) | They answer different questions (*which agent call* vs *which library*) and have opposite error models: the class join uses **exact** fence energy (cgroup `cpu.stat`) but **heuristic** time attribution; the DSO tables are statistical samples, reliable as **shares only, never rates**. Agreement between them (both put scikit's CPU in the test suite) is the cross-validation. |
| Call **class = plot-time text classification** of the agent's own logged action (`classify()` in `plot_internal_tools.py`): empty action → internal; prefixes `str_replace_editor/open/goto/scroll_*/search_*/submit/edit …` → internal; substrings `pytest/runtests.py/make/gcc/cc1/jest/npm test/…` → payload: build/tests; leading `git` → payload: git; else payload: other bash | The trajectory is the only record of call identity; the profiler stays blind during capture (no per-call instrumentation to pollute the fences). Classes are labels on the agent's log, not process observations — users of the figure inherit the substring rules' limits. |
| CPU credited to classes by the **ordinal anchor join** (calls > 5 s pair 1:1 in order with bursts > 5 s; segment fill weighted by `execution_time`), coverage stamped on the figure | Full mechanics, guards, and the exact/heuristic split are Report 03 — not duplicated here. "Coverage 100 %" means all *burst-covered* tool CPU was credited (sub-floor trickle excluded symmetrically). |
| Records resolved with the sandbox container's **overlayfs merged dir as `--symfs`** (`docker inspect -f '{{.GraphDriver.Data.MergedDir}}'` → `mk_tables`) | In-sandbox libraries (`/opt/miniconda3/envs/testbed/...`) do not exist at host paths; without symfs the tool-fence samples fall to `[unknown]` and the OpenBLAS finding is invisible. |
| Records sample **`task-clock` at 99 Hz**, cgroup-scoped per fence | DSO percentages are therefore **time-shares** of fence CPU. Chosen for attribution ("where was the instruction pointer"), never for rates — the kit's counted-event windows own all rates. |
| Featured runs per campaign, fixed: scikit r1/r1, astropy r1/r2, sympy r1/r2, django r2/r2 (Mohamad/new; new campaign's set matches `superseded_40min/plot_spec.json`) | Median-run policy for signature figures; runs are pinned in the plotting code (`FEAT_M`/`FEAT_N`) so the figure is deterministic. |
| Harness DSO rows bucketed by `dso_cat()`: python interpreter / tiktoken / JSON-pydantic (`_json`, `pydantic_core`, `multidict`) / libc-loader / OS kernel / other | Six buckets make the cross-campaign structural identity readable; raw per-DSO tables stay banked for anyone needing finer grain. |
| Per-class core-second tables are **hardcoded** in `cmp_allruns.py --view absolute` (`TOOL_M`/`TOOL_N`), copied from `plot_internal_tools.py` stdout | Mohamad's data root lives outside this repo (`/home/thu/llm-service-kernel-latest/archive/certified_glm_40min`); freezing the captured tables lets the slide figure regenerate without that mount and makes the numbers auditable in one place. |

### 2.2 Verification and hazards

1. **Time-shares are NOT miss-shares — an overreach caught and corrected during the
   study.** The draft reading "OpenBLAS causes the cache misses" was wrong as stated: the
   records sample `task-clock`, so 86.98 % is OpenBLAS's share of tool-fence *CPU time*.
   Attributing cache **misses** to functions requires sampling on a miss event (a
   dedicated sampled-miss-event replay) — not done here. The corrected claim is "the time
   is in OpenBLAS"; the memory verdict comes from counted TMA (Reports 02/04).
2. **`kptr_restrict` must be pinned to 0** (now a preflight FAIL-gate in
   `run_glm_campaign.sh`): a mid-campaign flip silently moves kernel samples from
   `[kernel.kallsyms]` into `[unknown]`, shifting every DSO table (seen 2026-07-15:
   78 % vs true 96 % on a live↔replay dso-match anchor). Mohamad's banked tables carry
   `[unknown]` rows of 5.5–8.8 % — read them with this in mind.
3. **Scope honesty for the OpenBLAS number**: `scope2_dso.txt` covers the whole tool
   fence, not "the test suite" per se; the equation *whole fence ≈ test suite* holds for
   scikit only because build/tests own 99 % of its tool CPU (per-class table).
4. **Cross-instrument agreement**: the trajectory-text join and the independent live 2 Hz
   process poll added later (Report 04) place the CPU in the same build/test phases;
   Report 03 §2.4 documents the audit. Anchor diagnostics (`anchors: X long calls vs Y
   long spans`) were checked on every featured run before the figure was trusted.
5. **Statistical layer stays statistical**: the harness breakdown is reliable as
   percentages, meaningless as absolute rates (analysis.md caveat) — the figure's bottom
   panels are share-of-samples axes, deliberately not core-seconds.

### 2.3 Reproduction recipe

```bash
cd ~/InferSuite   # no new capture; everything reads banked data; free; seconds to run
# per-class tool tables + per-task figure; prints calls/wall/cpu per class, anchor
# diagnostics, and the coverage stamp (SYSTEM python3, per repo convention)
PLOT_SPEC=local_agents/superseded_40min/plot_spec.json \
  python3 local_agents/kit/plot/plot_internal_tools.py
# the slide-13 figure (both campaigns, 2x2): tool classes (top) + harness DSO (bottom)
python3 local_agents/kit/plot/cmp_allruns.py --view absolute   # -> plots/compare/cmp_whats_heavy.png
```

DSO tables are banked per run as `scope1_dso.txt` (harness) / `scope2_dso.txt` (tool)
under `local_agents/superseded_40min/data/glm_swe_<task>/run_N/` (scope order fixed:
1 = harness, 2 = tool, 3 = proxy). To re-derive them from the records, use `mk_tables` in
`run_glm_campaign.sh` (`perf script -f -F comm,period,ip,sym,dso [--symfs <MergedDir>]`);
the sandbox must still exist for the symfs path, which is why tables are made at episode
teardown. Leaf-symbol and per-CPU-lane tables regenerate post-hoc:
`./local_agents/kit/replay/gen_lanes_leaf.sh <data_root> --leaf`. Caveat:
`cmp_allruns.py --view absolute` hardcodes Mohamad's data root at
`/home/thu/llm-service-kernel-latest/archive/certified_glm_40min` (outside this repo) —
without that mount the Mohamad harness-DSO panel renders empty; the frozen `TOOL_M` class
table still renders.

### 2.4 Scripts and artifacts

| Item | Location | Role |
|---|---|---|
| `plot_internal_tools.py` | `local_agents/kit/` | `classify()` + burst spans + ordinal anchor join; prints the per-class calls/wall/cpu table (source of `TOOL_M`/`TOOL_N`) and the coverage stamp |
| `run_glm_campaign.sh` | same dir | 99 Hz cgroup-scoped `task-clock` records per fence; `mk_tables` → `scopeN_{dso,comm,ksym,leaf,cpulanes,pidtime}` with MergedDir symfs; `kptr_restrict` preflight gate |
| `gen_lanes_leaf.sh` | same dir | post-hoc per-CPU lanes + leaf-symbol tables from banked records |
| `cmp_allruns.py --view absolute` | same dir | builds the slide figure `compare/cmp_whats_heavy.png` (class stacks + `dso_cat()` DSO stacks, both campaigns) |
| `scope{1,2}_dso.txt` per run | `local_agents/superseded_40min/data/.../run_N/` | banked DSO time-share tables (harness / tool) |
| `cmp_whats_heavy.png` | `local_agents/superseded_40min/plots/compare/` | the slide-13 figure |

## 3. Key insights (most → least important)

1. **Tool-fence CPU is the task's own build/test payload, not the agent's tooling**:
   70–99 % of tool CPU on every clean task in both campaigns (scikit 99/99, astropy
   93/73, sympy 71/78 % — Mohamad/new). SWE-agent's internal tools
   (editor/viewer/search/submit) are dust — ≤ 7.4 core-s per featured episode.
2. **scikit-learn's "tool work" is matrix arithmetic, not Python**: 86.98 %
   `libopenblasp`, 8.69 % kernel, 2.28 % libc, 1.28 % python3.9 (tool-fence DSO table,
   run_1). This is the ground truth behind the core-bound TMA verdict (Report 02) and the
   ports/L1-supply limit (Report 04).
3. **The harness fence is the interpreter, everywhere**: 73–87 % Python interpreter
   (min 72.56 % Mohamad sympy, max 87.25 % Mohamad django) + tiktoken (2.8–6.2 % where
   visible) + `_json`/pydantic (3.0–10.7 %), small libc/kernel tail — the same structure
   in both campaigns, on every task. The harness's measured job: run Python, count
   tokens, parse JSON.
4. **Two loops, one symptom, opposite content — class attribution is what tells them
   apart**: Mohamad's django loop repeated `git` (141.8 of 143.1 core-s → 99 %, reads as
   a genuine tool load), ours repeated a trivial shell command (15.7 core-s total tool
   fence; the loop's cost lands harness-side). Wall-clock and fence totals alone cannot
   make this distinction.
5. **Time-shares are not miss-shares** — the study's own corrected overreach (§2.2.1) is
   the standing rule for every DSO table in the repo: `task-clock` sampling attributes
   *time*; miss attribution needs a sampled-miss-event capture that does not yet exist
   here.
6. **The comparison axis is clean on agent version**: both campaigns ran the same
   vendored SWE-agent v1.1.0 (SWE-ReX + tool bundles). A leaner agent (e.g.
   mini-swe-agent) would show a lighter harness fence — a follow-up campaign, not a
   confound of this one.

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
