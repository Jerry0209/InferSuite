#!/usr/bin/env python3
"""Fig 4: can the CPU-by-process axis be recovered from the typeid instruments?
Ground truth = instruction-weighted dedicated-group window tags (P7 replays).
Estimate     = 2 Hz argv presence x exact cgroup CPU, split per observed PID.
"""
import csv, glob, os, collections, importlib.util, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("ca", f"{HERE}/cpu_axis.py")
ca = importlib.util.module_from_spec(spec)
_o = sys.stdout; sys.stdout = open(os.devnull, "w")
spec.loader.exec_module(ca); sys.stdout = _o

REPO = "/home/network/InferSuite-Jerry"
L3 = f"{REPO}/local_agents/ML_multiling/data/l3_study"
SURFACE, INK, INK2, INK3 = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8880"
CAT = {"BUILD": "#eda100", "TEST": "#1baf7a", "SEARCH": "#2a78d6"}
plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
                     "font.size": 9, "text.color": INK, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2,
                     "axes.edgecolor": "#d8d6cf", "axes.linewidth": 0.8})
L3C = {"compile": "BUILD", "pkg/build": "BUILD", "link": "BUILD",
       "shell": "SEARCH", "agent-tool": "SEARCH", "git": "SEARCH", "search": "SEARCH"}


def l3_mix(task):
    seen, tot = set(), collections.Counter()
    for r in csv.DictReader(open(f"{L3}/all_windows_{task}.csv")):
        if r["fence"] != "tool":
            continue
        k = (r["group"], r["run"], r["win"])
        if k in seen:
            continue
        seen.add(k)
        t = r["tag"]; c = L3C.get(t)
        if c is None:
            c = "TEST" if (t.startswith("tests(") or t.endswith("-other")) else None
        if c:
            tot[c] += int(r["instructions"])
    s = sum(tot.values())
    return {k: 100 * v / s for k, v in tot.items()}


def est_mix(task):
    agg = collections.Counter()
    for d in sorted(glob.glob(f"{REPO}/local_agents/ML_multiling/data/"
                              f"glm_replay_swe_{task}/run_*")):
        r = ca.episode(d)
        if r:
            for k, v in r[0].items():
                c = ca.COARSE.get(k)
                if c:
                    agg[c] += v
    s = sum(agg.values())
    return {k: 100 * v / s for k, v in agg.items()} if s else {}


TASKS = [("jqlang", "jq", "C"), ("prometheus", "prometheus", "Go"),
         ("google", "gson", "Java"), ("tokio-rs", "tokio", "Rust"),
         ("gin-gonic", "gin", "Go"), ("rubocop", "rubocop", "Ruby"),
         ("vuejs", "vue", "TypeScript"), ("php-cs-fixer", "php-cs-fixer", "PHP"),
         ("phpoffice-bT", "phpspreadsheet", "PHP")]
K = ("BUILD", "TEST", "SEARCH")
rows = []
for short, nice, lang in TASKS:
    g, e = l3_mix(short), est_mix(short)
    if g and e:
        rows.append((nice, lang, g, e))

fig, ax = plt.subplots(figsize=(9.8, 6.9))
ax.set_xlim(0, 100)
H, PAIR = 0.34, 0.95
tr = ax.get_yaxis_transform()
GAPPX = 2.0


def stack(y, sh):
    x = 0.0
    px = 100.0 / max(ax.get_window_extent().width, 1)
    vis = [k for k in K if sh.get(k, 0) > 0]
    for k in K:
        v = sh.get(k, 0)
        if v <= 0:
            continue
        w = v - (GAPPX * px if k != vis[-1] else 0)
        ax.barh(y, max(w, 0.01), left=x, height=H, color=CAT[k], edgecolor="none", zorder=3)
        if v >= 9:
            ax.text(x + v / 2, y, f"{v:.0f}", ha="center", va="center", fontsize=7.5,
                    color="white", zorder=4)
        x += v


nmatch = 0
for i, (nice, lang, g, e) in enumerate(rows):
    y0 = -i * PAIR
    stack(y0 + 0.20, g)
    stack(y0 - 0.20, e)
    gl, el = max(g, key=g.get), max(e, key=e.get)
    nmatch += gl == el
    ax.text(-0.030, y0 + 0.20, "truth", ha="right", va="center", fontsize=7.5,
            color=INK2, transform=tr)
    ax.text(-0.030, y0 - 0.20, "estimate", ha="right", va="center", fontsize=7.5,
            color=INK2, transform=tr)
    ax.text(-0.265, y0, f"{nice}\n{lang}", ha="left", va="center", fontsize=8.5,
            color=INK, transform=tr, linespacing=1.5)
    ok = gl == el
    ax.text(1.012, y0, "leader kept" if ok else "LEADER FLIPS", ha="left", va="center",
            fontsize=7.5, color="#0e7d57" if ok else "#c0322f", transform=tr)

ax.set_ylim(-len(rows) * PAIR + 0.4, 0.75)
ax.set_yticks([])
ax.set_xticks([0, 25, 50, 75, 100])
ax.set_xticklabels(["0", "25", "50", "75", "100%"])
ax.set_xlabel("share of tool-fence CPU  (truth = instructions  /  estimate = core-seconds)")
for s in ("left", "right", "top"):
    ax.spines[s].set_visible(False)
ax.tick_params(axis="y", length=0)
ax.set_title("The CPU-by-process axis cannot be recovered post hoc", fontsize=12,
             color=INK, loc="left", pad=26)
ax.text(0, 1.045, f"2 Hz argv presence x exact cgroup CPU keeps the leader on only "
        f"{nmatch} of {len(rows)} — search is inflated on every task",
        transform=ax.transAxes, fontsize=8.5, color=INK2)
ax.legend(handles=[Patch(facecolor=CAT[k], label=k.lower()) for k in K],
          loc="upper center", bbox_to_anchor=(0.5, -0.095), ncol=3, frameon=False,
          fontsize=8.5, handlelength=1.1, handleheight=0.9, columnspacing=2.0)
fig.subplots_adjust(left=0.225, right=0.845, top=0.855, bottom=0.145)
fig.savefig(f"{HERE}/fig4_estimator_vs_truth.png", dpi=170)
print(f"leader agreement {nmatch}/{len(rows)}")
for nice, lang, g, e in rows:
    print(f"{nice:<16}truth S={g.get('SEARCH',0):5.1f}%   est S={e.get('SEARCH',0):5.1f}%"
          f"   inflation x{e.get('SEARCH',0)/max(g.get('SEARCH',0.01),0.01):.1f}")
