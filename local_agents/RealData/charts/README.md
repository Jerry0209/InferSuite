# Realistic-dataset charts — versioned packs

Same convention as every other `charts/` tree: one folder per version, mentor layout inside,
never edit an existing version; `VERSION=vN_<date>_<tag> python3 local_agents/kit/plot/build_realdata_chart_pack.py`
(writes a README into the pack and into each of `Figures/`, `Raw data/`, `Scripts/`).

| Version | Status | Contents |
|---|---|---|
| `v1_2026-09-21_realistic-datasets/` | **CURRENT** | fig01 toy → realistic pairs per metric for six server workloads (Neo4j, Cassandra, Kafka, PageRank, Naive Bayes, video); fig02 the three-violin grid with the realistic Server set; fig03 the same grid with the suite set. Values: one per workload over its whole runtime. Method and findings: `../README.md` |
