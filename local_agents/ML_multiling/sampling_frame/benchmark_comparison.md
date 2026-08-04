# Benchmark comparison — SWE-bench Multilingual vs Multi-SWE-bench

**Date:** 2026-07-31 · **Role:** mentor-packet deliverable 1 of 3 (with `classification_protocol.md`
and `task_inventory.csv`). Answers: which multilingual issue-resolving benchmarks exist, what each
contains, and why this study starts with SWE-bench Multilingual.
**Rule of this document:** every number carries its source; numbers we measured locally are marked
MEASURED; numbers quoted from external pages are marked QUOTED and were retrieved 2026-07-31;
unresolved contradictions are listed in §5, not smoothed over.

Supersedes the counts in `docs/handwritten_notes/analysis.md` appendix ("side question: can
SWE-bench be grouped by programming language?"), which first surveyed these benchmarks and
explicitly left Multi-SWE-bench per-language counts unverified.

## 1. The candidates

**SWE-bench Multilingual** — by the SWE-bench team (Khandpur, Lieret, Jimenez, Press, Yang;
QUOTED from swebench.com/multilingual.html). Construction follows the original SWE-bench
methodology: issues from top-starred repos whose PR contains at least one test file, filtered
for under-specified statements / multi-issue PRs / solution-rejecting tests, then an 8-step
per-instance execution validation (clone → install → test → patch → build → gold patch →
verify → parse logs). Reference result QUOTED from the same page: SWE-agent + Claude 3.7
Sonnet resolves 43 % (vs 63 % on SWE-bench Verified) — the languages, not the format, carry
the difficulty.

**Multi-SWE-bench** — ByteDance Seed (arXiv:2504.02605, April 2025). QUOTED from the paper/HF
card: 1,632 instances curated from 2,456 candidates by 68 expert annotators; 7 languages;
Python deliberately excluded. A `Multi-SWE-bench_mini` variant (400 instances, 50 per language
incl. Python) exists per the HF card listing — counts not independently verified.

Context, not candidates: SWE-bench Verified (500, Python — our Y-class reference tasks come
from it) and SWE-bench Multimodal (517, all JavaScript; handwritten-note appendix).

## 2. Side by side

| | SWE-bench Multilingual | Multi-SWE-bench |
|---|---|---|
| Instances | **300** (MEASURED, snapshot below) | 1,632 (QUOTED) |
| Languages | **9**: C, C++, Go, Java, JS, TS, PHP, Ruby, Rust (MEASURED) | 7: Java, TS, JS, Go, Rust, C, C++ (QUOTED) — **no PHP, no Ruby** |
| Repositories | **41 in-snapshot** (MEASURED); site says 42 (QUOTED, unresolved §5) | 32 (QUOTED from HF card; card has an internal inconsistency, §5) |
| Per-language split | Ruby 44 · Java 43 · Rust 43 · PHP 43 · Go 42 · JS 31 · C 30 · TS 12 · C++ 12 (MEASURED; JS/TS published as one 43 bucket, split here by toolchain) | not stated on card; paper appendix is the source — **unverified** |
| Validation | executable 8-step filter, SWE-bench methodology (QUOTED) | 68 expert annotators, 1,632/2,456 kept (QUOTED) |
| Harness | drop-in for the swebench/SWE-agent stack; per-instance Docker images `swebench/sweb.eval.x86_64.<owner>_1776_<repo-id>` (MEASURED: 11 live episodes banked here) | own harness + image scheme (github.com/multi-swe-bench); integration cost for our capture stack **unknown** |
| License | MIT (QUOTED, HF card) | CC0 with ByteDance IP note (QUOTED, HF card) |
| Repo overlap with our corpus | — | 9 of our 41 repos also appear there per its card lists: axios, vuejs/core, tokio, bat, nushell, ripgrep, jq, fmt, nlohmann/json |

**Snapshot provenance (MEASURED):** HF `swe-bench/SWE-Bench_Multilingual`, split `test`,
revision `e5c585e008e2cb5eecc7c64192d855c53279d788` (lastModified 2026-07-22; local cache
2026-07-29; revision re-checked current 2026-07-31). 300 rows, 41 distinct repos, fields:
repo, instance_id, base_commit, patch, test_patch, problem_statement, hints_text, created_at,
version, FAIL_TO_PASS, PASS_TO_PASS. Per-language counts are assertion-checked in
`local_agents/scripts/glm/multiling_inventory.py` (FATAL on unmapped repo) and were
independently recomputed from the cached dataset for this document — both agree.

## 3. Why SWE-bench Multilingual first (the mentor's directive, and four reasons it was right)

1. **Harness compatibility is proven, not assumed.** `SWE_SUBSET=multilingual` is wired into
   `run_glm_campaign.sh`; 11 live episodes, 9 full replay sets, and the ownership/adequacy
   gates all ran on this benchmark (reports 16–17). Multi-SWE-bench would need its own
   integration + re-validation of the capture stack.
2. **It is the only one with an interpreted-suite class.** PHP + Ruby = 87 instances, 29 % of
   the corpus, mechanism class I. Multi-SWE-bench has neither language, so class I — one of
   the five CPU mechanisms this study characterizes — would be unmeasurable there.
3. **Scale fits the design.** One-per-cell sampling needs breadth across languages, not 1,632
   instances; 300 instances inventory in ~1 min at zero API cost.
4. **Ecosystem continuity.** Same schema and eval flow as SWE-bench Verified, so the three
   Python reference tasks (Y class) from the earlier campaigns remain directly comparable.

## 4. What Multi-SWE-bench would add later — and what it would cost

The concrete future use is **de-confounding repo-starved classes**: our C++ column is two
header-only template libraries (fmt, nlohmann/json) — the pathological end of the C++ build
spectrum (plan.md caveat 1) — while Multi-SWE-bench's C++ list adds compiled-library repos
(Catch2, simdjson, cpp-httplib per its card); its Java (fastjson2, logstash, mockito) and Rust
(10 repos) lists similarly widen the second-repo pool that language-level claims require
(every language currently has exactly one accepted repo). Costs: separate harness and image
scheme (integration effort unknown), per-language instance counts still to be verified from
the paper appendix before any sampling math is done on it.

## 5. Unresolved discrepancies and unknowns (do not quote around them)

- **41 vs 42 repos**: the snapshot contains 41 distinct repos (MEASURED, zero unmapped);
  swebench.com and the handwritten note say 42. Cause unknown (site drift or a repo counted
  differently). Our claims use 41.
- **Multi-SWE-bench per-language instance counts**: not stated on the HF card; unverified here.
- The HF card's C++ row says "4 repositories" then lists 5 — card self-inconsistency; its repo
  lists are used only for the overlap note, never for counts.
- SWE-bench Multilingual release date: not stated on the pages retrieved.

**Sources:** swebench.com/multilingual.html · huggingface.co/datasets/swe-bench/SWE-Bench_Multilingual ·
huggingface.co/datasets/ByteDance-Seed/Multi-SWE-bench · arxiv.org/abs/2504.02605 ·
github.com/multi-swe-bench/multi-swe-bench · `docs/handwritten_notes/analysis.md` (appendix) ·
local snapshot recount 2026-07-31 (this repo).
