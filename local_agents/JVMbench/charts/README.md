# Multi-suite charts — versioned packs

Same convention as every other `charts/` tree: one folder per version, mentor layout inside,
never edit an existing version; `VERSION=vN_<date>_<tag> python3 local_agents/kit/plot/build_jvm_chart_pack.py`
(the builder writes a README into the pack and into each of `Figures/`, `Raw data/`, `Scripts/`).

| Version | Status | Contents |
|---|---|---|
| `v4_2026-09-21_realistic-server-set/` | **CURRENT** | v3's ten figures plus fig01b: the three-violin grid with the six suite benchmarks that were re-characterised on realistic datasets (cassandra, kafka, neo4j, page-rank, naive-bayes, video) replaced by those versions — the Server family moves further from the agentic profile; details `../../RealData/README.md` |
| `v3_2026-09-15_runtime-votes/` | superseded | the same ten figures under the mentor's rule of 2026-09-15: one value per workload = the metric over its whole runtime (`Raw data/runtime_votes.csv`, `../README.md` §9); Server = DCPerf 2 + Renaissance 5 + DaCapo 3 (DCPerf confirmed in the set); README in every subdirectory |
| `v2_2026-09-14_cassandra-reinstated/` | superseded (window-median rule) | fig01–05: the mentor's three-violin layout — SPEC (26) · **Server** (Renaissance 5 + DaCapo 3, one vote each) · Agentic (36) — compact grid plus the four per-window companions with a single Server column. fig06–10: the per-benchmark layout (SPEC and Agentic violins, one marker/column per external benchmark incl. DCPerf). DaCapo `cassandra` included in both, reinstated after the steady-state gate that excluded it was found defective (`../README.md` §8). `Raw data/` holds every script input plus time-ordered per-window rows for all families; README in every subdirectory |
| `v1_2026-09-14_jvm-suites/` | superseded | identical figures without `cassandra`; keep for provenance of anything already circulated |
