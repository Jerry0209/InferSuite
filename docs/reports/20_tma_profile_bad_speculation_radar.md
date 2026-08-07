# Report 20 — TMA profile: where the slots go, and bad speculation on its own axis (SPEC deck slide 18)

**Date of study:** 2026-08-07 · **Author of record:** Tianrui (Jerry), with Claude Code
**Feeds:** SPEC deck slide 18 · `spec26/plots/spec_vs_agentic_tma.png` · the deck's caveat slide
**Data:** SPEC `~/spec26-infra/infra/data/*/tma_cont.csv` (26) · agentic matched `local_agents/SWE_iso8/` (16) · agentic legacy `local_agents/SWE_clean/` (16)
**Prerequisite:** report 19 (population and configuration)

---

## 1. Key summary

All four Top-down Microarchitecture Analysis Level-1 buckets on one radar, because the question
is the **shape** of the profile rather than its composition. TMA is the cleanest cross-campaign
view in the study: it reads the PERF_METRICS register and the fixed slots counter, consumes
**zero general-purpose counters**, and therefore runs continuously at 100 % duty alongside
whichever windowed group is live.

Median over episodes, share of pipeline slots:

| | Retiring | Frontend-bound | Bad speculation | Backend-bound |
|---|---|---|---|---|
| **SPEC CPU 2026** (26) | 36.0 % | 18.3 % | **10.0 %** | 26.7 % |
| **agentic, matched config** (16) | 29.9 % | **32.7 %** | **15.4 %** | 22.0 % |
| agentic, legacy SMT-ON (16) | 31.3 % | 34.1 % | 15.8 % | 18.3 % |

SPEC stalls on the back end; the agent stalls on the **front end** (1.8×) and additionally
**mis-speculates 1.5× more**. Bad speculation earns the axis the mentor asked for: it is a
second, independent front-end cost, and it does not follow from frontend-bound — the two are
different mechanisms (fetch cannot deliver, versus fetch delivered the wrong path).

This study also **prices the retired SMT caveat**. The legacy row is the same replays under
SMT-ON on 20 logical CPUs at 2 s windows. The TMA shape barely moves (frontend-bound 34.1 →
32.7, bad speculation 15.8 → 15.4), while **IPC moves 1.591 → 1.890, +18.8 %**. So the TMA
conclusions never depended on the SMT caveat and the IPC ones did — which is exactly the kind of
statement that used to be a hedge in prose and is now a measurement.

## 2. Methodology

### 2.1 Decisions

| # | Decision | Value | Why |
|---|---|---|---|
| D1 | Radar, not stacked bars | 4 axes | A stack forces the eye to compare segment lengths at different offsets. The claim is about profile shape, so give each bucket its own axis. |
| D2 | **Include bad speculation** | 4th axis | Mentor's request 2026-08-07. It earned it: 1.5×, and mechanistically independent of frontend-bound. |
| D3 | Radial scale fixed 0–40 % | not auto-scaled | An auto-scaled radar makes any two profiles look equally different. 40 % clears the largest value (36.0). |
| D4 | Legacy capture drawn as a dashed outline | no fill, no value labels | It is a *control*, not a third result. Filling it would imply three findings. |
| D5 | Per-episode scatter beside the radar | frontend-bound × bad speculation | Medians can hide a bimodal suite. This panel is also where the honest version of the bad-speculation claim lives (§3.2). |
| D6 | TMA from the **continuous census**, not the windowed groups | `perf stat -I 10000 -a --for-each-cgroup ... -e slots,topdown-*` | Zero GP counters ⇒ 100 % duty ⇒ no duty-cycle correction, and no interaction with the rotation. |

**How the numbers are derived.** `load_tma()` sums each `topdown-*` event over the census, then
normalises by the sum of the four L1 buckets. Level-2 siblings are computed as remainders
(`core_bound = be_bound − mem_bound`), exactly as the agentic kit does — see report 18 for the
Level-2 discussion.

### 2.2 Verification and hazards

**The four axes are per-episode medians and do NOT sum to 100 %** (SPEC: 91.1). Each axis must
be read on its own. This is stated on the slide and in the values dump, because a radar
*looks* like a composition.

**The bad-speculation claim needs the scatter to stay honest.** The agent's 15.4 % is high but
not extreme for the suite: **`729.abc_r` loses 49 % of its slots to mis-speculation**, and six
more SPEC benchmarks exceed 20 %. What isolates the agent is the *combination* — high
frontend-bound **and** high bad speculation simultaneously — a corner it shares only with
`706.stockfish_r` and `723.llvm_r`. SPEC's speculation-heavy members (`777.zstd_r`,
`707.ntest_r`, `731.astcenc_r`) pay that cost while feeding the front end comfortably.

**Cross-instrument check that the census is sane.** TMA `slots` ÷ windowed `cycles`
(duty-corrected) = **6.00–6.02** on all 26 SPEC episodes against the Golden Cove issue width of
6. Two instruments sharing no counter. This check caught a 10 % bias in the validator (report 18
§2.2): the `priv` group counts `cycles:u`/`cycles:k` instead of plain `cycles`, so a naive sum
dropped one group of 11 and read 6.62.

**Known limitations.** (a) Agentic n=16 over **2 tasks**; the four TMA values per episode come
from the census, so unlike the windowed metrics every one of the 16 contributes to every axis.
(b) Contention is not retired. (c) The legacy control differs in *two* variables at once (SMT
and window length), so it prices the pair, not SMT alone.

### 2.3 Reproduction recipe

```bash
# Prerequisite: the captures from report 19 §2.3 exist.
cd ~/spec26-infra/infra
SPEC_COMPARISON_OUT=$PWD/comparison_iso8.json python3 scripts/compare_spec_agentic.py data \
    ~/InferSuite/local_agents/SWE_iso8/data/*/run_*/     # matched  -> comparison_iso8.json
python3 scripts/compare_spec_agentic.py data \
    ~/InferSuite/local_agents/SWE_clean/data/*/run_*/    # legacy   -> comparison.json

/home/thu/miniforge3/envs/infersuite-full/bin/python \
    ~/InferSuite/spec26/kit/plot/plot_spec_results.py    # Fig 10 -> spec_vs_agentic_tma.png
```

`spec_common.py` reads the matched file by default (`SPEC_COMPARISON`) and the legacy one via
`SPEC_COMPARISON_LEGACY`; both are env-overridable. Cost: seconds, from banked data.

### 2.4 Scripts and artifacts

| Item | Location | Role |
|---|---|---|
| Continuous TMA census | `~/spec26-infra/infra/scripts/run_spec_campaign.sh` (`start_tma_cont`) and `local_agents/kit/campaign/run_glm_campaign.sh` | installs `slots` + `topdown-*`, `-I 10000`, zero GP counters |
| TMA parsing + L1/L2 normalisation | `~/spec26-infra/infra/scripts/extract_metrics.py` (`load_tma`) | one implementation, both campaigns |
| Cross-instrument gate | `~/spec26-infra/infra/scripts/validate_spec.py` (gate E10) | slots/cycle vs issue width, duty-corrected |
| Radar figure | [`spec26/kit/plot/plot_spec_results.py`](../../spec26/kit/plot/plot_spec_results.py) | Fig 10 |
| Populations (matched vs legacy) | [`spec26/kit/plot/spec_common.py`](../../spec26/kit/plot/spec_common.py) | `comparison()`, `comparison_legacy()` |
| Audit dump | `spec26/plots/values_dump.json` | key `tma_compare` |

## 3. Key insights (most → least important)

1. **The agent is frontend-bound where SPEC is backend-bound, and the gap is large.** 32.7 % vs
   18.3 % frontend-bound; 22.0 % vs 26.7 % backend-bound. This is the TMA restatement of report
   19's instruction-supply result, from a completely different instrument (PERF_METRICS, no GP
   counters), which is why the two together are stronger than either alone.
2. **Bad speculation is a second, independent front-end cost: 15.4 % vs 10.0 %.** It deserves its
   own axis because it is a different mechanism from frontend-bound — the front end delivering
   the *wrong* instructions rather than failing to deliver any. Adding it changes the story from
   "the agent can't fetch fast enough" to "the agent can't fetch fast enough *and* frequently
   fetches the wrong path".
3. **The retired SMT caveat is now priced, and it mattered only where we suspected.** IPC
   1.591 → 1.890 (**+18.8 %**) once the sibling thread stops stealing issue slots; TMA shape
   essentially unchanged. Every TMA conclusion drawn under the old configuration survives; every
   IPC number from it was ~19 % low.
4. **Retiring is lower for the agent (29.9 % vs 36.0 %) but that is a consequence, not a
   finding.** Slots lost to the front end and to mis-speculation have to come from somewhere.
   Quote it as context, never as an independent result.
5. **The suite's spread dwarfs the agent's position on any single axis.** SPEC bad speculation
   runs 0 % to 49 %; the agent's 15.4 % sits inside that. The separation is in *which corner of
   the plane* the agent occupies, which is why the scatter panel ships alongside the radar.
6. **The census is the most trustworthy instrument in the study.** Zero GP counters means it
   never competes with the rotation, never multiplexes, and covers 100 % of the episode where
   the windowed groups cover ~83 %.
