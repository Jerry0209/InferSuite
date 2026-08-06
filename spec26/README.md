# spec26 — the SPEC CPU 2026 traditional-workload baseline

The agentic campaigns in `local_agents/` produce numbers nobody has a reference for. Is an L1I
MPKI of 12 high? Is 11 % kernel time unusual? This tree is the answer: **SPEC CPU 2026 measured
with the same instrument, the same counter groups and the same formulas, on the same
workstation**, so the agentic findings have a baseline instead of an unanchored number.

It does two jobs at once:

1. **Validates the method.** Benchmarks whose microarchitectural character is already documented
   must come out with that character. They do — see `plots/spec_signature.png` and the deck's
   slide 13.
2. **Anchors the comparison.** Every SPEC-vs-agentic number is computed by the *agentic* kit's
   own `extract_metrics.py` over both sides' raw window files, restricted to the eight certified
   shared counter groups. A difference is then a difference between workloads, not between two
   implementations of brMPKI.

## Where things live

| What | Where |
|---|---|
| Capture kit, config, validators, raw windows | `~/spec26-infra/infra` — **outside this repo** (sibling kit; ~1.4 GB of perf text files) |
| Analysis + figure code | `spec26/kit/plot/` (this tree) |
| Thesis-ready figures + `values_dump.json` | `spec26/plots/` (tracked) |
| Per-window PNGs and per-benchmark galleries | `~/spec26-infra/infra/plots/windows/` — outside the repo, ~1.9 k PNGs |
| Curated figure view | `plots/spec26/` (synced by `scripts/sync_plots.sh`) |

The split matches `local_agents/`: code and curated figures are tracked, campaign data is not.
The capture kit is deliberately a **sibling outside the repo** — the same arrangement already
recorded in `docs/wiki/operations/isolation-setup-runbook.md`.

## The capture, in one paragraph

26 benchmarks (14 intrate + 12 fprate; `999.specrand_r` is a validation harness and was not
run), **ref** inputs (`refrate`), **1 copy / 1 thread**, one ref command line each (index 0),
fenced into a transient systemd scope under `measured.slice` on **8 SMT-free isolated cores**
(measured 4–11, siblings offlined; housekeeping 0–3, 12–15) at a fixed clock with turbo off.
Counters rotate through **11 groups, one per 100 ms window, shuffled every cycle**, so nothing
is ever multiplexed; a continuous TMA census runs alongside at 100 % duty on zero
general-purpose counters. 22,413 windows, 26/26 episodes pass every evaluable gate.

## Regenerate

Figures need matplotlib, which is not in the repo `.venv`:

```bash
PY=/home/thu/miniforge3/envs/infersuite-full/bin/python

$PY spec26/kit/plot/plot_spec_results.py      # 13 thesis figures + values_dump.json
$PY spec26/kit/plot/plot_spec_windows.py      # ~1.9k per-window PNGs (outside the repo)
$PY spec26/kit/plot/build_spec_gallery.py     # one HTML gallery per benchmark
DECK_OUT=~/spec26-infra/infra/plots/spec_deck.html \
  $PY spec26/kit/plot/build_spec_deck.py      # the 21-slide deck
bash scripts/sync_plots.sh                    # refresh plots/spec26/
```

Upstream of all of it (in the sibling tree, not here):

```bash
cd ~/spec26-infra/infra
python3 scripts/extract_metrics.py data/*/                       # metrics.json per episode
python3 scripts/validate_spec.py  data/*/                        # 13 gates per episode
python3 scripts/compare_spec_agentic.py data \
        ~/InferSuite/local_agents/SWE_clean/data/*/run_*/        # comparison.json
```

`comparison.json` is what makes the cross-campaign figures possible, and it never writes into
the agentic tree — that data is read-only banked evidence.

## Two things to get right when reading these figures

**Episode value ≠ per-window median.** The episode value is a ratio of sums over the whole run;
the per-window layer is a distribution of per-window ratios. Where they disagree the program has
phases (`plots/spec_phase_timelines.png`), and that gap is a finding, not an error.

**`LLC_MPKI` is a demand-miss metric, not a memory-boundedness metric.** `782.lbm_r` streams
4.3 GB/s from DRAM at an LLC MPKI of 0.01, because the prefetcher fetched every line before the
load retired. Use `DRAM_read_GBs` or TMA `mem_bound` for memory pressure, and read `LLC_MPKI` as
"how often the prefetcher failed".

Full methodology, decisions and hazards: `docs/reports/18_spec26_baseline.md`.
