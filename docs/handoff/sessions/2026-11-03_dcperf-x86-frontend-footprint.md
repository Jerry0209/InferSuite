# Session 2026-11-03 — Server set front-end footprint on x86 (P7)

**Goal:** execute `docs/handoff/execution/x86_server_footprint.md` end to end: one LBR footprint
pass (contract v1.1) for each of the 10 realistic Server workloads, gates, aggregate, report,
push `dcperf`.
**Machine state at start (2026-11-03 15:33):**
- P7, branch `dcperf` at `2e750a7f7`. The analyzer (`c7e3433ab`, cherry-picked from `spec-x86`
  `31c492b25`) is already present, and `local_agents/kit/frontend_footprint/` is identical to
  `spec-x86`. The installed binary `~/spec26-infra/infra/bin/lbr_footprint` is byte-identical
  to the kit build (src sha256 `298e417a…dce22`).
- Partition: 4–11 measured (SMT siblings 16–23 offline), 0–3 and 12–15 house.
  - system/user/init: `AllowedCPUs=0-3 12-15` (runtime drop-ins);
  - `measured.slice`: inactive, no property, no drop-ins;
  - measured cores: `performance`, min = max = 3.2 GHz; `no_turbo=1`, `nmi_watchdog=0`,
    THP `never`, workqueue and default IRQ mask `00f00f`. These are boot entry
    `agentic_benchmark.mode=controlled` (Jef).
  - `perf_event_max_sample_rate=100000`, `perf_cpu_time_max_percent=25`.
- `jeferson` logged in, idle (one claude process). No `perf`, no running containers.
- Root filesystem: 62 GB free. perf 6.8.12, kernel 6.17.0-1030-oem.
- JDK 21.0.12.1 / 17.0.20.1. The counter passes used 21.0.12 (+8).
- Every infra tree and dataset in the guide's §3 table is present.
  - `video_transcode_bench/datasets/cuts` is the original 1080p directory (not the 4K symlink).
  - `resized_clips` is empty.

## Decisions
| # | Decision | Why | Made by |
|---|---|---|---|
| 1 | `lbr` pseudo-group in `run_dcperf_profile.sh`, implemented in a sourced `lbr_pass.sh`. Everything around the instruments is unchanged: shield, ISO-PROOF, `bench_start`/`bench_stop`, 10 Hz pollers, receipts | Guide §2. The counter passes' steady state, fence, client placement and capture length carry over by construction | Claude |
| 2 | Both instruments start disabled (`-D -1 --control=fifo`). Order: record enabled, stat enabled, `CAPTURE_S` sleep, stat disabled, record disabled. Every command must ack | The guide's two independent `-- sleep CAPTURE_S` would cover different windows. Nesting the windows makes the coverage gate (samples × 20011 / exact taken count, ±0.5 %) like-for-like. Probed: 1.00025 | Claude |
| 3 | No `perf record --threads`, contrary to the guide's command line | perf 6.8.12 in threaded mode never acks the control FIFO's `enable` and ignores SIGINT (probe ~15:40; the hung process killed by PID). Single reader with `-m 512M`. The lost and coverage gates decide whether that suffices | Claude |
| 4 | Gates per pass, in `lbr_pass_gates.py`; DONE only if all pass:<br>• the contract's lost < 1 %, plus coverage ±0.5 % and zero THROTTLE (from SPEC);<br>• the validator's D4 (drift ≤ 25 %, ≥ 0.10 cores) and D5 (residual ≤ 20 %), restricted to the LBR window;<br>• server alive through the window;<br>• foreign-process witness clean;<br>• receipt comparable with the 9 banked passes (`receipt_compare.py`) | Guide §2's DONE rule plus the SPEC run's lessons | Claude |
| 5 | Witness: root kernel threads (`kworker`, `jbd2`, `ksoftirqd`, …) are not counted as a foreign task. They are still banked in `witness.tsv` | On the I/O servers they do our server's writeback on the house cores. LBR is cgroup-scoped on the measured cores, so house-core work cannot enter the footprint anyway | Claude |
| 6 | The wrapper `frontend_footprint_server.sh` owns everything around each pass:<br>• foreign-perf wait (never kill), then the whole-machine quiet gate (180 s);<br>• a 30 GB disk floor;<br>• a full knob snapshot before, then `RESTORE-VERIFY` diff after;<br>• `measured.slice` revert and stop;<br>• video-4k: dataset symlink and `resized_clips` restored;<br>• Cassandra, Kafka and Neo4j store sizes recorded | SPEC run lessons (`measured.slice` left active; "restored" needs evidence). The guide asks for store state to be recorded | Claude |
| 7 | Receipt metric per workload (`receipt_compare.py`); comparable = within ±15 % of the banked median, or inside [min × 0.95, max × 1.05]:<br>• feedsim: fixed-QPS achieved QPS + p95 ≤ 500 ms;<br>• Cassandra: YCSB OVERALL ops/s;<br>• Kafka: consumer MB/s in the window, plus producer records/s;<br>• Neo4j: ops/s in the window;<br>• Spark: mean s per pass in the window;<br>• tomcat: mean iteration ms in the window;<br>• Renaissance: mean op ms in the window;<br>• video-4k: **fence-load proxy** | Each module's own receipt, restricted to the capture window where timestamps allow. video-4k has no receipt by design: the 4K batch never ends inside any pass, and none of its 9 banked passes has one either. Leave-one-out over the banked passes: within ±4 % except Cassandra | Claude |

| 8 | `perf record` as root (`sudo -n taskset … perf record`). It is stopped by `kill -INT` to sudo's own perf child (`pgrep -P <sudo pid> -x perf`), and `lbr.data` is chowned back for analysis. `perf stat` stays non-root | See the non-root defect below. The servers are root-owned and already running when the window opens | Claude |
| 9 | For the Server session: `perf_cpu_time_max_percent=0` at `perf_event_max_sample_rate=100000` (the rate found at session start). Snapshotted, restored (percent first) on exit, and verified per workload | Without it the kernel lowers the rate mid-pass, as it did twice today. That changes a shared knob (Jef's sampling gets capped) and fails RESTORE-VERIFY. The static cap of 100 interrupts/tick/CPU is far above the PEBS-batched interrupt rate (no throttle even at 3000). Coverage and THROTTLE gates still decide | Claude |

| 10 | **cassandra-ycsb20m accepted by an explicit receipt override; store not rebuilt.**<br>• The pass passed every hygiene gate, but YCSB gave 52.0 k ops/s = 0.829 × the banked median (62.8 k), outside the band.<br>• `receipt_override.json` records it in the run dir: `receipt_ok` stays false, and `gates_v4.overrides = ["receipt"]` lets `all_ok` pass | The store degrades monotonically with every pass: 85.8 k → 56.9 k over the 9 counter passes (r = −0.90, ≈ −3.3 k per pass; the linear trend predicts ≈ 50.3 k for a 10th pass). It is 30.9 GB now vs 21 GB built. The counter passes ran on the same aging store, and the guide says to reuse it as-is. Fence load is 6.48 cores (in band) | **Jerry** (asked 17:10) |

## Defects
- **Shared kit killed other users' `perf` (`run_glm_campaign.sh` `apply_isolation`).** It ran
  `sudo pkill -9 -x perf` machine-wide. A colleague's collector started between the
  foreign-perf guard and that line would have been SIGKILLed. Fixed to our UID only.
  No incident: it was found by reading, before any pass.
- **Shared kit restarted dockerd on every restore, even with `SKIP_DOCKER=1`.** P7 has
  `live-restore: false`, so every past DCPerf, JVM or RealData pass restore stopped every
  running container. Harmless so far only because none were running. Jef's agentic rerun uses
  containers. Fixed: no docker action under `SKIP_DOCKER=1`.
- **`bench_video_transcode.sh` killed every `ffmpeg` on the box and never put the dataset swap
  back.** `bench_stop` ran a machine-wide `sudo pkill -f ffmpeg`; it now kills only processes
  in our scope. `vt_select_cuts` swapped `datasets/cuts` for a symlink, and nothing restored it
  (found restored by hand); `bench_stop` now restores it.
- **Non-root `perf record` against root-owned servers: 98 % of LBR entries unmapped (feedsim
  smoke, 15:51–16:02).** The servers run as root (`sudo systemd-run`) and are up before the
  window opens. perf learns their mappings only by reading `/proc/<pid>/maps` at start, which
  a non-root perf may not do for a root process.
  - Result: FORK and COMM records for LeafNodeRank but no MMAP, so 903.7 M of 920.8 M entries
    were unmapped.
  - It would have shipped footprint 2.12 MB, 111 001 unique taken branches, and
    `wavg_all` = `weff_all` ≈ 1380 targets/branch (nonsense).
  - Every gate of the time passed (coverage 0.99981, lost 0, throttle 0, D4 0.1 %, receipt
    1.000).
  - Fix: `perf record` runs under `sudo` (probe: root synthesizes MMAP2 for root processes),
    plus a new gate `mapped_ok` (unmapped < 1 %).
  - SPEC is unaffected: unmapped ≤ 0.004 % in all 26 episodes; there the benchmark ran as the
    user and started after perf.
  - Banked as `dcperf_feedsim/run_1.smoke_nonroot_unmapped` (no `lbr.data`).
- **`lbr_finish` read `summary.json["gates"]`, but the key is `gates_v4`.** Every pass would
  have been reported PASS-FAIL. Fixed. It happened to keep the smoke's `lbr.data` for the
  diagnosis.
- **The kernel lowered `perf_event_max_sample_rate` 100000 → 3000 before 15:47,** most likely
  during the `--threads` probe (~15:40); it was 100000 at 15:28.
  - The feedsim smoke ran at 3000 with 0 THROTTLE and coverage 0.99981: PEBS batching keeps
    the interrupt count low.
  - Restored to 100000 at ~16:07, before smoke run 2.
- **kafka-20g, 17:14: `perf record` could not start.** It failed with `failed to mmap with 12
  (Cannot allocate memory)` at `-m 512M`.
  - Memory was not short: 50 GB available, `ulimit -l` 7.8 GB, and root has CAP_IPC_LOCK.
  - Cause: at 512 MB per CPU the kernel needs a 1 MB physically contiguous page-pointer array
    per CPU (order-8 kmalloc). Under ~39 GB of Kafka page cache, memory was too fragmented.
  - No data was lost: the pass never sampled, and `lbr_capture` refused to continue without
    the ack.
  - Fix: `lbr_pass.sh` retries at `-m 256M`, then `128M`, and records the ring size used in
    `metadata.frontend_footprint.perf_record_mmap`. Ring size is not a contract parameter;
    the lost and coverage gates judge adequacy.
  - Kafka is to be rerun after video-4k.
- **Own process killed by `pkill -f` self-match, again (~15:41).** It hit the probe-cleanup
  shell only. Rule: kill by exact PID.

## What changed
- `local_agents/kit/dcperf/`: `lbr_pass.sh`, `lbr_pass_gates.py`, `frontend_footprint_server.sh`
  (new); `quiet_gate.py` (copied unchanged from the SPEC kit, `spec26/infra_kit/scripts/` on
  `spec-x86`); `run_dcperf_profile.sh` (`lbr` group), `bench_video_transcode.sh` (defect above);
  `receipt_compare.py` (subagent).
- `local_agents/kit/campaign/run_glm_campaign.sh`: the two defects above.
- Later in the session:
  - `lbr_pass.sh` gained root perf, the ring fallback and the gates key fix;
  - `lbr_pass_gates.py` gained `mapped_ok`, `contract_ok`, thresholds and the recorded-override rule;
  - `aggregate_server.py` (subagent) honours and reports overrides, and notes `sample_matched.csv`;
  - `sample_matched.py` is new;
  - `plot_frontend_footprint.py` gained `--group side` (subagent) and an automatic log axis.
  - Results: `local_agents/frontend_footprint_x86/`.
  - Report `docs/reports/24_server_frontend_footprint_x86.md`, registered in both indexes; pointer
    row in `docs/handoff/README.md`.
- **Smoke run 1 (15:44–16:02, `_session`):** feedsim ran with a non-root perf and FAILED.
  See Defects. The wrapper was then stopped by PID during tomcat's quiet gate, before any
  shield went up. RESTORE-VERIFY passed.
- **Smoke run 2 (from 16:07, `_session.2`):** root perf; sysctl pin (decision 9).
  **feedsim PASS-OK** (window 16:14:41 + 300 s):
  - samples 28 755 462; lost 0; coverage 0.99984; THROTTLE 0; unmapped 0.000 %;
  - D4 drift 0.1 % at 3.45 cores; D5 residual 0.0 %; witness clean;
  - receipt: fixed-QPS row comparable, ratio 1.000;
  - `lbr.data` 1.7 GB compressed (22.6 GB raw); analysis 299 s;
  - footprint 2 137 088 B (kernel 281 600); unique taken branches 110 807;
  - `wavg_all` 1381.7, `weff_all` 1380.6, `ge1pct_all` 1.52;
  - RESTORE-VERIFY PASS.
  **tomcat PASS-OK** (window 16:30:21 + 180 s):
  - samples 2 232 328; lost 0; coverage 0.99986; THROTTLE 0; unmapped 0.000 %;
    discontinuity rate 1.9e-6;
  - D4 drift 1.6 % at 0.94 cores; witness clean; receipt ratio 0.996;
  - footprint 7 744 448 B: anonymous (JIT) 62 %, `libjvm.so` 29 %, kernel 7 %;
  - unique taken branches 143 065; `weff_all` 1.80, `wavg_all` 17.3;
  - still sampling-limited (footprint 5.4 → 6.4 → … → 7.7 MB over the quarters).

  Smoke done 2/2 at 16:34; sysctl restored to 100000 / 25.
- **Campaign (from 16:35, `_session.3`):** the remaining 8 workloads in guide order, video-4k
  last. Every pass: quiet gate 181 s, ISO-PROOF 0.0 % busy, RESTORE-VERIFY PASS.

  | Workload | Result | Samples | Coverage | Cores | Receipt ratio | Footprint (B) | Unique taken | `weff_all` |
  |---|---|---|---|---|---|---|---|---|
  | finagle-chirper | OK | 21 541 636 | 0.99988 | 6.28 | 1.002 | 6 650 432 | 105 356 | 2.03 |
  | finagle-http | OK | 16 927 568 | 0.99986 | 6.63 | 1.006 | 5 807 680 | 93 494 | 2.41 |
  | cassandra-ycsb20m | OK by override (decision 10) | 15 494 520 | 0.99987 | 6.48 | **0.829** | 4 305 408 | 77 411 | 1.36 |
  | kafka-20g | **FAIL: perf could not start** (defect below) | – | – | 0.58 | – | – | – | – |
  | naivebayes-rcv1 | OK | 19 650 205 | 1.00003 | 6.75 | 1.004 | 11 970 816 | 182 840 | 1.20 |
  | neo4j-livejournal | OK | 11 209 775 | 1.00013 | 3.97 | 1.009 | 3 291 520 | 52 389 | 1.42 |
  | pagerank-livejournal | OK | 21 831 841 | 1.00005 | 7.72 | 1.023 | 5 223 872 | 84 775 | 1.11 |

  | video-4k | OK (fence-load proxy, decision 7) | 28 990 545 | 1.00009 | 7.97 | – | 1 757 184 | 27 457 | 1.23 |

  All OK passes: lost 0, THROTTLE 0, unmapped 0.000 %, D4 ≤ 2.6 %, D5 ≤ 3.9 %, witness clean.

  **video-4k:**
  - `-m 512M` and `256M` both failed with ENOMEM; it ran at **`-m 128M`** with 0 lost at the
    campaign's highest rate (161 k samples/s). The fallback worked as intended.
  - `cuts` was swapped to the 4K set and restored by `bench_stop`. The 15 GB of
    `resized_clips` scratch was removed by the wrapper.
  - Copy + downscale took 24 s (banked passes: 14–15 s), because `resized_clips` started
    empty.

  Run ended 18:03: 6 OK + Cassandra (override) + Kafka (rerun). Sysctl restored 100000 / 25.

  **Input state (wrapper), before → after:**
  - Cassandra data: 30 922 929 045 → 31 356 339 310 B;
  - Kafka data: 30 739 226 217 → 32 783 636 279 B (ingest during the failed pass);
  - Neo4j store: 3 091 488 768 B before.

  This is workload state, as after the counter passes. Free disk: 62 GB at start, 59 GB at
  18:03; our pass directories total ~210 MB, of which 172 MB is DaCapo's own `scratch`.
- **Kafka rerun (18:04–18:13, `_session.4`): kafka-20g PASS-OK.**
  - It started at `-m 512M` (no fallback needed).
  - samples 1 523 633; lost 0; coverage 1.00007; THROTTLE 0; unmapped 0.000 %.
  - D4 0.7 % at 0.64 cores; **D5 residual 9.4 %**, the highest of the 10 but under the 20 %
    limit. This is kernel work on the measured cores outside the fence, likely the broker's
    network softirq.
  - Receipt ratio 1.000.
  - Footprint 3 271 488 B, 56 131 unique taken branches, `weff_all` 1.74.
  - RESTORE-VERIFY PASS; sysctl restored.

  **10/10 Server workloads done.**
- **Final machine state (18:15):**
  - Diffed against the first snapshot of the day (15:47, before any shield): identical except
    `perf_event_max_sample_rate`, which is 100000 now vs 3000 then. 100000 is the value found
    at session start (15:28); my 15:40 probe caused the kernel to lower it.
  - No perf, no leftover scopes, `measured.slice` inactive, no `iso_applied`, CPUs 0–15 online.
  - `datasets/cuts` is the original directory and `resized_clips` is empty; 60 GB free.
- **Aggregation (`aggregate_server.py`, from the subagent; reuses `aggregate.py`):** 10/10
  `ok` (Cassandra by override), 300 long rows, `gates.csv`, `gates_global.csv`, `MANIFEST.md`,
  `spec26_rows_long.csv` (byte copy of `origin/spec-x86` @ `86b22c734`), and per-workload
  `summary.json` in `local_agents/frontend_footprint_x86/` (480 KB).
- **Plots** (`plot_frontend_footprint.py`; the subagent added `--group side`, I added an
  automatic log axis for target metrics spanning > 20×): `plots/server_by_family/` and
  `plots/spec_vs_server/`.
- **Sample-matched check (`sample_matched.py`, new).** Unique counts grow with samples, and a
  Server pass has more samples than a SPEC run (1.5–29 M vs 0.19–5.8 M). Each Server pass was
  therefore recomputed over its first N samples, from the tables' `first_seen` (the tables
  reproduce every summary exactly).
  - At N = 1 519 787 (SPEC's median), the Server median footprint is **2 522 KB vs 4 765 KB**
    over the full window, and unique taken branches **49 090 vs 89 134**.
  - SPEC's medians are 415 KB and 6 471. So about half of the Server-vs-SPEC gap is sample
    count, and **~6–8× remains at matched samples**.
- `lbr_pass_gates.py` refined after the aggregation subagent's review:
  - only the "Aggregated stats" section is counted (SAMPLE was doubled);
  - `contract_ok` (event, period, filter as recorded) is now a gate;
  - thresholds are saved in `gates_v4`, and the receipt notes are kept.

  feedsim's summary was re-judged from its banked files: same values, all OK.
- **feedsim's metric 3 is one synthetic call site.**
  - The site is `IND_CALL` LeafNodeRank+0x60acb7: **T = 100 001 distinct targets**, carrying
    1.38 % of all taken-branch executions. It contributes 1379.3 of `wavg_all`'s 1381.7.
  - This is DCPerf's ICacheBuster (`src/workloads/search/CMakeLists.txt`:
    `ICACHEBUSTER_NUM_METHODS 100000`, `LeafKernel.cc`). It deliberately sprays calls
    uniformly over 100 k generated methods, so inverse Simpson ≈ T as well. The 100 k methods'
    `RET`s are also why user `RET` dominates the unique-branch count (100 556 of 110 807).
  - For Rahul: a property of the benchmark, not an artefact. Any per-side mean of metric 3
    will be dominated by feedsim; use medians, or show it as a labelled point.

## Open threads
- **Banked receipts, found while writing `receipt_compare.py`.** These are not defects of this
  run, but they matter to anyone reading the counter data:
  1. **feedsim:** none of the 9 banked `feedsim_results.txt` holds the fixed-QPS row. Only the
     warm-up row exists (~21 QPS, p95 ~930 ms), because the passes were torn down early.
     The only SLA reference is `DCPerf/data/confirm` (15.96 QPS, p95 472 ms; n = 1).
  2. **Cassandra:** throughput drifted 85.8 k → 56.9 k ops/s across the 9 passes (r = −0.90 in run order, `receipt_compare.json` notes),
     while fence load rose from 5.88 to 6.30 cores. That fits the store accumulating ~15 M
     updates per pass.
  3. **Kafka:** the 20 GB backlog drains ~40 s into the 90 s warm-up. During every capture all
     6 consumers read at the produce rate (117.2 MB/s each), so the broker was **not**
     serving deep-log reads in the windows. That contradicts the intent in `bench_kafka.sh`.
  4. **tomcat:** no timed DaCapo iteration in any pass. All are warm-ups, timed here from
     Tomcat's access log.
- **For Rahul (report 24 §3):**
  - Plot `weff_targets_*`.
  - The Server-vs-SPEC separation is in the `indirect` form (median 2.63 vs 1.12), not in
    `all` (1.42 vs 1.43).
  - Show feedsim as a labelled point: ICacheBuster, 100 001 targets. Use medians.
  - Say "steady-state window on up to 8 cores vs whole single-core run" beside every
    footprint or branch comparison. `sample_matched.csv` gives the gap at equal samples
    (6.1× footprint, 7.6× unique branches).
- **For Jef:**
  - The contract is unchanged (v1.1, `:pp`, −c 20011, analyzer src `298e417a…`).
  - **New requirement from this run:** for processes that are already running when the
    window opens, `perf record` must run as root (or the processes as the perf user).
    Otherwise every mapping is silently lost, and every gate except an explicit unmapped
    check still passes. Containerised tool processes started before his window are exactly
    this case. Check `unmapped_entries / entries` (< 1 %).
  - Our shared kit no longer restarts dockerd on restore under `SKIP_DOCKER=1`, and no
    longer kills other users' `perf`.
- **CSV schema:** the Server long CSV has the guide's extra `capture_s` column, which SPEC's
  lacks. The plotter reads columns by name and ignores extras, so both (and Jef's) plot
  together. Resolved for plotting; a merged CSV would need the column added to SPEC's.
- **Not done (optional in guide §0):** the 6 toy suite versions for the suite-vs-realistic
  pair figure. Same wrapper, after adding their entries to `wl_spec`.
- **Branch split:** report 23 and its index rows live on `spec-x86`, report 24 and its rows
  on `dcperf`. Each branch's indexes list only its own; merging the branches must keep both
  rows.
