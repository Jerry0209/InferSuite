# cross_campaign — mentor-requested combined figure sets (2026-07-30)

Figures that combine tasks from TWO campaigns in one panel, produced on the mentor's explicit
instruction ("remove django, add fmtlib and babel; make new plots, do not touch the original
plots"). The originals are untouched: these render into their own `plots_*` directories from
their own specs.

**Method.** `data/` is a merged data root of **symlinks** into the source campaigns
(`superseded_40min` for the Python tasks and looped django; `SWE_clean` for babel and fmt).
Each variant has its own `spec_*.json` (same schema as a campaign `plot_spec.json`: label →
task dir → featured run) and is rendered by the standard, unmodified pipeline
(`plot_glm_results.py`) then certified by `audit_plots.py` — **all three variants report
ALL MATCH**. Featured runs are the campaigns' own: scikit run_1, astropy run_2, sympy run_2,
django run_2 (looped @0), babel run_1, fmt run_1.

| Variant | Spec | Tasks | Used by |
|---|---|---|---|
| `plots_5t/` | `spec_5t.json` | scikit-learn · astropy · sympy · babel · fmt | deck slides "Slide 1 · wall-clock" (`glm_time_split.png`), "Slide 2 · core-seconds" (`glm_cpu_work.png`), "Microarchitecture 1" right panel (`glm_tma_l1.png`) |
| `plots_calls6t/` | `spec_calls6t.json` | + django looped@0 (django@0.6 out) | deck "Slide 4 · call structure" (`glm_tool_calls.png`); its `glm_tma_l1.png` is also a mentor deliverable — the 6-task TMA-L1 breakdown (originals + looped django + babel/fmt) |
| `plots_tma4t/` | `spec_tma4t.json` | scikit-learn · astropy · sympy · django looped@0 | standalone TMA-L1 breakdown (django@0.6 submit-blocked run removed) |

**Provenance rule.** These panels mix campaigns; per the repo convention the mixing is stated
on the consuming slide/caption. Shares/TMA buckets are the cross-campaign-reproducible layer
(reports 06/08); absolute wall minutes and core-seconds are episode draws (babel spans
37.9–202.1 tool core-s across its four episodes — report 16).

**Regenerate** (any variant; ~1 min, no capture, housekeeping cores if a capture is live):

```bash
PY=~/miniforge3/envs/infersuite-full/bin/python3
PLOT_SPEC=local_agents/cross_campaign/spec_5t.json $PY local_agents/scripts/glm/plot_glm_results.py
PLOT_SPEC=local_agents/cross_campaign/spec_5t.json $PY local_agents/scripts/glm/audit_plots.py  # must say ALL MATCH
```

Side effect fixed while building this: `plot_glm_results.py`'s harness-anatomy figure had a
hardcoded 1×4 sub-grid and crashed at 5+ tasks (the four deck figures were already written, so
the crash was silent in practice); the grid now scales with the task count.
