# Handoff — start here

**Owner:** Tianrui (Jerry) · **Status:** active · **Last updated:** 2026-08-07

You are picking up a microarchitectural study of **agentic AI workloads** — what the CPU
actually does while an LLM agent repairs software — measured against **SPEC CPU 2026** as the
traditional-workload baseline. This page is the entry point for a new colleague or a fresh
Claude Code session. It assumes nothing.

The documentation contract is [`PROTOCOL.md`](PROTOCOL.md). Read it before writing anything.

---

## 1. The one-paragraph version

An LLM agent doing real software repair does not stress the CPU the way SPEC does. Measured on
the same machine, with the same counters and the same code computing every ratio: agentic work
costs **~15× the instruction-cache pressure**, **~28× the kernel time** and **~4× the legacy
instruction decode** of the median SPEC benchmark, while **AMAT, MLP, L1D and DRAM bandwidth do
not separate the two at all**. SPEC stalls on the back end; the agent stalls on the front end
and mis-speculates more. The metrics everyone reaches for first are the ones that carry no
signal here.

## 2. Where everything lives

| What | Path | In git? |
|---|---|---|
| Agentic campaigns (kit, data, figures) | `local_agents/` | code yes, `rec_*.data` no |
| **SPEC CPU 2026 analysis + figures** | `spec26/` | yes |
| SPEC capture kit + 1.4 GB of raw windows | `~/spec26-infra/infra` | **outside this repo** |
| SPEC install (binaries, ref inputs, run dirs) | `~/spec26-infra/cpu2026` | outside this repo |
| Study reports (one per study) | `docs/reports/` | yes |
| Session logs (one per chat) | `docs/handoff/sessions/` | yes |
| **ARM / AWS Graviton bring-up handoff** | `docs/handoff/arm_aws_bringup.md` | yes |
| Knowledge wiki (cross-cutting) | `docs/wiki/` | yes |
| Curated figure view | `plots/` (synced, never edited by hand) | yes |

The SPEC capture kit is deliberately a **sibling tree outside this repo** — same arrangement
recorded in `docs/wiki/operations/isolation-setup-runbook.md`. Only derived figures and
plotting code are tracked here.

## 3. The machine, and the one rule about it

Intel Xeon w5-3425 (Sapphire Rapids, Golden Cove, 6-wide issue). Boot partition:

| | |
|---|---|
| Measured cores | **4–11**, SMT siblings (16–23) **offline** |
| Housekeeping | **0–3, 12–15** — IRQs, workqueues, every system slice |
| Clock | governor `performance` on measured cores, `no_turbo=1` |
| THP | `never` |

> **This box is shared.** A colleague (`jeferson`) profiles the same cores from
> `agentic.slice`. Before any capture: `pgrep -a -x perf`. If anything is running that is not
> yours, **wait** — never kill another user's collectors, and never run concurrently (you would
> corrupt both measurements: the PMU general-purpose counters and PERF_METRICS are shared).
> `isolcpus` is **banned** — it removes cores from scheduler load balancing.

## 4. Run something

```bash
PY=/home/thu/miniforge3/envs/infersuite-full/bin/python   # matplotlib is NOT in the repo .venv

# Regenerate every SPEC figure + the audit dump (no capture, banked data only)
$PY spec26/kit/plot/plot_spec_results.py
$PY spec26/kit/plot/plot_spec_windows.py     # ~1.9k per-window PNGs (written outside the repo)
$PY spec26/kit/plot/build_spec_gallery.py    # one self-contained HTML gallery per benchmark
DECK_OUT=~/spec26-infra/infra/plots/spec_deck.html $PY spec26/kit/plot/build_spec_deck.py
bash scripts/sync_plots.sh                   # refresh plots/spec26/

# Re-derive the comparison from raw windows (both sides, one implementation)
cd ~/spec26-infra/infra
python3 scripts/extract_metrics.py data/*/          # metrics.json per episode
python3 scripts/validate_spec.py  data/*/           # 13 gates; exit 0 = all evaluable gates pass
SPEC_COMPARISON_OUT=$PWD/comparison_iso8.json python3 scripts/compare_spec_agentic.py data \
    ~/InferSuite/local_agents/SWE_iso8/data/*/run_*/
```

## 5. The five things that will bite you

1. **The co-counted denominator.** One counter group is live per window, so an event is counted
   in ~1/11 of the episode. Dividing by instructions summed over *all* windows understates every
   rate by the group count (~11×). Denominators are summed **per window**, over exactly the
   windows where that event was itself counted. This bug shipped once in the agentic campaign at
   ~8×.
2. **Undefined ≠ zero.** A metric whose counter group never got a window is `None`, never `0.0`.
   Coercing it to zero once inverted a DRAM finding into "SPEC issues no DRAM reads".
3. **`LLC_MPKI` is a demand-miss metric, not a memory-boundedness metric.** `782.lbm_r` streams
   4.3 GB/s at an LLC MPKI of 0.01 because the prefetcher won. Use `DRAM_read_GBs` or TMA
   `mem_bound`.
4. **A 100 ms window costs ~122 ms of wall.** perf is re-armed between windows (~22 ms fixed),
   and each episode has a lead-in and a teardown that carry no windows. An episode yields
   `(wall − lead_in − teardown) / pitch` windows — **72–82 %** of the naive `wall/WINSEC`.
5. **Populations are never merged.** The agentic side has two instruments (whole-episode
   rotation vs dedicated-group replay) and two configurations (legacy SMT-ON vs matched
   SMT-off). Which one a figure uses is stated in `spec26/plots/MANIFEST.md`, per figure.

## 6. Reading order

New to the project: **this page** → [`PROTOCOL.md`](PROTOCOL.md) →
[report 18](../reports/18_spec26_cpu2026_baseline.md) (the SPEC baseline: capture, validation,
the whole instrument) → reports 19–21 (the comparison studies) →
[`spec26/plots/MANIFEST.md`](../../spec26/plots/MANIFEST.md) (which population feeds which
figure) → `docs/handoff/sessions/` newest-first for what happened recently.

For the agentic side specifically, `docs/reports/` 01–17 predate the SPEC baseline and cover
the agent campaigns; `docs/reports/README.md` has the full index and its own reading order.
