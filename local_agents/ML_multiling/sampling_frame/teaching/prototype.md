# Teaching prototype — SWE-bench Multilingual ⟨language, type⟩ study

**Date:** 2026-08-03 · **Status:** prototype for approval. Sections A–F only; the full deck is
**not** generated yet and the existing dashboard artifact is **unmodified**.

This directory will eventually hold the full package: deck · per-slide speaker notes · Q&A ledger ·
consolidated study notes · glossary · claim–evidence table · technical appendix · open-decision list.

**Rule inherited from the study and enforced throughout the teaching material:**
> No evidence, no claim. Unknown information must be marked as unknown.
> A static label is a *prior*; only a measured episode is a *verdict*.

---

## A. Audience definition

**Who the learner is.** Someone with a general technical background — they can read code, use a
terminal, and follow a systems argument — who has never seen this project. They are capable of
understanding everything here; they simply have not been told any of it yet. The success test is
not recall: it is whether they can later *defend* the work to a skeptical questioner.

**Assumed knowledge — usable without definition:**

- programming languages, compilers and interpreters, what a test suite is
- Git repositories, commits, pull requests, diffs/patches
- basic shell: running a command, `grep`, pipes, `make`
- that Docker containers isolate a program's environment
- what an LLM is, and that a model can be given tools to call
- ordinary quantitative literacy: percentage, share, median, spread

**Explicitly NOT assumed — must be taught in-deck, or deferred to the appendix and flagged:**

- **The benchmark**: what SWE-bench is; what a "task"/"instance" contains; how success is graded
- **The agent harness**: what SWE-agent is; what an *episode*, an *action*, and a *trajectory* are
- **CPU measurement vocabulary**: core-seconds vs wall-clock; cgroups; hardware counters;
  instructions as a unit; sampling vs exact accounting
- **This project's terms**: fence, window, replay pass, ownership/adequacy gate, composition vs
  magnitude, realized vs prior label, co-dominance
- **Microarchitecture terms** (µop-cache, DSB, MPKI, IPC, TMA): appendix-only for this audience.
  They appear in the study but are *not* required to understand its argument.
- **The project's history**: the mentor's instruction, the earlier draft's error, the probe campaign
- **Why sampling is necessary at all** — the budget argument has to be shown, not assumed

**Deliberate exclusion.** The learner is not being trained as a microarchitecture analyst. Anything
that is a *result about the CPU's internals* rather than *a step in the argument* goes to the
appendix. The deck teaches the experimental logic; the appendix holds the physics.

---

## B. Learning objectives

After the session the learner should be able to explain, unprompted:

1. **The research question** — why anyone measures CPU work *outside* model inference, and why a
   coding agent is the revealing case.
2. **The unit of analysis** — what one SWE-bench Multilingual task contains, what the agent is
   given, and what decides success.
3. **Why sampling was necessary** — the concrete budget that makes running all 300 tasks impossible,
   and what the mentor's one-per-cell rule is designed to prevent.
4. **The ambiguity of "type"** — that it can mean what the *machine* does or what the *agent* does,
   and give a specific example where merging the two produces a false statement.
5. **How each axis is measured** — why the CPU boundary is a cgroup rather than a list of process
   names, and what "composition reproduces, magnitude does not" licenses and forbids.
6. **What was found** — both collapses, with the evidence for each, including that the second one
   was *tested by trying to falsify it* rather than assumed.
7. **Why action counts and CPU composition disagree** — using jq as the worked example, and what is
   actually being compiled.
8. **The honest boundary** — what cannot be concluded, what remains unknown, and how the mentor's
   original request should now be answered.

---

## C. Narrative arc

Each beat exists because the previous beat raised a question it cannot answer.

1. **When an AI fixes a bug, where does the CPU time go?** Attention goes to the model and the GPU.
   But the agent also *acts* — it greps, edits, compiles, and runs test suites, all on the CPU. How
   much, and doing what? → *To answer that, you must measure real tasks. Which tasks?*
2. **A benchmark supplies real tasks.** 300 real GitHub issues across nine languages, each with a
   pre-built environment and hidden grading tests. → *We cannot run all of them.*
3. **The budget forces sampling.** One task costs a paid model episode plus about 1.5 hours of
   exclusive machine time; 300 would be roughly 450 hours, serialized. → *So choose deliberately.*
4. **The mentor's rule: one task per ⟨language, type⟩.** Coverage without redundancy — no two
   build-heavy C++ tasks. → *But this requires knowing a task's "type" before running it.*
5. **"Type" turns out to be two different things.** What the machine does when the tests run, versus
   what the agent spends its actions on. → *Define both, separately, and measure both.*
6. **Axis 1 is a property of the repository.** The test command's process tree decides the physics.
   → *Can it be predicted before running? Yes — and the answer is surprising.*
7. **Axis 2 is a property of an episode.** What the agent does may vary run to run. → *Can it be
   predicted? That is an empirical question, so test it rather than assume.*
8. **First you need an instrument.** A fence is a cgroup; it counts every descendant process. Replay
   makes measurement repeatable and free. → *Now evidence can be read.*
9. **Result 1 — the grid collapses.** Mechanism is a function of the language: nine reachable cells,
   not forty-five, and all nine are already measured.
10. **Result 2 — the second axis collapses too.** Sixteen of sixteen episodes are search-led,
    including three probes deliberately chosen to fail. → *But wait: if the agent mostly searches,
    why is the CPU mostly compiling?*
11. **The jq case resolves it.** One `make` action spawns a whole process tree; sixty greps cost
    microseconds. Actions measure the agent; core-seconds measure the machine.
12. **So what may we say, and what may we not?** Separate measurement from interpretation from
    limitation from unknown — then answer the mentor, and name the decisions still open.

The pedagogical hook is the tension created at beat 10 and released at beat 11. A learner who feels
that contradiction and then resolves it will retain the two-axis distinction permanently.

---

## D. Proposed slide outline

Sixteen main slides plus an appendix. Format per entry: **title · purpose · visual · → notes ·
→ appendix**.

**1. Where does the CPU time go when an AI writes code?**
*Purpose:* establish the research question and that its answer is not obvious.
*Visual:* one episode's time as a single horizontal band split into "waiting for the model" and
"running tools on the CPU", the second half marked as the subject of study.
*→ notes:* the thesis's three parts; core-seconds as a unit; that this is a capacity question.
*→ appendix:* the full instrument stack; the service/serving half of the thesis.

**2. What is one SWE-bench Multilingual task?**
*Purpose:* make the unit of analysis concrete before anything is measured on it.
*Visual:* an anatomy card for a real instance (`jqlang__jq-2681`): repo + commit · issue text ·
hidden reference fix · hidden grading tests · pre-built container. Marked: the agent sees only the
first two rows.
*→ notes:* how the benchmark was built and validated; the reference resolution rate.
*→ appendix:* full field list, snapshot revision, licence, per-language provenance.

**3. What the agent does with a task: search, edit, test, repeat**
*Purpose:* show the loop that generates everything measured later.
*Visual:* the loop on the left; on the right, real numbered steps from jq's 105-action trajectory.
*→ notes:* what a harness is; what a trajectory is; why temperature is 0.6 and not 0.
*→ appendix:* harness configuration, tool bundles, the command blocklist.

**4. 300 tasks, nine languages — and we can afford a handful**
*Purpose:* make the sampling problem quantitative rather than rhetorical.
*Visual:* per-language bar chart, beside the cost arithmetic (1 task ≈ 1 paid episode + ~1.5 h
exclusive machine time → 300 ≈ ~450 h serialized).
*→ notes:* why captures cannot be parallelised; why the machine must be isolated.
*→ appendix:* exact counts, the JS/TS split rationale, the unresolved 41-vs-42 repo count.

**5. The mentor's rule: one task per ⟨language, type⟩**
*Purpose:* introduce the sampling design and the precondition it hides.
*Visual:* a language × type grid, one dot per cell, with a second C++ build-heavy dot crossed out.
*→ notes:* the verbatim instruction; this is stratified sampling; what redundancy costs here.
*→ appendix:* —

**6. But what is a "type"?**
*Purpose:* expose the ambiguity — the pivot of the entire deck.
*Visual:* one task at the top, two labelling paths diverging below it: *what the machine did* and
*what the agent did*, each ending in a different label for the same task.
*→ notes:* the draft error this ambiguity caused.
*→ appendix:* —

**7. Axis 1 — what the machine does when the tests run**
*Purpose:* define intrinsic CPU mechanism via process trees, before naming any class.
*Visual:* three process trees side by side: `make check` → make → gcc → cc1 → as; `cargo test` →
rustc → test binary; `phpunit` → (no compiler anywhere).
*→ notes:* the five class names, introduced only after the trees; why this is a repo property.
*→ appendix:* the formal class predicates and the out-of-corpus Python placeholder.

**8. Axis 2 — what the agent does during one episode**
*Purpose:* define observed behaviour and its four action categories.
*Visual:* a trajectory strip — 105 actions coloured search / edit / test / build — with the
"leads by at least 10 points, else *mixed*" rule shown on two example strips.
*→ notes:* why `view` counts as reading; why this is a property of an episode, not a task.
*→ appendix:* the classifier's ordered rules, the margin constant, the co-dominance rule.

**9. Why the two axes must stay separate**
*Purpose:* the central teaching point of the deck.
*Visual:* the wrong label — "Rust compiles, therefore build-dominated" — struck through beside the
measured composition; below it, the three-fact reporting template.
*→ notes:* the correction's history; that the corrected number is itself contaminated.
*→ appendix:* the tagger defect that contaminates it.

**10. How do you measure "CPU spent by the agent's tools"?**
*Purpose:* introduce the fence as a boundary that counts descendants.
*Visual:* nested boxes — harness fence, tool fence (the container), proxy — with a process tree
crossing into the tool fence and every node inside it shaded.
*→ notes:* why process names fail as a boundary; what a core-second is.
*→ appendix:* the four simultaneous instruments; the acceptance gates.

**11. Measuring the same episode twice: what reproduces and what doesn't**
*Purpose:* teach composition-vs-magnitude, which licenses or forbids every later claim.
*Visual:* two panels — replay passes clustered within ~1 %, versus four live episodes of one task at
37.9 / 54.9 / 199.0 / 202.1 core-seconds.
*→ notes:* why replay is free; why magnitude cannot rank candidate tasks.
*→ appendix:* per-task live-vs-replay figures.

**12. Result 1 — the language decides the mechanism**
*Purpose:* the first collapse, and what it does to the mentor's grid.
*Visual:* the 9 × 5 matrix: 36 cells greyed as structurally empty, 9 filled and ticked.
*→ notes:* verified as a total function over all 300 rows; the consequence for sampling.
*→ appendix:* per-class counts; the 5-of-9 predicate validation and its interesting failures.

**13. Result 2 — the agent searches, whatever the task**
*Purpose:* the second collapse, and that it was tested rather than assumed.
*Visual:* 16 stacked action-mix bars sorted by test share, the three probes flagged with the label
each was predicted to realize.
*→ notes:* falsification logic; why the Go probe is decisive; the blocklist bound on the build column.
*→ appendix:* the full mix table; the static prior's 1-of-10 scoreboard.

**14. Then why is the CPU compiling? The jq case**
*Purpose:* resolve the contradiction slide 13 creates — the payoff slide.
*Visual:* two bars for the *same* episode — actions (search 72 %, build 18 %) above, CPU
(compile 61 %, package-build 31 %) below — with one `make` action expanding into a process tree
between them.
*→ notes:* what is compiled (the repo, incrementally); the pre-built image; the `cd && make` bypass.
*→ appendix:* argv sample counts; the 12 build steps and 7 edits.

**15. What we can and cannot conclude**
*Purpose:* make the epistemic categories explicit and separable.
*Visual:* a four-column ledger — measured · interpretation · limitation · unknown — with the study's
headline items sorted into it.
*→ notes:* how to answer a skeptical mentor without overclaiming.
*→ appendix:* the full claim–evidence table.

**16. So how do we answer the mentor?**
*Purpose:* close the loop and hand over the open decisions.
*Visual:* the original grid, now annotated — nine cells covered, with the *real* remaining gaps named
(a second repository per language; the two refuted class arms) and three open decisions with costs.
*→ notes:* the argument for and against spending the suspended sweep.
*→ appendix:* the ranked run list and cut lines.

**Appendix (not taught linearly):** A1 the four instruments · A2 acceptance gates and validators ·
A3 the formal class predicates · A4 the action classifier's rules · A5 known instrument defects ·
A6 the microarchitectural results (µop-cache, branch, memory; the within-language pair) ·
A7 benchmark provenance and the Multi-SWE-bench comparison · A8 reproduction commands ·
A9 glossary · A10 claim–evidence table.

---

## E. Five-slide prototype

### Slide 1

**Title:** Where does the CPU time go when an AI writes code?

**Visible slide content**
- One line under the title: *An AI coding agent spends its time in two very different places.*
- A single wide band, split: **waiting for the model** · **running tools on the CPU**
- Under the second segment: *grep · file edits · compilers · test suites*
- One accented question over the second segment: **How much CPU, and doing what?**
- Small footer tag: *This study measures the second half.*

**Visual layout.** The band is the whole slide's centre of gravity — roughly 60 % of the width is
the model-wait segment in neutral grey, 40 % is the tool segment in green (the project's locked
colour for the tool fence). No axis, no numbers: proportions here are illustrative and the slide
says so. A thin callout bracket rises from the green segment to the question. Title top-left,
footer tag bottom-left. Nothing else on the slide.

**Speaker notes**

*Learning objective.* The learner should leave able to state, in one sentence, that an AI coding
agent's time divides into model-waiting and tool-running, and that this project measures the second
part in CPU terms.

*Connection.* This is the opening, so the connection is to the learner's existing mental model —
almost everyone arrives believing "AI coding = GPU work." The slide's job is to put a crack in that.

*Beginner-friendly explanation.* When we talk about what AI costs, we usually mean the model: the
GPU, the tokens, the API bill. But an agent that fixes bugs doesn't only think — it acts. It looks
through files, changes them, and then runs the project's own test suite to check whether the change
worked. Those actions are ordinary programs running on an ordinary CPU. If you're the person who
has to buy and provision the machines, that CPU work is real, and it is largely unaccounted for.

*Concrete example or analogy.* Think about hiring a specialist contractor to fix a building fault.
You budget for their expertise — the diagnosis, the decision. But the actual repair also runs
machinery: drills, mixers, lifts. If your budget only covers consulting hours, the site's power bill
will surprise you. This study meters the power at the site rather than the consultant's invoice.

*Formal technical explanation.* The thesis characterises CPU work **during** inference — the serving
engine that generates the model's tokens — against CPU work **outside** inference: retrieval,
caching, and agent tool execution. Both are reported in wall-clock time and in **core-seconds**,
which is simply "one CPU core kept busy for one second." A quantity in core-seconds is an amount of
work; the same quantity divided by elapsed time gives an occupancy rate we call "CPU usage in cores."

*Common misconception.* That the CPU side is trivial plumbing — a bit of file I/O around the real
work. It isn't. In one measured episode the agent's tool work alone came to roughly 383
core-seconds, and in several tasks the dominant consumer is a compiler. Saying so now, before any
evidence, is a promise the deck will keep by slide 14 — flag it as a promise, not yet a claim.

*Evidence.* No measurement is presented on this slide; it states the question. The 383 core-second
figure quoted verbally comes from the Go episode's tool fence in the nine-language campaign
(study report 16). If a learner challenges it here, the honest answer is "that's a preview; the
instrument that produced it is slide 10."

*Limitation.* This slide does **not** claim the CPU side is larger, costlier, or more important than
the GPU side. It claims only that it exists, is measurable, and has not been well characterised. The
band's proportions are illustrative, not measured — say that out loud.

*Transition.* If we want to know how much CPU and doing what, we cannot reason about it abstractly;
we have to run real repair jobs and watch. So the next question is: what does one of those jobs
actually consist of?

**Likely learner question.** "Isn't the GPU the expensive part? Why does the CPU matter?"

**Ideal professor response.** Plainly: per second, yes — the GPU is the expensive hardware. But the
agent spends a great deal of its wall-clock time *not* waiting for the model at all. Compiling a
project and running its test suite can take minutes per attempt, and an agent does that many times
in one task. Those minutes occupy CPU cores that somebody has to provision. Formally, this is a
capacity-attribution question: if you are sizing a fleet that serves agents, core-seconds spent
outside inference are a real line item, and today it is mostly invisible. The evidence for
"non-trivial" is that measured tool fences in this study range from tens to hundreds of core-seconds
per episode. The uncertainty worth stating: this study does not claim CPU cost exceeds GPU cost, and
it does not price either — it characterises what the CPU is doing. Now, in your own words: why might
CPU time matter even if the GPU dominates the dollar cost?

**Comprehension question for the learner.** In one sentence: what are the two places an AI coding
agent spends time, and which one is this study about?

---

### Slide 2

**Title:** What is one SWE-bench Multilingual task?

**Visible slide content**
A task card for one real instance, `jqlang__jq-2681`, in four rows:
- **The repository, frozen** — jqlang/jq at one specific commit, in a pre-built container
- **The issue** — a real GitHub bug report, in prose
- **The reference fix** — exists in the dataset, **withheld from the agent**
- **The grade** — hidden tests: some must go from failing to passing; others must not break
Marker beside rows 1–2: *the agent sees only this.*

**Visual layout.** A single card occupying the centre-left two-thirds, four stacked rows separated by
hairlines, each row a label on the left and its content on the right. The two withheld rows are
visually recessed — dimmed fill and a small lock glyph — so the "what the agent can see" boundary
reads instantly. Right third holds a short vertical caption: *300 such tasks · 9 languages ·
41 repositories.* No chart on this slide.

**Speaker notes**

*Learning objective.* The learner should be able to describe what one task contains, what the agent
is and is not given, and that success is decided mechanically by tests rather than by judgement.

*Connection.* Slide 1 said we must watch real repair jobs. This slide defines exactly one such job,
so that everything measured later has a clear unit.

*Beginner-friendly explanation.* Someone went to a real open-source project, found a real bug report,
and also found the pull request that fixed it. They froze the repository at the moment just before
the fix, packaged it so it builds and runs, and kept two things back: the actual fix, and the tests
that the fix made pass. The agent gets the frozen repository and the bug report. It has to produce
its own fix. Afterwards, the hidden tests are run: the ones that were failing must now pass, and the
ones that were already passing must still pass.

*Concrete example or analogy.* It is an exam question with a sealed answer key and an automatic
grader. The student sees the question and the textbook; the grader runs a fixed script. Nobody
argues about whether the answer was elegant — it either passes the tests or it doesn't.

*Formal technical explanation.* Each instance carries: `repo`, `base_commit`, `problem_statement`,
`patch` (the reference or "gold" fix), `test_patch`, and two test lists named FAIL_TO_PASS and
PASS_TO_PASS. Evaluation applies the test patch and runs both lists. The benchmark was built by the
SWE-bench team using their published methodology — issues drawn from top-starred repositories where
the fixing pull request contains at least one test file, then an eight-step execution validation per
instance.

*Common misconception.* Two, usually. First, that the agent writes code from scratch — it does not;
it modifies a large existing codebase it has never seen. Second, that a human or a model judges the
result — no: grading is running tests, which is why the benchmark can be run unattended.

*Evidence.* The dataset snapshot used throughout this study is the Hugging Face dataset
`swe-bench/SWE-Bench_Multilingual`, split `test`, at revision `e5c585e…`, containing 300 rows and 41
distinct repositories — recomputed locally, not quoted. The field list above is that snapshot's
actual schema. Difficulty reference from the benchmark's own page: SWE-agent with Claude 3.7 Sonnet
resolves 43 % of these tasks, against 63 % on the English-Python SWE-bench Verified.

*Limitation.* These tasks are *selected*, not a random sample of real-world bugs: the fixing pull
request had to contain tests, and under-specified issues were filtered out. So results generalise to
"well-specified, test-covered bugs in popular repositories," not to software maintenance in general.
One further item stays marked **unknown**: whether the models involved have previously seen these
repositories is a known general concern with this benchmark family and was not measured here.

*Transition.* We now know what the agent is handed. The natural next question is what it *does* with
it — because whatever it does is what will consume the CPU we came to measure.

**Likely learner question.** "If the correct fix is in the dataset, doesn't the agent just know it?"

**Ideal professor response.** Plainly: the reference fix is in the dataset for grading purposes, but
it is never shown to the agent — the agent receives the repository and the issue text and nothing
else. Formally, the gold patch is used only to construct and validate the instance; at run time the
harness supplies the problem statement and a working copy. The evidence is the frozen run
configuration for these episodes, which records exactly which fields are passed to the model. Where
honest uncertainty remains: a model may have encountered the upstream project — including its later
history — during pretraining. That is a real concern for any benchmark built from public
repositories, it is unmeasured in this study, and it belongs in the "unknown" column rather than
being argued away. Now put it back to me: what exactly is withheld from the agent, and why is it
withheld?

**Comprehension question for the learner.** What decides whether a task attempt succeeded — and who
or what makes that decision?

---

### Slide 3

**Title:** What the agent does with a task: search, edit, test, repeat

**Visible slide content**
- Left: the loop — **read the issue → find the relevant code → change it → run the tests → read the
  failures →** (back to *find*) **→ submit**
- Right, headed *one real episode — jq, 105 steps*: five real actions with their step numbers
  - step 5 · `./jq -n '. as $label | $label'` — reproduce the bug
  - step 17 · edit `src/parser.y`
  - step 21 · `make` — rebuild
  - step 31 · `make check` — run the suite
  - step 53 · `make` — rebuild again
- One line beneath: *7 edits · 12 rebuild-or-test commands · 105 actions total.*

**Visual layout.** Two columns. The left is a vertical cycle with a return arrow from "read the
failures" back to "find the relevant code" — deliberately drawn as a loop, because the repetition is
the point. The right is a numbered vertical strip of monospaced real commands, each tagged with the
loop stage it belongs to using the same colour as the left diagram, so the eye maps one onto the
other without a legend. The summary line sits under the strip.

**Speaker notes**

*Learning objective.* The learner should be able to describe the agent's working loop and recognise
that a single episode contains many repetitions of edit-and-verify — which is what makes the CPU
question interesting.

*Connection.* Slide 2 handed the agent a task. This slide is what happens next, and it is the source
of every number in the rest of the deck.

*Beginner-friendly explanation.* The agent works roughly the way a developer does when dropped into
an unfamiliar codebase with no debugger. It reads the bug report, then hunts around with searches and
file views until it finds the code it believes is responsible. It makes an edit. Then it rebuilds and
runs the tests, reads what failed, and goes back to hunting. That cycle repeats — in the jq episode,
seven separate edits and twelve rebuild-or-test commands, inside 105 total actions.

*Concrete example or analogy.* It is print-statement debugging in someone else's house. Most of the
time is spent finding the light switch, not doing the wiring.

*Formal technical explanation.* The harness is **SWE-agent**: it presents tools to the model and
executes the model's chosen tool calls inside a container. Each tool call is an **action**; the full
ordered log of actions and model messages is the **trajectory**; one complete attempt at one instance
is an **episode**. The model here is GLM-5.2 at temperature 0.6 — deliberately not 0, because greedy
decoding makes these agents degenerate: they truncate their narration and stop before the tool call,
or lock into repeating an identical action.

*Common misconception.* That the agent "reads the whole repository" and then reasons about it.
It does not: context is limited, so it navigates by searching and viewing fragments. That is worth
planting now, because it is the mechanism behind a finding on slide 13.

*Evidence.* The five steps quoted are real entries from the banked jq trajectory
(`jqlang__jq-2681`), together with its totals — 105 actions, 7 edits, 12 commands invoking `make`.
These were read directly from the trajectory file, not reconstructed.

*Limitation.* This is one harness, one model, one temperature. Nothing here shows that other agents
behave this way, and slide 13's finding will have to carry that caveat explicitly.

*Transition.* We can now watch one job end to end. The next question is which jobs to watch — because
there are 300 of them and we cannot afford them all.

**Likely learner question.** "Why does it rebuild so many times? Couldn't it make all its edits first
and build once?"

**Ideal professor response.** Plainly: it rebuilds because it cannot tell whether an edit worked
without running the tests, and it usually doesn't get the fix right the first time — so the loop is
edit, verify, learn, edit again. Building once at the end would mean writing the whole fix blind.
Formally, this is the standard edit–compile–test cycle, and its repetition count is a property of the
episode: jq's trajectory shows twelve build-or-test invocations interleaved with seven edits, not
batched. The evidence is the step ordering in the trajectory itself — the rebuild steps are
interleaved with, not appended after, the edits. The limitation worth naming: how many cycles an
agent runs is not fixed; it varies by episode, and slide 11 will show that this variability is large
enough to matter. Now, in your words: why can't the agent batch its edits?

**Comprehension question for the learner.** In the jq episode, which happened more often — edits, or
commands that rebuild and test? What does that ratio suggest about where the time goes?

---

### Slide 4

**Title:** 300 tasks, nine languages — and we can afford a handful

**Visible slide content**
- Left: horizontal bar chart, tasks per language —
  Ruby 44 · Java 43 · Rust 43 · PHP 43 · Go 42 · JavaScript 31 · C 30 · TypeScript 12 · C++ 12
- Right, headed *what one task costs*:
  - one paid model episode
  - **≈ 1.5 hours** of exclusive machine time (profiling, replays, teardown)
  - captures cannot overlap — **one at a time**
  - therefore 300 tasks ≈ **450 hours**, serialized
- Bottom, accented: *So the question is not "run them all." It is "which ones?"*

**Visual layout.** Bars on the left occupying half the width, single-hue, value labels at the bar
tips, languages ordered by count descending. The right half is a short vertical list of cost facts,
each on its own line with generous spacing, building arithmetically to the 450-hour figure, which is
the only emphasised number on the slide. The closing line runs full width beneath both.

**Speaker notes**

*Learning objective.* The learner should understand that sampling is forced by a real, quantified
budget — not chosen for convenience — and should know the shape of the corpus.

*Connection.* Slide 3 showed one episode. This slide multiplies that by the corpus and shows the
result is unaffordable, which is what makes the mentor's instruction necessary rather than merely
tidy.

*Beginner-friendly explanation.* There are 300 tasks spread across nine languages, quite unevenly:
Ruby has 44, C++ has 12. Each task we actually profile costs money, because the model is called
through a paid API, and — more importantly — costs about an hour and a half on a machine that has
been specially prepared and cannot be doing anything else at the time. Do that 300 times, one after
another, and you have spent something like 450 hours. That is not a schedule; it's a season.

*Concrete example or analogy.* It is a wind tunnel, not a spreadsheet. Runs are serial, the facility
is booked, and you cannot recover a wasted slot by adding more people.

*Formal technical explanation.* Profiling requires exclusive use of an isolated CPU partition and of
the machine's hardware performance counters, both of which are single-tenant: two concurrent captures
would contend for the counters and violate the isolation the measurements depend on. Per task the
cost is one live episode plus a gate probe plus roughly ten deterministic replay passes plus setup
and teardown — about 1.5 hours of exclusive-core time.

*Common misconception.* "Just parallelise it." You cannot: the constraint is not CPU throughput but
exclusive access to the measurement apparatus. Adding machines would also add a hardware variable to
every cross-task comparison, which the study's design specifically excludes.

*Evidence.* The per-language counts were recomputed from the dataset snapshot for this session and
are additionally assertion-checked inside the extractor, which aborts if any repository fails to map
to a language. The 1.5-hour per-task figure and the ~450-hour projection are the campaign's own cost
model, recorded in the sampling plan.

*Limitation.* One number on this slide is genuinely unresolved and should be said aloud rather than
hidden: the snapshot contains 41 distinct repositories, while the benchmark's own website says 42.
The cause is unknown. This study's claims use 41. Also note the JavaScript/TypeScript split is *our*
decision — the benchmark publishes them as a single 43-task bucket, and we separate them because
their toolchains differ; that reasoning is on slide 7.

*Transition.* If we can only run a handful, the handful had better be chosen for coverage rather than
convenience. That is exactly what the mentor proposed.

**Likely learner question.** "Why not run cheap short tasks and skip the expensive ones?"

**Ideal professor response.** Plainly: because we would then be measuring only cheap tasks, and the
thing we're trying to characterise is precisely how the expensive work is distributed. Selecting on
cost would bias the answer to the question we're asking. Formally, that is selection on the dependent
variable — choosing cases by the outcome you intend to measure. There is also a practical evidence
point: the study tried predicting task cost from static metadata and found essentially no signal, so
"cheap" isn't reliably knowable in advance anyway. The limitation to state honestly: some tasks *were*
excluded for being too small to measure reliably, and the thresholds used for that were fitted on
very few points — so that exclusion is a budget decision, not a finding. Now restate for me: what
goes wrong if we pick tasks by how cheap they look?

**Comprehension question for the learner.** Roughly how long would profiling all 300 tasks take, and
why can't that number be reduced by running several at once?

---

### Slide 5

**Title:** The mentor's rule: one task per ⟨language, type⟩

**Visible slide content**
- The instruction, quoted short: *"…categorize the tasks based on their tool properties… we will
  sample only one task from each ⟨language, type⟩ group. There's little sense in running two
  build-heavy tasks from C++."*
- A grid sketch: nine language rows × four illustrative type columns (search / edit / test / build),
  one filled dot per cell, and in the C++ row a **second** build dot struck through
- Three short labels around the grid: **cover every combination · never pay twice for the same
  combination · one row per language**
- One line at the bottom, accented: *This only works if we can tell a task's type before we run it.*

**Visual layout.** The grid dominates the centre, drawn large and sparse — dots, not heavy cells, so
it reads as a plan rather than as data. The struck-through duplicate sits in the C++ row and is the
only red element on the slide. The three labels are placed as short annotations with thin leader
lines to the grid feature each describes. The closing line is set apart with space above it, because
it is the hinge into slide 6.

**Speaker notes**

*Learning objective.* The learner should be able to explain the logic of stratified sampling in this
setting, and — more importantly — should notice on their own that the rule has a hidden precondition.

*Connection.* Slide 4 established that we must choose. This slide is the proposed choosing rule,
which arrived from the project's mentor and which the entire study was built to execute.

*Beginner-friendly explanation.* If you can only run a few tasks, don't pick them at random and don't
pick them by convenience. Instead, list the meaningfully different kinds of task, and take one of
each. That way every kind is represented and none is represented twice. The mentor's example is the
clean one: if two C++ tasks would both be dominated by compilation, the second one teaches you
nothing new, and it costs the same hour and a half as a task that would.

*Concrete example or analogy.* Sampling a restaurant's menu. You want one starter, one main, one
dessert — not three variations on the same curry. The goal is coverage of the space, not volume.

*Formal technical explanation.* This is stratified sampling: partition the population into strata
defined by the crossing of two variables — language and type — and draw one unit per stratum. Its
value depends entirely on the strata being *real*: the partition must correspond to genuine
differences in whatever you are measuring, or you are just relabelling arbitrary choices.

*Common misconception.* That the grid is guaranteed to be a full rectangle — nine languages times
four types equals thirty-six informative cells to fill. That is an assumption, not a fact. A grid can
be sparse, or nested, or collapse entirely. Do not let the learner leave this slide believing the
rectangle is real; the deck's next three slides exist to test it.

*Evidence.* The quotation is the mentor's instruction verbatim, which is the specification the study
was built against. Nothing else on this slide is a measurement — it is a proposed design.

*Limitation.* Nothing has been measured yet. This is a plan, and — read carefully — it contains an
untested assumption: it presumes we can determine a task's type *before* spending the episode. If
type could only be known after running, the rule could not be executed at all.

*Transition.* So everything now depends on one word in the mentor's sentence. What, precisely, is a
"type"? That question turns out to have two defensible answers, and the difference between them is
the whole study.

**Likely learner question.** "Couldn't we just run a few tasks per language and average them?"

**Ideal professor response.** Plainly: averaging assumes the tasks within a language are variations on
one thing. If they aren't — if some are dominated by compiling and others by running an interpreter —
the average describes no real task, and it hides exactly the structure we're trying to find. The
mentor's rule is a bet that the differences *between* types matter more than the variation *within*
them. Formally, that's the standard stratification argument: stratify when between-stratum variance
is large relative to within-stratum variance. Here's the honest part, and it's uncomfortable: that
condition is an empirical claim, and this study went on to measure it. On one axis the strata turned
out to be real but redundant; on the other they turned out not to exist at all. The evidence is on
slides 12 and 13, so hold the question — you've just anticipated the deck's main finding. Before we
move on, restate the bet the mentor's rule is making.

**Comprehension question for the learner.** Why is running two build-heavy C++ tasks considered
wasteful — and what would have to be true about those two tasks for that judgement to be correct?

---

## F. Critique of the current material

The existing artifact is a competent *dashboard*; the criticism below is about its fitness as a
*teaching* instrument, not its correctness or its craft.

**Information hierarchy.** Everything is peer-level. A five-step pipeline, per-language counts, two
independent findings, a sixteen-row chart, three document summaries and a provenance footer share one
page with no ranking. The headline conclusion is printed above the concepts it depends on, so a
newcomer meets the words *mechanism*, *realized* and *episode* in the verdict before any of them has
been defined. There is no visual distinction between "you must understand this to proceed" and "this
is supporting detail for someone who already agrees."

**Narrative flow.** The page is organised by *artifact type* — method, then evidence, then
deliverables — rather than by *question*. Consequently there is no causal chain: nothing explains why
falsification probes were run, because the fact that motivates them (the static prior scored 1 in 10)
is a footnote in a different panel. Most tellingly, the single most interesting logical moment in the
whole study never appears: the apparent contradiction between "the agent almost always searches" and
"the CPU is often compiling." Both facts are present, in different panels, with no bridge between
them — so the reader either misses the tension or resolves it incorrectly.

**Cognitive load.** By count, the page introduces roughly twenty specialised terms with no
definitions on the surface — fence, mechanism, ownership and adequacy gates, replay pass, realized,
prior, co-dominant, predicate, the five class letters, probe, breaker, composition, magnitude, and
more. Three charts compete for attention at the same visual weight, and the eye is given no
prescribed order in which to take them. For an expert scanning for a specific number this is
efficient; for a learner it exceeds working memory several times over on first contact.

**Terminology sequencing.** Terms consistently arrive before their intuitions. "Class N" is printed
before anything explains that it means "a transpiler runs as a child, then a JavaScript test runner."
"Realized action mix" uses *realized* as a modifier before the prior-versus-verdict distinction
exists for the reader. "Tool fence" appears only inside hover tooltips, so a reader who never hovers
never learns the measurement boundary at all. Worst, the word *type* is used in the page's own title
in exactly the ambiguous sense that the study's central finding splits in two — the ambiguity is
invisible precisely where it should be foregrounded.

**Visual design.** The execution is sound — validated palette, both themes, hover layer, table
fallback, no horizontal overflow. But the form is wrong for the job. Every graphic encodes a *result*
(counts, a coverage matrix, stacked shares); none encodes a *mechanism*. A learner needs to be able to
picture three things — a process tree, a cgroup boundary that counts descendants, and an
edit-build-test loop — and not one of them is drawn anywhere. The density itself is a signal:
it says "reference material, scan for what you need," which is the opposite of the sequential reading
a teaching deck requires.

**Relationship between evidence and conclusions.** Conclusions sit above their evidence, which suits a
reader who already trusts the work and inverts the order a learner needs. More seriously, the
epistemic categories are blended within single sentences: "16 of 16 episodes realized search-led"
(a measurement), "the behavioural mix is a property of this agent, not the task" (an interpretation),
and "the grid collapses" (a conclusion) are delivered as one continuous claim, while the limitations
that qualify all three are relegated to a small footer. The learner is given no way to see which
statements would survive if one measurement turned out to be wrong — and that is exactly the
discrimination they will need when the mentor pushes back.

---

## Approval requested

Before I build the full deck, please approve or revise:

1. **The audience definition (§A)** — particularly the decision to treat microarchitecture results as
   appendix-only, and the list of terms taught in-deck versus deferred.
2. **The narrative arc (§C)** — especially the choice to withhold the actions-versus-CPU
   contradiction until slide 13 and resolve it on slide 14, rather than explaining it early.
3. **The first five slides (§E)** — titles, content, visuals, and whether the speaker-note voice and
   depth are right for the lecturer you have in mind.

Tell me what to change and I will revise before generating slides 6–16, the appendix, and the rest of
the package.
