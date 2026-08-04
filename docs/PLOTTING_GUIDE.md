# InferSuite plotting guide

How the figures in this repo are made, and how to make new ones that hold up to the same
scrutiny. Written for a colleague joining the project; assumes no prior knowledge of the repo.
The measurement conventions referenced here are locked in `CLAUDE.md` (root) — violating them
invalidates figures.

## 0. Golden rules (read these even if you skip the rest)

1. **Use the right Python.** Every plotter runs with the `infersuite-full` conda env:
   `~/miniforge3/envs/infersuite-full/bin/python3`. Bare `python3` has no matplotlib/numpy
   and fails (or worse, picks up a random env). `measure.sh` resolves this via `$PY`;
   standalone invocations must spell the path out.
2. **Plotting never collects.** Collection scripts only collect; figures are regenerated
   afterwards from banked data. If you need new numbers, that is a *capture*, not a plot.
3. **Never pool runs.** For TMA/signature-style figures use the median run per cell and
   document the spread. Absolute magnitudes vary 2–5× across episodes of the same task;
   composition (shares, per-window distributions) is the layer that reproduces.
4. **A figure is not done until the audit passes.** The plotter writes every displayed number
   into `values_dump.json`; `audit_plots.py` independently recomputes them from raw data and
   must print **ALL MATCH** before anyone trusts the figure.
5. **Never edit figures in the curated views.** Top-level `plots/` and `results/` are synced
   *copies* (`scripts/sync_plots.sh`). Regenerate at the source location and re-sync.
6. **Never change a published figure's population in place.** If a deck slide or report
   describes "three tasks", the file it references must keep three tasks forever. New task
   sets get a **new** output file (see §4, frozen subsets, and §5, variants).

## 1. Where data and figures live

Each campaign banks data next to its kit, with figures alongside:

| campaign | data | figures | spec |
|---|---|---|---|
| SWE-agent (certified) | `local_agents/SWE_clean/data/` | `local_agents/SWE_clean/plots/` | `local_agents/SWE_clean/plot_spec.json` |
| Multilingual pilots | `local_agents/ML_multiling/data/` | per-task galleries + grids | — |
| Reproduced Python tasks | `local_agents/superseded_40min/data/` | `local_agents/superseded_40min/plots/` | — |
| Cross-campaign variants | `local_agents/cross_campaign/data` (symlinks) | `local_agents/cross_campaign/plots_*/` | `spec_*.json` per variant |

Every figure directory has a `MANIFEST.md` documenting what each figure shows and how terms
are defined. Definitions go in the MANIFEST, not in figure footers.

## 2. The standard pipeline (campaign figures)

```
plot_spec.json  →  plotter  →  figures + values_dump.json  →  audit_plots.py (ALL MATCH)
                                                            →  scripts/sync_plots.sh
```

- `plot_spec.json` names the **featured run** per task (`data` root, `out` dir, `resolved`
  list of `[label, episode_dir, [runs]]`). This is how "which episode does the deck show?"
  stays reproducible.
- The main plotter is `local_agents/scripts/glm/plot_glm_results.py`. Without `PLOT_SPEC` it
  renders the certified campaign; with `PLOT_SPEC=<json>` it renders any compatible data root
  (this one env var is the entire variant mechanism — the plotter itself is never edited for
  a variant).
- Regenerate the standard sets with `./measure.sh plots [set]` (never re-captures anything).

Standalone equivalents:

```bash
PY=~/miniforge3/envs/infersuite-full/bin/python3
PLOT_SPEC=local_agents/SWE_clean/plot_spec.json $PY local_agents/scripts/glm/plot_glm_results.py
PLOT_SPEC=local_agents/SWE_clean/plot_spec.json $PY local_agents/scripts/glm/audit_plots.py   # must say ALL MATCH
$PY local_agents/scripts/glm/plot_exploratory.py        # exploratory set (plots*/extra/)
$PY local_agents/scripts/glm/plot_harness_scaling.py    # cross-campaign turns-scaling figure
```

(The OpenClaw campaign, the service campaign, and the GPU-side kit were removed from the tree
on 2026-08-04 — repo narrowed to SWE-agent profiling; everything is in git history, and their
synced figures remain frozen under `plots/{agents/oc_clean,service,gpu,engine}`.)

## 3. The per-window distribution family (l3_study)

The box-plot grids, per-command box plots and tagged timelines come from a separate pipeline
fed by **deterministic replays** (no model, no API cost) with one counter group dedicated per
pass (zero multiplexing), 2-second windows, and a 2 Hz host-side poll of the tool cgroup that
records what command was running (`cmdlog.tsv`).

Data lives under `<campaign>/data/l3_study/`:

- `all_windows_<task>.csv` — LONG format: one row per (pass, window, fence, metric), with the
  window's epoch, duration, instruction count and command tag. **This CSV is the interface:**
  every per-window figure regenerates from it; nothing re-parses raw perf output.
- `tma_intervals_<task>.csv` — 10-s TMA L1/L2 interval shares per fence.

Scripts (all in `local_agents/scripts/glm/`):

```bash
# derive/refresh a task's CSVs from its replay passes (+ per-metric box/tag/timeline PNGs)
$PY analyze_l3_windows.py <data_root> <task_short> --plot

# cross-task grid (tool + harness fences) from the banked CSVs
GRID_LAYOUT=16 $PY cross_task_grid.py                 # the 4×4 family layout (16 panels)
TASKS_ONLY="scikit-learn,astropy,sympy" GRID_SUFFIX="_py3" GRID_LAYOUT=16 $PY cross_task_grid.py
```

Knobs on `cross_task_grid.py` (env vars, no flags):

- `TASKS_ONLY="a,b,c"` — restrict the grid to a subset (task keys = campaign SHORT names).
- `GRID_SUFFIX="_py3"` — names the output file so a restricted grid is **frozen** for the
  slide that describes that subset (`cross_task_grid16_tool_py3.png`). Always set a suffix
  when using `TASKS_ONLY`; an unsuffixed run rewrites the all-task default file.
- `GRID_LAYOUT=16` — the 4×4 layout (IPC/branch row, instruction-supply row, cache-MPKI row,
  miss-rate/AMAT/MLP row). Unset = the original 12-panel layout, kept for old slides.
- `GRID_OUT=<dir>` — redirect output away from the default l3_study plots dir.

Things the CSVs already encode so you don't rediscover them:

- **Window tags come from program basenames**, not argv substrings (path segments collide
  with tool names — `/usr/local/bundle/bin/rubocop` is the app under test, not bundler).
  The taxonomy and priority order live at the top of `analyze_l3_windows.py`.
- **Ratios must use co-counted denominators.** Each metric is computed within one pass
  (its own windows' instructions). Never join two metrics window-by-window across passes,
  and never divide one group's event by instructions summed over all groups.
- **No banked L1I access count exists**, so "L1I miss rate" is impossible; figures show the
  iCache-stall share of cycles, labelled as a proxy on the figure itself.

## 4. Making a variant without touching the originals

When someone asks "same figure, different task set", do **not** edit the original figure or
plotter. Follow the `local_agents/cross_campaign/` pattern:

1. Create (or reuse) a merged data root of **symlinks** to the source campaigns' episode dirs.
2. Write a per-variant `spec_<name>.json` (same schema as `plot_spec.json`) pointing `out` at
   a fresh `plots_<name>/` directory.
3. Render with the unmodified plotter: `PLOT_SPEC=spec_<name>.json $PY plot_glm_results.py`.
4. Audit with the same spec: `PLOT_SPEC=spec_<name>.json $PY audit_plots.py` → ALL MATCH.
5. Record the variant in the directory's `MANIFEST.md`: task set, provenance (which campaign
   each column comes from), and the regen command.

Cross-campaign mixing is legitimate only for the layers proven to reproduce across campaigns
(shares, per-window composition — see Report 08); state the per-task provenance in the
caption/MANIFEST every time.

## 5. House style (locked)

- **Colors** (cross-figure, non-negotiable): whitish grey = GPU/model wait, **green** = tool
  fence, **purple** = harness, **orange** = litellm proxy.
- **Vocabulary**: "CPU usage (cores)" = core-seconds per second; amounts in core-seconds;
  shares as % of CPU time; "core" = logical CPU; say "OS share", never "kernel"; no bare
  "CPUs"/"CPU-s" axis labels.
- **Language labels**: never truncate ("JavaScript"[:4] = "Java" names a different language).
  Use the `SHORT` map in `cross_task_grid.py` (Py, JS, TS, Rs, Go…).
- On-figure titles are SHORT; the caption/MANIFEST carries the description.
- Footers/captions state provenance when a figure mixes campaigns or uses a frozen subset.

## 6. The deck (and its PDF)

The team deck is one self-contained HTML with every figure inlined as base64:

```bash
DECK_OUT=/tmp/deck.html $PY local_agents/scripts/glm/build_deck.py
```

Figures are referenced by **path** in `build_deck.py`'s `IMG` table, so re-running after a
figure regeneration picks the new PNGs up automatically. The published deck is a Claude
artifact; the link registry is Report 14 §2.5 (every published deck/gallery must get a row).
A PDF export script (print-layout injection + headless-Firefox print, one page per slide)
lives at `/home/thu/deck_pdf_build/make_pdf.py` on the workstation.

## 7. Checklist for a new figure

- [ ] Data already banked? If not, that's a capture — separate step, separate approval.
- [ ] Rendered with the `infersuite-full` python, from banked data only.
- [ ] Median run per cell (no pooling); dispersion documented if you have multiple runs.
- [ ] House colors and vocabulary (§5); no truncated language labels.
- [ ] Every displayed number lands in `values_dump.json` (or the figure's data CSV exists),
      and the audit reports ALL MATCH.
- [ ] Frozen population: output filename encodes the task subset if a slide/report will cite it.
- [ ] MANIFEST entry: definition, provenance, regen command.
- [ ] Synced to the curated views with `scripts/sync_plots.sh` (never hand-copied).
- [ ] Thesis use: show in chat for approval first; copy into the thesis repo only when told.
