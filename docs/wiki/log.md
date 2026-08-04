# Wiki log

## [2026-07-29] ingest | Instantiate the LLM Wiki for InferSuite

Adopted the [LLM Wiki framework](../raw/llm-wiki.md) as the governing knowledge-base pattern,
mimicking the `docs/` organization of `JekxDevil/agentic-benchmark` (branch `feat/runtime`). Created
the three layers: `docs/raw/` (governing framework + [SHA256SUMS](../raw/SHA256SUMS), checksum
verified byte-for-byte against the template repo), `docs/wiki/` (this tree), and reused the existing
`docs/reports/` as the generated study-output layer. Wrote the [schema](schema.md), this log, and
the [index](index.md). Nothing existing was moved; `docs/reports/` and the two skills are unchanged.

## [2026-07-29] decision | Wiki is additive, CLAUDE.md stays canonical

Chose the additive instantiation: `docs/reports/` study reports keep their location and their
`study-report` + `report-check-commit` machinery; the wiki holds only cross-cutting knowledge
(ontology, architecture, decisions, profiling, operations). `CLAUDE.md` remains the canonical schema
— no competing `AGENTS.md` was added — and it now carries a short pointer to the wiki. Adopted the
template's status vocabulary (Proposed/Approved/Implemented/Validated/Superseded) and evidence
language (Fact/Decision/Hypothesis/Observation/Inference/Limitation).

## [2026-07-29] ingest | Seed core pages from existing repo knowledge

Compiled six knowledge pages from `CLAUDE.md`, `docs/handwritten_notes/analysis.md`, and
`local_agents/scripts/glm/events.md` — no new research, just consolidation of scattered knowledge:
[measurement ontology](concepts/measurement-ontology.md),
[agent measurement design](architecture/measurement-design.md),
[service data path](architecture/service-data-path.md),
[zero-mux rotation](decisions/zero-mux-windowed-rotation.md),
[lineage fencing](decisions/lineage-fork-exec-fencing.md),
[median run never pooled](decisions/median-run-not-pooled.md),
[perf & TMA conventions](profiling/perf-tma-conventions.md), and
[isolation & hardening](operations/isolation-hardening.md). Registered all in the index.

## [2026-08-04] update | Repo narrowed to SWE-agent profiling

At the user's request the service stack (`src/`, `deploy/`, `local_service/` incl. `data_iso`,
`benchmark_queries/`, `fastapi_runtime_assets/`, root deploy scripts), the GPU-side kit
(`agentic/inference/`), the banked OpenClaw campaign (`local_agents/OC_clean`), and the dead
EKS scripts were removed from the working tree — all fully committed beforehand, so every path
is recoverable from git history. Marked
[service data path](architecture/service-data-path.md) Historical and updated its source
links; `measure.sh`, `scripts/sync_plots.sh`, `CLAUDE.md`, and `docs/PLOTTING_GUIDE.md` were
updated in the same commit. The OpenClaw *harness* stays in tree (`agentic/openclaw/` — its
litellm venv is a hard dependency of the SWE campaign kit).

## [2026-08-04] update | litellm venv moved into the SWE kit; OpenClaw harness removed

Follow-up to the narrowing: the litellm proxy venv the SWE campaign launches (python 3.13.13,
litellm 1.89.4) moved from `agentic/openclaw/.venv_litellm` to
`local_agents/scripts/glm/.venv_litellm` (same bits — moved, shebangs/activate paths
rewritten; exact pins committed as `litellm_venv_freeze.txt`; `agents-swe preflight` passes).
With the dependency gone, `agentic/openclaw/` was removed (its `external/WildClawBench`
checkout was already absent, so no OC capture was runnable anyway); `measure.sh agents-oc` is
now a stub that explains the restore path. Method-update notes appended to reports
01–04/07–09/12.
