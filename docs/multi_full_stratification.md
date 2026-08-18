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

* During run time, collect
* Core-second of each process
    * 容器里每个死掉的进程留一张收据,记着它一生精确的 CPU(utime + stime,微秒)。

* Commands in 2 Hz window (Legacy, do not need any more)

    * 收据监听器写下每个进程的 comm/pid/ppid/CPU;2 Hz 日志写下每个存活 pid 的 argv;cpu.stat 写下围栏总量


* After runtime:
读这三个文件 → 打细标签 → 折叠粗类 → 归属链 → 算份额 → 打 B/T/S/M

* 1. 每个进程按名字/命令行打一个细标签
按可执行文件名查表

细标签	例子
compile	cc1, cc1plus, rustc, javac, ld, collect2, as, lto1, Go 的 compile/link
build-drv	make, cmake, ninja, cargo build, go build, configure, m4, libtool
pkg	apt, dpkg, pip, composer, npm install
test-run	phpunit, jest, rspec, cargo test, go test, tclsh, surefire, *.test 二进制
runtime	java, node, php, ruby, python —— 语言运行时,但没看出在跑测试框架
lint	go vet
search	grep, rg, find, cat, sed, awk, head, tail, sort
vcs	git
(脚手架)	sh, bash, sleep, timeout, swerex-remote —— 排除
other	没匹配上的(比如仓库自己的 jq 二进制)—— 不参与份额,但会报出来



build-drv:什么进程,怎么判,为什么
定义:自己几乎不烧 CPU、职责是编排别的程序去构建的命令。判定按可执行文件名 + 少量参数消歧:

进程	判定	为什么算 build-drv 而不是别的
make / gmake / cmake / ninja / meson / scons	名字直接命中	构建系统的驱动器,自己只算依赖图,活都是 cc1/ld 干的
configure / autoconf / automake / m4 / libtool	名字直接命中	autotools 的构建配置阶段;它 spawn 出的几千个 sed/grep 是探测编译器,不是 agent 在搜索——所以要有一个前端把它们兜住
cargo(argv 里不是 cargo test)	名字 + 参数	cargo build / cargo check
go(argv 里不是 go test)	名字 + 参数	go build / go install / go generate
rake	名字命中	Ruby 的 make
归属层的额外规则(修 bug 后加的):一个被判成 build-drv 的前端,如果它在收据里的孩子里有 vet 或 *.test,改判 test-run。因为"生了测试 runner 的 go"就是 go test,不管 argv 有没有被拍到。

其余细标签的判法(同一个函数,自上而下顺序匹配,先命中先算)
细标签	判定规则	为什么单独一类
compile	名字 ∈ {cc1, cc1plus, gcc, g++, clang, rustc, javac, tsc, as, ld, collect2, lto1, lto-wrapper, ar, ranlib…};Go 的 compile/link/asm/cgo(名字或路径含 pkg/tool)	真正烧指令的构建载荷,是叶子;它不拥有别人
pkg	名字 ∈ {apt, apt-get, dpkg, pip, composer, gem, bundler} 或 npm/yarn/pnpm 带 install|ci|add|update	装依赖;bootstrap 修正也靠它识别
test-run	名字 ∈ {phpunit, jest, vitest, mocha, rspec, pytest, ctest, tclsh, surefire, gotestsum…};cargo test / go test(参数);名字形如 *.test / *_test / -<16位hex>(Go/Rust 测试二进制)	前端 + 测试载荷都在这里;能拥有孩子
runtime	名字 ∈ {java, node, php, ruby, python, perl, valkey-server, redis-server},且参数里看不到测试框架	语言运行时在跑东西但不确定是什么——多半是被测程序或 agent 的复现脚本;归 TEST 粗类
lint	go vet / 名字 vet	归 TEST(是验证行为),但单独记以便看见
search	名字 ∈ {grep, rg, find, cat, ls, head, tail, sed, awk, sort, wc, diff…}	agent 的读/找
vcs	git	归 SEARCH 粗类;单列是因为它有时不小
(脚手架)	名字 ∈ {sh, bash, sleep, timeout, env, tee, mkdir, rm, cp…}、swerex-remote、python3.11(sandbox server)	排除,不投票:它们透明,拥有一切等于拥有什么都没说
other	以上都没命中	不投票但报出来——这一桶大就是打标表缺条目的信号(jq、shtest、dd)
三个值得知道的设计点
顺序有意义:python3 -m pytest 先被 test-run 抓住,不会落到 runtime;npm install 先被 pkg 抓住,不会落到 test-run。
粗类折叠:compile + build-drv + pkg → BUILD;test-run + runtime + lint → TEST;search + vcs → SEARCH。细标签保留在 top_procs 列里,想细看随时能看。
谁能当"前端":只有 test-run / build-drv / pkg——它们语义上是"替我把这事办了",所以孩子的 CPU 可以记给它们。compile/search/vcs 是叶子,runtime 是模糊的,脚手架是透明的,都不能拥有别人。
打标表在 typeid_cpu_matrix.py 顶部,就是几个字面上的 Python 集合——审计"为什么 X 算 Y"就是读那几行。


2. 细标签折叠成三个粗类
粗类	包含的细标签
BUILD	compile, build-drv, pkg
TEST	test-run, runtime, lint
SEARCH	search, vcs
other 和脚手架在三类之外:它们拉低 "classified %" 那一列,但不投票。


3. Sum and classification
* Process perspective
    * rustc 记 BUILD,不管谁引发
    * If not in any other category, then will be classified as others

* Ownership perspective
    * cargo test 拥有它的 rustc, then rustc is TEST

    * 二、"归属":沿 ppid 往上找最近的驱动前端
以 jq 为例。agent 打了一条 make check,容器里长出这棵树:


bash                          (脚手架,不算)
 └── make check               ← 驱动前端:build-drv
      ├── cc1   (2.1 core-s)
      ├── cc1   (1.7 core-s)
      ├── ld    (0.4 core-s)
      └── jq    (7.6 core-s)   ← 跑测试用例的 jq 二进制
归属规则:每张收据往上走 ppid,碰到第一个"驱动前端"(test-run / build-drv / pkg 三类之一)就停,记到那个前端的类别上。

收据	往上走	碰到	记到
cc1 (2.1)	→ make	build-drv	BUILD
ld (0.4)	→ make	build-drv	BUILD
jq (7.6)	→ make	build-drv	BUILD
全归 BUILD——因为是 make check 引发的。这和 P7 窗口打标一致:那 2 秒里 make 在跑,窗口就标 pkg/build。

同样的 cc1,换个祖先就换类别:


cargo test                    ← 驱动前端:test-run
 └── rustc (2.8 core-s)      → 往上碰到 cargo test → 记 TEST
"找不到这种祖先,就用进程自己的类别"——agent 直接打 grep -r foo,树是 bash → grep,往上只有脚手架、没有驱动前端 → grep 用自己的类别 search。


4. Limitation
* Decision
    * 0.5 s window VS 100 ms window -> we don't need 2 Hz window anymore
    * Which perspective we need to use: Count what kind of processes are really running (process perspective) or ownership perspective?
        * 顺便提醒进程视角的一个已知短板,选它之前要心里有数:仓库自己的二进制(jq、valkey-server、rubocop 的 ruby 进程)在 comm 里没有通用规则可识别,会落到 other,不投票。jq 那 7.6 core-s 就是这么丢的。归属视角不受影响(它们的祖先是 make check → BUILD)。补法是加一张仓库→自身二进制名的小登记表(41 个仓库,一行一个),把它们标成 test-run(被测程序)。这个我可以在 sweep 跑完前补上——要不要现在做?

        * jq 是那个刚好暴露短板的例子。两个视角给的答案不一样:

进程视角:other,不投票
jq 不在任何一张表里 → 落到 other。它自己的 7.6 core-s(占围栏 27%)排除在份额分母外——不算 BUILD、不算 TEST。所以 jq-2681 按进程视角是 43/16/41 的 M(mixed),而那 27% 根本没参与投票。这不是分类错,是信息丢失:一个明明是"被测程序在跑测试"的进程,被当成了不认识。

归属视角:BUILD,因为它的祖先是 make check
沿 ppid 往上:jq → sh(脚手架,跳过)→ make check(build-drv 前端,停)。所以 jq 的 7.6 core-s 记到 BUILD。这和 P7 的窗口打标一致(那 2 秒 make 在跑 → 标 build),所以归属视角的 jq-2681 是 90/9/1 的 B,和 P7 真值 92/0/8 吻合。

但仔细想,两个都不完全对
jq 在这里是被测程序——make check 在跑测试套件,每个用例调一次 jq。它的 CPU 语义上是 TEST(测试载荷),不是 build。归属视角把它记 BUILD 只是因为这个仓库的测试入口恰好是 make——这正是 B 类的定义("test entry point is a build target"),所以对 P7 可比性来说是"对"的,但对"CPU 上在跑什么"来说是模糊的。

补法:每个仓库登记自己的二进制
41 个仓库,一行一个,把仓库自己的可执行文件标成 test-run(被测程序):


jqlang/jq          → jq
redis / valkey     → redis-server, valkey-server, redis-cli   (已经在 runtime 里了)
sharkdp/bat        → bat
burntsushi/ripgrep → rg      ← 注意:rg 现在被当 search!ripgrep 仓库里的 rg 是被测程序
gohugoio/hugo      → hugo
caddyserver/caddy  → caddy
nushell/nushell    → nu
uutils/coreutils   → coreutils 的每个工具名……
ripgrep 那条是个真陷阱:rg 在 search 表里,但在 ripgrep 自己的仓库里,跑 rg 就是跑测试。这条登记表只在进程视角起作用(归属视角本来就靠祖先);加上之后 jq 会从 other 变成 test-run → TEST。

要不要我现在把这张表加进去?sweep 不用停——标签是事后算的,加完在已经跑完的集上重算就行。

* My questions:
    * What is comm/pid/ppid/CPU; pid's argv and cpu.stat 写下围栏总量




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

Rows with coverage <80% or classified share <50% are flagged `low-evidence`, kept, and never silently dropped. Note the two views can legitimately disagree (tokio: T by ownership, half-compile mixture by process) — a cell's answer states both, never one forced word.

**The final deliverable** — ⟨language × measured CPU-type⟩, ownership view, one count per instance (counts below are *illustrative*; the sweep fills them):

| language | B | T | S | M | low-evidence |
| --- | --- | --- | --- | --- | --- |
| C | 24 | 3 | 0 | 2 | 1 |
| C++ | 10 | 1 | 0 | 0 | 0 |
| Rust | 6 | 18 | 0 | 4 | 1 |
| … | | | | | |

Unlike the behavioural matrix (215/225 in a single column — no stratification power), this matrix has populated, distinguishable columns, because it classifies what the CPU actually ran instead of what the agent typed. Selection then takes one representative per populated ⟨language, type⟩ cell (tie-breakers: median corrected fence, E7-clean, toolchain witness present, second repo per language, magnitude spread; runner-up recorded per cell). Every pick remains a **prior** — the P7 live episode plus its layer-3 gate stays the verdict.



May I understand: for a live campaign, 8 cgroups will be profiled during one 5-s window or only one cgroup is profiled during one 5-s window?

