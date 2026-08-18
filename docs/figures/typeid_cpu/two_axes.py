#!/usr/bin/env python3
"""Exploratory figures for the code review of the two-axis classification protocol.

Fig 1  same episodes, two weightings: action-count mix vs instruction-weighted fence mix
Fig 2  Axis 2 has no variance -- 225 typeid episodes in the S/T plane
Fig 3  magnitude does not separate by mechanism class

Data:  local_agents/ML_multiling/data/l3_study/all_windows_*.csv  (instruction weights)
       local_agents/ML_multiling/data/glm_swe_*/run_*/traj/       (action counts)
       local_agents/ML_typeid/typing_ledger.tsv                   (225 live episodes)
NOTE: run with this machine's system python3 (no infersuite-full env on the typeid box).
"""
import csv, glob, os, types, collections
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np

REPO = "/home/network/InferSuite-Jerry"
OUT = os.path.dirname(os.path.abspath(__file__))

# ---- palette (dataviz reference instance, categorical slots 1-4, fixed order) ----
SURFACE = "#fcfcfb"
INK, INK2, INK3 = "#0b0b0b", "#52514e", "#8a8880"
CAT = {"S": "#2a78d6", "E": "#eb6834", "T": "#1baf7a", "B": "#eda100"}
NAME = {"S": "search / read", "E": "edit", "T": "verify (test + repro + app-under-test)",
        "B": "build / deps"}
GAP = 2.0  # px surface gap between stacked segments

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "font.size": 9, "text.color": INK, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2,
    "axes.edgecolor": "#d8d6cf", "axes.linewidth": 0.8,
})


def stack_h(ax, y, shares, height, labels=True):
    """One horizontal stacked bar with a 2px surface gap between segments."""
    x = 0.0
    fig = ax.figure
    # convert 2px to data units on the x axis
    bb = ax.get_window_extent()
    px = (ax.get_xlim()[1] - ax.get_xlim()[0]) / max(bb.width, 1)
    gap = GAP * px
    segs = [(k, shares.get(k, 0.0)) for k in "SETB"]
    vis = [k for k, v in segs if v > 0]
    for i, (k, v) in enumerate(segs):
        if v <= 0:
            continue
        w = v - (gap if k != vis[-1] else 0)
        ax.barh(y, max(w, 0.01), left=x, height=height, color=CAT[k],
                edgecolor="none", zorder=3)
        if labels and v >= 8:
            ax.text(x + v / 2, y, f"{v:.0f}", ha="center", va="center",
                    fontsize=7.5, color="white", zorder=4)
        x += v


# =====================================================================================
# Fig 1 -- two weightings of the same episodes
# =====================================================================================
def tag_to_class(tag):
    """window command-tag -> the Axis-2 vocabulary. `*-other` is the language runtime
    doing verification payload (rubocop's own binary under test; the agent's python
    repro scripts) -> T, same as behavior_classify's repro-script rule."""
    if tag in ("compile", "pkg/build", "link"):
        return "B"
    if tag.startswith("tests(") or tag.endswith("-other"):
        return "T"
    if tag in ("shell", "agent-tool", "git", "search"):
        return "S"
    return None  # idle / harness -> outside the tool payload


def cpu_mix(task):
    f = f"{REPO}/local_agents/ML_multiling/data/l3_study/all_windows_{task}.csv"
    seen, tot, raw = set(), collections.Counter(), collections.Counter()
    for r in csv.DictReader(open(f)):
        if r["fence"] != "tool":
            continue
        k = (r["group"], r["run"], r["win"])
        if k in seen:
            continue
        seen.add(k)
        raw[r["tag"]] += int(r["instructions"])
        c = tag_to_class(r["tag"])
        if c:
            tot[c] += int(r["instructions"])
    s = sum(tot.values())
    return {k: 100.0 * v / s for k, v in tot.items()}, s, raw


src = open(f"{REPO}/local_agents/kit/replay/behavior_classify.py").read().replace(
    'REPO = "/home/thu/InferSuite"', f'REPO = "{REPO}"')
bc = types.ModuleType("bc")
exec(compile(src.split("if __name__")[0], "bc", "exec"), bc.__dict__)


def act_mix(short):
    d = f"{REPO}/local_agents/ML_multiling/data/glm_swe_{short}"
    tr = [p for p in sorted(glob.glob(f"{d}/run_*/traj/*/*.traj"))
          if not p.endswith(".local.traj")]
    if not tr:
        return None, 0
    lab, c, tot = bc.episode_label(tr[0])
    sh, _ = bc._shares(c)
    return sh, tot


TASKS = [("jqlang", "jq", "C"), ("google", "gson", "Java"), ("tokio-rs", "tokio", "Rust"),
         ("gin-gonic", "gin", "Go"), ("rubocop", "rubocop", "Ruby"),
         ("vuejs", "vue", "TypeScript"), ("php-cs-fixer", "php-cs-fixer", "PHP"),
         ("phpoffice-bT", "phpspreadsheet", "PHP")]

rows = []
for short, nice, lang in TASKS:
    a, n = act_mix(short)
    c, ginstr, raw = cpu_mix(short)
    if a is None:
        continue
    rows.append((nice, lang, a, n, c, ginstr / 1e9, raw))

print(f"{'task':<16}{'lang':<11}{'n_act':>6}{'Ginstr':>9}   actions S/E/T/B      CPU S/E/T/B")
for nice, lang, a, n, c, g, raw in rows:
    print(f"{nice:<16}{lang:<11}{n:>6}{g:>9.0f}   "
          + " ".join(f"{k}{a.get(k,0):>3.0f}" for k in "SETB") + "      "
          + " ".join(f"{k}{c.get(k,0):>3.0f}" for k in "SETB"))

fig, ax = plt.subplots(figsize=(9.8, 6.6))
ax.set_xlim(0, 100)
H, PAIR = 0.34, 0.95
tr = ax.get_yaxis_transform()          # x in axes fraction, y in data
for i, (nice, lang, a, n, c, g, raw) in enumerate(rows):
    y0 = -i * PAIR
    stack_h(ax, y0 + 0.20, a, H)
    stack_h(ax, y0 - 0.20, c, H)
    ax.text(-0.030, y0 + 0.20, "actions", ha="right", va="center", fontsize=7.5,
            color=INK2, transform=tr)
    ax.text(-0.030, y0 - 0.20, "CPU", ha="right", va="center", fontsize=7.5,
            color=INK2, transform=tr)
    ax.text(-0.255, y0, f"{nice}\n{lang}", ha="left", va="center", fontsize=8.5,
            color=INK, transform=tr, linespacing=1.5)
    ax.text(1.012, y0 + 0.20, f"{n} actions", ha="left", va="center", fontsize=7,
            color=INK3, transform=tr)
    ax.text(1.012, y0 - 0.20, f"{g:,.0f} Ginstr", ha="left", va="center", fontsize=7,
            color=INK3, transform=tr)

ax.set_ylim(-len(rows) * PAIR + 0.4, 0.75)
ax.set_yticks([])
ax.set_xticks([0, 25, 50, 75, 100])
ax.set_xticklabels(["0", "25", "50", "75", "100%"])
ax.set_xlabel("share of the episode  (% of classified actions  /  % of tool-fence instructions)")
for s in ("left", "right", "top"):
    ax.spines[s].set_visible(False)
ax.tick_params(axis="y", length=0)
ax.set_title("Same episodes, two weightings", fontsize=12, color=INK, loc="left", pad=26)
ax.text(0, 1.045, "counting the agent's actions and counting the CPU they cause give "
        "opposite answers", transform=ax.transAxes, fontsize=8.5, color=INK2)
ax.legend(handles=[Patch(facecolor=CAT[k], label=NAME[k]) for k in "SETB"],
          loc="upper center", bbox_to_anchor=(0.5, -0.10), ncol=4, frameon=False,
          fontsize=8, handlelength=1.1, handleheight=0.9, columnspacing=1.6)
fig.subplots_adjust(left=0.215, right=0.855, top=0.86, bottom=0.15)
fig.savefig(f"{OUT}/fig1_two_weightings.png", dpi=170)
print("wrote fig1")

# =====================================================================================
# Fig 2 -- Axis 2 has no variance (225 live typeid episodes)
# =====================================================================================
led = [r for r in csv.DictReader(open(f"{REPO}/local_agents/ML_typeid/typing_ledger.tsv"),
                                 delimiter="\t") if r["status"] == "classified"]


def parse_mix(s):
    d = {}
    for part in s.split():
        k, v = part.split("=")
        d[k] = float(v.rstrip("%"))
    return d


S = np.array([parse_mix(r["mix"]).get("S", 0) for r in led])
T = np.array([parse_mix(r["mix"]).get("T", 0) for r in led])
LAB = [r["realized"] for r in led]
print(f"\nfig2: n={len(led)}  labels={collections.Counter(LAB)}")

fig, ax = plt.subplots(figsize=(7.4, 6.4))
ax.set_xlim(0, 100)
ax.set_ylim(0, 100)
# region where T leads S by >= MARGIN -> "test-dominated" is only below this line
ax.fill_between([0, 100], [10, 110], [100, 100], color="#1baf7a", alpha=0.07, zorder=0)
ax.fill_between([0, 100], [-10, 90], [10, 110], color=INK3, alpha=0.06, zorder=0)
ax.plot([0, 90], [10, 100], color=INK3, lw=0.9, ls="--", zorder=1)
ax.plot([10, 100], [0, 90], color=INK3, lw=0.9, ls="--", zorder=1)
rng = np.random.default_rng(7)
COLM = {"S": CAT["S"], "M": CAT["E"], "T": CAT["T"]}
for lab in ("S", "M", "T"):
    m = np.array([l == lab for l in LAB])
    if not m.any():
        continue
    ax.scatter(S[m] + rng.normal(0, .5, m.sum()), T[m] + rng.normal(0, .5, m.sum()),
               s=26, color=COLM[lab], alpha=.75, linewidths=.8, edgecolors=SURFACE,
               zorder=3, label=f"{lab}  (n={int(m.sum())})")
ax.text(72, 88, "test-dominated\nregion", fontsize=8.5, color="#0e7d57", ha="center")
ax.text(66, 62, "mixed (within 10 pt)", fontsize=8, color=INK3, ha="center", rotation=45)
ax.set_xlabel("search share of classified actions (%)")
ax.set_ylabel("verify share of classified actions (%)")
for s in ("right", "top"):
    ax.spines[s].set_visible(False)
ax.grid(True, color="#eceae3", lw=0.7, zorder=0)
ax.set_axisbelow(True)
ax.set_title("Axis 2 has no variance", fontsize=12, color=INK, loc="left", pad=26)
ax.text(0, 1.045, "225 live episodes, 9 languages, 35 repos — 215 land search-led, "
        "1 reaches test-dominated", transform=ax.transAxes, fontsize=8.5, color=INK2)
ax.legend(loc="upper right", frameon=False, fontsize=8.5, title="realized label",
          title_fontsize=8)
fig.subplots_adjust(left=0.11, right=0.97, top=0.86, bottom=0.10)
fig.savefig(f"{OUT}/fig2_axis2_collapse.png", dpi=170)
print("wrote fig2")

# =====================================================================================
# Fig 3 -- magnitude does not separate by mechanism class
# =====================================================================================
MECH_NAME = {"B": "B\nbuild-driver\nC / C++", "A": "A\nAOT-unified\nRust / Go",
             "J": "J\nJVM-unified\nJava", "I": "I\ninterpreted\nPHP / Ruby",
             "N": "N\nnode-transpile\nJS / TS"}
order = ["B", "A", "J", "I", "N"]
by = collections.defaultdict(list)
for r in led:
    try:
        v = float(r["tool_cs_corr"])
    except ValueError:
        continue
    if v > 0:
        by[r["mech"]].append(v)

fig, ax = plt.subplots(figsize=(8.2, 5.6))
rng = np.random.default_rng(3)
for i, m in enumerate(order):
    v = np.array(by[m])
    ax.scatter(i + rng.normal(0, .085, len(v)), v, s=22, color=CAT["S"], alpha=.5,
               linewidths=.7, edgecolors=SURFACE, zorder=3)
    med = np.median(v)
    ax.plot([i - .28, i + .28], [med, med], color=INK, lw=2.0, zorder=4,
            solid_capstyle="round")
    ax.text(i + .33, med, f"median {med:.0f}", fontsize=7.5, color=INK2, va="center")
    print(f"mech {m}: n={len(v):3d} median={med:7.1f} min={v.min():6.1f} "
          f"max={v.max():7.1f} spread={v.max()/max(v.min(),1e-9):.0f}x")

ax.axhline(20, color="#e34948", lw=1.1, ls="--", zorder=2)
ax.text(-0.55, 21.5, "STEP 5 stop gate: 20 core-s", fontsize=7.5, color="#e34948",
        ha="left", va="bottom")
ax.set_yscale("log")
ax.set_xticks(range(len(order)))
ax.set_xticklabels([MECH_NAME[m] for m in order], fontsize=8.5)
ax.set_xlim(-.6, 4.75)
ax.set_ylabel("corrected tool-fence CPU (core-seconds, log)")
for s in ("right", "top"):
    ax.spines[s].set_visible(False)
ax.grid(True, axis="y", color="#eceae3", lw=0.7, zorder=0)
ax.set_axisbelow(True)
ax.set_title("Magnitude does not separate by mechanism class", fontsize=12, color=INK,
             loc="left", pad=26)
ax.text(0, 1.055, "225 live episodes — every class spans two to three orders of "
        "magnitude and they overlap almost completely",
        transform=ax.transAxes, fontsize=8.5, color=INK2)
fig.subplots_adjust(left=0.10, right=0.98, top=0.85, bottom=0.16)
fig.savefig(f"{OUT}/fig3_magnitude.png", dpi=170)
print("wrote fig3")
