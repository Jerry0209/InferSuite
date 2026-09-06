# ML_iso36 charts — versioned chart packs

**The maintenance convention (PI directive 2026-09-02): every figure version lives in its
own folder here, each with the same internal layout:**

    vN_<date>_<tag>/
      Raw data/        one CSV (or values JSON) per figure — every number displayed
      Scripts/         the generator per figure (or SOURCES.md pinning a git commit)
      Figures/PDF/     -> paper
      Figures/PNG/     -> PPTX
      README.md        what this version is, figure index, provenance

New figure work NEVER edits an existing version folder: regenerate in the plots/
workspaces, then assemble a NEW vN folder with
`VERSION=vN_<date>_<tag> python3 local_agents/kit/plot/build_chart_pack.py`.

| Version | Status | Contents |
|---|---|---|
| `v3_2026-09-06_paperready/` | **CURRENT** | the paper-ready revision of v2 (PI 2026-09-06): no on-figure titles / explanatory grey text / red off-scale text / per-violin median labels; legends centred at the top (fig07's unboxed); fig08 unchanged |
| `v2_2026-09-01_paper/` | superseded | the paper-style set over the revised all-resolved 36: fig01–fig12 (bar family from plots/paper_v1, violin family from plots/paper_v2) |
| `v1_2026-08-28_original36/` | superseded | the pre-revision original-36 set (fpm-1829 in), frozen; scripts pinned by commit in its Scripts/SOURCES.md |

`../plots/paper_v1`, `../plots/paper_v2` are the RENDER WORKSPACES the generators write
into (see `../plots/MANIFEST.md` for figure definitions); this tree is the versioned
deliverable. The selection-matrix figure (metadata, not measurement) stays at
`../plots/iso36_selection_matrix.png`.
