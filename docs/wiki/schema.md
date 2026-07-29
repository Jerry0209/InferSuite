# Wiki schema

| Field | Value |
|---|---|
| Owner | LLM maintained, human reviewed |
| Status | Active |
| Last updated | 2026-07-29 |
| Governing source | [LLM Wiki framework](../raw/llm-wiki.md) |
| Instantiation reference | `JekxDevil/agentic-benchmark` `docs/wiki/` (branch `feat/runtime`) |

## Purpose

This schema turns the abstract [LLM Wiki framework](../raw/llm-wiki.md) into the operating rules
for **InferSuite**. The wiki is the persistent, compounding knowledge base for the measurement
suite: what the system measures, why each measurement decision was made, how campaigns are run,
and how raw counters connect to plotted conclusions. Knowledge is compiled once into interlinked
pages and then kept current — not re-derived from `CLAUDE.md` and scattered notes on every question.

The wiki does **not** replace the existing machinery. Per-study methodology lives in
`docs/reports/` (written by the [`study-report`](../../.claude/skills/study-report/SKILL.md) skill).
The wiki holds the cross-cutting, non-per-study knowledge — ontology, architecture, decisions,
profiling conventions, operations — that today is trapped in the long `CLAUDE.md` and in
`docs/handwritten_notes/`.

## Three layers

| Layer | Location | Ownership | Mutation rule |
|---|---|---|---|
| Raw sources | `docs/raw/` | Human curated | Immutable after ingestion |
| Wiki | `docs/wiki/` | LLM maintained | Updated whenever knowledge changes |
| Outputs | `docs/reports/`, top-level `plots/` & `results/` | Generated | Rebuildable from data + wiki |

Raw sources are ground truth. A source may be moved into `docs/raw/`, but its contents must never
be reformatted, corrected, or summarized in place — corrections and interpretations belong in the
wiki. Each raw source is registered in [SHA256SUMS](../raw/SHA256SUMS).

The same immutability principle governs **banked measurement evidence** under
`local_agents/*/data`, `local_service/data_iso`, and the archived campaigns. These are the
project's real "raw data" — invalid runs and rejected episodes are preserved, not deleted (see the
API-credit-starvation and greedy-decode lessons). Normal cleanup targets only derived, rebuildable
artifacts (figures, `values_dump.json`, lanes/leaf tables). The heavy `rec_*.data` perf captures
and the multi-GB campaign trees are gitignored and kept local by policy.

## Required navigation files

1. [index.md](index.md) is the content catalog. Every wiki page appears there with a one-sentence
   description, grouped by category.
2. [log.md](log.md) is the chronological record. New entries are appended (newest first) using the
   format `## [YYYY-MM-DD] operation | title`, so the log is greppable:
   `grep "^## \[" docs/wiki/log.md | head`.

## Page conventions

Every substantive page begins with a metadata table containing **Owner, Status, Last updated,** and
**Sources**. Status values:

| Status | Meaning |
|---|---|
| Proposed | Design or explanation awaits approval or evidence |
| Approved | Human-approved decision |
| Implemented | The repository implements this (kit code exists) |
| Validated | Confirmed by campaign validators (gates E1–E11) and/or figure audit (ALL MATCH) |
| Superseded | A newer page or decision replaces it |

Pages use **relative Markdown links** so they work in GitHub and Obsidian. Claims derived from
repo files link to those files by path; claims about Linux, Intel PMU/TMA, perf, cgroups, Docker,
SWE-agent, OpenClaw, or the GLM model link to primary documentation. Cross-reference sibling wiki
pages liberally — a decision links to the concept it turns on; an architecture page links to the
decisions that shaped it.

## Knowledge operations

### Ingest

1. Place the source in `docs/raw/` without altering it.
2. Record its checksum in [SHA256SUMS](../raw/SHA256SUMS) (`sha256sum <file> >> SHA256SUMS`).
3. Read the source and identify affected wiki pages.
4. Update the relevant concept, architecture, decision, profiling, and operations pages.
5. Update [index.md](index.md).
6. Append an ingest entry to [log.md](log.md).

### Query

1. Read [index.md](index.md).
2. Read the smallest relevant page set; follow its source links.
3. Distinguish recorded **fact**, **decision**, **observation**, and **inference** (see below).
4. File durable new conclusions back into the wiki when the answer is worth keeping — as a new page
   or an update to an existing one — and log it. Ad-hoc comparisons and analyses should not
   disappear into chat history.

### Lint

The automated lint (extended into
[`report-check-commit`](../../.claude/skills/report-check-commit/SKILL.md)'s `check_reports.py`)
checks:

1. Raw checksum registry — every `docs/raw/` file is registered and its hash matches.
2. Every wiki page is registered with a relative link from [index.md](index.md).
3. Relative links resolve to existing files.
4. Required **Owner / Status / Last updated** metadata is present on each page.
5. No unfinished markers (`TODO`, `TBD`, `FIXME`) remain.

Human / configuration-aware review (not automatable) checks: contradictions between pages, stale
model/kernel/tool identities, and claims whose evidence is present but insufficient or misclassified.

Generated outputs under `docs/reports/` are rebuildable study artifacts governed by their own
validators and are **not** part of wiki navigation lint.

## Evidence language

The wiki uses these terms precisely:

| Term | Meaning |
|---|---|
| Fact | Directly supported by a source, kit code, or machine output |
| Decision | An approved choice for this project (often with a rejected alternative) |
| Hypothesis | A testable explanation not yet established |
| Observation | A value measured in a campaign run |
| Inference | An interpretation derived from observations |
| Limitation | A known boundary on attribution or reproducibility |

An observed correlation is not called a cause without a controlled contrast. "CPU usage (cores)" is
an **occupancy rate** (core-seconds per second, spin included), a lower bound on peak concurrency —
never silently upgraded to "useful work" (high IPC/retiring does not certify useful work; see the
engine busy-wait fact in [measurement ontology](concepts/measurement-ontology.md)).

## Raw source registry

| Source | Role |
|---|---|
| [llm-wiki.md](../raw/llm-wiki.md) | Governing knowledge-base framework |
| [SHA256SUMS](../raw/SHA256SUMS) | Immutable raw-source checksum registry |
