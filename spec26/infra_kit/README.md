# spec26/infra_kit — snapshot of the SPEC CPU 2026 capture kit (code only)

**Imported:** 2026-11-02 from P7 `~/spec26-infra/infra` (branch `spec-x86`, inherited by
`spec-arm`). Until now the kit lived only outside the repo (see `spec26/README.md`). The ARM
campaign cannot reach P7's disk, so the code is versioned here. **On P7 the live copy is still
`~/spec26-infra/infra`.** Edit there and re-copy, or move P7 over to this copy deliberately.
Never keep two diverging live copies.

What is here:

| Path | What |
|---|---|
| `scripts/run_spec_campaign.sh` | Stages `preflight`, `dryrun`, `isolation-test`, `setup`, `episode`, `campaign`, `status`; shield + ISO-PROOF + fenced `systemd-run` scope + 11-group zero-mux rotation + continuous TMA (Intel-only events) |
| `scripts/build_one.sh`, `spec_env.sh` | Builds one benchmark outside the fence; `spec_env.sh` holds the SPEC root, config, label and the 26-benchmark list |
| `scripts/extract_cmd.py`, `clean_rundir.py`, `verify_output.py` | Get the exact ref command line out of a run dir (`specinvoke -n`); reset generated outputs between runs; SPEC's own output check after a run. **Architecture-neutral: reuse on ARM.** |
| `scripts/quiet_gate.py` | Whole-machine quiet gate and witness (waits for other users' work to stop, never kills it). Architecture-neutral |
| `scripts/extract_metrics.py`, `validate_spec.py`, `perf_census.py` | x86 metric formulas and gates (Intel event names) |
| `scripts/counter_group_episode.sh` | 2026-11-04: SPEC episodes for a chosen set of counter groups (`GORDER_OVERRIDE`, fresh `DATA_ROOT`): the campaign's own `run_episode` inside the footprint run's quiet gates, witness and verified restore. Used for the TLB groups `tlb_d`/`tlb_i` (`run_spec_campaign.sh`; results `spec26/tlb_x86/`) |
| `scripts/llc_dram_crosscheck.sh`, `xcheck_report.py`, `xcheck_calib.c`, `plot_llc_dram_violins.py` | The 2026-10 LLC/DRAM cross-check against the memory controllers (see `docs/spec26_profile_validation.md`) |
| `config/uarch-gcc14.cfg` | The x86 build config (gcc 14, `-g -O3 -march=native`, copies = 1, threads = 1) |
| `config/uarch-gcc14-aarch64.cfg` | The ARM twin: identical except `-mabi=lp64` and `-mcpu=native`, plus hw fields to fill in |
| `campaign.conf`, `cmd_index.tsv` | Partition, window and input-index settings (P7-specific values) |
| `docs/spec26_profile_validation.md` | Validation findings and known issues of the x86 profile (LLC_MPKI and DRAM_read_GBs mislabelled, ref input 0 only, …). Read before comparing anything |
| `x86_results/<bench>/{metrics.json,metadata.json}` | Per-benchmark x86 episode values (P7, 2026-08-05 campaign), so the ARM run can compare without P7 access |
| `llc_dram_xcheck/` | Cross-check summaries and the campaign-vs-corrected violin figures (`plots/README.md` explains them) |

Not here (and never to be committed — this repo is public): SPEC sources, binaries, inputs or
run directories (SPEC CPU 2026 is licensed), and raw perf window files (1.4 GB).
