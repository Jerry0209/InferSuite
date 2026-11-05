# Report 25 — TLB hierarchy on x86: SPEC CPU 2026 and the realistic Server set, next to ARM (Jef's TLB request)

**Date of study:** 2026-11-04/05 · **Author of record:** Tianrui (Jerry), with Claude Code
**Requested by:** Jef, 2026-11-04: "collect the remaining TLB hierarchy data for x86 (SPEC and Server)", for parity with the ARM families `tlb-data` / `tlb-code` (report 23 on `spec-arm`)
**Data:** SPEC on `spec-x86`: `spec26/tlb_x86/` (`spec_tlb_x86.csv`, `arm_vs_x86_tlb.csv`, `per_benchmark/*.metrics.json`, `MANIFEST.md`); raw windows `~/spec26-infra/infra/data_tlb` (1.5 GB, outside the repo). Server on `dcperf`: `local_agents/tlb_x86/` (`server_tlb_x86.csv`, `gates.csv`, `MANIFEST.md`, `plots/tlb_hierarchy.png`, copies of the two SPEC tables); raw passes `local_agents/{DCPerf,JVMbench,RealData}/data/tlb_x86/` (git-ignored)
**Session log:** `docs/handoff/sessions/2026-11-04_x86-tlb-hierarchy.md` ("dec. N" = its decision N)

---

## 1. Key summary

Before this study, x86 had no data-TLB or second-level-TLB count anywhere. SPEC had only `itlb_walk_pct` (cycles with a code page walk in progress), and the Server set only `icache_tag.stalls`, a stall-time proxy. ARM SPEC had the full hierarchy. This study adds the x86 hierarchy for both populations, with the instruments every earlier x86 number used:
- **SPEC:** 26 rate benchmarks, whole single-core runs.
- **Server:** the 10 realistic workloads, 180/300 s steady states on the 8-core fence.

**Method:** two new zero-multiplexing counter groups of 4 events each:
- `tlb_d`: `dtlb_{load,store}_misses.{stlb_hit,walk_completed}`;
- `tlb_i`: `itlb_misses.{stlb_hit,walk_completed,walk_active}` + `dtlb_load_misses.walk_active`.

On Intel, an STLB miss *is* a page walk. So L1 TLB misses = `stlb_hit + walk_completed` and second-level misses = `walk_completed`, giving ARM's L1 → L2 → walk ladder from four events per side.
- **SPEC:** the campaign's own episode, rotating only these two groups.
- **Server:** one dedicated pass per group, with the footprint run's gates.
- **Outcome:** **26/26 SPEC episodes and 20/20 Server passes valid; zero multiplexing; no override.**

Headlines (medians, ratios of sums; ARM is Graviton5 / Neoverse-V3 from report 23):

| Metric (per kilo-instruction unless %) | SPEC · ARM | SPEC · x86 | Server · x86 | Server / SPEC (x86) |
|---|---|---|---|---|
| L1 data-TLB misses | 2.67 | 7.85 | 11.75 | 1.5× |
| Data page walks (= x86 data STLB misses) | 0.041 | 0.246 | 0.632 | 2.6× |
| L1 instruction-TLB misses | 0.00009 | 0.0023 | 1.08 | ~480× |
| Instruction page walks | 0.00005 | 0.0018 | 0.137 | ~76× |
| Cycles walking, data loads (%) | — | 0.95 | 6.46 | 6.8× |
| Cycles walking, code (%) | — | 0.028 | 1.17 | 42× |

- **The Server set separates from SPEC on the code side, by two orders of magnitude.** On the data side it differs by 1.5–2.6×.
  - **JVM services:** 0.9–3.1 L1 instruction-TLB MPKI and 0.9–2.4 % of cycles walking for code.
  - **Batch analytics** (pagerank, naivebayes, video-4k) are SPEC-like on the code side.
- **The heaviest data-TLB load anywhere is naivebayes-rcv1 (Spark):** 12.1 walks per kilo-instruction and **24 % of cycles in data page walks**; 60 % of its L1 data-TLB misses also miss the STLB.
- **x86 vs ARM on the same SPEC binaries' source:** the per-benchmark rankings agree on the data side, at Spearman 0.89 (L1) and 0.82–0.91 (second level / walks). x86's rates are 2–3× higher. On the code side both are tiny, x86 ~50× higher, and the ranks agree only loosely (0.60–0.66).
- **Independent checks agree:**
  - the new `itlb_walk_pct` ranks SPEC like the banked campaign's (Spearman 0.95);
  - the new Server L1 instruction-TLB rate ranks the 10 workloads like the banked `icache_tag.stalls` share (0.95).

**Caveat, as in report 24:** SPEC numbers are whole single-core runs; Server numbers are steady states on up to 8 cores.

## 2. Methodology

### 2.1 Decisions

| # | Decision | Value | Why |
|---|---|---|---|
| D1 | Event groups (dec. 1) | `tlb_d` = `dtlb_load_misses.{stlb_hit,walk_completed}`, `dtlb_store_misses.{stlb_hit,walk_completed}`; `tlb_i` = `itlb_misses.{stlb_hit,walk_completed,walk_active}`, `dtlb_load_misses.walk_active`; + `cycles,instructions` | ≤ 4 GP events + fixed counters is the shape of every banked group, so zero multiplexing next to continuous TMA is the proven case (kit dry-run: 100 % enabled). The 8 events give ARM's ladder plus walk durations. `itlb_misses.walk_active` repeats SPEC's banked `fe_l3x` event as a cross-check |
| D2 | Hierarchy arithmetic | L1 misses = `stlb_hit + walk_completed`; STLB misses = walks = `walk_completed` | Golden Cove: an L1 miss looks up the STLB, an STLB miss starts a walk. `walk_completed` leaves out aborted (wrong-path) walks, so L1 counts are slightly low. ARM's events count speculative accesses too (report 23 caveat b) |
| D3 | ARM pairing | `L1D-TLB` ↔ `dTLB_L1_MPKI`; `L2-TLB` and `DTLB-walk` ↔ `dTLB_walk_MPKI`; `L1I-TLB` ↔ `iTLB_L1_MPKI`; `ITLB-walk` ↔ `iTLB_walk_MPKI`; all "analogue". ARM ratio of sums, never its window mean | On x86 the second-level miss and the walk are one event. On Neoverse-V3 they are two (median 0.128 vs 0.041 MPKI), so both ARM metrics pair with the one x86 count. Report 23 D12: cross-ISA numbers use the ratio of sums |
| D4 | Fresh data roots, not in any default rotation (dec. 2) | `GORDER_OVERRIDE="tlb_d tlb_i"`, `~/spec26-infra/infra/data_tlb`; `PROF_GROUPS`/`FF_GROUPS="tlb_d tlb_i"`, `<family>/data/tlb_x86` | Banked campaigns and their figures are untouched. The orchestrator `rm -rf`s a `run_N` whose group mismatches |
| D5 | SPEC wrapper (dec. 3) | new counter_group_episode.sh (`spec-x86`, spec26/infra_kit/scripts/): the campaign's `run_episode` unchanged, wrapped in the footprint run's foreign-perf and 180 s quiet gates, knob snapshot, 2 s witness (contaminated episode set aside, ≤ 3 attempts) and RESTORE-VERIFY | The `campaign` stage has none of these. The SPEC rules for this box require them |
| D6 | Server passes (dec. 4) | `frontend_footprint_server.sh` with `FF_GROUPS`/`FF_SUBDIR`; `run_dcperf_profile.sh` `PASS_GATES=1`: the witness runs over counter passes and `counter_pass_gates.py` decides DONE | The banked counter passes had no witness and a DONE of "> 10 windows". The LBR run's D4/D5/witness/receipt rules (report 24 D7) apply unchanged, plus counter rules: window span and pitch, zero multiplexing, fence alive, activity |
| D7 | `<not counted>` windows | zero multiplexing required; ≤ 1 % of windows may hold an event `<not counted>`; such a window is dropped whole by the aggregation (SPEC: per event, in extract_metrics.py on `spec-x86`) | The SPEC validator's S1 rule. Occasionally the last event of a group gets no counter for one window: SPEC 27 of 21,988 windows (0.12 %), Server 1 of 32,048, banked campaign 0.16 % |
| D8 | Server metric | ratio of sums over the pass's windows (+ window p25/median/p75); `tlb_d` and `tlb_i` metrics each over their own pass's instructions | The SPEC `metrics.json` convention. The two passes are separate windows of one steady state; only `STLB_MPKI` adds two rates |
| D9 | Disk (dec. 5, **Jerry**) | proceed at 58 GB free (rule: stop below 60 GB) with a 35 GB floor; nothing deleted | 2 GB kept, ~16 GB transient video scratch. Lowest observed: 55 GB |

### 2.2 Verification and hazards

**Before any capture:**
- **Kit dry-run:** both groups 100 % enabled on a busy dummy, and they coexist with the continuous TMA counter (0 multiplexed or not-counted lines).
- **Event semantics:** a pointer chase with one load per 4 KB page in random order (user-mode counts, 15 M minus 5 M loads):
  - a **1 GB** region (beyond STLB reach) gives **0.999 walks per load** and 0.001 STLB hits;
  - a **6 MB** region (beyond the L1 DTLB, within the STLB) gives **0.965 STLB hits** and 0.035 walks;
  - store and code walks read 0.000.
  - The kit's sequential 2 GB stream showed ~16× fewer L1 misses than one per page: sequential page crossings are largely hidden, which is a property of that access pattern.
- **Smoke:** `736.ocio_r` through the new SPEC wrapper. `itlb_walk_pct` 0.150 % vs banked 0.118 %, IPC 2.354 vs 2.311.

**SPEC, 26/26** (21:59–23:20):
- EPISODE-OK on the first attempt; no episode set aside; witness clean in every episode.
- Occupancy 0.997–1.000 cores.
- specdiff PASS, except 734.vpr_r, 735.gem5_r and 772.marian_r, which are not specdiff-testable from one command line, as in every SPEC run.
- validate_spec.py (`spec-x86`) PASS 26/26; 0 multiplexed windows. RESTORE-VERIFY PASS.

**Server, 20/20** (23:20–01:45; `gates.csv`):
- 1417–2530 windows per pass, pitch 0.117–0.127 s.
- D4 drift 0.0–4.8 % at 0.66–7.98 cores; D5 residual 0.0–5.6 %; witness clean.
- Receipt 0.955–1.016 against the 9 banked passes. Video-4k is judged on its fence-load proxy, 7.98 vs 7.97 cores. Cassandra passed without the override report 24 needed (0.955, 0.960).
- RESTORE-VERIFY PASS after every workload. End state: no perf running, `perf_event_max_sample_rate` 100000 / 25 %, video scratch empty, no leftover scopes.

**Cross-checks (two subsystems agreeing):**
- **SPEC:** new `itlb_walk_pct` (tlb_i windows, 1/2 of the run) vs the banked `fe_l3x` value (1/11 of the run, August): median relative difference +3.6 %, median |difference| 16 %, Spearman 0.95.
  - The largest relative gaps are on values below 0.25 % of cycles: cpython 0.10 vs 0.23, zstd 0.017 vs 0.035.
- **Server:** the banked `itlb_tag_stall_pct` (`icache_tag.stalls`, September counter passes, a different event) ranks the 10 workloads like the new `iTLB_L1_MPKI` (Spearman **0.95**) and `itlb_walk_pct` (0.87).

**Defect (session log):** my first `counter_pass_gates.py` failed a pass on any single `<not counted>` window, which is stricter than the SPEC rule it mirrors. The Server aggregation also read such an event as 0.
- **What it did:** it refused video-4k `tlb_d` for window 000 alone (1 of 1520), with every other gate passing.
- **What it would have shipped:** a valid pass refused; or, if accepted, store walks ~0.07 % low and one per-window value at 0.
- **Fix:** D7, applied before pass 2 was judged. All 20 passes were re-judged offline with the final script, and video-4k `run_1` was marked DONE on that verdict.

**Limitations:**
- **Window ≠ run** (report 24): SPEC is a whole single-core run; Server is a steady state on up to 8 cores, where a context switch or migration can cost TLB entries that SPEC's pinned single process never loses.
- **THP was `never`** on both machines, so every number holds for 4 KB pages. With THP the data-side numbers, Spark's above all, would drop.
- **Page size and TLB geometry differ between the ISAs,** so x86/ARM ratios compare designs, not just workloads. The rank agreement is the robust cross-ISA statement.
- **Kernel work** is counted while a fence task is current (user + kernel events, cgroup-scoped).
- **The stores carry the earlier campaigns' state:** Cassandra 31.4 GB, Kafka 32.3 GB (`input_state.tsv`).

### 2.3 Reproduction recipe

```bash
# SPEC (P7, ~80 min). Live kit ~/spec26-infra/infra (copy on spec-x86: spec26/infra_kit/)
cd ~/spec26-infra/infra
GORDER_OVERRIDE="tlb_d tlb_i" ./scripts/run_spec_campaign.sh dryrun          # 100 % enabled, TMA coexists
GORDER_OVERRIDE="tlb_d tlb_i" DATA_ROOT=$PWD/data_tlb ./scripts/counter_group_episode.sh
python3 scripts/extract_metrics.py data_tlb/7* && python3 scripts/validate_spec.py data_tlb/7*
cd ~/InferSuite      # branch spec-x86
python3 spec26/kit/tlb/aggregate_spec_tlb.py --data ~/spec26-infra/infra/data_tlb

# Server (P7, ~2.5 h: 10 workloads x 2 passes, quiet gates included). Branch dcperf
FF_GROUPS="tlb_d tlb_i" FF_SUBDIR=tlb_x86 FF_DISK_MIN_G=35 \
  bash local_agents/kit/dcperf/frontend_footprint_server.sh all
#   per workload: L3_BASE_PREFIX=<suite>_ L3_FENCES='{"server":"<suite>-"}' \
#     python3 local_agents/kit/replay/analyze_l3_windows.py local_agents/<family>/data/tlb_x86 <workload>
python3 local_agents/kit/dcperf/tlb_server_aggregate.py
~/miniforge3/envs/infersuite-full/bin/python3 local_agents/kit/dcperf/plot_tlb_x86.py
# re-judge a pass offline: counter_pass_gates.py <run> --group tlb_d --events "<GRP[tlb_d]>" --capture-s 180
```

**What should reproduce:** zero multiplexing, the gates, and the rankings; the Server/SPEC and code/data contrasts; magnitudes within run-to-run noise (SPEC `itlb_walk_pct` moved by a median 16 % between campaigns). Not exact counts: the Server windows are stochastic request streams.

### 2.4 Scripts and artifacts

Paths marked `spec-x86` live on that branch (and in the live kit `~/spec26-infra/infra/scripts/`), not on `dcperf`.

| Item | Location | Role |
|---|---|---|
| Groups `tlb_d`, `tlb_i` | `run_spec_campaign.sh` (`spec-x86` copy + live kit), `local_agents/kit/campaign/run_glm_campaign.sh` | byte-identical definitions, opt-in only |
| TLB formulas, SPEC | spec26/infra_kit/scripts/extract_metrics.py on `spec-x86` (TLB block) | episode ratios of sums, co-counted |
| TLB formulas, per window | `local_agents/kit/replay/analyze_l3_windows.py` (`derive`, groups `tlb_d`/`tlb_i`) | per-window rows (Server distributions) |
| SPEC wrapper | spec26/infra_kit/scripts/counter_group_episode.sh on `spec-x86` | gates and witness around `run_episode` |
| SPEC aggregation | `spec26/kit/tlb/aggregate_spec_tlb.py` (`spec-x86`) | `spec_tlb_x86.csv`, `arm_vs_x86_tlb.csv`, `per_benchmark/` |
| Server wrapper / orchestrator | `local_agents/kit/dcperf/frontend_footprint_server.sh` (`FF_GROUPS`, `FF_SUBDIR`), `run_dcperf_profile.sh` (`PASS_GATES`) | passes, witness, restore-verify |
| Server gates | `local_agents/kit/dcperf/counter_pass_gates.py` (imports `lbr_pass_gates.py`, uses `receipt_compare.py`) | `gates.json` per pass |
| Server aggregation | `local_agents/kit/dcperf/tlb_server_aggregate.py` | `server_tlb_x86.csv`, `gates.csv` |
| Figure | `local_agents/kit/dcperf/plot_tlb_x86.py` → `local_agents/tlb_x86/plots/tlb_hierarchy.png` | six panels, SPEC·ARM / SPEC·x86 / Server·x86 |

## 3. Key insights (most → least important)

1. **Server work stresses the instruction TLB on x86; SPEC barely touches it.** L1 instruction-TLB misses: median 1.08 vs 0.0023 MPKI (~480×). Code page walks: 0.137 vs 0.0018 MPKI. Cycles walking for code: 1.17 % vs 0.028 %.
   - The JVM services carry it: finagle-http 3.14 MPKI and 2.27 % of cycles, neo4j 2.43 %, Cassandra 1.87 %, tomcat 1.41 %.
   - pagerank, video-4k and naivebayes sit at SPEC's level (0.005–0.06 MPKI).
2. **On the data side, Server is only 1.5–2.6× SPEC.** L1 data-TLB misses: 11.75 vs 7.85 MPKI, and every Server value lies inside SPEC's range (0.17–58.5, cactus at the top). Data walks: 0.63 vs 0.25. Only feedsim (2.80) and naivebayes (12.07) exceed SPEC's maximum (nest, 2.04).
3. **naivebayes-rcv1 is the data-TLB outlier of both sets.**
   - 12.1 data walks per kilo-instruction (SPEC max 2.04, nest) and 24.3 % of cycles in data-load walks (SPEC max 9.0 %).
   - Only 40 % of its L1 data-TLB misses hit the STLB (median Server 93 %, SPEC 97 %): Spark's working set spans far more than the STLB's 4 KB-page reach.
   - With THP off, this is the case where huge pages would matter most.
4. **When an L1 instruction-TLB miss happens, the STLB usually catches it on Server (median 87 %) but not on SPEC (12 %).** This is consistent with two kinds of miss:
   - SPEC's few code misses are mostly cold or evicted pages, which walk;
   - Server's are capacity misses of the small L1 instruction TLB across a hot code region that still fits the STLB.
5. **x86 and ARM agree on which SPEC benchmarks are TLB-heavy, not on how heavy.**
   - **Data side:** Spearman 0.89 for L1 misses and 0.82–0.91 for second level / walks. x86/ARM medians are 2.8× (L1), 1.6× (vs ARM L2-TLB) and 2.3× (vs ARM walks).
   - **Code side:** both are tiny, x86 ~50× higher, and the ranks agree loosely (0.60–0.66).
   - The ratio mixes TLB geometry with workload, so state the rank agreement, not "x86 misses 3× more".
6. **The code footprint does not predict instruction-TLB pressure** (Server: Spearman 0.28 against report 24's footprint).
   - naivebayes has the largest footprint (11.97 MB) but 0.06 L1 instruction-TLB MPKI.
   - Page spread and reuse, not unique lines, set the TLB load. The two metrics are complementary.
7. **Stores are a large share of x86's L1 data-TLB misses.** SPEC median 3.34 MPKI for stores vs 4.17 for loads, and stores exceed loads on 8 of 26 benchmarks; Server 2.26 vs 8.74. The load/store split exists only on x86 (ARM's `L1D-TLB` counts both together).
8. **The x86 instrument is consistent with the banked campaigns:**
   - SPEC `itlb_walk_pct` correlates at 0.95 across campaigns 3 months apart;
   - the Server code-TLB ranking matches a different event (`icache_tag.stalls`) at 0.95.
   - Zero multiplexing in 54,036 windows.
