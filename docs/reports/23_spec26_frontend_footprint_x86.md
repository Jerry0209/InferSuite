# Report 23 — SPEC CPU 2026 front-end footprint on x86: instruction footprint, unique taken branches, targets per taken branch (Rahul's metrics)

**Date of study:** 2026-11-02 → 2026-11-03 · **Author of record:** Tianrui (Jerry), with Claude Code
**Feeds:** Rahul's Agentic-vs-SPEC-vs-Server footprint violins, SPEC part. Server is the next study (branch `dcperf`); Agentic is Jef's capture.
**Data:** in-repo `spec26/frontend_footprint_x86/` (per-benchmark summaries, long CSV, `gates.csv`, `gates_global.csv`, generated `MANIFEST.md`, preliminary violins) + sibling tree `~/spec26-infra/infra/data_frontend_footprint*` (raw episodes and tables, outside git)
**Contract and log:** `docs/handoff/execution/frontend_footprint_method.md` (v1.1), `docs/handoff/execution/x86_spec_footprint.md`; session log `docs/handoff/sessions/2026-11-02_spec-x86-frontend-footprint.md` ("dec. N" = its decision N)

---

## 1. Key summary

Rahul asked *why* the front end suffers in agentic work; the existing data shows only *that* it does. He named three metrics: instruction footprint (unique 64 B lines × 64), unique taken branches, and the weighted average number of targets per taken branch, Σ C_b·T_b / Σ C_b. This study supplies the SPEC CPU 2026 side. **Method:** PEBS-LBR sampling (`perf record -e br_inst_retired.near_taken:pp -c 20011 -j any,save_type`) on the benchmark's fence cgroup, measured cores 4–11, user + kernel, over the whole ref run (command index 0), for all 26 rate benchmarks. One committed analyzer (`31c492b25`) processed every episode. **26/26 episodes pass every evaluable V4 gate** (14 SPEC-int, 12 SPEC-fp). The August instruction-count gate for 3 of them cannot be evaluated and is reported as NO PROOF.

Headlines (n=26; medians SPEC-int n=14 vs SPEC-fp n=12):
- **Footprint:** 160 KB (782.lbm_r) to 4.85 MB (721.gcc_r), median 415 KB; int 534 KB vs fp 374 KB.
- **Unique taken branches:** 2,828 (782.lbm_r) to 132,266 (721.gcc_r), median 6,471; int 11,351 vs fp 5,517.
- **Targets per taken branch:**
  - literal `wavg_targets_all`: 1.007 (729.abc_r) to 61.3 (727.cppcheck_r), median 2.48; int 5.60 vs fp 1.45.
  - inverse-Simpson companion `weff_targets_all`: 1.003 (729.abc_r) to 2.61 (723.llvm_r), median 1.43; int 1.54 vs fp 1.11.

Two validation findings limit how these numbers can be used:
1. **Metrics 1 and 2 are sampled lower bounds that are still rising at the end of the run.** The last quarter of each run added 3.1–78.6 % of its final unique-branch count, so the convergence flag is set on 26/26. Against an exact Intel PT trace of three 1–4 s programs (V2), LBR recalled 26–53 % of the footprint and 17–42 % of the branches. Sampling 4× more densely raised both 1.14–1.59× (V3, n=3).
2. **Rahul's literal metric 3 is also a lower bound.** Contract v1 called it "robust to sampling"; that claim is wrong. V2 read it 48–61 % low for all branches on all 3 programs, and 4× denser sampling raised 721.gcc_r's value 13 %. The reason: T_b counts distinct targets, which is a rare-event unique count.
   - `weff_targets_*` stays within 0.33 % of PT on all 9 V2 values and within 0.23 % across periods (9 V3 values).
   - `wavg_targets_ge1pct_*` reaches −4.4 % (V2, g++, indirect). It is threshold-sensitive.

**Rahul should not read any footprint or branch count, or any literal `wavg_targets_*`, as exact.** Only `weff_targets_*` matched an exact trace to within 0.33 %.

## 2. Methodology

### 2.1 Decisions

| # | Decision | Value | Why |
|---|---|---|---|
| D1 | Instrument | LBR sampling (Arch-LBR, 32 entries) | PT is exact, but one ref run is ~50–150 GB of trace, and PT decodes at ~1 M branches/s (V2). Binary instrumentation slows servers 3–50× and cannot follow agentic tools into containers. LBR needs only addresses, so it works the same on SPEC, JVM servers and containerised agents (contract §2). |
| D2 | Sampling event | `br_inst_retired.near_taken:pp` (PEBS), contract v1.1 (dec. 9) | With the bare event, the LBR is frozen at the PMI after skid. Skid is counted in instructions, so it spans more branches in branch-dense code and oversamples some 32-branch windows. V1 read the weighted averages 1.8–3.7 % low. With `:pp`, PEBS writes the LBR at the overflowing branch, and V1 is within 0.052 %. |
| D3 | Period, filter | `-c 20011`, `-j any,save_type` | Shared with Server and Agentic, so every taken-branch execution has the same detection probability (32/20011 ≈ 0.16 %) and the lower-bound bias is comparable across families. The period is prime, which avoids aliasing with loop trip counts. Change it only with Jef, for all three families at once. |
| D4 | Scope | fence cgroup, `perf record -a -C 4-11 --cgroup=<fence>`; user + kernel; ref, 1 copy, index 0; SMT off, `performance` governor, no turbo | Same partition, inputs and command line as the August campaign (report 18), so wall time and IPC can be checked against it. A cgroup catches every child process. Kernel code run for the benchmark is front-end work too; user and kernel are split in every output. |
| D5 | Window | FIFO-gated start (dec. 3): a bash in the fence waits on a FIFO; `perf record` and `perf stat` start disabled (`-D -1 --control=fifo:…`), are enabled and must acknowledge, then the benchmark is released; stop at scope exit | The guide's `cycle_stats` override starts perf after the scope exists. By then the benchmark is running, so ld.so and init (~0.5–1.5 s) are missed. The contract window is start → exit. Probe: samples × 20011 / exact taken = 0.99998. |
| D6 | Exact counts alongside | `perf stat` on the same fence and interval: `cycles,instructions,br_inst_retired.near_taken` (dec. 5); gate \|samples × period / exact taken − 1\| ≤ 2 % (dec. 4) | Two independent subsystems must agree. The gate detects ring-buffer loss and dropped samples. `cycles` is a fixed counter (no GP cost) and gives an IPC check against August for the 3 benchmarks whose output cannot be verified. |
| D7 | Throttle gate | 0 perf `THROTTLE` records (dec. 4) | The kernel caps samples per tick. A loop retiring one taken branch per cycle is 160 k samples/s at −c 20011, and throttling drops samples exactly in hot phases. The coverage gate alone is not enough: in V3 attempt 1 coverage stayed inside ±2 % (§2.2). |
| D8 | Metric 3 forms (dec. 10) | literal `wavg_targets_{all,noret,indirect}`, labelled a lower bound; `weff_targets_*` = Σ C_b·E_b / Σ C_b, E_b = 1/Σ_t p_bt² (inverse Simpson; unbiased Σ n_t(n_t−1)/(n(n−1)) estimator, capped at T_b); `wavg_targets_ge1pct_*` = Σ C_b·max(1, #targets with ≥ 1 % of b's executions) / Σ C_b | The literal T_b counts distinct targets, so it is biased low like any unique count. The companions weight each target by its share of executions, so targets that sampling misses carry little weight. All three ship, and Rahul picks which one to plot. noret excludes returns (the return stack predicts those, not the BTB); indirect = IND + IND_CALL. |
| D9 | Canonical addresses | file code = (path, inode) + file offset; kernel = address; anonymous/JIT = (pid, address). Extensions: `[vdso]`/`[uprobes]` = name + offset, like a file; `[vsyscall]` likewise, counted as user; a user address in no mapping = (pid, address), and counted | A shared library counts once across processes, and ASLR does not change the keys. The vdso has no inode but is the same code in every process. JIT code is never merged across processes. V2 precision ≥ 0.999 on 3 programs confirms the keys. |
| D10 | Wrapper processes | the `runuser` parent and the pre-exec `bash` stay inside the fence; quantified per benchmark (`wrapper_*` columns of `gates.csv`) | Their kernel, ld.so and libc lines cannot be separated from the benchmark's. Their own objects are 0.09–2.90 % of the footprint (median 1.15 %) and 0.05–2.56 % of unique branches (n=26). runuser takes ≤ 0.0042 % of samples. These shares are lower bounds of the wrapper's share. |
| D11 | V2 programs (dec. 7) | 721.gcc_r **train** index 2 (1.95 s); a ~1 s deterministic CPython workload (`PYTHONHASHSEED=0`); `g++ -O2 -c lbr_footprint.cpp`, multi-process, with PT TSC on | SPEC `test` inputs run 15 ms (gcc) and 65 ms (abc), too short to resemble a ref run. Other train lines run 7–17 s, i.e. 35+ min of PT decode each. g++ adds a multi-process case, which a timeless (`tsc=0`) PT decode cannot attribute to processes. |
| D12 | V2 timing (dec. 11) | gcc and g++ after the campaign | v2_python's decode alone took 15 min and already showed the canonical keys are right (precision ≥ 0.999). The other two decodes then took 26 and 24 min on a house core; run before the campaign, they would have blocked its quiet gate. |
| D13 | Sysctl override, V3 only | `FF_MAX_SAMPLE_RATE=400000 FF_CPU_TIME_PCT=0` | At −c 5003 under the kernel's 3,000 limit, all 3 V3 episodes throttled (§2.2). Each sample costs 0.91–1.14 µs of PMI time (wall dilation, V3 vs period 20011). Even the cap's worst case (400 samples/tick) is therefore 40 % of the one measured core. The busiest V3 episode ran 118 k samples/s (721.gcc_r, wall +11.1 %). Production at 20011 never throttled, so it ran without the override. The override is snapshotted, restored and verified; percent is restored before rate, because the kernel refuses a rate write while the limit is off. |
| D14 | Restore (dec. 6) | full knob snapshot before the shield, diffed after the restore (`RESTORE-VERIFY`); `pre_cpuset.tsv` puts back effective cpusets; `measured.slice` is reverted when it had no `AllowedCPUs`/drop-ins and stopped when it had been inactive | The stock `restore_isolation` widens the house slices to 0–15 on this box (validation doc §1.5) and leaves `measured.slice` pinned 0–15 and active. The box is shared with Jef. |
| D15 | August gate, 734/735/772 (dec. 8) | NO PROOF; substitutes: IPC ratio and extrapolated instruction ratio | August banked windowed counts only (734.vpr_r: 33.5 s counted of 41.9 s wall), so "instructions within 1 % of August" cannot be evaluated (protocol rule 1). |
| D16 | Raw data | `lbr.data` is deleted only after every gate has passed; `summary.json` + `edges/lines/objects.tsv.zst` are kept | Disk is the binding constraint on P7. The tables carry `first_seen`, so every metric at any prefix of the run can be recomputed without the perf.data. |

### 2.2 Verification and hazards

**V1, synthetic truth (committed build; 1.8 M iterations, 59,357 samples, house core 1):** PASS. Footprint 368/368 lines and 541/541 branches. Weighted averages within +0.002 % / −0.005 % / +0.052 % (all / noret / indirect; the gate is 1 %). V1 tests C_b, not T_b: the least-sampled site has 1,383 sampled executions, and every T_b is exact.

**V2, exact Intel PT vs LBR on the same command** (user space; `compare.json` per program; LBR / PT, in %):

| Program | PT branches / LBR samples | Recall: footprint / branches | Precision: lines / branches | literal all / noret / ind | LBR C_b × PT T_b | `weff` | `ge1pct` |
|---|---|---|---|---|---|---|---|
| v2_python | 941.8 M / 47,207 | 0.257 / 0.170 | 1.000 / 0.999 | −61.1 / −42.6 / −55.1 | +0.5 / +0.7 / +0.8 | −0.13 / −0.11 / −0.33 | −0.03 / +0.19 / +0.33 |
| v2_gcc_train | 1.740 G / 87,397 | 0.490 / 0.424 | 0.999 / 0.999 | −48.4 / −5.4 / −27.2 | −0.1 / −0.1 / −0.4 | +0.13 / −0.03 / −0.11 | −1.26 / −0.30 / −1.93 |
| v2_gxx | 1.436 G / 73,363 | 0.534 / 0.387 | 1.000 / 1.000 | −47.9 / −9.6 / −28.7 | −0.5 / +0.1 / −0.4 | −0.13 / +0.05 / −0.11 | −0.21 / −0.82 / −4.39 |

**V3, period 5003 / period 20011 (736.ocio_r / 721.gcc_r / 749.fotonik3d_r):**
- Footprint: 1.519 / 1.136 / 1.252; kernel-only footprint 1.390 / 1.253 / 1.316.
- Unique taken branches: 1.593 / 1.171 / 1.283.
- Literal `wavg_targets_all`: 1.051 / 1.134 / 1.009.
- Companions over all 9 class × benchmark values: `weff` 0.9993–1.0023, `ge1pct` 0.9967–1.0036.

**V4, per episode (n=26):**
- exit 0 on 26/26; output check `pass` ×23 and `unavailable` ×3; lost 0 %.
- Coverage 0.99972–0.99993; 0 THROTTLE records; occupancy 0.995–1.000 cores.
- ISO-PROOF max busy 0.0 % on 26/26; witness clean on 26/26 (≤ 3 foreign rows; mean foreign CPU 5.5–7.3 %).
- 0 set-aside attempts.
- Wall time vs August: −2.9 % (767.nest_r) to +5.4 % (714.cpython_r), median +1.4 %. This is LBR overhead: ~1 µs per sample at up to 62 k samples/s.

Defects and hazards, each with the number it would have shipped:

1. **Contract v1's bare event biased C_b.** V1 with `br_inst_retired.near_taken` and no `:pp` (60,239 samples) read the weighted averages 1.3778 / 1.4144 / 6.2610 against a truth of 1.4031 / 1.4430 / 6.5000, i.e. −1.80 / −1.98 / −3.68 %. Unique counts were exact. No production episode used the v1 event (checked by the aggregator).
2. **The claim that literal metric 3 is "execution-weighted, so robust to sampling" is refuted.**
   - V2 read it 47.9–61.1 % low (all branches, n=3 programs).
   - LBR's sampled C_b with PT's exact T_b lands within −0.5…+0.8 % (all 9 values). The whole error is therefore in T_b.
   - Example: a hot `RET` in python3.13 runs 5.1 M times with 100 targets; its 8,432 sampled executions saw 20 of them.
   - Shipped as "robust", 727.cppcheck_r's 61.3 would read as a measured value. It is a lower bound, and it is entirely returns: noret reads 1.03.
3. **The ≥ 1 % companion is threshold-sensitive.** It is within 0.33 % on v2_python but −1.9 % (gcc train) and −4.4 % (g++) on indirect branches. A target near 1 % of its branch's executions flips in or out of the count with sampling noise. `weff` stayed within 0.33 % on all 9 values.
4. **V3 attempt 1 was throttled, and only the THROTTLE gate caught it.**
   - At −c 5003 with the sysctl at 3,000: 130 / 7,280 / 26 THROTTLE records (ocio / gcc / fotonik3d).
   - Coverage was 0.9945 / 0.9896 / 0.9993, inside the ±2 % band, so the coverage gate passed.
   - Against the clean rerun, user-space counts moved −1.0…+0.4 %, but kernel counts read 9.4–23.0 % high. The cause is not isolated.
   - The V3 ratios would have shipped as footprint 1.710 and 1.389 (instead of 1.519 and 1.252) and unique branches 1.783 and 1.449 (instead of 1.593 and 1.283) for ocio and fotonik3d, and as literal `wavg_targets_all` 1.195 (instead of 1.051) for ocio.
   - The attempt is kept in `~/spec26-infra/infra/data_frontend_footprint_c5003_throttled/` (lbr.data deleted).
   - Fix: the driver's default coverage tolerance is now ±0.5 % (`COVER_TOL`). All 26 production episodes and the clean V3 sit within 0.1 %; ±0.5 % would have failed ocio and gcc, and the THROTTLE gate catches the rest.
5. **The kernel lowered `perf_event_max_sample_rate` from 100,000 to 3,000 mid-study.**
   - The pre-shield snapshot read 100,000 at 09:36 and 3,000 from the smoke (10:30) on. dmesg put the drop at 10:07:35, after "interrupt took too long" during the first PEBS-LBR V1 capture.
   - Because each session's snapshot already read 3,000, RESTORE-VERIFY passed without bringing back the morning value.
   - **No data effect:** coverage 0.99972–0.99993 and 0 THROTTLE on all 26 episodes, including 714.cpython_r at 62 k samples/s (20× the nominal cap). Why the cap did not bite at −c 20011 is not established.
   - Restored to 100,000 after the last capture (13:35). The final machine check then matched the 09:40 pre-shield snapshot on every knob and every IRQ affinity.
6. **Witness set-asides.**
   - Mechanics test (736.ocio_r, stand-in analyzer): set aside with 2 of 7 witness rows foreign, `kswapd0` at 49 %. Most likely this was reclaim triggered by perf's own 8 × 512 MB ring buffers.
   - V3 ocio attempt 1: set aside because 1 of 7 rows had a foreign task above 10 %, against a limit of 5 % of rows. Short benchmarks have few rows, so a single busy 2 s row sets them aside.
   - Set-aside attempts are never analysed or aggregated, so no number shipped from either.
7. **Restore defects (machine state, not data).**
   - `restore_isolation` turns an empty `AllowedCPUs` snapshot into 0–15 (validation doc §1.5; it widened system/user/init on 2026-10-26). The driver wraps it with `pre_cpuset.tsv`; `run_spec_campaign.sh` itself is unchanged.
   - The mechanics test's RESTORE-VERIFY then caught `measured.slice` left *active* at 0–15, where it had been inactive; the restore now stops it.
   - Uncaught, either defect would put house work on cores 4–11 during later captures, Jef's included.
8. **Output-unverifiable benchmarks (734.vpr_r, 735.gem5_r, 772.marian_r).** The guide's gate, "instructions within 1 % of August", is **NO PROOF**, because August has no whole-run total. The substitutes put the 3 inside the range of the verified 23:
   - IPC ratio 0.980–0.994, against 0.971–1.049 for the verified 23.
   - Extrapolated instruction ratio 1.075–1.089, against 1.045–1.101. This ratio is offset from 1 on all 26 (median 1.09), so only its spread is evidence.
9. **V2 provenance.**
   - v2_gcc_train and v2_gxx ran the committed analyzer `31c492b25`.
   - v2_python's PT and LBR tables came from the pre-companion build (source sha256 `2fbd49d3…`; `gates_global.csv` flags it DIFFERENT). Its `compare.json` recomputes every metric-3 family from those tables, so the companions do not depend on that build.
   - The hybrid column (LBR C_b × PT T_b) is `compare_v2.py`'s `hybrid_lbr_C_pt_T`, committed in `fa094d581` and recomputed from the banked tables.
   - v2_gxx was decoded with TSC on, because it is multi-process. It had 9,935 PT trace errors in 1.436 G branches. Process attribution agrees between PT and LBR: cc1plus 98.66 / 98.62 %, as 1.33 / 1.36 %.

### 2.3 Reproduction recipe

```bash
# 0. Shared box: proceed only when no foreign perf and no foreign heavy work. Never kill or renice others.
pgrep -a -x perf; who; ps -eo user,pcpu,comm --sort=-pcpu | head; df -h /    # driver needs >= 20 GB
# 1. Analyzer (branch spec-x86), installed for the driver with its commit SHA
cd ~/InferSuite/local_agents/kit/frontend_footprint && make && ./lbr_footprint --version
cp lbr_footprint ~/spec26-infra/infra/bin/ && git rev-parse HEAD > ~/spec26-infra/infra/bin/lbr_footprint.sha
# 2. V1 and V2 on house core 1 (both refuse to start while another perf runs)
FV=~/InferSuite/local_agents/kit/frontend_footprint/footprint_validate; VAL=~/spec26-infra/infra/data_frontend_footprint_validation
GTR=~/spec26-infra/cpu2026/benchspec/CPU/721.gcc_r/run/run_base_train_uarch.0000; D=$(mktemp -d)
$FV/run_v1.sh $VAL/v1
$FV/run_v2.sh v2_python $VAL/v2/v2_python --env-file $FV/v2_python.env -- ~/miniforge3/bin/python3 $FV/v2_python.py
python3 ~/InferSuite/spec26/infra_kit/scripts/extract_cmd.py $GTR $D        # specinvoke env.sh + command lines
$FV/run_v2.sh v2_gcc_train $VAL/v2/v2_gcc_train --cwd $GTR --env-file $D/env.sh -- bash -c "exec $(sed -n 3p $D/speccmds_all.txt)"
PT_EVENT='intel_pt/cyc=0,mtc=0,noretcomp=0/u' $FV/run_v2.sh v2_gxx $VAL/v2/v2_gxx \
    --cwd ~/InferSuite/local_agents/kit/frontend_footprint -- g++ -O2 -c lbr_footprint.cpp -o /dev/null
# 3. Smoke, campaign (DONE markers make it resumable; default = all 26, index 0), V3
cd ~/spec26-infra/infra
./scripts/frontend_footprint_episode.sh 736.ocio_r 729.abc_r > logs/frontend_footprint_smoke.out 2>&1
setsid nohup ./scripts/frontend_footprint_episode.sh > logs/frontend_footprint_campaign.out 2>&1 &
PERIOD=5003 DATA_ROOT=$PWD/data_frontend_footprint_c5003 FF_MAX_SAMPLE_RATE=400000 FF_CPU_TIME_PCT=0 \
    ./scripts/frontend_footprint_episode.sh 736.ocio_r 721.gcc_r 749.fotonik3d_r > logs/frontend_footprint_v3b.out 2>&1
# 4. Aggregate (banked tables only) and preliminary SPEC-only violins
cd ~/InferSuite && python3 local_agents/kit/frontend_footprint/aggregate.py
~/miniforge3/envs/infersuite-full/bin/python3 local_agents/kit/frontend_footprint/plot_frontend_footprint.py \
    spec26/frontend_footprint_x86/frontend_footprint_rows_long.csv --out spec26/frontend_footprint_x86/plots
```

**Cost.**
- V1: ~5 s of capture.
- V2: PT decode runs at ~1 M branches/s: 15 / 26 / 24 min (python / gcc train / g++). The PT traces are 1.5 GB / 725 MB / 966 MB and are deleted after decode.
- Smoke: 6 min.
- Campaign: 10:37–12:06 for 24 benchmarks. That is 46.6 min of benchmark time, plus a 60 s quiet gate before each (180 s before the first), plus 3–57 s of analysis per episode (2 s for the smoke pair).
- V3: 17 min.
- Disk: `lbr.data` is 3.8–585 MB per episode after zstd (0.15–4.6 GB raw) and is deleted after verification. The kept tables are 37 MB (26 episodes) + 6.9 MB (V3); the repo directory is 1.3 MB.

**What should reproduce:**
- Gate verdicts, and wall time within ~5 % of August.
- Companion values across periods, to ≤ 0.4 %.
- Unique counts at the same period, for these deterministic benchmarks. The evidence is thin: the two period-5003 attempts agreed on user-space counts to −1.0…+0.4 % (n=3, one of them throttled). Kernel counts reproduce less well.

**What should not reproduce:** unique counts or literal metric 3 across periods (V3: 1.14–1.59× and up to +13 %) or across run lengths.

### 2.4 Scripts and artifacts

| Item | Location | Role |
|---|---|---|
| Analyzer | `local_agents/kit/frontend_footprint/lbr_footprint.cpp` (+ `Makefile`; commit `31c492b25`, source sha256 `298e417a…`) | perf script text → summary JSON, edge/line/object tables, convergence, all metric-3 forms |
| V1 tooling | `local_agents/kit/frontend_footprint/footprint_validate/` (`run_v1.sh`, `v1_regions.S`, `v1_synth.c`, `check_v1.py`, offline self-test `sim_v1_lbr.py`) | synthetic truth with known lines, branches and target schedules |
| V2 tooling | same directory: `run_v2.sh`, `compare_v2.py` (hybrid column: `fa094d581`), `v2_python.py` + `v2_python.env` | PT vs LBR on one command: recall, precision, metric-3 errors |
| Aggregation | `local_agents/kit/frontend_footprint/aggregate.py` | episodes → `spec26/frontend_footprint_x86/` (long CSV, `gates.csv`, `gates_global.csv`, generated `MANIFEST.md`) |
| Plots | `local_agents/kit/frontend_footprint/plot_frontend_footprint.py` | one violin per metric, from one or more long CSVs (SPEC, Server, Agentic) |
| Episode driver | `spec26/infra_kit/scripts/frontend_footprint_episode.sh` (live copy `~/spec26-infra/infra/scripts/frontend_footprint_episode.sh`, identical) | fence, shield, FIFO gate, perf record + stat, gates, restore + RESTORE-VERIFY |
| Reused kit | `spec26/infra_kit/scripts/{run_spec_campaign.sh, extract_cmd.py, verify_output.py, quiet_gate.py}` | partition, ISO-PROOF, command/env extraction, SPEC output check, quiet gate. Since 2026-11-04 `run_spec_campaign.sh` also defines the opt-in TLB groups `tlb_d`/`tlb_i` (report 25 on `dcperf`, results `spec26/tlb_x86/`); nothing this report uses changed |
| Contract and guide | `docs/handoff/execution/frontend_footprint_method.md` (v1.1), `docs/handoff/execution/x86_spec_footprint.md`, `local_agents/kit/frontend_footprint/README.md` | parameters, analyzer rules, gates; the same contract binds Server and Agentic |
| Results | `spec26/frontend_footprint_x86/` (+ `per_benchmark/*.summary.json`, `plots/*.png`) | what Rahul's figure reads |
| Raw (outside git) | `~/spec26-infra/infra/data_frontend_footprint{,_c5003,_c5003_throttled,_validation}/`; logs `~/spec26-infra/infra/logs/frontend_footprint_{smoke,campaign,v3,v3b}.out` | per-episode tables, metadata, perf stats, witness |

## 3. Key insights (most → least important)

1. **Plot `weff_targets_*` for metric 3, not the literal form.**
   - The literal form reads 47.9–61.1 % low against PT (all branches, 3 programs) and rises 13 % at 4× sampling density (721.gcc_r).
   - `weff` is within 0.33 % of PT (9 V2 values) and 0.23 % across periods (9 V3 values). `ge1pct` reaches −4.4 %.
   - On SPEC, the literal form spans 1.007–61.3, while `weff` spans 1.003–2.61.
2. **Unique counts depend on run length and period, so cross-family comparisons need matched sampling.**
   - The evidence: 26/26 flagged `sampling_limited`, with last-quarter growth of 3.1–78.6 % (727.cppcheck_r). V2 recall is 0.17–0.53, and V3 ratios are 1.14–1.59×.
   - SPEC runs last 9.6–329 s. Server windows and agentic tasks have other lengths.
   - Compare families at matched sampled-instruction counts, or show the convergence curves beside the violins.
3. **Three programs make SPEC's front-end tail:**
   - 721.gcc_r: 4.85 MB, 132,266 branches;
   - 723.llvm_r: 3.78 MB, 95,626 branches;
   - 727.cppcheck_r: 1.18 MB, 29,363 branches.

   The other 23 stay ≤ 0.99 MB and ≤ 21,136 branches. All 12 SPEC-fp are below 1 MB (max 766.femflow_r, 0.96 MB).
4. **Kernel code is a large, near-constant share of SPEC's footprint, even though the kernel runs little.**
   - Kernel footprint is 87–224 KB, which is 4.6–93.5 % of the total (median 38.6 %, n=26).
   - Yet the kernel executes only a median 0.44 % of sampled taken branches (0.08–20.4 %).
   - Kernel counts are also the most sampling-limited (V3 kernel footprint ratios 1.25–1.39).
   - Report user-only (median 248 KB, 2,769 branches) alongside the total.
5. **The PEBS event is required.** The bare event biases the weighted averages 1.8–3.7 % low (V1). Jef must capture agentic runs with `:pp`, the same period and the same analyzer commit.
6. **Gate on THROTTLE records, not on coverage alone.** A run with 7,280 THROTTLE records still showed 0.9896 coverage, and its kernel counts were 9–23 % high. At −c 20011 this kernel never throttled, even at 62 k samples/s.
7. **Measurement overhead does not distort the runs.** Wall time is −2.9…+5.4 % against August, IPC is 0.971–1.049× August, and each sample costs 0.91–1.14 µs of PMI time.
8. **Wrapper code is noise.** bash + runuser objects are at most 2.90 % of any benchmark's footprint (median 1.15 %).
