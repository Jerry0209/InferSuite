# Verification of the multilingual tool-property taxonomy

Everything below was recomputed from banked data, not read from the spec. Verification scripts are in `/tmp/claude-1006/-home-thu-InferSuite/d89d5011-7a68-46e3-b344-4c6f84677c31/scratchpad/` (`csv_check.py`, `elig.py`, `labels.py`, `argv.py`, `argv2.py`, `argv3.py`, `cores2.py`, `stats.py`, `sp2.py`, `traj.py`). Sources: `/home/thu/InferSuite/local_agents/ML_multiling/data/multiling_inventory.csv`, the `l3_study/all_windows_*.csv` + `glm_replay_swe_*/run_*/cmdlog.tsv` trees under `local_agents/{ML_multiling,SWE_clean,superseded_40min}/data`, and `local_agents/kit/replay/analyze_l3_windows.py` (the tagger, `tag_of` + `TAG_PRIORITY`, lines 30–98).

**What checks out first, so the rest is credible.** The 41-repo lookup table is a genuine total function over all 300 rows (42 B + 85 A + 43 J + 87 I + 43 N = 300, no repo missing, no repo unused). Eligibility reproduces exactly: 2 X-DEGEN, 104 X-SMALL, 194 eligible, split B 42 / A 47 / J 42 / I 41 / N 22. `ps_has_traceback` = 17/300 and is identically 0 for C++, JS, PHP, Ruby, TS; `ps_has_repro` = 265/300; `touches_build` fires on exactly axios-5316, carbon-2813, axum-682. All 12 published fence compositions reproduce from the banked window CSVs to within pass-to-pass noise. The argv counts quoted in `known_limits` are exact where I could check them: rubocop `pkg/build` = 652, vue `pkg/build` = 532 of which 523 are `@esbuild/linux-x64/bin/esbuild`, prometheus `compile` = 5234, tokio compile 1698 vs tests(rust) 775, gin total 261 argv samples. This is careful work. The problems below are not sloppiness; they are structural.

---

## 1. Agree / disagree table

Measured composition = median over the 10 dedicated-group passes. "Class prediction" is the literal predicate from `static_predictors`.

| # | task (class) | measured composition (median) | HHI | class predicate | verdict |
|---|---|---|---|---|---|
| 1 | fmt-3248 (B) | compile 97, shell 2, pkg/build 1 | 0.941 | build ≥60 ✓ (98), runner <30 ✓ (0) | **AGREE** |
| 2 | jq-2681 (B) | compile 61, pkg/build 31, shell 8 | 0.475 | build ≥60 ✓ (92), runner <30 ✓ (0) | **AGREE** |
| 3 | prometheus-9248 (A) | compile 62, tests(go) 28, pkg/build 6 | 0.467 | compile ≥20 ✓, runner ≥20 ✓, HHI<0.65 ✓ | **AGREE** |
| 4 | tokio-6551 (A) | tests(rust) 87, compile 10, shell 3 | **0.768** | compile ≥20 ✗ (10), HHI<0.65 ✗ | **DISAGREE (2 of 3 arms)** |
| 5 | gson-2061 (J) | tests(java) 89, compile 7, java-other 3 | 0.798 | tests(java) ≥75 ✓, compile ≤15 ✓ | **AGREE — but unfalsifiable, see §2** |
| 6 | vue-11915 (N) | tests(js) 99, shell 1 | 0.980 | runner 70–99 ✓ (edge), transpile 5–35 ✗ (**0**) | **HALF-DISAGREE** |
| 7 | php-cs-fixer-7523 (I) | tests(php) 97, shell 3 | 0.942 | runner+app ≥90 ✓, compile 0 ✓ | **AGREE** |
| 8 | rubocop-13668 (I) | pkg/build 54, tests(ruby) 41, ruby-other 3 | 0.461 | runner+app ≥90 ✓ (95–98), compile 0 ✓ | **AGREE only after manual argv re-read** |
| 9 | babel-15445 (N) | tests(js) 77, shell 13, git 7, compile 3 | 0.616 | runner 70–99 ✓, transpile 5–35 ✗ (3) | **HALF-DISAGREE** |
| 10 | astropy-14096 (Y) | pytest 52, python-other 18, pkg/build 17, compile 10 | 0.343 | *"No predictor is needed or offered"* | **UNSCOREABLE** |
| 11 | sympy-14248 (Y) | pytest 69, python-other 21, shell 7 | 0.526 | idem | **UNSCOREABLE** |
| 12 | scikit-learn-25232 (Y) | pytest 96, python-other 3 | 0.923 | idem | **UNSCOREABLE** |
| +13 | **gin-3741 (A)** — CTX omits its composition, but it is banked | **tests(go) 61, shell 16, python-other 15, pkg/build 6, compile 2** | 0.424 | compile ≥20 ✗ (**2**) | **DISAGREE** |

**Count: 5 clean agreements out of 9 scoreable in-corpus rows.** 1 nominal agreement that cannot be falsified (gson), 2 half-disagreements (both N members fail the transpile arm), 1 outright disagreement (tokio), plus gin which makes it 2 outright disagreements out of 10. The three Y rows cannot be counted either way: category Y explicitly offers no predictor, so it cannot be right. Scoring 12/12 requires counting three no-predictions as successes and grading tokio, vue and babel on their passing arm only.

**Per class:** B 2/2. A **1/3**. J 1/1 but vacuous. I 2/2 (one conditional). N **0/2** on the transpile arm, 2/2 on the runner arm. Class A — the largest class in the corpus at 85 instances, 47 eligible — is refuted by two of its three measured members.

---

## 2. Where they disagree: which side is wrong

**tokio (A) — the taxonomy is wrong, the measurement is a tagger artefact, and both.** `TAG_PRIORITY` (line 95) puts every `tests(X)` above `compile`, and `tag_for` awards one winner per window. `cargo test` is a persistent front-end that sits in every window it spawns rustc into, so it eats its own children. Confirmed: tokio's own argv log is compile 1698 vs tests(rust) 775 — 2.2× compile — while the window composition says 8.7× test. The ordering inverts. CTX names this. But CTX then draws the wrong conclusion: it says class A "predicts a MIXTURE and refuses to name the winner", which reads as a defensible retreat, and it is not — a class whose composition predicate is `compile ≥20 AND runner ≥20 AND HHI <0.65` **is** a falsifiable claim, and tokio fails two of three arms on the published numbers. Either the arms are dropped or class A is refuted. It cannot be both.

**gin (A) — the taxonomy is wrong and CTX hid the evidence by not quoting the composition.** gin measures compile = **2%**. There is no tagger story that rescues this: gin's `compile` bucket is 11 of 261 argv samples. A small Go module genuinely does almost no compilation, because the SWE-bench image ships a warm build cache. So class A's "one command compiles the closure, then runs" is false for the smaller half of its own membership, and 47 eligible A instances inherit an unvalidated prediction. Also 15% of gin's fence (`python-other` = 39 argv samples, apt/dpkg/`py_compile`) is container bootstrap, not agent work — I measure 36/261 = 13.8%, so CTX's "38 of 261, 15%" is right.

**gson (J) — the measurement does not reflect the task's type, and the class prediction is unfalsifiable by construction.** This is the finding CTX misses, and it is worse than the three artefacts CTX does list. gson's entire `compile` bucket is **75 argv samples, and every one of them is the agent's own scratch reproducer**: `javac -d build /tmp/Repro.java`, `/tmp/Repro2.java`, `/tmp/VerifyUpstreamTests.java`, `javac -version`. Not one is the repo build. The repo's bytecode compilation happens inside the maven JVM via the in-process JDK compiler API — the 777 `java -classpath .../plexus-classworlds` samples — so **no `javac` process exists for the tagger to see, ever, in any maven repo.** Class J predicts `compile ≤ 15%`; that prediction is guaranteed true for all 42 eligible J instances regardless of how much javac work occurs, and the 7% it was "confirmed" by measures agent scratch behaviour. J is not a validated class; it is a tautology, and gson — "the single most important calibration row in the study" — calibrates nothing about the build.

**fmt / jq (B) — both agree, but for opposite and accidental reasons, and there is a fourth tagger defect neither reviewer named.** `tag_of`'s compile regex does not match the GCC C++ driver: `/c\+\+\b` cannot match `/usr/bin/c++ ` because there is no word boundary between `+` and a space. Measured on fmt: **10,100 of 34,634 argv samples (29%) are `/usr/bin/c++`, and they are tagged `other` (5093) or `shell` (5007) — never `compile`.** The only reason fmt reads "compile 97%" is that `cc1plus` (5065 samples) happens to co-occur in the same 5 s windows and outranks `other`/`shell`. Meanwhile fmt's `make` family is 8838 samples — 25.5% of all argv, the single most-polled program — and the window composition reports `pkg/build` = **1%**, because `compile` outranks `pkg/build`. jq shows the mirror image: `pkg/build` = 31% of instructions, because jq's compiles are short enough that many windows catch make alone. So the two members of class B, running the same physics (make-driven C/C++ build), report `pkg/build` 1% and 31%. Class B's predicate survives only because it pools `compile+link+make`; its per-member descriptions ("compile 97%" vs "compile 60% + pkg/build 32%") are window-sampling artefacts and must not be read as a physical difference between the repos.

**vue / babel (N) — the class is right about the runner and unsupported about the transpile term.** N asserts "a transpile sub-term of 5–35%". vue measures 0% (esbuild is 523 argv samples but `pkg/build` carries 0% of window instructions); babel measures 3%. The sub-term is asserted from an argv *sample count* and predicted as an *instruction share* — two different quantities, and `attribute_windows.py`'s own docstring says argv poll counts are not instruction-weighted. Delete the arm or measure it; do not publish it as a prediction.

**prometheus — CTX's own correction commits the error it criticises.** The compile bucket breaks down as 61.9% real `pkg/tool/linux_amd64/{compile,link,asm}`, 29.1% the compiled test binary `/tmp/go-build*/b001/rules.test`, 8.2% `go vet`. CTX says 54/32/8 — directionally right, numerically off by 8 points. More importantly, CTX's inference "corrected, prometheus is much closer to 50/50" reallocates an *instruction* share in proportion to *argv sample* counts. That is exactly the unweighted-argv fallacy the spec warns against in `known_limits` #3's own caveat. The correction may well be right; it is not established by the arithmetic given.

**One CTX claim is simply wrong on the data.** "jq argv poll = make 1437 + gcc/libtool 1760." Compile = 1760 ✓ exact. But 1437 is `make check` (739) + bare `make` (698) only; jq's full make family is **4845** samples, 24% of its argv. The number understates its own bucket 3.4×.

**And one that CTX gets right, which I can independently confirm.** Deleting category S is correct. My own action classification over the live trajectories gives search/read 41–86% of actions for *every* task, and the ordering is anti-correlated with fence size — prometheus is the most search-heavy at 86% and has the largest fence (383 core-s). Action mix carries no CPU information. `ambiguity_rule` #5 is sound.

---

## 3. The risk rule against the three rejects: it does not work as advertised

| reject | R1 ps_chars<150 | R2/R3 scope gate | Layer-3 ≥20 core-s | Layer-3 ≥1000 Ginstr | E7 uniqueness |
|---|---|---|---|---|---|
| carbon-2813 (I) | **FIRES** (124) | would fire (scope 4 < 20) | *no banked data* | *no banked data* | fires (longest identical run 12, uniq 0.61) |
| laravel-51890 (I) | passes (741) | **FIRES** (scope 9 < 20) | *no banked data* | *no banked data* | **would also fire (longest identical run 12, uniq 0.84)** |
| gin-3741 (A) | passes (453) | **FIRES** (scope 2 < 10) | **PASSES — 29.3 core-s** | fires (137 Ginstr) | marginal (uniq 0.87) |

**Layer 1 does flag all three before spend. That part is usable.** But three things about how it is justified are not.

**(a) The floor-calibration story is false.** `risk_rule` states: "20 core-s comes from the three rejects (6.4, 6.6, and a 137 Ginstr fence, **all under 7 core-s**) versus the smallest accept (rubocop, 59.1) … the gap 7 → 59 is wide and unpopulated." gin's tool fence, summed from `cpustat_scope2.tsv` exactly as every accepted number was (`gen_manifest.py:132`: *1=harness, 2=tool, 3=proxy*), is **29.3 core-s**. gin sits in the middle of the gap that is claimed to be empty. The 20 core-s threshold does not separate the rejects from the accepts; only the ≥1000 Ginstr arm rejects gin — and since **Spearman(core-s, Ginstr) = 1.00** across all 10 verified episodes, the two arms of the Layer-3 gate are rank-redundant, which means one of them is calibrated wrong. Re-derive the floor, or drop the core-s arm and keep Ginstr.

**(b) Two of the three rejects have no banked measurement at all.** `agentic/swe_agent/runs/glm_live/briannesbitt__carbon-2813_r1/` and `.../laravel__framework-51890_r1/` contain only `.traj`, `.config.yaml` and logs. There is no `cpustat_scope*.tsv`, no `l3_study` CSV, no replay directory anywhere in the tree. The quoted 6.6 and 6.4 core-s and laravel's "split-half IPC unstable 27%" cannot be reproduced. The gate is therefore "validated" against 1 measured reject and 2 remembered ones.

**(c) The R2 slope is fitted almost entirely on those two unverifiable points.** "within-PHP measured slope ≈ 0.43 core-s per test, intercept ≈ 5" reproduces only from carbon (4 → 6.6) and laravel (9 → 6.4) plus php-cs-fixer (237 → 105.3). On the two *verifiable* class-I points the two-point line is **slope 0.241, intercept 48.3** — a 10× larger intercept, which is the difference between a fixed cost that can be ignored and one that dominates. Every PHP `expected_fence_size` in the per-language sections is computed from `2.94 + 0.432·scope`; the verified line gives materially different answers (carbon-3103: 22.8 predicted vs 59.4; php-cs-fixer-7998: 32.7 vs 64.9; phpspreadsheet-3940: 28.4 vs 62.5). Three of the four PHP picks were selected on their margin above a 20 core-s floor using a line whose intercept is understated ~10×.

**(d) The one thing that actually discriminates all three rejects is the free, measured E7 gate.** uniqueness 0.61 / 0.84 / 0.87 for the rejects vs 0.96–0.97 for the accepts, and longest-identical-action-run = 12 for both carbon *and* laravel. Note that laravel is degenerate by the exact criterion carbon was rejected for — CTX attributes laravel's rejection to IPC instability and never notices it is a loop. E7 is the load-bearing gate. Promote it; stop asking the static features to do this job.

**Verdict on the risk rule: Layer 1 is usable as a cheap pre-filter, and nothing more.** It flags 3/3 — but with 4 thresholds fitted to 3 points, 2 of which have no data behind them, and a floor whose stated justification is contradicted by the one reject that was measured. It is not validated. It is consistent with a story that was partly reconstructed from memory.

**The deeper problem, and it is fatal to the magnitude half of the spec.** On all 10 episodes with verified `cpustat_scope2` fences:

| instance | scope | tool core-s | Ginstr/pass | core-s per selected test |
|---|---|---|---|---|
| gson-2061 | 6 | 270.8 | 1475 | **45.1** |
| prometheus-9248 | 12 | 383.3 | 1618 | 31.9 |
| tokio-6551 | 22 | 192.3 | 696 | 8.7 |
| gin-3741 | 2 | 29.3 | 137 | 14.7 |
| jq-2681 | 28 | 65.8 | 398 | 2.3 |
| vue-11915 | 45 | 214.5 | 788 | 4.8 |
| rubocop-13668 | 45 | 59.1 | 339 | 1.3 |
| babel-15445 (run_1) | 56 | 37.9 | 189 | 0.68 |
| fmt-3248 | 117 | **270.5** | 1313 | 2.3 |
| php-cs-fixer-7523 | 237 | 105.3 | 566 | **0.44** |

**Spearman(tool core-s, scope) = −0.055.** The spec reports +0.32; that value reproduces only on the n=12 set that includes the two unverifiable rejects (+0.294). On verified data alone the sign flips and the magnitude vanishes. Per-test cost spans 102× (0.44 → 45.1). **Scope has no measured relationship to the fence, yet scope is the sole hard exclusion criterion and it discards 104 of 300 instances — 35% of the corpus.**

Two corollaries the spec has backwards. `Spearman(core-s, patch_add) = +0.358` on the verified set, not −0.08; it is the *best* static correlate available, better than scope (−0.055) and than ps_chars (−0.321). The spec puts patch_add on the explicit "do NOT use as risk predictors" list and deletes category E on the strength of the −0.08 figure. And fmt's tool fence is **270.5 core-s** — the spec records it as "n/a" while quoting the same quantity for seven other tasks from the same file.

---

## 4. Representative sanity check

I re-ran STEP 0 → STEP 4 over the CSV and compared to the labels the per-language sections assert.

| representative | asserted | recomputed | scope | eligible in repo | eligible in cell | in cell ∧ language |
|---|---|---|---|---|---|---|
| **jordansissel__fpm-1829** | "I", "zero W-NOLEV" | **I.F, W-NOLEV** | 47 | **1** | 5 | 3 |
| rubocop-13424 | I.L | I.L ✓ | 143 | 13 | 11 | 4 |
| rubocop-13503 | I.S | I.S ✓ | 23 | 13 | 14 | 5 |
| lombok-3009 | J.L | J.L ✓ | 323 | 17 | 10 | 10 |
| lucene-12196 | J.M | J.M ✓ | 12 | 8 | 12 | 12 |
| lombok-3602 | J.S | J.S ✓ | 2 | 17 | 12 | 12 |
| druid-16875 | J.F | J.F ✓ | 3 | 5 | 8 | 8 |
| ruff-15356 | A (L-end) | A.L ✓ | 134 | 5 | 7 | 5 |
| laravel-48636 | I.L | I.L ✓ | 168 | 7 | 11 | 7 |
| carbon-3103 | I.M | I.M ✓ | 46 | 7 | 11 | 7 |
| php-cs-fixer-7998 | I.S | I.S ✓ | 69 | 9 | 14 | 9 |
| phpspreadsheet-3940 | I.F | I.F ✓ | 59 | **2** | 5 | 2 |
| **gohugoio__hugo-12448** | "A.L, zero warn flags" | **A.F, W-NOLEV** (hugo eligible scopes 13/24/24/35, spread 2.69× < 3) | 35 | 4 | 24 | 17 |
| preact-4152 | N.L | N.L ✓ | 76 | 8 | **4** | 3 |
| redis-13115 | B (L-end) | B.L ✓ | 184 | 12 | 8 | 5 |
| **facebook__docusaurus-9897** | "N.L, zero warn flags" | **N.F, W-NOLEV** (docusaurus 35/36/92, spread 2.63× < 3) | 92 | 3 | 6 | 5 |
| nlohmann__json-4237 | B, W-NOLEV noted | B.F ✓ | 22 | **1** | 15 | **1** |

**Three of seventeen representatives carry a tier the spec's own STEP 3 contradicts, all in the same direction** — claimed high-leverage `L` where the rule yields flat `F` + W-NOLEV. In two of the three the section explicitly *rejected an alternative for being W-NOLEV* and then picked a W-NOLEV instance: Go rejects terraform-35543 because "the spec restricts W-NOLEV instances to negative-control duty" and picks hugo-12448 (W-NOLEV); TypeScript flags immutable-js as "a W-NOLEV negative control" downside and picks docusaurus-9897 (W-NOLEV). Ruby's *primary* class-I representative, fpm-1829, is W-NOLEV in a 1-eligible-instance repo and the section states "zero W-BIGDIFF/W-NOLEV/W-CONFOUND". Under `ambiguity_rule` #3 these three are admissible only as negative controls.

**Sole-candidate representatives.** `nlohmann__json-4237` is the only eligible instance in its repo, the only non-X-DUP C++ instance in the corpus, and 1-of-1 in its (cell ∧ language) slot. It is not a sample of anything — it is the population, and calling it a representative is a category error. `phpspreadsheet-3940` has exactly one alternative (the spec concedes "if both park, phpspreadsheet is simply unrepresentable"). `fpm-1829` is 1-of-1 in its repo. `preact-4152` sits in the smallest cell in the frame (N.L, 4 eligible; 3 in JavaScript).

**Repo over-representation.** rubocop ×2 and lombok ×2 among the 17 proposed; combined with the banked set, rubocop would carry **3** episodes. Five of the seventeen (rubocop-13424, rubocop-13503, laravel-48636, carbon-3103, php-cs-fixer-7998) re-spend already-banked repos and need STEP 1g X-DUP exemptions. The per-language budget comes out inverted: Ruby (44 instances) would get 3 new episodes while Rust (43) and Go (42) get 1 each, and C++ (12) gets its only possible one.

**The frame itself is misstated.** STEP 4 says "5 mechanisms × 3 tiers = 15 cells". The tier function has four outcomes because W-NOLEV produces `F`, and **F holds 58 of 194 eligible instances — 30%, the second-largest tier.** The real frame is 20 cells, all 20 non-empty: B {S10 M9 L8 F15}, A {S8 M8 L7 F24}, J {S12 M12 L10 F8}, I {S14 M11 L11 F5}, N {S7 M5 L4 F6}. And the banked accepts cover **8** cells, not 9 — prometheus-9248 and tokio-6551 both label A.M (B.L, B.F, A.M, J.L, N.M, N.S, I.L, I.M). So "9 of 15" is wrong twice, and the selection rule's premise that the frame is nearly filled is wrong in the safe direction for the argument it wants to make.

**Finally, `known_limits` #7 is false, and its falsity is the most important number in this review.** It says "EVERY BANKED CELL IS n = 1. No spread can be reported anywhere." `local_agents/SWE_clean/data/glm_swe_babel/` holds **four independent live episodes of the same instance** — `metadata.json` confirms `instance: babel__babel-15445` in all four, same model, same temperature, same repo_rev. Their tool fences are **37.9, 54.9, 199.0, 202.1 core-s: a 5.3× spread with nothing varying but the model's sampling** (wall clock 382–1036 s, 2.7×). The featured run in `plot_spec.json` is run_1, the smallest of the four. Two of the four would sit at or below the smallest "accept" in the reference set. Whatever the taxonomy predicts, it must beat 5.3× to be worth an episode — and no static predicate in this spec claims that kind of resolution.

**One arithmetic error that propagates into the thesis claim.** `fmt-3248 … 13128 Ginstr — the class maximum` and the headline pair "fmt (13128 Ginstr) vs gin (137 Ginstr)" compare a **10-pass sum against a 1-pass total**. fmt is 1313 Ginstr per pass over 10 passes = 13128; gin has exactly 1 banked replay pass at 137. Like-for-like it is 1313 vs 137 = **9.6×, not 96×** — and the core-second version agrees (270.5 vs 29.3 = 9.2×). fmt is also not the maximum on any basis: per pass, scikit-learn 3028 > prometheus 1618 > gson 1475 > fmt 1313. The single number carrying "the INSTANCE dominates fence size far more than the LANGUAGE" is inflated 10× and mis-titled, and — as `known_limits` #7 half-concedes — the pair confounds language, repo, toolchain and instance anyway. The babel replicates above are the honest version of that experiment, and they say the *sampling seed* moves the fence 5.3× within one instance.

---

## 5. Honest accuracy

On the 12 profiled rows the taxonomy earns **5 clean agreements out of 9 scoreable in-corpus episodes** — fmt, jq, prometheus, php-cs-fixer, rubocop — plus one unfalsifiable pass (gson, whose "compile 7%" is the agent's own `/tmp/Repro.java` because maven never spawns javac), two half-passes where the runner arm holds and the transpile arm fails (vue 0%, babel 3% against a predicted 5–35%), one outright failure (tokio, failing 2 of 3 arms), and — on the row CTX declined to quote — a second outright failure at compile 2% (gin). The three Python rows are unscoreable because category Y offers no predictor. So the claim "12/12 correct" is obtained by grading three no-predictions as correct and grading three failing classes on their passing arm; the defensible figure is 5/9, and the class most of the corpus lives in (A, 85 instances) is refuted by 2 of its 3 measured members. What that implies for the other 288 is narrower than it sounds but not nothing: what the taxonomy actually delivers is a **repo→toolchain lookup that is a pure relabelling of `language`** — I verified mechanism is a total function of language with zero exceptions, so STEP 0's whole "key on repo, not language" rationale buys nothing on the mechanism axis and the mentor's `<language × type>` grid is one cell wide per language by construction. Everything the spec adds on top of that relabelling is **magnitude** prediction, and magnitude is where it has no signal at all: Spearman(fence, scope) = **−0.055** on verified data (the published +0.32 needs two episodes whose measurements do not exist in the tree), per-test cost spans 102×, the PHP calibration line's intercept is understated ~10×, the "unpopulated 7→59 core-s gap" contains gin at 29.3, and one instance measured four times spans 5.3× on its own. Use it as a stratifier to avoid buying two build-driver C tasks — that much is sound and is worth the effort. Do not use it to predict which instance will yield a measurable fence, do not quote any `expected_fence_size` in the per-language sections, do not treat the 104 X-SMALL exclusions as anything but a budget-driven guess, and fix three things before spending another episode: repair `tag_of` (the `/usr/bin/c++` driver falls to `other`/`shell`, `*.test` binaries and `go vet` are tagged compile, `\bbundler?\b` catches the `/bundle/` install prefix, and `TAG_PRIORITY` lets `cargo test`/`mvn` swallow their own compilers — record the tag **multiset** per window instead of one winner); relabel hugo-12448, docusaurus-9897 and fpm-1829 as the W-NOLEV controls the spec's own rule makes them; and promote the free E7 uniqueness gate, which is the only criterion that cleanly separated all three rejects, ahead of every static scope threshold.