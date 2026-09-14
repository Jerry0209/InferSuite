# Multi-suite charts — versioned packs

Same convention as every other `charts/` tree: one folder per version, mentor layout inside,
never edit an existing version; `VERSION=vN_<date>_<tag> python3 local_agents/kit/plot/build_jvm_chart_pack.py`.

| Version | Status | Contents |
|---|---|---|
| `v1_2026-09-14_jvm-suites/` | **CURRENT** | SPEC · agentic 36 · DCPerf (2) · Renaissance (5) · DaCapo (2; cassandra excluded) — compact grid with one marker per benchmark grouped by suite, plus the four per-window companions |
