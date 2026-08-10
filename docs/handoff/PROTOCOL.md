# Handoff protocol

**Owner:** Tianrui (Jerry) · **Status:** active · **Last updated:** 2026-08-07

Why this file exists: most of what we know about this study lives in chat sessions, which are
not transferable. A colleague joining the group — or a future Claude Code session with no
memory of ours — must be able to *rebuild and reuse the work* from the repository alone. This
protocol says exactly what gets written down, where it goes, and when.

It is written to be read by **both a person and an agent**. Agents: this file is the contract;
`.claude/skills/handoff/SKILL.md` is a thin wrapper that points here. If the two ever disagree,
**this file wins** — it is the copy a person finds without knowing Claude Code's directory
layout, and the one a reviewer reads in a diff. (Both ship: `.claude/skills/` has been tracked
since 2026-08-10. Only `.claude/settings.local.json` stays untracked, being per-developer.)

---

## 1. The three layers

| Layer | Path | One file per | Answers |
|---|---|---|---|
| **Entry point** | `docs/handoff/README.md` | the repo | "What is this, what can I run, where is everything?" |
| **Study report** | `docs/reports/NN_*.md` | one *study* | "How was this result obtained, and can I reproduce it?" |
| **Session log** | `docs/handoff/sessions/YYYY-MM-DD_slug.md` | one *chat* | "What happened, what was decided, what is still open?" |

A **study** is one question answered by one measurement method. Not one figure, not one slide:
if four slides share a capture and a methodology, they are one study. If two slides share a
figure but rest on different populations or instruments, they are two.

## 2. Study report format (fixed — do not improvise)

```markdown
# Report NN — <Title> (<what it feeds: deck slide(s), figure(s)>)

**Date of study:** YYYY-MM-DD · **Author of record:** <user>, with Claude Code
**Feeds:** <slides / figures / downstream reports>
**Data:** <exact paths, and whether they are in-repo or in a sibling tree>

## 1. Key summary
The question, the method in one sentence, the headline numbers, and why it matters.
Someone who reads only this section should be able to state the result correctly.

## 2. Methodology
### 2.1 Decisions
A table: decision | value | **why**. The "why" column is the report. `WINSEC=0.1` alone is
worthless; "0.1 because a full 11-group rotation then fits in 1.32 s, so every benchmark
completes many rotations on its first command line" is the transferable part.
### 2.2 Verification and hazards
How the claims were checked, and every defect found *with the number it would have shipped*.
A methodology section that lists no failures is not finished being written.
### 2.3 Reproduction recipe
Exact commands with env vars, expected wall-clock cost, and what should reproduce (phenomena
and shares) versus what should not (exact trajectories).
### 2.4 Scripts and artifacts
A table: item | repo location | role. **Every script named here must exist at a stable path.**
If it only exists in a chat scratchpad, promote it into the repo before writing the report.

## 3. Key insights (most → least important)
Numbered. One claim per item, each carrying the number that supports it. Ranked by how much
the claim would change someone's decisions, not by the order you discovered them.
```

**Writing rules.** Target 100–200 lines. Compress by cutting narration, never by cutting
decisions, numbers, caveats or commands. Label proxies as proxies. State population sizes
inline (`n=16 over 2 tasks`) — never let a median hide how few episodes it rests on. Quote
numbers from banked artifacts (`values_dump.json`, validator output, CSVs), never from memory.

## 3. Session log format

One file per chat, created at the start and **updated as the chat goes**, not written at the
end from memory. It is the thing that makes a conversation resumable by someone else.

```markdown
# Session YYYY-MM-DD — <slug>

**Goal:** one line.
**Machine state at start:** partition, who else is on the box, what was already captured.

## Decisions
| # | Decision | Why | Made by |
Numbered so later text can cite them.

## What changed
Files, captures, artifacts — with commit SHAs once pushed.

## Defects found
Each with the wrong number it would have shipped.

## Open threads
What the next session must pick up, with enough context to act without re-reading the chat.
```

## 4. When to write

- **Session log:** create on the first substantive action; update at every decision, capture,
  defect, and push. Never batch it to the end.
- **Study report:** when a study produces a result someone would cite. Not when a figure is
  merely regenerated.
- **Entry point:** whenever a new tree, kit or campaign appears, or a path moves.

## 5. Rules that keep this honest

1. **Never claim a gate passed that could not be evaluated.** Report it as NO PROOF.
2. **Never quote a number you did not recompute from banked data in this session.**
3. **A defect found is part of the methodology.** Record the wrong number it would have
   shipped, so a reader can tell whether an older figure they hold is affected.
4. **Populations are named, never implied.** "n=16 over 2 tasks (babel, fmtlib)" — not "the
   replays".
5. **Shared machine.** Any capture instruction must say how to check the box is free and must
   never suggest killing another user's processes.
