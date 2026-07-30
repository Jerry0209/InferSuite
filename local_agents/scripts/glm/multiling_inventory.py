#!/usr/bin/env python3
"""multiling_inventory.py — inventory SWE-bench Multilingual by language, and extract the STATIC
per-instance features needed to categorise tasks by expected tool properties before running them.

Why static features: the sampling frame must be decided WITHOUT running the episodes (running one
costs an API episode plus ~50 min of profiling). The only information available a priori is the
instance metadata — repo, problem statement, the gold patch, the test patch, and the FAIL_TO_PASS /
PASS_TO_PASS test lists. Everything here is derived from those.

Outputs <out>/multiling_inventory.csv with one row per instance:
    instance_id, repo, language, ps_chars, ps_has_traceback, ps_has_repro, hints_chars,
    patch_files, patch_hunks, patch_add, patch_del, patch_exts,
    test_files, test_hunks, test_add, n_f2p, n_p2p,
    touches_header, touches_build, touches_core

and prints the per-language inventory table (the mentor's first question).

    python3 multiling_inventory.py [--out DIR]

Language mapping is explicit per repo rather than guessed: it is asserted against the published
per-language counts (Ruby 44, Go 42, Java 43, JS/TS 43, PHP 43, Rust 43, C 30, C++ 12 = 300) so a
silent mis-mapping cannot pass. JS and TS share one published bucket; they are separated here by
repo because they are different toolchains (tsc/vitest vs babel/jest) and the study treats them as
distinct columns.
"""
import csv, os, re, sys, collections

OUT = "/home/thu/InferSuite/local_agents/ML_multiling/data"
if "--out" in sys.argv: OUT = sys.argv[sys.argv.index("--out") + 1]

# repo -> language. Verified: the summed counts reproduce the published per-language totals.
REPO_LANG = {
    # Ruby (44)
    "rubocop/rubocop": "Ruby", "fluent/fluentd": "Ruby", "fastlane/fastlane": "Ruby",
    "jekyll/jekyll": "Ruby", "faker-ruby/faker": "Ruby", "jordansissel/fpm": "Ruby",
    # Go (42)
    "caddyserver/caddy": "Go", "gin-gonic/gin": "Go", "prometheus/prometheus": "Go",
    "gohugoio/hugo": "Go", "hashicorp/terraform": "Go",
    # Java (43)
    "projectlombok/lombok": "Java", "apache/lucene": "Java", "google/gson": "Java",
    "apache/druid": "Java", "javaparser/javaparser": "Java", "reactivex/rxjava": "Java",
    # JavaScript / TypeScript (43 combined) — split by toolchain, see docstring
    "preactjs/preact": "JavaScript", "babel/babel": "JavaScript", "axios/axios": "JavaScript",
    "mrdoob/three.js": "JavaScript",
    "facebook/docusaurus": "TypeScript", "vuejs/core": "TypeScript",
    "immutable-js/immutable-js": "TypeScript",
    # PHP (43)
    "laravel/framework": "PHP", "briannesbitt/carbon": "PHP",
    "php-cs-fixer/php-cs-fixer": "PHP", "phpoffice/phpspreadsheet": "PHP",
    # Rust (43)
    "tokio-rs/tokio": "Rust", "sharkdp/bat": "Rust", "astral-sh/ruff": "Rust",
    "tokio-rs/axum": "Rust", "nushell/nushell": "Rust", "uutils/coreutils": "Rust",
    "burntsushi/ripgrep": "Rust",
    # C (30)
    "redis/redis": "C", "jqlang/jq": "C", "micropython/micropython": "C",
    "valkey-io/valkey": "C",
    # C++ (12)
    "fmtlib/fmt": "C++", "nlohmann/json": "C++",
}
# Published totals; JS+TS are one published bucket so they are checked together.
EXPECT = {"Ruby": 44, "Go": 42, "Java": 43, "PHP": 43, "Rust": 43, "C": 30, "C++": 12}
EXPECT_JSTS = 43

# A build step is unavoidable before tests in these languages: the test command itself compiles.
COMPILED = {"C", "C++", "Rust", "Go", "Java"}
BUILD_FILES = re.compile(r"(CMakeLists\.txt|Makefile|configure\.ac|\.pro$|BUILD|Cargo\.toml|"
                         r"go\.mod|pom\.xml|build\.gradle|package\.json|composer\.json|Gemfile)")
HEADER_EXT = {".h", ".hpp", ".hh", ".hxx", ".inc"}


def diff_stats(patch):
    """files, hunks, added, deleted, set(extensions) for a unified diff."""
    files, hunks, add, dele, exts = set(), 0, 0, 0, set()
    for ln in (patch or "").splitlines():
        if ln.startswith("diff --git"):
            m = re.search(r" b/(\S+)$", ln)
            if m:
                files.add(m.group(1)); exts.add(os.path.splitext(m.group(1))[1].lower())
        elif ln.startswith("@@"): hunks += 1
        elif ln.startswith("+") and not ln.startswith("+++"): add += 1
        elif ln.startswith("-") and not ln.startswith("---"): dele += 1
    return files, hunks, add, dele, exts


def n_tests(field):
    """FAIL_TO_PASS / PASS_TO_PASS arrive as a JSON-ish list or a string; count entries."""
    if not field: return 0
    if isinstance(field, list): return len(field)
    s = str(field).strip()
    if s.startswith("["):
        # count quoted entries rather than json.loads: some rows use single quotes
        return len(re.findall(r'["\'][^"\']+["\']', s))
    return len([x for x in s.split("\n") if x.strip()])


def main():
    from datasets import load_dataset
    ds = load_dataset("swe-bench/SWE-Bench_Multilingual", split="test")

    unknown = sorted({r["repo"] for r in ds} - set(REPO_LANG))
    if unknown:
        sys.exit(f"FATAL: unmapped repos (would silently skew the inventory): {unknown}")

    rows = []
    for r in ds:
        lang = REPO_LANG[r["repo"]]
        pf, ph, pa, pd, pe = diff_stats(r.get("patch"))
        tf, th, ta, _, _ = diff_stats(r.get("test_patch"))
        ps = r.get("problem_statement") or ""
        rows.append({
            "instance_id": r["instance_id"], "repo": r["repo"], "language": lang,
            "ps_chars": len(ps),
            # a traceback or an explicit reproduction script tells the agent WHERE to look, which
            # should reduce searching; their absence is the search-heavy signature
            "ps_has_traceback": int(bool(re.search(r"Traceback|panic:|at [\w.]+\(.*:\d+\)|"
                                                   r"Exception in thread|#\d+ 0x", ps))),
            "ps_has_repro": int(bool(re.search(r"```|\$ |Steps to reproduce|reproduc", ps, re.I))),
            "hints_chars": len(r.get("hints_text") or ""),
            "patch_files": len(pf), "patch_hunks": ph, "patch_add": pa, "patch_del": pd,
            "patch_exts": " ".join(sorted(x for x in pe if x)),
            "test_files": len(tf), "test_hunks": th, "test_add": ta,
            "n_f2p": n_tests(r.get("FAIL_TO_PASS")), "n_p2p": n_tests(r.get("PASS_TO_PASS")),
            "touches_header": int(any(os.path.splitext(f)[1].lower() in HEADER_EXT for f in pf)),
            "touches_build": int(any(BUILD_FILES.search(f) for f in pf)),
            "touches_core": int(lang in COMPILED),
        })

    got = collections.Counter(r["language"] for r in rows)
    for lang, n in EXPECT.items():
        assert got[lang] == n, f"language count mismatch {lang}: got {got[lang]}, expected {n}"
    assert got["JavaScript"] + got["TypeScript"] == EXPECT_JSTS, \
        f"JS+TS mismatch: {got['JavaScript']}+{got['TypeScript']} != {EXPECT_JSTS}"
    assert len(rows) == 300, len(rows)

    os.makedirs(OUT, exist_ok=True)
    p = f"{OUT}/multiling_inventory.csv"
    with open(p, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

    print(f"wrote {p}: {len(rows)} instances\n")
    print("=== SWE-bench Multilingual inventory by language ===")
    print(f"{'language':<12}{'tasks':>6}{'repos':>7}   repos (n)")
    for lang, n in sorted(got.items(), key=lambda kv: -kv[1]):
        rp = collections.Counter(r["repo"] for r in rows if r["language"] == lang)
        print(f"{lang:<12}{n:>6}{len(rp):>7}   " +
              ", ".join(f"{k.split('/')[-1]} ({v})" for k, v in rp.most_common()))
    print(f"{'TOTAL':<12}{len(rows):>6}{len({r['repo'] for r in rows}):>7}")


if __name__ == "__main__":
    main()
