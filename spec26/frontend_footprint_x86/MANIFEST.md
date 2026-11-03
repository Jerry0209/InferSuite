# Front-end footprint, x86 — MANIFEST

Generated 2026-11-03 12:34 UTC by `local_agents/kit/frontend_footprint/aggregate.py` from `~/spec26-infra/infra/data_frontend_footprint`. Do not edit by hand: regenerate (last section).

Three numbers per workload, for Rahul's front-end question: instruction footprint, unique taken branches, and the weighted average number of targets per taken branch. The method is `docs/handoff/execution/frontend_footprint_method.md` (the contract); the analyzer is `local_agents/kit/frontend_footprint/`.

## Population

* Expected: 26 workloads (family `spec26`, from `local_agents/RealData/data/l3_study/workload_index.csv`).
* Aggregated (status ok): 26. By subgroup: SPEC-fp 12, SPEC-int 14.
* Set-aside attempts (`*.contaminated.N`, foreign work overlapped): 0 in 0 workload(s). Never aggregated.

## Contract

| Parameter | Value |
|---|---|
| Contract | v1.1 (2026-11-03) |
| Event | `br_inst_retired.near_taken:pp` (PEBS; user + kernel). Seen in the data: `br_inst_retired.near_taken:pp` |
| Period | `-c 20011`. Seen: 20011 |
| Branch filter | `-j any,save_type` |
| Scope | the benchmark's fence cgroup, `perf record -a -C <measured> --cgroup=<fence>`; measured cores 4-11 |
| Window | benchmark released from a FIFO gate after both perf instances acknowledged enable, to scope exit |
| Analyzer SHA | `31c492b25f13b5178b1dfd91aeb2dbe4cbe1fd86` (one SHA across every aggregated episode, V3 included; checked) |
| Analyzer source sha256 | `298e417a3dc3dbd0591380ccc36f6986b6c3aeb2e83c4d5a582759bcbd2dce22` |
| perf | perf version 6.8.12 |

## Lower bounds: what each number means

* Footprint and unique taken branches count only what the samples saw. Each taken-branch execution is captured with probability 32/20011 (about 0.16 %), so code that runs rarely is missed. Both are sampled LOWER BOUNDS.
* `wavg_targets_*` (Rahul's literal metric 3) is a sampled LOWER BOUND too. Its T_b is a unique count, the number of distinct targets seen, and a rarely taken target is missed like a rarely taken branch. The contract called metric 3 robust to sampling; V2 refutes that for the literal form (-61.1 % on v2_python, -48.4 % on v2_gcc_train, -47.9 % on v2_gxx, all branches). The weights C_b are not the cause: LBR's sampled C_b with PT's exact T_b gives +0.5 % (v2_python), -0.1 % (v2_gcc_train), -0.5 % (v2_gxx), so the error is all in T_b.
* `weff_targets_*` (inverse Simpson: the effective number of targets) and `wavg_targets_ge1pct_*` (targets carrying >= 1 % of the branch's executions) estimate frequency-weighted quantities. A target counts by its share of the executions, so the rare targets that sampling misses carry almost no weight, and the T_b bias does not arise. On V2 they are within 4.4 % of PT (18 values over 3 program(s)).
* Which of the three target metrics goes in the figure is Rahul's call. All three are in the long CSV.
* A separate C_b bias existed under contract v1 and is gone in v1.1 (V1 section below).
* The same period in every family makes the sampling bias comparable across families; it is largest for flat, tail-heavy profiles.

V2 measures the bias against an exact Intel PT trace of the same command (user-space, file-backed code). Recall = share of what PT proved executed that LBR also saw.

| Program | LBR samples | Footprint recall | Branch recall | Precision (lines / branches) | PT reference |
|---|---|---|---|---|---|
| v2_python | 47207 | 0.257 (PT 16847 lines) | 0.170 (PT 28860) | 1.000 / 0.999 | valid |
| v2_gcc_train | 87397 | 0.490 (PT 73691 lines) | 0.424 (PT 127432) | 0.999 / 0.999 | valid |
| v2_gxx | 73363 | 0.534 (PT 100951 lines) | 0.387 (PT 219468) | 1.000 / 1.000 | valid |

Relative error of the target metrics, LBR vs PT (same branches, user space):

| Program | Metric | all | noret | indirect |
|---|---|---|---|---|
| v2_python | literal `wavg_targets_*` | -61.1 % | -42.6 % | -55.1 % |
| v2_python | literal, LBR C_b x PT T_b | +0.5 % | +0.7 % | +0.8 % |
| v2_python | inverse Simpson `weff_targets_*` | -0.1 % | -0.1 % | -0.3 % |
| v2_python | >= 1 % `wavg_targets_ge1pct_*` | -0.0 % | +0.2 % | +0.3 % |
| v2_gcc_train | literal `wavg_targets_*` | -48.4 % | -5.4 % | -27.2 % |
| v2_gcc_train | literal, LBR C_b x PT T_b | -0.1 % | -0.1 % | -0.4 % |
| v2_gcc_train | inverse Simpson `weff_targets_*` | +0.1 % | -0.0 % | -0.1 % |
| v2_gcc_train | >= 1 % `wavg_targets_ge1pct_*` | -1.3 % | -0.3 % | -1.9 % |
| v2_gxx | literal `wavg_targets_*` | -47.9 % | -9.6 % | -28.7 % |
| v2_gxx | literal, LBR C_b x PT T_b | -0.5 % | +0.1 % | -0.4 % |
| v2_gxx | inverse Simpson `weff_targets_*` | -0.1 % | +0.0 % | -0.1 % |
| v2_gxx | >= 1 % `wavg_targets_ge1pct_*` | -0.2 % | -0.8 % | -4.4 % |

The V2 programs run 1-4 s. Recall depends on how often code runs, so it is a reference point for the size of the bias, not a correction factor: do not scale the numbers by it.

Convergence: each unique count is recomputed at 75 % and 100 % of the samples. Growth over the last quarter above 2 % marks the count `sampling_limited` (still rising). Over the 26 aggregated workloads:

* `footprint_bytes`: sampling_limited on 26 of 26; growth median 7.66 %, max 75.50 % (727.cppcheck_r).
* `footprint_bytes_user`: sampling_limited on 22 of 26; growth median 4.55 %, max 85.01 % (727.cppcheck_r).
* `footprint_bytes_kernel`: sampling_limited on 26 of 26; growth median 9.78 %, max 26.49 % (737.gmsh_r).
* `unique_taken_branches`: sampling_limited on 26 of 26; growth median 8.07 %, max 78.63 % (727.cppcheck_r).
* `unique_taken_branches_user`: sampling_limited on 23 of 26; growth median 5.53 %, max 85.39 % (727.cppcheck_r).
* `unique_taken_branches_kernel`: sampling_limited on 26 of 26; growth median 9.62 %, max 28.49 % (737.gmsh_r).

## V3: period sensitivity (period 5003 / period 20011)

Four times denser sampling. A ratio above 1 means the period-20011 value is sampling-limited.

| Benchmark | status | footprint | fp user | fp kernel | unique br | br user | br kernel |
|---|---|---|---|---|---|---|---|
| 736.ocio_r | ok | 1.519 | 1.722 | 1.390 | 1.593 | 1.802 | 1.462 |
| 721.gcc_r | ok | 1.136 | 1.131 | 1.253 | 1.171 | 1.168 | 1.270 |
| 749.fotonik3d_r | ok | 1.252 | 1.190 | 1.316 | 1.283 | 1.228 | 1.316 |

| Benchmark | status | literal all | literal noret | literal indirect | weff all | weff noret | weff indirect | ge1pct all | ge1pct noret | ge1pct indirect |
|---|---|---|---|---|---|---|---|---|---|---|
| 736.ocio_r | ok | 1.051 | 1.000 | 1.000 | 1.000 | 1.000 | 0.999 | 1.001 | 1.000 | 1.000 |
| 721.gcc_r | ok | 1.134 | 1.013 | 1.067 | 1.001 | 1.000 | 1.002 | 1.004 | 1.000 | 1.002 |
| 749.fotonik3d_r | ok | 1.009 | 1.000 | 1.013 | 1.000 | 1.000 | 0.999 | 1.000 | 1.000 | 0.997 |

## V1: synthetic truth

PASS (`~/spec26-infra/infra/data_frontend_footprint_validation/v1`): footprint 368 lines (expected 368), unique taken branches 541 (expected 541), literal weighted averages +0.00 %, -0.00 %, +0.05 % (all, noret, indirect; gate 1 %). The least-sampled V1 branch has 1383 sampled executions and every T_b is exact (`branches_target_count_mismatch` empty), so V1 tests C_b, not T_b. Analyzer source of the V1 run: same source as production.

Defect found and fixed (not a gate result): under contract v1 (bare event, `~/spec26-infra/infra/data_frontend_footprint_validation/v1_contract_v1_bare_event`) the LBR was frozen at the PMI after interrupt skid, which biased which 32-branch windows were sampled, i.e. C_b. V1 read the literal weighted averages -1.8 %, -2.0 %, -3.7 % (all, noret, indirect) while T_b and the unique counts were exact: a C_b bias, separate from the T_b bias above. Contract v1.1 samples with `:pp`, where PEBS writes the LBR at the overflowing branch, and the bias is gone. No production episode used the v1 event (checked).

## V4 and the August reference

* All 26 aggregated workloads passed V4 (exit 0, output check, lost < 1 %, sample coverage within 2 %, no throttling, occupancy). Witness clean on 26 of 26; ISO-PROOF recorded on 26 of 26.
* Wall time vs August (LBR overhead; guide: within ~10 %): within on 26 of 26; deviation median +1.4 %, range -2.9 to +5.4 %.
* IPC / August IPC, all workloads: median 0.99, range 0.97-1.05 (n=26). Instructions / August extrapolated instructions: median 1.09, range 1.04-1.10 (n=26). August counted in windows only (`raw_sums.seconds` of `wall_s`), so (a) carries the windowing error; (b) does not depend on it.
* The guide's gate "instructions within 1 % of August" for the 3 benchmarks whose SPEC output cannot be verified is NOT evaluable: August has no whole-run instruction total. Reported as `NO_PROOF` with two labelled substitutes:

| Benchmark | output_check | (a) instr / August extrapolated | (b) IPC / August IPC | wall dev |
|---|---|---|---|---|
| 734.vpr_r | unavailable | 1.0832 | 0.9943 | +2.1 % |
| 735.gem5_r | unavailable | 1.0751 | 0.9858 | +3.7 % |
| 772.marian_r | unavailable | 1.0894 | 0.9801 | +4.3 % |

## Wrapper code inside the fence

The fence also holds the `runuser` parent and the `bash` that waits on the start FIFO and then execs the benchmark. Their code is inside every number. Below: footprint and unique taken branches in `/usr/bin/bash` and in `runuser` (its binary plus its anonymous pages), from `top_objects_by_footprint` and `top_processes`. Kernel and shared-library code (ld.so, libc) that they ran cannot be separated from the benchmark's, so these are lower bounds of the wrapper's share.

| Workload | bash KB | bash branches | runuser KB | runuser branches | share of footprint | share of branches | runuser samples |
|---|---|---|---|---|---|---|---|
| 706.stockfish_r | 4.9 | 72 | 2.2 | 32 | 2.66 % | 2.07 % | 0.0005 % |
| 707.ntest_r | 4.4 | 76 | 1.3 | 25 | 1.85 % | 1.81 % | 0.0001 % |
| 708.sqlite_r | 1.9 | 28 | 0.4 | 13 | 0.82 % | 0.76 % | 0.0002 % |
| 709.cactus_r | 2.7 | 42 | 2.2 | 39 | 1.25 % | 1.37 % | 0.0024 % |
| 710.omnetpp_r | 3.1 | 45 | 2.7 | 41 | 1.31 % | 0.90 % | 0.0004 % |
| 714.cpython_r | 3.3 | 52 | 0.8 | 11 | 0.63 % | 0.46 % | 0.0002 % |
| 721.gcc_r | 4.2 | 63 | 3.6 | 62 | 0.16 % | 0.09 % | 0.0003 % |
| 722.palm_r | 2.8 | 43 | 4.2 | 74 | 1.17 % | 1.67 % | 0.0002 % |
| 723.llvm_r | 3.3 | 50 | 0.0 | 0 | 0.09 % | 0.05 % | 0.0002 % |
| 727.cppcheck_r | 3.0 | 47 | 0.0 | 0 | 0.26 % | 0.16 % | 0.0003 % |
| 729.abc_r | 4.2 | 62 | 0.6 | 8 | 2.90 % | 2.39 % | 0.0042 % |
| 731.astcenc_r | 1.9 | 28 | 1.3 | 25 | 0.97 % | 1.09 % | 0.0006 % |
| 734.vpr_r | 5.8 | 97 | 3.3 | 51 | 1.28 % | 0.97 % | 0.0005 % |
| 735.gem5_r | 4.7 | 75 | 0.0 | 0 | 0.47 % | 0.35 % | 0.0006 % |
| 736.ocio_r | 3.2 | 49 | 0.0 | 0 | 1.46 % | 1.28 % | 0.0038 % |
| 737.gmsh_r | 4.7 | 71 | 1.9 | 27 | 1.09 % | 0.81 % | 0.0007 % |
| 748.flightdm_r | 2.9 | 44 | 0.0 | 0 | 1.34 % | 1.21 % | 0.0012 % |
| 749.fotonik3d_r | 3.5 | 53 | 0.0 | 0 | 0.98 % | 1.05 % | 0.0006 % |
| 750.sealcrypto_r | 4.2 | 59 | 2.4 | 42 | 2.61 % | 2.56 % | 0.0002 % |
| 753.ns3_r | 3.1 | 53 | 2.0 | 36 | 0.83 % | 0.68 % | 0.0005 % |
| 765.roms_r | 3.0 | 49 | 0.0 | 0 | 0.45 % | 0.69 % | 0.0002 % |
| 766.femflow_r | 6.3 | 91 | 0.0 | 0 | 0.66 % | 0.70 % | 0.0004 % |
| 767.nest_r | 3.3 | 56 | 0.8 | 12 | 1.41 % | 1.33 % | 0.0011 % |
| 772.marian_r | 3.4 | 54 | 3.3 | 50 | 1.12 % | 0.95 % | 0.0004 % |
| 777.zstd_r | 4.0 | 64 | 0.0 | 0 | 1.63 % | 1.53 % | 0.0014 % |
| 782.lbm_r | 2.6 | 41 | 0.0 | 0 | 1.60 % | 1.45 % | 0.0029 % |

Share of footprint: median 1.15 %, range 0.09-2.90 % (n=26).

Kernel share of the footprint: median 38.63 %, range 4.61-93.53 % (n=26).

## Files

| File | What |
|---|---|
| `per_benchmark/<workload>.summary.json` | the episode's summary.json, copied (aggregated episodes only): analyzer output plus `workload`, `capture`, `exact_counts`, `gates_v4` |
| `frontend_footprint_rows_long.csv` | one row per (workload, metric); aggregated workloads only |
| `gates.csv` | one row per workload: V4, convergence, August, wrapper, V3 |
| `gates_global.csv` | V1, V2 per program, V3 per benchmark, analyzer identity |
| `plots/` | preliminary SPEC-only violins, one per headline metric: footprint, unique branches, and the three target metrics (literal, weff, ge1pct) for all / noret / indirect (`plot_frontend_footprint.py`) |

## `frontend_footprint_rows_long.csv`

Columns: `workload,family,subgroup,metric,value,analyzer_sha,period`. `family`/`subgroup` as in `workload_index.csv`. `analyzer_sha` = the analyzer commit. `period` = sampling period. An empty `value` = undefined (no branch of that kind was sampled). The `weff_targets_*` and `wavg_targets_ge1pct_*` rows exist only when the analyzer emitted them (older summaries lack them). The Server and Agentic CSVs use the same metric names, so one plotting script reads all three. Bytes are B; KB in the text and plots = 1000 B.

| Metric | Definition |
|---|---|
| `footprint_bytes` | 64 x unique 64 B instruction lines seen executing (user + kernel) |
| `footprint_bytes_user` | same, user-space lines only |
| `footprint_bytes_kernel` | same, kernel lines only (address >= 0xffff800000000000) |
| `unique_taken_branches` | distinct near taken branch instructions (canonical `from`), user + kernel |
| `unique_taken_branches_user` | same, user space |
| `unique_taken_branches_kernel` | same, kernel |
| `unique_taken_branches_COND` | unique taken branches of type COND (user + kernel) |
| `unique_taken_branches_UNCOND` | unique taken branches of type UNCOND (user + kernel) |
| `unique_taken_branches_CALL` | unique taken branches of type CALL (user + kernel) |
| `unique_taken_branches_IND_CALL` | unique taken branches of type IND_CALL (user + kernel) |
| `unique_taken_branches_IND` | unique taken branches of type IND (user + kernel) |
| `unique_taken_branches_RET` | unique taken branches of type RET (user + kernel) |
| `wavg_targets_all` | sum(C_b*T_b)/sum(C_b) over all near taken branches; C_b = sampled executions, T_b = distinct targets seen (Rahul's literal metric; sampled LOWER BOUND, T_b is a unique count) |
| `wavg_targets_all_user` | same, user-space branches only |
| `wavg_targets_noret` | same, returns excluded (the return stack predicts them, not the BTB) |
| `wavg_targets_noret_user` | same, user space |
| `wavg_targets_indirect` | same, indirect jumps and calls only (IND, IND_CALL) |
| `wavg_targets_indirect_user` | same, user space |
| `weff_targets_all` | sum(C_b*E_b)/sum(C_b), E_b = 1/sum_t(p_bt^2) (inverse Simpson: effective number of targets), p_bt = share of branch b's executions that went to target t; all near taken branches |
| `weff_targets_all_user` | same, user space |
| `weff_targets_noret` | same, returns excluded |
| `weff_targets_noret_user` | same, user space |
| `weff_targets_indirect` | same, indirect jumps and calls only |
| `weff_targets_indirect_user` | same, user space |
| `wavg_targets_ge1pct_all` | sum(C_b*K_b)/sum(C_b), K_b = number of targets with p_bt >= 0.01; all near taken branches |
| `wavg_targets_ge1pct_all_user` | same, user space |
| `wavg_targets_ge1pct_noret` | same, returns excluded |
| `wavg_targets_ge1pct_noret_user` | same, user space |
| `wavg_targets_ge1pct_indirect` | same, indirect jumps and calls only |
| `wavg_targets_ge1pct_indirect_user` | same, user space |

All unique counts are sampled lower bounds (above). Canonical addresses: file-backed code is keyed by (path, inode) + file offset, so a shared library counts once across processes; kernel by address; anonymous/JIT code by (pid, address).

## `gates.csv`

Booleans are 1/0; empty = not available.

| Column | Meaning |
|---|---|
| `workload` | benchmark (`<bench>@<k>` = ref command line k; extra rows, never replacements) |
| `family` | `--family` |
| `subgroup` | from `workload_index.csv` (SPEC-int / SPEC-fp) |
| `expected` | 1 if the workload is in the `--expect` list |
| `status` | ok = DONE, every V4 gate passed and the event/period match the contract (only these reach the long CSV); gate_failed = summary.json without DONE, or a failed gate; contract_mismatch; incomplete = episode dir without summary.json; missing = no episode dir |
| `in_long_csv` | 1 if the workload's rows are in the long CSV |
| `analyzer_sha` | `analyzer_sha` in summary.json |
| `period` | sampling period of the episode |
| `event` | sampling event of the episode |
| `contract_ok` | 1 if event = `br_inst_retired.near_taken:pp` and period = 20011 |
| `exit_status` | benchmark exit status |
| `output_check` | SPEC output check: pass / fail / unavailable / error |
| `output_ok` | pass, or unavailable (the 3 benchmarks SPEC cannot verify as one command) |
| `lost_pct` | lost samples / (samples + lost), % |
| `lost_ok` | lost_pct < 1 |
| `sample_coverage` | samples x period / exact `br_inst_retired.near_taken`; 1 = no sample dropped |
| `coverage_ok` | abs(sample_coverage - 1) <= 0.02 |
| `throttle_events` | perf THROTTLE records |
| `throttle_ok` | 0 THROTTLE records and perf's record stats were read |
| `mean_cores` | fence occupancy from the 10 Hz cpu.stat poller, cores |
| `occupancy_ok` | mean_cores <= the driver's MAX_MEAN_CORES |
| `witness_rows` | 2 s whole-machine witness rows during the episode |
| `witness_foreign_rows` | witness rows with a foreign task above 10 % CPU |
| `witness_mean_foreign_cpu_pct` | mean foreign CPU over the witness rows, % |
| `witness_clean` | driver's rule: rows > 0, foreign rows <= 5 % of rows, mean foreign CPU <= 25 % |
| `iso_proof_present` | 1 if an ISO-PROOF line is recorded |
| `analyzer_ok` | analyzer exit 0 and no `error` key |
| `v4_all_ok` | driver's `gates_v4.all_ok` |
| `contaminated_attempts` | set-aside attempts `<workload>.contaminated.N` (never aggregated) |
| `conv_growth_pct_<m>` | 100 x (m at 100 % of the samples - m at 75 %) / m at 100 %; m in `footprint_bytes`, `footprint_bytes_user`, `footprint_bytes_kernel`, `unique_taken_branches`, `unique_taken_branches_user`, `unique_taken_branches_kernel` |
| `conv_<m>` | sampling_limited if conv_growth_pct_<m> > 2, else converged; m in `footprint_bytes`, `footprint_bytes_user`, `footprint_bytes_kernel`, `unique_taken_branches`, `unique_taken_branches_user`, `unique_taken_branches_kernel` |
| `sampling_limited` | the unique metrics marked sampling_limited, `;`-separated |
| `wall_s` | benchmark wall time, release to exit, s |
| `aug_wall_s` | August campaign wall time, s |
| `wall_dev_pct` | 100 x (wall_s / aug_wall_s - 1); LBR sampling overhead |
| `wall_within_10pct` | abs(wall_dev_pct) <= 10 |
| `instructions` | exact instructions, `perf stat` on the fence over the window |
| `cycles` | exact cycles, same |
| `ipc` | instructions / cycles |
| `aug_ipc` | August `metrics.IPC` (windowed) |
| `ipc_ratio` | substitute (b): ipc / aug_ipc |
| `aug_instructions_extrap` | August `raw_sums.instructions` x wall_s / `raw_sums.seconds` (windowed counts scaled to the run) |
| `instr_ratio_extrap` | substitute (a): instructions / aug_instructions_extrap |
| `output_unverifiable` | 1 for benchmarks whose SPEC output cannot be checked (output_check unavailable) |
| `aug_instr_1pct_gate` | guide's 'instructions within 1 % of August' gate: NO_PROOF (August has no whole-run instruction total) where output_unverifiable, else not_required |
| `wrapper_bash_bytes` | footprint of /usr/bin/bash (the pre-exec shell in the fence), B |
| `wrapper_bash_branches` | unique taken branches in /usr/bin/bash |
| `wrapper_runuser_bytes` | footprint of the runuser binary plus anonymous code of runuser pids, B |
| `wrapper_runuser_branches` | unique taken branches in the same objects |
| `wrapper_bytes_pct` | 100 x (bash + runuser bytes) / footprint_bytes |
| `wrapper_branches_pct` | 100 x (bash + runuser branches) / unique_taken_branches |
| `runuser_sample_share_pct` | share of LBR samples taken in runuser processes, % |
| `wrapper_source` | top_objects (exact: list < 20 entries), tables (recomputed from objects/lines/edges.tsv.zst) or top_objects_partial (a wrapper object below the 20th entry counts 0) |
| `v3_status` | status of the period-5003 episode (blank = not in the V3 set) |
| `v3_contaminated_attempts` | set-aside attempts in the V3 root |
| `v3_ratio_<m>` | m at period 5003 / m at period 20011; m in `footprint_bytes`, `footprint_bytes_user`, `footprint_bytes_kernel`, `unique_taken_branches`, `unique_taken_branches_user`, `unique_taken_branches_kernel`, `wavg_targets_all`, `wavg_targets_noret`, `wavg_targets_indirect`, `weff_targets_all`, `weff_targets_noret`, `weff_targets_indirect`, `wavg_targets_ge1pct_all`, `wavg_targets_ge1pct_noret`, `wavg_targets_ge1pct_indirect` |

## `gates_global.csv`

Columns: `gate,name,metric,value,threshold,verdict,source`. Gates: `V1` (synthetic truth), `V1_defect` (the failed contract-v1 run, kept as the record of the defect), `V2` (one name per program: recall, precision, PT and LBR set sizes, relative error of the literal, weff and ge1pct target metrics and of the literal metric with LBR's C_b and PT's T_b (`*_rel_err_lbr_C_pt_T`), recall at 25/50/75 % of the LBR samples; the contract sets no pass threshold, so the verdict is REPORTED unless the PT reference is invalid), `V3` (ratios per benchmark), `analyzer` (SHA identity), `August` (the NO_PROOF gate and its substitutes). `pending` = input absent.

## Regenerate

```bash
python3 local_agents/kit/frontend_footprint/aggregate.py 
~/miniforge3/envs/infersuite-full/bin/python3 local_agents/kit/frontend_footprint/plot_frontend_footprint.py \
    spec26/frontend_footprint_x86/frontend_footprint_rows_long.csv --out spec26/frontend_footprint_x86/plots
```
