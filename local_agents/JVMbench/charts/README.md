# Multi-suite charts — versioned packs

Same convention as every other `charts/` tree: one folder per version, mentor layout inside,
never edit an existing version; `VERSION=vN_<date>_<tag> python3 local_agents/kit/plot/build_jvm_chart_pack.py`
(the builder writes a README into the pack and into each of `Figures/`, `Raw data/`, `Scripts/`).

| Version | Status | Contents |
|---|---|---|
| `v2_2026-09-14_cassandra-reinstated/` | **CURRENT** | fig01–05: the mentor's three-violin layout — SPEC (26) · **Server** (Renaissance 5 + DaCapo 3, one vote each) · Agentic (36) — compact grid plus the four per-window companions with a single Server column. fig06–10: the per-benchmark layout (SPEC and Agentic violins, one marker/column per external benchmark incl. DCPerf). DaCapo `cassandra` included in both, reinstated after the steady-state gate that excluded it was found defective (`../README.md` §8). `Raw data/` holds every script input plus time-ordered per-window rows for all families; README in every subdirectory |
| `v1_2026-09-14_jvm-suites/` | superseded | identical figures without `cassandra`; keep for provenance of anything already circulated |
