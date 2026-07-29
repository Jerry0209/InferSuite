# Report 02 — TMA Level-2 drill: latency vs bandwidth, core vs memory (deck slide 18)

**Date of study:** 2026-07-28 · **Author of record:** Tianrui (Jerry), with Claude Code
**Deck slides:** 18 (builds on 14–16, the TMA L1 comparisons)
**Longer prose version:** [`../handwritten_notes/analysis.md`](../handwritten_notes/analysis.md), Part 4 ("Level-2 drill" subsection)

---

## 1. Key summary

The mentor's TODO — "which commands are frontend-bound vs backend-bound, and split those
buckets further" — turned out to require **no new capture for Level 2**: every campaign
episode already banks a continuous top-down census whose event list includes the two
direct Level-2 children (`topdown-fetch-lat`, `topdown-mem-bound`), from which all eight
L2 sub-buckets derive. Reading them out settled three questions: **scikit-learn's backend
is core-bound (28.3 % of slots) not memory-bound (6.1 %)** — DRAM ruled out, consistent
with floor-level LLC MPKI and AMAT; **astropy and sympy split their frontend almost evenly
between fetch-latency and fetch-bandwidth** (~17/17 and ~16/15) — the large-code-footprint
signature; and, via a window↔activity join on banked logs, **astropy's episode-level L1I
MPKI of 24 is the test suite itself** (MPKI ≈ 28 in build/test windows carrying 80 % of
instructions, vs ≈ 8 in short-command windows). A wording correction was applied to slide
14 ("memory/execution limited" → core-bound, execution ports/FMA).

## 2. Methodology

### 2.1 Where the Level-2 numbers come from (no new capture)

Each episode runs a **continuous whole-episode TMA census**
(`run_glm_campaign.sh`, `TMA_EVENTS` at line ~60; launched by `start_tma_cont()`):

```
slots, topdown-retiring, topdown-bad-spec, topdown-fe-bound, topdown-be-bound,   # L1
topdown-heavy-ops, topdown-br-mispredict, topdown-fetch-lat, topdown-mem-bound   # L2 children
```

Key properties a reproducer must understand:

- These use the **PERF_METRICS MSR + fixed slots counter → zero general-purpose counters**,
  which is why the census runs at 100 % duty alongside the windowed GP groups without
  multiplexing (the dry-run gate verifies coexistence). The `-I 10000` is a *read* interval,
  not sampling — events stay installed between reads; counts are exact.
- Intel's PERF_METRICS provides only L1+L2; the four remaining L2 buckets are **parent
  remainders**: fetch-bandwidth = FE − fetch-lat; core-bound = BE − mem-bound;
  light-ops = retiring − heavy-ops; machine-clears = bad-spec − br-mispredict.
- Derivation is done by the kit plotter (`plot_glm_results.py`, `TMA_SPLIT` table ~line 791)
  and dumped to `values_dump.json` as `tma_l2_tool` / `tma_l2_harness`. **The dump is a bare
  8-element list; the order is the TMA_SPLIT order:**
  `[ret·light, ret·heavy, fe·fetch-lat, fe·fetch-bw, bad·mispredict, bad·clears,
  be·memory, be·core]`. Document this order wherever the numbers are re-used.

### 2.2 Key decisions

1. **Same plotter over both campaigns** (ours and Mohamad's archived
   `certified_glm_40min`), one featured episode per task, specs differing only in `data`
   path — so every cross-campaign difference is a data difference, not code drift.
2. **Featured runs**: our clean runs (scikit r1, astropy r2, sympy r2, django r2 tagged
   looped); Mohamad's run-1 set (his figures' convention). Never pool runs.
3. **Per-command L1I attribution without timestamps**: `agent.log` STEP banners carry no
   wall-clock and the traj has only per-step `execution_time`, so the join anchor is the
   **epoch-stamped instrumentation itself**: each `fe_lat` counter window has its epoch
   bracket in `windows.tsv`, and the tool fence's 10 Hz `cpu.stat` series identifies
   activity. Windows overlapping a **contiguous tool burst ≥ 3 s** were classed
   "build/tests" (only test/build commands run that long — the same insight behind the
   kit's 5 s anchor pairing); windows with tool instructions but no long burst =
   "short commands"; windows with < 1 M tool instructions = "quiet" (excluded from MPKI).
   Per-class MPKI = Σ`l2_rqsts.all_code_rd` / Σ`instructions` over that class's windows
   (co-counted — never divide by another group's instructions).
4. **Naming honesty**: the heatmap metric is computed from `l2_rqsts.all_code_rd` (code
   reads arriving at L2 = L1I misses), so reports call it *code-read MPKI / L1I-pressure
   proxy*, not a literal L1I-miss count.

### 2.3 Reproduction recipe

```bash
# L2 table for any campaign: point a spec at its data, run the plotter, read the dump
PLOT_SPEC=<spec.json> python3 local_agents/scripts/glm/plot_glm_results.py
python3 -c "import json; d=json.load(open('<out>/values_dump.json'));
print(d['scikit-learn (Python)']['tma_l2_tool'])"   # order documented above
```

Per-run L2 (used for the all-runs figure, slide 16) = one single-run spec per episode,
run the plotter, harvest `tma_l2_*` — the same pattern later productionized as
per-window analysis in Report 03's tooling. The window↔burst L1I join logic of §2.2(3)
is superseded by the 2 Hz process tagger of Report 03 (`analyze_l3_windows.py`), which
reproduces and refines it; use that script going forward.

### 2.4 Scripts and artifacts

| Item | Location | Role |
|---|---|---|
| `run_glm_campaign.sh` (`TMA_EVENTS`, `start_tma_cont`) | `local_agents/scripts/glm/` | census capture (already part of every episode) |
| `plot_glm_results.py` (`TMA_SPLIT`) | same dir | L2 derivation + `glm_tma_l2.png` + values dump |
| `tma_cont.csv` | every `run_*/` dir | raw census (10 s interval rows per fence) |
| Mohamad-side figures | `local_agents/superseded_40min/plots/compare/moh_featured/` | same plotter over his archive |
| `analyze_l3_windows.py` | `local_agents/scripts/glm/` | successor of the window↔command join |

## 3. Key insights (most → least important)

1. **scikit-learn/OpenBLAS is core-bound, not DRAM-bound**: BE 34 % = core 28.3 + memory
   6.1; with LLC MPKI 0.01 and AMAT ≈ 5.1 cyc at the scale floor, main memory is excluded
   at Level 2 (Report 04 later confirms at Level 3: the 6 % memory is L1-bound, DRAM-bound
   = 0.0 %). Retiring·heavy = 22 % — the vector/FMA fingerprint.
2. **astropy and sympy split frontend-bound ≈ 50/50 between fetch-latency and
   fetch-bandwidth** — simultaneously starved (L1I misses) and under-supplied (DSB→MITE),
   the classic oversized-instruction-footprint signature; plus 14–18 % branch-mispredict.
3. **astropy's L1I pressure is the test suite, time-resolved**: build/test windows carry
   ~80 % of tool instructions at MPKI ≈ 28 (peak 42); short-command windows sit at ≈ 8.
   The episode average (24) is a pytest-weighted number.
4. **The L2 splits reproduce across campaigns** on clean runs to within a few points —
   consistent with the broader finding that TMA shares are the most reproducible layer of
   the whole study.
5. **Instrumentation lesson**: the census already contained L2 — before designing new
   captures, read what the existing events imply. (The exact opposite held for L3, which
   did require new groups — Report 04.)
