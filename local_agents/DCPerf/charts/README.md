# DCPerf charts — versioned packs

Same convention as `local_agents/ML_iso36/charts/`: every figure version lives in its own
folder with `Raw data/ · Scripts/ · Figures/{PDF,PNG} · README.md`. Never edit an existing
version; assemble a new one with
`VERSION=vN_<date>_<tag> python3 local_agents/kit/plot/build_dcperf_chart_pack.py`.

| Version | Status | Contents |
|---|---|---|
| `v2_2026-09-10_feedsim-video/` | **CURRENT** | SPEC vs agentic 36 vs **two** DCPerf benchmarks (FeedSim + VideoTranscodeBench), one column per benchmark |
| `v1_2026-09-10_feedsim/` | superseded | the first pack, FeedSim only (single DCPerf column) |

`../plots/paper_v1` is the render workspace the generators write into; this tree is the
deliverable. Method, operating points and findings: `../README.md`.
