#!/usr/bin/env python3
"""build_chart_pack.py — assemble one VERSIONED chart pack (PI convention 2026-09-02):

Target: charts/$VERSION/ (env VERSION, default v2_2026-09-01_paper). Each version is a
separate folder; never rebuild an old version — bump VERSION for new figure revisions.

    charts/
      Raw data/   figNN_<name>.csv[.gz]   the exact numbers behind each figure
      Scripts/    figNN_<name>.{R,py}     the generator (copy of the canonical script,
                                          header states the canonical path + regen command)
      Figures/PDF/  figNN_<name>.pdf      -> paper
      Figures/PNG/  figNN_<name>.png      -> PPTX
      README.md

Sources: plots/paper_v1 (bar family) + plots/paper_v2 (violin family) — the two LATEST
generations per plots/MANIFEST.md. Rerunnable; overwrites the pack in place.
"""
import gzip
import json
import os
import shutil

import pandas as pd

REPO = os.path.expanduser("~/InferSuite")
ML = f"{REPO}/local_agents/ML_iso36"
KP = f"{REPO}/local_agents/kit/plot"
P1, P2 = f"{ML}/plots/paper_v1", f"{ML}/plots/paper_v2"
CH = f"{ML}/charts/" + os.environ.get("VERSION", "v2_2026-09-01_paper")
RAW, SCR = f"{CH}/Raw data", f"{CH}/Scripts"
FPDF, FPNG = f"{CH}/Figures/PDF", f"{CH}/Figures/PNG"
for d in (RAW, SCR, FPDF, FPNG):
    os.makedirs(d, exist_ok=True)

# fig number -> (name, source stem dir, canonical script, one-line description)
FIGS = [
    ("fig01", "live_overview", P1, "plot_paper_live_overview.py",
     "4-panel live overview: CPU working vs stall, tool vs harness, #calls, call duration"),
    ("fig02", "wall_split_live", P1, "plot_paper_wall_live.py",
     "episode wall split into disjoint tool / harness / model-wait segments (live, stacked)"),
    ("fig03", "busy_wall_live", P1, "plot_paper_wall_live.py",
     "tool busy, harness busy and model wait side by side with the wall tick (live, grouped)"),
    ("fig04", "cpu_work", P1, "plot_paper_cpu_work.py",
     "CPU work in core-seconds by fence, stacked per task (replays, median of 9 episodes)"),
    ("fig05", "active_wall", P1, "plot_paper_wall.py",
     "fence busy time in seconds, grouped, with implied tool parallelism (replays)"),
    ("fig06", "tma_l1_combined", P1, "plot_paper_tma_combined.py",
     "TMA Level 1 with both fences combined (slot-weighted), MEDIAN + SPEC reference rows"),
    ("fig07", "agg_compact_merged", P2, "plot_paper_agg_compact.R",
     "12-metric SPEC-vs-Agentic violin grid, one vote per workload, merged agent fence"),
    ("fig08", "hero_ipc", P2, "plot_paper_hero.R",
     "IPC hero: two violins + Min/Max/Median/Mean±Std stats strip"),
    ("fig09", "agg_ipc_merged", P2, "plot_paper_agg_groups.R",
     "IPC per-window violins: SPEC band + 36 tasks by language, merged fence"),
    ("fig10", "agg_frontend_merged", P2, "plot_paper_agg_groups.R",
     "frontend metrics (Branch/Branch-dir/BTB/L1I/DSB MPKI, DSB coverage), merged fence"),
    ("fig11", "agg_memory_merged", P2, "plot_paper_agg_groups.R",
     "memory metrics (L1D/L2/LLC MPKI, DRAM read GB/s), merged fence"),
    ("fig12", "agg_system_merged", P2, "plot_paper_agg_groups.R",
     "context switches per CPU-second (log axis), merged fence"),
]
LANGS = ["C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript"]
GROUP_METRICS = {
    "agg_ipc_merged": ["IPC"],
    "agg_frontend_merged": ["Branch MPKI", "Branch-direction MPKI", "BTB MPKI (BAClears)",
                            "L1I MPKI (code-read)", "uop-cache (DSB) MPKI", "DSB coverage (%)"],
    "agg_memory_merged": ["L1D-load MPKI", "L2-load MPKI", "LLC MPKI", "DRAM read (GB/s)"],
    "agg_system_merged": ["Context switches (/CPU-s)"],
}

# ---- figures + scripts ----
for fid, name, src, script, _d in FIGS:
    stem = f"{src}/iso36_{name}"
    shutil.copy(f"{stem}.pdf", f"{FPDF}/{fid}_{name}.pdf")
    shutil.copy(f"{stem}.png", f"{FPNG}/{fid}_{name}.png")
    dst = f"{SCR}/{fid}_{name}{os.path.splitext(script)[1]}"
    body = open(f"{KP}/{script}").read()
    hdr = (f"{'#!/usr/bin/env Rscript' if script.endswith('.R') else '#!/usr/bin/env python3'}\n"
           f"# {fid}_{name} — COPY of the canonical generator local_agents/kit/plot/{script}\n"
           f"# (single source of truth; edit THERE). Runs from the repo root against the\n"
           f"# banked data tree and writes into plots/{os.path.basename(src)}/.\n"
           f"# Regenerate: see charts/README.md.\n")
    body = body.split("\n", 1)[1] if body.startswith("#!") else body
    open(dst, "w").write(hdr + body)

# ---- raw data ----
def jcsv(vals_path, out, keys, agg_keys=None):
    v = json.load(open(vals_path))
    rows = []
    for k, m in v.items():
        if not isinstance(m, dict):
            continue
        row = {"row": k}
        row.update({c: m.get(c) for c in (keys if k not in ("AVG", "MEDIAN") or not agg_keys
                                          else agg_keys)})
        rows.append(row)
    pd.DataFrame(rows).to_csv(out, index=False)

shutil.copy(f"{P1}/iso36_live_overview_numbers.csv", f"{RAW}/fig01_live_overview.csv")
for fid, name in (("fig02", "wall_split_live"), ("fig03", "busy_wall_live")):
    jcsv(f"{P1}/iso36_wall_live_values.json", f"{RAW}/{fid}_{name}.csv",
         ["language", "cell", "wall", "seg_tool", "seg_harn", "seg_wait",
          "busy_tool", "busy_harn", "wait"])
jcsv(f"{P1}/iso36_cpu_work_values.json", f"{RAW}/fig04_cpu_work.csv",
     ["language", "cell", "n_episodes", "tool_core_s_median", "tool_core_s_min",
      "tool_core_s_max", "harness_core_s_median", "harness_core_s_min",
      "harness_core_s_max", "tool_core_s", "harness_core_s"])
jcsv(f"{P1}/iso36_active_wall_values.json", f"{RAW}/fig05_active_wall.csv",
     ["language", "cell", "n_episodes", "tool_busy_s_median", "tool_busy_s_min",
      "tool_busy_s_max", "harness_busy_s_median", "episode_wall_s_median",
      "tool_parallelism_x", "tool_busy_s", "harness_busy_s", "episode_wall_s"])
tv = json.load(open(f"{P1}/iso36_tma_combined_values.json"))
rows = []
for k, m in tv.items():
    if not isinstance(m, dict) or "shares" not in m:
        continue
    rows.append({"row": k, "language": m.get("language"), "cell": m.get("cell"),
                 **{f"pct_{c}": round(v, 3) for c, v in m["shares"].items()},
                 "tool_slot_share_pct": m.get("tool_slot_share_pct"), "n": m.get("n")})
pd.DataFrame(rows).to_csv(f"{RAW}/fig06_tma_l1_combined.csv", index=False)

d = pd.read_csv(f"{ML}/data/l3_study/agg_rows_long.csv")
d = d[d.fence == "both"]
spec = d[d.grp.isin(["SPEC-int", "SPEC-fp"])].copy()
spec["workload"] = spec.grp + " #" + (spec.groupby(["metric", "grp"]).cumcount() + 1).astype(str)
spec = spec.rename(columns={"value": "v"})[["metric", "workload", "v"]]
spec["side"] = "SPEC"
ag = (d[d.grp.isin(LANGS)].groupby(["metric", "col"], as_index=False)["value"].median()
      .rename(columns={"col": "workload", "value": "v"}))
ag["side"] = "Agentic"
pw = pd.concat([spec, ag])
pw.to_csv(f"{RAW}/fig07_agg_compact_merged.csv", index=False)
pw[pw.metric == "IPC"].to_csv(f"{RAW}/fig08_hero_ipc.csv", index=False)

for i, (name, mets) in enumerate(GROUP_METRICS.items(), start=9):
    sub = d[d.metric.isin(mets) & (d.grp != "Python")][["metric", "grp", "col", "value"]]
    with gzip.open(f"{RAW}/fig{i:02d}_{name}.csv.gz", "wt") as fh:
        sub.to_csv(fh, index=False)

# ---- README ----
lines = ["# ML_iso36 chart pack",
         "",
         "Organized per the mentor's layout (2026-09-02): one raw-data file, one script and",
         "one PDF+PNG per figure. **PDF → paper, PNG → slides.** Assembled from the two",
         "latest generations (`../plots/paper_v1` bar family, `../plots/paper_v2` violin",
         "family; see `../plots/MANIFEST.md` for full definitions and provenance).",
         "",
         "Population: the revised all-resolved 36 count-view tasks (jekyll-8167 in).",
         "`Raw data/` holds every number a figure displays. `Scripts/` are copies of the",
         "canonical generators in `local_agents/kit/plot/` (edit there — the header of each",
         "copy names its source); they run from the repo root against the banked data tree.",
         "Regenerate everything: run each script with the repo's conda interpreters",
         "(`infersuite-full` python for .py, the `rplot` env Rscript for .R), then rerun",
         "`local_agents/kit/plot/build_chart_pack.py` to refresh this pack.",
         "",
         "| Fig | Name | What it shows | Raw data |",
         "|---|---|---|---|"]
for fid, name, _src, _script, desc in FIGS:
    raw = f"fig{fid[3:]}_{name}.csv" + (".gz" if name.startswith("agg_") and name != "agg_compact_merged" else "")
    raw = f"{fid}_{name}.csv" + (".gz" if name.startswith("agg_") and name != "agg_compact_merged" else "")
    lines.append(f"| {fid} | {name} | {desc} | `Raw data/{raw}` |")
lines += ["",
          "Notes: fig02/fig03 share one values source (each CSV is complete on its own).",
          "fig09–fig12 raw data are per-window rows (gzipped; R reads .csv.gz natively).",
          "fig07/fig08 raw data are one row per workload (the per-window medians the violins",
          "vote with). The selection-matrix figure is metadata, not measurement, and lives at",
          "`../plots/iso36_selection_matrix.png`."]
open(f"{CH}/README.md", "w").write("\n".join(lines) + "\n")
print("chart pack assembled at", CH)
for root, _dirs, files in os.walk(CH):
    for f in sorted(files):
        p = os.path.join(root, f)
        print(f"  {os.path.relpath(p, CH):<44} {os.path.getsize(p)/1e6:6.2f} MB")
