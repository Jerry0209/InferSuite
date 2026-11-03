# Report 24 — Server-set front-end footprint on x86: instruction footprint, unique taken branches, targets per taken branch (Rahul's metrics)

**Date of study:** 2026-11-03 · **Author of record:** Tianrui (Jerry), with Claude Code
**Feeds:** Rahul's Agentic-vs-SPEC-vs-Server footprint violins, Server part. SPEC is report 23 (branch `spec-x86`); Agentic is Jef's capture.
**Data:** in-repo `local_agents/frontend_footprint_x86/` (per-workload `summary.json`, long CSV, `gates.csv`, `gates_global.csv`, `sample_matched.csv`, generated `MANIFEST.md`, `plots/`) + git-ignored passes under `local_agents/{DCPerf,JVMbench,RealData}/data/frontend_footprint/<suite>_<workload>/run_1/` (tables `*.tsv.zst`, logs, receipts)
**Contract and log:** `docs/handoff/execution/frontend_footprint_method.md` (v1.1), `docs/handoff/execution/x86_server_footprint.md`; session log `docs/handoff/sessions/2026-11-03_dcperf-x86-frontend-footprint.md` ("dec. N" = its decision N)

---

## 1. Key summary

This is the Server side of Rahul's three front-end metrics: instruction footprint (unique 64 B lines × 64), unique taken branches, and targets per taken branch. The population is the **10-workload realistic Server set** (`in_realistic_server_set = 1`):
- feedsim (DCPerf);
- tomcat (DaCapo);
- finagle-chirper and finagle-http (Renaissance);
- six RealData servers and batches.

**Method:** the SPEC contract unchanged: PEBS-LBR `perf record -e br_inst_retired.near_taken:pp -c 20011 -j any,save_type`, the same analyzer (`31c492b25`, source sha256 `298e417a…`), on the server's fence cgroup on cores 4–11.
- **Window:** each workload's existing steady-state window: 300 s for feedsim, 180 s for the rest. It is not a whole run.
- **Pass:** one new pseudo-group `lbr` in the existing orchestrator, so shield, client placement, liveness check and receipts are the counter passes'.
- **Gates:** **10/10 pass every gate**; Cassandra's receipt gate passed only by Jerry's recorded override (dec. 10).

Headlines (n=10 Server vs n=26 SPEC, medians; SPEC from report 23):
- **Footprint:** 1.76 MB (video-4k) to 11.97 MB (naivebayes-rcv1), median **4.77 MB vs SPEC 415 KB** (11.5×).
- **Unique taken branches:** 27,457 to 182,840, median **89,134 vs 6,471** (13.8×).
- **Sample-matched:** over each pass's first 1,519,787 samples (SPEC's median per run), the Server medians are **2.52 MB and 49,090**, still **6.1× and 7.6×** SPEC's (`sample_matched.csv`). Half of the raw gap is sample count; the rest is the code.
- **Targets per taken branch, all branches:** **no difference** in the robust form. `weff_targets_all` excluding feedsim has a median of 1.42 (range 1.11–2.41) vs SPEC 1.43.
- **Targets per indirect branch:** **a clear difference.** `weff_targets_indirect` excluding feedsim has a median of **2.63** (1.45–5.43) vs SPEC 1.12; the JVM suites are highest (finagle-http 5.43, chirper 4.67).
- **feedsim is an outlier by construction:** `weff_targets_all` 1381. One indirect call site in DCPerf's synthetic ICacheBuster has **100,001 distinct targets** and alone contributes 1379 of the 1382 literal average.

Same caveats as SPEC, with the same V2 bias measurement:
- All unique counts and the literal `wavg_targets_*` are **sampled lower bounds**.
- 8/10 passes are still rising at the end of the window: the last quarter of samples added 0.1–9.2 % of the unique branches.
- `weff_targets_*` is the form to plot (report 23 V2: within 0.33 % of Intel PT).
- **Server and SPEC differ in window as well as code:** a steady state on 8 cores vs a whole single-core run. State this beside every footprint or branch comparison.

## 2. Methodology

### 2.1 Decisions

| # | Decision | Value | Why |
|---|---|---|---|
| D1 | Contract | identical to SPEC: event `:pp`, `-c 20011`, `-j any,save_type`, `-a -C 4-11 --cgroup=<server fence>`, user + kernel, analyzer `31c492b25` (cherry-picked to `dcperf` as `c7e3433ab`, byte-identical source) | Three families are comparable only with one event, one period and one analyzer (contract §3). V1–V3 validate the analyzer and the period, so they are not re-run. `gates_global.csv` points to SPEC's rows |
| D2 | Pass type | pseudo-group `lbr` in `run_dcperf_profile.sh`, code in `lbr_pass.sh`; `PROF_GROUPS=lbr`, a fresh `DATA_ROOT=<family>/data/frontend_footprint` | Guide §2. Shield, ISO-PROOF, `bench_start`/`bench_stop`, client placement, liveness check, 10 Hz pollers and receipts carry over unchanged. A fresh root is required: a lone `lbr` aimed at the banked root would `rm -rf` its `run_1` |
| D3 | Window | `CAPTURE_S` of the banked counter passes (300 s feedsim, 180 s others), after the module's liveness check | Unique counts grow with the window, so "whole execution" must mean the same window as every other Server metric. Measured 180.01 / 300.01 s, and `capture_s` matches the banked value on 10/10 |
| D4 | Instruments aligned (dec. 2) | `perf record` and `perf stat` start disabled (`-D -1 --control=fifo`). Order: record enable, stat enable, sleep, stat disable, record disable; every command must ack | The guide's two independent `-- sleep` runs would cover different windows. Nested windows make the coverage gate like-for-like: 0.99984–1.00013 on 10/10 |
| D5 | `perf record` as **root** (dec. 8) | `sudo -n taskset … perf record`; stopped by `kill -INT` to sudo's own perf child; `lbr.data` chowned back | The servers are root-owned and already running when the window opens. A non-root perf cannot read their `/proc/<pid>/maps` and records no MMAP for them (defect below). `perf stat` stays non-root |
| D6 | No `--threads`; ring fallback | single reader; `-m 512M`, then 256M, then 128M on `failed to mmap` (ENOMEM) | perf 6.8.12 in threaded mode never acks the control FIFO and ignores SIGINT (probe). A 512 MB ring needs a 1 MB contiguous kmalloc per CPU, which fails under heavy page cache. Video-4k ran at 128M with 0 lost at 161 k samples/s; ring size is not a contract parameter |
| D7 | Gates per pass (`lbr_pass_gates.py`), DONE only if all pass | contract, lost < 1 %, coverage ±0.5 %, 0 THROTTLE, **unmapped < 1 %**, server alive, D4 drift ≤ 25 % at ≥ 0.10 cores, D5 residual ≤ 20 %, witness clean, receipt comparable | The guide's DONE rule (lost, receipt, D4), plus SPEC's coverage and throttle gates. Unmapped was added after the defect below passed every other gate. D4/D5 are the validator's rules restricted to the LBR window |
| D8 | Receipt rule (`receipt_compare.py`, dec. 7) | each workload's own throughput metric, within the window where timestamps allow; comparable = ±15 % of the banked median or inside [min × 0.95, max × 1.05]; **video-4k: fence-load proxy** | "The workload served as in the counter passes." The 4K batch never finishes inside a pass, so none of its 9 banked passes has a receipt either. Its saturated pool (7.97 vs 7.97 cores) is the only evidence |
| D9 | Cassandra (dec. 10, **Jerry**) | receipt 52.0 k ops/s = 0.829 × the banked median: accepted by a recorded override (`receipt_override.json`); `receipt_ok` stays false, and `gates_v4.overrides = ["receipt"]` | The store degrades with every pass: 85.8 k → 56.9 k over the 9 counter passes (r = −0.90, ≈ −3.3 k per pass; the trend predicts ≈ 50.3 k for pass 10). Store 30.9 GB (21 GB built). The guide says to reuse it as-is. Every hygiene gate passed |
| D10 | Kernel sampling limits (dec. 9) | session: `perf_cpu_time_max_percent=0` at `perf_event_max_sample_rate=100000`, restored (percent first) and verified per workload | The kernel lowered the rate 100000 → 3000 twice that day. That is a shared knob (Jef's sampling gets capped), and RESTORE-VERIFY would fail. 0 THROTTLE on 10/10; the coverage gate still decides |
| D11 | Machine (dec. 6) | wrapper `frontend_footprint_server.sh`: wait for foreign perf (never kill), whole-machine quiet gate 180 s, knob snapshot → RESTORE-VERIFY diff after each workload, `measured.slice` revert + stop, video dataset swap and 15 GB scratch undone | Shared box. "Restored" needs a diff, not a log line. 10/10 RESTORE-VERIFY PASS; the end state equals the 15:28 state |
| D12 | Witness | `quiet_gate.py witness` at 0.5 Hz during the window; root kernel threads not counted as foreign | On the I/O servers, kworkers do our server's writeback on the house cores. LBR is cgroup-scoped on the measured cores, so house-core work cannot enter the footprint. 87–148 rows per pass, all clean |

### 2.2 Verification and hazards

**Gates, 10/10** (`gates.csv`):
- lost 0 and THROTTLE 0;
- unmapped 0.000 %; discontinuity rate ≤ 3.9e-4 (video-4k, 29 processes), otherwise ≤ 5.8e-6;
- coverage 0.99984–1.00013; D4 drift 0.0–2.6 %; D5 residual 0.0–9.4 % (kafka-20g; broker network softirq);
- receipt ratio 0.995–1.023 on 8 workloads, plus Cassandra 0.829 (override) and video-4k on its proxy;
- ISO-PROOF 0.0 % busy before every pass.

The receipt is an independent check that the load was the banked one. The fence load in the D4 window is 0.64 (Kafka broker) to 7.97 cores (video-4k).

**Repeatability:** two independent feedsim passes, with different perf identity (the first was non-root), gave footprint 2.124 vs 2.137 MB, unique branches 111,001 vs 110,807, and `weff_all` 1379.6 vs 1380.6.

Defects, with the number each would have shipped:
1. **Non-root `perf record` against a root server (feedsim smoke).**
   - FORK and COMM records were present for LeafNodeRank but no MMAP, so 903.7 M of 920.8 M entries were unmapped (98 %): no ranges, no canonical keys.
   - **Every gate of the time passed:** coverage 0.99981, lost 0, D4 0.1 %, receipt 1.000.
   - Fixed by D5 and the new `mapped_ok` gate. SPEC was unaffected (≤ 0.004 % unmapped in 26/26; its benchmark ran as the user and started after perf).
   - Banked as `dcperf_feedsim/run_1.smoke_nonroot_unmapped`.
2. **Ring buffer failed to mmap (kafka-20g, first attempt).** `perf record` exited with `failed to mmap with 12` while 50 GB was available. No window was sampled; the pass was refused and rerun at 18:04 (D6).
3. **Shared-kit defects found before any pass, fixed** (`run_glm_campaign.sh`, `bench_video_transcode.sh`):
   - `apply_isolation` ran `sudo pkill -9 -x perf` machine-wide. It now kills our UID only.
   - `restore_isolation` restarted dockerd even with `SKIP_DOCKER=1`. With live-restore off, that stops every container on the box.
   - The video module ran `pkill -f ffmpeg` machine-wide. It now kills only our scope.
   - The video module never restored its `datasets/cuts` swap. It now does.
4. **Gate script bugs, caught on the smoke:** `summary.json["gates"]` vs `gates_v4` would have failed every pass. `perf report --stats` counted SAMPLE twice (harmless for the 0-THROTTLE test).
5. **Inherited properties of the banked Server data, found by the receipt parser (not fixed here):**
   - None of the 9 feedsim counter passes holds the fixed-QPS SLA row, so the reference is `DCPerf/data/confirm` (n = 1, 15.96 QPS).
   - Kafka's 20 GB backlog drains ~40 s into the 90 s warm-up, so in every window the broker serves consumers at the produce rate, not deep-log reads.
   - tomcat has no timed DaCapo iteration in any pass (all are warm-ups; timed here from Tomcat's access log).

**Limitations:**
- **Window ≠ run.** SPEC's numbers are whole runs of 10–329 s on 1 core; Server's are 180/300 s steady states on up to 8 cores. `sample_matched.csv` controls for the sample count but not for the time span (a Server prefix of N samples is a shorter, all-core window).
- **JIT code is keyed per process (pid, address).** Code the JIT recompiles at a new address counts again, as it does for the i-cache. Anonymous code is 45–78 % of the footprint on the JVM workloads.
- **Kernel code is sampled only while a fence task is current.** The Server kernel share of the footprint (median 10.7 %) is not comparable with SPEC's 38.6 % without saying that Server runs far more user code per sample.
- **The stores carry the counter campaign's state:** Cassandra 30.9 → 31.4 GB, Kafka 30.7 → 32.8 GB over this run.

### 2.3 Reproduction recipe

```bash
cd ~/InferSuite                                   # branch dcperf; P7, measured cores 4-11
make -C local_agents/kit/frontend_footprint      # lbr_footprint, src sha256 298e417a...
# one LBR pass per workload, strictly one at a time; never point DATA_ROOT at banked data
FF_MAX_SAMPLE_RATE=100000 FF_CPU_TIME_PCT=0 \
  setsid -w nohup bash local_agents/kit/dcperf/frontend_footprint_server.sh all
#   (or name workloads: feedsim tomcat finagle-chirper ... video-4k; DONE passes are skipped)
python3 local_agents/kit/frontend_footprint/aggregate_server.py           # -> local_agents/frontend_footprint_x86/
python3 local_agents/kit/frontend_footprint/sample_matched.py             # -> .../sample_matched.csv
PY=~/miniforge3/envs/infersuite-full/bin/python3; P=local_agents/kit/frontend_footprint/plot_frontend_footprint.py
D=local_agents/frontend_footprint_x86
$PY $P $D/frontend_footprint_rows_long.csv --group family --out $D/plots/server_by_family
$PY $P $D/spec26_rows_long.csv $D/frontend_footprint_rows_long.csv [jef_agentic.csv] --group side --out $D/plots/spec_vs_server
# re-judge a finished pass offline (no capture):
python3 local_agents/kit/dcperf/lbr_pass_gates.py <run_1 dir> --analyzer-rc 0
```

**Cost:** about 8–12 min per workload:
- quiet gate 3 min;
- start-up and warm-up 1–4 min;
- capture 3–5 min;
- analysis 15–300 s (feedsim 28.8 M samples in 299 s).

The campaign took 15:44–18:13 including two smokes. Peak disk use is ~1.7 GB of `lbr.data` (deleted after the gates pass) plus 15 GB of video scratch (removed); the banked passes total ~210 MB.

**What should reproduce:** gates, the per-workload ranking, the ICacheBuster's 100,001 targets, and footprints within a few %. Not exact counts: the windows are stochastic request streams.

### 2.4 Scripts and artifacts

| Item | Repo location | Role |
|---|---|---|
| `frontend_footprint_server.sh` | `local_agents/kit/dcperf/` | campaign wrapper: per-workload env, quiet/perf gates, snapshot + RESTORE-VERIFY, sysctl pin, cleanup |
| `lbr_pass.sh` | `local_agents/kit/dcperf/` | the `lbr` pass: root `perf record` + `perf stat` via control FIFOs, ring fallback, metadata, analysis |
| `run_dcperf_profile.sh` | `local_agents/kit/dcperf/` | orchestrator, now with the `lbr` pseudo-group |
| `lbr_pass_gates.py` | `local_agents/kit/dcperf/` | per-pass gates → `summary.json` (`gates_v4`), incl. the recorded-override rule |
| `receipt_compare.py` | `local_agents/kit/dcperf/` | each workload's receipt vs its 9 banked counter passes |
| `quiet_gate.py` | `local_agents/kit/dcperf/` | whole-machine quiet gate and witness (copy of the SPEC kit's) |
| `lbr_footprint.cpp` | `local_agents/kit/frontend_footprint/` | analyzer (same source as SPEC) |
| `aggregate_server.py` | `local_agents/kit/frontend_footprint/` | Server aggregation (imports `aggregate.py`) |
| `sample_matched.py` | `local_agents/kit/frontend_footprint/` | Server metrics over the first N samples, N = SPEC's |
| `plot_frontend_footprint.py` | `local_agents/kit/frontend_footprint/` | violins; `--group side` pools per side; automatic log axis |
| results | `local_agents/frontend_footprint_x86/` | summaries, long CSV (`…,period,capture_s`), gates, MANIFEST, plots |

## 3. Key insights (most → least important)

1. **Server code is about an order of magnitude larger than SPEC's, even at equal samples.**
   - Footprint median 4.77 MB vs 415 KB; unique taken branches 89,134 vs 6,471.
   - At SPEC's median sample count: 2.52 MB vs 415 KB (6.1×) and 49,090 vs 6,471 (7.6×).
   - All 10 Server footprints exceed every SPEC benchmark except the three compiler-like outliers (721.gcc_r 4.85 MB, 723.llvm_r 3.78 MB, 727.cppcheck_r 1.18 MB). 5/10 exceed even gcc.
   - For unique branches, all 10 exceed SPEC's 4th largest (21,136), and 2/10 exceed gcc (132,266).
2. **The robust targets-per-branch metric does not separate Server from SPEC overall, but indirect branches do.**
   - `weff_targets_all`: median 1.42 vs 1.43.
   - `weff_targets_indirect`: 2.63 vs 1.12. The JVM suites lead (finagle-http 5.43, finagle-chirper 4.67, tomcat 2.61): virtual dispatch spreads over more targets.
   - For a BTB/indirect-predictor story, plot the `indirect` form.
3. **feedsim's metric 3 is a synthetic artefact, not server behaviour.**
   - DCPerf's ICacheBuster (100,000 generated methods; `ICACHEBUSTER_NUM_METHODS`) puts 100,001 targets behind one indirect call site, with 1.38 % of executions. That makes `weff_all` 1381 and `weff_indirect` 28,814.
   - Its 100,556 user `RET`s also make up most of its 110,807 unique branches.
   - Show feedsim as a labelled point, and use medians, never means.
4. **The literal metric 3 is a sample-count artefact here too.**
   - Server literal `wavg_targets_all` median 4.89 (excl. feedsim) vs `weff` 1.42.
   - tomcat's literal value grew 11.5 → 17.3 across the quarters of its own window.
   - Use `weff` (report 23 V2).
5. **Most Server footprint is JIT and runtime code, not the kernel.**
   - Anonymous (JIT) code is 45–78 % of the footprint on the 8 JVM workloads; `libjvm.so` adds most of the rest.
   - The kernel share is median 10.7 % vs SPEC's 38.6 %.
   - video-4k (native `ffmpeg`, 29 processes) is 71 % file-backed and 29 % kernel.
6. **The capture method needed root perf for servers, and only an explicit mapping gate catches the failure.** A non-root perf facing an already-running root server silently loses every mapping. Coverage, lost, throttle, D4 and receipt all still pass. Any future LBR capture of a pre-started process (Jef's agentic containers included) must run perf as root and check the unmapped fraction.
