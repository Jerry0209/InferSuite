#!/usr/bin/env python3
"""Fig 5: does per-PID CPU sampling recover the composition that presence-weighting lost?
Three bars per task: instruction-weighted truth, per-PID measurement, presence-weighted estimate.
"""
import os, sys, collections, importlib.util
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("pr", f"{HERE}/pilot_report.py")
_o = sys.stdout; sys.stdout = open(os.devnull, "w")
pr = importlib.util.module_from_spec(spec); spec.loader.exec_module(pr)
sys.stdout = _o
ca = pr.ca
ML = pr.ML

SURFACE, INK, INK2, INK3 = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8880"
CAT = {"BUILD": "#eda100", "TEST": "#1baf7a", "SEARCH": "#2a78d6"}
K = ("BUILD", "TEST", "SEARCH")
plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
                     "font.size": 9, "text.color": INK, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2,
                     "axes.edgecolor": "#d8d6cf", "axes.linewidth": 0.8})

# (dir, label, language, l3 task for truth, strict?)
CASES = [("glm_replay_swe_php-cs-fixer-L3t7523", "php-cs-fixer-7523", "PHP", "php-cs-fixer", True),
         ("glm_replay_swe_google-t1100", "gson-1100", "Java", "google", False),
         ("glm_replay_swe_php-cs-fixer-t7875", "php-cs-fixer-7875", "PHP", "php-cs-fixer", False),
         ("glm_replay_swe_tokio-rs-t6838", "tokio-6838", "Rust", "tokio-rs", False)]

rows = []
for d, name, lang, l3, strict in CASES:
    rd = f"{ML}/data/{d}/run_1"
    if not os.path.exists(f"{rd}/DONE"):
        continue
    cs, attr, fence = pr.perpid_mix(rd)
    est = pr.coarse({k: v for k, v in (ca.episode(rd) or ({}, 0, 0))[0].items()})
    rows.append((name, lang, strict, pr.l3_truth(l3), pr.coarse(cs), est,
                 100 * attr / max(fence, 1e-9)))

fig, ax = plt.subplots(figsize=(9.8, 1.15 + 1.35 * len(rows)))
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


for i, (name, lang, strict, t, p, e, cov) in enumerate(rows):
    y0 = -i * GRP
    for j, (lbl, d) in enumerate((("l3 truth", t), ("per-PID", p), ("presence-est", e))):
        y = y0 + (0.30 - 0.30 * j)
        stack(y, d)
        ax.text(-0.035, y, lbl, ha="right", va="center", fontsize=7.5,
                color=INK if lbl == "per-PID" else INK2, transform=tr,
                fontweight="bold" if lbl == "per-PID" else "normal")
    ax.text(-0.395, y0 + 0.10, f"{name}   {lang}", ha="left", va="center", fontsize=8.5,
            color=INK, transform=tr)
    ax.text(-0.395, y0 - 0.12, "SAME instance" if strict else "different instance —\nnot a valid comparison",
            ha="left", va="center", fontsize=7.5, transform=tr, linespacing=1.4,
            color="#0e7d57" if strict else "#c0322f")
    ax.text(1.012, y0, f"PID coverage\n{cov:.0f}% of fence", ha="left", va="center",
            fontsize=7.5, color=INK2, transform=tr, linespacing=1.5)

ax.set_ylim(-len(rows) * GRP + 0.55, 0.72)
ax.set_yticks([])
ax.set_xticks([0, 25, 50, 75, 100])
ax.set_xticklabels(["0", "25", "50", "75", "100%"])
ax.set_xlabel("share of tool-fence CPU")
for s in ("left", "right", "top"):
    ax.spines[s].set_visible(False)
ax.tick_params(axis="y", length=0)
ax.set_title("Per-PID CPU sampling recovers the composition", fontsize=12, color=INK,
             loc="left", pad=26)
ax.text(0, 1.0 + 0.055 * (4.0 / max(len(rows), 1)),
        "measuring consumption instead of presence puts the estimate back on the truth",
        transform=ax.transAxes, fontsize=8.5, color=INK2)
ax.legend(handles=[Patch(facecolor=CAT[k], label=k.lower()) for k in K],
          loc="upper center", bbox_to_anchor=(0.5, -0.13 - 0.02 * len(rows)), ncol=3,
          frameon=False, fontsize=8.5, handlelength=1.1, handleheight=0.9, columnspacing=2.0)
fig.subplots_adjust(left=0.305, right=0.845, top=0.845, bottom=0.20)
fig.savefig(f"{HERE}/fig5_perpid_vs_truth.png", dpi=170)
for name, lang, strict, t, p, e, cov in rows:
    err_p = max(abs(p.get(k, 0) - t.get(k, 0)) for k in K)
    err_e = max(abs(e.get(k, 0) - t.get(k, 0)) for k in K)
    print(f"{name:<20}{lang:<7}cov={cov:5.1f}%  worst-err per-PID={err_p:5.1f}pt  "
          f"presence={err_e:5.1f}pt  {'STRICT' if strict else 'sibling'}")
