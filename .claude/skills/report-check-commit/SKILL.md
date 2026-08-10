---
name: report-check-commit
description: >-
  Check that the study reports in docs/reports/ AND the knowledge wiki in docs/wiki/ are
  up to date, then commit and push the repo — but ONLY if the checks are clean. Runs
  non-blocking report checks (index integrity, referenced scripts/figures exist, freshness,
  missing-report nudge) and wiki checks (raw-source checksums, index registration, page
  metadata, link resolution, unfinished markers); if any warning is raised it surfaces them
  and does NOT commit. If clean, it stages everything, guards against GitHub's 100 MB limit,
  excludes Claude session artifacts, commits with a concise message (no Claude attribution),
  and pushes. Use when the user asks to "commit and push" this repo, or invokes /report-check-commit.
---

# report-check-commit — verify reports + wiki, then ship

One command for the repeated "commit and push" workflow in this repo, with a docs
freshness gate in front of it. **Contract:** the check is non-blocking to *itself* (all
checks always run to completion and every warning is collected), but it **gates the
commit** — if there is even one warning, STOP and do not commit; only a clean check
proceeds to commit + push.

## Step 1 — run the check (always)

```bash
python3 .claude/skills/report-check-commit/check_reports.py
```

The script (self-documented at its top) runs, over `docs/reports/`:

1. **index-integrity** — every `docs/reports/NN_*.md` is registered in BOTH indexes
   (`docs/reports/README.md` and `docs/README.md`); no index link points at a missing file.
2. **referenced-files** — every script/figure (`.py`/`.sh`/`.png`) cited in backticks inside
   a report still exists in the repo (partial paths and placeholders are resolved/ignored).
3. **freshness** — warns if a cited script/figure — or `docs/handwritten_notes/analysis.md` —
   has a newer git-commit time than the report documenting it (report may be stale).
4. **report-nudge** — warns if the pending change set touches `analysis.md` / kit code
   (`local_agents/kit/*.py|*.sh`) / figures but no `docs/reports/*.md` was updated.

…and over the knowledge wiki `docs/wiki/` + raw sources `docs/raw/` (see the
[wiki skill](../wiki/SKILL.md) and [wiki schema](../../../docs/wiki/schema.md)):

5. **wiki-checksums** — every `docs/raw/` source is registered in `SHA256SUMS` and its hash
   matches (raw sources are immutable evidence).
6. **wiki-index** — every `docs/wiki/` page is linked from `docs/wiki/index.md`.
7. **wiki-metadata** — every wiki page (except `log.md`) has an Owner/Status/Last-updated table.
8. **wiki-links** — every relative link in a wiki page resolves to an existing file.
9. **wiki-markers** — no unfinished markers (TODO/TBD/FIXME) remain in wiki prose.

Exit code: **0 = clean, 1 = one or more warnings.**

## Step 2 — gate on the result

- **Exit 1 (warnings):** print the warning block verbatim to the user and **do not commit or
  push.** Explain what each warning means and offer the fix — e.g. register/refresh a report
  with `/study-report`, correct a renamed citation, or (if the user judges a warning a false
  positive) let them explicitly tell you to override and continue. Never commit on your own
  initiative while warnings stand.
- **Exit 0 (clean):** continue to Step 3.

## Step 3 — commit and push (only when clean)

Follow the house rules established for this repo:

1. **Inspect** what will be committed: `git status` and `git diff --stat`.
2. **Exclude Claude session artifacts.** Never stage `HANDOFF.md`, `further_check.md`, or any
   file that is a pasted chat transcript / session scratch (CLAUDE.md: "never commit session
   artifacts"). If such a file is untracked and would be swept by `git add -A`, add it to
   `.gitignore` instead of committing it, and tell the user.
3. **Size guard — GitHub rejects any file > 100 MB.** After staging, verify no staged blob
   exceeds the limit (warn at 50 MB):
   ```bash
   git ls-files -s -- $(git diff --cached --name-only) | awk '{print $2}' \
     | git cat-file --batch-check 2>/dev/null \
     | awk '$2=="blob" && $3>104857600{printf "OVER 100MB: %.0f MB %s\n",$3/1048576,$1}'
   ```
   If anything is over 100 MB, do NOT push — untrack it (`git rm --cached`) + gitignore the
   heavy tree (raw `rec_*.data` / multi-GB campaign data belong local, per `.gitignore`
   policy), then re-check. This is exactly how the `superseded_40min/data` tree was handled.
4. **Commit** with a concise, descriptive message grouped by theme. NO Claude attribution
   (no `Co-Authored-By`, no "Generated with") — this repo forbids it.
5. **Push:** `git push`, then report the new `origin/main` SHA.

## Notes

- `.claude/skills/` IS tracked (since 2026-08-10), so this skill ships with the repo and a
  "commit and push" run will include changes to it. Only `.claude/settings.local.json` — the
  per-developer permission allowlist — stays untracked.
- The checker is read-only except that it reads git state; it changes nothing.
- Complements `study-report` (which *writes* reports): this skill *verifies* them at ship time.
