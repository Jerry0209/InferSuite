# TLB hierarchy, x86 SPEC CPU 2026 — MANIFEST

Captured 2026-11-04 21:59–23:20 on P7 (Xeon w5-3425, Golden Cove), 26/26 rate benchmarks, ref
input index 0, copies = 1, by `spec26/infra_kit/scripts/counter_group_episode.sh` into
`~/spec26-infra/infra/data_tlb` (raw windows, 1.5 GB, not in git). Requested by Jef for parity
with the ARM `tlb-data` / `tlb-code` families (`spec-arm`, report 23). Session log:
`docs/handoff/sessions/2026-11-04_x86-tlb-hierarchy.md` (branch `dcperf`).

## Instrument

The campaign's own episode (report 18), with the rotation restricted to two new groups
(`GORDER_OVERRIDE="tlb_d tlb_i"`): fenced `systemd-run` scope on the measured cores 4–11 (SMT
siblings offline), 100 ms windows, one group per window, shuffled each cycle, zero
multiplexing, continuous TMA alongside, THP `never`.

| Group | Events (+ `cycles`, `instructions` on the fixed counters) |
|---|---|
| `tlb_d` | `dtlb_load_misses.stlb_hit`, `dtlb_load_misses.walk_completed`, `dtlb_store_misses.stlb_hit`, `dtlb_store_misses.walk_completed` |
| `tlb_i` | `itlb_misses.stlb_hit`, `itlb_misses.walk_completed`, `itlb_misses.walk_active`, `dtlb_load_misses.walk_active` |

## Metrics (episode ratios of sums, co-counted denominators; `extract_metrics.py`)

On Intel an L1 TLB miss either hits the shared second-level TLB (STLB) or starts a page walk,
and an STLB miss is a walk. So L1 misses = `stlb_hit + walk_completed` and STLB misses =
`walk_completed`. `walk_completed` leaves out walks that were aborted (wrong-path), so the L1
counts are slightly low.

| Column | Formula | ARM counterpart (pairing) |
|---|---|---|
| `dTLB_L1_MPKI` | 1000 (load + store `stlb_hit` + `walk_completed`) / instr | `L1D-TLB MPKI` (analogue) |
| `dTLB_L1_load_MPKI`, `dTLB_L1_store_MPKI` | the load and the store halves | — |
| `dTLB_walk_MPKI` | 1000 (load + store `walk_completed`) / instr = data STLB misses | `L2-TLB MPKI` and `DTLB-walk MPKI` (analogue) |
| `dTLB_STLB_hit_pct` | share of L1 data-TLB misses served by the STLB | — |
| `iTLB_L1_MPKI` | 1000 (`itlb_misses.stlb_hit` + `walk_completed`) / instr | `L1I-TLB MPKI` (analogue) |
| `iTLB_walk_MPKI` | 1000 `itlb_misses.walk_completed` / instr | `ITLB-walk MPKI` (analogue) |
| `iTLB_STLB_hit_pct` | share of L1 instruction-TLB misses served by the STLB | — |
| `STLB_MPKI` | `dTLB_walk_MPKI + iTLB_walk_MPKI` (each over its own group's instructions) | — |
| `dtlb_load_walk_pct`, `itlb_walk_pct` | 100 `walk_active` / cycles: cycles with a page walk in progress | none on ARM |

ARM's `L2-TLB MPKI` and `DTLB-walk MPKI` are separate counts on Neoverse-V3 (median 0.128 vs
0.041 MPKI), while on x86 an STLB miss and a walk are the same event, so both pair with
`dTLB_walk_MPKI`. Cross-ISA numbers use ARM's ratio of sums (report 23, D12), never its window mean.

## Gates and checks

* Every episode: EPISODE-OK (exit 0, windows ≥ 55, occupancy 0.997–1.000 core; specdiff PASS,
  except 734.vpr_r, 735.gem5_r and 772.marian_r, whose outputs are not specdiff-testable from one
  command line, as in every earlier SPEC run),
  witness clean on the first attempt (no episode set aside), `validate_spec.py` PASS (26/26).
  RESTORE-VERIFY PASS at the end.
* Multiplexing: 0 of 21,988 windows. `<not counted>`: 27 windows (0.12 %; 13
  `dtlb_load_misses.walk_active`, 14 `dtlb_store_misses.walk_completed`), dropped for that event
  only by the co-counted denominators. The banked 11-group campaign: 35 of 22,413 (0.16 %).
* Event semantics, before capture (pointer chase, one load per 4 KB page in random order,
  user mode): 1 GB region 0.999 walks per load; 6 MB region 0.965 STLB hits + 0.035 walks per
  load; store and code walks 0.000.
* Cross-check against the banked campaign (report 18, group `fe_l3x`, same event):
  `itlb_walk_pct` median relative difference +3.6 %, median |difference| 16 %, Spearman 0.95.
  Column `itlb_walk_pct_rel_diff`.

## Files

| File | What |
|---|---|
| `spec_tlb_x86.csv` | One row per benchmark: episode facts, the 11 TLB metrics, IPC, the `fe_l3x` cross-check |
| `arm_vs_x86_tlb.csv` | Benchmark × the 5 ARM TLB metrics: ARM ratio of sums, x86 value, x86/ARM, pairing |
| `per_benchmark/<bench>.metrics.json` | The episode's `metrics.json` as banked (every metric of the two groups + TMA) |

## Regenerate

```bash
cd ~/spec26-infra/infra
python3 scripts/extract_metrics.py data_tlb/7*        # metrics.json per episode
python3 scripts/validate_spec.py  data_tlb/7*         # exit 0 = every evaluable gate passes
cd ~/InferSuite   # branch spec-x86
python3 spec26/kit/tlb/aggregate_spec_tlb.py --data ~/spec26-infra/infra/data_tlb
```

Capture (about 80 min for the 26 benchmarks, quiet gates included):

```bash
GORDER_OVERRIDE="tlb_d tlb_i" DATA_ROOT=$PWD/data_tlb ./scripts/counter_group_episode.sh
```
