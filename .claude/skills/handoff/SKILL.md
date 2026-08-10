---
name: handoff
description: >-
  Maintain the transferable documentation for this repo so the work survives the chat it was
  done in: the top-level entry point (docs/handoff/README.md), one study report per study
  (docs/reports/NN_*.md), and one session log per conversation
  (docs/handoff/sessions/YYYY-MM-DD_slug.md). Use when the user asks to "write the handoff",
  "document this", "update the session log", "write the report for this study", or invokes
  /handoff — and ALSO proactively at the start of any conversation that will capture data,
  change methodology, or produce a result, to open the session log. Never triggers merely
  because a figure was regenerated.
---

# handoff — make the work transferable

The contract is the **committed** file [`docs/handoff/PROTOCOL.md`](../../../docs/handoff/PROTOCOL.md).
Read it before writing anything. This skill only tells you *when* to act and *how* to check
your work; the formats, rules and rationale live in the protocol.

**Why the split:** the protocol is the copy a person finds by browsing `docs/`, without
knowing Claude Code's directory layout, and the copy a reviewer sees in a diff. This file is
the agent-facing trigger list. Both are tracked (`.claude/skills/` since 2026-08-10), so if
they ever disagree, `PROTOCOL.md` wins.

## Step 0 — decide which layer the request touches

| Trigger | Layer | File |
|---|---|---|
| Conversation begins substantive work | session log | `docs/handoff/sessions/YYYY-MM-DD_slug.md` |
| A decision / capture / defect / push happens | session log | same file, appended live |
| A study produced a citable result | study report | `docs/reports/NN_*.md` (next free `NN`) |
| A new tree, kit, campaign or moved path | entry point | `docs/handoff/README.md` |

One study = one question answered by one method. Several slides sharing a capture are ONE
report. One figure resting on two populations is TWO.

## Step 1 — session log (do this first, and keep doing it)

Create it on the first substantive action, not at the end. A log written from memory at the end
of a long session loses exactly the things that make it worth having: the numbers a defect
would have shipped, and why a decision went the way it did.

Append at every: decision (numbered, with the why), capture (with configuration), defect (with
the wrong number), artifact publish (with URL), and push (with SHA).

## Step 2 — study report

Follow the fixed three-part skeleton in the protocol §2 exactly: (1) key summary, (2)
methodology — decisions with a **why** column, verification and hazards, reproduction recipe,
scripts table, (3) key insights ranked most→least important.

Before writing:
- Re-read the relevant session logs and the figure manifest.
- **Recompute every number you plan to quote** from banked artifacts in this session. Never
  copy a number out of the chat scroll — that is how a stale ratio survives three revisions.
- Confirm every script you will cite exists at a stable repo path. If one lives in a scratchpad,
  promote it into the repo first.

## Step 3 — register and verify

1. Add the report to **both** indexes: `docs/reports/README.md` and `docs/README.md`.
2. If artifacts (deck, gallery) were published or updated, add/refresh their row in the
   registry table in `docs/reports/14_*.md` §2.5.
3. Cite external-tree scripts with a `~/` prefix (e.g. `~/spec26-infra/infra/scripts/foo.py`) —
   the repo's report checker skips `~`-prefixed tokens and would otherwise warn.
4. Run the checker, which gates the commit:
   ```bash
   python3 .claude/skills/report-check-commit/check_reports.py
   ```
   Exit 0 = clean. **Any warning means do not commit** — surface it and let the user decide.

## Step 4 — close out

Tell the user: which files were written, what was registered, what you had to promote into the
repo, and anything you could **not** verify from banked data. Never silently guess a number.
Leave committing to the user unless they asked for it.

## The failure this skill exists to prevent

A result that only one person can reproduce, because the reason behind a decision, the
population a median rested on, or the defect that was fixed on the way lives in a chat log
nobody else can read. If you are unsure whether something belongs in the documentation, ask:
*would a colleague holding an older version of this figure be able to tell whether it is
affected?* If not, write it down.
