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









# Axis 2

## 1. Axis 2 classifies *actions*, not CPU



## 2. How actions are classified: four `act_class` values plus a catch-all

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




May I understand: for a live campaign, 8 cgroups will be profiled during one 5-s window or only one cgroup is profiled during one 5-s window?

