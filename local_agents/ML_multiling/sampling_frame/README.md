# Sampling frame for SWE-bench Multilingual (2026-07-30)

Produced by a multi-agent workflow (14 agents: adversarial critique → operational taxonomy →
per-language classification of all 300 instances → validation against the 12 episodes with
measured tool-fence compositions → sampling plan). Inputs: `../data/multiling_inventory.csv`
(static features; extractor `local_agents/scripts/glm/multiling_inventory.py`) plus the banked
compositions in `../data/l3_study/`.

- `taxonomy_spec.json`   — categories (B/A/J/I/N + Y placeholder), deterministic decision
  procedure, ambiguity/risk rules, known limits. Apply it to the inventory CSV to reproduce
  the classification without any LLM.
- `classifications.json` — all 300 assignments with confidence + per-language representatives.
- `validation.md`        — agree/disagree table vs the 12 measured compositions; honest-accuracy
  verdict (treat static labels as priors, not truth).
- `plan.md`              — ⟨language, type⟩ matrix and run list. NOTE: numbers in prose were
  audited afterwards; two corrections are recorded in docs/reports/17 (§2.2) — the babel 5.33×
  live-episode spread is CONFIRMED, the "fmt vs gin" magnitude pair is 9.6× per-pass (not 96×).

Method + verdicts: docs/reports/17_slide28_language_type_sampling_frame.md.

Mentor packet (2026-07-31) — consolidation deliverables, written after the falsification
probes; sources of truth unchanged (specs/scripts above win on any disagreement):

- `mentor_answer.md`          — layered answer to the instruction: one page, claim–evidence
  table, technical appendix, pending decisions.
- `classification_protocol.md`— the two-axis protocol (mechanism vs behaviour), intrinsic-vs-
  observed rules, confidence semantics, invalidation checklist.
- `benchmark_comparison.md`   — SWE-bench Multilingual vs Multi-SWE-bench with provenance;
  snapshot revision; unresolved discrepancies (41-vs-42 repos).
- `task_inventory.csv`        — per-instance: static features + mechanism class/confidence +
  behavioural prior + realized label where measured (`behavior_classify.py export`).
- `behavior_ledger.tsv`       — executed probe outcomes (3 realized-mismatch, 3 no-image
  false negatives — images verified available afterwards; check since fixed).
