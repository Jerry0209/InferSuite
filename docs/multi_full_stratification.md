# The composition of a 'Task'

* SWE-bench multilingual mines a merged PR that closes and issue from different repos.
    * That PR contains two parts: the code fix (→ gold patch) and the tests the human contributor added (→ test patch). 

    * During an episode, SWE-agent receives only the problem statement and the repo checked out at the base commit. It does not receive the F2P/P2P lists, and the test patch is not applied 

* Each task in SWE-bench multilingual = issue text + gold patch + the test lists (F2P fail-to-pass, P2P pass-to-pass) + a prebuilt docker image

    * Issue text (from repo)
    * Gold patch (from repo)
    * Test patch (from repo)
    * Existing test (from repo)
    * Test lists (from bench)
        * Gather the F2P and P2P tests from the repo
        * F2P — the tests that were broken and are now fixed → you solved the stated problem
        * P2P — the tests that were passing and still pass → and you didn't break anything else
    * Docker image (from bench)
        * In order to maintain reproducibility
        * One per task
        * The repo, cloned and checked out at the base commit (the parent of the fixing PR)
        * The language toolchain: rustc/cargo, JDK + maven, PHP + composer, node, go
        * Every dependency already installed — a populated ~/.m2, vendor/, node_modules/, the Go module cache, target/
        * SWE-bench's own eval scripts (unused by us)


* Polling only starts after the container is built
    * SWE-agent installing its own tooling — and that's exactly what the bootstrap correction removes (the apt/dpkg lineage interval in the first 300 s; 15% of gin's fence).

# Definition of 'Type'

## Axis 1
* Axis 1 is about verification toolchain mechanism.

* Axis 1 is not about the agent at all. It asks: when some command in the trajectory runs the repo's tests, what process graph does the repo's own toolchain spawn inside the tool cgroup, and what burns the instructions there?

* Axis 1 is a lookup into a frozen 41-repo table returning a conditional proposition: once this repo's test entry point is invoked, what process tree unfolds inside the fence, and how is cost split between fixed and variable? It describes the repo's toolchain and has nothing to do with what the agent is trying to do.

* The unit of Axis 1 is CPU inside the tool fence (instructions, core-seconds). 

* The measured mechanism composition is a function of toolchain × cache state, not of toolchain alone.

* At the end, they will be verified with sweep results.


### Why it's a property of the repo, not the task

* A SWE-bench instance doesn't get to choose how its repo builds. `jq` has an autotools test target; `tokio` has `cargo test`; `gson` has maven+surefire; `laravel` has phpunit. One `run_tests` command → a process tree fixed by the repo's build system. So the label is a lookup, not an inference: `taxonomy_spec.json` assigns each class by literal repo-set membership (repo ∈ {`jqlang/jq`, `redis/redis`, …}), deterministic and reapplicable without an LLM.

* The "hence, of the language" is a corpus fact, not a law: in these 300 rows mechanism turned out to be a total function of language too (B = all C/C++, A = all Rust/Go, J = all Java, I = all PHP/Ruby, N = all JS/TS), zero exceptions. Nothing forbids a Python repo from driving tests through `make` — it just doesn't happen here. That collinearity is exactly why `plan.md:168` calls the repo confound the dominant limitation: the ⟨language × type⟩ grid is one cell wide per language by construction, so the mechanism axis buys stratification, not a second dimension.


### 9 languages → 5 classes

Languages are merged when their toolchain physics match — not when their syntax does. C and C++ look nothing alike, but both enter tests through `make`, so the process tree has the same shape.

| Class | Languages | Why merged |
| --- | --- | --- |
| **B** build-driver | C, C++ | The test entry point *is* a build target (`make`/`cmake`+`ctest`); whole-project compilation is unavoidable |
| **A** AOT-unified | Rust, Go | One command (`cargo test`/`go test`) compiles the dependency closure, then runs the artifact |
| **J** JVM-unified | Java | Bytecode compilation is in-process and cheap; JVM boot + classpath + surefire dominate |
| **I** interpreted | PHP, Ruby | No compilation anywhere on the test path — just runner + program under test |
| **N** node-transpile | JavaScript, TypeScript | The test command spawns a transpiler/bundler child, then runs the JS runner |

(There is also **Y** = pytest, a placeholder for 3 Python reference tasks. It is not in the 300-row corpus.)

Because each language lands in exactly one class, the nominal 9×5 ⟨language × mechanism⟩ grid has only 9 reachable cells — one cell wide per language. This is the sense in which the mechanism axis buys stratification, not a second dimension.


### Prior vs verdict

The static label is only a prior. It becomes a verdict via instruction-weighted command-tag composition of the fence, median over the dedicated-group replay passes, behind the **ownership** (≥50% of fence instructions in toolchain-observed windows) and **adequacy** (≥20 windows, ≥150 Ginstr) gates — `classification_protocol.md:44`.

That's where "mostly validated" earns its hedge: 5/9 clean on scoreable rows.

- **A** is refuted by 2 of 3 members (tokio compile 10%, gin 2% — warm build caches).
- **J**'s compile ≤15% arm is a tautology — maven compiles in-process, so no `javac` process can ever appear in a cmdlog regardless of physics.
- **N**'s transpile sub-term is unsupported (predicted 5–35%, measured 0% and 3%).
- Part of **A**'s refutation is a measurement artifact, not physics: tokio's argv log says 2.2× compile while its window composition says 8.7× test — they disagree in opposite directions, because priority-winner tagging lets `cargo test` swallow its own `rustc`.

Hence the wave-0a tagger repairs (basename matching, tag multiset) being prerequisites before A and N can be re-judged.


## Axis 2

The unit of Axis 2 is counts of actions in the trajectory. 


Axis 1 looks at instructions burned inside the fence. Axis 2 looks at the count of commands in the trajectory.

The decisive difference is what each instrument can see:

| | What it sees |
| --- | --- |
| **Axis 1** (cgroup fence) | Every descendant process — you issue one command, and every child, grandchild, and great-grandchild it forks counts |
| **Axis 2** (action classifier) | Only the top-level commands the agent issued — subprocesses are invisible |


---

### How actions are classified: four `act_class` values plus a catch-all

Deterministic regex, ordered matching (first hit wins), after stripping the `cd` prefix the harness prepends:

| Class | Meaning | What it matches |
| --- | --- | --- |
| **E** edit | modify a file | `str_replace_editor {str_replace, create, insert, write, append}`, `sed -i`, `patch` |
| **T** test | run tests | pytest/jest/vitest/mocha/rspec/phpunit/gotestsum/ctest, `go|cargo test`, `mvn|gradlew … test`, and reproduction scripts the agent writes itself (`python|node|php|ruby -c/-e`, `./reproduce*`) |
| **B** build | compile / install | make/cmake/ninja/gcc/g++/javac/rustc, `go|cargo build`, and `install|add|update|ci` for pip/npm/yarn/bundle/gem/composer/apt |
| **S** search | read and find | grep/rg/find/cat/ls/head/tail/tree/wc, `sed -n`, and `str_replace_editor view` |




Each kind of claim therefore belongs to its own instrument:

| Claim type | Instrument |
| --- | --- |
| Computation / CPU | Axis 1 + measured composition |
| Behaviour | Axis 2 |
| Magnitude | Neither — there is no static signal |




# Experiment Settings

## Model and temperature

* All 285 live episodes: GLM-5.2 through a litellm proxy, **temperature 0.6** — verified in every episode's banked `metadata.json` (285/285).
* 0.6 is the campaign standard. At 0.0 the agent degenerates into identical-action loops: all six verifiable django episodes at temp 0 died in greedy-decode loops (Report 01). Jef's experiments likewise show the results are not sensitive to temperature.
* For the measurement itself, temperature is moot: **we measure replays of frozen trajectories**. Decoding randomness exists only in the recording step; the measured runs make no model calls at all.

## Data collected (per replayed episode)

| Stream | File | Rate | What it is |
| --- | --- | --- | --- |
| trace | `traj/<inst>.traj` | input | SWE-agent's recorded action sequence; the replay re-executes it verbatim |
| CPU core-seconds | `cpustat_scope2.tsv` | 10 Hz | container cgroup `cpu.stat usage_usec` — exact kernel accounting of the tool fence |
| commands | `cmdlog.tsv` | 2 Hz | argv of every process alive in the fence (`epoch \t pid \t argv`) — a witness of *what ran*, never a rate |
| per-process CPU | `pidcpu.tsv` | 2 Hz | `utime+stime` per pid from `/proc/<pid>/stat` — consumption, not presence |
| exit receipts | `taskstats.tsv` | on process exit | one row per process death with its exact lifetime CPU (`epoch \t kind \t pid \t ppid \t uid \t comm \t utime_us \t stime_us \t etime_us \t btime`) |

## Methodology

1. **Replay, not re-run.** One live episode per instance was already recorded; `sweagent run-replay` re-issues the recorded actions with **no model call** (zero tokens; live episodes spent 1.60 G tokens, 89% of their wall clock waiting on the model). Verified fidelity: replay reproduces the live tool-fence CPU to 0.98–1.04 (n=3, same machine), action counts reproduce exactly (41/41, 64/64, 92/92), and replay-to-replay spread is 0.5–5% on totals, ≤3 pt on composition (three same-trajectory triplicates).

2. **Commands.** Every 0.5 s the poller lists `cgroup.procs` of the tool container and reads each pid's `/proc/<pid>/cmdline`. Example captured line:
   `1786428352.389165 <TAB> 610409 <TAB> /root/python3.11/bin/python3.11 /root/python3.11/bin/swerex-remote --auth-token …`
   This tells you *which* commands ran (and supplies argv for long-lived pids), but poll counts must never be used as CPU weights.

3. **CPU core-seconds.** The tool fence *is* the task container's cgroup. `usage_usec` from its `cpu.stat` is read at 10 Hz; the delta between two timestamps is core-seconds burned in between — exact kernel bookkeeping, valid on any machine under any contention. Sleeping/blocked time is never counted.

4. **Why taskstats.** Samplers structurally miss processes shorter than the sampling interval — on jq, 2 Hz per-pid sampling accounted for only 12% of the fence CPU (jq's test binary runs live ~1 ms each), and sampling 5× faster doubled coverage without changing the answer. taskstats is the kernel's exit-time accounting: on every process death it emits that process's exact lifetime CPU plus `comm`/`pid`/`ppid`. With receipts, 96.7–97.0% of every fence is accounted for (the ~3% residual is tick-granularity rounding). Receipts are machine-wide, so fence membership is decided offline by walking the `ppid` graph up to any pid ever seen in the tool cgroup. Self-test: receipt 1.507 s vs `/usr/bin/time` 1.50 s.

5. **Aggregation — two views, both reported.**
   * **Ownership**: a receipt's CPU belongs to the nearest enclosing driver front-end (`make`, `./configure`, `cargo test`, `phpunit`, …) found by walking its ancestry. This is the same ontology as the P7 window tagging and reproduces the P7 instruction-weighted truth to ≤9.1 pt on all three strict same-instance checks (jq, tokio, php-cs-fixer). **The matrix and the ≤30 selection use this view.**
   * **Process**: a receipt's CPU belongs to its own `comm` (thread-name fixups applied). This answers the mechanism question — e.g. rustc really burned ~half of tokio's fence even though `cargo test` "owns" it — but its coarse B/T/S projection is context-blind for driver children, so it is banked alongside, not selected on.

Reproduce: `./measure.sh typeid replay <instance>` (one), `./measure.sh typeid replay-sweep` (all; resumable; stop with `touch local_agents/ML_typeid/STOP_REPLAY`), then `python3 local_agents/kit/campaign/typeid_cpu_matrix.py build && … matrix`. Scope: **all 300** (289 typeid + 11 older consumed instances). The last four (prometheus-9248, terraform-35543, carbon-2813, laravel-51890) had no banked trajectory, so they were re-run live on 2026-08-19 and then replayed like the rest.

### Classification method

The method has two stages. **During the replay** we only record raw data; **after the replay** we read that data and classify. Nothing is judged at run time, so any rule can be changed later and the finished replays are simply re-analysed — no re-run needed.

#### Stage 1 — what is recorded during the replay

| File | Written by | One row means | Fields |
| --- | --- | --- | --- |
| `taskstats.tsv` | kernel exit receipts | one process (or thread) has just **died** | `comm` = its program name (kernel-visible, max 15 chars); `pid` = its process id; `ppid` = its parent's id; `utime`/`stime` = the exact CPU it used in its whole life (user / kernel, microseconds); `etime` = how long it lived |
| `cpustat_scope2.tsv` | 10 Hz poller | the container's total CPU so far | `usage_usec` from the container cgroup — the **fence total**, exact kernel accounting |
| `cmdlog.tsv` | 2 Hz poller | one process was **alive** at this moment | `pid` + its full command line (`argv`, e.g. `cargo test --lib`) |

Two things matter here. The receipt is the primary source: every process leaves exactly one, however short it lived, so nothing is missed. The 2 Hz log is now only a helper: it supplies the full command line for long-lived processes (the kernel `comm` is truncated, so `cargo` alone cannot say *test* or *build*). We tested 2 Hz against 10 Hz: faster polling doubled coverage but did not change a single label, so 2 Hz stays.

#### Stage 2 — how the recorded data is classified (after the replay)

`read the three files → fine tag per process → collapse to coarse class → attribute → shares → label`

**Step 1. Fine tag per process.** Each process is looked up by its program name (its `argv` if the 2 Hz log saw it, otherwise its `comm`). The lookup is a fixed table, matched top to bottom, first hit wins:

| Fine tag | Programs | Why it is its own tag |
| --- | --- | --- |
| `compile` | cc1, cc1plus, gcc, clang, rustc, javac, tsc, as, ld, collect2, lto1; Go's `compile`/`link`/`asm` | The real build workload. A leaf: it never spawns others. |
| `build-drv` | make, cmake, ninja, meson; configure, autoconf, m4, libtool; `cargo build`, `go build`; rake | A build **driver**: it burns almost nothing itself and orchestrates compilers. `configure` also spawns thousands of sed/grep to probe the compiler — these are build work, not agent searches, so a driver must exist to claim them. |
| `pkg` | apt, dpkg, pip, gem, composer; npm/yarn/pnpm with `install`/`ci`/`add` | Dependency installation (also identifies the container bootstrap). |
| `test-run` | phpunit, jest, vitest, mocha, rspec, pytest, ctest, tclsh, surefire; `cargo test`, `go test`; binaries named `*.test`, `*_test`, `-<16 hex>` (Go/Rust test binaries); the repo's own binary under test (see registry below) | The verification payload and its front-ends. |
| `runtime` | java, node, php, ruby, python, perl — when no test framework is visible in the arguments | A language runtime running something (usually the program under test or the agent's repro script). Counted as TEST. |
| `lint` | `go vet`, PMD | Verification work; kept separate so it stays visible. |
| `search` | grep, rg, find, cat, ls, head, tail, sed, awk, sort, wc, diff | The agent's read/locate tools. |
| `vcs` | git | Counted as SEARCH; listed separately because it is sometimes large. |
| *(scaffold)* | sh, bash, sleep, timeout, env, mkdir, rm, cp; `swerex-remote`; SWE-agent's own tool plumbing | **Excluded, no vote.** These are transparent wrappers — bash spawns everything, so "bash owns it" says nothing. |
| `other` | anything not matched | **No vote, but reported.** A large `other` bucket is the signal that the table is missing an entry. |

Order matters: `python3 -m pytest` is caught by `test-run` before it can fall to `runtime`; `npm install` is caught by `pkg` before `test-run`.

*Repo payload registry.* A repo's own binary — `jq`, `rg` in ripgrep, `hugo`, `caddy` — is the program under test, but no general rule can recognise it (`jq` looks like nothing; `rg` looks like a search tool). A small per-repo list marks these as `test-run`. Without it, 27% of jq's fence fell into `other`.

**Step 2. Collapse to three coarse classes.**

| Coarse class | Fine tags |
| --- | --- |
| **BUILD** | compile, build-drv, pkg |
| **TEST** | test-run, runtime, lint |
| **SEARCH** | search, vcs |

`other` and scaffold sit outside the three: they lower the "classified %" column but never vote.

**Step 3. Attribute CPU — two views, both computed.**

* **Process view**: each process's CPU is credited to its **own** class. `rustc` is BUILD no matter who started it. This is the direct physical answer ("what did the CPU actually run") and depends on nothing but the receipts.
* **Ownership view**: each process's CPU is credited to the class of its **nearest driver ancestor**. Walk up the `ppid` chain until you meet a driver front-end (`test-run`, `build-drv` or `pkg`); credit the CPU to that front-end's class. If no driver is found, use the process's own class. Only those three tags can be drivers, because only they mean "do this job for me"; leaves (compile, search) and transparent wrappers (bash) cannot own anything.

  A driver's own class is decided **by its children, not its name**: a `go` process that spawned `vet` or a `*.test` binary is a test invocation even if the 2 Hz log never saw its arguments. (This fix mattered: `go test ./...` spawns thousands of half-second `go` children that the log misses.)

Worked example, jq. The agent typed `make check`; the container grew this tree:

```
bash                      scaffold, skipped
 └── make check           driver: build-drv
      ├── cc1   2.1 s
      ├── cc1   1.7 s
      ├── ld    0.4 s
      └── jq    7.6 s     the jq binary running test cases
```

| Process | Process view | Ownership view (walk up → meet `make` → BUILD) |
| --- | --- | --- |
| cc1, ld | BUILD | BUILD |
| jq | TEST (payload registry) | BUILD |

Same `cc1`, different ancestor, different owner: under `cargo test`, a `rustc` child is TEST by ownership (cargo test owns it) and BUILD by process. A bare `grep -r foo` typed by the agent has no driver above it, so both views say SEARCH.

**Step 4. Shares and label.** Shares = each class's core-seconds ÷ total classified core-seconds. Label = the leading class if it leads the runner-up by **≥ 10 percentage points**, otherwise **M** (mixed). The 10-point margin exists because replay-to-replay noise is ≤ 3 points: a 45/44 split would flip between runs and is honestly a mixture anyway.


**Step 5. Evidence flags.** A label says *what type* an episode is; a flag says *how solid the evidence behind that label is*. Flags never change the label and never remove the row — a flagged row is kept in the table and shown in its own "low-evidence" column, so nobody mistakes "measured, but weak" for "empty cell". Dropping rows silently would hide exactly the cases a reader most needs to see.

| Flag | Condition | What it means |
| --- | --- | --- |
| `low-coverage` | CPU we could attach to a named process (receipts + last samples) is **< 80 %** of the container's total | A large part of the fence was burned by processes we never identified (normal is 96–99 %). The label rests on incomplete evidence. |
| `low-classified` | CPU that actually voted (BUILD/TEST/SEARCH) is **< 50 %** of the fence | We saw the processes but could not name them: too much went to scaffold or `other`. Usually the tag table is missing an entry for this repo. |
| `drain` | the replay hit the **2400 s** time cap and was stopped | The fence is a lower bound, not the whole episode. The type label is probably still right; the magnitude must not be compared. |
| `below-floor` | corrected fence **< 10 core-s** (from the ledger's magnitude bin) | Too little CPU to profile on P7 (its stop gate is 20 core-s), whatever the label. Skip at selection time. |
| `LOST` rows in `taskstats.tsv` | the kernel dropped receipts because the listener could not drain the netlink buffer fast enough | The episode's receipt set is incomplete by an unknown amount; every receipt-derived number is a lower bound. Recorded since 2026-08-20 — see "Receipt loss" below. |

**Step 6. Low evidence — when no label is issued at all.** A flag annotates a row that still has a label; **low evidence** (printed as `?`, and shown as the "no evidence" column of the matrix) means the opposite: the measurement does not support any label, so none is given. Three conditions trigger it, tested in this order. (i) *Thin fence* — fewer than **10 classified core-seconds**: the agent never really invoked the toolchain, and what the fence contains is container bootstrap, shell and a little git; there is simply nothing to type (44 of the 75 low-evidence rows, mostly PHP episodes of 2–5 core-s). (ii) *Mostly unclassified* — less than **50 %** of the fence CPU voted: either a large process is deliberately unscored (one long `git` operation in rubocop-13396) or coverage itself was poor because very short children died unrecorded (preact-3454, prometheus-9248); we know roughly what ran, but not enough of it to name a winner (3 rows). (iii) *Replay invalid* — the **replay/live fence ratio falls outside [0.5, 2]**: the replay did not reproduce the recorded episode, so whatever CPU it burned is not that episode's CPU (28 rows: lucene's failed gradle network check, caddy's drain cap, and tiny fences where a few seconds of bootstrap swing the ratio). The first two conditions are properties of the *episode* ("there was nothing to measure"); the third is a property of the *measurement* ("this run is not comparable"). Both kinds are kept in the table and counted in their own column, never dropped, because "no such episode" and "an episode we could not type" are different facts and a reader must be able to tell them apart. The test is applied per view, so a row can be `?` in one view and labelled in the other: 75 rows are low evidence by ownership and 77 by process. The two extra are PHP episodes (phpspreadsheet-3463, -3659) whose fence is mostly the `php` runtime plus a package install: ownership credits the installer's children to it and clears the floor, while the process view splits the same CPU and falls just under. The gap used to be much wider — before the tag table learned the truncated process names (see the note on `other` below) six redis rows were `?` in the process view alone.

#### Which view do we use, and why both are kept

* **Ownership** is the view that can be validated: it uses the same ontology as the P7 2-second window tags, and matches the P7 instruction-weighted truth to ≤ 13 points (leaders all correct) on the three same-instance checks. It answers "which kind of agent command paid for this CPU".
* **Process** is the view with no assumptions: no ancestor walk, no dependence on the 2 Hz log. It answers "what physics did the CPU run". It is the one that shows, for instance, that half of tokio's fence is really `rustc` even though `cargo test` owns it — and that jq's fence is a third compiling and half the jq test suite.

Both are columns in `cpu_matrix.tsv`; the ≤ 30 selection can be driven by either (a `--view` switch). Because the selection's purpose is to stratify CPU physics for P7 profiling, the process view is a defensible primary; the ownership view is the P7-comparable projection reported alongside.

#### Known limits

* Coverage: receipts + last samples account for 96–99% of the fence total; the ~3% residual is tick-granularity rounding.
* `other` is a maintenance signal, not a class: the payload registry has to be extended by hand when a new repo appears.
* CPU time is not instruction count. On the four tasks where both weightings can be compared they agree within 2 points; busy-wait would fool any per-process counter and is left to the P7 TMA layer.





# Expected final matrix examples

**Per-episode rows** (`local_agents/ML_typeid/cpu_matrix.tsv`; these three are real pilot rows):

| instance | lang | mech | fence (core-s) | coverage | own B/T/S | own label | proc B/T/S | proc label |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| jq-2681 | C | B | 29.0 | 96.8% | 90/9/1 | **B** | 43/16/41 | M |
| tokio-6551 | Rust | A | 116.0 | 97.0% | 10/89/0 | **T** | 50/49/0 | M |
| php-cs-fixer-7523 | PHP | I | 81.0 | 96.7% | 0/99/1 | **T** | 0/99/1 | T |

**Label definitions** (a share = % of the classified tool-fence CPU; label = the leading class if it leads by ≥10 pt, else M):

| Label | One-sentence definition |
| --- | --- |
| **B** build-dominated | Most fence CPU was burned by build machinery: compilers (`cc1`, `rustc`, `javac`), linkers, build drivers (`make`/`cmake`/`ninja`, `cargo\|go build`), and package installs. |
| **T** test-dominated | Most fence CPU was burned executing the verification payload: test runners (`phpunit`, `jest`, `cargo test`, surefire, …), the language runtime running tests or the agent's own repro scripts, and the repo's own binary under test. |
| **S** search-dominated | Most fence CPU was burned by read/locate tooling (`grep`/`rg`/`find`/`cat`/`sed -n`) — this column staying near-empty is itself a finding: search actions are many but cheap. |
| **M** mixed | No class leads by ≥10 pt, so the episode is a genuine mixture — a 49/47 split is not "dominated" by anything. |

**Why there is no E column.** E (edit) is an *action* category, not a CPU category: modifying a file costs essentially no compute. Measured, editor CPU is 0% of fence instructions in all eight ground-truth episodes — including jq-2681, whose gold patch is the largest in the reference set (6 files / 71 hunks / 1561 added lines → editor CPU **0%**). A class whose share is always ~0 can never lead, so E is unreachable as a CPU label. The real cost of an edit appears *indirectly*, as the **B** work it triggers (recompiling whatever the edit dirtied). E stays a live category on Axis 2 (action counts), where edits are 1–10% of actions.

A row carries **no evidence** ("?") when fewer than 10 classified core-seconds exist, when less than half of the fence was classified, or when the replay/live fence ratio falls outside [0.5, 2] (the replay did not reproduce the episode); it is kept and shown in its own column, never dropped. Note the two views can legitimately disagree (tokio: T by ownership, half-compile mixture by process) — a cell's answer states both, never one forced word.

# Final matrix (complete corpus, 2026-08-19)

**Population:** **300 replayed episodes** = 289 typeid + 11 older consumed instances. The four instances that had no banked trajectory (prometheus-9248, terraform-35543, carbon-2813, laravel-51890) were re-run live on 2026-08-19 and then replayed, so the corpus is now complete. Zero unresolved failures; 7 trajectories needed the harness-abort turn stripped before replay (axios-5316, fluentd-3640, lombok-3486/3571/3674/3697, bat-1892). Receipts: 17.90 M rows (deduplicated on pid+birth time); coverage median 99.4 %, 8 rows < 80 %; 40 replays hit the 2400 s drain cap (fence = lower bound). Corpus-wide replay/live fence ratio (n=288): median 0.995, IQR 0.93–1.09. A **replay-invalid gate** (ratio outside [0.5, 2]) marks a row "no evidence" when the replay clearly did not reproduce the live episode; the per-row diagnosis (see "Replay invalid" below, revised 2026-08-25) attributes all 28 to three measured causes — **lucene's gradle wrapper-jar download failing offline** (7 rows: JVM tests never ran), **wall-proportional background burn from leaked test servers** (8 rows: the live fence was mostly idle-time background at 0.03–0.16 cores, which the compressed replay wall removes), and **replays pinned at the 2400 s drain cap** accruing slow background onto tiny live fences (13 rows, the E7-loop episodes). Without the gate those rows would have shipped as labels measuring a broken toolchain or a leaked server rather than the agent's work. The 75 no-evidence rows (ownership view) split into 44 **thin fences** (under 10 classified core-seconds — the agent never invoked the toolchain), 28 **replay-invalid** rows (the gate above), and 3 rows where the classified share of the fence stayed under half. Files: `local_agents/ML_typeid/cpu_matrix.tsv` (per-episode rows, both views plus the count-weighted columns), `selection_30.tsv`. Figures: `docs/figures/typeid_cpu/08a_matrix_process_view.png`, `08b_matrix_ownership_view.png` (the 30 picks are marked ★), `08c_no_evidence_reasons.png`, `08d_matrix_count_view.png`.

**Ownership view** (which agent command paid; P7-comparable — drives the selection):

| language | class | B | T | S | M | no evidence | n |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C | B | 12 | 6 | 0 | 1 | 11 | 30 |
| C++ | B | 12 | 0 | 0 | 0 | 0 | 12 |
| Rust | A | 16 | 22 | 0 | 4 | 1 | 43 |
| Go | A | 14 | 17 | 0 | 3 | 8 | 42 |
| Java | J | 0 | 32 | 0 | 0 | 11 | 43 |
| PHP | I | 1 | 18 | 0 | 0 | 24 | 43 |
| Ruby | I | 0 | 31 | 0 | 0 | 13 | 44 |
| JavaScript | N | 0 | 25 | 0 | 0 | 6 | 31 |
| TypeScript | N | 0 | 11 | 0 | 0 | 1 | 12 |
| **all** | | **55** | **162** | **0** | **8** | **75** | **300** |

**Process view** (what the CPU physically ran):

| language | class | B | T | S | M | no evidence | n |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C | B | 11 | 8 | 0 | 0 | 11 | 30 |
| C++ | B | 12 | 0 | 0 | 0 | 0 | 12 |
| Rust | A | 38 | 2 | 0 | 2 | 1 | 43 |
| Go | A | 32 | 1 | 0 | 1 | 8 | 42 |
| Java | J | 0 | 32 | 0 | 0 | 11 | 43 |
| PHP | I | 1 | 16 | 0 | 0 | 26 | 43 |
| Ruby | I | 0 | 31 | 0 | 0 | 13 | 44 |
| JavaScript | N | 0 | 25 | 0 | 0 | 6 | 31 |
| TypeScript | N | 0 | 11 | 0 | 0 | 1 | 12 |
| **all** | | **94** | **126** | **0** | **3** | **77** | **300** |

**What the matrix says**

1. **It stratifies.** 16 populated ⟨language, type⟩ cells by ownership (15 by process) versus one column for the behavioural matrix (215/225 search-led). B, T and M are all real, populated types.
2. **The S column is empty in both views** (0/225 labelled rows). Search never dominates CPU — search actions are many but cheap. This is the measured version of "action mix ≠ CPU mix".
3. **Class A (Rust, Go) splits within the language, and the two views disagree about it — both correctly.** By ownership Rust is 16 B / 22 T / 4 M and Go 14 / 17 / 3: whether an episode is build- or test-dominated depends on how much of the closure the agent's edits dirtied, not on the repo. By process both are ~90 % B: the compiler is what actually burns, whatever command owns it. So the earlier "class A refuted by tokio and gin" verdict was an ontology artifact — A's own definition ("a mixture; compile ≥ 20 % and runner ≥ 20 %; refuse to predict the winner") is exactly what the ownership row shows.
4. **Class B is not uniformly build-dominated.** C splits 12 B / 6 T / 1 M by ownership and 11 B / 8 T by process: most jq/redis/valkey episodes spend the fence running the repo's own test binary, and only the large-patch episodes (jq-2681, the P7 reference with the corpus's largest gold patch; redis-11631) are heavily build. C++ is 12/12 B — but 11 of 12 are fmt, a header-only template library, so this is an fmt statement (W-CONFOUND), not a C++ one.
5. **Classes J, I, N behave exactly as their prior predicts:** T-dominated with essentially no exception, identical in both views (no compilation to re-attribute). The prior is simply correct there, and stays boring — as a good prior should.
6. **PHP has the largest no-evidence column (24 of 43)** and Java's 11 are mostly the lucene replay failure. These are small fences (median ~10 core-s) whose CPU is mostly the language runtime and git; the P7 stop gate (20 core-s) would reject them anyway. It is a magnitude finding about PHP tasks in this corpus, not a classification failure.

**Selection (30 of 300)** — `selection_30.tsv`, produced by `local_agents/kit/campaign/typeid_select.py`. The rule is deterministic, so it can be re-run after any matrix rebuild and the picks change only when the data changes.

*Eligibility.* Only rows carrying a **B / T / M label in the ownership view** may be picked. A `?` row has no type evidence, so it can never represent a cell — that is the whole point of keeping the no-evidence column separate rather than guessing.

*Step 1 — cover the grid (16 picks).* One representative per populated ⟨language, type⟩ cell. Cells are filled **smallest first**, so a cell with only one member claims its repo before a large cell has to choose; otherwise the big cells would take the shared repo and the small cell would be left with nothing. Within a cell candidates are ranked by, in strict order: E7-clean in the live ledger (no starvation, loop or drain flags) → coverage ≥ 80 % → classified ≥ 50 % → a repo not already picked → not a W-CONFOUND repo (fmt is 11 of 12 C++ rows, preact 17 of 31 JavaScript rows, so picking them would make a language claim that is really a repo claim) → **closest to the cell's median fence**. The median, not the maximum: a representative should be typical of its cell, not its outlier. The next candidate in that same order is recorded as the runner-up, which is what makes a pick replaceable without re-deriving anything.

*Step 2 — a second repo per language (5 picks).* Any claim at language level needs at least two repos behind it, otherwise "C++ is build-dominated" is really "fmt is build-dominated". Languages that already have two picked repos are skipped.

*Step 3 — magnitude spread (9 picks).* The largest, then the smallest typed fence per language, so the subset spans the size range P7 will meet (17 core-s to 4,000). Two guards: a candidate is skipped when it does not widen the language's existing spread by more than 1.5×, and a fresh repo within 1.5× of the extreme beats an already-picked repo — breadth is worth more than the last few core-seconds. 16 cells → 16 picks; +5 second-repo picks; +9 magnitude picks (largest fence per language, smallest measurable for C). 28 distinct repos, all 9 languages, only one already P7-profiled (gson-2061, kept deliberately as the calibration anchor). Caveats carried per row: **axios-6539 (19 core-s) and micropython-13039 (17 core-s)** sit below the 20 core-s P7 stop gate and were kept only as magnitude-spread anchors, and **hugo-12204** is one of the 40 replays that hit the 2400 s drain cap — though its replay/live ratio is 1.05, so the cap truncated wall-clock without losing fence CPU, and the row passes the gate on its own merits. Seven picks carry `call-step-mismatch` in the live ledger; that flag is bookkeeping (proxy calls vs logged steps), not a viability flag. Every pick is a **prior** — the P7 live episode plus its layer-3 gate stays the verdict.


## Justification

This section answers four questions a careful reader will ask about the final matrix:
what a "mixed" episode really looks like, what the two "no-evidence" reasons mean in
practice, why four tasks are missing, and why PHP has so many no-evidence rows. Every
number below comes from `cpu_matrix.tsv`.

### What a "mixed" episode looks like

A "mixed" (M) label is not a failure. It means we measured the fence cleanly, but no
single class (build, test, or search) leads the next one by 10 percentage points or more,
so we refuse to name one winner.

In practice, every mixed episode is close to a 50/50 split between build and test, with
almost no search. There are eight of them, and all but one are Rust or Go:

| instance | language | fence (core-s) | ownership B/T/S | process B/T/S |
| --- | --- | --- | --- | --- |
| tokio-rs__axum-734 | Rust | 1108 | 49/51/0 | 99/1/0 |
| sharkdp__bat-3108 | Rust | 251 | 46/54/0 | 83/17/0 |
| sharkdp__bat-562 | Rust | 130 | 54/45/0 | 56/44/0 |
| uutils__coreutils-6377 | Rust | 101 | 55/45/1 | 93/7/1 |
| caddyserver__caddy-5626 | Go | 154 | 53/46/0 | 85/15/0 |
| gin-gonic__gin-1957 | Go | 25 | 48/51/1 | 61/38/1 |
| gin-gonic__gin-3741 | Go | 19 | 47/52/0 | 86/13/0 |
| redis__redis-10068 | C | 38 | 54/46/0 | 54/44/1 |

So a typical mixed episode is about 48–52% build, 48–52% test, and 0% search. This is not
an accident. These tasks belong to class A, where one command (`cargo test` or `go test`)
both compiles the code and runs the tests. The ownership view credits the compile step to
the test command that started it, so the split lands near 50/50. The process view on the
right shows what really burned the CPU — often 85–99% compiler. This gap between the two
views is the signature of class A, not a problem.

### "Replay invalid" — the replay ran, but its CPU was very different from the live run

Every episode is a saved recording of the agent's actions. We re-run that recording with no
model calls, to measure CPU cheaply. We only trust the result if the replay's fence is
close to the live episode's fence. The test is a ratio (replay CPU ÷ live CPU) that must
fall between 0.5 and 2. If it falls outside that range, the replay did not reproduce the
episode, so we give the row no type label.

**Per-row diagnosis (2026-08-25, revised).** All 28 rows were re-examined from banked
evidence — live `episode_summary.json`, replay `cpustat` spans (summed over positive
increments, because the container cgroup resets when it turns over), and replay log
markers — by `kit/campaign/typeid_replay_invalid_report.py`, which banks the full table in
`local_agents/ML_typeid/replay_invalid_report.tsv`. The key instrument is a two-point
decomposition: the same action sequence was measured under two different wall clocks (live
with model waits, replay without), so `fence = action_CPU + background_rate × wall` solves
per row, and a large wall-proportional term is the signature of a leaked background
process.

| Cause | Rows | Mechanism |
| --- | --- | --- |
| **gradle-wrapper-offline** | 7 (all lucene, 0.07–0.29×) | every `./gradlew` repeatedly tries to download `gradle-wrapper.jar` and fails offline — the JVM tests never start; the replay measured bootstrap only |
| **background-dominated** | 8 (5 caddy, 2 micropython, 1 jq; 0.32–0.47×) | these replays finished in 25–95 s; the live fences were mostly leaked test servers/daemons burning 0.03–0.16 cores through the model-wait gaps — the replay compresses the wall and that component vanishes |
| **drain-cap-background** | 13 (2.0–10.6×; 12 are E7-loop episodes) | the mirror image: a lingering process kept the fence from going quiet, so the replay sat pinned at the 2400 s drain cap, accruing ~12 core-s of slow background onto live fences of only 1–6 core-s |

**Side-finding worth keeping:** degenerate live episodes can burn *tenths of a core* in
leaked processes while the agent is only waiting on the model. The gate is catching real
wall-proportional background burn, not replay noise — and that idle-time background burn is
itself a property of live agentic episodes that any harness-level energy or capacity claim
should account for.

Three causes in detail, and an earlier version of this section got two of them wrong:

- **gradle-wrapper-offline — the 7 lucene rows (ratios 0.07–0.29).** The replay logs show
  every `./gradlew` invocation repeatedly attempting to download `gradle-wrapper.jar` from
  the network and failing (12 attempts per episode), so the JVM tests never start and the
  replay fence (16–49 core-s) is bootstrap plus wrapper attempts, against live fences of
  92–522 core-s. It is the wrapper-jar download, not a "start-up network check" as
  previously written.
- **background-dominated — 8 rows: 5 caddy, 2 micropython, 1 jq (ratios 0.32–0.47).** The
  earlier claim that these `go test` / C suites "ran past the 2400 s time cap" is **wrong**:
  their replays completed in **25–95 s**. What actually happened: the live fences were
  mostly wall-proportional background burn — leaked test servers/daemons at an implied
  0.03–0.16 cores (caddy's integration tests start caddy servers) running through the live
  episode's long model-wait gaps (600–1,400 s of wall). The replay compresses the wall to
  under two minutes, that component vanishes, and only the action CPU remains — e.g.
  caddy-6350: live 189 core-s over 934 s, replay 83 core-s over 95 s, background
  0.13 cores. The replay is not wrong here; the two runs measure different amounts of
  *idle-time background burn*. This is also a finding in its own right: degenerate live
  episodes can burn tenths of a core in leaked processes while the agent is only waiting
  on the model.
- **drain-cap-background — 13 rows (ratios 2.0–10.6; 12 of 13 are E7-loop episodes).** The
  mirror image: these replays all sat pinned at the **2400 s drain cap** (a lingering
  process never let the fence go quiet), accruing ~0.005 cores of slow background for the
  full 40 minutes (~12 core-s) on top of live fences of only 1–6 core-s — so the ratio
  explodes upward. The tiny-fence instability noted before is real, but the cap-pinned
  drain is the measured mechanism.

Without this gate, the lucene rows would have shipped as confident labels from replays
whose toolchain never ran, and the background-heavy rows as labels measuring a leaked
server rather than the agent's work.

### "Mostly unclassified" — we saw the CPU, but the program name is not in our table

Each process is named by looking up its program in a fixed table. Anything not in the table
goes to "other" and gets no vote. When the voting classes (build + test + search) cover
less than half of the fence, we cannot honestly name the type. Three rows hit this, and
each for a different reason:

- **rubocop-13396** (Ruby, fence 43 core-s, but only 24% classified): the top process is
  git, which burned 29 of the 43 core-s. Git is counted as search but listed on its own,
  and here one large git operation dominated the fence. We know exactly what ran; it is just
  not a build/test/search signal.
- **preact-3454** (JavaScript, fence 31 core-s, coverage 57%): here the problem is coverage
  — about 43% of the fence CPU was never attached to any named process, because short-lived
  node children died unrecorded. Of what we could name, test led, but on less than half
  the fence we do not commit.
- **prometheus-9248** (Go, fence 212 core-s, coverage 52%): the same coverage problem at a
  much larger size. The listener banked 11,013 exit receipts, which is far fewer than a Go
  build of this size forks, so receipts were probably lost during the compile burst. What we
  did capture is 66 core-s of compiler and 18 of build driver — a build-dominated episode on
  the face of it — but on half the fence we refuse to say so. Re-replaying it would settle
  the question; it is the only large episode in this state.

So "cannot name" means either a real workload we do not score (git) or CPU that slipped
through (very short processes, or receipts lost under a fork storm) — not a mystery about
what the program was.

### The last four tasks — recorded on 2026-08-19, and why they still carry no type

Four tasks were long missing: prometheus-9248, terraform-35543 (Go), carbon-2813,
laravel-51890 (PHP). They never crashed and never failed a gate; they had been consumed by
earlier campaigns, and unlike the other 11 such tasks their trajectories were not saved
anywhere on disk, so there was nothing to replay. On 2026-08-19 they were re-run live (73
minutes, fresh tokens) and then replayed with the full instrument set, which completes the
corpus at 300 rows — Go now shows n=42 and PHP n=43.

All four land in the no-evidence column, each for a reason the gates already describe:

| task | fence (core-s) | why no type |
| --- | --- | --- |
| prometheus-9248 | 212 | receipts cover only 52 % of the fence (see above) |
| terraform-35543 | 12 | replay/live ratio 4.98 — the live episode was 2.4 core-s |
| carbon-2813 | 15 | replay/live ratio 2.99; the live run was also API-starved |
| laravel-51890 | 7 | thin fence: 7 core-s total, under the 10 core-s floor |

Three of them are below the 20 core-s P7 gate anyway, so they were never selection
candidates. Only prometheus-9248 is large enough to matter, and it is the one row where a
re-replay could still turn a "no evidence" into a label.

### Why PHP has the most no-evidence rows — it is about size, not classification

PHP has 24 no-evidence rows out of 43, and 15 of them are thin fences: under 10 classified
core-s, because the agent barely ran the toolchain. Real examples:

| instance | fence (core-s) | classified (core-s) | top processes |
| --- | --- | --- | --- |
| laravel-48636 | 2.1 | 1.0 | runtime 0.8, git 0.3, search 0.2 |
| laravel-53914 | 2.9 | 1.4 | runtime 1.2, git 0.5 |
| phpspreadsheet-4114 | 4.0 | 2.7 | runtime 2.4, search 0.3, git 0.3 |
| laravel-52684 | 4.7 | 3.4 | pkg 1.2, runtime 0.8, git 0.5 |

The median PHP thin fence is about 5 core-s. PHP is interpreted (class I): there is no
compilation, and the test suites here are small, so the whole episode is a few seconds of
`php` runtime plus git. There is almost no CPU to classify. This matters because the P7
profiling machine has a 20 core-s stop gate — it will not spend time on a fence this small.
So these tasks would be rejected for profiling no matter what type they are. The classifier
is correctly saying "there is not enough CPU here to type," which is the right answer and
lines up exactly with the tasks P7 would skip. It is a fact about the size of PHP tasks in
this corpus, not a failure of the method.

### Naming the last 3 % — the `other` census (2026-08-19)

Every process whose program name is not in the tag table lands in `other` and does not vote,
so `other` is the maintenance signal for the table. A census over all 300 replays found
**1,374 core-s in `other`, 3.1 % of the 44,300 core-s of in-fence receipts**, spread over
43,922 distinct names — but only 58 of those names carried as much as one core-second. The
long tail is thread names; the head was six recognisable families, and two of them were not
missing entries at all but the same bug twice: the kernel truncates a process name to 15
characters, so `lto1-ltrans` (GCC's LTO worker, 482 core-s in redis and valkey) and
`integration.tes` (a Go test binary) never matched the `lto1` and `*.test` entries that were
already in the table. The rest were `esbuild` (the JS/TS transpiler, 136 core-s), Rust test
threads named after the test path, headless-chromium threads, `clippy`/`rustfmt`, and
artifact-inspection tools (`javap`, `nm`, `strings`). After the fixes `other` is **80 core-s,
0.2 %**, and no unnamed process reaches 10 core-s anywhere in the corpus.

Two consequences worth recording. First, the process view gained six rows that had been "no
evidence" purely because their compiler CPU was unnamed (five redis, one valkey) — C moves
from 5 B / 8 T to 11 B / 8 T. Second, `esbuild` is direct evidence for the transpile term of
class N, which the earlier window analysis had measured as 0 %: it was running, it was simply
unnamed. The ownership view barely moved (three labels), because a driver ancestor was
already paying for most of this CPU — which is the same robustness argument that makes
ownership the view the selection is built on.

One defect was introduced and caught during this work: the pattern for Rust test-thread names
(`::`, `/src/`) was first written unanchored and matched against the full command line, which
tagged every compile whose arguments mention a `/src/` path as a test run — it flipped redis
and nlohmann from build to test before the ownership tables were re-read. The rule is now
anchored to thread-name shape (no leading slash, no spaces), and the tagger is checked against
a fixed list of known commands after every edit.

### Count-weighted classification: tested, not adopted

A fair objection to this whole method is that time-weighting favours build and test by
construction: compilers and test runners are slow, `grep` is fast, so search can never lead.
The alternative is to weight every command equally — label an episode by the class with the
most *leaf commands* (a command that executed inside the fence and spawned nothing) instead of
the most CPU. We implemented it over all 300 episodes and compared.

The distribution does change, a lot. Ownership gives B 55 / T 162 / M 8, and the S column is
empty; leaf-count gives **B 61 / T 109 / S 60 / M 42**, and the two agree on only 112 of the
225 rows both can label. So this is not a negligible difference that can be waved away.

Here is the same ⟨language × type⟩ grid under count weighting, with the time-weighted
(ownership) number in brackets for contrast — figure
`docs/figures/typeid_cpu/08d_matrix_count_view.png`:

| language | class | B | T | S | M | no evidence | n |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C | B | 1 (12) | 8 (6) | **13** (0) | 5 (1) | 3 | 30 |
| C++ | B | 12 (12) | 0 | 0 | 0 | 0 | 12 |
| Rust | A | **31** (16) | 8 (22) | 0 | 4 (4) | 0 | 43 |
| Go | A | 13 (14) | 7 (17) | 0 | **15** (3) | 7 | 42 |
| Java | J | 1 (0) | 1 (32) | **24** (0) | 8 (0) | 9 | 43 |
| PHP | I | 2 (1) | 11 (18) | **15** (0) | 6 (0) | 9 | 43 |
| Ruby | I | 1 (0) | **39** (31) | 2 (0) | 2 (0) | 0 | 44 |
| JavaScript | N | 0 | **28** (25) | 1 (0) | 2 (0) | 0 | 31 |
| TypeScript | N | 0 | 7 (11) | 5 (0) | 0 | 0 | 12 |
| **all** | | **61** (55) | **109** (162) | **60** (0) | **42** (8) | 28 | 300 |

Three rows carry the whole argument. **Java** goes from 32 T to 24 S: a JVM test run is *one*
`java` process burning hundreds of core-seconds, while the agent typed dozens of cheap greps
beside it — by headcount the greps win, though nobody would call the episode a search task.
**Rust** moves the opposite way, 16 B → 31 B, because `cargo test` forks thousands of `rustc`
children. So count weighting is not biased towards search; it is biased towards **whatever
forks most**, which is a property of the toolchain, not of the workload. **C++** is the only
language where the two agree exactly (12 B either way): every fmt test compiles, so headcount
and CPU point at the same answer.

But the change is diagnosable, and one number explains it:

| class | leaf commands | % of commands | core-s | % of CPU | ms per command |
| --- | --- | --- | --- | --- | --- |
| SEARCH | 139,877 | 13 % | 308 | 1 % | **2.2** |
| TEST | 535,364 | 48 % | 7,185 | 31 % | **13.4** |
| BUILD | 438,847 | 39 % | 15,678 | 68 % | **35.7** |

A counted search costs 2.2 ms; a counted build command costs 16× more. Counting does not
uncover hidden search CPU — it declares one `wc` equal to one `cc1`. And the commands it
counts are mostly not the agent's searches at all, but the toolchain's own shell plumbing:
vue-11739 flips from test to search on 4,617 `grep` + 4,571 `cat` + 4,522 `sort` + 4,522
`uniq` + 4,522 `wc` — one `sort | uniq | wc` pipeline run about 4,500 times by the build
tooling, 18 core-s in total, while esbuild and node burn 125. jq-2598 flips from build to
search on 3,680 `sed` calls (0.7 ms each) issued by `configure`, against 296 `cc1` runs at
103 ms each.

There is also a direct check on the original worry. The episodes where search genuinely leads
*by CPU* — php-cs-fixer-8367 (100 %), php-cs-fixer-7663 (70 %), carbon-2762 (69 %) — are all
already "no evidence" rows of a few core-seconds. The S column is empty because
search-dominated episodes are too small to profile, not because time-weighting hides them.
Count-weighting does not change that: those episodes still fail the 20 core-s P7 gate.

**Caveat on the count column, and how much it matters.** 23 episodes lost receipts partway
through when the taskstats listener was killed by a netlink buffer overflow (see the defect
note below), and they are concentrated exactly in the fork-heavy languages — Go 9, JavaScript
6, TypeScript 5. Their command counts are truncated, and they are still shown in the table
above. Applying a coverage ≥ 95 % gate and dropping those episodes gives B 55 / T 96 / S 59 /
M 39 with 51 no-evidence rows: Go falls to 8/6/12 and TypeScript to 2 T, but **the S column
barely moves (60 → 59)**. The dirty rows shift the B/T/M split; they do not create the search
column, so the conclusion below stands either way.

Conclusion: the type label stays time-weighted, because the question this taxonomy serves is
what the CPU spends its time on. The count-weighted numbers are banked next to it —
`n_leaf`, `leaf_B`, `leaf_T`, `leaf_S`, `leaf_label` in `cpu_matrix.tsv` — so the comparison
is reproducible without re-running anything. Where search *should* be visible is Axis 2,
which counts what the agent typed and finds 215 of 225 episodes search-led; the disagreement
between that and the CPU matrix is the finding, not a defect in either instrument.

#### Why the count column cannot be more than a reference

Three limits, and they are not the same kind of limit. Only the middle one can be engineered
away.

**1. What it measures is the toolchain's fork style, not the workload.** This is the decisive
one, and no instrument fixes it. Even with a perfect count, a JVM test run is *one* `java`
process burning hundreds of core-seconds while `cargo test` forks thousands of `rustc`
children for the same amount of work. That is why Java lands in S and Rust in B above: the
metric ranks languages by how many processes their toolchain happens to create. Fork style is
a property of the build system, not of what the episode is doing, so a label derived from it
does not answer "what kind of work is this task" — it answers "how fine-grained is this
toolchain's process model".

**2. Threads are counted as if they were commands.** taskstats emits one receipt per *task*,
and a thread is a task, so a `java` process with 40 GC and JIT threads leaves 41 receipts. The
matrix separates them by name shape (`tokio-runtime-w`, `GC Thread#0`, `ThreadPoolForeg`…),
which is a guess. The guess was audited against the pids the pollers saw in `cgroup.procs` —
that file lists only thread-group leaders, so every pid in it is a confirmed process — and only
**201 of 39,186 confirmed processes (0.5 %)** were wrongly discarded as threads. The opposite
direction, threads slipping through and being counted as commands, cannot be measured from
receipts at all, because the confirmed set covers just 3.5 % of counted commands. This limit
*is* fixable: the kernel's proc connector reports `child_pid` and `child_tgid` on every fork,
and `child_pid != child_tgid` is the kernel's own definition of a thread. A listener for it
(`procconn_listen.py`) now runs alongside taskstats on the re-replays, so the heuristic will
get a measured error bar instead of an argument.

**3. The answer depends on what we refuse to count.** `bash` leaves 4.8 M receipts in this
corpus and `sleep` 3.7 M — both are excluded as scaffold. Include them and every episode
becomes a shell episode. Time weighting is far less sensitive to that choice: the same two
programs are only 12 % of fence CPU, and that CPU is real work (process startup), not an
artifact of where a line was drawn.

Taken together: fixing (2) makes the count column *accurate*; nothing makes it *relevant* to
the question this study asks. It stays a documented alternative that we measured and did not
adopt.

### Receipt loss: found, fixed, being re-measured (2026-08-20)

The receipts arrive over a netlink socket, which has a fixed-size kernel buffer (`SO_RCVBUF`,
by default a couple of hundred kilobytes on this machine). Our listener reads one message,
decodes it and writes a line, and while it does that the kernel keeps pushing. When processes
die faster than we drain — a `go build ./...` forks thousands of short-lived children in a
second or two — the buffer fills, the kernel **drops** receipts and reports `ENOBUFS`
(errno 105) on the next read. Two things then go wrong at once: the dropped receipts are gone
for good (netlink never resends), and our receive loop catches only `socket.timeout`, so the
error escapes the loop and **the listener exits**. From that moment the episode records nothing
at all.

This is not hypothetical: 23 of the 300 episode logs contain the traceback. prometheus-9248
banked 11,279 receipts before dying (coverage 52 %); hugo-12171 reached 87,361 (coverage 93 %).
The affected set is concentrated in the fork-heavy languages — Go 9, JavaScript 6, TypeScript 5,
plus one each of C, Rust and Java. Eight rows fall below 80 % coverage, and **four are current
selection picks** (hugo-12171, immutable-js-2005, preact-3010, docusaurus-9897). The bias has a
known direction: truncation always loses the *end* of the episode, and dependency installs and
compilation happen at the start, so an affected row over-states BUILD.

**The fix** (`taskstats_listen.py`, three changes): a 64 MB receive buffer set with
`SO_RCVBUFFORCE` before the socket is even registered, so no startup burst is lost; `ENOBUFS`
caught, counted, and written as a `LOST` row instead of killing the process; and receive
separated from decode by a queue, so the receiving thread does nothing but move bytes out of
the kernel buffer while a second thread parses. The `LOST` row matters on its own: loss becomes
*data in the file* rather than something inferred afterwards from a low coverage number.

Both paths were tested against a deliberate fork storm of 72,000 short-lived processes:

| test | result |
| --- | --- |
| 72,000 processes, 64 MB buffer | 72,127 receipts, **0 drop events**, listener alive |
| same storm, buffer shrunk to 8 KB to force the failure | **2,128 drop events recorded as `LOST` rows, listener alive**; 51,425 receipts banked |

Under the old code the second test is exactly what killed 23 episodes: the first drop ended the
run. The 23 are being re-replayed (no tokens) with the fixed listener; their damaged directories
are kept alongside as `*.enobufs_bak` for comparison. Until that finishes, their rows in the
matrix are the truncated ones, and the four affected picks should not be sent to P7.

# Selection (36 of 300) on the count view — the ML_iso36 profiling set (2026-08-21)

The count-weighted matrix above was built as a tested-not-adopted reference; this section
records the selection that was subsequently built **on** it, by PI directive: pick 36 tasks
for full P7 profiling (TMA + the complete metric card) using the **count view** (`leaf_label`),
**4 per language × 9 languages**, one per populated ⟨language, B/T/S/M⟩ cell, and when a row
has empty cells, take the extra picks from that language's **majority count category**. Files:
`local_agents/ML_typeid/selection_36_count.tsv` (the picks, with per-row reasons and
runner-ups), `local_agents/kit/campaign/typeid_select36.py` (the deterministic rule),
`local_agents/ML_iso36/plots/iso36_selection_matrix.png` (the picks drawn on the count
matrix), `local_agents/ML_iso36/README.md` (the campaign this feeds).

## Method

The rule mirrors `typeid_select.py` (the 30-of-300 ownership-view selection) with two changes:
the cell axis is the count label instead of the ownership label, and the quota is exactly 4
per language with majority top-ups instead of the three-step 30-slot budget.

*Profilability (hard excludes).* A cell only counts as populated if it holds a candidate that
can actually be replay-profiled on the P7: excluded are `replay-invalid` rows (28), E7
loop-degenerate episodes (41), and rows with no banked trajectory (11). This distinction
matters once: the JavaScript×S cell has n=1, but that one member is hard-flagged, so the cell
is *unprofilable* — its slot went to JavaScript's majority category, and the matrix figure
says "no profilable candidate" rather than "empty".

*One per profilable cell*, singleton cells filled first (their repo is forced, so the ranking
in bigger cells can account for it).

*Within a cell*, candidates are ranked by, in order: coverage ≥ 80 % → classified ≥ 50 % → a
repo not already picked → not a W-CONFOUND repo (fmt, preact) when an alternative exists →
**closest to the cell's median fence** (a representative should be typical of its cell, not
its outlier) → instance id as the deterministic tie-break. The next candidate in the same
order is recorded as the runner-up.

*Top-ups* walk down the majority cell's same ranking, preferring fresh repos.

## The realized matrix (picks per cell)

| language | B | T | S | M | top-ups |
| --- | --- | --- | --- | --- | --- |
| C | redis-12272 | micropython-13039 | jq-2598 | valkey-1499 | — |
| C++ | nlohmann-4237 | *empty* | *empty* | *empty* | + fmt-3750, fmt-3901, fmt-2457 (B) |
| Rust | nushell-13831 | ripgrep-2209 | *empty* | bat-2835 | + axum-1730 (B) |
| Go | caddy-4774 | gin-2121 | *empty* | prometheus-10720 | + hugo-12579 (M) |
| Java | gson-1093 | gson-2134 | lombok-3479 | javaparser-4538 | — |
| PHP | laravel-52684 | php-cs-fixer-8064 | carbon-2752 | phpspreadsheet-3463 | — |
| Ruby | fpm-1829 | fastlane-20958 | rubocop-13396 | rubocop-13560 | — |
| JavaScript | *empty* | babel-15649 | *(n=1, unprofilable)* | preact-3763 | + axios-6539, three.js-26589 (T) |
| TypeScript | *empty* | docusaurus-9897 | vuejs-core-11589 | *empty* | + immutable-js-2006, docusaurus-10130 (T) |

Column sums: **B 11 / T 12 / S 5 / M 8** = 36 picks; 27 distinct cells covered, 31 repos,
Σ tool-fence 4,797 core-s (17 → 655 per task).

## Honest limitations (all recorded per-row in the TSV `why` column)

- **C++ is 3× fmtlib** — the cell is 11/12 fmt, so with nlohmann taken first the top-ups have
  nowhere else to go. Any C++-level claim from this set is still largely an fmt claim
  (W-CONFOUND), exactly as in the 30-selection.
- **Java×B and Java×T are forced gson singletons** (n=1 cells), so those two cells share one
  repo.
- **Ruby×S and Ruby×M are forced single-profilable picks**; rubocop-13396 additionally carries
  a low classified % (24 % — one large git operation dominates its fence).
- **The search column is small (5 picks) and its members are small** (5–213 core-s): a fact
  about the population — count-search-led tasks are rare and mostly tiny — not about the
  sampler. Several PHP/Ruby picks sit under the historical 20 core-s magnitude gate; they are
  kept deliberately, because under this directive the cell exists and must be represented,
  and the dedicated-group replays make even small fences measurable (every window carries the
  pass's group at 100 % duty).
- Every pick is a **prior**: the P7 replay and its gates are the verdict on each row.

The profiling campaign itself (9 dedicated-group passes per task — the shared 8 plus
`fe_miss`, which turns the previous 13-of-16 metric card into 16-of-16 — plus DRAM read
bandwidth and context-switch rate, at 100 ms windows on cores 4–11 SMT-off) is documented in
`local_agents/ML_iso36/README.md`.


## Slides and per-task galleries (published 2026-08-24)

**Agent deck** (updated in place, now **41 slides**):
<https://claude.ai/code/artifact/e93ebcb7-015d-4f40-8f83-62fe21777e62>

Slides 37–47 carry this campaign: the selection matrix (37); **the replay-invalid gate with
per-row causes** (38, added 2026-08-25 — the fig. 9 scatter of replay vs live fence with the
three diagnosed cause families); **CPU work by fence over the 36 tasks** (39, added
2026-08-25 — slide 2's core-seconds split rebuilt on the replays: median 89% tools, but
53–66% on the small-fence tasks); **fence busy time in seconds** (40, added 2026-08-25 — the core-seconds companion in wall units, grouped never stacked, each tool bar annotated with its implied parallelism core-s ÷ busy-s: median ×1.2, up to ×3.6 on parallel builds); TMA Level 1 of the 36 tasks (41: tool and harness fences,
SPEC CPU 2026 INT/FP closing panel); **TMA Level 1 with both fences combined** (42, added
2026-08-26 — census counts summed across the two fences, slot-weighted, one bar per task,
with each task's tool-slot share in the margin); **the live-vs-replay validation** (43,
added 2026-08-27 — the 36 tasks' live census runs carry no counters by design, so the
validation rides the 12 same-trajectory pairs of the matched capture: per metric, the live
rotation distribution as a violin+box beside the dedicated-replay distribution, with one
replay violin per episode on the TMA panels; replay/live TMA median ratios retiring 1.00 /
bad-spec 0.96 / frontend 0.86 / backend 1.12; all twelve figures:
<https://claude.ai/code/artifact/a2ca53ea-cbcf-4427-b758-b933344fd64b>); the per-window distribution charts for both fences in
the **final format (2026-08-25, mentor spec)** — one metric per full-width row, workload
groups ordered **SPEC-int (14 benchmarks) → SPEC-fp (12) → one group per language**, each
language's 4 tasks as per-window boxes in the language's color — covering the mentor's 16
metrics **including the three fe_miss metrics** plus DRAM read bandwidth and context switches
(18 rows; slides 44–45); the **aggregated comparison view** (46, added 2026-08-25) — SPEC
collapsed to two suite boxes (SPEC-int / SPEC-fp, each a box over per-benchmark
window-medians so every benchmark votes once) plus a **Python group** (scikit-learn, astropy,
sympy from the matched-configuration replays; the three fe_miss metrics carry a "to be
measured" mark there and a fourth Python slot is reserved — no new profiling was run); and
the gallery index (47). The SPEC side's per-window derivations were extended so all 18
metrics exist there too; the earlier compact 18-panel grids (count-cell-type coloring) remain
banked beside the new figures. Note: the deck's share link
is version-pinned — viewers of an existing share see the new slides only after the share pin
is moved to the new version.

**Per-task per-window galleries** (one artifact per task, modeled on the SPEC gallery: every
metric with the tag-split tool-fence distribution, the harness-fence distribution, and both
episode timelines at 100 ms; links also on deck slide 47 and banked in
`local_agents/ML_iso36/gallery_links.json`):

### C

- redis-12272 (B): <https://claude.ai/code/artifact/db4944b6-6736-40f3-b65f-d99570ce7101>
- micropython-13039 (T): <https://claude.ai/code/artifact/0785f8ba-0c4a-4846-bde9-d778a3ce2623>
- jq-2598 (S): <https://claude.ai/code/artifact/a2b4d318-9892-4a46-a596-098d33bad391>
- valkey-1499 (M): <https://claude.ai/code/artifact/3ddb6092-f834-4853-99a4-61acc6766295>

### C++

- nlohmann-4237 (B): <https://claude.ai/code/artifact/77d5e44e-8b02-411f-8f8c-18838dd5890e>
- fmt-3750 (B, top-up): <https://claude.ai/code/artifact/ca7a60a6-be95-47a7-bb9e-cd3d8f386758>
- fmt-3901 (B, top-up): <https://claude.ai/code/artifact/d424b721-5eac-4618-9152-161a2cf5870e>
- fmt-2457 (B, top-up): <https://claude.ai/code/artifact/d82b1902-6c94-4c2c-bf7f-e643c23625c9>

### Rust

- nushell-13831 (B): <https://claude.ai/code/artifact/bbef37a9-2c28-4013-ad1b-30c22376c20f>
- ripgrep-2209 (T): <https://claude.ai/code/artifact/14150b17-215e-4b2f-bd32-638ae487aaf5>
- bat-2835 (M): <https://claude.ai/code/artifact/333bacd3-14dd-42bb-967c-d578932d9d2c>
- axum-1730 (B, top-up): <https://claude.ai/code/artifact/5089bf45-95ff-4b7c-b624-467eece4d97c>

### Go

- caddy-4774 (B): <https://claude.ai/code/artifact/086aee95-ab65-4eb2-9994-026277d3e90d>
- gin-2121 (T): <https://claude.ai/code/artifact/23701afc-0932-4050-82f5-7777b058133a>
- prometheus-10720 (M): <https://claude.ai/code/artifact/b9c14865-6d94-469f-b439-39009a1c39ff>
- hugo-12579 (M, top-up): <https://claude.ai/code/artifact/c23b8032-c73e-4fd3-b706-775d386fa4b0>

### Java

- gson-1093 (B): <https://claude.ai/code/artifact/88938855-14de-443d-b406-f056de789de9>
- gson-2134 (T): <https://claude.ai/code/artifact/53e7dcf5-fd55-495d-836f-55c4cfac0efb>
- lombok-3479 (S): <https://claude.ai/code/artifact/cdb06472-d9e0-4ba1-af5d-c2633789cd5a>
- javaparser-4538 (M): <https://claude.ai/code/artifact/96cfcacc-cd85-446f-9db8-de4b9f04aab3>

### PHP

- laravel-52684 (B): <https://claude.ai/code/artifact/35b1b0ea-52b2-4a4a-86c2-5ec3b852b94f>
- php-cs-fixer-8064 (T): <https://claude.ai/code/artifact/bab2ae4d-8b58-4cee-a288-4f8db2b20ad4>
- carbon-2752 (S): <https://claude.ai/code/artifact/ea6532f8-2d1e-4e74-bb4b-cce0d0d52f02>
- phpspreadsheet-3463 (M): <https://claude.ai/code/artifact/44f71782-00e9-4d2e-bacf-1e70294ac706>

### Ruby

- fpm-1829 (B): <https://claude.ai/code/artifact/9474fff4-d93a-48d9-8f55-0b53d9e3ea08>
- fastlane-20958 (T): <https://claude.ai/code/artifact/993654c3-4a04-4273-9ec8-34a87b286a1f>
- rubocop-13396 (S): <https://claude.ai/code/artifact/87929382-ac2c-4481-a2a4-70e208182063>
- rubocop-13560 (M): <https://claude.ai/code/artifact/db093563-614e-4d78-8046-468821c7364b>

### JavaScript

- babel-15649 (T): <https://claude.ai/code/artifact/0e09624e-ec68-4c98-9e6e-ee32ebd42f6e>
- axios-6539 (T, top-up): <https://claude.ai/code/artifact/266cc08f-ce5e-4193-a769-bc3a261caf19>
- three.js-26589 (T, top-up): <https://claude.ai/code/artifact/69f2da96-9860-4830-8dc1-de596cd20607>
- preact-3763 (M): <https://claude.ai/code/artifact/ed0e5ddd-1fdf-4d43-abb0-6db46c73c134>

### TypeScript

- docusaurus-9897 (T): <https://claude.ai/code/artifact/c2f41a8e-650c-4832-8d9f-d5c03e1ac882>
- immutable-js-2006 (T, top-up): <https://claude.ai/code/artifact/790f90fb-97ed-400c-9000-33e74035ccf4>
- docusaurus-10130 (T, top-up): <https://claude.ai/code/artifact/3c47000c-3b79-4886-bf94-9f2a81186aa9>
- vuejs-core-11589 (S): <https://claude.ai/code/artifact/5e19e4bb-b819-4c9c-a837-d5daeb10b181>

# Resolution status of the 36 picks — official SWE-bench evaluation (2026-08-26)

The question "how many of the 36 actually solved their issue" had never been measured — the
census ledger records only that an episode *submitted*. I ran the official evaluation: each
pick's banked prediction (the `.pred` the live census episode wrote on ws02) evaluated by the
SWE-bench harness (`swebench` 5.0.2, dockerized, dataset `swe-bench/SWE-Bench_Multilingual` —
the same id the live episodes ran against) in the task's own image, judged on the official
FAIL_TO_PASS + PASS_TO_PASS suites. 33 of the 36 had a prediction; all 33 evaluated cleanly
(zero infrastructure failures), and I spot-checked per-instance test logs against the summary
before trusting it.

**Result: 32 of 36 resolved (89 %).**

| | C | C++ | Rust | Go | Java | PHP | Ruby | JS | TS |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| resolved | 3/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 | 3/4 | 3/4 | 3/4 |

The four misses, with two distinct failure modes:

- **valkey-1499 (C×M), rubocop-13396 (Ruby×S), vuejs-core-11589 (TS×S)** — the live episodes
  **never submitted a patch** (empty submission in the trajectory), so they were unresolved
  before any test ran. Notably all three are S/M-cell picks — consistent with those cells
  being where the corpus's odd episodes live (rubocop-13396 is also the low-classified row
  flagged in the selection notes).
- **axios-6539 (JS×T top-up)** — submitted a patch that fails its FAIL_TO_PASS tests: the one
  genuine tried-and-failed case.

Two framing notes before this number goes on a slide. First, 89 % is the resolve rate **of
the selection**, which excluded loop-degenerate and replay-invalid episodes by construction —
it must not be quoted as GLM-5.2's corpus-wide SWE-bench-Multilingual rate. Second, the
useful reading for the profiling story is that the P7 replays are re-executing predominantly
*successful* agent work: 32 of the 36 trajectories whose CPU we characterize end in a patch
that actually fixes the issue, and the three that contribute no patch are exactly the small
S/M-cell fences.

Evidence banked at `agentic/swe_agent/evals/iso36res/` (harness report JSON, the 33
predictions, per-instance eval logs), next to the earlier GLM-era eval proofs.

# Full-census resolution + resolution-clean revision of the 36 (2026-08-27)

Following the 36-pick evaluation, I ran the official harness over the **whole census** — one
banked prediction per instance (the same live episode the classification used; for the 15
pre-census tasks, their banked campaign episode) — 236 predictions evaluated, plus 64
episodes that never submitted a patch. Every instance lands in exactly one bucket:

| | count | share |
| --- | --- | --- |
| **resolved** (patch passes FAIL_TO_PASS + PASS_TO_PASS) | **211** | 70.3 % |
| unresolved — patch fails the tests | 25 | 8.3 % |
| unresolved — no patch ever submitted | 64 | 21.3 % |

Per language (resolved / fails / no-patch): C 22/1/7 · C++ 10/1/1 · Go 22/6/14 ·
Java 28/3/12 · JavaScript 26/4/1 · PHP 26/2/15 · Ruby 33/4/7 · Rust 35/4/4 ·
TypeScript 9/0/3. Two observations worth a slide caption: the dominant failure mode is
**not submitting** (64) rather than submitting wrong (25) — and the no-patch column is
where the loop-degenerate episodes live, so "resolution rate" and "episode viability" are
largely the same phenomenon. Go and PHP carry the largest no-patch counts (14, 15).

**The 36-set revision.** Per instruction, the four picks whose episodes are not officially
resolved were replaced, keeping the other 32 (and their banked P7 profiles) fixed and
re-applying the original within-cell ranking over resolved candidates only:

| slot | out (reason) | in | note |
| --- | --- | --- | --- |
| C×M | valkey-1499 (no patch) | **redis-10068** | closest resolved to cell median; runner-up redis-10764 |
| Ruby×S | rubocop-13396 (no patch) | **fluentd-3328** (T top-up) | Ruby×S has NO resolvable candidate (only other member is E7-excluded) → slot converted to Ruby's majority category T per the selection's own rule; fresh repo, at the 29-candidate median |
| TS×S | vuejs-core-11589 (no patch) | **core-11870** | same repo (TS×S is vuejs-only); at cell median |
| JS×T top-up | axios-6539 (fails F2P) | **axios-5892** | fresh-repo rule keeps axios; runner-up axios-4731 |

Files updated: `selection_36_count.tsv` (rows + summary: 36 picks, now 26 cells, 31 repos,
Σ fence 4,728 core-s) and the ML_iso36 README layout table. Consequences to schedule: the
**four replacements need P7 replay profiling**; the four dropped tasks' banked profiles stay
valid data but leave the 36-set figures, and the Ruby×S cell is now honestly reported as
"no resolvable profilable candidate". Caveat as before: 211/300 is GLM-5.2 under *this*
harness/config at temp 0.6, one episode per task — not a leaderboard number (single seed,
loop guard active, 40-min drain cap). Evidence: `agentic/swe_agent/evals/res300/`
(per-instance reports + predictions + verdict summary).

## The revised realized matrix (resolution-clean, 2026-08-27)

Replacements in **bold**; every pick is officially resolved. Column sums B 11 / T 13 / S 4 /
M 8 = 36; 26 cells, 31 repos, Σ tool-fence 4,728 core-s (16 → 655 per task).

| language | B | T | S | M | top-ups |
| --- | --- | --- | --- | --- | --- |
| C | redis-12272 | micropython-13039 | jq-2598 | **redis-10068** | — |
| C++ | nlohmann-4237 | *empty* | *empty* | *empty* | + fmt-3750, fmt-3901, fmt-2457 (B) |
| Rust | nushell-13831 | ripgrep-2209 | *empty* | bat-2835 | + axum-1730 (B) |
| Go | caddy-4774 | gin-2121 | *empty* | prometheus-10720 | + hugo-12579 (M) |
| Java | gson-1093 | gson-2134 | lombok-3479 | javaparser-4538 | — |
| PHP | laravel-52684 | php-cs-fixer-8064 | carbon-2752 | phpspreadsheet-3463 | — |
| Ruby | fpm-1829 | fastlane-20958 | *(no resolvable candidate)* | rubocop-13560 | + **fluentd-3328** (T) |
| JavaScript | *empty* | babel-15649 | *(n=1, unprofilable)* | preact-3763 | + **axios-5892**, three.js-26589 (T) |
| TypeScript | *empty* | docusaurus-9897 | **vuejs-core-11870** | *empty* | + immutable-js-2006, docusaurus-10130 (T) |

The selection-matrix figure was regenerated from the revised TSV
(`local_agents/ML_iso36/plots/iso36_selection_matrix.png`, footer now states the resolution
filter; `plot_iso36_selection.py` and `build_deck.py` were made machine-portable in the
process). **Deck slide 37 still shows the old figure**: the deck can only be rebuilt on the
P7 — 9 of its embedded figures derive from the gitignored `superseded_40min/data` tree that
exists only there — so after pulling this commit, on the P7:
`python3 local_agents/kit/plot/build_deck.py` (figures auto-refresh from the repo) and
republish the artifact to the same URL, then move the share pin.

## Why the 89 are unresolved — cause taxonomy (2026-08-27)

Every unresolved task was diagnosed from its own evidence: the 25 test-failures from their
official eval reports (`agentic/swe_agent/evals/res300/logs/`), the 64 no-patch episodes
from their census ledger rows (exit status, E7 flags, wall clock).

**A. The 25 that submitted a patch that fails (evidence: per-instance `report.json`):**

| cause | n | reading |
| --- | --- | --- |
| bug not fixed — FAIL_TO_PASS still failing, zero regressions | 21 | the patch applies cleanly and breaks nothing; it just doesn't fix the bug as the hidden tests define it (often a partial fix: 3 rows pass *some* F2P tests) |
| patch does not apply to the pristine tree | 3 | axios-4738, axios-5316, php-cs-fixer-7635 — the submitted diff no longer matches upstream files (context drift in the sandbox) |
| regression — F2P passes but P2P breaks | 1 | apache-lucene-12626, the corpus's **only** case of a fix that breaks other tests |

The striking asymmetry: agent patches essentially never regress (1 of 236). Wrong patches
fail by *under-fixing*, not by collateral damage. Note prometheus-9248 — one of the July
banked reference episodes — is among the 21: a profiled, composition-confirmed episode whose
patch nonetheless fails the official tests. Profiling validity and resolution are
independent axes.

**B. The 64 that never submitted (evidence: ledger exit status + E7 flags + wall):**

| cause | n | reading |
| --- | --- | --- |
| loop-degenerate (E7 flags) | 38 | the agent locked into repeated/cyclic actions and the loop guard (or its own spiral) ended the episode before any submit; concentrated in PHP (12) and Go (11) |
| drain-killed at the 40-min episode cap | 17 | still working when the wall hit — Java/lucene-heavy (slow JVM verify loops); includes the re-run apache-lucene-13704. Some of these are likely convertible by a longer cap |
| harness stop with no exit status | 5 | includes valkey-1499 and rubocop-13396 (two of the replaced picks) |
| per-command timeout (exit_command_timeout) | 2 | lombok-3571/-3674 — one tool command exceeded the command timeout and the episode aborted |
| pre-census parked/probe episodes | 2 | carbon-2813 (degenerate, 2026-07) and phpspreadsheet-3940 (the July probe: 217 steps, composition-confirmed, never submitted) |

Cross-corpus reading: **loop degeneracy is the single largest cause of non-resolution
(38/89 = 43 %)**, dwarfing wrong answers (25/89); the drain cap is second (17/89 = 19 %) and
is a *harness budget choice*, not an agent failure — a follow-up worth one experiment is
re-running the 17 drain-kills at a longer cap to see how many convert. Together with the
resolution table this sharpens the earlier caption: GLM-5.2's ceiling on this corpus is set
less by patch quality than by episode viability — staying out of loops and finishing in
budget.


