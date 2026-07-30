# Report 17 — Sampling SWE-bench Multilingual by ⟨language, type⟩ (deck slide 28)

**Date of study:** 2026-07-30 · **Author of record:** Jerry0209, with Claude Code
**Deck slides:** 28; governs the next profiling campaign (behavioural-type sampling)
**Longer prose version:** `local_agents/ML_multiling/sampling_frame/{plan,validation}.md`
**Cross-refs:** 15 (per-tag attribution) · 16 (the expansion this frame replaces the selection rule of)

---

## 1. Key summary

The mentor's instruction: inventory the Multilingual suite per language, categorize tasks by
tool properties (search- / edit- / test-execution- / build-dominated), and sample **one task per
⟨language, type⟩ cell** — "there's little sense in running two build-heavy tasks from C++."
This study built that frame. Inventory: 300 instances, 41 repos — Ruby 44 · Java 43 · Rust 43 ·
PHP 43 · Go 42 · JavaScript 31 · C 30 · TypeScript 12 · C++ 12 (JS/TS are one published bucket
of 43, split here by toolchain). All 300 were classified under an adversarially-refined,
deterministic taxonomy and validated against the 12 workloads with *measured* fence
compositions. Central finding: **if "type" means the CPU mechanism, type is a function of the
language** — every language occupies exactly one mechanism class, the 9×5 grid collapses to 9
reachable cells, and the 12 already-profiled workloads cover all 9. The mentor's deduplication
is automatic at mechanism level ("another build-heavy C++ task" is the only kind there is).
The intended second axis was the **agent's behavioural mix** — but measuring it properly
(§2.2 correction) shows *all 13 banked episodes realize as search-dominated* (S = 47–84 % of
classified actions, dominant in every one), so the behavioural axis may be a property of the
agent, not of the task. The campaign therefore opens with three falsification probes (the
instances statically most likely to realize non-S) before any full sweep; cells are credited
only by an episode's *realized* type. Static prediction earned little trust twice over —
5/9 clean on the mechanism validation, and **1/10** on realized behavioural labels.

## 2. Methodology

### 2.1 Design decisions

| Decision | Value | Why |
|---|---|---|
| Static features only for selection | problem statement/hints length + traceback/repro cues, gold-patch shape (files/hunks/lines/extensions), test-patch size, FAIL/PASS_TO_PASS counts, header/build-file touches | Running 300 episodes to learn their types costs ~450 h serialized; selection must precede execution |
| Language mapping | explicit repo→language dict, **assertion-checked** against the published per-language totals | A silent mis-mapping would skew every count; the extractor exits FATAL on unmapped repos |
| JS vs TS | split by repo toolchain (babel/jest vs tsc/vitest) | Different toolchains = different columns, though the benchmark publishes them as one 43-task bucket |
| Taxonomy pipeline | adversarial critique (predictive power + sampling design) → one operational spec → 9 per-language classifiers → validation vs the 12 measured compositions → plan | A taxonomy asserted without attack would have shipped the draft's error: calling Rust "build-dominated" because it compiles (measured: `tests(rust)` 87 %) |
| Category set (mechanism) | B build-driver (C/C++) · A AOT-unified (Rust/Go) · J JVM-unified (Java) · I interpreted-suite (Ruby/PHP) · N node-transpile (JS/TS) · Y pytest placeholder (0/300) | Emerged from reconciling predictors against measured compositions; the spec's `decision_procedure` is deterministic — same CSV row ⇒ same label, no LLM needed to reapply |
| Cell-credit rule | a cell is covered by an episode's **realized** type (post-hoc, from its trajectory/tags), not its predicted type | Behaviour varies per episode (babel magnitude 5.33× across seeds); prediction is a prior |
| Magnitude as criterion | **demoted** | Within-instance episode spread (5.33×) exceeds most between-instance contrasts; select for composition, gate for adequacy after the fact |

### 2.2 Verification and honest limits

**Validation against ground truth** (`sampling_frame/validation.md`): 5 clean agreements of 9
scoreable in-corpus rows; gson agrees but is unfalsifiable as specified; both N members fail
the predicted transpile sub-term arm — which turned out to be a **tagger defect, not a taxonomy
defect** (esbuild routed to `pkg/build` by a `.pnpm/` path match; fixed in the basename rewrite,
report 16 §2.2 defect 6); tokio disagrees on the compile arm because cargo hides rustc inside
`tests(rust)` — a *visibility* limit, so class A claims a mixture and refuses to predict the
winner. The validator also caught: the `/c\+\+` word-boundary bug (29 % of fmt's argv samples
mis-tagged), and two numeric errors in my own narrative — "fmt vs gin ≈100×" (pooled-vs-single-
pass; correct 9.6×) and fmt as "class maximum" (scikit-learn is, 2988 G/pass). One validator
claim was itself wrong and is corrected here: it attributed the 5.33× spread to "replicates";
the replicates (replay passes) are 1.0× — the 5.33× is across **live episodes** (verified:
37.9/54.9/199.0/202.1 core-s, `glm_swe_babel/run_{1,5,2,4}`).

**Risk rule verdict:** the spec's pre-flight risk thresholds flag 3/3 known rejects but are
fitted to those same 3 points — usable as a cheap pre-filter, **not validated**. The plan's
"repo probe" (unpatched tree + image's test command under a `cpu.stat` poller, ~2–10 min, no
API spend) is the only honest magnitude estimator proposed.

**Limits, stated plainly:** mechanism-nested-in-language was verified by the classification
sweep over all 300 rows and spot-checked against the 12 measured episodes — not hand-verified
per instance. Behavioural type is a property of an *episode*; the same instance can yield a
search-heavy episode one seed and an edit-heavy one the next, which is exactly why cells are
credited by realized type. Static behavioural predictors (vague statement + tiny patch ⇒
search-dominated, etc.) are priors with unknown per-language accuracy until episodes land.

### 2.3 Reproduction recipe

```bash
cd $REPO/agentic/swe_agent   # needs the datasets package from this venv
taskset -c 0,1,12,13 .venv/bin/python \
  $REPO/local_agents/scripts/glm/multiling_inventory.py        # -> data/multiling_inventory.csv
# reapply the taxonomy without any LLM: taxonomy_spec.json §decision_procedure over the CSV
# artifacts: local_agents/ML_multiling/sampling_frame/{taxonomy_spec,classifications}.json
```
The taxonomy/classification/validation/plan were produced by a 14-agent workflow
(1.13 M tokens); its banked outputs in `sampling_frame/` are the record, and the spec is
deterministic so the classification is re-derivable mechanically. Costs: inventory ~1 min;
no API spend; the *resulting* campaign costs ~1.5 h exclusive-core time per cell.

### 2.4 Scripts and artifacts

| Item | Repo location | Role |
|---|---|---|
| `multiling_inventory.py` | `local_agents/scripts/glm/` | inventory + static features; language counts assertion-checked |
| `multiling_inventory.csv` | `local_agents/ML_multiling/data/` | 300 rows × 20 features |
| `taxonomy_spec.json` | `local_agents/ML_multiling/sampling_frame/` | categories, deterministic decision procedure, ambiguity/risk rules, known limits |
| `classifications.json` | same dir | all 300 assignments + per-language representatives with runners-up |
| `validation.md` | same dir | agree/disagree table vs measured compositions; accuracy verdict |
| `plan.md` | same dir | ⟨language, type⟩ matrix + run list (numeric corrections noted in its README) |
| `attribute_windows.py mix/probe` | `local_agents/scripts/glm/` | the post-episode instrument that confirms a cell's realized type |

## 3. Key insights (most → least important)

1. **Mechanism-type is nested in language** in this benchmark: 9 reachable ⟨language,
   mechanism⟩ cells, not 45 — and the 12 profiled workloads already cover all 9. The mentor's
   deduplication happens automatically at this level.
2. **The behavioural axis appears agent-dominated, not task-dominated** (corrected 2026-07-30):
   with `str_replace_editor view` counted as reading, every banked episode across 9 languages
   and 12 repos is search-dominated (S 47–84 %, T 0–46 %, E 1–18 %, B 0–18 %). The residual
   variation is a search↔test *gradient* (babel S84/T11 vs php-cs-fixer S53/T46), not discrete
   types. Whether any instance can realize E/T/B dominance is exactly what the probes test.
3. **Static prediction is a prior, not a verdict**: 5/9 clean agreement against measured
   compositions; two of the four misses were tagger visibility problems rather than taxonomy
   errors — attribution instruments and taxonomy must be debugged together.
4. **Composition is falsifiable, magnitude is not**: episode-to-episode 5.33× on one instance
   means "expected work size" cannot rank candidates; the plan orders episodes by falsifiable
   composition and uses a free repo-probe for magnitude floors.
5. **The inventory itself corrected the working numbers**: JS/TS is one published 43-bucket that
   splits 31/12; per-language counts now assertion-checked so a silent remap cannot recur.

---

**Correction (2026-07-30, same day).** The first published version motivated the behavioural
axis with "babel 72 % searches vs fmt 34 % edits". That contrast was an artifact of the
action extractor counting `str_replace_editor view` — a *read* — as an edit: fmt's 38 editor
calls are 28 `view` + 10 actual edits, so fmt is S=71 %/E=11 %, not edit-heavy. Reclassifying
all 13 banked trajectories with view=read (`behavior_classify.py labels`) yields S-dominant
for every episode. The static behavioural prior scores 1/10 against these realized labels.
Consequence: the planned one-episode-per-⟨language, behaviour⟩ sweep (20 cells, ~30 h) is not
run blindly; three falsification probes run first (`sampling_frame/behavior_plan.tsv` rows:
PHP/T phpspreadsheet-3940, JavaScript/T preact-4152, Go/E terraform-35543 — the candidates
statically most likely to realize non-S). If none realizes non-S, the honest deliverable is
the finding that SWE-agent's action mix is agent-dominated, and the ⟨language, type⟩ frame
collapses on both of its natural definitions.
