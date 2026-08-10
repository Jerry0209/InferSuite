#!/usr/bin/env python3
"""check_reports.py — pre-commit report AND wiki checks for InferSuite docs/.

Runs non-blocking checks and prints every warning it finds. The checks always run to
completion (one bad file never aborts the rest); the exit code only reports the verdict
so the calling skill can decide whether to commit.

Report checks (docs/reports/):
  1. index-integrity  — every docs/reports/NN_*.md is registered in BOTH indexes
                        (docs/reports/README.md and docs/README.md); and every index
                        link points at a report file that exists (no dangling links).
  2. referenced-files — file paths cited in `backticks` inside each report still
                        exist in the repo (catches reports that rot when scripts /
                        figures are renamed or moved).
  3. freshness        — warn if a cited script/figure — or analysis.md — has a NEWER
                        git-commit time than the report documenting it (report may be
                        stale; consider refreshing it via /study-report).
  4. report-nudge     — if the pending commit touches analysis.md / kit code / figures
                        but NO docs/reports/*.md, warn that a report update may be missing.

Wiki checks (docs/wiki/ + docs/raw/), mirroring the LLM-Wiki framework's lint:
  5. wiki-checksums   — every docs/raw/ source is registered in SHA256SUMS and its hash
                        matches (raw sources are immutable).
  6. wiki-index       — every docs/wiki/ page is linked from docs/wiki/index.md.
  7. wiki-metadata    — every wiki page (except log.md) has Owner/Status/Last updated.
  8. wiki-links       — every relative link in a wiki page resolves to an existing file.
  9. wiki-markers     — no unfinished markers (TODO/TBD/FIXME) remain in wiki prose.

Exit: 0 = clean, 1 = one or more warnings. Usage: python3 check_reports.py
"""
import hashlib, os, re, subprocess, sys

# ---- repo location -------------------------------------------------------------
def sh(*args):
    return subprocess.run(args, capture_output=True, text=True).stdout

ROOT = sh("git", "rev-parse", "--show-toplevel").strip()
if not ROOT:
    print("check_reports: not inside a git repo", file=sys.stderr)
    sys.exit(2)
os.chdir(ROOT)

REPORTS_DIR = os.path.join("docs", "reports")
REPORTS_INDEX = os.path.join(REPORTS_DIR, "README.md")
TOP_INDEX = os.path.join("docs", "README.md")
ANALYSIS = os.path.join("docs", "handwritten_notes", "analysis.md")

# Backticked tokens with these extensions are treated as "names a script or figure".
# Restricted to scripts + figures on purpose (the user's definition of "referenced
# files"): data files (csv/tsv/txt/json) are per-run artifacts that legitimately may
# not be banked, and it excludes counter-event names like fp_arith_inst_retired.scalar.
SRC_EXT = {"py", "sh", "png"}   # referenced-files AND freshness both use this set

# Top-level repo dirs — used to tell a *partial repo path* (warn if missing) apart
# from an *illustrative external path* like django/core/validators.py (skip).
REPO_TOPDIRS = {"local_agents", "local_service", "docs", "src", "agentic",
                "deploy", "scripts", "archive", "h100"}

# ---- wiki layer (docs/wiki/, docs/raw/) ----------------------------------------
WIKI_DIR = os.path.join("docs", "wiki")
WIKI_INDEX = os.path.join(WIKI_DIR, "index.md")
RAW_DIR = os.path.join("docs", "raw")
RAW_SUMS = os.path.join(RAW_DIR, "SHA256SUMS")
MD_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
MARKER = re.compile(r"\b(TODO|TBD|FIXME)\b")
META_FIELDS = ("Owner", "Status", "Last updated")

warnings = []  # (category, message)
def warn(cat, msg):
    warnings.append((cat, msg))

# ---- helpers -------------------------------------------------------------------
def report_files():
    if not os.path.isdir(REPORTS_DIR):
        return []
    return sorted(f for f in os.listdir(REPORTS_DIR) if re.match(r"\d{2}_.*\.md$", f))

def read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""

def git_ct(path):
    """Last commit unix time for a tracked path, else None (untracked / no history)."""
    out = sh("git", "log", "-1", "--format=%ct", "--", path).strip()
    return int(out) if out else None

def _pending_set():
    """paths with uncommitted (staged or unstaged) modifications."""
    out = set()
    for line in sh("git", "status", "--porcelain").splitlines():
        if len(line) > 3:
            out.add(line[3:].strip().strip('"'))
    return out

_PENDING = None
def eff_ct(path):
    """Effective 'documents/changed at' time: a path with UNCOMMITTED edits counts as its
    worktree mtime, else its last commit time. Without this, check 3 has a blind spot on
    both sides: a report refreshed in the pending change-set still reads stale (its content
    fix cannot move git_ct until the very commit this check gates), and a source with
    pending edits reads older than reports that predate those edits."""
    global _PENDING
    if _PENDING is None:
        _PENDING = _pending_set()
    rel = os.path.relpath(path, ROOT) if os.path.isabs(path) else os.path.normpath(path)
    if rel.replace(os.sep, "/") in _PENDING and os.path.exists(path):
        return int(os.path.getmtime(path))
    return git_ct(path)

def repo_files():
    """every tracked + untracked-but-not-ignored path (repo-relative, forward slashes)."""
    files = set()
    for flag in (["git", "ls-files"], ["git", "ls-files", "--others", "--exclude-standard"]):
        for line in sh(*flag).splitlines():
            if line:
                files.add(line)
    return files

def pending_paths():
    """Every path with a pending change: staged, unstaged, or untracked."""
    paths = []
    for line in sh("git", "status", "--porcelain").splitlines():
        if not line:
            continue
        p = line[3:].strip()
        if " -> " in p:            # rename: take the destination
            p = p.split(" -> ", 1)[1]
        paths.append(p.strip('"'))
    return paths

BACKTICK = re.compile(r"`([^`]+)`")
def is_placeholder(tok):
    """glob/placeholder notation, not a literal filename: wNNN, scopeN, run_1/2/3, foo*."""
    if "NNN" in tok or "*" in tok or "<" in tok or ">" in tok or "{" in tok:
        return True
    if re.search(r"\d/\d", tok):            # 1/2/3 alternatives, e.g. cpustat_scope1/2/3.tsv
        return True
    if re.search(r"(?:^|[/_])N(?=[/_.]|$)", tok):   # a bare 'N' path/name segment
        return True
    return False

def cited_tokens(text):
    """backticked tokens that name a script or figure (single token, SRC_EXT extension)."""
    out = []
    for tok in BACKTICK.findall(text):
        tok = tok.strip()
        if not tok or " " in tok or tok.startswith(("http://", "https://")):
            continue
        if "$" in tok or tok.startswith("~") or is_placeholder(tok):
            continue
        if "." not in os.path.basename(tok):
            continue
        ext = tok.rsplit(".", 1)[1].lower()
        if ext in SRC_EXT and re.match(r"^[\w./+-]+$", tok):
            out.append(tok)
    return out

# ---- check 1: index integrity --------------------------------------------------
def check_index():
    reports = report_files()
    ridx, tidx = read(REPORTS_INDEX), read(TOP_INDEX)
    # links registered in each index
    r_links = set(re.findall(r"\((\d{2}_[^)]+\.md)\)", ridx))
    t_links = set(re.findall(r"\(reports/(\d{2}_[^)]+\.md)\)", tidx))
    for rep in reports:
        if rep not in r_links:
            warn("index-integrity", f"{rep} is NOT registered in {REPORTS_INDEX}")
        if rep not in t_links:
            warn("index-integrity", f"{rep} is NOT registered in {TOP_INDEX}")
    existing = set(reports)
    for link in sorted(r_links - existing):
        warn("index-integrity", f"{REPORTS_INDEX} links {link} but that report file does not exist")
    for link in sorted(t_links - existing):
        warn("index-integrity", f"{TOP_INDEX} links reports/{link} but that report file does not exist")

# ---- check 2: referenced files exist -------------------------------------------
def check_refs():
    allfiles = repo_files()
    names = {os.path.basename(f) for f in allfiles}
    def suffix_match(tok):                       # a partial repo path, e.g. SWE_clean/plots/x
        needle = "/" + tok
        return any(f == tok or f.endswith(needle) for f in allfiles)
    for rep in report_files():
        rpath = os.path.join(REPORTS_DIR, rep)
        seen = set()
        for tok in cited_tokens(read(rpath)):
            if tok in seen:
                continue
            seen.add(tok)
            if "/" in tok:
                resolved = (os.path.exists(os.path.normpath(os.path.join(REPORTS_DIR, tok)))
                            or os.path.exists(os.path.normpath(tok))
                            or suffix_match(tok))
                if resolved:
                    continue
                # Unresolved. Warn only if it *looks like* a repo path (known top dir or a
                # basename we have elsewhere); otherwise it's an illustrative external path.
                top = tok.split("/", 1)[0]
                if top in REPO_TOPDIRS or os.path.basename(tok) in names:
                    warn("referenced-files", f"{rep} cites `{tok}` — script/figure not found in repo")
            else:
                if os.path.basename(tok) not in names:
                    warn("referenced-files", f"{rep} cites `{tok}` — script/figure not found in repo")

# ---- check 3: freshness --------------------------------------------------------
def check_freshness():
    # map basename -> its repo path, for resolving bare-name citations
    path_of = {}
    for line in sh("git", "ls-files").splitlines():
        if line:
            path_of.setdefault(os.path.basename(line), line)
    for rep in report_files():
        rpath = os.path.join(REPORTS_DIR, rep)
        rct = eff_ct(rpath)
        if rct is None:            # brand-new / untracked report — nothing to be stale against
            continue
        sources = {ANALYSIS}
        for tok in cited_tokens(read(rpath)):
            ext = tok.rsplit(".", 1)[1].lower()
            if ext not in SRC_EXT:
                continue
            if "/" in tok:
                p = os.path.normpath(os.path.join(REPORTS_DIR, tok))
                if not os.path.exists(p):
                    p = os.path.normpath(tok)
                sources.add(p)
            elif os.path.basename(tok) in path_of:
                sources.add(path_of[os.path.basename(tok)])
        newer = []
        for s in sources:
            sct = eff_ct(s)
            if sct is not None and sct > rct:
                newer.append(os.path.basename(s))
        if newer:
            shown = ", ".join(sorted(set(newer))[:4])
            warn("freshness", f"{rep} predates its source(s): {shown} — report may be stale")

# ---- check 4: report nudge -----------------------------------------------------
def check_nudge():
    pend = pending_paths()
    report_touched = any(p.startswith(REPORTS_DIR + os.sep) and p.endswith(".md") for p in pend)
    def is_trigger(p):
        if os.path.basename(p) == "analysis.md":
            return True
        if p.startswith(os.path.join("local_agents", "scripts", "glm")) and p.endswith((".py", ".sh")):
            return True
        if p.endswith(".png") and (os.sep + "plots" in p or "plots" + os.sep in p):
            return True
        return False
    triggers = [p for p in pend if is_trigger(p)]
    if triggers and not report_touched:
        shown = ", ".join(triggers[:5]) + (" …" if len(triggers) > 5 else "")
        warn("report-nudge", f"pending changes touch analysis/kit/figures ({shown}) but no docs/reports/ file — a report update may be missing")

# ---- check 5-9: wiki integrity -------------------------------------------------
def wiki_pages():
    out = []
    for dirpath, _, files in os.walk(WIKI_DIR):
        for f in files:
            if f.endswith(".md"):
                out.append(os.path.join(dirpath, f))
    return sorted(out)

def strip_code(text):
    """drop fenced blocks and inline-code spans so illustrative `TODO` isn't flagged."""
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"~~~.*?~~~", "", text, flags=re.DOTALL)
    return re.sub(r"`[^`]*`", "", text)

def local_link_targets(text):
    """relative (non-external, non-anchor) markdown link targets in `text`."""
    for tgt in MD_LINK.findall(text):
        tgt = tgt.split("#", 1)[0].strip()
        if tgt and not tgt.startswith(("http://", "https://", "mailto:")):
            yield tgt

def check_wiki():
    if not os.path.isdir(WIKI_DIR):
        return                                       # no wiki in this repo — nothing to lint
    pages = wiki_pages()

    # 5. raw checksum registry: every raw source registered, hashes match, no dangling entry
    if os.path.isdir(RAW_DIR):
        registered = {}
        if os.path.exists(RAW_SUMS):
            for line in read(RAW_SUMS).splitlines():
                m = re.match(r"([0-9a-fA-F]{64})\s+\*?(.+)$", line.strip())
                if m:
                    registered[m.group(2).strip()] = m.group(1).lower()
        else:
            warn("wiki-checksums", f"{RAW_SUMS} is missing")
        for f in sorted(os.listdir(RAW_DIR)):
            fp = os.path.join(RAW_DIR, f)
            if f == "SHA256SUMS" or not os.path.isfile(fp):
                continue
            if f not in registered:
                warn("wiki-checksums", f"docs/raw/{f} is not registered in SHA256SUMS")
            elif hashlib.sha256(open(fp, "rb").read()).hexdigest() != registered[f]:
                warn("wiki-checksums", f"docs/raw/{f} hash mismatch — a raw source was altered")
        for name in registered:
            if not os.path.isfile(os.path.join(RAW_DIR, name)):
                warn("wiki-checksums", f"SHA256SUMS lists {name} but docs/raw/{name} is missing")

    # 6. index registration: every page (except index.md itself) linked from index.md
    idx_targets = {os.path.normpath(os.path.join(WIKI_DIR, t))
                   for t in local_link_targets(read(WIKI_INDEX))}
    for p in pages:
        if os.path.normpath(p) != os.path.normpath(WIKI_INDEX) \
           and os.path.normpath(p) not in idx_targets:
            warn("wiki-index", f"{os.path.relpath(p)} is not linked from {WIKI_INDEX}")

    # 7. metadata table present (except the chronological log)
    for p in pages:
        if os.path.basename(p) == "log.md":
            continue
        text = read(p)
        missing = [fld for fld in META_FIELDS if not re.search(rf"\|\s*{fld}\s*\|", text)]
        if missing:
            warn("wiki-metadata", f"{os.path.relpath(p)} missing metadata: {', '.join(missing)}")

    # 8. relative links resolve; 9. no unfinished markers
    for p in pages:
        text = read(p)
        base = os.path.dirname(p)
        for tgt in local_link_targets(text):
            if not os.path.exists(os.path.normpath(os.path.join(base, tgt))):
                warn("wiki-links", f"{os.path.relpath(p)} → `{tgt}` does not resolve")
        if MARKER.search(strip_code(text)):
            warn("wiki-markers", f"{os.path.relpath(p)} contains an unfinished marker (TODO/TBD/FIXME)")

# ---- run all -------------------------------------------------------------------
def main():
    for fn in (check_index, check_refs, check_freshness, check_nudge, check_wiki):
        try:
            fn()
        except Exception as e:                       # a broken check must not kill the rest
            warn(fn.__name__, f"check crashed: {e!r}")

    ORDER = ("index-integrity", "referenced-files", "freshness", "report-nudge",
             "wiki-checksums", "wiki-index", "wiki-metadata", "wiki-links", "wiki-markers")
    print("=" * 68)
    print("  report + wiki check — docs/")
    print("=" * 68)
    if not warnings:
        print("  ✅ all clear: report indexes consistent, references resolve, reports")
        print("     fresh; wiki pages registered, linked, checksummed, and complete.")
        print("=" * 68)
        return 0
    by_cat = {}
    for cat, msg in warnings:
        by_cat.setdefault(cat, []).append(msg)
    for cat in ORDER:
        for msg in by_cat.get(cat, []):
            print(f"  ⚠️  [{cat}] {msg}")
    for cat, msgs in by_cat.items():                 # any crash categories
        if cat not in ORDER:
            for msg in msgs:
                print(f"  ⚠️  [{cat}] {msg}")
    print("=" * 68)
    print(f"  {len(warnings)} warning(s). Per the skill contract: DO NOT commit — surface")
    print("  these to the user and let them fix or explicitly override.")
    print("=" * 68)
    return 1

if __name__ == "__main__":
    sys.exit(main())
