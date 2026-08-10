---
name: study-report
description: >-
  Write (or update) a reproducibility-grade study report in docs/reports/ for one
  measurement/microarchitectural study of this repo, in the lab's fixed three-part format:
  (1) key summary, (2) methodology with every load-bearing decision, a reproduction recipe,
  and a scripts table, (3) insights ranked most→least important. Also registers the report
  in both indexes. IMPORTANT: this skill is strictly user-invoked — run it ONLY when the
  user explicitly asks for a study report (e.g. "/study-report", "write the report for
  slide N", "document this study"). Never trigger it proactively when slides, figures, or
  studies are added or discussed.
---

# study-report — methodology reports for measurement studies

Produce one markdown report per study under `docs/reports/`, so the methodology that
otherwise lives only in a chat session survives for peers and posterity. The consumer is a
future researcher (or future Claude) who has the repo and the banked data but **not** this
conversation: every decision they'd need to re-make must be stated *with its reason*, and
every number must be traceable to banked data.

**Invocation contract:** only on explicit user request. Adding a slide, finishing a
capture, or discussing a study is *not* a trigger — the user decides when a study is
report-worthy.

## Step 0 — scope the report

Ask (or extract from the request): which study / deck slide(s)? One report = one study =
one methodology. If a study spans several slides sharing one capture method, write ONE
report covering the slide range (exemplar: report 04 covers slides 19–20, 22–23). Check
`docs/reports/` for the next number `NN` and for an existing report to *update* instead
of duplicating.

File name: `NN_slideXX[_slideYY-ZZ]_short_kebab_topic.md` (match existing names).

## Step 1 — gather before writing

- Re-read the study's sections in `docs/handwritten_notes/analysis.md` and the relevant deck slides.
- Identify every script the study used; **each must exist in the repo** at a stable path.
  If one lives only in a session scratchpad, promote it into the repo first (exemplar:
  `build_metric_gallery.py`) — a report that references unreachable scripts fails its
  purpose.
- Pull all quoted numbers from banked artifacts (CSVs, `values_dump.json`, logs), never
  from memory.
- Collect the operational lessons/hazards hit during the study (failed approaches,
  environment traps) — these are methodology, not noise: they're exactly what a
  reproducer will trip over.

## Step 2 — write in the fixed template

Use this exact skeleton (see `docs/reports/04_*.md` as the gold exemplar):

```markdown
# Report NN — <Title> (deck slide[s] X[–Y])

**Date of study:** YYYY-MM-DD · **Author of record:** <user>, with Claude Code
**Deck slides:** X[–Y] (+ what they feed)
**Longer prose version:** analysis.md, Part N        ← and other cross-refs

---

## 1. Key summary
One or two paragraphs: the question, the method in one sentence, the headline result
with its key numbers, and why it matters.

## 2. Methodology
### 2.1 <Design / decisions>       ← a table of load-bearing decisions with a "Why" column
### 2.2 <Verification / hazards>   ← how claims were checked; failures + fixes
### 2.3 Reproduction recipe        ← exact commands, env vars, data paths, expected costs
### 2.4 Scripts and artifacts      ← table: item | repo location | role

## 3. Key insights (most → least important)
1. ... numbered, one claim per item, each carrying its supporting number(s).
```

Writing principles (these carry the report's value):

- **Concise and crisp, losing nothing.** Target 100–180 lines. Compress by cutting
  narration, never by cutting decisions, numbers, caveats, or commands.
- **Decision + why.** "`TIER_PREFIX=glm-t06`" is useless alone; "…so new runs cannot
  overwrite the temp-0 evidence" is the report. Prefer tables of decision/value/why.
- **Honest labels.** Proxy metrics stay labeled as proxies (e.g. code-read MPKI as
  L1I-pressure proxy); heuristic layers (thresholds, joins, taggers) are distinguished
  from exact layers (kernel/cgroup accounting), with their guards/diagnostics named.
- **Reproducer's eye view.** Exact invocations with env vars, event names, file schemas,
  and data layouts; note nondeterminism (what should reproduce: phenomena and shares, not
  exact trajectories); note costs (wall time, API spend or "free").
- **Known limitations belong in §2**, stated plainly (e.g. window ≠ call, with the
  quantified reconciliation).

## Step 3 — register the report

1. Add a row to the table in `docs/reports/README.md` (report link + one-line study
   summary); adjust the reading-order note if the new report changes it.
2. Add the matching row to the reports table in `docs/README.md` (the docs entry point).
3. **Slide-link registry.** The table "Published Claude artifacts" in
   `docs/reports/14_slides1-25_instrument_to_figure_reference.md` §2.5 is the canonical
   list of live slide links. Whenever the study added deck slides or published/updated a
   Claude artifact (deck, per-window gallery, status page):
   - new artifact → add a row (name | link | what it covers);
   - new deck slides → update the deck row's "Covers" column (and report 14's header/§2.1
     slide count if it changed);
   - then verify completeness: list the published artifacts (Artifact tool,
     `action: "list"`) and diff against the table — every project artifact must have a
     row; register any missing link before closing out. Artifacts from other projects
     stay out.

## Step 4 — close out

Tell the user: file path, what was registered, and anything you had to promote into the
repo or could not verify from banked data (never silently guess). Leave everything
uncommitted — committing is the user's call.
