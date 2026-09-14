# Multi-suite charts — versioned packs

Same convention as every other `charts/` tree: one folder per version, mentor layout inside,
never edit an existing version; `VERSION=vN_<date>_<tag> python3 local_agents/kit/plot/build_jvm_chart_pack.py`.

| Version | Status | Contents |
|---|---|---|
| `v2_2026-09-14_cassandra-reinstated/` | **CURRENT** | SPEC · agentic 36 · DCPerf (2) · Renaissance (5) · DaCapo (3) — same five figures with DaCapo `cassandra` reinstated after the steady-state gate that excluded it was found defective and rewritten (`../README.md` §8) |
| `v1_2026-09-14_jvm-suites/` | superseded | identical figures without `cassandra`; keep for provenance of anything already circulated |
