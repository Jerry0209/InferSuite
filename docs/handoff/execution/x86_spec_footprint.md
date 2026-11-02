# Execution — SPEC CPU 2026 front-end footprint on x86 (P7)

**Owner:** Tianrui (Jerry) · **Written:** 2026-11-02 · **Status:** ready to execute
**Machine:** P7 (`networking-ThinkStation-P7`, Xeon w5-3425) · **Results branch:** `spec-x86`
**Request:** Rahul, 2026-11: instruction footprint, unique taken branches and weighted average
targets per taken branch, for SPEC26 (this doc), Server ([`x86_server_footprint.md`](x86_server_footprint.md)) and Agentic (Jef).
**Method:** [`frontend_footprint_method.md`](frontend_footprint_method.md) — read it first; it
is the contract. This doc is only the "how to run it on SPEC" part.

## 0. Done means

* 26 SPECrate benchmarks (the existing campaign's set: ref input, copies = 1, ref command
  index 0), each with a clean LBR footprint episode under the shield, its output check
  passed, and an analyzer summary.
* Gates V1–V4 of the method contract recorded (V3 on 3 benchmarks).
* `spec26/frontend_footprint_x86/` on branch `spec-x86`: per-benchmark `summary.json`,
  `frontend_footprint_rows_long.csv` (all benchmarks, long format), `MANIFEST.md`, the analyzer source
  and SHA. A study report and a session log are written, and the branch is pushed.

## 1. Blocking checks — do these before touching anything

1. **Disk.** `df -h /`. On 2026-11-02 the root filesystem had **8.6 GB free (100 % used)**.
   This campaign needs **≥ 60 GB free** (one compressed `perf.data` at a time is 1–3 GB, plus
   the PT cross-check). If it is below that, **stop and ask Jerry to free space**. Never delete
   files you did not create. `du -sh ~/* ~/.cache/* 2>/dev/null | sort -h` helps him decide.
2. **Shared box.** Jef (`jeferson`) profiles the same cores from `agentic.slice`.
   * `pgrep -a -x perf` must show nothing that is not yours.
   * `who`, and `ps -eo user,pcpu,comm --sort=-pcpu | head`, must show no foreign heavy work.
   * If either is busy, **wait**: `python3 ~/spec26-infra/infra/scripts/quiet_gate.py` blocks
     until the machine is quiet. Never kill or renice another user's process, and never
     capture concurrently: LBR and the PMU are per-core hardware, so both captures would be
     corrupted.
3. **Read**, in this order:
   * the method contract;
   * `~/spec26-infra/infra/spec26_profile_validation.md`, especially §1.4 (shared L3) and
     §1.5 (`restore_isolation` widens the house cpusets on this box);
   * `docs/handoff/README.md` §3 (the partition and the shared-box rule).
4. **Kit state.**
   * `cd ~/spec26-infra/infra && ./scripts/run_spec_campaign.sh status` must show all 26
     built and set up. The binaries and run dirs from the August campaign are there; do not
     rebuild.
   * perf is `$(ls -d /usr/lib/linux-tools-6.8*/perf | tail -1)`. Always glob: package
     updates move it, and `/usr/bin/perf` is broken.
5. **Branch.** `cd ~/InferSuite && git fetch && git switch spec-x86` (it has
   `spec26/infra_kit/`, a snapshot of the live kit, and these docs). The live kit stays at
   `~/spec26-infra/infra`. Run from there, and copy new scripts into
   `spec26/infra_kit/scripts/` when committing.

## 2. Step 1 — the analyzer, validated before any production capture

Implement the analyzer exactly as §4 of the contract specifies, once, at
`local_agents/kit/frontend_footprint/` in the repo (this path exists on both `spec-x86` and `dcperf`,
so the Server run reuses the same code: cherry-pick the commit onto `dcperf`).

* Suggested files: `lbr_footprint.cpp` (C++17, reads `perf script -F pid,brstack
  --show-mmap-events` on stdin, writes the summary JSON and the edge table), `Makefile`,
  `footprint_validate/` (V1 synthetic program and its expected values), `README.md`.
* Python is too slow for the volume: about 30 k samples/s × 32 entries per benchmark-second.
  Use C++ or Rust; perf script itself decodes about 110 k samples/s on P7.
* **Run V1** (synthetic truth) and **V2** (exact Intel PT cross-check on 2–3 short programs)
  now, on house core 1 with `taskset`. Record the numbers in the session log. If V1 fails, fix
  the analyzer before going on.
* Commit the analyzer on `spec-x86` and note its SHA. Every summary records `analyzer_sha`.

## 3. Step 2 — the footprint episode driver

Write `~/spec26-infra/infra/scripts/frontend_footprint_episode.sh`, modelled on
`llc_dram_crosscheck.sh`. That script already does each of the following, so copy its
patterns:

* it **sources** `run_spec_campaign.sh` (`source "$XKIT/run_spec_campaign.sh" help >/dev/null`)
  instead of copying the fence;
* it wraps `restore_isolation` so the pre-shield **effective** cpusets are put back
  (`pre_cpuset.tsv`; this is the §1.5 bug fix and is mandatory);
* it runs `quiet_wait 60`, the 2 s witness and the `contaminated()` rule: an episode that
  overlapped foreign work is set aside and re-run, up to 3 tries;
* it supports `<bench>@<k>` for other ref inputs (not needed for the main run).

What changes is only the instruments. Override `cycle_stats`, the windowed rotation, so that
for the life of the scope, from the house cores (`taskset -c "$CPUS_HOUSE"`), it runs:

```bash
# the contract's capture, scoped to the fence on the measured cores
$PERF record -z -m 512M -e br_inst_retired.near_taken -c 20011 -j any,save_type \
      -a -C "$CPUS_MEASURED" --cgroup="$CG" -o "$OUT/lbr.data" &
$PERF stat -x, -a -C "$CPUS_MEASURED" -e instructions,br_inst_retired.near_taken \
      --for-each-cgroup="$CG" -o "$OUT/exact_counts.csv" &
# ... wait while the scope is active, then SIGINT both
```

* Disable `start_records` (the 99 Hz record) and `start_tma_cont` for these episodes. They
  are not needed, and the fewer PMU users the cleaner. Keep the 10 Hz `cpu.stat` pollers
  (they give the occupancy gate).
* **Verify the event and flag syntax on the box first** with a 1 s probe. `perf record --help`
  documents `--cgroup` per event; if perf rejects it combined with `-C`, use `-a` alone (the
  fence is pinned to the measured cores anyway) and say so in the metadata.
* After the scope exits:
  1. run SPEC's output check (`verify_output.py`, as `run_episode` already does);
  2. write `metadata.json` with the contract parameters, perf version, period, window and
     exit status;
  3. run `perf script -i lbr.data -F pid,brstack --show-mmap-events | lbr_footprint`;
  4. check lost records (`perf report -i lbr.data --stats`, or the `LOST` lines in
     `perf script --show-lost-events`);
  5. only if everything passed, delete `lbr.data` and keep `summary.json` +
     `edges.tsv.zst`.
* Data root: `DATA_ROOT=~/spec26-infra/infra/data_frontend_footprint` (outside git).

## 4. Step 3 — smoke

1. `736.ocio_r` (shortest: 10 s on index 0) and `729.abc_r` (12 s).
2. Check:
   * the episode wall time is within ~10 % of the August campaign's `wall_s` (LBR sampling
     overhead; the instruction stream is deterministic, so overhead does not change the
     metrics);
   * lost records < 1 %;
   * occupancy ≈ 1.0 core;
   * output check `pass`;
   * the convergence curve is printed;
   * the user/kernel split is plausible (kernel share small for SPEC).
3. Restore the machine and verify. The house cpusets must read `0-3,12-15`.

## 5. Step 4 — the campaign

* All 26, index 0, one at a time, quiet gate before each. Expected cost: about 47 min of
  benchmark time (sum of the August `wall_s`) plus 1–3 min of analysis each, so roughly
  2–3 h. Run it under `tmux`/`nohup` with resumable DONE markers (the existing runner's
  convention), because a session can die.
* **V3 sensitivity:** re-run `736.ocio_r`, `721.gcc_r` and `749.fotonik3d_r` with
  `-c 5003`, into a separate data root. Report the unique-count ratios.
* Expected "unavailable" output checks, as on x86 before: `734.vpr_r`, `735.gem5_r` and
  `772.marian_r` cannot be verified when run as one command line. Their instruction counts
  must match the August campaign within 1 % instead (`x86_results/<bench>/metrics.json` on
  this branch).
* Optional, only after everything above is pushed: other ref inputs via `<bench>@<k>`. The
  August data is index 0 only (validation issue 1.6), so these would be extra rows, never
  replacements.

## 6. Step 5 — aggregate and hand over

* `spec26/frontend_footprint_x86/`:
  * one `summary.json` per benchmark;
  * `frontend_footprint_rows_long.csv` with columns
    `workload,family,subgroup,metric,value,analyzer_sha,period` (family = `spec26`,
    subgroup = `SPEC-int`/`SPEC-fp`, matching `local_agents/RealData/data/l3_study/workload_index.csv`);
  * `gates.csv` (V1–V4 per benchmark);
  * `MANIFEST.md` with definitions and the lower-bound caveat.
* A preliminary SPEC-only violin per metric is fine for a sanity look. The real figure
  (Agentic vs SPEC vs Server) waits for Jef's data and the Server run.

## 7. Step 6 — document, push, restore

1. Keep a **session log** from the first action (`/handoff`, `docs/handoff/sessions/`).
2. Write the **study report** (`/study-report`, next free number in `docs/reports/`), in the
   fixed three-part format, including the V2 recall numbers and every defect found.
3. Commit on `spec-x86`:
   * analyzer + driver (copied into `spec26/infra_kit/scripts/`), `spec26/frontend_footprint_x86/`,
     report, session log;
   * **no Claude attribution lines** (repo rule), nothing ≥ 100 MB;
   * no SPEC sources, binaries or inputs: **the repo is public**.

   `/report-check-commit` does the checks and the push.
4. Cherry-pick the analyzer commit onto `dcperf` for the Server run.
5. Final machine check:
   * house cpusets `0-3,12-15`;
   * `measured.slice` back to its pre-run value;
   * governors and `no_turbo` restored;
   * no `spec-*` scopes and no `perf` left.

## 8. Hazards already known

| Hazard | What happens | Guard |
|---|---|---|
| Disk full | `perf record` truncates; corrupt or partial data | §1 check; delete `lbr.data` only after the summary verifies |
| Jef capturing at the same time | Both LBR and PMU data corrupted | §1 check, quiet gate, witness |
| `restore_isolation` on this box | Widens system/user/init to 0–15 after every run | `pre_cpuset.tsv` wrapper (from `llc_dram_crosscheck.sh`) |
| Other perf users holding the PMU | `<not counted>` or failed `perf record` | `pgrep -a -x perf`. Only kill **your own** orphans |
| Sampling bias on unique counts | Lower bounds, workload-dependent | Same period everywhere; V2 recall; V3 ratio; convergence curve |
