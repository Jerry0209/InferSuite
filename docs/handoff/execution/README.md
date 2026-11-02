# Execution docs — SPEC and Server, x86 and ARM (2026-11)

**Owner:** Tianrui (Jerry) · **Written:** 2026-11-02 · **Status:** ready to execute

Four self-contained execution docs, one per ⟨suite, machine⟩, plus the shared method contract
for Rahul's front-end metrics. Each doc is written for a fresh Claude Code session on that
machine. It says what "done" means, what to check before touching anything, every step, where
results go, and how to document and push them.

| Doc | Machine | What | Results branch |
|---|---|---|---|
| [`x86_spec_footprint.md`](x86_spec_footprint.md) | P7 (x86) | SPEC CPU 2026: Rahul's footprint metrics (LBR) | `spec-x86` |
| [`x86_server_footprint.md`](x86_server_footprint.md) | P7 (x86) | Server set: Rahul's footprint metrics (LBR) | `dcperf` |
| [`arm_spec_profiling.md`](arm_spec_profiling.md) | AWS Graviton | SPEC CPU 2026 single-core profile with Jef's ARM metric families | `spec-arm` |
| [`arm_server_profiling.md`](arm_server_profiling.md) | AWS Graviton | Server set (realistic datasets) with Jef's ARM metric families | `dcperf-arm` |
| [`frontend_footprint_method.md`](frontend_footprint_method.md) | — | Contract for Rahul's three metrics. **Share with Jef**: agentic must use the same contract | — |

## Rules shared by all four

1. **One capture at a time per machine.** The two docs for a machine share the measured cores.
   Run them sequentially, never concurrently. On both machines a colleague (Jef) may also be
   capturing. Check with `pgrep -a -x perf` and `who`, and wait for quiet. **Never kill or
   renice another user's process.**
2. **Isolation is applied, then proven.** Apply the shield, pass the ISO-PROOF gate (measured
   cores silent, slices pinned), pass the whole-machine quiet gate, and run a witness during
   capture. Restore every knob from its snapshot afterwards, and check that it actually came
   back.
3. **The repo is public** (`github.com/Jerry0209/InferSuite`). Never commit:
   * SPEC sources, binaries, inputs or run dirs (SPEC CPU 2026 is licensed);
   * datasets;
   * keys;
   * **code or data from Jef's private `agentic-benchmark` repo**. Reimplement from his
     *method*: event lists and formulas are facts, his code is not ours to publish.
4. **Commits:** no Claude attribution lines (repo rule, `CLAUDE.md`). Nothing ≥ 100 MB. Raw
   bulk data stays outside git, summaries and long-format CSVs go in. `/report-check-commit`
   does the checks and the push.
5. **Document as you go** (`docs/handoff/PROTOCOL.md`):
   * a session log from the first action (`/handoff`);
   * a study report when the result exists (`/study-report`);
   * defects recorded with the wrong number they would have shipped.
6. **Subagents** are welcome for non-measurement work (building, downloading datasets,
   writing parsers, drafting reports). Only the main session drives captures, and only one at
   a time.
7. **ARM cost:** the Graviton metal box bills about $8.5/h. When the work is done, or blocked
   waiting for a human, say so plainly so Jerry can stop the instance from the AWS console. A
   Claude session cannot stop it.

## Order

* x86: `x86_spec_footprint.md` first. It builds and validates the analyzer that the Server
  run reuses. Then `x86_server_footprint.md`.
* ARM: `arm_spec_profiling.md` first. It brings up the box, the isolation and the profiler.
  Then `arm_server_profiling.md`.
