# Classification protocol — task "tool properties" on SWE-bench Multilingual

**Date:** 2026-07-31 · **Role:** mentor-packet deliverable 2 of 3. This is the human-readable
protocol layer; the operational truth it summarizes lives in `taxonomy_spec.json`
(`decision_procedure` — deterministic, reapplicable without any LLM), `behavior_classify.py`
(`act_class`, `MARGIN`, `credits`), and `analyze_l3_windows.py` (`_progs`/`tag_of`). Where this
document and those artifacts disagree, the artifacts win and this document has a bug.

**Governing rule:** a static label is a *prior*; only a measured episode produces a *verdict*.
No evidence, no claim; unknowns are marked unknown.

---

## 1. "Type" has two defensible meanings — the protocol defines both

The mentor's categories (search- / edit- / test-execution- / build-dominated) can mean:

- **Axis 1 — CPU mechanism** (*intrinsic*): which toolchain physics runs in the tool fence
  when the agent verifies its work. A property of the **repo** (hence, in this corpus, of the
  language). Static, deterministic, and mostly validated.
- **Axis 2 — behavioural mix** (*observed*): what the **agent** spends its actions on.
  A property of an **episode**, not of a task — measured, this axis collapsed (§3.2).

Conflating them was the draft's central error ("Rust is build-dominated because it compiles" —
measured: `tests(rust)` 87 %). Every task answer states both, never a forced single word.

## 2. Axis 1 — mechanism classes (B/A/J/I/N + Y)

| class | definition (abridged from `taxonomy_spec.json`) | languages | n |
|---|---|---|---|
| **B** build-driver | test entry point *is* a build driver (make/cmake+ctest); whole-project compilation unavoidable | C, C++ | 42 |
| **A** AOT-unified | one command (`cargo test`, `go test`) compiles the dependency closure, then runs it | Rust, Go | 85 |
| **J** JVM-unified | bytecode compile cheap and in-process; JVM boot + classpath + surefire dominate | Java | 43 |
| **I** interpreted-suite | no compilation anywhere in the test path; runner + app-under-test | PHP, Ruby | 87 |
| **N** node-transpile | JS/TS test command runs a transpiler/bundler child, then a JS runner | JS, TS | 43 |
| **Y** pytest | out-of-corpus placeholder for the 3 Python reference tasks | — | 0 |

**Central verified fact: mechanism is a total function of `repo` and of `language`** — zero
exceptions over all 300 rows (`validation.md` §"What checks out first"; cross-tab reproduced in
`task_inventory.csv`). Consequence: the 9×5 ⟨language, mechanism⟩ grid has **9 reachable
cells**, all already covered by the 12 banked workloads. Within-language variation is carried
by the second-axis tier (within-repo test scope S/M/L/F, `plan.md` §2), not by mechanism.

**How a mechanism label is *confirmed*:** instruction-weighted command-tag composition of the
tool fence — median over the 10–11 dedicated-group replay passes (`attribute_windows.py mix`,
tags from `analyze_l3_windows.py`), behind the two-part gate: ownership ≥50 % of fence
instructions in toolchain-observed windows, adequacy ≥20 windows and ≥150 Ginstr per pass.

**Validation status (honest):** 5/9 clean agreements on scoreable measured rows. Per class:
B 2/2 *but only as the pooled compile+link+make predicate* (per-member "compile 97 %" vs
"pkg/build 31 %" is a window-sampling artefact, not physics); A **refuted by 2 of its 3
measured members** (tokio compile 10 %, gin compile 2 % — warm build caches); J's `compile ≤15 %`
arm is a **tautology** (maven compiles in-process; no `javac` process can ever be seen);
I 2/2; N's runner arm 2/2 but its transpile sub-term unsupported (predicted 5–35 %, measured
0 % and 3 %). Full table: `validation.md` §1–2. The wave-0a tagger repairs (basename matching,
tag multiset) are prerequisites for re-judging A and N — argv sample counts are **not**
instruction weights, and priority-winner tagging lets a persistent front-end swallow its own
compiler.

## 3. Axis 2 — behavioural mix (S/E/T/B, else M)

**Action classifier** (`behavior_classify.py act_class`, ordered, deterministic, harness `cd`
prefix stripped): **E** = `str_replace_editor {str_replace,create,insert,write,append}`,
`sed -i`, `patch` · **T** = test runners (pytest/jest/vitest/mocha/rspec/phpunit/gotestsum/
ctest, `go|cargo test`, `mvn|gradlew … test`) and repro-script forms (`python|node|php|ruby
-c/-e`, `./reproduce*`, `node|php|ruby <file>`) · **B** = compilers/builders (make/cmake/ninja/
gcc/g++/javac/rustc, `go|cargo build`) and package installs (pip/npm/pnpm/yarn/bundle/gem/
composer/apt `install|add|update|ci|download`) · **S** = grep/rg/find/cat/ls/head/tail/tree/wc,
`sed -n`, and **`str_replace_editor view`** — the load-bearing correction: `view` is reading;
counting it as editing had inverted the study's conclusion (report 17, dated correction).

**Episode label:** shares over classified actions (`other` excluded); label = argmax **only if
it leads by ≥ MARGIN = 10 points**, else **M** (a 49/47 episode is not "dominated" by
anything). **Cell credit** (`credits()`): leader *or* co-dominant within MARGIN — a 49 % S /
47 % T episode does supply test-execution behaviour.

**Measured verdict (16 episodes, 9 languages, 15 repos):** every episode is search-led — 13
banked: 11 S + 2 M (S/T co-dominant); 3 falsification probes chosen as the statically
*strongest* non-S candidates all realized S-led (phpspreadsheet-3940 S=49/T=47 co-dominant;
preact-4152 S=87; terraform-35543 — the **largest gold patch of any E candidate, 9 files /
534+ lines — realized E=3 %**). Edit and build never lead anywhere (E ≤ 18 %, B ≤ 18 %);
the residual structure is a **search↔test gradient** (T spans 0–47 %), not discrete types.
Conclusion: the behavioural mix is a property of *this agent at temperature 0.6*, not of the
task. **The static behavioural prior scored 1/10** against realized labels
(`behavior_classify.py predict`) — use priors as tie-breakers, never as verdicts.

**Harness constraints that bound this axis** (properties of the config, not of tasks):
(a) the SWE-agent blocklist refuses bare `make` (frozen config
`agentic/swe_agent/runs/glm_live/phpoffice__phpspreadsheet-3940_r1/run_batch.config.yaml`), so
agent-issued build actions are structurally suppressed — realized B is a lower bound under
this harness; (b) `_state_anthropic` fails once per step on images without `python3` on PATH
(prometheus/gson/php-cs-fixer episodes — report 16 disclosure), degrading agent state
information; (c) temperature is fixed at 0.6 campaign-wide. A different agent/config could
realize a different mix; that would be a new finding about the *agent*, not a revision of the
task labels.

## 4. Intrinsic vs observed — and why action mix ≠ CPU mix

The fence measures **all descendants** (cgroup); the action classifier sees only **top-level
agent commands**. jq is the clean example: the agent can never issue `make` (blocklisted) and
its realized build-action share is 18 %, yet the fence composition is compile 61 % +
`pkg/build` 31 % — make and gcc enter as *children* of permitted commands (`./configure`, test
scripts). Symmetrically, prometheus is the most search-heavy episode by actions (86 %) with
the largest fence (383 core-s) — search actions are many and cheap; verification children are
few and expensive. **Action mix carries almost no CPU information** (anti-correlated with
fence size across the banked set). Compute claims use Axis 1 + measured composition;
behavioural claims use Axis 2; magnitude claims use neither (no static signal, `plan.md`
caveat 3).

## 5. Which instrument answers which question

| question | instrument | source |
|---|---|---|
| behavioural S/E/T/B of an episode | `act_class` over the trajectory | `behavior_classify.py labels` |
| mechanism composition of the fence | instruction-weighted window tags, replay median | `analyze_l3_windows.py` + `attribute_windows.py mix` |
| is the fence the language's? | ownership+adequacy gate | `attribute_windows.py probe` |
| internal-vs-payload CPU split | `plot_internal_tools.py classify()` — its build/test **merged** bucket cannot serve the 4-way split | `plot_internal_tools.py` |
| trajectory workload summary | `WORK` 8-category regexes | `attribute_windows.py` |

Divergence hazards (manual, undocumented failure modes): the per-language PROBE regexes are
**duplicated** in `attribute_windows.py` and `behavior_campaign.sh`; new tasks must be
registered by hand in `attribute_windows.py` (CAMPAIGN/LANG/PROBE) *and* `cross_task_grid.py`.

## 6. Label lifecycle and confidence

candidate (static) → realized (one episode) → confirmed (replay median + gates)

- **candidate**: mechanism class = repo lookup (high confidence *as a toolchain lookup*;
  per-row confidence in `classifications.json`); behavioural prior = `predict_row` (low —
  measured 1/10). Sampling may *select* on candidates; claims may not cite them.
- **realized**: one trajectory's action mix / one episode's fence. Bounded by episode noise —
  the same instance spans **5.33×** in tool core-s across live seeds (babel quadruplicate),
  so single-episode magnitude contrasts under ~5.3× are unresolvable.
- **confirmed**: composition as replay median behind E1–E11 + ownership/adequacy. Composition
  reproduces to ~1 % (Java ~7 %); magnitude does not reproduce and is never a label.

A ⟨language, type⟩ cell is credited only by realized/confirmed labels (`credits()`), never by
a prior — the falsification probes exist because the one measured co-dominant T episode was
nearly discarded under a stricter rule.

## 7. Worked example — the five-question card for `phpoffice__phpspreadsheet-3940`

1. *What did we measure?* Mechanism: class I (interpreted-suite), **confirmed** — composition
   `tests(php)` 96 %, gate 96.3 % ownership at 888 windows / 1293 Ginstr per pass (11 passes,
   second-largest fence in the study). Behaviour: **realized M — S=49/E=4/T=47/B=0**, S/T
   co-dominant; credits PHP/T under `credits()`.
2. *How?* 217-step trajectory classified by `act_class`; fence composition from dedicated-group
   replays, instruction-weighted, median over passes.
3. *Why this task?* Chosen by the probe design as PHP's statically strongest T candidate
   (heavy verify set, 1+58 tests) — the cell most likely to falsify "everything realizes S".
4. *What did we reject?* php-cs-fixer-7523 as the T runner-up (already banked — re-running
   re-measures a banked episode); a hard-label rule that would have discarded this 49/47
   episode as "not test-dominated".
5. *What could invalidate it?* Tagger artefacts (wave-0a: argv-vs-instruction weighting);
   the co-dominance margin choice (10 pts); agent/config change (temp, blocklist) — the
   behavioural half is a property of the agent.

Answer sentence for the mentor: "class I mechanism, test-runner CPU (96 %), search/test
co-dominant actions (49/47) — both numbers, no forced single word."

## 8. What invalidates a label (checklist before quoting one)

- argv sample counts quoted as instruction shares (they are not weights)
- pre-basename-fix tag labels (report 16 defect 6) or the un-repaired `/c\+\+` compile regex
- a composition read from a single pass instead of the replay median
- a magnitude number used as a type criterion (no static signal; 5.33× episode noise)
- a prior quoted as a verdict (mechanism: A and N arms unvalidated; behaviour: 1/10)
- a language-level sentence from a single-repo language (every language currently has exactly
  one accepted repo; C++'s two repos are both header-only template libraries)
- an episode with failed gates (ownership/adequacy, E1–E11) or empty-turn API starvation
