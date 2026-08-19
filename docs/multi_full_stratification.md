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



镜像冻结了第三方依赖、并且在 base commit 上预构建过一次。但 episode 里没有任何东西是靠镜像验证的。agent 每次想验证自己改得对不对，就打一条命令，仓库自己的工具链就在容器里拉起来烧一次 CPU——一个 episode 里会发生 5 次、10 次、20 次。

Axis 1 管的是这个「每次调用都要重复付」的成本，不是那笔一次性的安装成本。而这些成本在预构建之后原封不动地活着：

类	镜像帮你省掉的（一次性）	每次调用仍然要跑的
J Java	~/.m2 下载	JVM 启动、classpath 解析、surefire fork、JIT 预热
I PHP/Ruby	vendor/ 安装	解释器启动 + 整个被选中的测试套件
A Rust/Go	依赖闭包的编译	补丁弄脏的那部分重新编译、链接、运行
B C/C++	—	make 重新推导依赖图；改了源码就必须真编译
N JS/TS	node_modules 安装	transpiler/bundler 子进程，然后 JS runner


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

Reproduce: `./measure.sh typeid replay <instance>` (one), `./measure.sh typeid replay-sweep` (all; resumable; stop with `touch local_agents/ML_typeid/STOP_REPLAY`), then `python3 local_agents/kit/campaign/typeid_cpu_matrix.py build && … matrix`. Scope: 296 of 300 replayable (285 typeid + 11 older consumed instances with banked trajectories); 4 instances have no trajectory anywhere (prometheus-9248, terraform-35543, carbon-2813, laravel-51890).

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

# Final matrix (sweep complete 2026-08-19)

**Population:** 296 replayed episodes = 285 typeid + 11 older consumed instances with banked trajectories. 4 instances have no trajectory anywhere (prometheus-9248, terraform-35543, carbon-2813, laravel-51890). Zero unresolved failures; 7 trajectories needed the harness-abort turn stripped before replay (axios-5316, fluentd-3640, lombok-3486/3571/3674/3697, bat-1892). Receipts: 17.45 M rows (deduplicated on pid+birth time); coverage median 99.4 %, 7 rows < 80 %; 38 replays hit the 2400 s drain cap (fence = lower bound). Corpus-wide replay/live fence ratio (n=284): median 0.995, IQR 0.93–1.09. A **replay-invalid gate** (ratio outside [0.5, 2]) marks a row "no evidence" when the replay clearly did not reproduce the live episode; it caught two systematic cases — **lucene** (8 of 9 rows at 0.07–0.29×: gradle's start-up network check fails inside the replay container, so the JVM tests never ran and the replay measured only bootstrap) and **5 caddy rows** (0.32–0.44×: `go test ./...` exceeds the drain cap). Without the gate those 13 rows would have shipped as T/B on failed or truncated replays. The 71 no-evidence rows (ownership view) split into 43 **thin fences** (under 10 classified core-seconds — the agent never invoked the toolchain), 26 **replay-invalid** rows (the gate above), and 2 rows where more than half the fence ran under unregistered process names. Files: `local_agents/ML_typeid/cpu_matrix.tsv` (per-episode rows, both views), `selection_30.tsv`. Figures: `docs/figures/typeid_cpu/08a_matrix_process_view.png`, `08b_matrix_ownership_view.png` (the 30 picks are marked ★), `08c_no_evidence_reasons.png`.

**Ownership view** (which agent command paid; P7-comparable — drives the selection):

| language | class | B | T | S | M | no evidence | n |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C | B | 12 | 6 | 0 | 1 | 11 | 30 |
| C++ | B | 12 | 0 | 0 | 0 | 0 | 12 |
| Rust | A | 17 | 20 | 0 | 5 | 1 | 43 |
| Go | A | 14 | 17 | 0 | 3 | 6 | 40 |
| Java | J | 0 | 32 | 0 | 0 | 11 | 43 |
| PHP | I | 1 | 18 | 0 | 0 | 22 | 41 |
| Ruby | I | 0 | 31 | 0 | 0 | 13 | 44 |
| JavaScript | N | 0 | 25 | 0 | 0 | 6 | 31 |
| TypeScript | N | 0 | 11 | 0 | 0 | 1 | 12 |
| **all** | | **56** | **160** | **0** | **9** | **71** | **296** |

**Process view** (what the CPU physically ran):

| language | class | B | T | S | M | no evidence | n |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C | B | 5 | 8 | 0 | 0 | 17 | 30 |
| C++ | B | 12 | 0 | 0 | 0 | 0 | 12 |
| Rust | A | 38 | 1 | 0 | 2 | 2 | 43 |
| Go | A | 32 | 1 | 0 | 1 | 6 | 40 |
| Java | J | 0 | 32 | 0 | 0 | 11 | 43 |
| PHP | I | 1 | 16 | 0 | 0 | 24 | 41 |
| Ruby | I | 0 | 31 | 0 | 0 | 13 | 44 |
| JavaScript | N | 0 | 25 | 0 | 0 | 6 | 31 |
| TypeScript | N | 0 | 11 | 0 | 0 | 1 | 12 |
| **all** | | **88** | **125** | **0** | **3** | **80** | **296** |

**What the matrix says**

1. **It stratifies.** 16 populated ⟨language, type⟩ cells by ownership (15 by process) versus one column for the behavioural matrix (215/225 search-led). B, T and M are all real, populated types.
2. **The S column is empty in both views** (0/225 labelled rows). Search never dominates CPU — search actions are many but cheap. This is the measured version of "action mix ≠ CPU mix".
3. **Class A (Rust, Go) splits within the language, and the two views disagree about it — both correctly.** By ownership Rust is 17 B / 20 T / 5 M and Go 14 / 17 / 3: whether an episode is build- or test-dominated depends on how much of the closure the agent's edits dirtied, not on the repo. By process both are ~90 % B: the compiler is what actually burns, whatever command owns it. So the earlier "class A refuted by tokio and gin" verdict was an ontology artifact — A's own definition ("a mixture; compile ≥ 20 % and runner ≥ 20 %; refuse to predict the winner") is exactly what the ownership row shows.
4. **Class B is not uniformly build-dominated.** C splits 12 B / 6 T / 1 M by ownership and 5 B / 8 T by process: most jq/redis/valkey episodes spend the fence running the repo's own test binary, and only the large-patch episodes (jq-2681, the P7 reference with the corpus's largest gold patch; redis-11631) are heavily build. C++ is 12/12 B — but 11 of 12 are fmt, a header-only template library, so this is an fmt statement (W-CONFOUND), not a C++ one.
5. **Classes J, I, N behave exactly as their prior predicts:** T-dominated with essentially no exception, identical in both views (no compilation to re-attribute). The prior is simply correct there, and stays boring — as a good prior should.
6. **PHP has the largest no-evidence column (22 of 41)** and Java's 11 are mostly the lucene replay failure. These are small fences (median ~10 core-s) whose CPU is mostly the language runtime and git; the P7 stop gate (20 core-s) would reject them anyway. It is a magnitude finding about PHP tasks in this corpus, not a classification failure.

**Selection (30 of 296)** — `selection_30.tsv`, produced by `local_agents/kit/campaign/typeid_select.py` (ownership view; one pick per populated cell, then a second repo per language, then magnitude spread; within a cell prefer E7-clean, coverage ≥ 80 %, closest to the cell median, unpicked repo, non-W-CONFOUND; runner-up recorded). 16 cells → 16 picks; +5 second-repo picks; +9 magnitude picks (largest fence per language, smallest measurable for C). 28 distinct repos, all 9 languages, only one already P7-profiled (gson-2061, kept deliberately as the calibration anchor). Caveats carried per row: three picks need a look before spending P7 minutes — hugo-12204 was drain-capped (its cell has a clean runner-up, hugo-12562), and axios-6539 (19.1 core-s) and micropython-13039 (16.9 core-s) sit below the 20 core-s P7 stop gate and were kept only as magnitude-spread anchors. Eight picks carry `call-step-mismatch` in the live ledger; that flag is bookkeeping (proxy calls vs logged steps), not a viability flag. Every pick is a **prior** — the P7 live episode plus its layer-3 gate stays the verdict.



May I understand: for a live campaign, 8 cgroups will be profiled during one 5-s window or only one cgroup is profiled during one 5-s window?

