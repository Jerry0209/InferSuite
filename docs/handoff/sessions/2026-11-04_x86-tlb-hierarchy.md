# Session 2026-11-04 — TLB hierarchy on x86 (P7), SPEC and Server

**Goal:** Jef's request (relayed by Jerry, 2026-11-04): collect the TLB hierarchy metrics on x86
that ARM already has (L1 data/code TLB misses, second-level TLB misses, page walks), for SPEC
CPU 2026 and for the 10 realistic Server workloads. Also answer why ARM Server was not run.
**Machine state at start (2026-11-04 21:33):**
- P7, branch `dcperf` at `a82d33ce8` (clean). `spec-x86` at `86b22c734`. The SPEC kit in
  `~/spec26-infra/infra/scripts` is byte-identical to `spec26/infra_kit/scripts` on `spec-x86`.
- Partition as on 2026-11-03: 4–11 measured (16–23 offline), 0–3 and 12–15 house; THP `never`;
  `perf_event_max_sample_rate=100000`, `perf_cpu_time_max_percent=25`.
- `jeferson` logged in (pts/1, pts/8), idle. No `perf` running. Load average 0.26.
- Root filesystem **58 GB free**, under the SPEC rule's 60 GB stop line. Jerry decided:
  proceed, nothing deleted, stop if it falls below 35 GB.

## What was there before
- x86: no data-TLB or STLB event in any banked group. Code side only, as cycle shares:
  SPEC `itlb_walk_pct` (`itlb_misses.walk_active`, group `fe_l3x`, all 26), Server and agentic
  `itlb_tag_stall_pct` (`icache_tag.stalls`, group `fe_lat`). Server never ran `fe_l3x`.
- ARM (`spec-arm`, report 23): families `tlb-data` (L1D-TLB, L2-TLB, DTLB-walk MPKI) and
  `tlb-code` (L1I-TLB, ITLB-walk MPKI) plus `frontend_tlb_bound`, all 26 SPEC. ARM Server: not
  run (`dcperf-arm` holds only the kit cherry-pick `b3dfbbfcc`).

## Decisions
| # | Decision | Why | Made by |
|---|---|---|---|
| 1 | Two new groups, 4 GP events each: `tlb_d` = `dtlb_{load,store}_misses.{stlb_hit,walk_completed}`; `tlb_i` = `itlb_misses.{stlb_hit,walk_completed,walk_active}` + `dtlb_load_misses.walk_active` | Same shape as every banked group (≤ 4 GP + the fixed counters), so zero multiplexing next to the continuous TMA is the proven case. An STLB miss is a walk on Intel, so L1 misses = `stlb_hit + walk_completed` and STLB misses = `walk_completed`: the ARM L1/L2/walk ladder from 4 events per side. `itlb_misses.walk_active` repeats SPEC's banked `fe_l3x` event: a run-to-run cross-check | Claude |
| 2 | Not in any default rotation; `GORDER_OVERRIDE` (SPEC) / `PROF_GROUPS` (Server), fresh data roots `~/spec26-infra/infra/data_tlb` and `local_agents/<family>/data/tlb_x86` | Banked campaigns and their figures stay untouched | Claude |
| 3 | SPEC: new `counter_group_episode.sh`, the campaign's own `run_episode` wrapped in the footprint run's session discipline (foreign-perf + 180 s quiet gates, snapshot, witness with up to 3 attempts, verified restore) | The counter campaign's `campaign` stage has no quiet gate, witness or restore-verify | Claude |
| 4 | Server: `frontend_footprint_server.sh` takes `FF_GROUPS`/`FF_SUBDIR`; `run_dcperf_profile.sh` `PASS_GATES=1` runs the witness over counter passes and `counter_pass_gates.py` (windows, zero mux, alive, activity, D4, D5, witness, receipt) before DONE | The banked counter passes had no witness and a DONE of "> 10 windows"; the footprint run's gates apply to counter passes unchanged | Claude |
| 5 | Disk below 60 GB: proceed with a 35 GB floor | 2 GB kept, ~16 GB transient video scratch | **Jerry** |

## Verification before capture
- Kit dry-run (`GORDER_OVERRIDE="tlb_d tlb_i" run_spec_campaign.sh dryrun`, 21:48): both groups
  100 % enabled on a busy dummy, TMA coexistence OK.
- Ad hoc, TLB groups next to the continuous TMA on the kit's div/stream loads: 0 lines with
  `<not counted>`/multiplexing.
- Event semantics, pointer chase with one load per 4 KB page in random order (`tlbwalk.c`,
  scratch; user-mode counts, difference of 5 M and 15 M loads):
  1 GB region (> STLB reach) → `walk_completed` 0.999 per load, `stlb_hit` 0.001;
  6 MB region (> L1 DTLB, < STLB) → `stlb_hit` 0.965, `walk_completed` 0.035;
  store and code walks 0.000. The kit's sequential `stream` load showed ~16× fewer L1 DTLB misses
  than one per page: sequential page crossings are largely hidden (prefetched translations), which
  is a property of the access pattern, not of the event.
- Without `:u`, the 1 GB case read 0.116 `stlb_hit` per load on top of 1.000 walks: kernel-side
  run-to-run noise from the setup phase (differencing two runs), gone in user mode.

- SPEC smoke, `736.ocio_r` through `counter_group_episode.sh` into `data_tlb_smoke/` (21:51–21:55):
  EPISODE-OK, exit 0, specdiff PASS, 68 windows (34 per group), occupancy 1.000, witness clean,
  RESTORE-VERIFY PASS. `validate_spec.py`: PASS (S1 zero multiplexing; one window had
  `dtlb_load_misses.walk_active` `<not counted>`, the others in it counted). The banked
  11-group campaign has the same effect in 35 of 22,413 windows (0.16 %), usually the last event
  of a group; the co-counted denominators drop such a window for that event only.
  `itlb_walk_pct` 0.150 % vs banked `fe_l3x` 0.118 %; IPC 2.354 vs 2.311.
- Server gates offline: `counter_pass_gates.py` on a copy of banked `renaissance_finagle-http/run_5`
  (`fe_lat`): 1513 windows, pitch 0.119 s, 0 not counted, 0 multiplexed, D4 0.06 %, D5 0.0 %,
  receipt 1.008; only the witness fails (banked passes have none), as it should.

## What changed
- **Kits.** Groups `tlb_d`/`tlb_i`, byte-identical, in `~/spec26-infra/infra/scripts/run_spec_campaign.sh`
  (mirrored to `spec26/infra_kit/scripts/` on `spec-x86`) and `local_agents/kit/campaign/run_glm_campaign.sh`;
  neither is in a default rotation. TLB block in `extract_metrics.py`; `derive()` branches in
  `analyze_l3_windows.py`. New: `counter_group_episode.sh` (SPEC), `counter_pass_gates.py`,
  `tlb_server_aggregate.py`, `plot_tlb_x86.py` (Server), `spec26/kit/tlb/aggregate_spec_tlb.py`.
  `frontend_footprint_server.sh` takes `FF_GROUPS`/`FF_SUBDIR` (defaults unchanged: `lbr`,
  `frontend_footprint`); `run_dcperf_profile.sh` takes `PASS_GATES=1` (default off: the banked
  counter-pass behaviour is unchanged).
- **SPEC capture** 21:59–23:20 into `~/spec26-infra/infra/data_tlb` (1.5 GB): 26/26 EPISODE-OK on the
  first attempt, every witness clean, `validate_spec.py` PASS 26/26, 0 multiplexed of 21,988
  windows, 27 not counted (0.12 %), RESTORE-VERIFY PASS. Smoke dir `data_tlb_smoke/` kept.
- **Server capture** 23:20–01:45 into `local_agents/*/data/tlb_x86/` (540 MB, git-ignored): 10
  workloads × (`tlb_d`, `tlb_i`), 19/20 DONE live, video-4k `run_1` DONE after the offline re-judge
  (defect 1); all 20 re-judged with the final `counter_pass_gates.py`: 20/20 all_ok, no override.
  Receipts 0.955–1.016 (Cassandra 0.955/0.960: no override needed this time), video-4k fence load
  7.98 vs 7.97 cores. RESTORE-VERIFY PASS after every workload. Disk lowest 55 GB.
- **End state (01:46):** no perf; `perf_event_max_sample_rate` 100000, `perf_cpu_time_max_percent` 25;
  video scratch empty; no leftover scopes; as at session start.
- **Results:** `spec26/tlb_x86/` (`spec-x86`), `local_agents/tlb_x86/` (`dcperf`), report 25
  (`docs/reports/25_x86_tlb_hierarchy_spec_server.md`), registered in both indexes and in
  `docs/handoff/README.md`.
- Headlines (medians, x86): Server vs SPEC L1 iTLB 1.08 vs 0.0023 MPKI, code walk cycles 1.17 % vs
  0.028 %, L1 dTLB 11.75 vs 7.85, data walks 0.63 vs 0.25, data-load walk cycles 6.5 % vs 0.95 %;
  naivebayes-rcv1 12.1 data walks/kI and 24 % of cycles walking. SPEC x86 vs ARM: data side
  Spearman 0.82–0.91, x86 2–3× higher; code side tiny on both (x86 ~50×), Spearman 0.60–0.66.
- Cross-checks: SPEC `itlb_walk_pct` vs banked `fe_l3x` Spearman 0.95 (median |Δ| 16 %); Server
  `iTLB_L1_MPKI` vs banked `icache_tag.stalls` share Spearman 0.95.

## Why ARM Server was not run (Jef's question)
`arm_server_profiling.md` is the second of two ARM guides and runs after the SPEC one. The ARM
session of 2026-11-03 executed the SPEC guide only (364/364 passes, report 23, pushed 17:02 UTC).
"Ported" (`b3dfbbfcc` on `dcperf-arm`) is that guide's first setup step only: cherry-picking the
shield, profiler and exporter. The Server work itself was never started:
- port the 10 workload launchers to arm64 (JDK paths hard-coded in 7 files, host-scaled JVM
  heaps, jemalloc for Cassandra);
- install and build the software and datasets (~120 GB);
- capture 10 workloads × 9 tier-1 families (~10–15 h at ~$8.5/h).

It needs a session on the Graviton box itself, and Jerry has to start the instance. P7 has no part
in it.

## Defects found
- **My Server gate was stricter than the rule it mirrors, and the Server aggregation read a
  `<not counted>` event as 0.** `counter_pass_gates.py` failed any pass with even one window
  holding a `<not counted>` event; the SPEC validator (S1) accepts them and the co-counted
  denominators drop the window. Video-4k `tlb_d` (01:40) was refused for window 000 alone
  (`dtlb_store_misses.walk_completed`, the group's last event; 1 of 1520), every other gate
  passing. Would have shipped: a valid pass refused, and had it been accepted, the aggregation
  summing that window's instructions without its store walks (~0.07 % low), and the per-window
  derivation reading the walk count as 0. Fixed before pass 2 was judged: `counted_ok` = zero
  multiplexing and ≤ 1 % of windows not counted; `tlb_server_aggregate.py` drops such a window
  whole (sums and window distributions). Video-4k `run_1` re-judged offline with the fixed gate.

## Push
- `spec-x86` → `243851228` (SPEC results `spec26/tlb_x86/`, kit mirror, aggregation; report 23 pointer).
- `dcperf`: Server results, kit, report 25, this log (SHA in the follow-up commit below).
- Report check: the 11 date-based freshness warnings on reports 01–15 (unchanged content), overridden by
  **Jerry** for this push as on the two before; the cross-branch citation and report 23/24 freshness
  warnings were fixed instead.

## Open threads
- ARM Server (`dcperf-arm`): not started; see above. Its tier-1 families include `tlb-data` and
  `tlb-code`, so it will complete the 2 × 2 TLB table.
- Agentic TLB: the `tlb_d`/`tlb_i` groups are in the agentic kit too (opt-in via `GORDER_OVERRIDE`)
  but no agentic episode has run them; Jef's agentic capture would need them to join this table.
- THP: every number is for 4 KB pages (`never` on both machines). A THP-on pass for naivebayes-rcv1
  (24 % of cycles in data walks) would show how much of it huge pages remove.
