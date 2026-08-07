# Report 19 — Traditional compute vs agentic work: the headline comparison (SPEC deck slide 17)

**Date of study:** 2026-08-06 → 2026-08-07 · **Author of record:** Tianrui (Jerry), with Claude Code
**Feeds:** SPEC deck slide 17 · `spec26/plots/spec_vs_agentic_metrics.png` · reports 20–21 build on this population
**Data:** SPEC `~/spec26-infra/infra/data/` (26 episodes) · agentic `local_agents/SWE_iso8/data/` (16 replays) · derived `~/spec26-infra/infra/comparison_iso8.json`

---

## 1. Key summary

Twelve microarchitectural metrics, SPEC CPU 2026 against SWE-agent × GLM-5.2, computed by **one
implementation** over both sides' raw window files and restricted to the **eight counter groups
both campaigns rotate**. Against the median SPEC benchmark, agentic work costs **15.31× the L1I
MPKI, 28.04× the kernel time, 9.56× the microcode-sequencer share, 4.16× the legacy decode and
3.41× the branch MPKI** — while **AMAT (0.99×), MLP (0.97×), L1D-load MPKI (0.81×) and DRAM read
bandwidth (0.79×) do not separate the two workloads at all**.

That asymmetry is the result. The metrics a computer architect reaches for first — the memory
ladder — carry no signal here; the separation lives entirely in **instruction supply and system
time**. Read the other way: an agent is not a memory-bound workload wearing a different hat, it
is a workload whose cost is getting instructions to the core and getting into and out of the
kernel.

The population is small and must be quoted with the result: **16 dedicated-group replays over 2
tasks** (babel/JavaScript, fmtlib/C++), so each metric rests on the **2** replays that ran its
counter group (IPC on 14). Both sides were captured on the same 8 isolated SMT-free cores at
100 ms windows, so no SMT or window-length caveat is carried.

## 2. Methodology

### 2.1 Decisions

| # | Decision | Value | Why |
|---|---|---|---|
| D1 | One implementation computes both sides | `~/spec26-infra/infra/scripts/extract_metrics.py` | If SPEC and the agent differ it must be because the workloads differ, not because two scripts implemented brMPKI slightly differently. Nothing is written into the agentic tree — it is read-only banked evidence. |
| D2 | Shared **8** counter groups only | `fpbr cache mlp fe fe_lat core_ports dram_bw priv` | SPEC rotates 11, the agent 8. IPC is total instructions over total cycles across *all* windows, so an 11-group SPEC side would sample a different part of the program (26-episode median 2.427 vs 2.418). Per-event ratios are immune — their denominators are co-counted per group — but mixing sources in one chart is indefensible regardless. |
| D3 | Agentic side = **dedicated-group replays** | 16 episodes | A replay re-executes a recorded trajectory with the model never called and gives ONE group **100 % duty** for the whole episode, instead of ~1/8 under rotation. Deterministic, free, and no model latency inside the measured interval. |
| D4 | Population selected by **provenance**, not group count | `glm_replay_swe_*` | Three *live* episodes also dedicate a whole run to one group via `GORDER_OVERRIDE` — kit method probes, model in the loop. See §2.2. |
| D5 | Both sides on the **same configuration** | measured 4–11, SMT off, `WINSEC=0.1` | Retires the SMT and window-length caveats rather than carrying them in prose. See report 20 §2.1 for what the retired caveat was worth. |
| D6 | **No whisker** on the agentic bar | individual points, marked by task | With 26 benchmarks a range says whether a gap is the suite or one outlier. With 2 episodes a "range" *is* the two points, so the figure plots them. This matters: kernel time is **21.8 %** on babel against **4.63 %** on fmtlib — a 4.7× spread inside a 2-point median. |
| D7 | Log x-axis | — | Ratios span 0.78× to 28×; a linear axis shows one bar. |

### 2.2 Verification and hazards

**Defect — population selected by the wrong key.** The shipped 2026-08-06 figure selected
replays with `len(groups)==1`, which also matched three live probe episodes
(`glm_swe_babel` run_2/4/5, groups `fe_lat`/`dram_bw`/`core_ports`). Selecting by provenance
drops them, 19 → 16, and moves two rows: **L1I MPKI 18.00× → 17.31×** and **DRAM read bandwidth
0.52× → 0.92×** on the legacy capture. Anyone holding a figure dated 2026-08-06 has those two
numbers wrong; every other row is unchanged.

**`<not counted>` on the agentic side is not a defect.** 44,141 occurrences across 11,077
windows (~4 per window) are the *harness fence idle* signal: `parse_window` sums across the two
cgroups in each file, and a fence with nothing running contributes nothing. Expected, and the
reason the agentic numbers are harness+tool combined.

**Known limitations.** (a) **2 tasks, both non-Python** — django and sympy are absent, and
per-metric `n` is 2. (b) **Contention is not retired**: SPEC runs one copy with L3 and DRAM to
itself; the agent runs a harness process and a container. (c) `AMAT_cyc` is a fixed-latency
model (5/15/50/250 cycles weighted by retired-load counts), not a measured latency. (d)
`LLC_MPKI` counts retired **demand** loads that missed L3 — not memory-boundedness.

### 2.3 Reproduction recipe

```bash
# 1. agentic capture at the SPEC configuration (~36 min, no API cost; box must be free)
cd /home/thu/InferSuite
SHORT=babel SRC=1 DATA_ROOT=$PWD/local_agents/SWE_iso8/data TIER_PREFIX=glm \
  WINSEC=0.1 PROF_GROUPS="fpbr cache mlp fe fe_lat core_ports dram_bw priv" \
  CPUS_MEASURED=4-11 CPUS_HOUSE=0-3,12-15 SKIP_K3S=1 \
  TRAJ_OVERRIDE=$PWD/local_agents/SWE_clean/data/glm_swe_babel/run_1/traj/babel__babel-15445/babel__babel-15445.local.traj \
  bash local_agents/kit/replay/replay_l3_profile.sh          # repeat with SHORT=fmtlib

# 2. derive the comparison (both sides, one implementation)
cd ~/spec26-infra/infra
SPEC_COMPARISON_OUT=$PWD/comparison_iso8.json python3 scripts/compare_spec_agentic.py data \
    ~/InferSuite/local_agents/SWE_iso8/data/*/run_*/

# 3. figure + audit dump
/home/thu/miniforge3/envs/infersuite-full/bin/python \
    ~/InferSuite/spec26/kit/plot/plot_spec_results.py
```

Costs: ~36 min of machine time for the two tasks, zero API spend (replays never call the
model). What should reproduce: the ratios and their directions, not exact per-window
trajectories. Expect ~2 % drift on episode metrics (report 18 §2.2).

### 2.4 Scripts and artifacts

| Item | Location | Role |
|---|---|---|
| Replay driver (11 or 8 passes, one group each) | `local_agents/kit/replay/replay_l3_profile.sh` | dedicated-group capture + 2 Hz command tagger |
| Replay episode + fence discovery | `local_agents/kit/campaign/run_glm_campaign.sh` (`replay_episode`, `cycle_stats`) | systemd scope for the harness, docker cgroup for the tool, one perf per window over **both** |
| Metric derivation (both sides) | `~/spec26-infra/infra/scripts/extract_metrics.py` | co-counted denominators |
| Comparison | `~/spec26-infra/infra/scripts/compare_spec_agentic.py` | shared-8 only; `SPEC_COMPARISON_OUT` selects the output file |
| Figure | [`spec26/kit/plot/plot_spec_results.py`](../../spec26/kit/plot/plot_spec_results.py) | Fig 9 → `spec_vs_agentic_metrics.png` |
| Loading + populations | [`spec26/kit/plot/spec_common.py`](../../spec26/kit/plot/spec_common.py) | `agentic_split()`, `is_replay()` |
| Which population feeds which figure | [`spec26/plots/MANIFEST.md`](../../spec26/plots/MANIFEST.md) | — |
| Audit dump (every displayed number) | `spec26/plots/values_dump.json` | key `comparison` |

## 3. Key insights (most → least important)

1. **The two workload families separate on instruction supply and system time, and *not* on the
   memory hierarchy.** L1I MPKI **15.31×**, kernel **28.04×**, microcode **9.56×**, MITE
   **4.16×**, branch MPKI **3.41×** — against AMAT **0.99×**, MLP **0.97×**, L1D **0.81×**, DRAM
   **0.79×**. A study that profiled only the memory ladder would conclude these workloads are
   indistinguishable.
2. **Kernel time is the single largest gap and the least ambiguous.** 13.2 % vs 0.47 % of
   cycles. It needs no microarchitectural interpretation: the agent is a workload that
   constantly crosses the user/kernel boundary (process spawn, file I/O, pipes), and SPEC by
   construction does not.
3. **The instruction-supply story is coherent across four independent counters.** L1I MPKI
   (L2 code reads), MITE share, microcode share and DSB share all move together and in the
   direction that means "the front end is struggling to feed the core". They come from two
   different counter groups (`fe`, `fe_lat`), so this is not one event misbehaving.
4. **DRAM bandwidth does not separate the workloads — and the earlier claim that it did was an
   artefact.** 0.79× on the matched capture. Earlier figures reported SPEC reading 14× more,
   which was task composition (Python-heavy rotation episodes) compounded by a population
   selection bug, not a property of agentic work.
5. **The 2-point medians hide real within-population spread, and the figure must show it.**
   kernel time 21.8 % (babel) vs 4.63 % (fmtlib); L1D MPKI 3.95 vs 6.92. Both tasks agree on
   *direction* for every metric, but a reader must not treat these medians as tight estimates.
6. **The comparison is only legitimate because one implementation computes both sides.** The
   restriction to eight shared groups, and the co-counted-denominator rule inside
   `extract_metrics.py`, are what make a ratio here a statement about workloads rather than
   about two people's code.
