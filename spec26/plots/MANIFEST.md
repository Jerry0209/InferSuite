# SPEC CPU 2026 baseline — figure manifest

Data: `~/spec26-infra/infra/data/` (26 episodes, 22,413 windows of 100 ms, ref inputs, 1 copy on
1 isolated SMT-free core). Regenerate with
`/home/thu/miniforge3/envs/infersuite-full/bin/python spec26/kit/plot/plot_spec_results.py`.
Every number any figure displays is also written to `values_dump.json`, so a reader can check a
bar without reading pixels.

## Labelling and ordering convention (2026-08-06)

Every figure labels a benchmark by its **full published SPEC name**, `7xx.workload_r` — the form
spec.org uses, and the only form a reader can look up. The bare stem survives in per-window PNG
*filenames* only.

Six figures are ordered **SPECrate integer block first, then SPECrate floating-point**, each
block by SPEC number, with a dashed INT|FP divider on the axis: `spec_suite_overview`,
`spec_tma_l1`, `spec_tma_l2`, `spec_uop_supply`, `spec_memory_ladder`, `spec_window_grid`.
The reason is that the categories behave differently and a value-sorted axis interleaves them:
branch MPKI 2.36 (INT) vs 0.059 (FP), bad speculation 14.5 % vs 1.5 %, backend-bound 19.4 % vs
42.0 %, DRAM read 0.87 vs 3.45 GB/s. Those numbers are banked under `int_vs_fp` in
`values_dump.json`.

`spec_signature` keeps its IPC ordering (its title says so) and `spec_instrument` keeps SPEC
numeric order — neither makes a category claim.

## Which population each figure uses

Two SPEC numbers exist for the same episodes and they are **not** interchangeable:

- **11 groups** (the episode's `metrics.json`) — the richest SPEC number. Used by every
  SPEC-only figure.
- **8 shared groups** (`comparison.json`, reloaded by `compare_spec_agentic.py`) — used by
  every SPEC-vs-agentic figure, because the agentic campaign only ever rotated those eight.
  IPC is the metric that actually moves: it is total instructions over total cycles across
  *all* windows, so a different group mix samples a different part of the program
  (26-episode median **2.427** over 11 groups vs **2.418** over 8). Per-event ratios are
  immune — their denominators are already co-counted per group.

The agentic side is likewise split by instrument and **never merged**:

| Population | n | Tasks | What one episode gives you |
|---|---|---|---|
| **legacy rotation** | 7 | 4 — babel, django, fmtlib, sympy | all 8 groups shuffled across the episode, i.e. the same instrument SPEC runs, so one episode yields a full metric card at ~1/8 duty per group. 6 live + 1 replay anchor |
| **matched replay** (primary) | 96 | **12 — astropy, babel, fmtlib, gson, jq, php-cs-fixer, prometheus, rubocop, scikit-learn, sympy, tokio, vue (10 languages)** | one group for a whole deterministic episode (2 s windows) at 100 % duty, model never called — so **each metric rests on the 12 replays that ran its group, never on all 96** (IPC is the exception at 84: cycles and instructions ride in every group). Each task was replayed 8 times, once per shared counter group |

**Configuration (2026-08-07).** The agentic replays were re-captured on the SPEC configuration —
measured cores **4–11 with SMT off**, **100 ms** windows, same partition, same fence — and that
matched capture (`comparison_iso8.json`) is now the agentic side of every comparison figure. The
retired SMT-ON / 2 s capture (`comparison.json`) is kept as the configuration control, because
the pair *measures* what the old caveat was worth: agentic IPC **1.591 → 1.890 (+18.8 %)** with
the sibling thread gone, while the TMA shape barely moves (frontend-bound 34.1 → 32.7 %,
bad speculation 15.8 → 15.4 %). SPEC-vs-agentic ratios on the matched 12-task capture: kernel **31.7×**,
microcode **13.7×**, L1I MPKI **11.7×**, MITE **3.2×**, branch MPKI **3.0×** — against
AMAT **0.99×**, MLP **1.02×**, DRAM **0.84×**, DSB **0.79×**, L1D **0.60×**. Widening from
2 tasks to 12 held every direction and moved magnitudes within ~30 %.

Populations are selected by **provenance**, not by counter-group count. Three *live* episodes
(`glm_swe_babel` run_2/4/5) also dedicate a whole episode to one group via `GORDER_OVERRIDE` —
they are method probes with the model in the loop, and belong to neither population.

`spec_vs_agentic_metrics` uses the **replay** population only (PI decision 2026-08-06) and prints
the contributing episode count per row; `spec_vs_agentic_tma` shows both plus SPEC;
`spec_vs_agentic_frontend` and `spec_landscape` use rotation, with replays overlaid.

Earlier populations are recorded so an older figure can be dated: rotation-only gave L1I
11.96× / kernel 23.18× / DRAM 0.07×; the 2-task replay population gave 15.31× / 28.04× / 0.79×;
the 12-task population gives 11.73× / 31.74× / 0.84×. The DRAM number moved because of **task
composition, not instrument** — the 2-task sample was babel (JS) and fmtlib (C++), and fmtlib
compiles C++ and moves real memory traffic where the Python tasks do not.

| Figure | What it shows | Population |
|---|---|---|
| `spec_suite_overview.png` | wall time and windows captured per benchmark, with the 55-window floor | SPEC 26 |
| `spec_instrument.png` | slots/cycle vs the core's issue width · counting duty · rotation balance | SPEC 26 (no metric value used) |
| `spec_tma_l1.png` | TMA Level 1 across the suite, INT block then FP | SPEC 26 |
| `spec_tma_l2.png` | TMA Level 2 — which half of each L1 bucket carries the stall | SPEC 26 |
| `spec_signature.png` | 10-metric signature heatmap on **absolute** reference scales (sorted by IPC) | SPEC 26 (11 groups) |
| `spec_uop_supply.png` | DSB/MITE/MS/LSD delivery shares beside L1I MPKI | SPEC 26 |
| `spec_memory_ladder.png` | L1D / LLC / DRAM GB/s / MLP, with the demand-miss caveat | SPEC 26 |
| `spec_landscape.png` | IPC vs stalled slots, with the agentic median placed in it | SPEC 26 (8 groups) + agentic rotation |
| `spec_vs_agentic_metrics.png` | paired medians on a log axis, ratios per metric; SPEC carries a full-range whisker, the agentic side carries its individual episode points marked by task (a range over 2 points is not a range) | SPEC 26 (8 groups) + **replay only** |
| `spec_vs_agentic_tma.png` | TMA L1 **radar** over all four buckets incl. bad speculation, + per-episode frontend-bound vs bad-speculation scatter | SPEC 26 + matched replay + legacy replay |
| `spec_vs_agentic_frontend.png` | SPEC distributions with agentic episodes overlaid, and the agentic median's SPEC percentile | SPEC 26 (8 groups) + rotation + replay |
| `spec_window_grid.png` | 12 metrics × 26 benchmarks of **per-window** distributions | SPEC 26, per-window |
| `spec_phase_timelines.png` | per-window IPC over the episode for 6 benchmarks | SPEC 26, per-window |

## Reference scales in `spec_signature.png`

Shade is position on a **fixed** domain range, never per-column min–max, so a cell means the
same thing here as in the agentic `glm_signature.png`. Anchors are hardware ceilings where they
exist, otherwise the span the performance literature treats as low..severe:

| Column | Range | Anchor |
|---|---|---|
| IPC | 0–6 | Golden Cove retire width |
| Branch MPKI | 0–20 | <1 well-predicted; ~20 severe |
| DSB coverage % | 0–100 | share of delivered uops |
| L1I MPKI | 0–20 | >20 = datacenter "instruction-footprint wall" |
| L1D-load MPKI | 0–40 | >40 = genuinely memory-intensive load streams |
| LLC MPKI | 0–10 | ~10 = fully memory-bound territory |
| AMAT | 5–50 | L1-hit latency .. L3 territory |
| MLP | 1–16 | 16 L1D fill buffers |
| DRAM read GB/s | 0–12 | measured suite ceiling (749.fotonik3d_r / 765.roms_r ≈ 11.3) |
| kernel % | 0–20 | 0 = pure user-space; 20 covers the agentic range |

`AMAT_cyc` is a **fixed-latency model** (5/15/50/250 cycles for L1/L2/L3/DRAM hits weighted by
retired-load counts), not a measured latency — it is a comparable composite, and is labelled as
such wherever it appears.

## Standing caveats for every cross-campaign figure

- **SMT.** Agentic runs are SMT-ON on 20 logical CPUs; SPEC is SMT-OFF on 8 physical cores.
  Cycle-normalised metrics (IPC, port utilisation, frontend bandwidth shares) cross that
  boundary badly; per-instruction rates survive it far better.
- **Contention.** SPEC runs one copy on one core with L3 and DRAM to itself. The agentic
  workload ran many concurrent processes and did contend.
- **Population size.** The primary agentic side is 7 full-rotation episodes over 4 tasks. The
  19 replay episodes corroborate every direction but not magnitude.
- **`LLC_MPKI`** counts retired demand loads that missed L3 — not memory-boundedness.
