---
name: wiki
description: >-
  Maintain the InferSuite knowledge wiki (docs/wiki/) following the LLM-Wiki framework.
  Three operations: INGEST a new raw source (place it in docs/raw/ immutably, checksum it,
  and integrate its knowledge across affected wiki pages + index + log); QUERY the wiki to
  answer a question and optionally file the durable answer back as a page; LINT the wiki for
  integrity. The wiki holds cross-cutting knowledge (ontology, architecture, decisions,
  profiling, operations) — per-study methodology stays in docs/reports/ via /study-report.
  Use when the user asks to ingest a source into the wiki, ask a question of the wiki, add or
  update a wiki page, or invokes /wiki. Governed by docs/wiki/schema.md.
---

# wiki — maintain the InferSuite knowledge base

The wiki (`docs/wiki/`) is the persistent, compounding knowledge base. **Read
[`docs/wiki/schema.md`](../../../docs/wiki/schema.md) first** — it is the source of truth for
layers, page conventions, evidence language, and these operations. This skill is the operator
entry point; the schema is the law.

Scope reminder: the wiki holds **cross-cutting** knowledge. **Per-study** methodology belongs in
`docs/reports/` via [`study-report`](../study-report/SKILL.md), not here. Never move existing
`docs/reports/` files into the wiki.

## Operation: INGEST a source

1. Place the source **unaltered** in `docs/raw/` (never reformat/correct/summarize in place).
2. Register its checksum: `sha256sum docs/raw/<file> >> docs/raw/SHA256SUMS` (keep it sorted/clean).
3. Read the source; discuss the key takeaways with the user.
4. Identify affected pages (`concepts/`, `architecture/`, `decisions/`, `profiling/`,
   `operations/`, …). Update them — a single source may touch several pages. Use the evidence
   language (Fact / Decision / Hypothesis / Observation / Inference / Limitation) and relative links.
5. Add the source to the **Raw source registry** table in `schema.md`.
6. Register any new page in [`docs/wiki/index.md`](../../../docs/wiki/index.md).
7. Append a log entry: `## [YYYY-MM-DD] ingest | <title>` at the **top** of
   [`docs/wiki/log.md`](../../../docs/wiki/log.md).

## Operation: QUERY the wiki

1. Read [`docs/wiki/index.md`](../../../docs/wiki/index.md) first.
2. Read the **smallest** relevant page set; follow its source links to primary evidence.
3. In the answer, distinguish recorded **fact** vs **decision** vs **observation** vs **inference**;
   name **limitations**. Never upgrade an occupancy rate ("cores") to "useful work".
4. If the conclusion is durable and worth keeping, **file it back** — a new page (or an update to
   an existing one), registered in the index, with a `query` log entry. Don't let good analysis
   vanish into chat history.

## Operation: LINT

Run the shared checker (it lints the wiki *and* the reports):

```bash
python3 .claude/skills/report-check-commit/check_reports.py
```

Automated checks: raw-source checksums, index registration, page metadata, link resolution,
unfinished markers. Then do the **human review** the schema calls for: contradictions between
pages, stale model/kernel/tool identities, and claims whose evidence is present but insufficient
or misclassified. Fix what you find (or surface it), then re-run.

## Creating a new page

Start from the metadata table (Owner / Status / Last updated / Sources), write in evidence
language, cross-link sibling pages with relative links, register in the index, and log it. Match
an existing page (e.g. [`concepts/measurement-ontology.md`](../../../docs/wiki/concepts/measurement-ontology.md))
for format. Then LINT before finishing.

## Commit

Committing wiki changes goes through [`report-check-commit`](../report-check-commit/SKILL.md), which
runs this same lint as its gate. Use it (or `/report-check-commit`) so the wiki is verified before
it ships.
