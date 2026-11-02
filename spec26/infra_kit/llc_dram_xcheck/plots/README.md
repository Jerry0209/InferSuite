# LLC and DRAM: campaign vs cross-check re-run

Built by `scripts/plot_llc_dram_violins.py` (needs matplotlib + numpy) from:

- `data/`: the original campaign, unchanged;
- `data_llc_xcheck/`: re-run of 782.lbm_r, 749.fotonik3d_r, 765.roms_r, 772.marian_r, 710.omnetpp_r and 767.nest_r, all ref input 0 (same input as the campaign);
- `data_llc_xcheck_nest/`: 767.nest_r inputs 0, 1 and 2 (`767.nest_r@k`).

Ignore `772.marian_r.contaminated.1` and `_session.aborted.1`. Those runs overlapped another user's job and were re-run.

| file | what it is |
|---|---|
| `llc_violin.png` | per 100 ms window: campaign `LLC_MPKI` (blue) vs re-run `longest_lat_cache.miss` per 1000 inst (orange) |
| `dram_violin.png` | campaign `DRAM_read_GBs` per 100 ms window (blue) vs re-run memory-controller read+write GB/s per 0.5 s (orange) |
| `summary.csv` | one row per benchmark: campaign value, the same definition re-measured, the corrected metric, sample counts |
| `per_window.csv` | every window/sample behind the violins |

## Definitions

- **`LLC_MPKI` (campaign):** `mem_load_retired.l3_miss`, i.e. retired demand loads only. Prefetches, store misses (RFO) and fill-buffer hits are not counted.
- **LLC misses, corrected:** `longest_lat_cache.miss`, i.e. every core request that misses L3. It matches 93–96% of the memory controller's reads on lbm, fotonik3d and roms.
- **`DRAM_read_GBs` (campaign):** `offcore_requests.data_rd` × 64 B, i.e. reads leaving L2. It includes L3 hits and excludes RFOs and writebacks.
- **DRAM, corrected:** `unc_m_cas_count.rd + .wr` × 64 B at the memory controllers. This is system-wide, so each episode has two things subtracted:
  - the idle rate measured just before it;
  - the capture stack's own traffic, measured on an empty fence: 0.40 GB/s in `data_llc_xcheck`, 0.34 GB/s in `data_llc_xcheck_nest`.

## Caveats

- **Low traffic:** below about 0.3 GB/s (omnetpp, nest inputs 1 and 2), the corrected DRAM figure is only good to about an order of magnitude. Single 0.5 s samples can go negative, and those are drawn at 0.01.
- **nest inputs 1 and 2:** the campaign never ran them, so they have no blue half.
- **Same-definition check:** with the campaign's own definitions, the re-run reproduces the campaign (`*_rerun_same_def` columns). The exceptions are `DRAM_read_GBs` for marian (9.8 → 7.2) and nest (4.6 → 8.9). That metric includes L3-hit traffic, so it shifts with what else is resident.
- **Full write-up:** `spec26_profile_validation.md`, §1 and §3.
