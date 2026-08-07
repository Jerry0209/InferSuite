# Session 2026-08-06 → 08-07 — SPEC CPU 2026 baseline: figures, deck, galleries, comparison

**Goal:** turn the finished SPEC CPU 2026 capture into InferSuite-style figures, a deck and
per-window galleries; document it; then make the SPEC-vs-agentic comparison defensible.

**Machine state at start:** Xeon w5-3425, measured 4–11 (SMT siblings 16–23 offline), house
0–3,12–15, governor `performance` on measured cores, `no_turbo=1`, THP `never`. Shared box —
`jeferson` profiles the same cores from `agentic.slice`. SPEC side already captured: 26
episodes, 22,413 windows of 100 ms, ref inputs, 1 copy, 26/26 passing every evaluable gate.

---

## Decisions

| # | Decision | Why | Made by |
|---|---|---|---|
| 1 | SPEC analysis code + figures live in **InferSuite** (`spec26/`), capture kit and 1.4 GB of raw windows stay in the sibling tree `~/spec26-infra/infra` | Mirrors how `local_agents/` splits tracked code from untracked campaign data; the sibling-kit arrangement was already recorded in the wiki | Claude, stated to PI |
| 2 | SPEC-only figures use all **11** counter groups; every SPEC-vs-agentic figure uses the **8 shared** groups on both sides | IPC is total instructions over total cycles across *all* windows, so a different group mix samples a different part of the program (26-episode median 2.427 over 11 vs 2.418 over 8). Per-event ratios are immune — their denominators are already co-counted per group | Claude |
| 3 | Full `7xx.workload_r` labels on every figure | The published SPEC name is the only identifier a reader can look up; the bare stem is ambiguous across suites | **PI** |
| 4 | Six figures ordered **INT block then FP**, each by SPEC number, with a divider | The categories behave differently and a value-sorted axis interleaves them. Earned out immediately: branch MPKI 2.36 vs 0.059 (40×) | **PI** |
| 5 | Slide 17 compares against **replays only** | A replay gives one counter group 100 % duty on a deterministic, model-free episode — the cleanest per-metric agentic number | **PI** |
| 6 | Replay population selected by **provenance**, not counter-group count | Three *live* episodes also dedicate a whole run to one group via `GORDER_OVERRIDE`; they are method probes with the model in the loop (defect 2 below) | Claude |
| 7 | Agentic side **re-captured at the SPEC configuration** — cores 4–11 SMT-off, 100 ms | Retires the SMT and window-length caveats instead of carrying them in prose, and prices them | **PI** |
| 8 | Slide 18 becomes a **TMA radar** including bad speculation | Mentor: the question is the shape of the profile, not its composition | **PI's mentor** |
| 9 | Publish 8 of 26 galleries, chosen to span the behavioural space | 26 artifacts is excessive; all 26 are built locally and any can be published on request | Claude |
| 10 | Commit the SPEC scope only; leave the isolation-runbook workstream's pending edits alone | The report checker's 7 freshness warnings are pre-existing and unrelated; PI chose to override for the SPEC scope only | **PI** |

## What changed

**New in-repo (`spec26/`):** `kit/plot/{spec_common,plot_spec_results,plot_spec_windows,
build_spec_gallery,build_spec_deck}.py`, `plots/` (13 figures + `values_dump.json` +
`MANIFEST.md`), `README.md`. Curated view `plots/spec26/` wired into `scripts/sync_plots.sh`.

**New agentic capture:** `local_agents/SWE_iso8/` — 16 dedicated-group replays (8 shared groups ×
babel, fmtlib) at the SPEC configuration; ~350 windows per babel pass, ~1,110 per fmtlib pass.
Driver `run_iso8_languages.sh`. Raw `rec_*.data` gitignored.

**Docs:** report 18 (`docs/reports/18_spec26_cpu2026_baseline.md`), registered in both indexes
and in report 14's artifact registry.

**Artifacts:** deck (21 slides) + 8 per-window galleries — links in report 18 §2.5.

**Pushed:** `62bb7325` (baseline) → `2bac6a2c` (labels + INT/FP order) → `a65c51e9` (window
budget) → `bbebedf0` (slide 17 replay-only) → `afa4faad` (provenance fix) → `922d3f69` (matched
capture + radar).

## Defects found

Each with the number it would have shipped.

1. **`slots/cycle` biased 10 % high.** The `priv` group counts `cycles:u`/`cycles:k` instead of
   plain `cycles`, so summing `v["cycles"]` dropped 1 of 11 groups from the denominator. The
   gate reported **6.62** against a true **6.01** (passed either way, band 3.5–8.5 — but the
   number *is* the cross-instrument evidence). All 26 now read 6.00–6.02.
2. **Replay population selected by group count.** Swept three live probe episodes into a
   "replays only" figure. Moved **L1I MPKI 18.00× → 17.31×** and **DRAM 0.52× → 0.92×** — i.e.
   from "SPEC reads 1.9× more DRAM" to near parity.
3. **The agentic kit would have destroyed the operator's partition.** `apply_isolation`
   snapshotted the governor from **cpu0 only** (`powersave`) and restore wrote it to `cpu*`
   (would have left measured cores 4–11 in powersave); restore also reset `system.slice`,
   `user.slice` and `measured.slice` to `AllowedCPUs=<all online>`, wiping the 0–3,12–15 split.
   Same defects fixed in the SPEC kit on 2026-08-05; ported and verified before any capture.
4. **`int(os.environ["WINSEC"])`** raised on `0.1` inside a background heredoc, so a run
   produced 363 windows and **no `metadata.json`** — which also starved the 2 Hz command tagger,
   since it waits on that file to learn the tool cgroup.
5. **Figure ratio labels printed against the wrong rows** (axes-fraction placement on an
   inverted axis). Caught visually before publish; `get_yaxis_transform()` now used.

## Verified, not assumed

- **Core migration.** `cpu-migrations` = 0 in all 26 episodes; the per-CPU `/proc/stat` witness
  (100 % coverage, vs the ~1/11 the `priv` group sees) agrees: **19/26 never left cpu7**, the
  other 7 show a single 10 ms sample elsewhere, residency 99.885–100.000 %. Counting is
  migration-safe by construction — `perf stat -a --for-each-cgroup` arms per-CPU counters on
  every CPU and filters by cgroup.
- **Window budget.** An episode yields `(wall − lead_in − teardown)/pitch` windows, **72–82 %**
  of naive `wall/WINSEC`. Worked example `729.abc_r`: (11.74 − 0.16 − 1.00)/0.123 = 86, where
  11.74/0.1 would suggest 117.
- **Reproducibility control.** Two independent full-suite captures differ by a median **2.12 %**
  across 11 metrics × 26 benchmarks (0.30 % steadiest, 13.8 % noisiest).

## Open threads

1. **Nine-language re-capture — NOT DONE, stopped on PI instruction.** Only babel (JS) and
   fmtlib (C++) exist at the matched configuration. Trajectories are banked for 8 more
   languages (astropy/Python — PI's pick — prometheus/Go, gson/Java, jq/C, php-cs-fixer/PHP,
   tokio/Rust, rubocop/Ruby, vuejs/TS); ~3 h of machine time, no API cost. Driver ready at
   `local_agents/SWE_iso8/run_iso8_languages.sh`; it skips completed tasks. **Blocked on the
   shared box being free.** Its foreign-`perf` guard currently fires only between tasks — make
   it fire before every *pass* before relaunching.
2. **Comparison figures still rest on 2 tasks**, both non-Python. Per-metric `n` on slide 17 is
   2. Expect magnitudes to move when (1) lands; report 16 suggests composition reproduces across
   languages at ~1 %.
3. **SWE-bench Multilingual ⟨language, type⟩ selection.** PI wants ≤30 representatives chosen
   from a *classification-only* live run (no perf/TMA). Report 17 already found the discrete
   matrix collapses (16/16 episodes search-led; static prediction 1/10 on realized behaviour).
   Proposal on the table: keep language as rows, replace discrete types with **tertiles of
   realized test-share weighted by tool-fence CPU** → 9 × 3 = 27 cells. **Awaiting PI decision**
   on the axis and on how many instances to spend on the classify pass.
4. **7 pre-existing report-checker freshness warnings** on `run_glm_campaign.sh` remain; they
   clear only when reports 02/03/04/07/08/09/12 are refreshed.
