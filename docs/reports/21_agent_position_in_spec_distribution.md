# Report 21 — Where the agent sits in the SPEC distribution: ranks, not ratios (SPEC deck slide 19)

**Date of study:** 2026-08-06 → 2026-08-07 · **Author of record:** Tianrui (Jerry), with Claude Code
**Feeds:** SPEC deck slide 19 · `spec26/plots/spec_vs_agentic_frontend.png` · the deck's takeaway slide
**Data:** SPEC `~/spec26-infra/infra/data/` (26, shared-8 reload) · agentic matched + legacy replays
**Prerequisite:** report 19 (population, configuration, the ratios this report qualifies)

---

## 1. Key summary

Report 19 quotes ratios against the SPEC **median**. A ratio against a median flatters whenever
the reference distribution is wide — and SPEC's are enormous: L1I MPKI spans **0.031 to 93.3**,
a factor of 3,000. This study asks the harder question: **where in the distribution does the
agent actually fall?**

| Metric | SPEC median | agentic | agent's SPEC percentile | SPEC benchmarks more extreme |
|---|---|---|---|---|
| L1I MPKI | 0.98 | 15.05 | **p77** | 6 / 26 |
| MITE (legacy decode) % | 7.40 | 30.81 | **p65** | 9 / 26 |
| DSB (uop cache) % | 92.51 | 67.65 | **p27** | 7 / 26 |
| kernel time % | 0.47 | 13.21 | **p96** | **1 / 26** |

So the honest claim is **not** "the agent is outside the suite". It is: on instruction supply
the agent sits in SPEC's **tail** — the corner occupied by the compilers (`723.llvm_r`,
`721.gcc_r`), the simulator (`735.gem5_r`), the interpreter (`714.cpython_r`) and
`709.cactus_r`. Only **kernel time** genuinely leaves the suite.

This sharpens the finding rather than weakening it. SPEC *does* contain
instruction-supply-starved members, but they are the minority and they are frontend-bound only
in phases (report 18, insight 7: `723.llvm_r`'s per-window IPC spans 0.02–3.54). The agent is
there **on every task, in every episode, for the whole episode** — and it is there while also
paying 28× the kernel time, which no SPEC benchmark does.

## 2. Methodology

### 2.1 Decisions

| # | Decision | Value | Why |
|---|---|---|---|
| D1 | Report a **rank**, not only a ratio | percentile + count more extreme | A ratio against a median is uninterpretable without the reference spread. With SPEC L1I MPKI spanning 3,000×, "15×" and "p77" are both true and tell opposite stories about how unusual the agent is. |
| D2 | Direction-aware "more extreme" | `<` for DSB, `>` for the rest | DSB coverage is good when high; the others are costs. A single comparison operator would score DSB backwards. |
| D3 | Box + all 26 points, not a summary box | strip over box | 26 is few enough to draw every benchmark. The reader can see that the SPEC "distribution" is a handful of clusters, not a smooth density. |
| D4 | Log axis for L1I MPKI and kernel % | — | Both span 3 decades across the suite. |
| D5 | Both agentic captures overlaid | ★ matched, ○ legacy | Shows that the agent's *position in the distribution* is robust to the configuration change, even where the absolute value moved. |
| D6 | Reject the earlier framing | — | The first version of this figure was titled "the agent is outside the suite, not at its edge" and printed "7/7 agentic episodes inside the SPEC range" beneath it — a title contradicted by its own annotation. Corrected before publish. |

### 2.2 Verification and hazards

**The figure originally shipped a self-contradicting claim.** Title asserted "outside the
suite"; the per-panel annotation computed 7/7 episodes *inside* the SPEC range. The metric was
right, the framing was wrong. Fixed by replacing "inside the range" (nearly always true, hence
uninformative) with the percentile and the count of more-extreme benchmarks.

**Percentiles are computed on the shared-8 SPEC reload**, not the 11-group `metrics.json`, so
this report's SPEC side is identical to report 19's. Using the 11-group values would shift IPC
and nothing else, but the two must not be mixed in one claim.

**Known limitations.** (a) With **n=2** agentic episodes per metric, "the agentic median" is the
mean of two numbers; the percentile of a 2-point median is a coarse statistic. It is reported
because it is *less* misleading than the ratio alone, not because it is precise. (b) 26 is a
small reference distribution — a percentile has a resolution of ~4 points. (c) Both tasks are
non-Python. (d) The suite is not a random sample of software; SPEC is curated, so "p77 of SPEC"
means p77 of a deliberately diverse benchmark suite, not of software in general.

### 2.3 Reproduction recipe

```bash
# Prerequisite: captures + comparison from report 19 §2.3.
/home/thu/miniforge3/envs/infersuite-full/bin/python \
    ~/InferSuite/spec26/kit/plot/plot_spec_results.py     # Fig 11 -> spec_vs_agentic_frontend.png

# The percentiles themselves, without the figure:
python3 - <<'PY'
import json
V = json.load(open("/home/thu/InferSuite/spec26/plots/values_dump.json"))
for k, v in V["frontend"].items():
    print(f"{k:<14} SPEC median {v['spec_median']:8.3f}  agent {v['agentic_rotation_median']:8.3f}"
          f"  p{v['spec_percentile_of_agentic_median']:.0f}"
          f"  {v['n_spec_more_extreme']}/26 more extreme")
PY
```

Cost: seconds, from banked data. What should reproduce: the ranks. The percentiles are computed
from 26 fixed benchmarks, so they are exact given the same captures.

### 2.4 Scripts and artifacts

| Item | Location | Role |
|---|---|---|
| Figure + percentile computation | [`spec26/kit/plot/plot_spec_results.py`](../../spec26/kit/plot/plot_spec_results.py) | Fig 11 (`FRONT` block) |
| SPEC shared-8 reload | `~/spec26-infra/infra/scripts/compare_spec_agentic.py` | the `spec` rows of `comparison_iso8.json` |
| Populations | [`spec26/kit/plot/spec_common.py`](../../spec26/kit/plot/spec_common.py) | `agentic_split()` |
| Audit dump | `spec26/plots/values_dump.json` | key `frontend` — per-metric SPEC min/max/median, agentic points, percentile, count more extreme |
| Per-benchmark context for the tail | [`spec26/plots/spec_signature.png`](../../spec26/plots/spec_signature.png) | which benchmarks occupy the tail |

## 3. Key insights (most → least important)

1. **Kernel time is the only metric on which the agent leaves the suite.** p96, with just
   **1 of 26** SPEC benchmarks higher. Everything else places the agent inside SPEC's range.
   If the study needs one metric that says "this is a different kind of workload", it is this
   one — and it is also the least dependent on microarchitectural interpretation.
2. **On instruction supply the agent is in SPEC's tail, not beyond it: L1I MPKI p77, MITE p65,
   DSB p27.** The right sentence is "the agent looks like SPEC's compilers and interpreter",
   not "the agent is unlike anything in SPEC". That is a *more* useful claim — it names the
   mechanism and gives a reader a familiar reference point.
3. **What separates the agent is persistence, not peak.** SPEC's frontend-heavy members reach
   these levels in phases (`723.llvm_r` per-window IPC 0.02–3.54, report 18). The agent's
   replays sit in a tight cluster: every episode, whole episode. A future study should quantify
   this directly — per-window *dispersion* of L1I MPKI, agent vs SPEC — which the banked
   per-window layer already supports.
4. **Ratios and ranks must be reported together.** 15.31× (report 19) and p77 (here) are both
   correct and, quoted alone, lead to different conclusions. The deck now carries both on
   adjacent slides for exactly this reason.
5. **The agent's rank is robust to the configuration change even where its value is not.**
   Matched and legacy captures land in the same region of every panel, so the positional claim
   survives the SMT/window-length change that moved IPC by 18.8 % (report 20).
6. **A figure whose title contradicts its own annotation will ship unless someone reads it.**
   This one did, briefly. The check that caught it was rendering the PNG and reading it, not
   any automated gate — worth keeping in the workflow.
