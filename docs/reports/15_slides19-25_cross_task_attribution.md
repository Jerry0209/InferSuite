# Report 15 — What each task actually runs, and why its microarchitecture differs (deck slides 19–25)

**Date of study:** 2026-07-29 · **Author of record:** Jerry0209, with Claude Code
**Deck slides:** 19–23 (per-window grids and galleries) and 24–25 (language axis) — this report
explains the *differences* those slides display; it adds no new capture of its own. Insight 8
cites the Rust language pilot (`ML_multiling`), which was captured separately while extending the
language axis; that expansion gets its own report once its languages are complete.
**Longer prose version:** analysis.md, per-window sections
**Cross-refs:** 04 (capture method) · 09–12 (metric groups) · 13 (language axis) · 14 (instrument reference)

---

## 1. Key summary

Slides 19–25 show five tasks separated by large factors on several metrics: L1D- and L2-load
MPKI and branch-direction MPKI highest for sympy and fmt, BTB-miss proxy highest for babel,
µop-cache MPKI highest for astropy and babel. The question this report answers is *why*, and
the answer is not "difficulty": **the five tasks are five different programs**, and each fence's
metrics belong to whichever program owns that fence's instructions. Identifying that program
from banked evidence — the replayed trajectory plus the 2 Hz process poll, weighted by
instructions per pass — makes every gap on the slides legible, and it retires the "one workload,
five difficulties" reading that the grid layout invites.

Tool-fence instruction-weighted episode ratios (Σevent/ΣI, the correct aggregate for an MPKI):

| metric | scikit-learn | astropy | sympy | babel | fmtlib |
|---|---|---|---|---|---|
| owning program (share of fence instructions) | pytest→NumPy/BLAS **96 %** | pytest + source build **52/17/10 %** | pytest + snippets **69/21 %** | jest/node **77 %** | cc1plus **97 %** |
| L1D-load MPKI | 0.45 | 6.38 | **7.76** | 5.25 | **8.23** |
| L2-load MPKI | 0.04 | 0.39 | **0.82** | 0.44 | **0.77** |
| branch-direction MPKI | 0.18 | 1.72 | **3.05** | **3.70** | **4.56** |
| branch-indirect MPKI | 0.09 | 1.24 | 1.42 | 0.59 | 0.31 |
| BTB MPKI (BAClears) | 0.08 | 0.28 | 0.34 | **1.46** | 0.81 |
| µop-cache MPKI | 22.95 | **63.51** | 54.01 | **61.29** | 53.34 |
| DSB coverage % | 83.4 | 52.6 | 58.2 | 58.8 | 62.3 |
| MLP | **3.17** | 1.70 | 1.85 | 1.66 | 1.62 |
| vector-FP share % | **54.8** | 2.7 | 0.02 | 0.09 | 0.00 |
| tool-fence work (Ginstr/pass) | 2890 | 1377 | 559 | **190** | 1311 |

The study also corrected three defects in shipped artifacts (§2.2): a truncated axis label that
rendered JavaScript as **"Java"**, a plotter that **silently dropped** unknown command tags, and
a command tagger with **no non-Python test-runner rules**, which had been mislabelling babel's
jest runs as `shell`.

## 2. Methodology

### 2.1 Attribution design

| Decision | Value | Why |
|---|---|---|
| Aggregate for a ratio metric | instruction-weighted Σevent/ΣI | The median over windows weights a 30-Ginstr window equally with a 0.6-Ginstr one. Both are printed and must agree on the headline gaps; that agreement is the check, not decoration |
| Resolution test | median + p25–p75 per task | Each metric comes from exactly **one** dedicated pass per task, so there is no within-task replicate. Gaps narrower than the IQR are declared unresolved rather than reported |
| Cross-metric joins | forbidden per window | Different counter groups occupy different windows (cache → run_4, fe_miss → run_11). Only a metric and *its own pass's* command log may be joined per window |
| Program identification | replayed trajectory + 2 Hz poll, per pass | Action counts describe agent behaviour; instruction shares describe where CPU went. They diverge sharply (babel: 72 % of actions are searches, 77 % of instructions are JavaScript) |
| Which trajectory | the one named in `metadata.json` `extra.traj` | The astropy and sympy L3 studies replayed **run_2, not run_1**. Reading run_1 misattributes the workload — the first attempt at this report did exactly that |
| Toolchain-presence probe | regex over polled argv, instruction-weighted | Presence over-credits a program (processes coexist in a 2-s window) but bounds the opposite error, which is the one that matters: a language cannot be credited for work in windows where its runtime never appeared |

Ground truth per task (`attribute_windows.py work` + `mix`):

- **scikit-learn** `scikit-learn-25232` — `python -m pytest sklearn/impute/tests/`; the imputer
  tests drive repeated regression fits, i.e. NumPy/BLAS dense linear algebra. 96 % of fence
  instructions in pytest windows, 54.8 % of FP arithmetic vectorised, MLP 3.17.
- **astropy** `astropy-14096` (run_2) — `python -m pytest astropy/coordinates/tests/` **plus**
  `pip download astropy==5.3.1 --no-deps --no-binary :all:`, which compiles from source. Hence a
  mixed fence: pytest 52 %, python-other 18 %, pkg/build 17 %, compile 10 %.
- **sympy** `sympy-14248` (run_2) — `sympy.utilities.runtests` on the printer tests plus 56
  distinct `python -c` snippets building `MatrixSymbol` expressions and printing them: recursive
  expression-tree traversal, `isinstance` dispatch, cached `dict` lookups. pytest 69 %,
  python-other 21 %.
- **babel** `babel-15445` — `BABEL_ENV=test yarn jest …` and `node reproduce_issue.js` under V8,
  amid heavy `grep`/`find`/`cat` searching. Only 31 % of windows contain the JS toolchain but
  those windows carry **77–78 %** of fence instructions.
- **fmtlib** `fmt-3248` — `make` → `/usr/bin/c++` → **cc1plus** compiling the fmt test suite
  (header-only, template-heavy), then running `./bin/format-test`. 97 % compile.

### 2.2 Verification, rejected hypotheses, and defects fixed

**Two mechanisms tested and rejected.** A cold BTB after an exec is a real effect and was the
obvious candidate for babel's BAClears. Neither proxy supports it — per-task signs disagree, so
no single mechanism is carried by the data (`attribute_windows.py churn`):

| proxy vs BTB_MPKI (same-pass per-window join) | scikit | astropy | sympy | babel | fmtlib | pooled |
|---|---|---|---|---|---|---|
| concurrent PIDs in window | −0.256 | +0.008 | −0.764 | −0.078 | −0.345 | **−0.172** |
| newly-appearing PIDs (exec-rate proxy) | +0.475 | +0.043 | −0.584 | −0.191 | −0.197 | **+0.193** |

Spearman over 359 tool windows. The BTB gap is therefore reported **descriptively** — it tracks
program identity — and no causal claim is made.

**Cross-check that did hold.** babel's JavaScript share was obtained two independent ways: the
toolchain-presence probe gives 78.2 % of instructions in windows containing jest/node/yarn/npm,
and re-deriving the window tags with the extended tagger gives `tests(js)` = 77 %. Agreement
between a regex over raw argv and the priority-tagged window label is what licenses calling
babel's numbers a JavaScript measurement despite the old `shell` label.

**Defect 1 — the "Java" axis label (shipped in figures).** `cross_task_grid.py` built tick
labels with `LANG[t][:4]`, so `"JavaScript"` rendered as `Java` — the name of a *different*
SWE-bench-Multilingual language — and `"Python"` as `Pyth`. Fixed with an explicit `SHORT` map
(`Py`/`JS`/`TS`/`C++`/`Rb`/`Java`/`PHP`/`Rs`/`Go`) and a `slang()` accessor; grids regenerated.
The underlying `LANG` data was always correct, and instance IDs confirm it: `babel__babel-15445`
is the Babel JavaScript compiler, `fmtlib__fmt-3248` the fmt C++ library. **No Java instance has
ever been profiled.**

**Defect 2 — the tagger had no non-Python test runners.** `tag_of()` recognised only pytest, so
`jest`/`rspec`/`gradle`/`phpunit`/`cargo test`/`go test` fell through to `other`, which
`TAG_PRIORITY` ranks *below* `shell`; a JS test sharing a window with its parent bash was
labelled `shell`. Report 13/14 flagged the resulting missing test bar as a labelling artifact;
it is now fixed rather than merely documented. Added per-language `tests(...)` rules, compiler
rules (including `cc1plus`, which `\bcc1\b` never matched), package/build front ends
(`yarn`/`npm`/`bundler`/`composer`/`cargo`/`go build`), and `node-/ruby-/java-/php-other`
fallbacks — all ranked above `shell`. Effect, verified by re-deriving from banked logs:

| task | tags before | tags after |
|---|---|---|
| babel | shell 80 %, git 16 %, python-other 4 % | **tests(js) 77 %**, shell 12 %, git 8 %, node-other 1 % |
| scikit-learn / astropy / sympy / fmtlib | — | **byte-identical** (no regression) |

Re-deriving is free: tags are computed at analysis time from banked `cmdlog.tsv`, so no
re-capture was needed. Regenerating `all_windows_babel.csv` changed **0 of 1306 values** and
219 tags, all in the expected direction.

**Defect 3 — the plotter silently dropped unknown tags.** `analyze_l3_windows.py` selected tag
rows by iterating `TAGCOL`'s keys, so a tag absent from that colour dict vanished from the box
panels and the legend while `ALL` still counted its windows — the rows stopped summing to the
total (babel: 14 shown of 20). Replaced with a data-driven `tags_present()` ordered by
`TAG_PRIORITY`, with a fallback colour, so a new tag can never go missing again.

**A retracted claim.** An earlier reading of this data attributed astropy's low
branch-direction MPKI to "more predictable array loops". That is unsupported: astropy's fence is
library-import and framework-heavy Python plus a source build. The defensible statement is about
*which* branch structure fails — see insight 4.

### 2.3 Reproduction recipe

Free, no capture, no API spend; seconds to run. Plotting needs the `infersuite-full` conda
env — matplotlib is **not** in the system interpreter on this workstation (the older
"plot with system python3" convention in CLAUDE.md is stale).

```bash
cd local_agents/scripts/glm
PY=/home/thu/miniforge3/envs/infersuite-full/bin/python3

$PY attribute_windows.py                 # all sections
$PY attribute_windows.py table           # weighted ratios + median/IQR, both fences
$PY attribute_windows.py mix probe       # who owns each pass's instructions
$PY attribute_windows.py churn work      # rejected hypotheses; ground-truth workloads

# after a tagger change, re-derive tags + figures from banked logs (no re-capture):
$PY analyze_l3_windows.py /home/thu/InferSuite/local_agents/SWE_clean/data babel --plot
$PY cross_task_grid.py                   # 5-task grids with corrected language labels
$PY build_metric_gallery.py --plots <l3_study>/plots --out <dir> babel
```

Expected: values reproduce exactly (banked CSVs are inputs). A *new* capture reproduces
phenomena and shares, not exact trajectories or absolute Ginstr.

### 2.4 Scripts and artifacts

| Item | Repo location | Role |
|---|---|---|
| `attribute_windows.py` | `local_agents/scripts/glm/` | **new** — every number in this report: weighted/median tables, per-tag and per-pass composition, toolchain-presence probe, churn tests, workload identification |
| `analyze_l3_windows.py` | same dir | `tag_of()` + `TAG_PRIORITY` extended for multilingual toolchains; `tags_present()` replaces the TAGCOL-keyed selection |
| `cross_task_grid.py` | same dir | `SHORT`/`slang()` replace `LANG[t][:4]` |
| `build_metric_gallery.py` | same dir | per-task galleries (33 metrics × 4 views) |
| Per-window CSVs | `local_agents/{superseded_40min,SWE_clean}/data/l3_study/all_windows_*.csv` | banked source of every value |
| Command logs | `.../glm_replay_swe_<task>/run_*/cmdlog.tsv` | 2 Hz tool-cgroup process poll, same epoch clock as `windows.tsv` |
| Trajectories | `.../glm_swe_<task>/run_*/traj/<instance>/*.traj` | ground-truth actions; `metadata.json` `extra.traj` names the replayed one |
| Figures | `.../l3_study/plots/cross_task_grid_{tool,harness}.png`, `box_*`/`timeline_*` | regenerated with corrected labels and tags |

## 3. Key insights (most → least important)

1. **The tasks differ by program, not by difficulty — and one of them is not like the others.**
   scikit-learn's fence is 96 % NumPy/BLAS SIMD kernels: 54.8 % vectorised FP, MLP 3.17, AMAT
   5.03 cycles, near-zero misses everywhere. The other four have **essentially zero vector FP**
   (0.00–2.68 %) and are scalar, branchy, pointer-chasing programs. Every "high" value on slides
   19–23 is high *relative to a dense-linear-algebra baseline*, which is why the grid's spread
   looks dramatic. Quote the owning program with any cross-task number.
2. **sympy's and fmt's memory pressure is dependent-load pointer chasing, and MLP proves it.**
   L1D 7.76 and 8.23 MPKI, L2 0.82 and 0.77, at MLP 1.85 and 1.62 versus scikit-learn's 3.17 —
   few misses in flight means one load's address comes from the previous load's result. This is
   symbolic expression trees (sympy) and AST/symbol tables (cc1plus), not streaming. Both also
   reach further down the hierarchy than astropy (LLC 0.12/0.23 vs 0.08; DRAM-bound 3.8 %/6.6 %
   vs 2.0 %). sympy's L1D IQR overlaps astropy's, so *that* pair is unresolved; the L2 and DRAM
   separations are clean.
3. **Direction misses come from data-dependent control flow; the tagger locates them within a
   task.** Weighted branch-direction MPKI is 4.56 (fmt), 3.70 (babel), 3.05 (sympy) against 1.72
   (astropy) — so babel belongs in the "high" group too, which the original framing of the
   question omitted. Within astropy the split is visible: its own `compile`-tagged windows reach
   4.48, matching fmt's 4.16, while its pytest windows sit at 1.14. Compiler parsing and
   symbolic rewriting mispredict; library-framework Python does not.
4. **astropy and fmt fail in opposite branch structures — the interesting result behind
   astropy's low direction MPKI.** Taking indirect ÷ direction misses: astropy 1.24/1.72 = 0.72
   (indirect-dominated — interpreter dispatch and virtual calls, mispredicted by *target*),
   fmt 0.31/4.56 = 0.068 (almost purely direction). Same "branchy" label, opposite front-end
   failure mode. This supersedes the retracted "predictable loops" claim (§2.2).
5. **µop-cache pressure is instruction-footprint pressure, and three counters agree.** astropy
   63.5 and babel 61.3 MPKI coincide with the lowest DSB coverage (52.6 %, 58.8 %), the highest
   legacy-decode share (45.1 %, 38.5 %), and L2 code-read ≈ 20–21 MPKI — a large, flat,
   non-looping footprint: CPython plus many compiled extensions, and V8 plus JIT-emitted code.
   The contrast confirms the reading: fmt's compile windows sit at 38.7 with 72.1 % DSB coverage
   (cc1plus has hot inner loops that fit), scikit-learn at 22.9 with 83.4 %.
6. **babel's BTB result is real but rests on the least evidence in the study.** 1.46 weighted
   MPKI, ~1.8× fmt and ~5× astropy, and the tag split now puts it in the right place:
   `tests(js)` windows ≈1.6 and `node-other` 1.75 against `compile` 0.75 and `git` 0.2. But
   babel's fence is the smallest measured (190 Ginstr/pass vs 1311–2890) across only 20 windows,
   and its IQR overlaps fmt's. Treat "babel ≫ astropy/sympy/scikit-learn" as established and
   "babel > fmt" as not resolved. Both churn mechanisms were tested and rejected (§2.2).
7. **A language axis is only meaningful when the language's toolchain owns the fence.** fmt is
   the clean case (97 % compile); babel needed a raw-argv probe to establish 78 %. An instance
   where the agent mostly greps would measure `grep`, not the language. **Before profiling more
   of SWE-bench Multilingual, verify per-pass composition with `attribute_windows.py mix probe`
   and treat a language whose toolchain owns <50 % of fence instructions as unprofiled** — the
   tagger rules for Ruby/PHP/Go/Rust/Java/C now exist but are, as of this report, **untested
   against real logs for those languages**.
8. **A third tagger defect, found the moment a compiled language arrived (2026-07-29).** The
   pytest rule's fallback clause was `"testbed" in argv and " -m " in argv and "test" in argv`,
   intended for `python -m pytest`. The GNU linker satisfies all three independently: `/testbed`
   is the SWE-bench working dir, `-m elf_x86_64` supplies the `-m`, and a test-binary name
   supplies "test". Every link window in a compiled language was therefore labelled as a Python
   test run — **36 % of Rust's tool-fence instructions**. Invisible across a year of Python
   campaigns because those tasks barely link. Fixed by requiring a real python binary on that
   branch (plus `collect2` added to `compile`); all five pre-existing tasks re-derive
   byte-identical. Pattern worth internalising: each new language has now exposed one silent
   tagger defect (JS → no test-runner rules; Rust → linker false-positive).
9. **Silent-drop defects are the dangerous class.** Both the `Java` truncation and the TAGCOL
   omission produced figures that looked complete and were wrong — one mislabelled a language,
   the other left tag rows not summing to their own total. Neither would have been caught by the
   figure audit, which recomputes plotted *values*, not labels or completeness.

---

**Method update (2026-07-30).** `analyze_l3_windows.py` and `cross_task_grid.py` changed after
this report: the command tagger now matches program **basenames** instead of argv substrings
(report 16 §2.2, defect 6), which retro-corrects three labels this report's era produced
elsewhere (rubocop-as-`pkg/build`, esbuild-as-`pkg/build`, `/usr/bin/c++` never matching
`compile`) — and resolves §2.2's "maven matched by path, luck not design" caveat: maven-jar
path evidence is now an explicit deliberate rule. Counter values are untouched (0-value diffs
re-derived on all 13 tasks); the five tasks analysed here re-derive with identical tags except
the documented fmt `pkg/build`↔`compile` window bookkeeping. `cross_task_grid.py` additionally
gained per-task roots for the 12-task axis and `TASKS_ONLY`/`GRID_SUFFIX` frozen-subset grids;
later the same day both registries gained the behavioural-probe task `phpoffice-bT`
(13-task grid; report 17 §2.4). None of this alters this report's numbers.

---

**Method update (2026-07-30, late).** `analyze_l3_windows.py` gained cache **miss-rate**
metrics (and `cross_task_grid.py` a `GRID_LAYOUT=16` rearranged grid) on the mentor's request —
additive only; every number this report documents is unchanged. Details: report 11's note.
