# Decision: median run per cell, never pooled

| Field | Value |
|---|---|
| Owner | LLM maintained, human reviewed |
| Status | Validated |
| Last updated | 2026-07-29 |
| Sources | [CLAUDE.md](../../../CLAUDE.md), [analysis.md](../../handwritten_notes/analysis.md), [plot_spec.json](../../reports/README.md) |

## Context

Each cell (task × campaign) is captured with several attempts. A figure needs a single
representative per cell.

## Decision

For TMA and signature figures, **use the median run per cell and document the spread** — never pool
runs. `plot_spec.json` names the featured run per cell explicitly.

## Alternatives rejected

- **Pooling runs.** *Fact:* run-to-run variance is large — absolute wall-clock and core-seconds are
  2–3× draws even within one campaign (within-campaign variance ≥ between-campaign difference).
  Pooling would average across microarchitecturally distinct episodes and manufacture a signature
  no single run exhibits. What reproduces are the *proportions* and *shapes*, not the absolutes.

## Consequences

- Comparisons are median-vs-median with spread reported, not point-vs-point (comparing one run to
  one run "compares two lottery tickets").
- The featured-run selection is auditable: `audit_plots.py` recomputes each plotted number from the
  named raw run and must report ALL MATCH.

## Related pages

- [Agent measurement design](../architecture/measurement-design.md)
- Study reports on variance and featured selection: [`docs/reports/`](../../reports/README.md).
