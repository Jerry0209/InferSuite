Great questions — these are all about the CPU isolation setup that makes your measurements trustworthy. Let me walk through each one, tied to your specific machine.

First, a quick note on the numbers, because they reconcile once you separate physical cores from logical CPUs (hardware threads):

Set	Physical cores	Logical CPUs (HT)
Measuring (harness + tools)	10	20
Housekeeping	2	4
Total	12	24
So "harness and tools share 10 cpus" = 10 physical cores (20 threads), and "housekeeping cpus are 2" = 2 physical cores (4 threads). The w5-3425 has 12 P-cores × 2 SMT threads = 24 logical CPUs (0–23), which matches. When you write this up, be consistent about "core" vs "logical CPU" — your CLAUDE.md conventions define "core" = logical CPU, so 20 + 4 = 24 logical CPUs is the phrasing that will pass the audit.

TMA — Top-down Microarchitecture Analysis
TMA is Intel's method for answering "why isn't this core retiring instructions every cycle?" Every CPU pipeline slot in a cycle is classified into one of four top-level buckets:

Retiring — slot did useful work (an instruction completed).
Bad Speculation — work was done but thrown away (branch mispredict, etc.).
Frontend Bound — pipeline starved: couldn't fetch/decode instructions fast enough.
Backend Bound — pipeline stalled: couldn't execute (waiting on caches/memory, or execution ports busy).
These are the "L1" categories; each drills down into L2, L3, etc. It's a hierarchy that tells you where the bottleneck is without guessing.

This is exactly the instrument behind your "continuous whole-episode TMA L1/L2" measurement. On your hardware it comes from the dedicated PERF_METRICS MSR, which reports these buckets directly — so it uses zero general-purpose counters (that's why it can run continuously alongside your windowed perf stat groups without competing for PMU counters or multiplexing). It's also why your CLAUDE.md warns that "high IPC/retiring does NOT certify useful work" — the engine's CUDA busy-wait retires instructions at IPC ~3.6 and looks great in TMA's Retiring bucket, yet it's just spinning.

Housekeeping CPUs
A modern kernel can't put all cores into a pristine measurement state — someone has to run the unavoidable background work: kernel threads, interrupt (IRQ) handlers, RCU callbacks, timer ticks, writeback, and any daemons.

The housekeeping set is the small pool of cores (your 2 physical / 4 logical) deliberately set aside to absorb all that noise, so the measuring set stays as quiet as possible. In your design, this is where the litellm proxy runs (your "user slice → housekeeping cores" fence) and, importantly, where the perf TMA-collection tooling itself runs — you don't want the profiler's own CPU cost polluting the cores it's measuring. This is the mechanism behind the CLAUDE.md note that "measured-partition capacity claims are tool+harness only."

NMI watchdog
The NMI (Non-Maskable Interrupt) watchdog is a kernel lockup detector. It programs a performance counter to fire a periodic NMI on each CPU; a handler checks whether the CPU is still making progress and screams if a core has hung (hard lockup).

Two reasons you disable it for measurement:

It steals a hardware PMU counter. The watchdog permanently occupies one of the limited general-purpose performance counters on every core. With it off, all counters are free for your windowed perf stat groups — critical when you're already fighting to fit ~6 events per group with zero multiplexing.
The NMI itself is measurement noise — a periodic interrupt landing on your measured cores.
So disabling it both frees a counter and removes a periodic perturbation.

Tick suppression (nohz_full)
Normally the kernel fires a scheduler timer tick on every CPU (typically 1000 Hz = every 1 ms). Each tick is a timer interrupt that runs kernel code — scheduler bookkeeping, time accounting, RCU processing. That's 1000 tiny involuntary interruptions per second on every core.

Tick suppression (the nohz_full kernel feature) says: on the isolated cores, when exactly one runnable task is on the CPU, stop the periodic tick — drop to (nearly) 0 Hz. With no competing task, there's nothing to schedule, so the tick is pure overhead. This is the "20 hw threads with tick suppression" in your measuring set.

Effect: your measured cores run your harness/tool code with far fewer involuntary kernel interruptions, so the TMA and perf numbers reflect your workload, not the timer. It's the nohz_full half of the nohz_full+rcu_nocbs boot mode your CLAUDE.md mandates (and why isolcpus is banned — nohz_full does the isolation without breaking load-balancing).

RCU callback offloading (rcu_nocbs)
RCU (Read-Copy-Update) is a kernel synchronization mechanism. When kernel data is freed under RCU, the actual cleanup is deferred to a callback that runs later, once it's safe. By default, those callbacks execute on the same CPU that queued them — as periodic softirq work driven by... the timer tick.

Here's the catch: tick suppression and RCU callbacks fight each other. If callbacks must run on the isolated core, the kernel can't fully quiet that core's tick. RCU callback offloading (rcu_nocbs) breaks the deadlock: it moves RCU callback processing off the isolated cores onto dedicated rcuo kernel threads that run on the housekeeping cores.

That's the "RCU callback offloading" line in your measuring set, and it's why nohz_full and rcu_nocbs are always paired: offloading the callbacks is a precondition for the tick actually going quiet.

"No scheduler isolation, but restricted within the two CPU partitions"
This is the subtle one, and it's the key design decision.

What you did NOT do: isolcpus-style scheduler isolation. That kernel parameter removes cores from the scheduler's load-balancing domains entirely — the scheduler will never automatically migrate a task onto them; you'd have to pin every thread by hand. Your CLAUDE.md explicitly bans this: "isolcpus breaks scheduler load-balancing and stacks every thread on one core." Without balancing, all your harness+tool threads would pile onto a single core instead of spreading across the 10.

What you DID do: created two cpuset partitions (measuring vs housekeeping) and confined work to them. Within the measuring partition, the normal Linux scheduler still runs and still load-balances — it's free to move threads across all 10 measuring cores to keep them evenly used. It just cannot cross the partition boundary into housekeeping (and vice-versa).

So the sentence means: the scheduler is still fully alive and balancing (no isolcpus), but it operates inside a walled garden. You get the best of both — realistic multi-core scheduling of your harness and tools and a clean separation from the noisy housekeeping cores. This is the "runtime isolation (cpuset split)" your kits apply and that the ISO-PROOF gate verifies (effective cpusets correct + measured cores actually silent before capture starts).

One-line summary of the whole stack: nohz_full + rcu_nocbs (boot) quiet the ticks and offload RCU work; NMI-watchdog-off frees a counter and removes an interrupt; the cpuset partition (not isolcpus) keeps the scheduler balancing your 10 measuring cores while fencing off the 2 housekeeping cores that run litellm, kernel noise, and the perf/TMA collector — so the PERF_METRICS-based TMA reads your workload, not the measurement apparatus.

Want me to check how any of these are actually configured in scripts/harden_isolation.sh to confirm the settings match your notes?


>>>>>> Could you explain the structure of this repository? What does each file do? I want to know, for example, when I run the cd ~/InferSuite/local_agents/kit

./run_glm_campaign.sh dryrun          # zero-mux gate: all 8 groups must report 100% enabled

DATA_ROOT=$HOME/InferSuite/local_agents/superseded_40min/data \
SWE_INSTANCES="scikit-learn__scikit-learn-25232" REPEATS=1 \
  ./run_glm_campaign.sh campaign swe                    # one episode, ~10-40 min, real spend What does it do? How does it plot? Thank you!




Now I have the full picture. Here's a complete walkthrough.

The repository at a glance
InferSuite measures what the CPU does during LLM inference vs. outside it. Per CLAUDE.md there are three parts, and only the isolated campaigns count for the thesis:

Area	Where	What it is
The Service	src/service/, deploy/	RAG + semantic-cache + vLLM chatbot on k8s
Benchmark harness	local_service/	isolated k3s service campaign (data_iso)
Agentic workloads	local_agents/, agentic/	SWE-agent & OpenClaw under GLM-5.2 — this is what your command drives
Curated views	plots/, results/	synced-out figures; never edited in place
Old stuff	archive/	H100/EKS/exploratory; do not resurrect
Everything normally goes through the single entry point measure.sh, which is just a thin wrapper that sets env vars and calls the real kit. Your command bypasses measure.sh and calls the kit directly, pointing DATA_ROOT at the superseded_40min side campaign instead of the thesis SWE_clean/data.

The GLM agent kit — local_agents/kit/
The one script that does the work is run_glm_campaign.sh (915 lines). Around it:

campaign.conf — sourced config: model id, CPU partition (CPUS_MEASURED/CPUS_HOUSE), endpoints.
litellm_glm.yaml, my_api_glm.json — proxy config to relay model calls to the GLM API.
oc_lineage_watcher.py — OpenClaw-only fork/exec fence splitter.
validate_glm_agents.py — gates E1–E11.
Plotters: plot_glm_results.py (the big one — writes values_dump.json), plus plot_call_structure.py, plot_internal_tools.py, plot_calls_vs_bursts.py, plot_exploratory.py, plot_harness_scaling.py.
audit_plots.py — independently recomputes every plotted number from raw data (must say ALL MATCH).
.state/ — stage-gate markers (dryrun_ok, smoke_ok); the .out/.log files are captured console logs from past runs.
The campaign case dispatch is at run_glm_campaign.sh:900-914.

What your command actually does

cd ~/InferSuite/local_agents/kit
./run_glm_campaign.sh dryrun
DATA_ROOT=$HOME/InferSuite/local_agents/superseded_40min/data \
SWE_INSTANCES="scikit-learn__scikit-learn-25232" REPEATS=1 \
  ./run_glm_campaign.sh campaign swe
Step 1 — dryrun (no spend, no model calls)
dryrun runs stage_preflight then stage_dryrun (run_glm_campaign.sh:902). The dryrun (:655-834) is the zero-multiplexing gate. It:

Launches a busy NumPy dummy process in its own cgroup (:657-666).
For each of the 8 counter groups (fpbr cache mlp fe fe_lat core_ports dram_bw priv, defined at :45-58), runs perf stat on the dummy and greps the output. If any event reads <not counted> or shows an enabled-time percentage below 100% (i.e. the PMU had to time-share counters), that group fails (:668-674). This is the "all 8 groups must report 100% enabled" check — multiplexing is invalid for bursty agent workloads (per CLAUDE.md).
A coexistence check: the continuous TMA session (PERF_METRICS + fixed slots, no general-purpose counters) must run simultaneously with two windowed groups without either multiplexing (:675-694).
A new-event semantics check: proves each exotic counter fires on a workload known to exercise it and stays quiet on one that doesn't (divider kernel lights arith.div_active but not DRAM occupancy; a 2 GB streaming loop does the opposite) (:696-750).
On success it writes .state/dryrun_ok, which the campaign requires later. No GLM API calls, no cost.

Step 2 — campaign swe (real spend)
campaign swe calls stage_campaign swe (:875-896). Note it first checks that both dryrun_ok and smoke_ok exist (:877-878) — the reproduce.md snippet assumes you ran a smoke episode earlier (or you'd need FORCE=1). Then:

apply_isolation — splits the machine into measured vs. housekeeping cores, pins the k3s/system/user slices, sets governor/no-turbo, and the ISO-PROOF gate verifies the measured cores are actually silent before capture.
start_proxy — launches the litellm proxy on the housekeeping cores, relaying openai/GLM-5.2 calls to the GLM API. (Because it's off the measured partition, proxy CPU never pollutes the fence totals.)
Loops for INST in $SWE_INSTANCES × for N in 1..REPEATS. With your env that's exactly one episode: scikit-learn__scikit-learn-25232, run 1.
Each episode is swe_episode (:443-493):

Output dir: $DATA_ROOT/glm_swe_scikit-learn/run_1/ (so → local_agents/superseded_40min/data/…). A DONE marker makes reruns resumable/skippable.
Launches SWE-agent (agentic/swe_agent/) inside a systemd scope in measured.slice, running sweagent run-batch against that instance, pointed at the local proxy, temperature 0.6 (:454-463).
Discovers the two fences (cgroups): the harness scope (the Python process) and the per-task docker sandbox container where every tool action runs (:467-480). It waits for the sandbox to appear and for the agent to reach "STEP 2" before trusting the run ("WORK VERIFIED").
Writes metadata.json with cgroup ids, model, CPU partition, git rev.
Starts the four instruments simultaneously on those cgroups (CGS = harness,tool,proxy):
start_pollers — 10 Hz cpu.stat per fence + a /proc/stat partition witness (:217-243) → cpustat_scope*.tsv, procstat_partition.tsv. Exact core-seconds; behind every timeline/burst figure.
start_records — 99 Hz cgroup-scoped perf record (:246-254) → rec_scope*.data. Statistical; used only for what-program/symbol/CPU attribution.
start_tma_cont — continuous whole-episode TMA L1/L2 from PERF_METRICS (:256-265) → tma_cont.csv.
cycle_stats — the windowed perf rotation (:376-394): loops until the agent finishes (or SWE_DRAIN_S), each cycle shuffling the 8 groups and counting one group per 5 s window with zero multiplexing → group_<name>_w###.txt + windows.tsv (records the realized order for provenance).
When the agent exits, it stops all instruments (records first, before any cgroup teardown), stops the scope, copies the agent trajectory into run_1/traj/, cleans the sandbox, and episode_ok writes DONE if it captured ≥8 windows and a non-trivial record file (:411-421).
After the loop: stop_proxy, restore_isolation (via a trap, even on Ctrl-C), then stage_validate runs the E1–E11 gates over the new data.

So one run of your command produces a directory like the SWE_clean run I inspected: agent.log, cpustat_scope{1,2}.tsv, group_*_w###.txt, windows.tsv, tma_cont.csv, rec_scope*.data, scope*_{cpulanes,leaf,pidtime,comm,dso,ksym}.txt, metadata.json, DONE.

The ~10–40 min is one real SWE-agent episode against the live GLM-5.2 API — that's the "real spend."

How it plots
Plotting is completely decoupled from capture — the campaign script never plots. You plot afterward from the banked data, using system python3 (matplotlib is system-wide, not in .venv). Two ways:

Via the wrapper (measure.sh:68-76) — but note this is hardcoded to the thesis SWE_clean/OC_clean specs, not superseded_40min:


./measure.sh plots agents-swe
Directly, for the superseded_40min set — point PLOT_SPEC at that campaign's spec:


PLOT_SPEC=local_agents/superseded_40min/plot_spec.json python3 local_agents/kit/plot/plot_glm_results.py
The pipeline (from CLAUDE.md):


plot_spec.json  →  plotters  →  values_dump.json  →  audit_plots.py (ALL MATCH)  →  sync_plots.sh  →  thesis figure/ tree
plot_spec.json (example) names the data dir, the out dir, and which run of each cell is "featured" (resolved list) plus each cell's outcome. This is what tells the plotters which runs to draw.
plot_glm_results.py reads the spec, loads each featured run's cpustat_*.tsv / group_*.txt / tma_cont.csv / scope*_leaf.txt, and writes the figures (glm_timeline.png, glm_cpu_work.png, glm_signature.png, glm_tma_*.png, glm_harness_anatomy.png, …) plus values_dump.json — every single number displayed on any figure.
The other plotters (plot_call_structure.py, plot_internal_tools.py, plot_calls_vs_bursts.py) add the call/burst-structure figures.
audit_plots.py re-derives every value in values_dump.json straight from the raw data, independently of the plotters. Figures are only trusted once it reports ALL MATCH.
scripts/sync_plots.sh copies the approved figures into the curated top-level plots/; only after in-chat approval do they go to the thesis repo.
For superseded_40min specifically, the figures already exist in local_agents/superseded_40min/plots/ (they show as modified in your git status, meaning a recent regen changed the bytes).

One caveat worth flagging: superseded_40min is, per CLAUDE.md, a superseded soft-isolated side campaign — it's not part of the thesis scope (which uses SWE_clean/OC_clean). Your command is the documented way to (re)generate a single episode of that side set, likely for a reproducibility/sanity check rather than for a thesis figure. Also, scikit-learn__scikit-learn-25232 isn't one of the four featured cells in the SWE_clean spec (django/sympy/babel/fmt), so it wouldn't show up in the main figures unless its plot_spec.json lists it.

Want me to open plot_glm_results.py and walk through how a specific figure (say the timeline or the CPU-work breakdown) is computed from the raw .tsv files?


>>>>>> SWE_SUBSET="${SWE_SUBSET:-verified}"  What's this? What is litellm, what is validate_glm_agents.py and what are the gates inside? What does that mean? why does it has dryrun 8 counter groups, what does this mean? A coexistence check: the continuous TMA session (PERF_METRICS + fixed slots, no general-purpose counters) must run simultaneously with two windowed groups without either multiplexing. What's this A new-event semantics check: proves each exotic counter fires on a workload known to exercise it and stays quiet on one that doesn't (divider kernel lights arith.div_active but not DRAM occupancy; a 2 GB streaming loop does the opposite) (:696-750). Where is the apply isolation? what is the difference between litellm proxy and swe agent? Doesn't the agent call GLM 5.2 directly?  How can it know which part is tool, which part is LLM inference, which part is api proxy? Why API proxy is an category? Is is possible to know what tools are running behind it? And it's able to distinguish what tools are heavy workload. Is this already implemented?  How can it perform TMA? How can it make stats for that? How does it collect those data? Thank you!


Excellent questions — these get at the heart of the measurement design. Let me answer each.

SWE_SUBSET="${SWE_SUBSET:-verified}"
Standard bash "default value" idiom: use whatever SWE_SUBSET is set to in the environment, else fall back to "verified". It selects which SWE-bench subset the SWE-agent pulls tasks from. SWE-bench is a benchmark of real GitHub issues; the subsets are lite / verified / full / multimodal / multilingual (campaign.conf). verified = the human-validated 500-issue subset. It flows straight into the harness launch as --instances.subset $SWE_SUBSET (run_glm_campaign.sh:457) and is banked in metadata.json. (Side note: your Python tasks like scikit-learn are verified; the SWE_long JS/C++ ones use multilingual.)

What is litellm, and how does it differ from the SWE-agent?
They are two completely different processes at two different layers:

SWE-agent (agentic/swe_agent/) is the agent: the ReAct loop that reads the GitHub issue, decides "I should grep for X, then edit file Y," emits tool calls, and runs those tools in a sandbox. This is the workload being measured.
litellm is a proxy — a tiny HTTP server (pip install litellm[proxy]) that speaks the OpenAI API on localhost:8100 and forwards each request to the real GLM API at api.z.ai. Started by start_proxy (run_glm_campaign.sh:422-437).
"Doesn't the agent call GLM directly?" It could, but the harness deliberately inserts the proxy. Look at the launch: --agent.model.api_base 'http://localhost:8100/v1' (run_glm_campaign.sh:460). The agent thinks it's talking to a local OpenAI server; litellm relays to GLM. Why do this?

Uniform interface — SWE-agent and OpenClaw both speak OpenAI; the proxy hides GLM's endpoint/auth differences (litellm_glm.yaml).
It keeps the API key out of the agent (dummy key to the agent; real key only in the proxy).
Crucially for measurement: it isolates the request-marshalling CPU cost. Serializing the whole conversation to JSON, gzipping, TLS, HTTP — that's real CPU work, and it belongs to neither the agent's reasoning nor a tool. By running the proxy as its own cgroup pinned to the housekeeping cores (taskset -c "$CPUS_HOUSE", :427), that cost is fenced off and kept off the measured partition entirely.
How does it know which part is tool vs. LLM-inference vs. proxy? Why is "API proxy" a category?
This is the core trick, and the answer is cgroups, not process names. The machine is split into two CPU partitions (campaign.conf):

Measured cores 2-11,14-23 (20 logical) — where the real workload runs.
Housekeeping cores 0-1,12-13 — OS, ssh, dockerd, the proxy, the perf writers, IRQs.
Then each slice of interest gets its own control group (cgroup), and the harness records the exact cgroup path of each:

Category	Cgroup	What runs there
Harness (agent reasoning + orchestration)	$HARNESS_CG = the systemd scope	the SWE-agent Python process
Tool (tool execution)	$TOOL_CG = the docker sandbox container	every grep/edit/python the agent runs
Proxy (API marshalling)	$PROXY_CG = litellm's scope	request serialization + relay to GLM
Set at run_glm_campaign.sh:482: CGS="$HARNESS_CG,$TOOL_CG,$PROXY_CG". Fences are cgroups — the kernel accounts every core-nanosecond to exactly one cgroup, so perf --for-each-cgroup=$CGS and the 10 Hz cpu.stat pollers give you an exact, non-overlapping split with no name-guessing. The docker sandbox is a natural fence (tools literally run in a separate container); the harness is a natural fence (separate systemd scope).

Why "API proxy" is its own category: it's the empirical stand-in for "the CPU cost of talking to the model," as distinct from (a) the agent's own reasoning/orchestration CPU and (b) tool CPU. And per CLAUDE.md, since it lives on the housekeeping cores, the thesis's measured-partition capacity claims are tool+harness only — the proxy is measured but explicitly excluded from the "CPU during inference" partition. Note: the actual LLM inference (GLM-5.2 forward passes) happens remotely on z.ai's GPUs — it never appears on this machine at all. This suite measures the CPU work around inference (agent, tools, marshalling), which is exactly the thesis question: what the CPU does outside inference.

The one exception — OpenClaw (oc_episode): there, the Node gateway and all its tools live in one container, so there's no cgroup boundary between agent and tool. That's why oc_lineage_watcher.py exists — it splits them by process lineage (a fork stays agent-side; the moment it execs a program it becomes a tool). SWE-agent doesn't need this because docker already provides the fence.

Can it tell which tools ran, and which were heavy? Already implemented?
Yes to both, via the 99 Hz perf record instrument (start_records, :246-254). Every ~10 ms it samples the instruction pointer + call stack + which program was running, scoped to each cgroup. After the episode, mk_tables (:270-299) turns those samples into per-scope tables:

scopeN_comm.txt — which programs ran and their % of CPU samples (grep, python, git, node…).
scopeN_leaf.txt — the hottest functions/symbols. You can see this live in the sample I pulled: python3.11, OpenBLAS (libscipy_openblas64), sqlite, grep, plus kernel symbols like do_user_addr_fault.
scopeN_dso.txt — hot shared libraries; scopeN_pidtime.txt — per-PID timeline (feeds the OC lineage purity check); scopeN_cpulanes.tsv — which physical CPU each sample landed on.
"Heavy" is a defined term (CLAUDE.md vocabulary): a burst is contiguous fence CPU above a floor (tool 0.005 / harness 0.02 cores, gaps <0.4 s merged); a burst is heavy if its peak exceeds 0.3 cores. That classification comes from the exact 10 Hz cpu.stat timeline (not the statistical samples), and validator gate E9 censuses heavy bursts. So: what tools ran comes from perf-record attribution; how heavy comes from the cpu.stat burst analysis. Both are implemented and banked. One honest caveat the code documents: perf record is statistical — used only for what-program/symbol/CPU attribution, never for rates (CLAUDE.md).

⚠️ mk_tables and gen_lanes_leaf.sh note the lane/leaf writer wasn't originally committed and was reconstructed post-hoc from banked records — the derivation is exact (records carry per-sample CPU + callchain), just worth knowing the history.

Where is apply_isolation?
run_glm_campaign.sh:89-182. It runs at the start of stage_campaign (:880). What it does:

Snapshots the baseline (governor, no_turbo, THP, NMI watchdog, IRQ affinities, docker daemon.json, k3s state) into .state/ — so restore_isolation can put everything back, even after a crash (:90-108).
Applies runtime isolation (:109-144): performance governor, disable turbo (stable clocks), THP off, NMI watchdog off, route all IRQs to housekeeping cores, pin system.slice/user.slice/docker/kubepods.slice to housekeeping cores, and pin measured.slice to the measured cores. It also stops k3s + kills leftover pods (they escape the slice shield otherwise).
The ISO-PROOF gate (:145-181): applied ≠ verified. It re-reads the effective cpusets, confirms governor/no_turbo, and runs a 1.5 s quiet-check requiring the measured cores to be <2% busy with no foreign tasks. If anything fails, it aborts before any capture. (Boot-time isolation — nohz_full/rcu_nocbs — is separate, via scripts/harden_isolation.sh; this is the runtime layer.)
Why 8 counter groups in the dryrun? What does that mean?
A CPU's PMU (Performance Monitoring Unit) has only a handful of general-purpose counter registers (typically 4–8). You want to measure far more than 8 events (cache hits at L1/L2/L3, branch misses, FP scalar vs. vector, port utilization, DRAM bandwidth, divider activity, privileged vs. user cycles…). The events are therefore organized into 8 groups of ~6 events each (:45-58):


fpbr  cache  mlp  fe  fe_lat  core_ports  dram_bw  priv
Each group fits within the available registers, so it can be counted with zero multiplexing (all its events on real counters simultaneously, 100% of the window). The alternative — asking for all events at once — forces the kernel to time-multiplex: count group A for a few ms, swap to B, etc., then extrapolate. That extrapolation assumes the workload looks identical in every time-slice — catastrophically false for bursty agent loads (errors reach tens of percent, CLAUDE.md). So the design counts one group per window, cycling through all 8 over the episode (cycle_stats, :376-393), with the group order shuffled each cycle to avoid phase-locking with the agent loop.

The dryrun's job (stage_dryrun, :655-674): before spending real money, run each of the 8 groups against a busy dummy and prove each one counts at 100% enabled time — no <not counted>, no (NN.N%) scaling annotation. If any group can't fit without multiplexing on this hardware, the whole methodology is invalid, so it fails loudly. That's the "all 8 groups must report 100% enabled" gate.

The coexistence check — what is it?
Two instruments run at the same time during an episode: the windowed GP groups (above) and a continuous TMA session. TMA (Top-down Microarchitecture Analysis) on this Intel chip reads from a dedicated PERF_METRICS register + the fixed "slots" counter — it does not consume any of the general-purpose counter registers (start_tma_cont, :256-263). In principle that means TMA and the GP groups can run simultaneously without competing for registers.

The coexistence check (:675-694) verifies that principle on this actual hardware: it starts the continuous TMA session and two GP groups at once on the busy dummy, then confirms both still report 100% enabled — i.e. TMA didn't secretly steal a GP counter and force multiplexing. If it did, the whole-episode TMA census would corrupt the windowed measurements, so this must be proven clean before any capture.

The new-event semantics check — what is it?
Some of the exotic events (arith.div_active, DRAM-occupancy counters) are rare enough that they can carry silicon errata — the CPU counts the wrong thing (this is a known class of problem; the code cites Kanev et al. ISCA'15). Reading 100% enabled time proves a counter fired, not that it counted the right thing.

So the dryrun runs two microbenchmarks with known ground truth (:696-750):

A cache-resident divider kernel (np.divide on ~1 MB, in-place): heavy on the FP divider, but touches no DRAM. It must light up arith.div_active and stay near-zero on the DRAM-occupancy event. (DRAM is the negative control here.)
A 2 GB streaming sum: guaranteed DRAM-resident. Must do the opposite — saturate DRAM occupancy, near-zero divider activity.
The embedded Python check (:721-748) asserts each event is high on the workload that should exercise it and ≥3–5× lower on the one that shouldn't. If a counter fires on the wrong workload (or fails to fire on the right one), it's mis-wired and the run is refused. It's a positive-and-negative-control test that each exotic counter measures what its name claims.

How does it perform TMA / collect / make stats?
TMA collection — start_tma_cont (:256-265):


perf stat -I 10000 -x, -a -e "$TMA_EVENTS" --for-each-cgroup="$CGS" -o tma_cont.csv -- sleep 100000
The $TMA_EVENTS list is slots,topdown-retiring,topdown-bad-spec,topdown-fe-bound,topdown-be-bound,… (:60). These read the hardware's Top-down metrics directly. TMA classifies every pipeline "slot" into four L1 buckets — Retiring (useful), Bad Speculation (wasted on mispredicts), Frontend-bound (starved for instructions), Backend-bound (stalled on data/execution) — then L2 sub-buckets (heavy-ops, branch-mispredict, fetch-latency, memory-bound). -I 10000 reads the running totals every 10 s per cgroup, but the events stay installed the whole time, so it's a 100% duty-cycle exact census — the intervals are just periodic reads, not sampling. It's continuous (not windowed) precisely because it costs no GP counters. On episode end, stop_tma_cont sends SIGINT so perf flushes the final partial interval (:266-268).

Four instruments run simultaneously per episode (all started together at :484):

#	Instrument	Mechanism	Output	Used for
1	10 Hz cpu.stat pollers	read cgroup usage_usec every 100 ms	cpustat_scope*.tsv	exact core-seconds, timelines, bursts
2	Windowed perf stat	8 groups, one per 5–10 s window, shuffled	group_*_w###.txt, windows.tsv	zero-mux event ratios (cache miss %, IPC, FP mix…)
3	Continuous TMA	PERF_METRICS + fixed slots	tma_cont.csv	pipeline breakdown (retiring/FE/BE/bad-spec)
4	99 Hz perf record	statistical stack sampling per cgroup	rec_scope*.data → tables	what program/symbol/CPU (never rates)
Plus a 5th partition-wide /proc/stat witness (:234-241) that catches kernel work no cgroup owns (writeback, IRQ), so gate E11 can bound the "unfenced residual."

How the stats are made: everything is decoupled — collection just banks raw files; plotting happens later from banked data. The windowed group files are parsed for co-counted ratios (an event divided by instructions from its own windows, never pooled across groups — the "cross-group ratio dilution" bug in CLAUDE.md). TMA percentages come straight from the topdown events. Timelines/bursts/core-seconds come from the exact cpu.stat series. Program/symbol attribution comes from the perf-record tables.

validate_glm_agents.py and its gates E1–E11
validate_glm_agents.py runs after capture (stage_validate, :898). Its philosophy (CLAUDE.md): an "OK" line is not proof — each gate requires observed evidence plus an independent cross-check (two subsystems agreeing). The gates:

Gate	What it proves	Cross-check
E1	window length correct	perf's own "seconds time elapsed" vs configured WINSEC
E2	our "CPUs utilized" formula is right	vs perf's own # N CPUs utilized comment
E3	CPU accounting is trustworthy	kernel cpu.stat deltas vs PMU task-clock, same window+scope (two independent subsystems)
E4	OC fence purity	perf-record comms: /agent must be node-dominated, /toolexec not (lineage or comm mode)
E5	the agent actually worked (SWE)	"STEP" markers in the log + trajectory dir present
E6	kernel-share is real	PMU cycles:k/(u+k) vs scheduler's independent accounting
E7	not a degenerate greedy loop (SWE)	action-uniqueness in the trajectory (<40% unique = degenerate)
E9	heavy-burst census	every counter group's windows must have seen heavy bursts (rotation coverage)
E10	continuous-TMA census valid	zero-multiplex, full coverage over intervals
E11	unfenced work is bounded	partition witness: partition-busy − fence-sums must be <1% of capacity
(E8 is referenced in comments as the burst-side guard.) A run isn't trusted until these pass — and separately, the figures aren't trusted until audit_plots.py reports ALL MATCH.

If you want, I can now open plot_glm_results.py and trace how, say, the TMA tree figure or the CPU-work split is computed from tma_cont.csv and the group files — that would close the loop from raw counters to a specific plotted number.


下面是 metrics.md 的中文翻译。技术术语、代码标识符、文件名保持原样，散文部分译成中文。

问得很好——这些都是关于让你的测量结果可信的 CPU 隔离设置。让我结合你这台具体的机器逐一讲解。

先快速说明一下那些数字,因为只要把**物理核(physical core)和逻辑 CPU(logical CPU,即硬件线程)**分开,它们就能对上:

分组	物理核	逻辑 CPU(超线程)
测量组(harness + tools)	10	20
后勤组(Housekeeping)	2	4
合计	12	24
所以"harness 和 tools 共用 10 个 cpu" = 10 个物理核(20 个线程),"housekeeping cpu 是 2 个" = 2 个物理核(4 个线程)。w5-3425 有 12 个 P 核 × 2 个 SMT 线程 = 24 个逻辑 CPU(0–23),正好对上。你在论文里写的时候,要在 "core" 和 "logical CPU" 上保持一致——你的 CLAUDE.md 约定里 "core" = 逻辑 CPU,所以 "20 + 4 = 24 个逻辑 CPU" 这个说法才能通过审计。

TMA —— Top-down Microarchitecture Analysis(自顶向下微架构分析)
TMA 是 Intel 用来回答"这个核为什么没能每个周期都退休(retire)指令?"的方法。一个周期里的每个流水线槽位(pipeline slot)都被归入四个顶层桶之一:

Retiring(退休) —— 槽位做了有用的工作(一条指令完成了)。
Bad Speculation(错误推测) —— 做了工作但被丢弃(分支预测错误等)。
Frontend Bound(前端受限) —— 流水线饿着了:取指/译码跟不上。
Backend Bound(后端受限) —— 流水线卡住了:执行不了(在等缓存/内存,或执行端口忙)。
这些是 "L1" 类别;每个再往下钻取到 L2、L3 等。它是一个层级结构,不用猜就能告诉你瓶颈在哪。

这正是你"连续整回合 TMA L1/L2"测量背后的仪器。在你的硬件上,它来自专用的 PERF_METRICS MSR 寄存器,直接报告这些桶——所以它用了零个通用计数器(这就是为什么它能持续运行、和你那些开窗的 perf stat 组并存,而不用争抢 PMU 计数器或多路复用)。这也是为什么你的 CLAUDE.md 警告"高 IPC/retiring 并不能证明是有用的工作"——引擎的 CUDA 忙等(busy-wait)以 IPC ~3.6 退休指令,在 TMA 的 Retiring 桶里看着很漂亮,但其实只是在空转。

后勤 CPU(Housekeeping CPUs)
现代内核没法把所有核都置于纯净的测量状态——总得有人去跑那些不可避免的后台工作:内核线程、中断(IRQ)处理程序、RCU 回调、定时器 tick、回写(writeback),以及各种守护进程。

后勤组就是特意划出来的一小撮核(你的 2 物理 / 4 逻辑),用来吸收所有这些噪声,好让测量组尽量安静。在你的设计里,litellm 代理就跑在这里(你那个"user slice → 后勤核"的围栏),而且很重要的是,perf 的 TMA 采集工具本身也跑在这里——你不想让剖析器自身的 CPU 开销污染它正在测量的那些核。这就是 CLAUDE.md 里"被测分区的容量声明只算 tool+harness"这条说法背后的机制。

NMI 看门狗(NMI watchdog)
NMI(不可屏蔽中断)看门狗是内核的死锁检测器。它编程一个性能计数器,在每个 CPU 上周期性触发 NMI;处理程序检查该 CPU 是否还在推进,如果某个核卡死了(硬死锁)就报警。

测量时禁用它有两个理由:

它占了一个硬件 PMU 计数器。 看门狗在每个核上永久占用一个有限的通用性能计数器。关掉它,所有计数器都能给你的开窗 perf stat 组用了——当你已经在拼命想把每组 ~6 个事件塞进去还要做到零多路复用时,这一点至关重要。
NMI 本身就是测量噪声——一个周期性落在你被测核上的中断。
所以禁用它既释放了一个计数器,又消除了一个周期性扰动。

Tick 抑制(nohz_full)
正常情况下内核会在每个 CPU 上触发调度器定时器 tick(通常 1000 Hz = 每 1 ms 一次)。每个 tick 都是一个运行内核代码的定时器中断——调度器记账、时间统计、RCU 处理。也就是每秒在每个核上有 1000 次微小的、非自愿的打断。

Tick 抑制(nohz_full 内核特性)的说法是:在被隔离的核上,当 CPU 上恰好只有一个可运行任务时,停掉周期性 tick——降到(近乎)0 Hz。既然没有竞争任务,就没什么可调度的,tick 纯属开销。这就是你测量组里"20 个带 tick 抑制的硬件线程"。

效果:你的被测核跑你的 harness/tool 代码时,非自愿的内核打断少得多,所以 TMA 和 perf 的数字反映的是你的工作负载,而不是定时器。它是你 CLAUDE.md 规定的 nohz_full+rcu_nocbs 启动模式里 nohz_full 那一半(也是为什么 isolcpus 被禁用——nohz_full 能做到隔离而不破坏负载均衡)。

RCU 回调卸载(rcu_nocbs)
RCU(Read-Copy-Update,读-拷贝-更新)是一种内核同步机制。当在 RCU 保护下释放内核数据时,真正的清理会被推迟到一个回调里,在安全的时候再跑。默认情况下,这些回调在排队它们的那个 CPU 上执行——作为周期性的 softirq 工作,由……定时器 tick 驱动。

问题就在这:tick 抑制和 RCU 回调互相打架。如果回调必须在被隔离的核上跑,内核就没法让那个核的 tick 完全安静下来。RCU 回调卸载(rcu_nocbs)打破了这个死结:它把 RCU 回调处理挪出被隔离的核,交给跑在后勤核上的专用 rcuo 内核线程。

这就是你测量组里"RCU 回调卸载"那一行,也是为什么 nohz_full 和 rcu_nocbs 总是成对出现:卸载回调是 tick 真正安静下来的前提条件。

"没有调度器隔离,但被限制在两个 CPU 分区内"
这一条比较微妙,也是关键的设计决策。

**你没有做的:**isolcpus 式的调度器隔离。那个内核参数会把核完全从调度器的负载均衡域里移除——调度器永远不会自动把任务迁移到它们上面;你得手动把每个线程都钉住。你的 CLAUDE.md 明确禁用它:"isolcpus 破坏调度器负载均衡,把每个线程都堆到一个核上"。没有均衡,你所有的 harness+tool 线程会全挤到单个核上,而不是分散到那 10 个核。

你做的:创建了两个 cpuset 分区(测量组 vs 后勤组)并把工作限制在其中。在测量分区内部,正常的 Linux 调度器照常运行、照常做负载均衡——它可以自由地在全部 10 个测量核之间迁移线程以保持均匀利用。它只是不能越过分区边界进到后勤组(反之亦然)。

所以这句话的意思是:调度器仍然完全活跃、仍在做均衡(没有 isolcpus),但它在一个围起来的花园里运作。你两全其美——既有对 harness 和 tool 真实的多核调度,又和吵闹的后勤核干净地分开。这就是你的套件所施加、并由 ISO-PROOF 门禁验证的"运行时隔离(cpuset 划分)"(有效 cpuset 正确 + 采集开始前被测核确实安静)。

整套栈一句话总结: nohz_full + rcu_nocbs(启动时)让 tick 安静并卸载 RCU 工作;关闭 NMI 看门狗释放一个计数器并去掉一个中断;cpuset 分区(不是 isolcpus)让调度器继续在你那 10 个测量核上做均衡,同时把跑着 litellm、内核噪声和 perf/TMA 采集器的那 2 个后勤核围隔开——这样基于 PERF_METRICS 的 TMA 读到的是你的工作负载,而不是测量仪器本身。

想让我去 scripts/harden_isolation.sh 里核对一下这些实际是怎么配置的、确认设置和你的笔记一致吗?

文件后面(第 63 行往后,以 >>>>>> 分隔)还保存了我们之前那几轮问答的完整存档——仓库结构讲解、run_glm_campaign.sh dryrun/campaign swe 的逐步走查、如何绘图,以及关于 SWE_SUBSET、litellm、validate_glm_agents.py 的 E1–E11 门禁、8 个计数器组、coexistence 检查、new-event semantics 检查、apply_isolation、TMA 采集等的详细解答。

需要我把 >>>>>> 之后那三大段问答也一并翻成中文吗?那部分很长,内容基本就是我们这次对话前面已经讨论过的英文原文。



第一段问答
>>>>>> 你能讲讲这个仓库的结构吗?每个文件是做什么的?比如说,当我运行


cd ~/InferSuite/local_agents/kit
./run_glm_campaign.sh dryrun          # 零多路复用门禁:8 个组必须全部报告 100% enabled
DATA_ROOT=$HOME/InferSuite/local_agents/superseded_40min/data \
SWE_INSTANCES="scikit-learn__scikit-learn-25232" REPEATS=1 \
  ./run_glm_campaign.sh campaign swe                    # 一个回合,约 10–40 分钟,真实花费
它做了什么?怎么绘图的?谢谢!

现在我掌握了完整的图景。这是一份完整的走查。

仓库概览
InferSuite 测量的是 CPU 在 LLM 推理期间 vs 推理之外分别做什么。按 CLAUDE.md,它有三个部分,而只有隔离的 campaign 才算入论文范围:

领域	位置	是什么
The Service	src/service/、deploy/	k8s 上的 RAG + 语义缓存 + vLLM 聊天机器人
Benchmark harness	local_service/	隔离的 k3s service campaign(data_iso)
Agentic workloads	local_agents/、agentic/	GLM-5.2 下的 SWE-agent 和 OpenClaw——这就是你的命令所驱动的
Curated views	plots/、results/	同步出来的图;不在原地编辑
Old stuff	archive/	H100/EKS/探索性内容;不要复活
一切通常都经由单一入口 measure.sh,它只是个薄封装,设好环境变量再调用真正的 kit。你的命令绕过了 measure.sh 直接调用 kit,并把 DATA_ROOT 指向 superseded_40min 这个旁支 campaign,而不是论文用的 SWE_clean/data。

GLM agent kit —— local_agents/kit/
真正干活的那个脚本是 run_glm_campaign.sh(915 行)。围绕它的有:

campaign.conf —— 被 source 进来的配置:模型 id、CPU 分区(CPUS_MEASURED/CPUS_HOUSE)、端点。
litellm_glm.yaml、my_api_glm.json —— 把模型调用转发到 GLM API 的代理配置。
oc_lineage_watcher.py —— 仅 OpenClaw 用的 fork/exec 围栏拆分器。
validate_glm_agents.py —— 门禁 E1–E11。
绘图器:plot_glm_results.py(最大的那个——写出 values_dump.json),外加 plot_call_structure.py、plot_internal_tools.py、plot_calls_vs_bursts.py、plot_exploratory.py、plot_harness_scaling.py。
audit_plots.py —— 从原始数据独立重算每一个被绘制的数字(必须报 ALL MATCH)。
.state/ —— 阶段门禁标记(dryrun_ok、smoke_ok);那些 .out/.log 文件是过往运行捕获的控制台日志。
campaign 的 case 分派在 run_glm_campaign.sh:900-914。

你的命令实际做了什么

cd ~/InferSuite/local_agents/kit
./run_glm_campaign.sh dryrun
DATA_ROOT=$HOME/InferSuite/local_agents/superseded_40min/data \
SWE_INSTANCES="scikit-learn__scikit-learn-25232" REPEATS=1 \
  ./run_glm_campaign.sh campaign swe
第 1 步 —— dryrun(无花费、无模型调用)

dryrun 先跑 stage_preflight 再跑 stage_dryrun(run_glm_campaign.sh:902)。dryrun(:655-834)就是零多路复用门禁。它:

在自己的 cgroup 里启动一个繁忙的 NumPy 假进程(:657-666)。
对 8 个计数器组中的每一个(fpbr cache mlp fe fe_lat core_ports dram_bw priv,定义在 :45-58),对假进程跑 perf stat 并 grep 输出。如果任何事件读到 <not counted>,或显示的 enabled 时间百分比低于 100%(即 PMU 不得不分时复用计数器),该组就失败(:668-674)。这就是"8 个组必须全部报告 100% enabled"的检查——对突发性 agent 工作负载而言多路复用是无效的(按 CLAUDE.md)。
coexistence(并存)检查:连续 TMA 会话(PERF_METRICS + 固定槽位,不占通用计数器)必须能和两个开窗组同时运行而互不多路复用(:675-694)。
new-event semantics(新事件语义)检查:证明每个 exotic 计数器在已知会触发它的负载上确实点亮,而在不该触发的负载上保持沉默(divider kernel 点亮 arith.div_active 但不点亮 DRAM 占用;2 GB streaming 循环则相反)(:696-750)。
成功后它写出 .state/dryrun_ok,后面的 campaign 会用到。没有 GLM API 调用,不产生费用。

第 2 步 —— campaign swe(真实花费)

campaign swe 调用 stage_campaign swe(:875-896)。注意它先检查 dryrun_ok 和 smoke_ok 都存在(:877-878)——reproduce.md 的片段假设你之前跑过一个 smoke 回合(否则你需要 FORCE=1)。然后:

apply_isolation —— 把机器分成被测核 vs 后勤核,钉住 k3s/system/user 各 slice,设置 governor/no-turbo,ISO-PROOF 门禁在采集前验证被测核确实安静。
start_proxy —— 在后勤核上启动 litellm 代理,把 openai/GLM-5.2 调用转发到 GLM API。(因为它在被测分区之外,代理 CPU 永远不会污染围栏总量。)
循环 for INST in $SWE_INSTANCES × for N in 1..REPEATS。按你的环境变量,这恰好是一个回合:scikit-learn__scikit-learn-25232,run 1。
每个回合是 swe_episode(:443-493):

输出目录:$DATA_ROOT/glm_swe_scikit-learn/run_1/(即 → local_agents/superseded_40min/data/…)。一个 DONE 标记让重跑可恢复/可跳过。
在 measured.slice 里的一个 systemd scope 中启动 SWE-agent(agentic/swe_agent/),对该实例跑 sweagent run-batch,指向本地代理,temperature 0.6(:454-463)。
发现两个围栏(cgroup):harness scope(Python 进程)和每任务的 docker 沙箱容器(所有工具动作在其中运行)(:467-480)。它会等沙箱出现、等 agent 到达 "STEP 2" 才信任这次运行("WORK VERIFIED")。
写出 metadata.json,含 cgroup id、模型、CPU 分区、git rev。
在这些 cgroup 上同时启动四个仪器(CGS = harness,tool,proxy):
start_pollers —— 每围栏 10 Hz 的 cpu.stat + 一个 /proc/stat 分区见证者(:217-243)→ cpustat_scope*.tsv、procstat_partition.tsv。精确的核秒;每张时间线/突发图背后都是它。
start_records —— 99 Hz 的、按 cgroup 限定范围的 perf record(:246-254)→ rec_scope*.data。统计性;只用于"什么程序/符号/CPU"归因。
start_tma_cont —— 来自 PERF_METRICS 的连续整回合 TMA L1/L2(:256-265)→ tma_cont.csv。
cycle_stats —— 开窗 perf 轮转(:376-394):循环直到 agent 结束(或到 SWE_DRAIN_S),每个周期打乱 8 个组,每个 5 秒窗口数一个组、零多路复用 → group_<name>_w###.txt + windows.tsv(记录实际顺序以备溯源)。
agent 退出时,它停掉所有仪器(先停 records,在任何我们控制的 cgroup 拆除之前),停掉 scope,把 agent 轨迹拷进 run_1/traj/,清理沙箱,若捕获到 ≥8 个窗口和一个非平凡的 record 文件,episode_ok 就写出 DONE(:411-421)。
循环之后:stop_proxy、restore_isolation(经由 trap,即使 Ctrl-C 也执行),然后 stage_validate 对新数据跑 E1–E11 门禁。

所以你这条命令的一次运行会产生一个目录,类似我查看过的 SWE_clean 运行:agent.log、cpustat_scope{1,2}.tsv、group__w###.txt、windows.tsv、tma_cont.csv、rec_scope.data、scope*_{cpulanes,leaf,pidtime,comm,dso,ksym}.txt、metadata.json、DONE。

那"约 10–40 分钟"是针对活的 GLM-5.2 API 的一个真实 SWE-agent 回合——这就是"真实花费"。

它怎么绘图
绘图与采集完全解耦——campaign 脚本从不绘图。你事后从存好的数据绘图,用系统的 python3(matplotlib 装在系统层,不在 .venv 里)。两种方式:

经封装器(measure.sh:68-76)——但注意它硬编码到论文的 SWE_clean/OC_clean spec,不是 superseded_40min:


./measure.sh plots agents-swe
直接针对 superseded_40min 集——把 PLOT_SPEC 指向那个 campaign 的 spec:


PLOT_SPEC=local_agents/superseded_40min/plot_spec.json python3 local_agents/kit/plot/plot_glm_results.py
流水线(出自 CLAUDE.md):


plot_spec.json  →  绘图器  →  values_dump.json  →  audit_plots.py (ALL MATCH)  →  sync_plots.sh  →  论文 figure/ 树
plot_spec.json(示例)指明 data 目录、out 目录,以及每个单元格哪一次运行是"featured"(resolved 列表)加上每个单元格的结果。这告诉绘图器要画哪些运行。
plot_glm_results.py 读取 spec,加载每个 featured 运行的 cpustat_.tsv / group_.txt / tma_cont.csv / scopeleaf.txt,写出图(glm_timeline.png、glm_cpu_work.png、glm_signature.png、glm_tma.png、glm_harness_anatomy.png、…)外加 values_dump.json——任何图上显示的每一个数字。
其他绘图器(plot_call_structure.py、plot_internal_tools.py、plot_calls_vs_bursts.py)补上 call/burst 结构图。
audit_plots.py 直接从原始数据、独立于绘图器地重新导出 values_dump.json 里的每个值。只有当它报 ALL MATCH 时图才被信任。
scripts/sync_plots.sh 把批准的图拷进顶层 plots/;只有在对话里获批后才进论文仓库。
对 superseded_40min 而言,图已经存在于 local_agents/superseded_40min/plots/(它们在你的 git status 里显示为 modified,说明最近一次重绘改动了字节)。

一个值得点出的注意点:按 CLAUDE.md,superseded_40min 是一个被取代的软隔离旁支 campaign——它不在论文范围内(论文用 SWE_clean/OC_clean)。你的命令是(重新)生成那个旁支集单个回合的规范做法,大概是为了可复现性/合理性检查,而不是为了论文图。另外,scikit-learn__scikit-learn-25232 不在 SWE_clean spec 的四个 featured 单元格里(django/sympy/babel/fmt),所以除非它的 plot_spec.json 列出它,否则它不会出现在主图里。

第二段问答
>>>>>> SWE_SUBSET="${SWE_SUBSET:-verified}" 这是什么?litellm 是什么?validate_glm_agents.py 是什么,里面的门禁是什么?那是什么意思?为什么 dryrun 有 8 个计数器组,这什么意思?"A coexistence check: 连续 TMA 会话(PERF_METRICS + 固定槽位,不占通用计数器)必须和两个开窗组同时运行而互不多路复用"——这是什么?"A new-event semantics check: 证明每个 exotic 计数器在已知会触发它的负载上点亮、在不触发的负载上保持沉默(divider kernel 点亮 arith.div_active 但不点亮 DRAM 占用;2 GB streaming 循环相反)(:696-750)"。apply isolation 在哪?litellm 代理和 swe agent 有什么区别?agent 难道不是直接调 GLM 5.2 吗?它怎么知道哪部分是 tool、哪部分是 LLM 推理、哪部分是 api 代理?为什么 API 代理是一个类别?有没有可能知道背后跑了哪些工具?它能区分哪些工具是重负载吗?这已经实现了吗?它怎么执行 TMA?怎么为此做统计?怎么采集这些数据?谢谢!

问得非常好——这些触及了测量设计的核心。让我逐一回答。

SWE_SUBSET="${SWE_SUBSET:-verified}"
标准的 bash "默认值"惯用法:用环境里设的 SWE_SUBSET,否则回退到 "verified"。它选择 SWE-agent 从哪个 SWE-bench 子集取任务。SWE-bench 是真实 GitHub issue 的基准;子集有 lite / verified / full / multimodal / multilingual(campaign.conf)。verified = 经人工验证的 500-issue 子集。它直接进入 harness 启动参数 --instances.subset $SWE_SUBSET(run_glm_campaign.sh:457),并存入 metadata.json。(附注:你的 Python 任务如 scikit-learn 用 verified;SWE_long 的 JS/C++ 任务用 multilingual。)

litellm 是什么,和 SWE-agent 有何不同?
它们是两个完全不同的进程,处在两个不同的层:

SWE-agent(agentic/swe_agent/)是 agent 本身:那个 ReAct 循环,读 GitHub issue,决定"我应该 grep X,然后编辑文件 Y",发出工具调用,并在沙箱里运行这些工具。这是被测量的工作负载。
litellm 是 一个代理——一个小 HTTP 服务器(pip install litellm[proxy]),在 localhost:8100 上讲 OpenAI API,把每个请求转发给 api.z.ai 上真正的 GLM API。由 start_proxy 启动(run_glm_campaign.sh:422-437)。
"agent 难道不是直接调 GLM 吗?" 它可以,但 harness 故意插入了代理。看启动:--agent.model.api_base 'http://localhost:8100/v1'(run_glm_campaign.sh:460)。agent 以为自己在跟一个本地 OpenAI 服务器说话;litellm 把它转发给 GLM。为什么这么做?

统一接口 —— SWE-agent 和 OpenClaw 都讲 OpenAI;代理隐藏了 GLM 的端点/鉴权差异(litellm_glm.yaml)。
它把 API key 挡在 agent 之外(给 agent 的是 dummy key;真 key 只在代理里)。
对测量至关重要:它隔离了请求编组(marshalling)的 CPU 开销。 把整段对话序列化成 JSON、gzip、TLS、HTTP——这些是实打实的 CPU 工作,既不属于 agent 的推理,也不属于某个工具。通过把代理作为自己的 cgroup、钉在后勤核上(taskset -c "$CPUS_HOUSE",:427),这份开销被围隔开、彻底挡在被测分区之外。
它怎么知道哪部分是 tool、哪部分是 LLM 推理、哪部分是代理?为什么"API 代理"是一个类别?
这是核心把戏,答案是用 cgroup,不是用进程名。机器被分成两个 CPU 分区(campaign.conf):

被测核 2-11,14-23(20 个逻辑核)—— 真实工作负载运行处。
后勤核 0-1,12-13 —— OS、ssh、dockerd、代理、perf 写入器、IRQ。
然后每个感兴趣的切片都拿到自己的控制组(cgroup),harness 记录下每一个的确切 cgroup 路径:

类别	Cgroup	那里跑什么
Harness(agent 推理 + 编排)	$HARNESS_CG = systemd scope	SWE-agent Python 进程
Tool(工具执行)	$TOOL_CG = docker 沙箱容器	agent 跑的每个 grep/edit/python
Proxy(API 编组)	$PROXY_CG = litellm 的 scope	请求序列化 + 转发到 GLM
在 run_glm_campaign.sh:482 设定:CGS="$HARNESS_CG,$TOOL_CG,$PROXY_CG"。围栏就是 cgroup——内核把每一核纳秒都精确记到恰好一个 cgroup,所以 perf --for-each-cgroup=$CGS 和 10 Hz 的 cpu.stat pollers 给你一个精确、不重叠的划分,不用猜名字。docker 沙箱是天然围栏(工具确实在独立容器里跑);harness 是天然围栏(独立 systemd scope)。

为什么"API 代理"自成一类:它是"跟模型对话的 CPU 开销"的经验代表,区别于(a)agent 自身的推理/编排 CPU 和(b)工具 CPU。而且按 CLAUDE.md,由于它住在后勤核上,论文的被测分区容量声明只算 tool+harness——代理被测量但明确排除在"推理期间 CPU"分区之外。注意:真正的 LLM 推理(GLM-5.2 前向传播)发生在 z.ai 的远端 GPU 上——它根本不出现在这台机器上。这套件测量的是推理周边的 CPU 工作(agent、工具、编组),这正是论文的问题:CPU 在推理之外做什么。

唯一的例外 —— OpenClaw(oc_episode):那里 Node 网关和它所有的工具都住在一个容器里,所以 agent 和 tool 之间没有 cgroup 边界。这就是 oc_lineage_watcher.py 存在的原因——它按进程血缘拆分二者(fork 保持在 agent 侧;一旦 exec 一个程序就变成 tool)。SWE-agent 不需要这个,因为 docker 已经提供了围栏。

它能说出跑了哪些工具、哪些是重的吗?已经实现了吗?
两者都能,经由 99 Hz perf record 仪器(start_records,:246-254)。每 ~10 ms 它采样指令指针 + 调用栈 + 当时在跑哪个程序,按 cgroup 限定范围。回合结束后,mk_tables(:270-299)把这些采样变成每范围的表:

scopeN_comm.txt —— 哪些程序跑过,及其占 CPU 采样的百分比(grep、python、git、node…)。
scopeN_leaf.txt —— 最热的函数/符号。你能在我拉出来的样本里看到:python3.11、OpenBLAS(libscipy_openblas64)、sqlite、grep,外加内核符号如 do_user_addr_fault。
scopeN_dso.txt —— 热的共享库;scopeN_pidtime.txt —— 每 PID 时间线(喂给 OC 血缘纯度检查);scopeN_cpulanes.tsv —— 每个采样落在哪个物理 CPU。
"Heavy(重)"是一个有定义的术语(CLAUDE.md 词汇表):*burst(突发)*是超过某地板值的连续围栏 CPU(tool 0.005 / harness 0.02 核,间隙 <0.4 s 合并);一个 burst 若峰值超过 0.3 核就是 heavy。该分类来自精确的 10 Hz cpu.stat 时间线(不是统计采样),验证门禁 E9 会做 heavy-burst 普查。所以:跑了哪些工具来自 perf-record 归因;有多重来自 cpu.stat 突发分析。两者都已实现并存好。代码记录了一个诚实的注意点:perf record 是统计性的——只用于"什么程序/符号/CPU"归因,绝不用于速率(CLAUDE.md)。

⚠️ mk_tables 和 gen_lanes_leaf.sh 注明 lane/leaf 写入器最初没提交,是事后从存好的 record 重建的——推导是精确的(record 已带每采样的 CPU + 调用链),只是这段历史值得知道。

apply_isolation 在哪?
run_glm_campaign.sh:89-182。它在 stage_campaign 的开头运行(:880)。它做的事:

快照基线(governor、no_turbo、THP、NMI 看门狗、IRQ 亲和性、docker daemon.json、k3s 状态)到 .state/——这样 restore_isolation 能把一切还原,即使崩溃后也行(:90-108)。
施加运行时隔离(:109-144):performance governor、禁 turbo(稳定时钟)、THP off、NMI 看门狗 off、把所有 IRQ 路由到后勤核、把 system.slice/user.slice/docker/kubepods.slice 钉到后勤核、把 measured.slice 钉到被测核。它还停掉 k3s + 杀掉遗留 pod(否则它们会逃出 slice 屏蔽)。
ISO-PROOF 门禁(:145-181):施加 ≠ 已验证。它重读有效 cpuset,确认 governor/no_turbo,并跑一个 1.5 秒安静检查,要求被测核忙碌 <2% 且无外来任务。若有任何失败,它在任何采集之前中止。(启动期隔离——nohz_full/rcu_nocbs——是另一回事,经由 scripts/harden_isolation.sh;这一层是运行时的。)
为什么 dryrun 里有 8 个计数器组?什么意思?
一颗 CPU 的 PMU(性能监控单元)只有寥寥几个通用计数器寄存器(通常 4–8 个)。你想测量的事件远多于 8 个(L1/L2/L3 缓存命中、分支预测错误、FP 标量 vs 向量、端口利用率、DRAM 带宽、除法器活动、特权 vs 用户周期…)。因此事件被组织成 8 个组、每组 ~6 个事件(:45-58):


fpbr  cache  mlp  fe  fe_lat  core_ports  dram_bw  priv
每个组都能装进可用寄存器,所以能以零多路复用计数(它的所有事件同时上真实计数器,占满整个窗口 100%)。另一种做法——一次性要求全部事件——会迫使内核分时复用:数组 A 几毫秒,切到 B,如此循环,然后外推。那种外推假设工作负载在每个时间片里看起来一样——对突发性 agent 负载而言这大错特错(误差达到几十个百分点,CLAUDE.md)。所以设计上是每窗口数一个组,整个回合里轮完全部 8 个(cycle_stats,:376-393),而且每个周期打乱组顺序以避免和 agent 循环相位锁定。

dryrun 的职责(stage_dryrun,:655-674):在花真金白银之前,对繁忙假进程跑 8 个组中的每一个,证明每个都能在 100% enabled 时间下计数——没有 <not counted>,没有 (NN.N%) 缩放标注。如果任何组在这台硬件上装不下而不多路复用,整套方法论就无效,所以它会大声失败。这就是"8 个组必须全部报告 100% enabled"的门禁。

coexistence 检查 —— 是什么?
回合期间有两个仪器同时运行:开窗 GP 组(上面那些)和一个连续 TMA 会话。这颗 Intel 芯片上的 TMA(自顶向下微架构分析)读自专用的 PERF_METRICS 寄存器 + 固定的 "slots" 计数器——它不消耗任何通用计数器寄存器(start_tma_cont,:256-263)。原则上这意味着 TMA 和 GP 组能同时运行而不争抢寄存器。

coexistence 检查(:675-694)在这台实际硬件上验证这条原则:它对繁忙假进程同时启动连续 TMA 会话和两个 GP 组,然后确认二者仍报 100% enabled——即 TMA 没有偷偷占走一个 GP 计数器、逼出多路复用。如果它偷了,整回合 TMA 普查就会破坏开窗测量,所以这必须在任何采集前被证明是干净的。

new-event semantics 检查 —— 是什么?
有些 exotic 事件(arith.div_active、DRAM 占用计数器)罕见到可能带有硅片 errata(勘误)——CPU 数错了东西(这是一类已知问题;代码引用了 Kanev 等人 ISCA'15)。读到 100% enabled 时间只证明计数器触发了,不证明它数的是对的东西。

所以 dryrun 跑两个带已知真值的微基准(:696-750):

一个缓存驻留的除法器 kernel(np.divide 在 ~1 MB 上、原地):对 FP 除法器很重,但不碰 DRAM。它必须点亮 arith.div_active 且在 DRAM 占用事件上保持近零。(这里 DRAM 是负对照。)
一个 2 GB streaming sum:保证 DRAM 驻留。必须做相反的事——占满 DRAM 占用,除法器活动近零。
内嵌的 Python 检查(:721-748)断言每个事件在该触发它的负载上高、在不该触发的负载上低 ≥3–5 倍。如果某计数器在错误的负载上触发(或在正确的负载上没触发),它就是接错线了,该次运行被拒。这是一个对每个 exotic 计数器"数的是不是名字所声称之物"的正负对照测试。

它怎么执行 TMA / 采集 / 做统计?
TMA 采集 —— start_tma_cont(:256-265):


perf stat -I 10000 -x, -a -e "$TMA_EVENTS" --for-each-cgroup="$CGS" -o tma_cont.csv -- sleep 100000
$TMA_EVENTS 列表是 slots,topdown-retiring,topdown-bad-spec,topdown-fe-bound,topdown-be-bound,…(:60)。这些直接读硬件的 Top-down 指标。TMA 把每个流水线"槽位"分入四个 L1 桶——Retiring(有用)、Bad Speculation(浪费在误预测上)、Frontend-bound(饿于取指)、Backend-bound(卡在数据/执行上)——再分 L2 子桶(heavy-ops、branch-mispredict、fetch-latency、memory-bound)。-I 10000 每 10 秒读一次每 cgroup 的累计值,但事件全程保持安装,所以它是100% 占空比的精确普查——那些间隔只是周期性读取,不是采样。它之所以连续(而非开窗),正因为它不占 GP 计数器。回合结束时,stop_tma_cont 发 SIGINT 让 perf 刷出最后一个部分间隔(:266-268)。

每回合同时运行四个仪器(在 :484 一起启动):

#	仪器	机制	输出	用途
1	10 Hz cpu.stat pollers	每 100 ms 读 cgroup usage_usec	cpustat_scope*.tsv	精确核秒、时间线、突发
2	开窗 perf stat	8 组,每 5–10 s 窗口一个,打乱	group_*_w###.txt、windows.tsv	零多路复用事件比率(缓存缺失率、IPC、FP 混合…)
3	连续 TMA	PERF_METRICS + 固定 slots	tma_cont.csv	流水线拆分(retiring/FE/BE/bad-spec)
4	99 Hz perf record	每 cgroup 统计性栈采样	rec_scope*.data → 表	什么程序/符号/CPU(绝不用于速率)
外加第 5 个分区级 /proc/stat 见证者(:234-241),捕捉无 cgroup 认领的内核工作(writeback、IRQ),这样门禁 E11 能约束"未围隔残差"。

统计怎么做的:一切解耦——采集只是把原始文件存起来;绘图事后从存好的数据进行。开窗组文件被解析成 co-counted 比率(某事件除以它自己那些窗口里的 instructions,绝不跨组汇总——即 CLAUDE.md 里的"cross-group ratio dilution"bug)。TMA 百分比直接来自 topdown 事件。时间线/突发/核秒来自精确的 cpu.stat 序列。程序/符号归因来自 perf-record 表。

validate_glm_agents.py 及其门禁 E1–E11
validate_glm_agents.py 在采集后运行(stage_validate,:898)。它的理念(CLAUDE.md):一行 "OK" 不是证明——每个门禁都要求观测证据加上一个独立交叉核对(两个子系统互相印证)。各门禁:

门禁	证明什么	交叉核对
E1	窗口长度正确	perf 自己的 "seconds time elapsed" vs 配置的 WINSEC
E2	我们的 "CPUs utilized" 公式对	vs perf 自己的 # N CPUs utilized 注释
E3	CPU 记账可信	内核 cpu.stat 增量 vs PMU task-clock,同窗口+范围(两个独立子系统)
E4	OC 围栏纯度	perf-record comm:/agent 必须 node 主导,/toolexec 则否(lineage 或 comm 模式)
E5	agent 确实工作了(SWE)	日志里的 "STEP" 标记 + 轨迹目录存在
E6	kernel-share 是真的	PMU cycles:k/(u+k) vs 调度器独立记账
E7	不是退化的贪婪循环(SWE)	轨迹里的动作唯一性(<40% 唯一 = 退化)
E9	heavy-burst 普查	每个计数器组的窗口都必须见过 heavy burst(轮转覆盖)
E10	连续 TMA 普查有效	零多路复用,间隔上全覆盖
E11	未围隔工作被约束	分区见证者:分区忙 − 围栏总和 必须 <容量的 1%
(E8 在注释里作为突发侧守卫被提及。)一次运行在这些通过前不被信任——而且另外,图在 audit_plots.py 报 ALL MATCH 前也不被信任。

翻译完毕。三段问答对应仓库走查、逐问逐答的测量设计细节,以及 E1–E11 门禁表。如需我把 metrics.md 整体导出成一份纯中文的 Markdown 文件(方便你直接用),或反过来做中英对照版,告诉我一声即可。