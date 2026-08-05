# Report 16 — Nine-language expansion of the per-window study (deck slides 26–27)

**Date of study:** 2026-07-29/30 · **Author of record:** Jerry0209, with Claude Code
**Deck slides:** 26 (nine languages, gate results) and 27 (composition vs magnitude); also
feeds the corrected chips on slides 24–25.
**Longer prose version:** none — this report is the record. **Cross-refs:** 13 (first two
multilingual tasks) · 15 (ownership gate's origin, per-tag attribution) · 17 (sampling frame).

---

## 1. Key summary

The language axis was extended from 2 to 9 languages (12 tool workloads including the three
Python tasks): tokio/Rust, jq/C, prometheus/Go, gson/Java, vue/TypeScript, rubocop/Ruby and
php-cs-fixer/PHP joined babel/JavaScript and fmt/C++. Each language = one paid live episode →
a 1-pass gate probe → 10 more dedicated-group replay passes. Every accepted task passes a
two-part gate — **ownership** (≥50 % of tool-fence instructions in windows where the language's
own toolchain was observed; measured 92.1–99.2 %) and **adequacy** (≥20 windows and ≥150 Ginstr
per pass; floor = babel, so nothing previously published is retroactively invalidated) — plus
all standard validators (E1–E11). Three instances were rejected by automated gates, none by
judgment. Headline methodological result: **per-window composition is the reproducible layer
(replay reproduces a live episode's tool CPU to ~1 %); absolute magnitude is not (four live
episodes of one instance span 5.33×)**. Headline microarchitectural result: within one Go
episode, compile windows run at µop-cache 59.4 MPKI vs 37.6 in test windows — the study's only
confound-free front-end contrast — and Java's warmed JIT has the best front end of any tool
workload (25.9 MPKI, DSB 82.5 %), which retires the earlier "compiler sophistication" story in
favour of *code reuse per unit work*. The expansion doubled as a harness stress test: six
silent defects surfaced, each producing confident wrong answers rather than errors.

## 2. Methodology

### 2.1 Design decisions

| Decision | Value | Why |
|---|---|---|
| Data root | `local_agents/ML_multiling/data` (new tree) | Pilots must not touch the certified `SWE_clean`; promotion is deliberate, not incidental |
| Subset | `SWE_SUBSET=multilingual` | maps to HF `swe-bench/SWE-Bench_Multilingual` (default `verified` has none of these instances) |
| Instance choice | one per language, shortest problem statement | **Superseded**: Report 17 shows this is near-arbitrary; kept here as the honest record of what was done |
| Sequence per language | live episode → 1-pass gate probe → 10 passes | The probe (~4 min, free) answers "is this fence the language?" before the ~50 min of passes; a bad instance costs one episode, not a campaign |
| Ownership gate | ≥50 % of fence instructions in toolchain-observed windows (2 Hz argv poll, per-language regex over program names) | Report 15 insight 7: a fence the language doesn't own measures `grep`, not the language |
| Adequacy gate | ≥20 windows AND ≥150 Ginstr per pass | Added after gin passed ownership (63.5 %) on 15w/137G — two orders below the columns it would sit beside. Floor set at babel (20w/189G), the weakest task already in the deck |
| Rejection policy | keep rejected data in-tree, documented | gin/carbon/laravel remain as evidence; only mid-flight-killed captures were removed |
| Replay run numbering | gate probe = `run_1` (fe_miss), passes fill `run_2..11` | Differs from older tasks (fe_miss=run_11); safe because the analyzer keys on `l3group.txt`, not run number |

### 2.2 Verification, rejections, defects, disclosures

**Gate results** (pooled over all passes; `attribute_windows.py probe`):
Java gson **99.2 %** (40w/1475G per pass) · TypeScript vue **99.1 %** (22w/788G) · Ruby rubocop
**98.1 %** (39w/339G) · C++ fmt **97.2 %** (66w/1313G) · Rust tokio **96.9 %** (44w/696G) · PHP
php-cs-fixer **96.7 %** (80w/566G) · Go prometheus **95.7 %** (119w/1618G) · C jq **92.1 %**
(47w/398G) · JavaScript babel **78.2 %** (20w/189G). Probe caveats: presence-based in 2-s
windows (over-credits co-residents; under-observes Go's sub-half-second compilers → Go is a
lower bound); Python's 100 % is plumbing-inflated (`python` matches the in-container swerex).

**Three rejections, three different automated causes** — 3 of 12 attempted instances (~25 %):
gin-3741 (Go) episode fine but 15w/137G → adequacy; carbon-2813 (PHP) 12 identical actions →
E7 loop guard at threshold; laravel-51890 (PHP) 6.4 core-s, split-half IPC 27 % → E-gate. The
PHP pair share one cause: unit suites of small libraries finish in seconds; the accepted PHP
task is CPU-bound static analysis (105.3 core-s, 16× the rejects).

**Six defects found and fixed** (each silent, each surfaced by a new language):
1. Dry-run gate unpassable — its three numpy workloads invoked bare `python3`; numpy lives only
   in `infersuite-full`. Fixed with `dry_python()` resolver (`DRY_PY` override).
2. ISO-PROOF quiet check was a coin flip — single 1.5-s sample lands in the cpuset-migration
   drain (measured 2-of-5 pass rate idle). Fixed: bounded settle-and-retry (≤8×4 s), threshold
   untouched, every attempt logged.
3. GNU linker tagged `tests(pytest)` — `/testbed` + `-m elf_x86_64` + test-binary name satisfied
   the old heuristic; 36 % of Rust's fence. Fixed: `-m` branch requires a python binary.
4. Go toolchain invisible — `pkg/tool/<arch>/{compile,link,asm}` fell to `other` (< `shell`).
   Fixed pre-emptively; verified against gin's real argv log.
5. Liveness check killed a healthy run — waited for the literal "STEP 2" banner; SWE-agent
   logged STEP 1 then 3..17. Fixed: `swe_max_step()` ≥ 2.
6. **Path-collision tagging (the general form of 3/4)** — `tag_of` matched substrings of the
   whole argv, so directory names collided with tool names: `/usr/local/bundle/bin/rubocop` →
   `pkg/build` ("bundler dominates Ruby" was false — it was rubocop as the app under test);
   `.pnpm/.../esbuild` → `pkg/build` (vue's transpile term hidden; "vue is JIT-only" was false);
   `/c\+\+\b` can never match `/usr/bin/c++ ` (no word boundary), so 29 % of fmt's argv samples
   (the C++ driver) were `other`/`shell` and "compile 97 %" was right only by window
   co-residency. Fixed: program-identity rules match **basenames** (`_progs()`); install-vs-run
   split for package managers; deliberate path evidence (Go tool dir, maven jar, gem bindir)
   kept as explicit rules. Re-deriving all 13 tasks changed **0 counter values**; only labels.
   `pip download --no-binary` restored to `pkg/build` (astropy back to 52/18/17/10).

**Disclosure — `_state_anthropic` hook (closes task #11).** SWE-agent's state tool has a
`#!/usr/bin/env python3` shebang; several Multilingual images ship no `python3` on PATH, so it
fails **once per step**: prometheus/Go 223 of 235 steps, gson/Java 114 of 123, php-cs-fixer/PHP
142 of 152 — and 0 on tokio/jq/rubocop/vue. Impact bounded: cgroup fences measure what actually
ran; E5/E7/E11 passed; the failed execs are negligible CPU. But those three episodes ran with
degraded agent state information and are not harness-equivalent to the other four. Unexplained
residue: why some images resolve `python3` and others don't was not root-caused.

**Replay fidelity vs episode noise.** Live-vs-replay tool core-s: Rust 192.3 vs 191.6–193.8,
C 65.8 vs 66.7–67.2, Go 383.3 vs 380.3–381.8 (all ≈1 %); Java 270.8 vs 251.1–270.5 (~7 % — JIT
and GC are genuinely nondeterministic under replay). Per-pass instructions within each task:
1.0× (scikit-learn 1.2×). Against that: babel's **four independent live episodes** of one
instance = 37.9 / 54.9 / 199.0 / 202.1 core-s (**5.33×**). Consequences: (a) composition and
shares are the layer that supports cross-task claims; (b) magnitude-based instance selection is
futile; (c) the gin rejection judged an *episode*, not the instance.

**Corrected en route (do not reuse):** "front-end pressure orders by compiler sophistication"
(type-confounded: compared build-dominated C/Go/C++ with test-dominated Rust/Java; the
within-Go split replaces it); "fmt vs gin = ~100×" (pooled-vs-single-pass arithmetic; correct
is 1313 vs 137 = **9.6×** per pass); fmt is not the largest fence (scikit-learn is, 2988
G/pass); "bundler dominates Ruby" and "vue is JIT-only" (defect 6).

### 2.3 Reproduction recipe

```bash
# per language: episode (paid; 6–29 min agent wall) -> gate probe (free) -> passes (free ~50 min)
SWE_SUBSET=multilingual SWE_INSTANCES="<owner__repo-NNN>" REPEATS=1 \
  DATA_ROOT=$REPO/local_agents/ML_multiling/data ./measure.sh agents-swe campaign
K=$REPO/local_agents/kit
SHORT=<owner> SRC=1 DATA_ROOT=$REPO/local_agents/ML_multiling/data WINSEC=2 \
  PROF_GROUPS="fe_miss" "$K/replay_l3_profile.sh"                      # gate probe -> run_1
PY=~/miniforge3/envs/infersuite-full/bin/python3                       # NOT system python3
$PY "$K/analyze_l3_windows.py" $DATA_ROOT <owner>
$PY "$K/attribute_windows.py" probe mix        # ownership+adequacy verdict; composition
SHORT=<owner> SRC=1 DATA_ROOT=... WINSEC=2 \
  PROF_GROUPS="fe_miss fe_lat fe fpbr cache mlp core_ports dram_bw mem_bound fe_l3x priv" \
  "$K/replay_l3_profile.sh"                                            # skips run_1, fills 2..11
$PY "$K/analyze_l3_windows.py" $DATA_ROOT <owner> --plot
```
Serialized (GP counters shared; one capture at a time). Expected: composition reproduces;
magnitude and trajectory do not. Register new tasks in `attribute_windows.py` (CAMPAIGN/LANG/
PROBE) and `cross_task_grid.py` (LANG/NAME/ROOT/ORDER/TCOL) — currently manual.

### 2.4 Scripts and artifacts

| Item | Repo location | Role |
|---|---|---|
| `run_glm_campaign.sh` | `local_agents/kit/` | episode runner; this study added `dry_python()`, ISO-PROOF settle-retry, `swe_max_step()` liveness |
| `replay_l3_profile.sh` · `analyze_l3_windows.py` | same dir | per-group passes; window CSVs + figures; **basename tagger** (`_progs()`) |
| `attribute_windows.py` | same dir | ownership+adequacy gate (`probe`), per-pass composition (`mix`), cross-task tables |
| `cross_task_grid.py` | same dir | 12-task grids; `TASKS_ONLY`/`GRID_SUFFIX` freeze subset grids so deck figures can't drift from captions |
| `build_deck.py` | same dir | deck builder (promoted from scratchpad; `DECK_OUT`) |
| Episodes + replays + CSVs | `local_agents/ML_multiling/data/` | `glm_swe_*/`, `glm_replay_swe_*/`, `l3_study/all_windows_*.csv` (perf records gitignored; prometheus traj >100 MB gitignored per sympy precedent) |
| Galleries (7) + deck | artifact URLs on deck slide 26 | browsable per-metric sets |

## 3. Key insights (most → least important)

1. **Composition reproduces; magnitude does not.** Replay ≈1 % (Java ~7 %) vs 5.33× across live
   episodes of one instance. Every cross-task figure should be read as shares/distributions;
   absolute core-seconds are episode draws.
2. **Within-Go compile vs test: µop-cache 59.4 vs 37.6 MPKI (61.9 % vs 27.6 % of fence
   instructions)** — same episode, so no language/repo/instance confound. The only front-end
   contrast in the study that needs no sampling frame to defend.
3. **Java has the best front end of any tool workload** (µop-cache 25.9, DSB 82.5 %, L1I 9.6)
   despite the JVM's size; V8 — also a JIT — sits at 61.3. What the metrics track is *distinct
   code per unit work* (warmed hot loops vs streaming once through vast code), not compiler
   size and not "JIT vs interpreter".
4. **The two-part gate works, and both parts are needed**: ownership alone would have admitted
   gin (63.5 % owned, 15 windows). 3/12 instances rejected, all by automated criteria — the
   accepted nine aren't survivors of eyeballing.
5. **Every new language exposed at least one silent defect** (6 total). The common failure
   shape: confident wrong labels, invisible to the figure audit (which recomputes values, not
   labels). Path-collision matching was the root cause of three; basename matching is the fix.
6. **Front-end and memory pressure are independent axes**: Go pairs a near-C front end
   (µop-cache 51.0) with near-Rust DRAM-bound (7.2 % vs C's 1.5 %) at the study's lowest MLP
   (1.55) — consistent with GC/pointer-heavy runtime traffic, though the data doesn't prove
   that mechanism.
7. **Fence size is instance-dominated but only ~1.8× above episode noise** (9.6× per-pass
   spread vs 5.33× within-instance) — a far weaker claim than the uncorrected 100× version.
8. **Kernel share of the tool fence rises with build/IO-heavy toolchains** (Go 35.2 %, PHP
   36.9 %, Java 34.3 % vs Python-era ~20 %): a real component of "CPU outside inference" that
   pure user-mode analyses would miss.
