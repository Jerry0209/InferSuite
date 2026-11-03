# frontend_footprint — LBR front-end footprint analyzer

Implements §4 ("Analyzer rules") of the method contract
[`docs/handoff/execution/frontend_footprint_method.md`](../../../docs/handoff/execution/frontend_footprint_method.md)
for Rahul's three front-end metrics (SPEC26, Server, Agentic families):

1. **instruction footprint** — unique 64 B instruction lines executed × 64 B;
2. **unique taken branches** — distinct branch instructions ever taken;
3. **weighted average targets per taken branch** — `Σ C_b·T_b / Σ C_b` (the literal metric,
   `wavg_targets_*`), reported with two sampling-robust companions, `weff_targets_*` and
   `wavg_targets_ge1pct_*` (see [Metric 3 and its companions](#metric-3-and-its-companions)).

Not to be confused with `local_agents/kit/dcperf/measure_footprint.sh`, which measures the
*data* (memory) footprint.

| File | What |
|---|---|
| `lbr_footprint.cpp` | the analyzer (C++17, no dependencies, one streaming pass) |
| `Makefile` | `make` builds `./lbr_footprint` with the source's sha256 embedded |
| `footprint_validate/` | gates V1 (synthetic truth) and V2 (exact Intel PT cross-check) |
| `aggregate.py` | episodes → `per_benchmark/`, `frontend_footprint_rows_long.csv`, `gates.csv`, `gates_global.csv`, generated `MANIFEST.md` (stdlib python) |
| `plot_frontend_footprint.py` | violins per metric from one or more long CSVs (SPEC, Server, Agentic), conda `infersuite-full` python |

## Build and run

```bash
make                                   # -> ./lbr_footprint ; ./lbr_footprint --version
P=$(ls -d /usr/lib/linux-tools-6.8*/perf | tail -1)
$P script -i lbr.data -F pid,brstack --show-mmap-events --show-task-events --show-lost-events \
  | ./lbr_footprint --mode lbr --analyzer-sha <git sha> --summary summary.json \
      --edges edges.tsv --objects objects.tsv --lines lines.tsv --meta workload=<b> --meta period=20011
# exact reference (V2): Intel PT branch trace, never stored as text
$P script -i pt.data --itrace=be -F pid,tid,ip,addr,flags --show-mmap-events --show-task-events \
  | ./lbr_footprint --mode pt --summary pt.json --edges ... --objects ... --lines ...
```

Flags: `--mode lbr|pt` (default lbr), `--summary/--edges/--objects/--lines FILE` (each optional),
`--analyzer-sha SHA` (echoed as `analyzer_sha`; the compile-time sha256 of the source is always
written as `analyzer_src_sha256`), `--meta k=v` (repeatable, copied verbatim into `meta`),
`--snapshot-every N` (convergence granularity; default 1000 samples / 1e6 PT branches),
`--input FILE` (instead of stdin), `--no-pt-classify`. A one-line result goes to stderr; it
includes the literal, `weff` and `ge1pct` weighted averages (all / noret / ind).
Exit status 0 on success; a summary never contains a top-level `error` key unless it failed.

## Input

* **LBR**: `pid` then up to 32 entries `from/to/pred/in_tx/abort/cycles/TYPE/spec`, newest
  first. Near types are `COND UNCOND CALL IND_CALL IND RET`; every other type (`SYSCALL`,
  `SYSRET`, `IRQ`, `ERET`, `-`, …) is a far transfer. Entries with `from` or `to` = 0 are skipped
  and counted.
* **PT**: `pid tid flags ip => addr` (tid optional). `tr strt 0 => X`: tracing (re)starts at X;
  `tr end <why> X => 0`: tracing stops at X; `instruction trace error` lines (from `--itrace=e`)
  are counted and invalidate that thread's resume point.
* **Side-band** (any prefix: `0`, `pid`, `pid/tid`): `PERF_RECORD_MMAP`/`MMAP2` (pid taken from
  the `pid/tid:` token; only executable mappings; pid −1 = kernel image and modules),
  `COMM exec` (drops the pid's user mappings), `FORK` (a new process inherits a copy of the
  parent's mappings; a synthesized FORK — leading pid 0 — starts empty because its own
  synthesized MMAPs follow; same pid = new thread, nothing to do), `EXIT` (counted; mappings are
  kept because PT prints a thread's branches just before its EXIT), `LOST`/`LOST_SAMPLES`.
  Events are applied in stream order, so each sample is resolved against the mappings valid at
  that point. With `-a`, perf emits mappings for every process on the machine; they cost a few
  hundred bytes each.

## Canonical addresses (contract §4.2)

| Address | Canonical key | `objects.tsv` kind |
|---|---|---|
| file-backed executable mapping | (path, inode) + `addr − map_start + pgoff` (= file offset) | `file` |
| kernel, `addr ≥ 0xffff800000000000` | (kernel, addr) — one object for kernel text and modules | `kernel` |
| anonymous / JIT mapping (`//anon`, `[anon:…]`, `[heap]`, …) | (pid, addr), never merged across processes | `anon` |
| *extension:* `[vdso]`, `[uprobes]` (no inode, same code in every process) | name + offset, like a file | `special` |
| *extension:* `[vsyscall]` page (fixed at 0xffffffffff600000, user-visible) | name + offset, counted as user | `special` |
| *extension:* user address in no known mapping | (pid, addr) as anonymous; counted in `unmapped_entries` | `anon` |

Each exec (and each fork) starts a new anonymous object for the pid, so pid reuse never merges
two processes' JIT code. Keys are packed as `obj_id << 47 | offset` (user VAs and kernel VAs
minus `0xffff800000000000` fit in 47 bits); mappings are page aligned, so the 64 B line of a key
is `key & ~63` in VA and canonical space alike.

## Footprint and branch rules

* **LBR footprint** (contract §4.3): for consecutive entries `e[k]` (older) and `e[k-1]`
  (newer), the straight-line run `[e[k].to, e[k-1].from]` is added line by line if
  `0 ≤ from − to ≤ 4096` and both ends are in the same mapping (the same kernel MMAP region, or
  the same user mapping of that pid); otherwise it is a discontinuity, counted by reason
  (`cross_mapping`, `negative`, `over_4096`, `unmapped_end`). Plus `line(from)` and `line(to)` of
  every non-zero entry, far entries included.
* **PT footprint** (exact): per thread, the run from the previous resume point (previous branch
  target or `tr strt` target) to the current branch `ip` — or to the `tr end` IP, inclusive for
  `syscall`-type ends (X executed) and exclusive for `async` (X is the next, unexecuted
  instruction) — with the same-mapping check and no 4096 cap (a 1 MiB sanity bound is counted as
  a discontinuity), plus `line(ip)` and `line(addr)` of every branch.
* **Per branch** b (canonical `from`, near types only): `C_b` = entries with that `from`,
  `T_b` = distinct canonical `to`. `Σ C_b·T_b` is maintained incrementally, so convergence
  snapshots are O(1). A branch's type is the type of its first entry (`type_conflicts` counts
  disagreements).
* **Metric 3 companions**: computed in a final pass over the (from, to) → count edge table,
  grouped by canonical `from`, near types only; see the next section.
* **PT types**: PT says `jmp`/`call` but not whether they are indirect. The analyzer reads the
  branch's own bytes from the object file at the canonical (= file) offset (inode checked;
  `[vdso]` from its own vdso, same kernel) and decodes `E8`/`E9`/`EB` vs `FF /2`/`FF /4`
  (prefixes and REX skipped). Undecodable sites stay `JMP_UNK`/`CALL_UNK` (counted).

## Metric 3 and its companions

The literal metric `wavg_targets_*` = `Σ C_b·T_b / Σ C_b` uses `T_b`, the number of
**distinct** targets of branch b. That is a unique count, so under LBR sampling it is a
**sampled lower bound**, like metrics 1 and 2: a target taken rarely is rarely seen. In V2 on
`v2_python`, a hot return executed 5.1 M times has 100 targets; its 8 432 sampled executions
saw 20. Combining LBR's sampled `C_b` with PT's exact `T_b` gives 6.892 against PT's 6.859, so
the whole error is in `T_b`, not in the weights.

Two companions measure frequency-weighted quantities instead. LBR samples estimate those
without the rare-event bias. Both are weighted by the same `C_b` (entry count) as the literal
metric, and both are computed from the per-target counts `n_t` of each branch (`n = Σ n_t`):

* **`weff_targets_*`** = `Σ C_b·E_b / Σ C_b`. `E_b = 1 / Σ_t p_t²` is the effective number of
  targets (inverse Simpson index). For `Σ p²`, lbr mode uses the unbiased estimator
  `Σ n_t(n_t−1) / (n(n−1))` (for n ≥ 2), and pt mode uses the plug-in `Σ (n_t/n)²` (its counts
  are exact). `E_b = 1` when n = 1. `E_b` is capped at the observed distinct count `T_b`, which
  also covers an estimate of 0 (every target seen once).
* **`wavg_targets_ge1pct_*`** = `Σ C_b · max(1, #{t : n_t/n ≥ 1 %}) / Σ C_b`: the number of
  targets that each carry at least 1 % of the branch's executions.

Each comes in `_all`, `_noret` and `_indirect` classes (same classes as the literal metric),
each with `_user` and `_kernel` variants. V2 on `v2_python`, LBR relative to exact PT
(user space; `compare_v2.py` reports all three families):

| | literal | inverse Simpson | ≥ 1 % |
|---|---|---|---|
| all | −61.1 % | −0.1 % | −0.0 % |
| noret | −42.6 % | −0.1 % | +0.2 % |
| indirect | −55.1 % | −0.3 % | +0.3 % |

## Outputs

**`summary.json`** (top level): `footprint_bytes`, `_user`, `_kernel`, `footprint_lines`;
`unique_taken_branches`, `_user`, `_kernel`, `unique_taken_branches_by_type` (all/user/kernel);
`wavg_targets_all`, `wavg_targets_noret` (RET excluded), `wavg_targets_indirect` (IND +
IND_CALL), each also `_user`/`_kernel`, followed by the companions `weff_targets_{all,noret,
indirect}` and `wavg_targets_ge1pct_{all,noret,indirect}`, each also `_user`/`_kernel`;
`taken_entries_by_type`; `far_transfers` (entries,
`unique_from`, entries by type); `convergence`; `processes_with_samples`, `top_processes`
(pid, comm, samples or branches, share); `top_objects_by_footprint` and
`top_objects_by_entries` (20 each: how much is the benchmark vs bash/ld.so/libc/kernel);
`diagnostics`; `analyzer_sha`, `analyzer_src_sha256`, `mode`, `meta`.

`diagnostics`: `samples` (PT: branch records), `entries`, `near_entries`, `far_entries`,
`zero_address_entries`, `unmapped_entries`, `kernel_unmapped_entries`, `candidate_ranges`,
`discontinuities`, `discontinuity_rate`, `discontinuities_by_reason`, `lost_samples` (sum of the
counts in `PERF_RECORD_LOST` and `LOST_SAMPLES` lines), `lost_records`, `unparsed_lines`
(+ examples), `type_conflicts`, event counts, `unique_edges`, PT-only `pt_*` counters
(`pt_trace_errors`, classification counts, …), `elapsed_s`, `samples_per_s`.

`convergence.points`: unique counts (exact, from first-seen) and `wavg_targets_all` (from the
nearest snapshot) at 25/50/75/100 % of the samples in time order;
`last_quarter_growth_pct` = share of the final unique count first seen in the last quarter
(well above 0 means the count is still rising: a sampling-limited lower bound — say so);
`curve` = up to 100 snapshots.

**`objects.tsv`**: `obj_id kind path inode pid` (only objects that were hit; `pid` −1 except
anon). **`lines.tsv`**: `obj line_off first_seen`. **`edges.tsv`**: `from_obj from_off to_obj
to_off type count first_seen`, near and far edges (far `to` is `-` for a PT trace end).
Offsets are hex file offsets; kernel offsets are printed as the full kernel address.
`first_seen` is the 1-based sample (PT: branch) ordinal at which the line/edge first appeared, so
the footprint, the branch counts and the weighted averages — and their values at any prefix of
the run — can be recomputed from the tables without the perf.data.

## Known approximations

* **Sampled lower bounds.** Metrics 1 and 2 count only what the samples saw (each taken branch
  is captured with probability 32/period). So does the literal metric 3, through `T_b`. Its
  weights `C_b` are unbiased, but its distinct-target counts are not. The companions
  `weff_targets_*` and `wavg_targets_ge1pct_*` do not have that bias (see above). V2 makes all of
  this quantitative.
* A branch instruction that straddles a line boundary can miss its second line (≤ 1 line per
  range); the 4096 B cap drops longer straight-line runs (counted as discontinuities).
* All entries of a sample are resolved against the sampled pid's mappings. This relies on x86
  perf flushing the LBR when a task is scheduled in during system-wide LBR sampling, so a
  sample's user entries belong to that task (kernel entries are pid-independent anyway).
* An address in kernel space outside the kernel's MMAP regions (BPF, trampolines) keeps the
  (kernel, addr) key but cannot be part of a straight-line run.
* PT with `tsc=0` (the contract's setting) is decoded "timelessly": no context-switch sideband,
  so it is only valid when one process runs the traced code (plus `exec`). For commands that
  fork, use `PT_EVENT='intel_pt/cyc=0,mtc=0,noretcomp=0/u'`; `compare_v2.py` warns when a
  process seen by LBR is missing from the PT decode.
* Capture with the PEBS event `br_inst_retired.near_taken:pp` (contract v1.1). With the bare
  event the LBR is frozen at the PMI, after interrupt skid. That skid is counted in instructions,
  so it spans more branches in branch-dense code, and some 32-branch windows become
  systematically more likely than others. On V1 this biased per-branch entry shares by
  −20 %…+12 % and the weighted averages by −1.8 % (all), −2.0 % (noret) and −3.7 % (indirect).
  With `:pp`, adaptive PEBS writes the LBR at the overflowing branch, and V1 passes at ≤ 0.10 %.
  Unique counts were exact either way.
* Throttling: the kernel can drop samples when `perf_event_max_sample_rate` is exceeded.
  `samples × period` against the exact `br_inst_retired.near_taken` count from `perf stat`
  detects it (it matched to 0.99998 in the 2026-11-02 probe); the episode driver gates on that
  ratio and on perf's `THROTTLE` record count.

## Validation

**V1 — synthetic truth** (`footprint_validate/`): `v1_synth` runs hand-placed assembly
(`v1_regions.S`): (a) 8 chained 40-line blocks of nops, each ending in a 5-byte `jmp`; (b)
indirect call sites with K = 1, 4 and 16 targets on fixed non-uniform schedules, called 3, 1 and
2 times per pass; (c) 500 always-taken `jz`. `check_v1.py` derives the truth from the design plus
`nm`/`objdump`/the ELF headers of the built binary (constants and schedules are read back from
the binary): **368 lines, 541 unique taken branches, wavg all 1.403053 (919/655), noret 1.442953
(860/596), indirect 6.5 (39/6)**. Pass = footprint within 2 lines, branch count exact, every
weighted average within 1 %.

```bash
footprint_validate/run_v1.sh <outdir>          # build, capture ~4 s on core 1, analyze, check
footprint_validate/sim_v1_lbr.py --binary footprint_validate/v1_synth | ./lbr_footprint ...
                                               # offline self-test (no capture): must PASS;
                                               # --break-k16 must FAIL
```

**V2 — exact Intel PT cross-check**: `run_v2.sh <name> <outdir> [--cwd DIR] [--env-file FILE] --
<cmd...>` captures the command once with PT (user only) and once with the contract's LBR
settings on core 1, streams the PT decode into `--mode pt`, deletes `pt.data`, and runs
`compare_v2.py`: recall (|LBR ∩ PT| / |PT|) and precision (should be ≈ 1; anything else is a
canonicalization bug or a different execution) of footprint lines, unique branches and edges,
relative error of the weighted averages (literal, `weff`, `ge1pct` × all/noret/indirect), and
recall at 25/50/75 % of the LBR samples, all over user-space file/special objects. `v2_python.py` is the deterministic Python workload
(~1 s; run it with `--env-file footprint_validate/v2_python.env`, which sets `PYTHONHASHSEED=0`). Both scripts refuse to start while another `perf` runs.

**Throughput** (P7, one house core): 0.42 M LBR samples/s (32 entries, ~640 MB/s of text) on
the python probe read with `--input`, 0.31–0.37 M samples/s through a pipe; 0.35–0.39 M samples/s on a synthetic 3.6 MB-footprint hot/cold
profile; ~70 k samples/s in a pathological 263 MB-footprint case (cache-miss bound). perf script
itself decodes ~0.11 M samples/s, so the analyzer is not the bottleneck. PT mode keeps up with
the decoder (~1 M branches/s).
