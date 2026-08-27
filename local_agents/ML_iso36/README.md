# ML_iso36 — 36-task count-view TMA + full-metric profiling (P7, matched configuration)

**Branch `multiling-type-id`, started 2026-08-21.** Dedicated-group replay profiling of **36
SWE-bench-Multilingual tasks selected on the COUNT-based type matrix** (leaf commands counted
once, `cpu_matrix.tsv` `leaf_label`), on the same configuration as the SPEC CPU 2026 baseline —
measured cores 4–11, SMT off, 100 ms windows, ISO-PROOF-gated. Replays never call the model:
machine time only.

## Selection (PI directive 2026-08-21)

`../ML_typeid/selection_36_count.tsv`, produced by `kit/campaign/typeid_select36.py`:
**4 tasks per language × 9 languages**; one per populated ⟨language, count-label⟩ cell among
B/T/S/M; a row's empty cells donate their slots to that language's **majority count category**.
A cell is "empty" when it has no *profilable* candidate: `replay-invalid`, E7 loop flags, and
no-banked-trajectory are hard excludes; within a cell the pick mirrors `typeid_select.py`
(coverage ≥ 80, classified ≥ 50 soft, repo diversity, confound avoidance, then closest to the
cell's median fence). Realized layout (27 cells + 9 top-ups):

| lang | B | T | S | M | top-ups |
|---|---|---|---|---|---|
| C | redis-12272 | micropython-13039 | jq-2598 | redis-10068 | — |
| C++ | nlohmann-4237 | — | — | — | 3× fmt (B; only repo besides nlohmann in the cell) |
| Rust | nushell-13831 | ripgrep-2209 | — | bat-2835 | axum-1730 (B) |
| Go | caddy-4774 | gin-2121 | — | prometheus-10720 | hugo-12579 (M) |
| Java | gson-1093 | gson-2134 | lombok-3479 | javaparser-4538 | — |
| PHP | laravel-52684 | php-cs-fixer-8064 | carbon-2752 | phpspreadsheet-3463 | — |
| Ruby | fpm-1829 | fastlane-20958 | — | rubocop-13560 | fluentd-3328 (T) |
| JavaScript | — | babel-15649 | — | preact-3763 | axios-5892, three.js-26589 (T) |
| TypeScript | — | docusaurus-9897 | vuejs-core-11870 | — | immutable-js-2006, docusaurus-10130 (T) |

**Resolution-clean revision (2026-08-27).** After the full-census official SWE-bench
evaluation (docs/multi_full_stratification.md, 2026-08-27 section), the four picks whose
live episodes are not officially resolved were replaced under the original ranking:
valkey-1499 → redis-10068 (C×M), rubocop-13396 → fluentd-3328 (Ruby×S had no resolvable
candidate — slot converted to majority-T top-up), vuejs-core-11589 → core-11870 (TS×S),
axios-6539 → axios-5892 (JS×T). The table above shows the revised set (26 cells). The
four replacements still need P7 replay profiling; the four dropped tasks's banked
profiles remain valid data but leave the 36-set figures.

Known forced outcomes (all recorded in the TSV `why` column): the JavaScript×S cell's only
member is hard-flagged, so JS runs without S; Java×B and Java×T are singletons (both gson);
C++ is fmt-dominated by population; several PHP/Ruby picks are small-fence tasks (a fact about
those languages' realized CPU, kept deliberately — the cell exists, so it is represented).

## Instrument (identical to the SWE_iso8 matched capture, plus fe_miss)

Per task, **9 dedicated-group replay passes** (`replay_l3_profile.sh`, one counter group at
100 % duty per episode, 100 ms windows, shuffled-rotation not needed since every window is the
same group), plus per pass: continuous whole-episode TMA (PERF_METRICS), 10 Hz `cpu.stat`
pollers, 2 Hz command tagger, 99 Hz lanes record.

```
PROF_GROUPS = fpbr cache mlp fe fe_lat core_ports dram_bw priv fe_miss
```

The first 8 are the shared SPEC/agent groups of report 19; **`fe_miss` is the 9th pass** and is
what turns the previous 13-of-16 metric card into 16-of-16 (it carries `baclears.any`,
`frontend_retired.any_dsb_miss`, `br_misp_retired.cond/.indirect`). SPEC already rotates
fe_miss, so the comparison side needs no new SPEC capture.

## Metric contract (the 18 figures rows)

Mentor's 16 (cross_task_grid.py `PANELS16`): IPC · branch MPKI · branch-direction MPKI (cond)
· BTB MPKI (BAClears) · DSB coverage % · µop-cache (DSB-miss) MPKI · L1I MPKI (code-read) ·
L1D-load MPKI · L2-load MPKI · LLC MPKI · L1I stall %cyc (miss-rate proxy) · L1D miss rate % ·
L2 miss rate % · LLC miss rate % · AMAT (cycles) · MLP.
Plus the two PI additions: **DRAM read bandwidth (GB/s)** (dram_bw group, 64 B ×
`offcore_requests.data_rd` / window wall) and **context switches per CPU-second** (priv group,
task-clock-normalized so fence concurrency does not distort the rate).
Derivations: per-window in `kit/replay/analyze_l3_windows.py`; episode cards for the SPEC
comparison by the one shared implementation `~/spec26-infra/infra/scripts/extract_metrics.py`
(report 19 D1). TMA L1/L2 per fence from `tma_cont.csv`; per-task value = median across the 9
passes, never pooled.

## Data flow

1. `fetch_trajs.sh` — rsync the 36 banked census trajectories from
   `bz-network-ws02.local:~/InferSuite-Jerry/local_agents/ML_typeid/data/` into
   `data/traj_src/<short>/` (checksum mode; read-only on the source).
2. `run_ml_iso36.sh` — resumable sweep: per task ensure the swebench image (pull ×3, disk
   floor 40 G with swebench-image GC), localize the trajectory
   (`kit/replay/localize_traj.py`), then the 9 passes via `replay_l3_profile.sh`.
   Banked under `data/glm_replay_swe_<short>/run_{1..9}/`. `touch STOP` stops cleanly between
   tasks; a foreign perf on the box stops the sweep (exit 3) — never kill another user's
   collectors.
3. Derivation/figures follow the standard pipeline (analyze → extract → figures → audit)
   and are documented with the figures' MANIFEST when they land.

Cost: zero API spend. Machine time estimate before smoke: the 12-task × 8-pass SWE_iso8 sweep
measured 4.4 h; this set is 36 tasks × 9 passes with a larger summed fence (4,797 core-s) —
expect roughly 8–16 h, refined after the smoke task.
