# paper_v2 — the violin-family revision (2026-09-01)

This generation revises the **violin figures only** (mentor violin spec: paired
blue-vs-red hue/lightness palette, thick-black-IQR inner glyph, raw-point overlays,
rule-gated broken axes, hero stats strip). It supersedes `../paper_v1/`'s
`iso36_agg_{ipc,frontend,memory,system}_merged` and `iso36_agg_compact_merged`.

**The bar-family figures remain current in `../paper_v1/`** (live overview, cpu work,
busy seconds, TMA combined, the two model-wait live companions) — they are not
duplicated here.

- `iso36_agg_compact_merged` — the 12-panel SPEC-vs-Agentic grid; broken axes on the four
  panels where pooled max > 3× pooled p95 (L1I, L1D, L2, LLC — printed by the script);
  medians in the x tick labels; context-switches stays log (0† = SPEC median exactly 0).
- `bandwidth_variants/` — the same grid at KDE adjust 0.8 / 1.2 (default 1.0) for the
  mentor to pick; per-side nrd0 bandwidths in the numbers CSV.
- `iso36_hero_ipc` — the hero template: two violins + the Min/Max/Median/Mean±Std stats
  strip aligned under the columns (regenerate for any metric via `METRIC=... plot_paper_hero.R`).
- `iso36_agg_*_merged` — the four group pictures with the new inner glyph; hue stays the
  locked language palette there (the blue/red pairing encodes SPEC-vs-Agentic, which is
  not these figures' contrast); per-window violins, so no raw-point overlay.
