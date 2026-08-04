# local_agents — SWE-agent × GLM-5.2 CPU-profiling campaigns

The agent-side measurement trees. Everything here is driven by the kit in `scripts/glm/`
(dispatched via the repo-root `./measure.sh`); figures regenerate from banked data only.
See `CLAUDE.md` (repo root) for the locked measurement conventions and
`docs/PLOTTING_GUIDE.md` for the plotting pipeline.

| Tree | What it is |
|---|---|
| `SWE_clean/` | The certified hardened SWE-agent × GLM-5.2 campaign (nohz_full boot, ISO-PROOF gate, zero-mux shuffled rotation, continuous TMA): live episodes (django, sympy, babel/JS, fmtlib/C++), deterministic replays, per-window `l3_study/` CSVs, figures + `plot_spec.json`. |
| `superseded_40min/` | The reproduced 4-task Python campaign (scikit-learn, astropy, sympy, django; 40-min cap) used for the cross-campaign reproducibility study, the django temp-0.6 experiment, and the per-window replay study. The *campaign design* is superseded — the data is live and backs the deck's per-window and reproducibility figures. `data/` is **gitignored and irreplaceable**. |
| `ML_multiling/` | The SWE-bench Multilingual expansion: live episodes + 11-pass dedicated-group replays across 9 languages, the 300-instance inventory, and `sampling_frame/` (the ⟨language, type⟩ taxonomy, classifications, behaviour ledger). Reports 16/17. Raw perf recordings gitignored. |
| `cross_campaign/` | Audited figure variants that mix campaigns for the deck (symlink data root + per-variant `spec_*.json` + `plots_*/`); see its `MANIFEST.md`. |
| `glm_plots/` | Frozen curated figure views from the archived soft-isolated long campaigns (`archive/glm_softiso_long_campaigns/`). |
| `scripts/glm/` | The measurement kit: staged campaign runner, validators (gates E1–E11), plotters, window tagger, figure audit, deck builder — plus the gitignored litellm proxy venv (`.venv_litellm`; exact pins in `litellm_venv_freeze.txt`). |

History: the pre-GLM local-loop experiment (live 7B-served agents; software-view figures,
loose capture/chain scripts, a held thesis subsection) and the empty `data/` stub were removed
from the tree on 2026-08-04 — recover from git history if ever needed.
