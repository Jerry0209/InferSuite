#!/usr/bin/env python3
"""Fig 6: exit-time receipts (taskstats) on the three strict instances.
Per task: the l3 window truth, receipts aggregated by OWNERSHIP (the l3 ontology),
receipts aggregated by PROCESS (the mechanism ontology). Coverage annotated."""
import os, sys, io, collections, importlib.util
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("rr", f"{HERE}/receipt_report.py")
_o = sys.stdout; sys.stdout = io.StringIO()
rr = importlib.util.module_from_spec(spec); spec.loader.exec_module(rr)
sys.stdout = _o
ca, pr = rr.ca, rr.pr

SURFACE, INK, INK2 = "#fcfcfb", "#0b0b0b", "#52514e"
CAT = {"BUILD": "#eda100", "TEST": "#1baf7a", "SEARCH": "#2a78d6"}
K = ("BUILD", "TEST", "SEARCH")
plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
                     "font.size": 9, "text.color": INK, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2,
                     "axes.edgecolor": "#d8d6cf", "axes.linewidth": 0.8})


def coarse_shares(counter):
    cc = collections.Counter()
    for k, v in counter.items():
        c = ca.COARSE.get(k)
        if c:
            cc[c] += v
    s = sum(cc.values())
    return {k: 100 * v / s for k, v in cc.items()} if s else {}


CASES = [("glm_replay_swe_jqlang-X2681", "jq-2681", "C · class B", "jqlang"),
         ("glm_replay_swe_tokio-rs-X6551", "tokio-6551", "Rust · class A", "tokio-rs"),
         ("glm_replay_swe_php-cs-fixer-X7523", "php-cs-fixer-7523", "PHP · class I", "php-cs-fixer")]
rows = []
for d, name, cls, l3 in CASES:
    rd = f"{rr.ML}/data/{d}/run_1"
    a = rr.analyze(rd)
    rows.append((name, cls, pr.l3_truth(l3),
                 coarse_shares(a["own"] + a["alive_cs"]),
                 coarse_shares(a["cs"] + a["alive_cs"]),
                 100 * (a["receipts_in"] + a["alive"]) / max(a["fence"], 1e-9)))

fig, ax = plt.subplots(figsize=(9.8, 5.6))
ax.set_xlim(0, 100)
H, GRP = 0.26, 1.35
tr = ax.get_yaxis_transform()


def stack(y, sh):
    x = 0.0
    px = 100.0 / max(ax.get_window_extent().width, 1)
    vis = [k for k in K if sh.get(k, 0) > 0]
    for k in K:
        v = sh.get(k, 0)
        if v <= 0:
            continue
        w = v - (2.0 * px if k != vis[-1] else 0)
        ax.barh(y, max(w, 0.01), left=x, height=H, color=CAT[k], edgecolor="none", zorder=3)
        if v >= 9:
            ax.text(x + v / 2, y, f"{v:.0f}", ha="center", va="center", fontsize=7.5,
                    color="white", zorder=4)
        x += v


for i, (name, cls, t, own, proc, cov) in enumerate(rows):
    y0 = -i * GRP
    for j, (lbl, d, bold) in enumerate((("window truth (P7)", t, False),
                                        ("receipts · ownership", own, True),
                                        ("receipts · process", proc, True))):
        y = y0 + (0.30 - 0.30 * j)
        stack(y, d)
        ax.text(-0.035, y, lbl, ha="right", va="center", fontsize=7.5,
                color=INK if bold else INK2, transform=tr,
                fontweight="bold" if bold else "normal")
    ax.text(-0.40, y0 + 0.42, name, ha="left", va="bottom", fontsize=8.5, color=INK,
            transform=tr, fontweight="bold")
    ax.text(-0.40, y0 + 0.13, cls, ha="left", va="center", fontsize=7.5, color=INK2,
            transform=tr)
    ax.text(1.012, y0, f"receipts cover\n{cov:.0f}% of fence", ha="left", va="center",
            fontsize=7.5, color=INK2, transform=tr, linespacing=1.5)

ax.set_ylim(-len(rows) * GRP + 0.55, 0.72)
ax.set_yticks([])
ax.set_xticks([0, 25, 50, 75, 100])
ax.set_xticklabels(["0", "25", "50", "75", "100%"])
ax.set_xlabel("share of tool-fence CPU")
for s in ("left", "right", "top"):
    ax.spines[s].set_visible(False)
ax.tick_params(axis="y", length=0)
ax.set_title("Exit receipts: one fence, two ontologies", fontsize=12, color=INK,
             loc="left", pad=26)
ax.text(0, 1.075, "~97% of every fence accounted; owner view matches the window truth, "
        "process view shows the physics", transform=ax.transAxes, fontsize=8.5, color=INK2)
ax.set_ylim(-len(rows) * GRP + 0.55, 0.95)
ax.legend(handles=[Patch(facecolor=CAT[k], label=k.lower()) for k in K],
          loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=3, frameon=False,
          fontsize=8.5, handlelength=1.1, handleheight=0.9, columnspacing=2.0)
fig.subplots_adjust(left=0.315, right=0.85, top=0.83, bottom=0.20)
fig.savefig(f"{HERE}/fig6_receipts.png", dpi=170)
print("wrote fig6")
