#!/usr/bin/env python3
"""Cross-task per-window distribution grids (tool + harness fences) from all_windows CSVs."""
import csv, os
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Per-task l3_study roots. The three Python tasks come from the reproduced superseded_40min
# campaign; the two multilingual tasks (SWE-bench Multilingual) come from the certified
# SWE_clean campaign — the only place their trajectories are banked. Cross-campaign mixing is
# acceptable here because per-window microarchitecture shares are the layer that reproduces
# across campaigns (Report 08); the provenance is stated in every figure's caption.
D  = "/home/thu/InferSuite/local_agents/superseded_40min/data/l3_study"
DM = "/home/thu/InferSuite/local_agents/SWE_clean/data/l3_study"
OUTD = os.environ.get("GRID_OUT", D)
LANG = {"scikit-learn": "Python", "astropy": "Python", "sympy": "Python",
        "babel": "JavaScript", "fmtlib": "C++"}
ROOT = {"scikit-learn": D, "astropy": D, "sympy": D, "babel": DM, "fmtlib": DM}
TASKS = [t for t in ["scikit-learn", "astropy", "sympy", "babel", "fmtlib"]
         if os.path.exists(f"{ROOT[t]}/all_windows_{t}.csv")]
TCOL = {"scikit-learn": "#159f77", "astropy": "#4d9e83", "sympy": "#6b4fa0",
        "babel": "#cf6a1f", "fmtlib": "#b2182b"}
ROWS = {t: list(csv.DictReader(open(f"{ROOT[t]}/all_windows_{t}.csv"))) for t in TASKS}

def vals(task, metric, fence):
    return [float(r["value"]) for r in ROWS[task]
            if r["fence"] == fence and r["metric"] == metric]

PANELS = [  # (metric key, panel title)  — mentor's list + the new fe_miss metrics
    ("IPC", "IPC"),
    ("branch_MPKI", "Branch MPKI (all mispredicts)"),
    ("DSB_pct", "DSB coverage (%)"),
    ("codeRead_MPKI_L1I", "L1I MPKI (code-read)"),
    ("L1D_MPKI", "L1D-load MPKI"),
    ("L2_MPKI", "L2-load MPKI"),
    ("LLC_MPKI", "LLC MPKI"),
    ("AMAT_cyc", "AMAT (cycles)"),
    ("MLP", "MLP"),
    ("branchDir_MPKI", "Branch-direction MPKI (cond.)"),
    ("BTB_MPKI", "BTB MPKI (BAClears)"),
    ("uopCache_MPKI", "µop-cache (DSB) MPKI"),
]

for fence in ("tool", "harness"):
    panels = [(m, ttl) for m, ttl in PANELS if any(vals(t, m, fence) for t in TASKS)]
    ncol = 4; nrow = (len(panels) + ncol - 1) // ncol
    fig, axes = plt.subplots(nrow, ncol, figsize=(16, 3.4 * nrow))
    axes = axes.flatten()
    for ax, (m, ttl) in zip(axes, panels):
        data = [vals(t, m, fence) for t in TASKS]
        bp = ax.boxplot(data, tick_labels=[f"{t[:6]}\n{LANG[t][:4]}\n(n={len(d)})"
                                          for t, d in zip(TASKS, data)],
                        showmeans=True, patch_artist=True, whis=(5, 95))
        for box, t in zip(bp["boxes"], TASKS):
            box.set_facecolor(TCOL[t]); box.set_alpha(.7)
        ax.set_title(ttl, fontsize=10.5); ax.grid(axis="y", alpha=.3)
        ax.tick_params(labelsize=8)
    for ax in axes[len(panels):]: ax.axis("off")
    fig.suptitle(f"Per-window distributions across tasks and languages — {fence} fence, 2-s "
                 f"windows (box = IQR, orange = median, ▲ = mean, whiskers = 5–95%, ○ = outliers)",
                 fontsize=12.5, y=1.0)
    fig.text(0.5, -0.004, "Python tasks: reproduced superseded_40min campaign · "
             "babel (JavaScript) + fmt (C++): SWE-bench Multilingual instances from the "
             "certified SWE_clean campaign", ha="center", fontsize=8.5, color="#666")
    fig.tight_layout(rect=[0, 0, 1, 0.985])
    out = f"{OUTD}/plots/cross_task_grid_{fence}.png"
    fig.savefig(out, dpi=135, bbox_inches="tight"); plt.close(fig)
    print("wrote", out, f"({len(panels)} panels)")

# per-call duration cross-task panel
fig, ax = plt.subplots(figsize=(7, 3.2))
have = [t for t in TASKS if os.path.exists(f"{ROOT[t]}/call_durations_{t}.csv")]
data = []
for t in have:
    data.append([float(r["execution_time_s"]) for r in csv.DictReader(open(f"{ROOT[t]}/call_durations_{t}.csv"))])
if data:
    bp = ax.boxplot(data, tick_labels=[f"{t[:6]}\n{LANG[t][:4]}\n(n={len(d)})" for t, d in zip(have, data)],
                    showmeans=True, patch_artist=True, whis=(5, 95))
    for box, t in zip(bp["boxes"], have): box.set_facecolor(TCOL[t]); box.set_alpha(.7)
    ax.set_yscale("log"); ax.set_ylabel("tool-call duration (s, log)")
    ax.set_title("Per-call wall-clock duration across tasks (trajectory execution_time)", fontsize=11)
    ax.grid(axis="y", alpha=.3)
    fig.tight_layout(); fig.savefig(f"{OUTD}/plots/cross_task_calldur.png", dpi=135, bbox_inches="tight")
    print("wrote cross_task_calldur.png")
