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


>>>>>> Could you explain the structure of this repository? What does each file do? I want to know, for example, when I run the cd ~/InferSuite/local_agents/scripts/glm

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

The GLM agent kit — local_agents/scripts/glm/
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

cd ~/InferSuite/local_agents/scripts/glm
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


PLOT_SPEC=local_agents/superseded_40min/plot_spec.json python3 local_agents/scripts/glm/plot_glm_results.py
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
