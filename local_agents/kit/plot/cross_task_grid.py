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
DML = "/home/thu/InferSuite/local_agents/ML_multiling/data/l3_study"   # language pilots
LANG = {"scikit-learn": "Python", "astropy": "Python", "sympy": "Python",
        "babel": "JavaScript", "fmtlib": "C++",
        # SWE-bench Multilingual pilots. Task keys are the campaign's SHORT = the owner segment
        # of the instance id, which is why several read as an org rather than a project.
        "tokio-rs": "Rust", "jqlang": "C", "gin-gonic": "Go", "google": "Java",
        "rubocop": "Ruby", "briannesbitt": "PHP", "vuejs": "TypeScript",
        "prometheus": "Go", "php-cs-fixer": "PHP", "phpoffice-bT": "PHP"}
# Display name per task: the raw SHORT is often unreadable on an axis ("google" is gson/Java,
# "briannesbitt" is carbon/PHP), and t[:6] would truncate it to something worse.
NAME = {"scikit-learn": "scikit", "tokio-rs": "tokio", "jqlang": "jq", "gin-gonic": "gin",
        "google": "gson", "briannesbitt": "carbon", "vuejs": "vue", "fmtlib": "fmt",
        "prometheus": "promth", "php-cs-fixer": "cs-fixer", "phpoffice-bT": "sheet-T"}
def tname(t):
    return NAME.get(t, t)[:8]
# Axis labels use SHORT, never LANG[...][:4] — truncating "JavaScript" yields "Java", which
# names a DIFFERENT SWE-bench-Multilingual language, and "Python" yields "Pyth".
SHORT = {"Python": "Py", "JavaScript": "JS", "TypeScript": "TS", "C++": "C++", "C": "C",
         "Java": "Java", "Ruby": "Rb", "PHP": "PHP", "Rust": "Rs", "Go": "Go"}
def slang(t):
    return SHORT.get(LANG[t], LANG[t])
# GRID_ROOT=<l3_study dir> points every task at ONE campaign instead of the historical
# per-task mix. Added 2026-08-10 for the matched-configuration re-capture (SWE_iso8: cores 4-11
# SMT off, 100 ms windows), where all twelve tasks live in a single tree — so the figure no
# longer has to state a per-task provenance, because there is only one.
_GRID_ROOT = os.environ.get("GRID_ROOT")
# The window length used to be hard-coded as "2-s" in the suptitle. That silently became a
# false caption the moment the campaign was re-captured at 100 ms, so it is now a parameter:
# GRID_WINSEC in seconds, rendered as ms below 1 s.
_WS = float(os.environ.get("GRID_WINSEC", "2"))
WINLAB = f"{_WS*1000:.0f} ms" if _WS < 1 else f"{_WS:g} s"
# GRID_PROV replaces the per-task provenance footer when every task comes from ONE campaign —
# listing twelve tasks under one label is noise, and the interesting fact is the configuration.
_PROV = os.environ.get("GRID_PROV")
ROOT = {"scikit-learn": D, "astropy": D, "sympy": D, "babel": DM, "fmtlib": DM,
        "tokio-rs": DML, "jqlang": DML, "gin-gonic": DML, "google": DML,
        "rubocop": DML, "briannesbitt": DML, "vuejs": DML, "prometheus": DML, "php-cs-fixer": DML, "phpoffice-bT": DML}
# Existing tasks first so the established figures keep their column order; pilots append in
# language order. A task with no banked CSV is skipped, so this list can name work not yet run.
ORDER = ["scikit-learn", "astropy", "sympy", "babel", "fmtlib",
         "vuejs", "google", "tokio-rs", "prometheus", "jqlang", "rubocop", "php-cs-fixer", "phpoffice-bT"]
if _GRID_ROOT:
    ROOT = {t: _GRID_ROOT for t in ROOT}
    OUTD = os.environ.get("GRID_OUT", _GRID_ROOT)
TASKS = [t for t in ORDER if os.path.exists(f"{ROOT[t]}/all_windows_{t}.csv")]
# TASKS_ONLY="a,b,c" restricts the grid; GRID_SUFFIX names the output so a restricted grid can be
# FROZEN for a deck slide whose prose describes that subset. Added when the 12-task grid silently
# replaced the 3-task figure under deck slide 22 ("Three tasks, three distribution shapes") — a
# figure a slide references must not change population out from under its caption.
_only = os.environ.get("TASKS_ONLY")
if _only:
    keep = [t.strip() for t in _only.split(",") if t.strip()]
    TASKS = [t for t in TASKS if t in keep]
SUFFIX = os.environ.get("GRID_SUFFIX", "")
TCOL = {"scikit-learn": "#159f77", "astropy": "#4d9e83", "sympy": "#6b4fa0",
        "babel": "#cf6a1f", "fmtlib": "#b2182b",
        "vuejs": "#e08a1f", "google": "#3d6b1f", "tokio-rs": "#8c4a1f",
        "gin-gonic": "#1f6f8c", "prometheus": "#1f6f8c", "jqlang": "#7a1f5b", "rubocop": "#8c1f3d",
        "briannesbitt": "#5b4b8a", "php-cs-fixer": "#5b4b8a", "phpoffice-bT": "#8f86b5"}
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

# Mentor-requested 4x4 rearrangement (2026-07-30): branch family on one row, front-end/L1 on
# the next, then the cache ladder as MPKI + MISS-RATE pairs. Selected with GRID_LAYOUT=16,
# written to cross_task_grid16_* — the original 12-panel files are never overwritten.
# "L1I stall (% cycles)" stands in for an L1I miss rate: no L1I access count is banked
# (l2_rqsts.all_code_rd counts misses only), stated here and in the figure footer.
PANELS16 = [
    ("IPC", "IPC"),
    ("branch_MPKI", "Branch MPKI (all mispredicts)"),
    ("branchDir_MPKI", "Branch-direction MPKI (cond.)"),
    ("BTB_MPKI", "BTB MPKI (BAClears)"),
    ("DSB_pct", "DSB coverage (%)"),
    ("uopCache_MPKI", "µop-cache (DSB) MPKI"),
    ("codeRead_MPKI_L1I", "L1I MPKI (code-read)"),
    ("L1D_MPKI", "L1D-load MPKI"),
    ("L2_MPKI", "L2-load MPKI"),
    ("LLC_MPKI", "LLC MPKI"),
    ("icache_data_stall_pct", "L1I stall (% cycles) — miss-rate proxy"),
    ("L1D_missrate_pct", "L1D miss rate (%)"),
    ("L2_missrate_pct", "L2-load miss rate (%)"),
    ("LLC_missrate_pct", "LLC miss rate (%)"),
    ("AMAT_cyc", "AMAT (cycles)"),
    ("MLP", "MLP"),
]
LAYOUT16 = os.environ.get("GRID_LAYOUT") == "16"
if LAYOUT16:
    PANELS = PANELS16

for fence in ("tool", "harness"):
    panels = [(m, ttl) for m, ttl in PANELS if any(vals(t, m, fence) for t in TASKS)]
    ncol = 4; nrow = (len(panels) + ncol - 1) // ncol
    # Width must grow with the task count: at 5 tasks 16in was fine, at 12 the tick labels
    # collided into an unreadable smear. ~0.30in per task per panel column keeps them apart.
    fig_w = max(16, ncol * (1.7 + 0.30 * len(TASKS)))
    fig, axes = plt.subplots(nrow, ncol, figsize=(fig_w, 3.4 * nrow))
    axes = axes.flatten()
    for ax, (m, ttl) in zip(axes, panels):
        data = [vals(t, m, fence) for t in TASKS]
        # n on its own line and comma-grouped: at 12 tasks the four-digit counts of a 100 ms
        # capture ran together into "(n=826)(n=1359)" and could not be read.
        bp = ax.boxplot(data, tick_labels=[f"{tname(t)}\n{slang(t)}\n{len(d):,}"
                                          for t, d in zip(TASKS, data)],
                        showmeans=True, patch_artist=True, whis=(5, 95))
        for box, t in zip(bp["boxes"], TASKS):
            box.set_facecolor(TCOL[t]); box.set_alpha(.7)
        ax.set_title(ttl, fontsize=10.5); ax.grid(axis="y", alpha=.3)
        ax.set_xlabel("task · language · windows", fontsize=7.5, labelpad=1)
        ax.tick_params(labelsize=7 if len(TASKS) > 8 else 8)
    for ax in axes[len(panels):]: ax.axis("off")
    fig.suptitle(f"Per-window distributions across tasks and languages — {fence} fence, "
                 f"{WINLAB} windows (box = IQR, orange = median, ▲ = mean, whiskers = 5–95%, "
                 "○ = outliers)", fontsize=12.5, y=1.0)
    # Provenance is built from the task set actually plotted. Hard-coding it (it used to name
    # "babel + fmt" as the only multilingual tasks) silently becomes a false caption the moment
    # another language is added — the same failure mode as the truncated "Java" label.
    def prov(root, label):
        ts = [f"{tname(t)} ({LANG[t]})" for t in TASKS if ROOT[t] == root]
        return f"{label}: {', '.join(ts)}" if ts else ""
    fig.text(0.5, -0.004, _PROV or " · ".join(x for x in [
        prov(D, "reproduced superseded_40min campaign"),
        prov(DM, "certified SWE_clean campaign"),
        prov(DML, "SWE-bench Multilingual language pilots (ML_multiling)")] if x),
        ha="center", fontsize=8.5, color="#666")
    fig.tight_layout(rect=[0, 0, 1, 0.985])
    out = f"{OUTD}/plots/cross_task_grid{'16' if LAYOUT16 else ''}_{fence}{SUFFIX}.png"
    fig.savefig(out, dpi=135, bbox_inches="tight"); plt.close(fig)
    print("wrote", out, f"({len(panels)} panels)")

# per-call duration cross-task panel
fig, ax = plt.subplots(figsize=(max(7, 1.2 + 0.62 * len(TASKS)), 3.2))
have = [t for t in TASKS if os.path.exists(f"{ROOT[t]}/call_durations_{t}.csv")]
data = []
for t in have:
    data.append([float(r["execution_time_s"]) for r in csv.DictReader(open(f"{ROOT[t]}/call_durations_{t}.csv"))])
if data:
    bp = ax.boxplot(data, tick_labels=[f"{tname(t)}\n{slang(t)}\n(n={len(d)})" for t, d in zip(have, data)],
                    showmeans=True, patch_artist=True, whis=(5, 95))
    for box, t in zip(bp["boxes"], have): box.set_facecolor(TCOL[t]); box.set_alpha(.7)
    ax.set_yscale("log"); ax.set_ylabel("tool-call duration (s, log)")
    ax.set_title("Per-call wall-clock duration across tasks (trajectory execution_time)", fontsize=11)
    ax.grid(axis="y", alpha=.3)
    fig.tight_layout(); fig.savefig(f"{OUTD}/plots/cross_task_calldur{SUFFIX}.png", dpi=135, bbox_inches="tight")
    print(f"wrote cross_task_calldur{SUFFIX}.png")
