# Report 03 — How tool/agent-call boundaries are marked (deck slide 21)

**Date of study:** 2026-07-28 · **Author of record:** Tianrui (Jerry), with Claude Code
**Deck slides:** 21 (method audit; underpins slides 13, 18 and Report 04's tagging)
**Longer prose version:** [`../handwritten_notes/analysis.md`](../handwritten_notes/analysis.md), Part 7

---

## 1. Key summary

The mentor required certainty about how "tool call boundaries" are marked in the
measurement kit. Verified in code, line by line, the answer has two independent layers.
**Spatially** (what counts as tool CPU at all), the boundary is a kernel cgroup wall —
harness in a systemd scope created at launch, tools in the docker sandbox's cgroup resolved
from the container's init PID — exact, kernel-enforced, and name-blind. **Temporally**
(which call owns which seconds), nothing is marked during profiling; call labels are
attached **at plot time** by an *ordinal anchor join* between the trajectory's ordered call
list and the fence's measured CPU bursts: calls > 5 s pair 1:1 in order with bursts > 5 s
(anchors), and between anchors, short bursts' core-seconds are distributed over short calls
weighted by each call's harness-logged `execution_time`. Fence totals are exact; only the
time-attribution layer is heuristic, and every assumption has a printed diagnostic. A
second, independent tagging mechanism added later (Report 04's 2 Hz live process poll)
agrees with this one where they overlap.

## 2. Methodology

### 2.1 Spatial boundary (exact, kernel accounting)

- **Harness fence** = `measured.slice/<unit>.scope`, a transient systemd scope the runner
  creates around `sweagent run-batch` (`run_glm_campaign.sh` ~:460–473). The fence path is
  **constructed from the unit name**, never discovered via pgrep/PIDs (the launch chain is
  sudo→systemd-run→runuser; PID discovery would find the wrong process and lie about
  liveness).
- **Tool fence** = the sandbox container's cgroup. Docker's `daemon.json` is rewritten with
  `cgroup-parent: measured.slice` (so containers cannot escape the measured partition,
  ~:126–138); the container is found once by name pattern (`sweb*`, ~:477–480), and its
  cgroup is resolved **through the kernel**: `docker inspect .State.Pid` →
  `/proc/<pid>/cgroup` (`cg_of_container`, ~:68–69). After that, membership is cgroup
  inheritance: SWE-ReX (the in-container action executor), the persistent session shell,
  and every spawned child are inside the fence *whatever their names*. (Contrast: OpenClaw
  has no container wall and needs the netlink fork+exec lineage watcher; SWE does not.)
- **Proxy fence** = litellm in its own user scope pinned to housekeeping CPUs.
- All three cgroup paths are banked per episode in `metadata.json`; capture begins only
  after the fences exist and the agent demonstrably works ("WORK VERIFIED" = STEP 2 in
  the agent log).
- Scope order is fixed: **scope1 = harness, scope2 = tool, scope3 = proxy** in every
  `cpustat_scopeN.tsv`, `rec_scopeN.data`, `scopeN_{dso,comm}.txt`.

### 2.2 Temporal boundaries (assigned at plot time)

Nothing about call types is recorded during profiling — the 10 Hz `cpu.stat` poller just
banks exact cumulative CPU per fence. At plot time (`plot_internal_tools.py`):

1. **Bursts** from the 10 Hz series: a span opens above a detection floor (tool 0.005 /
   harness 0.02 cores), gaps < 0.4 s merge, spans ≤ 0.001 core-s drop as dust; "heavy" =
   peak > 0.3 cores. Constants are locked in the campaign MANIFEST. Burst *energy* is the
   exact sum of usec deltas; only edge placement quantizes to the 0.1 s grid.
2. **Calls** from the trajectory, in order, each `(class, execution_time)`.
   **Class comes from text classification of the agent's own logged action string**
   (`classify()`, ~:39): empty action → internal (requery); prefixes
   `str_replace_editor/open/goto/scroll/search_*/submit/edit` → internal; substrings
   `pytest/runtests.py/make/gcc/cc1/jest/npm test/…` → payload: build/tests; leading
   `git` → payload: git; else payload: other bash.
3. **The ordinal anchor join** (~:66–103): calls with `execution_time > 5 s` pair 1:1, in
   sequence order, with bursts longer than 5 s (only test suites/builds run that long);
   anchors partition both sequences into aligned segments; within a segment, the summed
   core-seconds of its short bursts are distributed over its short calls **weighted by
   execution_time**. "Attribution coverage 100 %" ≡ every core-second inside a detected
   burst was credited to some call class. Sub-floor trickle CPU is excluded symmetrically
   (numerator and denominator).

### 2.3 Exact vs heuristic, and the guards

| Layer | Status |
|---|---|
| Fence membership; fence CPU totals; burst core-seconds | **Exact** (kernel cgroup accounting) |
| Per-class wall time (`execution_time`) | Exact as logged by the harness |
| Burst thresholds; 5 s anchor rule; ordinal pairing; weights | **Heuristic** — definitional/alignment choices |

Guards a reproducer should check on every new figure: the printed
`anchors: X long calls vs Y long spans (pairing min)` diagnostic (a mismatch = visible
misalignment before the figure is trusted); the explicit fallback label
"duration-weighted (no long calls)" when no anchors exist; `plot_calls_vs_bursts.py`
quantifying calls ≫ bursts (light calls legitimately produce no burst).

### 2.4 How this was verified, and the cross-check

The write-up was produced by exhaustive code reading with line references
(`plot_internal_tools.py`, `plot_calls_vs_bursts.py`, `run_glm_campaign.sh` fence/launch
sections, campaign MANIFEST) and verified against banked data (e.g. `swerex-remote`
visible inside tool-fence comm tables). Report 04 later added an **independent** mechanism
— a live 2 Hz poll of processes inside the tool cgroup — which reproduces the same
placement of CPU into build/test phases; two unrelated taggers agreeing is the strongest
evidence the boundary story is right.

### 2.5 Scripts and artifacts

| Item | Location | Role |
|---|---|---|
| `run_glm_campaign.sh` | `local_agents/scripts/glm/` | fence creation/resolution, pollers, records |
| `plot_internal_tools.py` | same dir | `classify()` + burst detection + ordinal anchor join + coverage stamp |
| `plot_calls_vs_bursts.py` | same dir | burst vocabulary, calls-vs-bursts accounting |
| `SWE_clean/plots/MANIFEST.md` | `local_agents/SWE_clean/plots/` | locked burst constants |
| `metadata.json` (per run) | every `run_*/` | banked fence cgroup paths |

## 3. Key insights (most → least important)

1. **The tool/harness boundary is structural, not inferred**: kernel cgroup inheritance
   from a container wall and a launch-time scope. No name matching, no PID sampling —
   the one part of the pipeline that cannot mis-attribute.
2. **Call types are plot-time labels on the agent's own action text**, not observations
   of processes. Anyone re-using the per-call figures must know the classes come from
   `classify()`'s substring rules and inherit their limits.
3. **The temporal join is ordinal, not timestamped** — it works because call and burst
   sequences share an order and because >5 s events are rare and unambiguous. Its failure
   modes (a long call with no CPU; extra long spans; no anchors at all) are each surfaced
   by a printed diagnostic rather than silently absorbed.
4. **"Coverage 100 %" has a precise, narrower-than-it-sounds meaning**: all *burst-covered*
   tool CPU attributed; sub-floor trickle is deliberately out of scope on both sides of
   the ratio.
5. **Two independent taggers (trajectory-text join vs live process poll) agree**, which
   both validates the older figures (slides 13/18) and justifies preferring the live poll
   (Report 04) when per-window granularity is needed.
