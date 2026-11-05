# TLB hierarchy, x86 Server set — MANIFEST

Captured 2026-11-04 23:20 – 2026-11-05 01:45 on P7 (Xeon w5-3425, Golden Cove): the 10 workloads of
the realistic Server set (`in_realistic_server_set = 1`), two dedicated-group passes each,
by `local_agents/kit/dcperf/frontend_footprint_server.sh` with `FF_GROUPS="tlb_d tlb_i"
FF_SUBDIR=tlb_x86`. Raw passes in `local_agents/{DCPerf,JVMbench,RealData}/data/tlb_x86/<suite>_<workload>/run_{1,2}`
(git-ignored). Requested by Jef for parity with the ARM `tlb-data` / `tlb-code` families.
Report: `docs/reports/25_x86_tlb_hierarchy_spec_server.md`. Session log:
`docs/handoff/sessions/2026-11-04_x86-tlb-hierarchy.md`.

## Instrument

Each pass is a banked counter pass of `run_dcperf_profile.sh`, unchanged except for the group:
the server in its fence on cores 4–11 (SMT siblings offline), the client on the house cores,
the module's liveness check, then `CAPTURE_S` (300 s feedsim, 180 s the rest) of 100 ms windows
of ONE group, `perf stat --for-each-cgroup=<server fence>`, continuous TMA alongside. Two passes
per workload: `run_1` = `tlb_d`, `run_2` = `tlb_i` (events and formulas: `spec26/tlb_x86/MANIFEST.md`
on `spec-x86`, byte-identical groups). `PASS_GATES=1`: the whole-machine witness runs during the
pass and `counter_pass_gates.py` decides DONE.

## Metrics

`server_tlb_x86.csv`, one row per workload. Each metric is a ratio of sums over the pass's
windows (the SPEC `metrics.json` convention), with the window p25 / median / p75 next to it from
`analyze_l3_windows.py`'s per-window rows. `tlb_d` metrics use `tlb_d`'s own instructions,
`tlb_i` metrics `tlb_i`'s: the two passes are separate 180 s windows of the same steady state,
never summed into one ratio except `STLB_MPKI` (a sum of two rates). A window with an event
`<not counted>` is dropped whole (1 of 32,048 windows: video-4k `tlb_d` w000).

## Gates (`gates.csv`, one row per pass; 20/20 all_ok, no override)

| Gate | Rule | Observed |
|---|---|---|
| windows | span ≥ 98 % of `CAPTURE_S`, pitch ≤ 1.33 × 100 ms | 1417–2530 windows, pitch 0.117–0.127 s |
| counted | zero multiplexing; `<not counted>` in ≤ 1 % of windows | 0 multiplexed; 1 window not counted in total |
| alive, active | fence alive after every window; ≥ 95 % of windows ≥ 5e5 instructions | all |
| D4 | first vs last fifth of the fence load, drift ≤ 25 %, load ≥ 0.10 cores | drift 0.0–4.8 %, load 0.66–7.98 cores |
| D5 | measured-partition busy not explained by the fence ≤ 20 % | 0.0–5.6 % (kafka-20g) |
| witness | ≤ 5 % of 2 s rows with another user's task > 10 %, mean ≤ 25 % | clean, 20/20 |
| receipt | `receipt_compare.py` vs the 9 banked counter passes | 0.955–1.016; video-4k on its fence-load proxy (7.98 vs 7.97 cores) |

Every workload: RESTORE-VERIFY PASS (knob snapshot before, diff after). Video-4k `run_1` was
refused live by an earlier, stricter `counted_ok` (zero not-counted windows) and re-judged offline
with the final rule (session log, defect 1); the other 19 passes were re-judged with it too.

## Cross-checks

* Banked `itlb_tag_stall_pct` (`icache_tag.stalls`, group `fe_lat`, the 2026-09 counter
  passes, window median) ranks the 10 workloads like the new `iTLB_L1_MPKI` (Spearman 0.95) and
  `itlb_walk_pct` (0.87): a different event, different passes.
* Report 24's instruction footprint does not predict them (Spearman 0.28 and 0.24).

## Files

| File | What |
|---|---|
| `server_tlb_x86.csv` | 10 workloads × 11 TLB metrics (ratio of sums + window p25/median/p75) |
| `gates.csv` | 20 passes × gate verdicts and numbers |
| `spec_tlb_x86.csv`, `arm_vs_x86_tlb.csv` | copies from `spec-x86` @ `243851228`, `spec26/tlb_x86/` (byte-identical; SPEC x86, and SPEC ARM vs x86) for the figure |
| `plots/tlb_hierarchy.png` | six panels, one dot per benchmark/workload, median bar, log y: SPEC on ARM, SPEC on x86, Server on x86. ARM has no walk-cycle counter, so the two walk-cycle panels show x86 only |

## Regenerate

```bash
cd ~/InferSuite      # branch dcperf
for each <family>:<suite>:<workload>:   # the 10 rows of tlb_server_aggregate.py WLS
  L3_BASE_PREFIX=<suite>_ L3_FENCES='{"server":"<suite>-"}' \
    python3 local_agents/kit/replay/analyze_l3_windows.py local_agents/<family>/data/tlb_x86 <workload>
python3 local_agents/kit/dcperf/tlb_server_aggregate.py
~/miniforge3/envs/infersuite-full/bin/python3 local_agents/kit/dcperf/plot_tlb_x86.py
```
