# Front-end footprint, x86, Server set — MANIFEST

Generated 2026-11-03 17:32 UTC by `local_agents/kit/frontend_footprint/aggregate_server.py` from `local_agents/DCPerf/data/frontend_footprint`, `local_agents/JVMbench/data/frontend_footprint`, `local_agents/RealData/data/frontend_footprint` (pass dirs `<family>_<workload>/run_1`). Do not edit by hand: regenerate (last section).

Three numbers per workload, for Rahul's front-end question: instruction footprint, unique taken branches, and the weighted average number of targets per taken branch, for the realistic Server set. The method is `docs/handoff/execution/frontend_footprint_method.md` (the contract), the capture `docs/handoff/execution/x86_server_footprint.md`. The analyzer, the metric definitions and the long-CSV schema are SPEC's (`spec26/frontend_footprint_x86/MANIFEST.md` on `origin/spec-x86` @ `86b22c734862`; report `docs/reports/23_spec26_frontend_footprint_x86.md` there).

## Population

* Expected: 10 workloads (`in_realistic_server_set = 1` in `local_agents/RealData/data/l3_study/workload_index.csv`).
* Aggregated (status ok): 10. By family: dcperf 1, dacapo 1, renaissance 2, realdata 6.
* Sibling dirs not named `run_1` (never read): feedsim: run_1.smoke_nonroot_unmapped.

## Contract and analyzer

| Parameter | Value |
|---|---|
| Contract | v1.1 (2026-11-03) |
| Event | `br_inst_retired.near_taken:pp` (PEBS; user + kernel). Seen: `br_inst_retired.near_taken:pp` |
| Period | `-c 20011`. Seen: `20011` |
| Branch filter | `-j any,save_type`. Seen: `any,save_type` |
| Scope | the server's fence cgroup, `perf record -a -C <measured> --cgroup=<fence>`; client outside the fence as in the counter passes; measured cores `4-11` |
| Window | steady state, after the liveness check, for CAPTURE_S s (caveat 1). Seen: `180`, `300` s |
| Analyzer SHA | `31c492b25f13b5178b1dfd91aeb2dbe4cbe1fd86` (one SHA across every pass with a summary; checked). SPEC's: `31c492b25f13b5178b1dfd91aeb2dbe4cbe1fd86` |
| Analyzer source sha256 | required `298e417a3dc3dbd0591380ccc36f6986b6c3aeb2e83c4d5a582759bcbd2dce22` (SPEC's). Seen: `298e417a3dc3dbd0591380ccc36f6986b6c3aeb2e83c4d5a582759bcbd2dce22` |
| perf | `perf version 6.8.12` |
| JDK on PATH | `openjdk version "21.0.12.1" 2026-08-18` |

## Validation gates V1-V3: SPEC's, not re-run

V1 (synthetic truth) and V2 (exact Intel PT cross-check) validate the analyzer; V3 (period 5003 vs 20011) validates the period. The Server runs the same analyzer source (sha256 checked per pass, `analyzer_src_ok`) at the same period, so their results carry over unchanged. They are not copied here: see `spec26/frontend_footprint_x86/gates_global.csv` on `origin/spec-x86` @ `86b22c734862`, the lower-bound section of `spec26/frontend_footprint_x86/MANIFEST.md` on `origin/spec-x86` @ `86b22c734862`, and report `docs/reports/23_spec26_frontend_footprint_x86.md` on the same commit. V4 (capture hygiene) is per pass: `gates.csv`.

## Caveats (Server-specific; numbers from the aggregated passes)

Every unique count is a sampled LOWER BOUND, and the literal `wavg_targets_*` too (its T_b is a unique count); `weff_targets_*` and `wavg_targets_ge1pct_*` are frequency-weighted. Same sampling and analyzer as SPEC, so SPEC's V2 measurement of that bias applies (see above). In addition:

1. **The window is a steady state, not a whole run.** Each pass samples the server for CAPTURE_S seconds after the liveness check (the same window and length as the workload's banked counter passes), not from start to exit. Aggregated passes: 300 s: feedsim; 180 s: tomcat, finagle-chirper, finagle-http, cassandra-ycsb20m, kafka-20g, naivebayes-rcv1, neo4j-livejournal, pagerank-livejournal, video-4k; measured window median 180.0 s, range 180.0-300.0 s (n=10). Capture length equal to the banked counter passes' on 10 of the 10 aggregated passes with banked passes. Banked CAPTURE_S of the expected set: 300 s: feedsim; 180 s: tomcat, finagle-chirper, finagle-http, cassandra-ycsb20m, kafka-20g, naivebayes-rcv1, neo4j-livejournal, pagerank-livejournal, video-4k. SPEC's numbers cover whole runs of median 70 s, range 10-329 s (n=26) (`spec26/frontend_footprint_x86/gates.csv` on `origin/spec-x86` @ `86b22c734862`, `wall_s`). Unique counts grow with the window: over the last quarter of the samples, `footprint_bytes` grew median 6.48 %, max 8.19 % (finagle-http) and `unique_taken_branches` median 6.61 %, max 9.20 % (tomcat) (sampling_limited on 8 and 8 of 10). So Server and SPEC footprints and unique-branch counts are not comparable in absolute terms unless it is said that one is a fixed steady-state window and the other a whole run. The literal `wavg_targets_*` also accumulates (T_b); `weff_targets_*` and `wavg_targets_ge1pct_*` are averages over executions, not counts. Sample-matched (`sample_matched.csv`, n=10): over each pass's first 1,519,787 samples, SPEC's median samples per run, the Server medians are footprint 2,522 KB and unique taken branches 49,090, against 4,765 KB and 89,134 over the whole window.
2. **Several processes in one fence: file-backed code is canonicalised by (path, inode).** A binary or library that runs in many processes (video-4k's `ffmpeg` processes, a JVM's helper processes) counts once: its key is (path, inode) + file offset, not the virtual address. Processes with samples: video-4k 29 (top: ffmpeg 13.5 % of samples; ffmpeg x12, sh x4, time x3, parallel x1 among the 20 busiest), neo4j-livejournal 2 (top: java 100.0 % of samples; java x2 among the 2 busiest); one process: feedsim, tomcat, finagle-chirper, finagle-http, cassandra-ycsb20m, kafka-20g, naivebayes-rcv1, pagerank-livejournal. Share of the footprint in file-backed code: median 33.5 %, range 18.2-86.8 % (n=10).
3. **JIT code is keyed per process.** Anonymous executable memory (the JVM's JIT code cache, and any user address no mapping covers) is keyed (pid, address) and never merged across processes; each exec starts a new key space. Within a process the key is the address, so code the JIT recompiles or moves counts again at each new address, and different code later placed at a freed address counts once: neither is visible from LBR addresses. Share of the footprint in anonymous code: naivebayes-rcv1 77.6 % (65.0 % of the branches, 1 process(es)), finagle-chirper 63.4 % (46.8 % of the branches, 1 process(es)), tomcat 62.3 % (52.2 % of the branches, 1 process(es)), finagle-http 61.7 % (46.3 % of the branches, 1 process(es)), pagerank-livejournal 59.0 % (42.6 % of the branches, 1 process(es)), neo4j-livejournal 53.2 % (36.7 % of the branches, 2 process(es)), cassandra-ycsb20m 45.6 % (30.4 % of the branches, 1 process(es)), kafka-20g 45.0 % (29.8 % of the branches, 1 process(es)), video-4k 0.2 % (0.2 % of the branches, 1 process(es)), feedsim 0.0 % (0.0 % of the branches, 0 process(es)). Unmapped user entries, also keyed as anonymous, are bounded by gate `mapped_ok` (< 1 % of entries): median 0.000 %, range 0.000-0.000 % (n=10).
4. **Kernel share.** Kernel share of the footprint, Server: median 10.7 %, range 4.3-29.0 % (n=10); SPEC: median 38.6 %, range 4.6-93.5 % (n=26). Of the unique taken branches, Server: median 11.3 %, range 5.2-38.1 % (n=10); SPEC: median 47.7 %, range 3.0-95.3 % (n=26) (`spec26_rows_long.csv`). Only kernel code run while a fence task is current is sampled (`--cgroup` filters on the running task): its system calls, page faults, and interrupts that land on it. Kernel threads (kworker, ksoftirqd, ...) belong to no fence and are not sampled, nor is work done on the house cores (the client's side of the network stack). Measured-partition busy time not explained by the fence (D5 residual): median 0.0 %, range 0.0-9.4 % (n=10).
5. **Receipt basis.** The workload served as in the banked counter passes (`receipt_ok`); for video-4k the evidence is the fence load (a batch without a throughput receipt by design). Receipt ratio new / banked median: median 1.002, range 0.829-1.023 (n=9). **cassandra-ycsb20m: receipt gate failed (ratio 0.8286330975) and was accepted by a recorded decision of Jerry (Tianrui), in the session chat** (`receipt_override.json` in its run dir): YCSB throughput is below the banked band only because the store degrades monotonically with every pass (the guide: reuse the Cassandra store as-is, rebuild only on Jerry's say-so). The 9 counter passes ran on the same aging store, so this pass is consistent with them.

Convergence (the SPEC rule): each unique count is recomputed at 75 % and 100 % of the samples; growth over the last quarter above 2 % marks it `sampling_limited`. Over the 10 aggregated passes:

* `footprint_bytes`: sampling_limited on 8 of 10; growth median 6.48 %, max 8.19 % (finagle-http).
* `footprint_bytes_user`: sampling_limited on 8 of 10; growth median 6.79 %, max 8.52 % (finagle-http).
* `footprint_bytes_kernel`: sampling_limited on 4 of 10; growth median 1.78 %, max 4.82 % (finagle-http).
* `unique_taken_branches`: sampling_limited on 8 of 10; growth median 6.61 %, max 9.20 % (tomcat).
* `unique_taken_branches_user`: sampling_limited on 8 of 10; growth median 6.95 %, max 9.83 % (tomcat).
* `unique_taken_branches_kernel`: sampling_limited on 6 of 10; growth median 2.22 %, max 5.48 % (finagle-http).

Per aggregated pass:

| Workload | Family | CAPTURE_S | window s | footprint KB | kernel % | file-backed % | anonymous % | processes | top process | unmapped % | footprint growth, last quarter |
|---|---|---|---|---|---|---|---|---|---|---|---|
| feedsim | dcperf | 300 | 300.0 | 2137.1 | 13.2 | 86.8 | 0.0 | 1 | LeafNodeRank | 0.000 | 0.11 % |
| tomcat | dacapo | 180 | 180.0 | 7744.4 | 7.2 | 30.5 | 62.3 | 1 | java | 0.000 | 7.44 % |
| finagle-chirper | renaissance | 180 | 180.0 | 6650.4 | 8.9 | 27.7 | 63.4 | 1 | java | 0.000 | 2.51 % |
| finagle-http | renaissance | 180 | 180.0 | 5807.7 | 8.7 | 29.5 | 61.7 | 1 | java | 0.000 | 8.19 % |
| cassandra-ycsb20m | realdata | 180 | 180.0 | 4305.4 | 13.3 | 41.1 | 45.6 | 1 | java | 0.000 | 6.90 % |
| kafka-20g | realdata | 180 | 180.0 | 3271.5 | 16.5 | 38.5 | 45.0 | 1 | java | 0.000 | 7.59 % |
| naivebayes-rcv1 | realdata | 180 | 180.0 | 11970.8 | 4.3 | 18.2 | 77.6 | 1 | java | 0.000 | 6.59 % |
| neo4j-livejournal | realdata | 180 | 180.0 | 3291.5 | 12.5 | 34.3 | 53.2 | 2 | java | 0.000 | 5.64 % |
| pagerank-livejournal | realdata | 180 | 180.0 | 5223.9 | 8.2 | 32.8 | 59.0 | 1 | java | 0.000 | 6.37 % |
| video-4k | realdata | 180 | 180.0 | 1757.2 | 29.0 | 70.8 | 0.2 | 29 | ffmpeg | 0.000 | 0.82 % |

## Files

| File | What |
|---|---|
| `<workload>/summary.json` | the pass's summary.json, copied (aggregated passes only): analyzer output plus `workload`, `capture`, `exact_counts`, `gates_v4` (lbr_pass_gates.py) |
| `frontend_footprint_rows_long.csv` | one row per (workload, metric); aggregated passes only |
| `gates.csv` | one row per expected workload: gates_v4 flattened, convergence, composition, status |
| `gates_global.csv` | analyzer and contract identity; pointers to SPEC's V1-V3 |
| `spec26_rows_long.csv` | byte copy of `spec26/frontend_footprint_x86/frontend_footprint_rows_long.csv` at `origin/spec-x86` = commit `86b22c734862d71e76c953803a816e8da6231dd9` (sha256 `d3ca506dc31bb61efd57cc3480407846e07689122956e5ab0663b5503b4b3cec`), so the combined figure regenerates on this branch |
| `sample_matched.csv` | each pass's footprint and unique taken branches over its first N samples, N = SPEC's median and maximum samples per run (`sample_matched.py`, from the tables' `first_seen`; not written here) |
| `plots/` | violins from `plot_frontend_footprint.py`: `server_by_family/` (`--group family`), `spec_vs_server/` (`--group side`, SPEC + Server); on log panels the diamond is the geometric mean (not written here) |

## `frontend_footprint_rows_long.csv`

Columns: `workload,family,subgroup,metric,value,analyzer_sha,period,capture_s`: SPEC's schema plus `capture_s` (the pass's window, s; the plotter ignores extra columns). `family`/`subgroup` as in `workload_index.csv`. The metric names, their order, and the value formatting are SPEC's (aggregate.py), so one plotting script reads SPEC, Server and Agentic. An empty `value` = undefined (no branch of that kind was sampled). Bytes are B; KB in the text and plots = 1000 B.

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

Canonical addresses: file-backed code is keyed by (path, inode) + file offset, so a shared library counts once across processes; kernel by address; anonymous/JIT code by (pid, address).

## `gates.csv`

Booleans are 1/0; empty = not available. Gate thresholds are lbr_pass_gates.py's.

| Column | Meaning |
|---|---|
| `workload` | workload name as in `workload_index.csv` |
| `family` | `workload_index.csv` family (dcperf / dacapo / renaissance / realdata); the pass dir is `<family>_<workload>` |
| `subgroup` | `workload_index.csv` subgroup |
| `status` | ok = DONE exists, `gates_v4.all_ok` is true, the event/period/filter match the contract and the analyzer source is SPEC's (only these reach the long CSV); gate_failed = summary.json present but any of those fails; incomplete = run dir without summary.json (pass running, or aborted before its gates); missing = no run dir |
| `why` | reasons for a status other than ok, `;`-separated (failed `gates_v4.*_ok` keys by name) |
| `in_long_csv` | 1 if the workload's rows are in the long CSV |
| `pass_dir` | the pass directory read |
| `ignored_dirs` | sibling dirs not named exactly `--run-name` (e.g. a failed smoke kept as defect evidence); never read |
| `done` | 1 if `DONE` exists (lbr_pass.sh writes it only when every gate passed) |
| `analyzer_sha` | `analyzer_sha` in summary.json (the analyzer commit) |
| `analyzer_src_ok` | 1 if `analyzer_src_sha256` = `298e417a3dc3dbd0591380ccc36f6986b6c3aeb2e83c4d5a582759bcbd2dce22` (the SPEC run's analyzer source) |
| `event` | sampling event, `capture.frontend_footprint.event` |
| `period` | sampling period, `capture.frontend_footprint.period` |
| `branch_filter` | LBR filter, `capture.frontend_footprint.branch_filter` |
| `contract_ok` | 1 if event = `br_inst_retired.near_taken:pp`, period = 20011 and filter = `any,save_type` |
| `capture_s` | CAPTURE_S of the pass: the steady-state window requested, s |
| `window_s` | measured window: `ts_end - ts_start` of the perf enable/disable acknowledgements, s |
| `capture_s_banked` | CAPTURE_S of the workload's banked counter passes (`<family>_<workload>/run_*/metadata.json`), `;`-separated if several |
| `capture_s_match` | 1 if capture_s equals every banked value (the guide's comparability rule; reported, not gated) |
| `samples` | LBR samples (`diagnostics.samples`) |
| `lost_pct` | lost samples / (samples + lost), % |
| `lost_ok` | lost_pct < 1 |
| `sample_coverage` | samples x period / exact `br_inst_retired.near_taken` (perf stat, same fence, nested window); 1 = no sample dropped |
| `coverage_ok` | abs(sample_coverage - 1) <= lbr_pass_gates.py `--cover-tol` (0.005 unless overridden; the value used is not banked) |
| `throttle_events` | THROTTLE records in `perf report --stats` (lbr_pass_gates.py sums both of its sections) |
| `throttle_ok` | 0 THROTTLE records and the stats were read |
| `alive_ok` | the server fence existed for the whole window |
| `unmapped_pct` | LBR entries at a user address no mapping covers, % of entries |
| `discontinuity_rate` | share of candidate straight-line ranges skipped (not in one mapping, negative or > 4096 B) |
| `mapped_ok` | unmapped_pct < 1 |
| `d4_first_fifth_cores` | D4: mean fence load over the first fifth of the window (10 s means of the 10 Hz cpu.stat), cores |
| `d4_last_fifth_cores` | D4: same, last fifth |
| `d4_drift_pct` | D4: 100 x abs(last - first) / max(first, last) |
| `d4_mean_cores` | D4: mean fence load over the window, cores |
| `d4_ok` | drift <= 25 % and mean load >= 0.10 cores |
| `d5_partition_core_s` | D5: measured-partition busy time over the window (/proc/stat), core-s |
| `d5_fence_core_s` | D5: fence CPU time over the window (cpu.stat), core-s |
| `d5_residual_pct` | D5: partition busy not explained by the fence, % of partition busy |
| `d5_ok` | residual <= 20 % |
| `witness_rows` | 2 s whole-machine witness rows in the window |
| `witness_foreign_rows` | witness rows with a foreign task above 10 % CPU (root kernel threads not counted) |
| `witness_mean_foreign_cpu_pct` | mean foreign CPU over the witness rows, % |
| `witness_clean` | aggregate.py's rule recomputed: rows > 0, foreign rows <= 5 % of rows, mean foreign CPU <= 25 % |
| `witness_ok` | `gates_v4.witness_ok` (the same rule, from the pass) |
| `receipt_metric` | the workload's throughput receipt (receipt_compare.py) |
| `receipt_unit` | its unit |
| `receipt_new` | this pass's value |
| `receipt_banked_median` | median over the banked counter passes |
| `receipt_banked_n` | number of banked passes with a receipt |
| `receipt_ratio` | receipt_new / receipt_banked_median |
| `receipt_comparable` | receipt_compare.py verdict (rule in `gates_v4.receipt.rule`) |
| `receipt_basis` | `workload receipt`, or `fence-load proxy` for a batch without a receipt by design (video-4k) |
| `overrides` | gates accepted by a recorded human decision (`<run>/receipt_override.json`); the gate's own column stays false |
| `override_by` | who decided the override |
| `override_reason` | why, as recorded in the run directory |
| `receipt_ok` | receipt comparable (or, for the fence-load proxy, fence load in band) |
| `fence_cores_new` | mean fence load of this pass (whole cpu.stat file), cores |
| `fence_cores_banked_median` | same, median over the banked counter passes |
| `fence_cores_in_band` | fence load within the receipt band (never gates, except as the proxy) |
| `iso_proof_present` | 1 if an ISO-PROOF line is recorded |
| `analyzer_ok` | analyzer exit 0 and no `error` key |
| `all_ok` | `gates_v4.all_ok`: every gate above |
| `conv_growth_pct_<m>` | 100 x (m at 100 % of the samples - m at 75 %) / m at 100 %; m in `footprint_bytes`, `footprint_bytes_user`, `footprint_bytes_kernel`, `unique_taken_branches`, `unique_taken_branches_user`, `unique_taken_branches_kernel` |
| `conv_<m>` | sampling_limited if conv_growth_pct_<m> > 2, else converged; m in `footprint_bytes`, `footprint_bytes_user`, `footprint_bytes_kernel`, `unique_taken_branches`, `unique_taken_branches_user`, `unique_taken_branches_kernel` |
| `sampling_limited` | the unique metrics marked sampling_limited, `;`-separated |
| `instructions` | exact instructions, `perf stat` on the fence over the window |
| `cycles` | exact cycles, same |
| `ipc` | instructions / cycles |
| `processes_with_samples` | processes with at least one LBR sample |
| `top_process` | comm of the process with most samples |
| `top_process_share_pct` | its share of the samples, % |
| `kernel_footprint_pct` | 100 x footprint_bytes_kernel / footprint_bytes |
| `kernel_branches_pct` | 100 x unique_taken_branches_kernel / unique_taken_branches |
| `file_footprint_pct` | share of the footprint in file-backed code (kinds file + special: keyed by (path, inode) + offset), % |
| `anon_footprint_pct` | share of the footprint in anonymous code (JIT, unmapped; keyed by (pid, address)), % |
| `anon_branches_pct` | share of the unique taken branches in anonymous code, % |
| `anon_processes` | processes with anonymous code in the footprint |
| `objects_source` | top_objects (exact: the list holds every object hit) or tables (recomputed from objects/lines/edges.tsv[.zst]); empty = neither available |

## `gates_global.csv`

Columns: `gate,name,metric,value,threshold,verdict,source`. Gates: `analyzer` (one SHA across the passes; source sha256 = SPEC's; SPEC's own SHA and source, read from its gates_global.csv), `contract` (event, period, filter seen), `V1`/`V2`/`V3` (NOT_RERUN: a pointer to SPEC's rows), `reference` (the commit and sha256 of `spec26_rows_long.csv`).

## Regenerate

```bash
python3 local_agents/kit/frontend_footprint/aggregate_server.py
~/miniforge3/envs/infersuite-full/bin/python3 local_agents/kit/frontend_footprint/plot_frontend_footprint.py \
    local_agents/frontend_footprint_x86/spec26_rows_long.csv local_agents/frontend_footprint_x86/frontend_footprint_rows_long.csv [AGENTIC_CSV] \
    --group side --out local_agents/frontend_footprint_x86/plots
```
