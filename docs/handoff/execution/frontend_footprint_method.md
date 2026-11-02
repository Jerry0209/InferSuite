# Front-end footprint metrics — method contract (Rahul, 2026-11)

**Owner:** Tianrui (Jerry) · **Written:** 2026-11-02 · **Status:** contract v1, not yet executed
**Used by:** [`x86_spec_footprint.md`](x86_spec_footprint.md) (SPEC CPU 2026),
[`x86_server_footprint.md`](x86_server_footprint.md) (Server set), and Jef's agentic capture.
**Share this file with Jef before anyone captures.** The three families are only comparable if
all three use this exact contract (same event, same period, same analyzer commit).
Not to be confused with `local_agents/kit/dcperf/measure_footprint.sh` (2026-09), which measures
the *data* (memory) footprint. Everything here is named `frontend_footprint` to keep the two
apart.

## 1. The request (Rahul, verbatim intent)

Extract three more numbers on the **x86** machine for SPEC26, Server and Agentic workloads, to
explain *why* the front end suffers in agentic work (the existing data shows *that* it does):

1. **Instruction footprint** — the number of unique 64 B instruction-cache blocks touched over
   the whole execution, × 64 B.
2. **Unique taken branches** — how many distinct branch instructions are ever taken.
3. **Weighted average targets per taken branch** — for n unique taken branches with taken
   counts C1…Cn and distinct-target counts T1…Tn: `(C1·T1 + … + Cn·Tn) / (C1 + … + Cn)`.

Plots: one violin figure per metric, Agentic vs SPEC (and Server), same style as the existing
per-metric violins (`local_agents/kit/plot/plot_paper_agg_compact_server.R`).
Split of work: Jerry = SPEC26 + Server; Jef = agentic.

## 2. Instrument decision: LBR sampling, not an exact trace

| Option | Why not / why |
|---|---|
| Intel PT, whole run | Exact, but one SPEC ref run (1–2 T instructions) is ~50–150 GB of trace and hours of decode per benchmark; P7 has <10 GB free today. JIT code (every JVM server, node in agentic) needs jitdump + `perf inject --jit`. Not viable for 46+ workloads. |
| DynamoRIO / Pin | Exact, but 3–50× slowdown distorts server timing (clients time out, GC/JIT change); JVM support is fragile; cannot follow agentic tool processes inside docker containers. |
| **LBR sampling (chosen)** | `perf record -j` on Sapphire Rapids Arch-LBR (32 entries). Works identically for SPEC, JVM servers and containerised agentic processes, because it needs addresses only (no code bytes), so JIT code and short-lived processes are fine. Overhead a few %. Probed on P7 2026-11-02: works with `-j any,save_type`. |

**Consequence that must be stated with every number:** unique counts (metrics 1 and 2) are
**sampled lower bounds**. Code executed only a handful of times is rarely captured. Metric 3 is
execution-weighted, so it is dominated by hot branches and robust to sampling. Using the
**same period for every family** gives every taken-branch execution the same detection
probability (32 / 20011 ≈ 0.16 %), so the bias is comparable across families. Undercounting
falls hardest on flat, tail-heavy profiles (agentic), which makes an "agentic footprint is
larger" finding conservative.

## 3. Contract parameters (identical for SPEC, Server, Agentic)

| Parameter | Value |
|---|---|
| Machine | P7, Xeon w5-3425 (Sapphire Rapids), measured cores 4–11 SMT-free, 3.2 GHz, turbo off |
| Sampling event | `br_inst_retired.near_taken` (no `:u`/`:k` modifier: user + kernel) |
| Period | `-c 20011` (prime; avoids aliasing with loop trip counts). Change it only with Jef, for all three families at once |
| Branch filter | `-j any,save_type` (all taken branches, with type) |
| Scope | the workload's fence cgroup: `perf record -a -C <measured cpus> --cgroup=<fence>` |
| Concurrent exact counts | `perf stat --cgroup=<fence> -a -C <measured cpus> -e instructions,br_inst_retired.near_taken` over the same interval (scaling and sanity) |
| Window | SPEC: benchmark start to exit (whole run). Server: the same steady-state window the existing captures used (duration recorded). Agentic: Jef's definition, recorded in his metadata |
| Compression | `perf record -z` (zstd), big buffers `-m 512M`; abort if any `LOST` records exceed 1 % of samples |
| Isolation | the existing shield + ISO-PROOF + whole-machine quiet gate; no other `perf` on the box |

## 4. Analyzer rules (implement once, commit, record its SHA in every output)

Input: `perf script -F pid,brstack --show-mmap-events` text. Each sample has up to 32 entries
`from/to/flags/…/cycles/TYPE/…`, newest first.

1. **Taken branch** = a near taken branch: types `COND`, `UNCOND` (direct jump), `CALL`
   (direct), `IND_CALL`, `IND` (indirect jump), `RET`. Far transfers (`SYSCALL`, `SYSRET`, `IRQ`,
   `ERET`, interrupts, …) are excluded from metrics 2 and 3 and reported separately.
2. **Canonical address** (so shared libraries mapped in several processes are not double
   counted, and ASLR does not matter):
   * file-backed executable mapping: key = (file path, inode) + `addr − map_start + pgoff`;
   * kernel (address ≥ `0xffff800000000000`): key = (kernel, addr);
   * anonymous / JIT mapping: key = (pid, addr). Never merge JIT code across processes.

   Mappings are page-aligned, so 64 B line boundaries are the same in VA and canonical space.
3. **Footprint lines:** for consecutive entries `e[k]` (older) and `e[k-1]` (newer), the
   straight-line range `[e[k].to, e[k-1].from]` executed. Add every 64 B line from
   `line(e[k].to)` to `line(e[k-1].from)`, but only if `0 ≤ from − to ≤ 4096` and both ends
   fall in the same mapping (otherwise skip it, and count it as a discontinuity). Also add
   `line(from)` and `line(to)` of every entry. Known approximation: a branch instruction that
   straddles a line boundary can miss its second line (≤1 line per range).
4. **Per branch** b (canonical `from`): `C_b` = number of entries with that `from`, and
   `T_b` = number of distinct canonical `to` values.
5. **Outputs** (per workload, JSON plus long-format CSV rows `workload,family,metric,value`):
   * `footprint_bytes` = 64 × |lines|, plus `_user` and `_kernel` splits;
   * `unique_taken_branches`, plus a split by type;
   * `wavg_targets_all` (Rahul's literal metric), `wavg_targets_noret` (returns excluded:
     returns are predicted by the return stack, not the BTB) and `wavg_targets_indirect`
     (indirect jumps and calls only);
   * diagnostics: samples, entries, lost records, discontinuity rate, exact instruction and
     taken-branch totals from `perf stat`, and **convergence**: each unique count recomputed
     at 25 / 50 / 75 / 100 % of samples in time order (a curve still rising at 100 % means
     the number is sampling-limited — say so);
   * `analyzer_sha`, perf version, period, window start/end.
6. Keep a compressed per-workload table of (canonical from, canonical to, type, count) so
   the numbers can be recomputed without re-running. Delete `perf.data` once the table and
   summary are verified. Disk is the binding constraint on P7.

## 5. Validation gates (all must pass before production numbers are quoted)

* **V1 Synthetic truth.** A small C program with (a) a straight-line region of known size
  executed in a loop, (b) one indirect call site rotating among K = 1, 4, 16 targets with
  known frequencies, and (c) a known count of distinct taken conditional branches. The
  analyzer must recover the footprint within 2 lines, the unique branch count exactly, and
  the weighted average within 1 %.
* **V2 Exact cross-check vs Intel PT.** On 2–3 short real programs (≈1–3 s each, e.g. a
  SPEC `test`-size run or compiling one C file), decode a full PT trace
  (`perf record -e intel_pt/cyc=0,mtc=0,tsc=0/`, then `perf script --itrace=b`) for the exact
  sets, and compare with the LBR estimate of the same command. Report LBR recall of
  footprint and unique branches, and the relative error of the weighted average. This
  number travels with the results; it is what makes "lower bound" quantitative.
* **V3 Period sensitivity.** Re-run 3 SPEC benchmarks (one short, one branchy int, one FP)
  at `-c 5003`. Report the ratio of unique counts (4× denser sampling).
* **V4 Capture hygiene.** Lost records < 1 %, ISO-PROOF passed, quiet gate passed, no
  foreign `perf`, benchmark output check passed (SPEC) or liveness/steady-state gate passed
  (Server).

If any gate fails, record it (with the number it would have shipped) and do not publish that
metric.

## 6. Where results go

* SPEC: data under `~/spec26-infra/infra/data_frontend_footprint/` (outside git); summaries and long
  CSV committed on branch `spec-x86` under `spec26/frontend_footprint_x86/`.
* Server: data under `local_agents/{DCPerf,JVMbench,RealData}/data/frontend_footprint/`
  (git-ignored data areas); summaries and long CSV committed on branch `dcperf` under
  `local_agents/frontend_footprint_x86/` (a new tracked directory: the `data/` trees are
  ignored).
* Agentic (Jef): his repo, same CSV schema, so one plotting script reads all three.
