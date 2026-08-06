# Report 18 — SPEC CPU 2026: the traditional-workload baseline (own deck, slides 1–21)

**Date of study:** 2026-08-04 → 2026-08-06 · **Author of record:** Tianrui (Jerry), with Claude Code
**Deck:** its own 21-slide deck (not the agent deck) — link in §2.5
**Related:** Report 08 (TMA-L1 signatures), Report 11 (memory hierarchy), Report 09 (frontend
instruction supply) — this report supplies the baseline those three had none for
**Capture kit:** the sibling tree `~/spec26-infra/infra`, outside this repo

---

## 1. Key summary

Every agentic finding in this study is an unanchored number: nobody has a reference for whether
an L1I MPKI of 12 is high or 11 % kernel time is unusual. So the agentic instrument was pointed
at **SPEC CPU 2026** — 26 benchmarks, **ref** inputs, 1 copy on 1 isolated SMT-free core, the
same eight certified counter groups, the same shuffled zero-multiplexing rotation, and the same
code computing every ratio. 22,413 windows of 100 ms; **26/26 episodes pass every evaluable
gate**, with 3 reported as NO PROOF rather than as passes.

It answers both questions it was built for. **The method is sound**: two instruments that share
no counter agree on the core's issue width to 0.3 % on all 26 episodes (slots/cycle 6.00–6.02
against a Golden Cove width of 6); cgroup accounting and the PMU agree to 0.005 CPUs; zero
windows were multiplexed; and benchmarks with documented characters came out with those
characters without anyone aiming at them (749.fotonik3d_r 80 % backend-bound at 11.3 GB/s, 714.cpython_r
55 % legacy-decode, 729.abc_r 49 % bad speculation). **The comparison separates cleanly**: against the
median SPEC benchmark, agentic work costs **11.96× the L1I MPKI, 4.26× the legacy decode and
23.18× the kernel time** while moving **14× less DRAM traffic**. SPEC stalls on the back end
(be 26.7 % vs fe 18.3 %); the agent stalls on the front end (fe 28.1 % vs be 23.8 %), and 19
dedicated-group replay episodes that shared no run with the rotation episodes push every one of
those directions further, not back.

One qualifier, which sharpens the result rather than weakening it: the agent is in SPEC's
**tail**, not outside its range (L1I MPKI at SPEC p73 — the compilers, 709.cactus_r and 714.cpython_r are
worse). SPEC does contain instruction-supply-starved members; they are the minority and are
frontend-bound only in phases, whereas the agent is there on every task, for the whole episode.
Only kernel time genuinely leaves the suite (p96).

## 2. Methodology

### 2.1 The capture, decision by decision

| # | Decision | Value | Why |
|---|---|---|---|
| D1 | Input size | **ref** (`refrate`) everywhere | PI decision. train/test are tuning/smoke inputs; only ref exercises the documented working sets. Verified four ways: all 26 run dirs are `refrate`, every episode records `size=refrate`, expected outputs come from `data/refrate/output`, zero references to `data/train`/`data/test` in any command file. |
| D2 | Copies / threads | **1 / 1** | SPECrate `copies` runs N independent processes side by side; the agentic comparison is per-core microarchitecture, so N>1 would measure L3/DRAM contention instead. Gated: mean fence occupancy ≤1.05 cores (measured 1.000). |
| D3 | Command line | index **0**, exactly one per benchmark | Benchmarks define up to 3 ref command lines. Running all of them blends distinct programs into one "benchmark" number. All lines are banked to `speccmds_all.txt`; the chosen index goes into `metadata.json`. |
| D4 | Window length | **100 ms** | PI decision, replacing 5 s. A full 11-group rotation drops from 55 s to 1.32 s, so every benchmark completes many rotations on its first command line — which retired all 9 command-line escalations and all 3 per-benchmark window overrides that the 5 s capture had needed. |
| D5 | Counter groups | 11, **one per window, reshuffled every cycle** | ≤4 GP events per group fits the per-thread budget, so perf never time-shares and never scales. 8 groups are byte-identical to the agentic campaign (that identity is what licenses the comparison); 3 drill groups are SPEC-only and never enter a cross-campaign figure. |
| D6 | Partition | measured **4–11** (SMT siblings offlined), house **0–3, 12–15** | Adopted, not imposed: the machine is shared and was booted into another campaign's partition. `isolcpus` was rejected outright — it removes cores from scheduler load balancing. |
| D7 | Fence | transient systemd scope under `measured.slice` | A cgroup catches every child the benchmark forks; a PID list does not. cpusets are hierarchical, so the scope must live under a top-level slice. |
| D9 | Figure labelling + ordering | full `7xx.workload_r` names; **INT block, then FP**, each by SPEC number | PI decision 2026-08-06. The published SPEC name is the identifier a reader can look up; a bare stem is ambiguous across suites. Ordering by category rather than by measured value puts the suite's own structure on the axis — and the two categories do behave differently (insight 2), which a value-sorted axis interleaves and hides. Applied to the capture, both TMA, instruction-supply, memory-ladder and per-window-grid figures. |
| D8 | Comparison population | agentic split by **instrument**, never merged | **Rotation, n=7 over 4 tasks** (babel, django, fmtlib, sympy): all 8 groups shuffled, the same instrument SPEC runs, so one episode yields a full metric card. **Replay, n=19 over 2 tasks** (babel, fmtlib): one group per whole deterministic episode at 100 % duty, no model in the loop. Merging them would mix two instruments in one median. |
| D10 | Headline comparison figure uses **replays only** | `spec_vs_agentic_metrics` | PI decision 2026-08-06: the replay measures its group at 100 % duty on a deterministic, model-free episode, which is the cleanest per-metric agentic number available. Cost, stated on the slide: only 2 tasks, and each metric rests on the **2–3** replays that ran its group (IPC 17), not on all 19 — so the figure prints that count per row and plots the individual episode points instead of a whisker. It also shifts the result: instruction supply strengthens (L1I 11.96× → 18.00×, kernel 23.18× → 27.27×) and DRAM weakens (0.07× → 0.52×), the latter being task composition — fmtlib compiles C++ and moves real memory traffic where the Python rotation tasks do not. |

### 2.2 Verification, and the defects it caught

Thirteen gates per episode; a gate that cannot be evaluated reports **NO PROOF** and is never
counted as a pass. Suite-wide: 0 multiplexed windows, 2,026 distinct rotation orders over 2,026
complete cycles, co-counted denominators 10.9–11.1× smaller than the episode total (exact match
on all 26), ISO-PROOF max busy 0.0 %, cpu.stat-vs-PMU median |ΔCPUs| ≤ 0.005, unfenced residual
≤ 0.03 % of partition capacity.

**Three NO PROOFs (734.vpr_r, 735.gem5_r, 772.marian_r).** Their specdiff targets are built by a post-processing
step that lives outside every ref command line, so running one line directly — the whole design
— never produces them. Output correctness is *untestable*, not failed; exit status was 0 and the
counters are as clean as the rest. Reported as missing rather than silently passed.

Defects found and fixed during the study, each of which would have shipped a wrong number:

- **Cross-group denominator dilution (~11×).** An event is counted in ~1/11 of the episode;
  dividing by instructions summed over *all* windows understates every rate by the group count.
  Fixed by co-counting per **window** — a window where the event was unscheduled contributes to
  neither the numerator nor its denominator. (Found for real at ~8× in the agentic campaign.)
- **Never-measured read as zero.** Metrics whose group never got a window returned `0.0`, which
  inverted the DRAM finding into "SPEC issues no DRAM reads". They now return **undefined**.
- **Dirty SPEC run directories.** Run dirs are reused and some benchmarks *append*: `737.gmsh_r`
  produced a 15-line `choi.val` against a 5-line reference — exactly 3× — after three runs. Every
  episode now deletes only SPEC-declared outputs (`-o`/`-e` targets, compare targets,
  `.cmp`/`.mis`) first; inputs are never touched.
- **False "pass" on corrupted output.** specdiff died on a missing `$ENV{SPEC}` and left an empty
  `.cmp` that scored as clean. An empty or missing `.cmp` is now an error, never a pass.
- **`slots/cycle` biased 10 % high (fixed 2026-08-06).** The `priv` group spends its GP slots on
  `cycles:u`/`cycles:k` instead of plain `cycles`, so summing `v["cycles"]` dropped one group of
  11 from the denominator: the gate reported **6.62** against a true **6.01**. It passed either
  way (band 3.5–8.5), but the number *is* the cross-instrument evidence. All 26 now read 6.00–6.02.
- **Restore path destroyed the operator's partition.** An early isolation-restore reset the
  system slices to "all online CPUs" instead of what it had snapshotted. It now snapshots and
  restores the real values, per-CPU (governors differ per core; offline CPUs reject writes).

**Known limitations.** (a) **Counting duty is 83.3 %**: re-arming perf costs a fixed ~22 ms per
window, so a 100 ms window occupies ~122 ms of wall (measured pitch 0.121–0.125 s across the
suite). The dead time sits between windows and is uncorrelated with program phase, and the
continuous TMA census is unaffected (100 % duty, zero GP counters) — but ~17 % of wall is
unobserved by the windowed groups. **A corollary worth stating because it is asked every time:**
an episode does not yield `wall / WINSEC` windows. Each one also has a lead-in before the first
window is armed (median 0.11 s) and a teardown after the benchmark exits (median 1.43 s — TMA
flush, poller and record stop, scope stop) that carry no windows, so
`windows = (wall − lead_in − teardown) / pitch`. Every episode lands at **72–82 %** of the naive
figure (median 80 %); short ones sit lowest because they pay the fixed teardown out of a small
budget. Worked example, 729.abc_r: (11.74 − 0.16 − 1.00) / 0.123 = **86**, where 11.74 / 0.1
would suggest 117. The per-episode terms are banked in `values_dump.json` under `capture`. (b) **SMT and contention**
differ between campaigns (§2.4). (c) The agentic rotation population is **7 episodes over
4 tasks** — small. (d) `AMAT_cyc` is a fixed-latency model (5/15/50/250 cycles), not a measured
latency.

**Reproducibility control.** Two independent full-suite captures at 100 ms (`data/` and
`data_100ms_dirtyrundirs/`, both banked) differ by a median **2.12 %** across 11 metrics × 26
benchmarks — 0.30 % for the steadiest benchmark (706.stockfish_r, 678 windows) and 13.8 % for the
noisiest (734.vpr_r, 329 windows). Short, phase-heavy episodes vary most, which is the expected shape.

### 2.3 Reproduction recipe

Capture (sibling tree; ~55 min of benchmark time, no API cost, requires the isolated partition):

```bash
cd ~/spec26-infra/infra
./scripts/run_spec_campaign.sh preflight        # env + ISO-PROOF checks, no state change
./scripts/run_spec_campaign.sh campaign         # 26 episodes, WINSEC=0.1, SPEC_SIZE=refrate
python3 scripts/extract_metrics.py data/*/      # metrics.json per episode
python3 scripts/validate_spec.py  data/*/       # 13 gates; exit 0 = all evaluable gates pass
python3 scripts/compare_spec_agentic.py data \
        ~/InferSuite/local_agents/SWE_clean/data/*/run_*/     # writes comparison.json
```

Figures, galleries and deck (this repo; matplotlib is **not** in the repo `.venv`):

```bash
PY=/home/thu/miniforge3/envs/infersuite-full/bin/python
$PY spec26/kit/plot/plot_spec_results.py        # 13 figures + values_dump.json
$PY spec26/kit/plot/plot_spec_windows.py        # ~1.9k per-window PNGs (outside the repo)
$PY spec26/kit/plot/build_spec_gallery.py       # 26 self-contained HTML galleries
DECK_OUT=~/spec26-infra/infra/plots/spec_deck.html $PY spec26/kit/plot/build_spec_deck.py
bash scripts/sync_plots.sh                      # refresh plots/spec26/
```

What should reproduce: the phenomena, the shares and the directions — not the exact per-window
trajectories. Expect ~2 % drift on episode metrics (§2.2) and more on short benchmarks.

### 2.4 Scripts and artifacts

| Item | Location | Role |
|---|---|---|
| Capture kit | `~/spec26-infra/infra/scripts/run_spec_campaign.sh` | staged runner, isolation, fencing, rotation, 4 instruments |
| Config | `~/spec26-infra/infra/campaign.conf` | pinned partition, `WINSEC=0.1`, `SPEC_SIZE=refrate`, gates |
| Metrics | `~/spec26-infra/infra/scripts/extract_metrics.py` | co-counted denominators; the one implementation both campaigns use |
| Gates | `~/spec26-infra/infra/scripts/validate_spec.py` | 13 gates; NO PROOF is not a pass |
| Output check | `~/spec26-infra/infra/scripts/verify_output.py` | runs SPEC's own specdiff |
| Run-dir hygiene | `~/spec26-infra/infra/scripts/clean_rundir.py` | deletes only SPEC-declared outputs |
| Comparison | `~/spec26-infra/infra/scripts/compare_spec_agentic.py` | shared-8 only; agentic tree read-only |
| Loading + style | [`spec26/kit/plot/spec_common.py`](../../spec26/kit/plot/spec_common.py) | episode + per-window layers, duty, slots/cycle, palette |
| Thesis figures | [`spec26/kit/plot/plot_spec_results.py`](../../spec26/kit/plot/plot_spec_results.py) | the 13 figures + `values_dump.json` |
| Per-window figures | [`spec26/kit/plot/plot_spec_windows.py`](../../spec26/kit/plot/plot_spec_windows.py) | 36 metrics × 26 benchmarks, distribution + timeline |
| Galleries | [`spec26/kit/plot/build_spec_gallery.py`](../../spec26/kit/plot/build_spec_gallery.py) | one self-contained HTML page per benchmark |
| Deck | [`spec26/kit/plot/build_spec_deck.py`](../../spec26/kit/plot/build_spec_deck.py) | the 21-slide deck, figures inlined |
| Figure manifest | [`spec26/plots/MANIFEST.md`](../../spec26/plots/MANIFEST.md) | which population feeds each figure; reference scales; caveats |
| Tree overview | [`spec26/README.md`](../../spec26/README.md) | what lives where, and why data stays outside the repo |
| Curated view | `plots/spec26/` | synced by `scripts/sync_plots.sh` |

**Standing caveats, to travel with every cross-campaign number.** *SMT*: agentic is SMT-ON on 20
logical CPUs, SPEC is SMT-OFF on 8 physical cores — cycle-normalised metrics (IPC, port
utilisation, frontend bandwidth shares) cross that boundary badly; per-instruction rates survive
it far better. *Contention*: SPEC runs 1 copy with L3 and DRAM to itself; the agentic workload
ran many concurrent processes and did contend. *`LLC_MPKI` is a demand-miss metric, not a
memory-boundedness metric* — `782.lbm_r` streams 4.3 GB/s at an LLC MPKI of 0.01 because the
prefetcher won; use `DRAM_read_GBs` or TMA `mem_bound`.

### 2.5 Published artifacts

| Artifact | Link |
|---|---|
| SPEC CPU 2026 — the traditional-workload baseline (the deck, **21 slides**) | https://claude.ai/code/artifact/5a6ac70c-b2e4-4969-b2f0-1ec0a8de6e78 |
| Per-window gallery — 749.fotonik3d_r (most memory-bound) | https://claude.ai/code/artifact/38a39910-5629-4073-b02d-7dda179c1bee |
| Per-window gallery — 782.lbm_r (streaming; the demand-miss caveat) | https://claude.ai/code/artifact/91f043be-d23f-45cc-911c-9284c77941ba |
| Per-window gallery — 723.llvm_r (most frontend-bound) | https://claude.ai/code/artifact/3f7a6f76-cb54-45dd-bd34-85b5b4eb2a4c |
| Per-window gallery — 714.cpython_r (interpreter; closest to an agent harness) | https://claude.ai/code/artifact/616a5aec-782e-4fee-a1e7-55c547e35432 |
| Per-window gallery — 709.cactus_r (extreme instruction footprint) | https://claude.ai/code/artifact/0a46c434-84f0-4c20-83f0-bd5c391dff98 |
| Per-window gallery — 750.sealcrypto_r (compute-dense, IPC 4.15) | https://claude.ai/code/artifact/10499fe5-fd0b-41f1-bed7-58ddb8550f16 |
| Per-window gallery — 729.abc_r (branchy; 49 % bad speculation) | https://claude.ai/code/artifact/d0a0ff27-e08a-42e1-9b80-7fd786925197 |
| Per-window gallery — 765.roms_r (longest episode, 2,658 windows) | https://claude.ai/code/artifact/89c20c12-0ee5-4eed-a851-f8bb43a9ab4f |

Eight galleries were published, chosen to span the behavioural space (memory-bound, streaming,
frontend-bound, interpreter, instruction-footprint, compute-dense, speculation-bound, longest).
**All 26 are built locally** at `~/spec26-infra/infra/plots/windows/gallery_<bench>.html` and any
of them can be published on request.

## 3. Key insights (most → least important)

1. **The two workload families separate on instruction supply and system time, not on data.**
   Agentic work costs **11.96×** the L1I MPKI, **4.26×** the legacy decode, **8.29×** the
   microcode and **23.18×** the kernel time of the median SPEC benchmark, while moving **14×
   less** DRAM traffic and showing an indistinguishable AMAT (0.99×) and MLP (1.05×). SPEC is a
   data-movement suite; agentic work is an instruction-supply and system-call workload. The
   memory-hierarchy metrics everyone reaches for first are exactly the ones that do not separate.
2. **The two SPEC categories are themselves different machines — which is why the figures are
   ordered INT-then-FP.** Branch prediction is the sharpest separation in the whole capture:
   integer median **2.36** mispredicts per 1000 instructions against
   **0.059** for floating-point, a **40×**
   gap, and TMA bad speculation follows it at **14.5 % vs
   1.5 %** (10/14 integer
   benchmarks lose more than a tenth of their slots to it, against
   3/12 FP). The FP block trades that for the memory system:
   backend-bound **42.0 % vs 19.4 %**,
   DRAM read bandwidth **3.45 vs 0.87 GB/s**
   (6/12 FP benchmarks exceed 4 GB/s; **0/14**
   integer ones do). Integer code also carries the harder instruction-supply problem
   (L1I MPKI 3.9 vs 0.53,
   frontend-bound 25.6 % vs 8.9 %) —
   with two loud FP exceptions, 709.cactus_r and 748.flightdm_r. IPC, notably, does **not**
   separate them (2.35 vs 2.45): the categories
   reach similar throughput by failing in different places.
3. **The direction holds under an independent instrument.** The 19 dedicated-single-group replay
   episodes never shared a run with the 7 rotation episodes, and they push every direction
   further: L1I MPKI 17.70 vs 11.76, kernel 12.85 % vs 10.92 %, MITE 34.98 % vs 31.53 %, TMA
   frontend-bound 34.8 % vs 28.1 %. Two instruments, one conclusion.
4. **The agent sits in SPEC's tail, not outside its range — and that is the sharper claim.**
   L1I MPKI at SPEC p73 (7/26 worse), MITE at p73, DSB at p27. SPEC *does* contain
   instruction-supply-starved members — 723.llvm_r, 721.gcc_r, 709.cactus_r, 714.cpython_r — but they are the minority
   and are frontend-bound only in phases. Only kernel time genuinely leaves the suite (p96, 1/26
   higher). Ratios against a median flatter; the percentile is the defensible statistic.
5. **Agentic behaviour is uniform where SPEC behaviour is diverse.** On the TMA plane every
   agentic episode lands in one tight cluster (fe 26–36 %, be 15–30 %) while the 26 SPEC
   benchmarks spray across the whole space (fe 0.5–40 %, be 2.5–80 %). Medians alone hide this,
   and it is arguably the strongest argument that "agentic workload" names a real, single
   microarchitectural regime.
6. **The method validates: known characters came out as known characters.** Nothing was targeted
   — every row is the first ref command line at index 0 under the same rotation. 749.fotonik3d_r
   IPC 0.77 / 80 % backend / 55 % memory-bound / 11.3 GB/s; 765.roms_r 70 % backend at 11.3 GB/s; 782.lbm_r
   4.3 GB/s but LLC MPKI 0.01 and 45 % core-bound; 723.llvm_r L1I MPKI 21.7 with 40 % frontend-bound;
   714.cpython_r 55 % MITE and 3 % backend-bound; 750.sealcrypto_r IPC 4.15 with 74 % retiring; 729.abc_r 49 % bad
   speculation.
7. **Two instruments that share no counter agree on the machine itself.** TMA slots ÷ windowed
   cycles = **6.00–6.02** on all 26 episodes against the Golden Cove issue width of 6 — a check
   that uses no metric value at all, and the one that caught the 10 % `priv`-group denominator
   bias in the validator (§2.2).
8. **The episode value is a sum over states, not a description of one.** 723.llvm_r's episode IPC of
   1.61 is assembled from windows spanning 0.02–3.54, 749.fotonik3d_r's 0.77 from 0.10–3.06, while 782.lbm_r
   is genuinely one state (2.80 from 1.98–3.99). This is also why a per-window median is not the
   episode value: the latter is a ratio of sums, weighted by where the cycles went.
9. **`LLC_MPKI` reverses the suite's memory ranking if read as memory-boundedness.** 782.lbm_r reads
   0.01 while streaming 4.3 GB/s; 749.fotonik3d_r reads 18.0 at 11.3 GB/s. It measures how often the
   prefetcher failed, not how much memory traffic exists.
