# Did my re-run reproduce Mohamad's campaign?

**Author** Tianrui (Jerry)

**Date:** 2026-07-24

## What I did, in one paragraph

Mohamad measured what the CPU does while an AI agent (GLM-5.2 driving SWE-agent) fixes real
bugs in four open-source projects: **scikit-learn, astropy, sympy, django**. I re-ran exactly
the same experiment on the same machine — same four tasks, same settings, 3 attempts per task —
and compared my 12 recordings against his 12. This document explains what I compared and what
I concluded.

## The conclusion, up front

**The experiment reproduces — but only at the level it was designed to.**

- ✅ **What reproduces:** the *proportions* (how CPU time is split between waiting, tools, and
  the agent program), the *shapes* of the activity over time, the cost of a single tool call,
  and *what* is consuming the CPU inside each part.
- ❌ **What does not reproduce:** the *absolute numbers* (how many minutes an episode takes,
  how many CPU-seconds it burns). These vary 2–3× even between two attempts of the same task
  in the *same* campaign — so a 2–3× difference between our campaigns is normal noise, not a
  real change.

In short: if you compare one of my runs against one of his runs number-by-number, they look
different. If you compare *how the time and CPU are divided up*, they look the same. The
second comparison is the meaningful one, and it passes.

## Four words you need

- **Episode** = one complete attempt at one task. The agent works in a loop: it asks the
  model what to do, runs the one command the model suggests, feeds the result back, and
  repeats — until it submits a fix or hits the 40-minute time limit. One attempt = one episode.
  Each task was attempted 3 times, so each campaign has 12 episodes.
- **Turn** = one round of that loop (one question to the model + one command executed).
- **Looped episode (⟳)** = a failed episode where the agent got stuck repeating the exact same
  command over and over until the 40-minute limit killed it. This happens because the runs
  used temperature 0.0 ("always pick the most likely next word") — once repeating becomes the
  most likely continuation, there is no randomness to escape it. Looped episodes are real
  measurements of a *failure*, not of the task, so they are excluded from the task profiles.
- **Fences** = the measurement separates CPU into three boxes: the **tool** box (the commands
  the agent runs — tests, git, etc.), the **harness** box (the agent program itself), and the
  model **wait** (time spent doing nothing, waiting for the API to reply).



## What I compared — three levels

**Level 1 — the headline episodes.** Mohamad's figures showed one representative episode per
task; I compared mine against his, number by number.

**Level 2 — all 24 episodes.** Because single episodes vary a lot, I plotted every run from
both campaigns side by side (wall-time split, CPU-work split, activity timelines, tool-call
structure — both as percentages and as raw numbers).

**Level 3 — inside the boxes.** For the CPU that *was* used, I broke down what program/library
was actually burning it, inside the tool box and inside the harness box.

All figures: `local_agents/superseded_40min/plots/compare/` (also in the shared slide deck,
slides 7–13). Both datasets were rendered with the same plotting code, so none of the
differences come from plotting changes. (One earlier red herring: his old figures show a
"peak parallelism" panel where mine show "agent-internal calls" — that panel was simply
replaced in a newer version of the plotter. Same data underneath.)

## Part 1 — Reproduced representative results (deck slides 2–6)

One featured episode per task (the clean run where one exists: scikit-learn run 1, astropy
run 2, sympy run 2; django run 2 is shown but tagged "(looped)" since no clean django episode
exists). Figures: `local_agents/superseded_40min/plots/glm_*.png`, audit-verified (ALL MATCH).

**Slide 2 · Wall-clock time split.** Episodes ran 8 / 37 / 26 / 41 minutes
(scikit-learn / astropy / sympy / django). In every one, waiting for the model dominates:
74 / 89 / 78 / 74 % of wall. Tools got 23 / 9 / 11 / 5 %, the harness 3 / 2 / 11 / 21 %.

**Slide 3 · CPU work (core-seconds).** Once the wait is stripped away, the split is
task-dependent: scikit-learn 1,449 core-s at 100 % tools (its test suite); astropy 265 core-s
at 88 % tools; sympy 234 core-s inverted to 53 % harness; django-looped 486 core-s at 89 %
harness — the CPU signature of an agent repeating itself.

**Slide 4 · Orchestration timeline.** scikit-learn fires three bursts that saturate the full
20-core partition, with quiet model-wait gaps between; astropy is spiky (peak 17 cores); sympy
never exceeds one core on either fence — a continuous trickle; the django loop is a solid
41-minute harness wall (up to ~6 cores) with tools flatlined.

**Slide 5 · Tool-call structure.** scikit-learn: 67 calls, 26 heavy, 22.8 % of wall
tool-active. astropy: 130 calls, 58 heavy, 9.3 %. sympy: 238 calls, 157 heavy, 10.9 %.
django-looped: 383 calls but only 4 heavy and 2 agent-internal — a flood of shallow repeats,
5.1 % tool-active.

**Slide 6 · Takeaways.** The profile is task-dependent: elapsed time is model-wait everywhere,
but CPU work is tool-bound for scikit-learn/astropy and harness-bound for sympy (and for every
loop). A stuck agent has a recognizable CPU signature — cost with nothing to show for it.

## Part 2 — All 24 episodes, both campaigns (deck slides 7–12)

Every run from both campaigns side by side (12 + 12), share-normalized *and* absolute.
Figures: `local_agents/superseded_40min/plots/compare/cmp_*.png`. ⟳ marks looped episodes.

**Slide 8 · Wall-clock shares, every run.** Model wait is 65–90 % of wall in all 24 episodes —
both campaigns, clean or looped. The most robust result in the study.

**Slide 9 · CPU-work shares, every run.** The per-task "personalities" reproduce on clean
runs (scikit-learn ≈ all-tool ×4, astropy tool-heavy ×3, sympy harness-leaning ×4), and every
looped run shifts toward harness — django's loops all land near 90 %. The absolute totals
under the bars swing 2–3× — episode luck, not campaign drift.

**Slide 10 · Timeline small-multiples.** All 24 activity traces in two 4×3 grids. Same task →
same shape in both campaigns; loops are instantly recognizable as solid harness walls running
into the 40-minute cap. Loop rate: Mohamad ~5/12, mine 7/12 — chance, not settings.

**Slide 11 · Absolute values (what shares hide).** Un-normalized wall minutes and
core-seconds. Mohamad's clean scikit-learn runs burn 1,771 and 2,568 core-s; mine 1,449 and
1,389. Loops pile up at the 40-minute cap in both campaigns. Shares reproduce; absolutes are
draws from a wide distribution.

**Slide 12 · Tool-call / burst structure, every run.** Clean runs of a task have matching
structure across campaigns (scikit-learn ≈ 60–140 turns, fraction heavy); loops balloon to
350–460 shallow turns. The stable constant: median tool-burst duration is 0.3–0.9 s in all 24
episodes — the price of one step reproduces even when episode length doesn't.

## Part 3 — Inside the fences: what is actually heavy (deck slide 13)

Attribution of the CPU *inside* each box, featured runs, both campaigns
(figure: `compare/cmp_whats_heavy.png`).

**Tool fence, by agent-call class** (trajectory-anchored, 100 % coverage): build/test commands
are 70–99 % of tool CPU on every clean task in both campaigns. One level deeper via profiling:
scikit-learn's test-suite CPU is ~87 % **OpenBLAS** — the "tool work" is matrix arithmetic,
not Python. The two django loops differ in content: Mohamad's repeated `git` (99 % of 143
core-s, so it reads as tool CPU), mine repeated a trivial shell command (16 core-s total, so
the cost lands harness-side).

**Harness fence, by library** (99 Hz profiling samples): 75–87 % Python interpreter, then
**tiktoken** (token counting) and **JSON/pydantic** parsing, small libc/kernel tail —
near-identical structure in both campaigns. The harness's measured job: run Python, count
tokens, parse JSON. (Note: this is the *full* SWE-agent v1.1.0 with SWE-ReX and tool bundles —
both campaigns ran the same vendored version, so the comparison is clean on that axis. A
leaner agent, e.g. mini-swe-agent, would show a lighter harness fence; that would be a
follow-up campaign, not this one.)

## Part 4 — Microarchitecture (TMA) side by side (deck slides 14–16)

The dig-deeper question: for the CPU cycles that *were* spent, what was the pipeline actually
doing? Top-down analysis (TMA) splits every pipeline slot into four buckets: **Retiring**
(useful work), **Frontend-bound** (starved of instructions), **Bad speculation** (thrown away
on wrong branch guesses), **Backend-bound** (stalled on data/execution resources). Both
campaigns carry whole-episode TMA per fence; per-run values were harvested for all 23
verifiable episodes. Figures: `compare/moh_featured/glm_tma_l1.png` + `glm_tma_l1.png`
(featured, per campaign), `glm_signature.png` both sides, `compare/cmp_tma_l1_allruns.png`
(every run).

**Slide 14 · TMA Level 1, featured episodes, side by side.** The buckets match within 1–5
points on every clean fence across campaigns. scikit-learn tool: 43/24/1/33 (Mohamad) vs
42/23/1/34 (mine) — retiring/frontend/bad-spec/backend, nearly identical.

**Slide 15 · Per-side signatures on absolute scales** (ranges anchored to hardware ceilings
where they exist — IPC 0–6, DSB coverage 0–100 %, cache MPKIs…). Cell-by-cell agreement:
scikit tool IPC 0.69 vs 0.64 with DSB 82 vs 84 %; harness IPC 2.4–2.9 in both campaigns; and
the tool side's signature instruction-cache pain (L1I MPKI 19–31) shows up in both. Reminder
from the study's own rules: high IPC/retiring does **not** certify useful work — the
interpreter retires many instructions per unit of real progress.

**Slide 16 · TMA for every run.** The most reproducible metric in the whole comparison:

- Clean runs of the same task agree within a few points across campaigns
  (e.g. sympy tool fence: 29/34/19/19 and 28/34/19/20 for Mohamad; 31/32/19/18 and
  32/31/19/18 for mine).
- The **harness fence is nearly the same bar 24 times** (~40 % retiring, ~20 % frontend,
  ~8 % bad-spec, ~28 % backend) — regardless of task, campaign, or even looping. The agent
  program's microarchitecture profile is task-independent.
- Why TMA reproduces when absolutes don't: the bucket mix is a property of **which code
  executes** (pytest, OpenBLAS, CPython), not of how long the episode ran or which path it
  took. Episode length varies 2–3×; the instruction mix doesn't.

**Which commands are frontend- vs backend-bound** (the TODO question, answered at fence
granularity): scikit-learn's tool fence is **backend-bound** (33–35 %), astropy's and sympy's
tool fences are **frontend-bound** (31–35 %) with high bad-speculation (11–19 %). The harness
is balanced retiring/backend everywhere.

**Level-2 drill (deck slide 18).** The banked continuous census also counts the Level-2
splits directly (fetch-latency and memory-bound; bandwidth and core are the remainders), so
the drill-down needs no new capture:

| Task (tool fence) | FE·fetch-lat | FE·fetch-bw | Bad·mispred | BE·memory | BE·core | Ret·heavy |
|---|---|---|---|---|---|---|
| scikit-learn | 19.6 | 3.7 | 0.6 | 6.1 | **28.3** | 22.1 |
| astropy | 17.4 | 17.1 | 14.1 | 7.0 | 6.6 | 4.2 |
| sympy | 16.4 | 15.3 | 18.0 | 10.4 | 8.0 | 2.6 |

- **scikit-learn's backend is core-bound, not DRAM**: core 28.3 % vs memory 6.1 %, with 22 %
  heavy-ops retiring (vector/FMA) — OpenBLAS is limited by execution ports/dependencies, and
  the floor-level LLC MPKI (0.01) and AMAT (5.1) independently rule out main-memory latency.
- **astropy/sympy split their frontend ~evenly between fetch-latency and fetch-bandwidth**
  (17.4/17.1 and 16.4/15.3) — the large-code-footprint signature: L1I misses stall fetch, and
  DSB→MITE undersupply throttles it, plus 14–18 % branch-mispredict.

**During which commands is L1I MPKI high?** Answerable from banked logs by joining each
`fe_lat` counter window (exact, zero-mux, epoch-bracketed in `windows.tsv`) to the tool
fence's activity bursts (10 Hz cpu.stat; contiguous bursts ≥ 3 s are the build/test
executions). astropy featured run: **MPKI ≈ 28 during build/test windows** (which carry
200 of 253 G instructions, peaking at 42) **vs ≈ 8 in short-command windows** — the
episode-level L1I MPKI of 24 is the test suite itself, not the small commands. True
*function-level* attribution would need one sampled-event replay (`GORDER_OVERRIDE`,
deterministic, no API cost) — available on request.

This directly answers the acceptance criterion ("as long as the successful runs of each task
share a similar distribution pattern, it's fine"): **they do — and at the microarchitecture
level the distributions are the tightest of all.**

## Part 5 — The django experiment: two episodes at temperature 0.6 (deck slide 17)

The follow-up my mentor asked for: since django looped in every temp-0.0 attempt, run it twice
more at temperature 0.6 (with the loop guard armed, N = 12) and see whether it can solve the
task. Method: same kit, same isolation (ISO-PROOF quiet at 0.7 %), data banked under a separate
`glm-t06` config so the temp-0.0 evidence is untouched; temperature 0.6 verified in each
episode's recorded metadata. Figures on deck slides 2–5 and 16 now carry a fifth
"django @0.6" column (audit: ALL MATCH).

**What happened:**

- **Run 1 (36.5 min, 160 turns).** Temperature 0.6 did what it is supposed to do: ~126 turns
  of genuinely varied work — **64 heavy tool bursts** versus 4 in the temp-0 loops — and only
  78 core-seconds total (the temp-0 loops burned 486–743). The agent finished its work and
  tried to **submit 29 times**. Every attempt bounced with the same error: the harness's
  submit tool (`review_on_submit_m/bin/submit`) crashes with a **Python SyntaxError** inside
  this task's container — the tool uses modern f-string syntax, and django-10097's ancient
  testbed image cannot parse it. The 12th identical bounce tripped the loop guard.
- **Run 2 (~18 min, 160 turns).** A classic work-loop (repeated `git diff-tree` inspection),
  caught by the guard — django remains genuinely loop-prone even at 0.6; the guard turned a
  40-minute burn into an 18-minute one.

**The answer to "can it solve django at higher temperature": no — and the reason is new.**
django-10097 is unsolvable in this harness configuration at *any* temperature, because no
patch can ever be produced: the submission mechanism itself is broken in this task's
environment. The failure is **two-layered**: greedy-decode loops (layer 1, fixed by 0.6 +
guard) had masked an environment/tooling incompatibility (layer 2) that only became visible
once the agent survived long enough to reach submission. Neither campaign could have seen
layer 2 before — every temp-0.0 episode died in a work-loop first.

Notes for precision: "solve" here means "submit a patch" — formal SWE-bench resolution would
additionally require the SWE-bench evaluation harness, which this kit does not run. The
harness TMA of both 0.6 episodes is the same constant bar as the other 24 (retiring ≈ 45,
frontend ≈ 22, bad-spec ≈ 8, backend ≈ 25) — one more confirmation that the agent program's
microarchitecture profile is independent of task, temperature, and outcome.

## The findings

### 1. The computer mostly waits — in every single episode

In all 24 episodes, in both campaigns, **65–90 % of the elapsed time is spent waiting for the
model API to reply**, with the CPU idle. This is the most robust result in the whole study:
no episode ever spent the majority of its time computing.

### 2. Each task has a CPU "personality," and it reproduces

When the CPU *is* busy, where the work goes depends on the task — and the split came out the
same in both campaigns (clean episodes):

| Task | CPU personality | Mohamad | Mine |
|---|---|---|---|
| scikit-learn | almost pure tool work (its test suite) | 99 % tool | 100 % tool |
| astropy | tool-heavy | 83–92 % tool | 88 % tool |
| sympy | leans toward the harness | 59–75 % harness | 53–63 % harness |
| django | (no clean episode in either campaign — see below) | — | — |

The activity *shapes* match too: scikit-learn fires three big bursts that use all 20 cores
(test runs) with long quiet waits between; sympy never uses more than one core, just a steady
trickle; a looped episode is a solid wall of low activity running into the time limit.

### 3. Absolute numbers do NOT reproduce — and that's expected

The same task, in the same campaign, varies hugely between attempts. Examples: Mohamad's two
clean scikit-learn episodes took 7 and 20 minutes (a 2.9× spread); his sympy episodes burned
142 and 412 CPU-seconds (also 2.9×). My spread is similar. So episode length and total CPU are
best understood as **draws from a wide distribution** — comparing any single episode of mine
to any single one of his is comparing two lottery tickets.

This fully explains the one alarming-looking difference: my astropy episode (37 min) was 2.4×
longer than his featured one (15 min). It decomposes into more turns (82 → 129) × slower API
responses that day (11 → 17 s per turn), i.e. entirely more *waiting*, not more work — and both
episodes sit inside the observed astropy range (15–37 min).

One number that IS stable everywhere: the median cost of a single tool call, 0.3–0.9 s in all
24 episodes. Episodes vary in *length*, not in the price of each step.

### 4. What's actually burning the CPU — same answer in both campaigns

- **Inside the tool box:** build/test commands account for 70–99 % of tool CPU on every clean
  task. And digging one level deeper on scikit-learn: ~87 % of its test-suite CPU is inside
  **OpenBLAS** — the math library. The "tool work" is mostly matrix arithmetic, not Python.
- **Inside the harness box:** ~75–87 % is the Python interpreter itself, followed by
  **tiktoken** (counting tokens) and **JSON parsing**. Measured plainly: the agent program's
  job is to run Python, count tokens, and parse JSON. Identical structure in both campaigns.

### 5. The microarchitecture mix is the most reproducible metric of all

TMA Level-1 buckets (useful work / instruction-starved / wrong guesses / data-stalled) agree
within 1–5 points between campaigns on every clean fence, and the harness fence shows nearly
the same bar in all 24 episodes. The pipeline mix depends on *which code runs*, not on how
long or which path — so it survives the episode-to-episode chaos untouched. The per-fence
attribution: scikit-learn's tool work is backend-bound (OpenBLAS, memory/execution limited),
astropy/sympy tool work is frontend-bound with high bad-speculation (interpreter churn), and
the harness is the same balanced profile on every task.

### 6. django never produced a clean episode — for either of us

django looped in 5 of its 6 verifiable attempts across both campaigns (Mohamad's remaining one
has an unreadable, empty trajectory file). Interestingly the two loops got stuck on *different*
commands — his repeated `git` (which shows up as tool CPU), mine repeated a trivial shell
command (which shows up as harness CPU, because each turn re-sends the ever-growing
conversation to the model). Same disease, different symptom — and a good demonstration of why
looped episodes must not be presented as a task's profile.

Also worth noting: temperature 0.0 is *supposed* to be deterministic, but over a live API it
isn't — his three django attempts ran 304/414/443 turns under identical settings.

**Update (the re-run happened — see Part 5):** two fresh django episodes at temperature 0.6
confirmed the loops are only half the story. One episode escaped the work-loops entirely, did
real varied work, reached submission — and discovered that the harness's submit tool crashes
(SyntaxError) inside django-10097's ancient container. So this task cannot produce a patch in
this setup at any temperature; the greedy-decode loops had been hiding an environment bug.

## The temperature question

Two natural objections came up while reading these results. Both deserve a written answer.

### "Isn't temp 0.0 better for repeatability?" — in theory yes, in practice no

Temperature 0.0 (greedy decoding) means "always pick the single most likely next word." That
is deterministic **only if the word probabilities are bitwise identical on every call** — and
over a shared serving API, they are not:

1. **Your request shares a GPU batch with other customers.** Providers batch concurrent
   requests together, and GPU math is not batch-invariant: the order of floating-point
   additions changes with batch size and shape, so the computed probabilities differ in the
   last decimal places. Usually harmless — but when two candidate words are nearly tied, the
   winner *flips*. This is the well-known "LLM APIs aren't deterministic even at temperature
   0" phenomenon; it comes from the serving infrastructure, not the sampler.
2. **An agent episode is a chaos amplifier.** One flipped word → a slightly different command
   → different tool output → a different conversation history → every later turn now has a
   *different input*. The divergence compounds over hundreds of turns rather than averaging
   out. Two episodes identical for 50 turns can end in different universes.

That is exactly what the data shows: Mohamad's three django attempts, at identical settings,
ran **304 / 414 / 443 turns**. Temp 0.0 bought no path repeatability at all.

### Why loops strike some episodes and not others

Think of the looping state as an **inescapable trap in the episode's state space**: a
conversation state where "repeat the last command" is the model's top choice and the command's
result doesn't change the state. Two independent things must happen:

- the episode's (chaotically divergent) path must **wander into** the trap — effectively a
  coin flip per episode, which is why scikit-learn, astropy and sympy each had a mix of clean
  and looped attempts;
- once inside, temp 0.0 **removes the exit** — with no sampling randomness, the second-best
  "try something else" token is never picked, ever.

So greedy decoding doesn't make the agent *reach* the trap more often — it makes the trap
inescapable *when* reached. Whether an episode loops is decided by its random path; whether it
stays looped is decided by the temperature. django's state space evidently funnels into the
trap (5 of 6 verifiable attempts), which is why it dies almost every time.

The uncomfortable conclusion: **temp 0.0 over a shared API is the worst of both worlds** — no
actual repeatability (batching noise + chaos amplification) *and* absorbing loops (no escape
hatch). And when this study does need true determinism it doesn't use temperature at all: the
kit's **replay mode** re-executes a recorded trajectory with no model in the loop — same
commands, same order, every time.

### Why 0.6, specifically?

Honestly: 0.6 is an empirical convention, not a derived value — this repo inherited it from an
earlier fix ("per prior Qwen fix" in the config) and froze it. But the convention sits where it
does for a reason. Temperature tunes exactly one thing: how much probability the *non-top*
words get.

```
0.0 ──────── 0.3 ───────── 0.6 ───────── 1.0 ──────── 1.5+
greedy:      still nearly   enough noise   noticeably    unlikely words
loops are    greedy; loop   to escape      diverse;      get sampled:
inescapable  traps survive  repetition,    quality       broken JSON,
                            syntax intact  degrades      malformed commands
```

- Below ~0.3 the distribution is still so peaked that a repetition trap survives — you keep
  the loop problem you were trying to fix.
- Around 0.6, near-ties get real probability (a would-be loop escapes within a few turns),
  while the *confident* tokens — tool-call syntax, JSON structure, code keywords — sit at
  0.99+ probability and are barely perturbed. Loop escape without breaking machine-readable
  output.
- Above ~1.0 genuinely unlikely words get sampled: malformed tool calls, invented flags — a
  different failure mode.

The usable band for agentic coding is roughly **0.4–0.8**, and 0.6 is the industry's midpoint
habit (several vendors recommend exactly this region for their coding/reasoning models). Nobody
tuned it further here on purpose: this study measures CPU behavior, not solve rate, so any
value in the safe band produces representative episodes — and **a frozen, recorded value beats
an optimized one**, because temperature must never be a hidden variable between runs (it is
written into every episode's metadata). The loop guard and the action-uniqueness validator
gate backstop it, so 0.6 only needs to make loops rare, not impossible.

## Bottom line

> **Same experiment, same machine, same settings → the proportions, shapes, per-step costs and
> CPU composition all reproduce; the absolute minutes and CPU-seconds of any single episode do
> not, and were never expected to.** Judge agent campaigns by shares and structure, never by
> one episode's raw numbers.

## Caveats

- My astropy has only one clean episode (and it's a long one). A temp-0.6 astropy re-run
  would give it a dispersion band.
- django has no *solved* episode anywhere — and Part 5 shows it cannot have one in this
  harness configuration (broken submit tool in its container), independent of temperature.
  A genuine django profile would need either a tool fix (patch `review_on_submit_m` for old
  Python) or a different django instance with a modern testbed image.
- "Looped" is classified by a simple rule (≥ 8 of the last 12 actions identical); the kit's
  validator gate E7 is the formal version.
- The harness breakdown comes from statistical profiling samples — reliable as percentages,
  meaningless as absolute rates.

---

## Appendix — side question: can SWE-bench be grouped by programming language?

**Not the original benchmark — it is 100 % Python.** Classic SWE-bench (and its Verified-500 /
Lite-300 subsets) draws from 12 Python repositories, so the meaningful axis is *by repository*,
and it is heavily skewed:

SWE-bench full test set — 2,294 instances, all Python:

| Repo | Instances | Share |
|---|---|---|
| django | 850 | 37 % |
| sympy | 386 | 17 % |
| scikit-learn | 229 | 10 % |
| sphinx | 187 | 8 % |
| matplotlib | 184 | 8 % |
| pytest | 119 | 5 % |
| xarray | 110 | 5 % |
| astropy | 95 | 4 % |
| pylint | 57 | 2 % |
| requests | 44 | 2 % |
| seaborn | 22 | 1 % |
| flask | 11 | 0.5 % |

Django alone is ~37 % — "how do you do on SWE-bench" is substantially "how do you do on
Django." The fair critique of the benchmark is repo/framework skew, not language skew.

Language diversity exists only in the newer variants:

- **SWE-bench Multilingual** — 300 instances, 9 languages, 42 repos
  (Ruby 44, Go 42, Java 43, JS/TS 43, PHP 43, Rust 43, C 30, C++ 12).
- **Multi-SWE-bench** (ByteDance) — 1,632 instances, 7 languages, Python deliberately excluded
  (exact per-language counts are in that paper's appendix; not re-verified here).
- **SWE-bench Multimodal** — 517 instances, all JavaScript (front-end repos).

The thesis campaign (SWE_clean) already uses the multilingual axis: babel (JavaScript) and
fmtlib (C++) alongside django and sympy (Python).
