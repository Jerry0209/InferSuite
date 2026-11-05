# arm/ — SPEC CPU 2026 single-core profile on AWS Graviton5 (branch `spec-arm`)

What: the 26 SPECrate 2026 benchmarks (ref inputs, copies = 1, threads = 1, ref command
index 0 — the x86 rows' set) profiled on **one pinned Neoverse-V3 core** with Jef's ARM
metric families: one dedicated `perf stat` pass per family, cycle counter + ≤ 6 events,
no multiplexing, 100 ms windows, filtered to our fence cgroup. Procedure:
[`docs/handoff/execution/arm_spec_profiling.md`](../docs/handoff/execution/arm_spec_profiling.md).
Session log: [`docs/handoff/sessions/2026-11-03_arm-spec26-profiling.md`](../docs/handoff/sessions/2026-11-03_arm-spec26-profiling.md).

Everything here is our code. Jef's method (event lists, formulas, layout) is reimplemented
from its description; nothing from his private repo is copied. No SPEC file is in git.

| Path | What |
|---|---|
| `config/host.toml` | the box as observed: CPUs, partition, kernel, perf, PMU, boot cmdline |
| `config/profiling_plan.toml` | families → events (aliases + raw codes), formulas, parity labels, suites. Single source for the profiler and the exporter |
| `kit/arm_shield.sh` | `apply / verify / restore / status`: runtime 8 + 8 isolation with snapshot-based restore and the ISO-PROOF gate |
| `kit/arm_profile.py` | `qualify / run / check / summary`: the capture driver and per-pass gates |
| `kit/export.py` | banked passes → per-window / per-benchmark CSVs in Jef's figure schemas (`--selftest`) |
| `data/raw/` | **git-ignored**: perf JSON per ⟨benchmark, family, attempt⟩, witness, qualification receipts |
| `data/interim/` | **git-ignored**: build/setup logs, extracted SPEC command lines, shield snapshots |
| `data/processed/spec26/` | `spec26_arm_windows.csv.gz`, `spec26_arm_votes.csv`, `episodes.csv`, `determinism.csv` |
| `reports/figures/data/` | figure-ready `spec26_arm_votes.csv`, `metric_parity.csv`, `spec26_arm_vs_x86.csv` |

## Reproduce

```bash
# box free?  who; pgrep -a -x perf      (never kill another user's process)
export SPEC_ROOT=~/spec26-arm/cpu2026
arm/kit/arm_shield.sh apply && arm/kit/arm_shield.sh verify     # ISO-PROOF, JSON on stdout
python3 arm/kit/arm_profile.py qualify                          # per boot
python3 arm/kit/arm_profile.py run --families tier1 --bench 736.ocio_r   # smoke
arm/kit/arm_shield.sh restore                                   # back to the snapshot, verified
tmux new -s armspec 'python3 arm/kit/arm_profile.py run --shield --families tier1 2>&1 | tee -a arm/data/interim/tier1.log'
python3 arm/kit/export.py
```

## Caveats (carry into every comparison)

* Arm cache and TLB events count speculative accesses, stores included; x86's load metrics
  count retired loads. Parity labels in `config/profiling_plan.toml` / `metric_parity.csv`.
* `DRAM read (GB/s)` is a core-side LL-miss proxy (no CMN/uncore PMU). What "last level"
  is on Graviton5 is unverified. x86 `LLC_MPKI`/`DRAM_read_GBs` are different quantities
  again (`spec26/infra_kit/docs/spec26_profile_validation.md` §1.1–1.2).
* No Arm counterpart for x86 DSB/uop-cache coverage and MPKI (no such event exposed).
* ARM runs are pinned to **one** core; x86 runs were free to migrate across an 8-core fence.

## Server set (branch `dcperf-arm`)

The 10 realistic Server workloads, one dedicated perf pass per ⟨workload, family⟩, server fenced on
CPUs 8–15 and client on 0–7 (`kit/server/run_server.sh` + `kit/arm_server.py`; procedure
[`docs/handoff/execution/arm_server_profiling.md`](../docs/handoff/execution/arm_server_profiling.md)).
`python3 arm/kit/server/export_server.py` (`--raw`, `--out`, `--selftest`) turns the accepted passes
(the attempt `DONE` names, with `meta.json` valid) into:

| Path | What |
|---|---|
| `data/processed/server/server_arm_windows.csv.gz` | Jef's Server schema `suite,category,workload,metric,value`, one row per 100 ms window (≥ 2 ms fence task-clock) and metric |
| `data/processed/server/server_arm_votes.csv` | per workload × metric: **`value` = whole-runtime value** (the x86 Server rule, `local_agents/JVMbench/README.md` §9: every window's raw counters summed, ratio taken once; a metric's terms pooled over every accepted pass that co-counted them, so IPC and context switches pool all passes as x86 IPC pooled its runs), **`mean_of_windows` = Jef's vote** (mean of the family pass's windows), `n_windows` (Jef's), `gap_pct` = 100 × (mean_of_windows − value) / value, `runtime_windows`, `runtime_families` |
| `data/processed/server/passes.csv` | every attempt, accepted or not: gates, failing gates, wall, mean cores, D4 drift, D5 residual, GHz, coverage, receipt, window counts |
| `data/processed/server/receipts/<workload>/<family>.json` | the accepted pass's receipt files (`*_receipt.*`, `feedsim_results.txt`, `.load_json`, `iso.json`; nothing > 1 MB) |
| `reports/figures/data/server_arm_votes.csv` | figure-ready copy of the votes; **the Server figures use `value`** (whole runtime), as the x86 Server violins did |
| `reports/figures/data/server_arm_vs_x86.csv` | ARM `value` next to the x86 Server whole-runtime value (`median` column of the `Server:<suite>` rows of `local_agents/JVMbench/plots/paper_v1/multi_server_compact_realistic_numbers.csv`), with the plan's parity label; x86 left empty where the x86 Server set has no such metric (TLB, TMA, frequency, tier 2) |
