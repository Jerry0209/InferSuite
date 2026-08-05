# Sampling plan — SWE-agent × GLM-5.2 on SWE-bench Multilingual

**Status:** proposal for approval. Frame and counts recomputed from `/home/thu/InferSuite/local_agents/ML_multiling/data/multiling_inventory.csv` (300 rows) and from the banked fences under `local_agents/{ML_multiling,SWE_clean}/data`. Every number below is reproducible; where the earlier draft spec disagrees with the data, this document follows the data and says so.

---

## 1. The sampling frame, and why it replaces "shortest problem statement"

Tasks are now stratified on a **two-axis frame computed entirely from static instance metadata: (i) TOOLCHAIN MECHANISM, a total function of the `repo` column — B build-driver, A AOT-unified, J JVM-unified, I interpreted-suite, N Node transpile+suite — and (ii) a within-repo scope tier S/M/L, or F when the repo's own eligible-scope spread is under 3×**, giving 20 cells of which all 20 are populated and 194 of 300 instances eligible after the hard gates (2 excluded for a degenerate problem statement, 104 for insufficient test scope). This replaces the previous rule — pick the instance with the shortest problem statement — which was not merely arbitrary but *adversely* selected: problem-statement length is uncorrelated with anything we measure (Spearman(tool core-seconds, `ps_chars`) = −0.32, n = 10 verified episodes), while its shortest tail is precisely where degenerate episodes live (`carbon-2813`, 124 characters, 12 identical actions, parked), so the old rule spent paid episodes buying the one failure mode the budget cannot absorb. The new frame's honest claim is narrow and worth stating to the mentor up front: **it reliably predicts the *kind* of CPU work a task will do (which toolchain runs, hence which command tags can appear in the fence), and it does not predict *how much* — magnitude has no static signal at all** (Spearman(fence, test scope) = −0.055; per-selected-test cost spans 102× across the banked set; one instance measured four times spans 5.3× on sampling seed alone). It is therefore used here as a *stratifier that stops us buying two build-heavy C++ tasks*, exactly as instructed — never as a magnitude oracle.

---

## 2. The ⟨language, type⟩ matrix

**Read this first: the grid is nested, not crossed.** Mechanism is a total function of `repo`, and — verified with zero exceptions over all 300 rows — also of `language`. Each language therefore occupies **exactly one** category column, so the mentor's 9 × 5 grid has 9 reachable cells, not 45, and **all 9 are already DONE** by the 12 banked episodes. Counts are `candidates / eligible`.

| language (n) | **B** build-driver | **A** AOT-unified | **J** JVM-unified | **I** interpreted-suite | **N** Node transpile | **Y** pytest |
|---|---|---|---|---|---|---|
| **C** (30) | 30 / 30 — **DONE** `jq-2681` · NEW `redis__redis-13115` | – | – | – | – | – |
| **C++** (12) | 12 / 12 — **DONE** `fmt-3248` · NEW `nlohmann__json-4237` | – | – | – | – | – |
| **Go** (42) | – | 42 / 23 — **DONE** `prometheus-9248` · NEW `gohugoio__hugo-12448` | – | – | – | – |
| **Rust** (43) | – | 43 / 24 — **DONE** `tokio-6551` · NEW `astral-sh__ruff-15356` | – | – | – | – |
| **Java** (43) | – | – | 43 / 42 — **DONE** `gson-2061` · NEW `apache__lucene-12196` | – | – | – |
| **PHP** (43) | – | – | – | 43 / 25 — **DONE** `php-cs-fixer-7523` · NEW `laravel__framework-48636` | – | – |
| **Ruby** (44) | – | – | – | 44 / 16 — **DONE** `rubocop-13668` · NEW `jordansissel__fpm-1829` | – | – |
| **JavaScript** (31) | – | – | – | – | 31 / 13 — **DONE** `babel-15445` (×4 runs) · NEW `babel__babel-14532`, `preactjs__preact-4152` | – |
| **TypeScript** (12) | – | – | – | – | 12 / 9 — **DONE** `vue-11915` · NEW `facebook__docusaurus-9897` | – |

`Y` is empty by construction: 0 of 300 candidates. Its three reference rows (`astropy-14096`, `sympy-14248`, `scikit-learn-25232`) come from the earlier SWE-bench Verified campaigns and no further Y episode is proposed.

**Because the ⟨language, type⟩ grid is saturated, the operational frame is mechanism × within-repo tier.** This is the table the run list actually draws from (eligible counts; DONE = banked accept):

| mech | S | M | L | F (flat, W-NOLEV) |
|---|---|---|---|---|
| **B** | 10 | 9 | 8 — **DONE** `fmt-3248` · NEW `redis-13115` | 15 — **DONE** `jq-2681` · NEW `json-4237` |
| **A** | 8 | 8 — **DONE** `prometheus-9248`, `tokio-6551` | 7 — NEW `ruff-15356` | 24 — NEW `hugo-12448` |
| **J** | 12 — NEW `lombok-3602` | 12 — NEW `lucene-12196` | 10 — **DONE** `gson-2061` · NEW `lombok-3009` | 8 |
| **I** | 14 | 11 — **DONE** `rubocop-13668` | 11 — **DONE** `php-cs-fixer-7523` · NEW `laravel-48636` | 5 — NEW `fpm-1829` |
| **N** | 7 — **DONE** `babel-15445` | 5 — **DONE** `vue-11915` | 4 — NEW `babel-14532`, `preact-4152` | 6 — NEW `docusaurus-9897` |

Two corrections to the earlier draft, both material: the frame is **20 cells, not 15** (the F tier holds 58 of 194 eligible instances, 30% — the second-largest tier), and the banked accepts cover **8 cells, not 9** (`prometheus-9248` and `tokio-6551` are both A.M).

---

## 3. Run list, ordered by value per hour

**Ordering principle, stated so it can be challenged.** Composition — what `attribute_windows.py` / `analyze_l3_windows.py` report as the instruction-weighted tag mix — is reproducible: median over 10–11 replay passes, and all 12 banked compositions re-derive from the window CSVs within pass-to-pass noise. Magnitude is not: `babel-15445` has **four independent live episodes of the same instance** whose tool fences are **37.9 / 54.9 / 199.0 / 202.1 core-seconds — a 5.33× spread with only the sampling seed varying**. Episodes are therefore ranked by how much *falsifiable composition* they buy, and magnitude contrasts are demoted unless their predicted ratio clears that 5.3× noise floor or their baseline arm is already replicated.

**Cost model.** Per task: 1 paid live episode (~15–25 min wall) + 11-pass deterministic replay (~50 min) + ISO-PROOF gate and teardown (~15 min) ≈ **1.5 h of exclusive-core time**, serialized — cores 2–11,14–23 cannot be shared.

### Wave 0 — free prerequisites (housekeeping cores only, 0 exclusive-core hours)

Do these *before* spending an episode; without them three of the five class predictions cannot be falsified and several banked compositions are partly tagger artefacts.

| # | action | why it must come first |
|---|---|---|
| 0a | **Repair `tag_of` / `TAG_PRIORITY`** in `local_agents/kit/replay/analyze_l3_windows.py`: match `argv[0]` basename; the compile regex `/c\+\+\b` cannot match `/usr/bin/c++ ` (no word boundary between `+` and space), so **10,100 of `fmt`'s 34,634 argv samples — 29% — are the GCC C++ driver tagged `other`/`shell`**; stop tagging `*.test` binaries and `go vet` as `compile`; add an app-under-test tag for `*/bin`, `vendor/bin`, `node_modules/.bin` so `\bbundler?\b` stops catching the `/bundle/` install prefix; and record the **tag multiset** per window instead of one priority winner (a persistent `cargo test` or `mvn` front-end currently swallows its own compiler). | `fmt` reports `pkg/build` 1% and `jq` 31% for the *same* physics; `tokio`'s window mix and its own argv log invert (8.7× test vs 2.2× compile); class N's transpile sub-term is invisible because `esbuild` routes to `pkg/build` via `\bpnpm\b`. |
| 0b | **Layer-2 repo probe (R5)** on the wave-1 shortlist: unpatched tree, image's install + test command, 10 Hz `cpu.stat` poller only. ~2–10 min per repo. | Gives a measured `fence_floor(repo)`. It is the only thing that can replace guessed magnitude thresholds, and at the observed ~20% rejection rate each avoided reject saves ~1.5 h of unparallelisable exclusive-core time. |
| 0c | **Publish the four banked `babel-15445` replicates** as the study's first measured spread. | Free. It retires the false claim "every banked cell is n = 1, no spread can be reported", and it supplies the noise band every contrast below is judged against. |
| 0d | **Promote the E7 action-uniqueness gate** ahead of every static scope threshold, and re-derive the Layer-3 floor. | E7 is the only criterion that cleanly separated all three rejects (uniqueness 0.61 / 0.84 / 0.87 vs 0.96–0.97 for accepts; both `carbon-2813` and `laravel-51890` have a longest-identical-action run of 12). The 20 core-second floor does not separate them: **`gin-3741`'s tool fence is 29.3 core-seconds**, inside the "wide and unpopulated 7 → 59" gap it was justified by. Keep the ≥1000 Ginstr arm; core-seconds and Ginstr are rank-redundant (Spearman 1.00). |
| 0e | Restate the headline pair like-for-like. | `fmt` 13128 vs `gin` 137 Ginstr compares a 10-pass sum against a 1-pass total; per pass it is **1313 vs 137 = 9.6×, not 96×**, and `fmt` is not the maximum on any basis (per pass: `scikit-learn` 3028 > `prometheus` 1618 > `gson` 1475 > `fmt` 1313). |

### Wave 1 — paid episodes

| rank | instance | lang | cell | flags | cum. episodes | cum. exclusive-core h |
|---|---|---|---|---|---|---|
| 1 | `facebook__docusaurus-9897` | TypeScript | N.F | W-NOLEV | 1 | 1.5 |
| 2 | `astral-sh__ruff-15356` | Rust | A.L | none | 2 | 3.0 |
| 3 | `babel__babel-14532` | JavaScript | N.L | X-DUP (pre-declare) | 3 | 4.5 |
| 4 | `redis__redis-13115` | C | B.L | none | 4 | 6.0 |
| 5 | `gohugoio__hugo-12448` | Go | A.F | W-NOLEV | 5 | 7.5 |
| 6 | `apache__lucene-12196` | Java | J.M | none | 6 | 9.0 |
| 7 | `nlohmann__json-4237` | C++ | B.F | W-NOLEV, sole candidate | 7 | 10.5 |
| 8 | `jordansissel__fpm-1829` | Ruby | I.F | W-READ, W-NOLEV, magnitude-marginal | 8 | 12.0 |
| 9 | `laravel__framework-48636` | PHP | I.L | X-DUP (pre-declare) | 9 | 13.5 |
| 10 | `preactjs__preact-4152` | JavaScript | N.L | W-CONFOUND (0.55) | 10 | 15.0 |
| 11 | `projectlombok__lombok-3009` | Java | J.L | none | 11 | 16.5 |
| 12 | `projectlombok__lombok-3602` | Java | J.S | W-LOWLEV, W-BIGDIFF | 12 | 18.0 |

**Cut lines.** MINIMUM = 1–2 (3 h). CORE = 1–5 (7.5 h): repairs the two class arms that currently fail, buys the only powered magnitude contrast, and adds four new repos. RECOMMENDED = 1–8 (12 h): every class arm probed on a second toolchain, and 6 of 9 languages become claimable at language level. FULL = 1–12 (18 h).

---

#### 1. `facebook__docusaurus-9897` — TypeScript, N.F, scope 92
**Buys:** the only class arm that currently measures **0 for 2**. Class N asserts a transpile sub-term of 5–35% of fence instructions; `vue-11915` measures 0% and `babel-15445` 3%. Docusaurus is a *third, structurally different* N front-end (jest + ts over a yarn monorepo, vs vitest/esbuild and jest/babel), so after the 0a tagger fix this episode either recovers the sub-term or kills the arm. Also the second TypeScript repo, which is what `known_limits` #6 requires before any TypeScript-level sentence.
**Runner-up:** `facebook__docusaurus-9183` (N.F, scope 36, W-BIGDIFF) for an instance-level failure. If the failure is repo-level — jest's on-disk cache making repeat invocations nearly free — do **not** retry inside docusaurus: switch to `immutable-js__immutable-js-2006` (N.F, scope 23).
**Risk:** W-NOLEV — docusaurus's eligible scopes are 35 / 36 / 92, spread 2.63× < 3, so by STEP 3 this is tier **F**, not the "N.L, zero warn flags" the earlier draft claimed. It is a composition probe and a flat-repo control, not a high-leverage instance. Magnitude risk moderate; run 0b on docusaurus first.

#### 2. `astral-sh__ruff-15356` — Rust, A.L, scope 134
**Buys:** a decisive test of the largest class in the corpus. A holds 85 instances (47 eligible) and is **refuted by two of its three measured members** — `tokio-6551` fails two of the three predicate arms (compile 10% < 20; HHI 0.768 > 0.65) and `gin-3741` measures compile **2%**. Rust's single A datapoint is one of the failures. Ruff has the same `cargo test` front-end as tokio but a much wider multi-crate rebuild closure, so post-fix it separates "the tagger swallowed rustc" from "class A is wrong". Second Rust repo.
**Runner-up:** `nushell__nushell-13605` (A.L, scope 51, no flags) — a third Rust repo with an even heavier workspace rebuild, independent of both tokio and ruff.
**Risk:** none static. Magnitude expected comfortably above the Ginstr gate, but that expectation is a prior, not a measurement.

#### 3. `babel__babel-14532` — JavaScript, N.L, scope 524
**Buys:** the **only magnitude contrast in the corpus with a replicated baseline**. `babel-15445` (scope 56) has four banked episodes spanning 37.9–202.1 core-seconds, so a single episode at 9.4× the scope is judged against a *measured* noise band instead of a guess — repo, language, toolchain and harness held fixed. This is the only design that can carry the "the instance, not the language, dominates fence size" sentence; the present `fmt`-vs-`gin` evidence varies language, repo, toolchain and instance simultaneously.
**Runner-up:** `babel__babel-13928` (N.M, scope 249) — a 4.4× arm, weaker but still above the noise floor; `babel__babel-15649` (scope 106) is 1.9× and therefore *not* worth an episode.
**Risk:** X-DUP — babel is already banked. Pre-declare `14532` in `plot_spec.json` as the L-arm of the babel contrast pair before running, per STEP 1g. Note it does **not** add a repo, so item 10 is still needed for a JavaScript-level claim.

#### 4. `redis__redis-13115` — C, B.L, scope 184
**Buys:** class B on a **non-make front-end**. B is currently validated on `jq` (make is the front-end process) and on `fmt` (whose "compile 97%" survives only because `cc1plus` co-occurs in the same windows as the mis-tagged `/usr/bin/c++`). Redis's entry point is `make` *then* `./runtest` — tclsh driving `redis-server` — which is a different process topology, and **21 of C's 30 instances** (redis, valkey, micropython) inherit the prediction from it. Informative either way: a compile/runner mixture falsifies B's "compile+link+make ≥ 60%, runner < 30%" for most of the C column; compile dominance validates B's scope-gate exemption on a repo other than jq. Second C repo; scope 184 is the C maximum and `unit/scripting.tcl` burns real CPU in the embedded Lua interpreter.
**Runner-up:** `valkey-io__valkey-1499` (B.L, scope 47, no flags) — same physics, so it fails with redis; hedge the actual failure axis with `micropython__micropython-12158` (B.F, different toolchain: make + CPython `run-tests.py`, `touches_header`, 8 patched `.c`/`.h` files = the broadest rebuild in its repo).
**Risk:** none static; repo share 0.40 so no W-CONFOUND. The open question is whether the image ships a prebuilt tree — exactly what 0b measures.

#### 5. `gohugoio__hugo-12448` — Go, A.F, scope 35
**Buys:** a third class-A datapoint in Go, which discriminates the two live explanations of `gin`'s compile 2% — "gin's module is small and the build cache is warm" versus "class A's compile term does not exist as specified". Hugo's `go test` closure (goldmark/chroma/image/template stacks) is roughly two orders of magnitude larger than gin's. Second *unrejected* Go repo.
**Runner-up:** `caddyserver__caddy-6051` (A.F, scope 20, W-READ — read and passed: concrete heredoc repro plus the exact adapter error), a fourth Go repo. In-repo alternate `gohugoio__hugo-12579` (scope 24).
**Risk:** W-NOLEV — hugo's eligible scopes are 13 / 24 / 24 / 35, spread 2.69× < 3, so tier **F**. The earlier draft rejected `terraform-35543` *for being W-NOLEV* and then picked this, which is also W-NOLEV; the flag is recorded here rather than removed.

#### 6. `apache__lucene-12196` — Java, J.M, scope 12
**Buys:** a test of whether class J's `compile ≤ 15%` arm is a **tautology**. `gson-2061`'s entire compile bucket is 75 argv samples and every one is the agent's own scratch reproducer (`javac -d build /tmp/Repro.java`, `/tmp/Repro2.java`, `javac -version`); the repo's bytecode compilation runs inside the maven JVM via the in-process compiler API (777 `plexus-classworlds` samples), so **no `javac` process exists for the tagger to see in any maven repo, ever**. Lucene is gradle, not maven. If gradle also never forks a compiler, the arm is confirmed unfalsifiable and must be withdrawn — a publishable negative that costs one episode. Second Java repo.
**Runner-up:** `apache__lucene-12212` (J.S, scope 11, W-LOWLEV, `ps_chars` 3723 — the richest lucene statement) or `apache__lucene-12626` (J.L, scope 107, lucene max, no flags) if a larger fence is wanted. Third repo: `apache__druid-16875` (J.F).
**Risk:** none static. Outcome is likely "tautology confirmed" — informative but unsurprising, which is why this sits at rank 6 rather than higher.

#### 7. `nlohmann__json-4237` — C++, B.F, scope 22
**Buys:** the only available answer to "is *compile-dominated at 97%* a class-B property or an `fmt` property?". Different repo, different driver (cmake + ctest + doctest vs fmt's gtest), and the gold patch touches `single_include/nlohmann/json.hpp`, the amalgamated header every test translation unit includes, so rebuild breadth is maximal.
**Runner-up:** none exists. `fmt__fmt-3729` (B.S, scope 13, X-DUP + W-CONFOUND 0.92) is a *different experiment* — a within-fmt 9× contrast against banked `fmt-3248` testing whether the build, not test selection, sets the magnitude. Worth queueing as the first spillover item if a 13th episode is funded.
**Risk:** W-NOLEV, and it is the **only eligible instance in its repo, the only non-X-DUP C++ instance in the corpus, and 1-of-1 in its (cell ∧ language) slot** — it is the population, not a sample. Both C++ repos are header-only template libraries, so this buys a second repo but **not** a de-confounded C++ claim (see caveats).

#### 8. `jordansissel__fpm-1829` — Ruby, I.F, scope 47
**Buys:** a composition unlike anything in the banked set. Its F2P builds and re-reads a package for each of 11 `--provides` values and its P2P include "should use bz2/xz/gz for data and control files" and "should output bit-for-bit identical packages", so a class-I fence (no repo compilation) would be driven by **native `tar`/`gzip`/`bzip2`/`xz`/`dpkg-deb` subprocesses**. That directly probes I's "runner + app-under-test ≥ 90%, compile = 0%" and the new app-under-test tag from 0a — the same mis-routing that made `rubocop`'s 53% "bundler (pkg/build)" bar actually 652 samples of `/usr/local/bundle/bin/rubocop`, the application under test, with no `bundle install` or `gem` anywhere in the log. Second Ruby repo.
**Runner-up:** `jekyll__jekyll-8167` (I.F, scope 20) or `fluent__fluentd-3641` (I.F, scope 20) — each the sole eligible row in its repo, so equally singleton. High-confidence fallback `rubocop__rubocop-13424` (I.L, scope 143, X-DUP exemption needed, expected 80–150 core-seconds) if the gate fires.
**Risk:** highest magnitude risk in the list — 15–40 core-seconds estimated from test-name reading, straddling the floor. W-READ (`ps_chars` 595, manually confirmed: names `--provides 'foo (<< 1.0.0-54)'` and dpkg exact-version policy). W-NOLEV, 1-of-1 in its repo. Run 0b on the fpm image before committing; the earlier draft's claim of "zero W-BIGDIFF/W-NOLEV/W-CONFOUND" is wrong on W-NOLEV.

#### 9. `laravel__framework-48636` — PHP, I.L, scope 168
**Buys:** the second *accepted* PHP repo — php-cs-fixer is currently the only one, since both other banked PHP episodes were parked. Doubles as a within-repo contrast against the parked `laravel-51890` (scope 9 → 168, 19×), and is the sharpest patch-vs-CPU decoupling case in PHP: a 1-file / 1-hunk / +1-line fix behind a 166-case test class.
**Runner-up:** `phpoffice__phpspreadsheet-3940` (I.F, scope 59, W-NOLEV) if a genuinely unsampled repo is preferred — phpspreadsheet has zero measured episodes and its tests build object graphs and run the formula engine, the PHP repo most likely to show a distinct app-under-test term. Same-repo alternate `laravel__framework-52684` (scope 151).
**Risk:** X-DUP (pre-declare as the L-arm of the laravel pair). **Ignore any published `expected_fence_size` for PHP**: they were all computed from `2.94 + 0.432·scope`, a line fitted mostly on two episodes whose measurements do not exist in the tree; on the two *verifiable* class-I points the line is slope 0.241, intercept 48.3 — a 10× larger intercept.

#### 10. `preactjs__preact-4152` — JavaScript, N.L, scope 76
**Buys:** the second JavaScript repo (item 3 re-spends babel), which is the precondition for any JavaScript-level sentence. Preact's test entry point is karma + webpack + babel driving headless Chrome — a fourth N front-end, and the browser process is a fence descendant inside the docker sandbox, so it is an independent test of the transpile sub-term with a structurally different transpiler from docusaurus's.
**Runner-up:** `axios__axios-5892` (N.F, scope 33, W-NOLEV) — a third JavaScript repo with no W-CONFOUND, but the sole eligible axios row and a thinner magnitude case.
**Risk:** W-CONFOUND (preact is 17 of 31 JavaScript instances, 0.55). Per the ambiguity rule this is a *phrasing* constraint, not a disqualifier: report as "preact (JavaScript)" in every figure, table and caption, never with JavaScript as the subject. N.L is the **smallest cell in the frame** (4 eligible, 3 in JavaScript).

#### 11–12. `projectlombok__lombok-3009` (J.L, scope 323) + `projectlombok__lombok-3602` (J.S, scope 2) — 2 episodes
**Buys:** the only within-repo scope contrast in the corpus whose ratio — **162×** — exceeds the 5.33× within-instance sampling floor by enough that a *null* result is interpretable. Class J asserts fence magnitude is nearly independent of test count, and lombok's F2P entries make each test its own `javac`-with-annotation-processor invocation, so this pair either confirms the intercept claim (a ≤5.3× change against a 162× scope change bounds the proportional effect at ≲3%) or localises its failure inside lombok. `gson-2061`, the calibration row for J, cannot do this: it passes only because J is *exempted* from the scope gate.
**Runner-ups:** `projectlombok__lombok-3215` (J.L, scope 312, no flags) and `projectlombok__lombok-3594` (J.S, scope 3, W-LOWLEV) preserve the pair.
**Risk:** two episodes for one claim, which is why it ranks last on value-per-hour despite carrying a headline sentence. `3602` is W-LOWLEV + W-BIGDIFF and is *expected* to be small — if its corrected fence lands below the Layer-3 floor that is the finding, not a failure. lombok would then hold 2 of 12 new episodes; accept that or drop to the single L arm.

---

## 4. Cells deliberately not run — with reasons

Silence here is the failure mode we are avoiding, so every unfilled cell is listed.

**A. The 36 empty ⟨language, category⟩ cells — reason: structurally impossible.** Mechanism is a total function of `language` (verified, zero exceptions over 300 rows), so 36 of the 45 grid cells contain zero candidates and can never be filled at any budget. This is a property of the corpus, not of the plan. Anyone expecting 45 informative cells should be told this before the plan is read.

**B. Category Y (pytest) — reason: out of corpus, already covered.** 0 of 300 candidates. Its three reference rows are banked from the earlier SWE-bench Verified campaigns. No episode.

**C. The 9 diagonal ⟨language, category⟩ cells — reason: already DONE.** No episode is spent to "fill" any of them; every item in §3 lands in a DONE cell or a tier cell, and buys a *second repo*, a *contrast arm*, or a *falsification test*, never a first occupancy. Stating this plainly: **cell-filling is not the binding constraint** — the frame is saturated on the primary axis, and what is unvalidated is the class predictions.

**D. Five of the twenty mechanism × tier cells stay empty.**

| cell | eligible | reason not run |
|---|---|---|
| **B.S** (10) / **B.M** (9) | 19 | **Redundant.** B has no scope gate because the build intercept sets the magnitude, so a low-scope B task measures the same quantity as B.L with added risk that the image ships a prebuilt tree. Every C++ member of these cells is `fmt` → X-DUP + W-CONFOUND 0.92. *Exception queued, not run:* `fmt-3729` (B.S, 13) vs banked `fmt-3248` (B.L, 117) is a 9× within-repo test of B's own "the build, not test selection, sets magnitude" claim — first spillover item. |
| **A.S** (8) | 8 | **Redundant + too-small risk.** This region is already measured: `gin-3741` sits here (29.3 core-seconds, 137 Ginstr, compile 2%, 1 replay pass) and was parked. Re-buying it purchases a second unmeasurable fence. |
| **J.F** (8) | 8 | **Redundant.** J's claim is that the intercept dominates and scope is irrelevant, so a "flat" J cell measures the same quantity as J.M/J.L. J's actual defect is the unfalsifiable compile arm, which item 6 tests more cheaply than `druid-16875` would. |
| **I.S** (14) | 14 | **Too-small risk with no valid predictor.** Both parked PHP episodes were class I with scope < 20, and the only basis for predicting anything here is the PHP line whose intercept is understated ~10×. Explicitly deferred pending 0b probe data — not silently dropped. |

**E. 19–20 of the 41 repos are never sampled** (fluentd, jekyll, fastlane, faker, phpspreadsheet, three.js, axios, immutable-js, javaparser, rxjava, druid, bat, axum, coreutils, ripgrep, caddy, terraform, micropython, valkey, gin at the FULL cut line). **Reason: budget, plus an untested assumption.** The frame assumes mechanism is repo-invariant *within* a class; §3 tests that assumption exactly once per class (items 1, 2, 4, 6, 8) and does not test it further. `fastlane` (7 instances) and `faker` (2) have **zero** eligible rows and are unreachable without relaxing a gate, which the ambiguity rule forbids.

**F. 104 of 300 instances excluded as X-SMALL, 2 as X-DEGEN.** Reason: budget-driven, and **the X-SMALL thresholds are a guess** — see caveats. They are published as excluded with a reason code, not treated as unmeasurable.

---

## 5. Caveats — read before quoting any cell

1. **The repo confound is the dominant limitation, and it cannot be fixed in this corpus.** The mechanism axis is nearly collinear with language (B = all C/C++, A = all Rust/Go, J = all Java, I = all PHP/Ruby, N = all JS/TS), so the ⟨language × type⟩ grid is one cell wide per language. Worse at repo level: **C++ has 2 repos and both are header-only template libraries**, so every test translation unit re-instantiates the library — the pathological end of the C++ build spectrum, not its centre. Keep `fmt` as an explicitly labelled build-extreme case study, phrase it as an existence claim ("at least one C++ task is compile-dominated"), and exclude C++ from every cross-language comparison figure. The same treatment applies to `preact` (17 of 31 JavaScript instances) and to `fmt` (11 of 12 C++). **A language-level claim requires ≥ 2 sampled repos in that language**; every language currently has exactly one accepted repo, which is why 6 of the 12 proposed episodes exist mainly to buy the second.

2. **Static prediction accuracy, honestly.** On the 12 profiled rows the taxonomy earns **5 clean agreements out of 9 scoreable in-corpus episodes** (`fmt`, `jq`, `prometheus`, `php-cs-fixer`, `rubocop` — the last only after manually re-reading its argv log), plus one unfalsifiable pass (`gson`), two half-passes where the runner arm holds and the transpile arm fails (`vue` 0%, `babel` 3% against a predicted 5–35%), and two outright failures (`tokio` fails 2 of 3 arms; `gin` measures compile 2%). The three Python rows are unscoreable because category Y offers no predictor. The figure "12/12 correct" is obtained by grading three no-predictions as successes and grading three failing classes on their passing arm; **the defensible figure is 5/9**, and the class most of the corpus lives in — A, 85 instances, 47 eligible — is refuted by 2 of its 3 measured members. What the frame reliably delivers is a repo → toolchain lookup; everything beyond that is currently a prior.

3. **Magnitude prediction has no signal. Do not quote an `expected_fence_size`.** Spearman(tool core-seconds, test scope) = **−0.055** on the 10 episodes with verified `cpu.stat` fences; the published +0.32 reproduces only on an n = 12 set that includes two episodes whose measurements do not exist in the tree (`carbon-2813` and `laravel-51890` have `.traj` and logs but no `cpustat_scope*.tsv`, no `l3_study` CSV, no replay directory — their quoted 6.6 and 6.4 core-seconds cannot be reproduced). Per-selected-test cost spans **102×** (`php-cs-fixer` 0.44 → `gson` 45.1 core-seconds/test). `patch_add`, which the draft blacklists on a −0.08 figure, is actually the *best* static correlate available at **+0.358**. The 104 X-SMALL exclusions rest on 4 thresholds fitted to 3 points, 2 of them unverifiable — treat that 35% of the corpus as a budget decision, not as a finding.

4. **Sampling noise sets the resolution floor, and it is large.** `babel-15445` measured four times: 37.9 / 54.9 / 199.0 / 202.1 core-seconds, **5.33× on sampling seed alone** (wall clock 382–1036 s, 2.7×). Two of the four would sit at or below the smallest "accept" in the reference set, and the run featured in `plot_spec.json` is the smallest. **Any single-episode magnitude contrast whose predicted ratio is under ~5.3× is unresolvable** — which is why the rubocop (6.2×) and php-cs-fixer (3.4×) pairs from the earlier draft are not in the run list, and why items 3 and 11–12 are.

5. **Singleton cells.** `nlohmann__json-4237` is 1-of-1 in its repo, 1-of-1 in its (cell ∧ language) slot, and the only non-X-DUP C++ instance — it is the population, not a sample. `jordansissel__fpm-1829` is 1-of-1 in its repo. `phpoffice__phpspreadsheet` has exactly 2 eligible rows, so if both park the cell must be published as "0 of 10" with that reason. N.L holds 4 eligible instances (3 in JavaScript). Every published cell should carry `n_sampled / n_candidates`, `n_repos`, the repo's share of its language, and the sampled instance's within-repo scope percentile.

6. **Three tier labels in the earlier draft are wrong in the same direction, and are corrected here.** `hugo-12448`, `docusaurus-9897` and `fpm-1829` were presented as high-leverage `L` with "zero warn flags"; by the frame's own STEP 3 all three are **F tier with W-NOLEV** (repo eligible-scope spreads 2.69×, 2.63×, 1.00×). They are retained as class-composition probes and flat-repo controls. They must not be described as high-leverage, and in two cases the draft rejected an alternative *for being W-NOLEV* and then chose a W-NOLEV instance.

7. **A cell's type is a PRIOR until the run confirms it.** The only authority on a task's category is the measured composition reported by `attribute_windows.py` / `analyze_l3_windows.py` — the instruction-weighted tag mix, median over the 10–11 replay passes. Static metadata contains no feature for build intercept, compilation-unit granularity, dependency-closure size, reverse-dependency fan-in, JVM/bundler warmup, or the harness's test selectivity. **And that confirmation is itself blocked until wave-0a lands:** `fmt` and `jq` report `pkg/build` 1% and 31% for the same physics; `prometheus`'s "compile 62%" is 61.9% real compiler, 29.1% the compiled test binary `/tmp/go-build*/b001/rules.test`, 8.2% `go vet`; `tokio`'s window mix and argv log invert; `vue`'s transpile term is 523 mis-routed `esbuild` samples. Note also that argv poll counts are **not** instruction-weighted, so a re-tag establishes *which* tags exist and their ordering, not their instruction shares.

8. **Scope of the whole exercise.** This classifies **tool-fence CPU** only. Action mix is a covariate on a *different* fence (the harness fence) and never a category — every task is search/edit-dominated by action count (41–86% across the banked set, anti-correlated with fence size), so that axis carries almost no CPU information; `babel` is reported as "class N, test-runner CPU, search-heavy actions", both numbers, no forced choice. Nothing here speaks to the litellm proxy (which runs on the housekeeping cores and is excluded from measured-partition capacity claims) or to API cost. Kernel threads belong to no cgroup, so all fence totals remain lower bounds, bounded by the partition witness and gate E11.