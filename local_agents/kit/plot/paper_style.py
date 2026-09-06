#!/usr/bin/env python3
"""paper_style.py — the ONE paper figure style (mentor spec 2026-08-31), matplotlib side.

The visual contract (identical to theme_paper.R; anchors: Hermes MICRO'22 Fig 9/12 and
Constable ISCA'24 Fig 11/13):
  - serif type: Linux Libertine O everywhere;
  - full black panel border, thin; the value axis TERMINATES EXACTLY at its outermost
    labeled tick (no expansion) — use exact_limits();
  - dotted light-grey major gridlines, behind the marks;
  - tick marks outward, visible outside the border;
  - every bar / stacked segment carries a thin black edge (BAR_EDGE);
  - AVG / MEDIAN aggregate groups sit on a grey band (band()) behind grid and bars, closed
    off by a solid black separator heavier than the language separators;
  - language groups separated by dotted grey lines (lang_sep()), lighter than the aggregate
    separator: aggregate boundary > language boundary > gridline;
  - legend on top, one row, no title, small square keys with black borders.
No chart may set these properties locally — import and use.
"""
import glob as _glob
import math

import matplotlib
from matplotlib import font_manager as _fm

for _f in _glob.glob("/usr/share/fonts/opentype/linux-libertine/LinLibertine_R*.otf"):
    try:
        _fm.fontManager.addfont(_f)
    except Exception:
        pass

SERIF = "Linux Libertine O"
GRID = "#cccccc"          # dotted major grid
LANG_SEP = "#666666"      # dotted language separator
BAND = "#ebebeb"          # aggregate band fill (grey90)
BAR_EDGE = dict(edgecolor="black", linewidth=0.5)       # every bar / segment
BORDER_LW = 0.8           # panel border (pt)
TICK_LW = 0.6
AGG_SEP_LW = 0.9          # solid black aggregate boundary

RC = {
    "font.family": SERIF,
    "font.serif": [SERIF, "Times New Roman", "DejaVu Serif"],
    "mathtext.fontset": "custom", "mathtext.rm": SERIF, "mathtext.it": f"{SERIF}:italic",
    "figure.dpi": 150, "savefig.dpi": 300,
    "axes.linewidth": BORDER_LW, "axes.edgecolor": "black",
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.5, "grid.linestyle": ":",
    "grid.alpha": 1.0, "axes.axisbelow": True,
    "xtick.direction": "out", "ytick.direction": "out",
    "xtick.major.width": TICK_LW, "ytick.major.width": TICK_LW,
    "xtick.major.size": 3.0, "ytick.major.size": 3.0,
    "xtick.labelsize": 8, "ytick.labelsize": 8,
    "axes.labelsize": 10, "axes.titlesize": 9.5,
    "legend.fontsize": 9, "legend.frameon": False,
}


def apply():
    matplotlib.rcParams.update(RC)


def exact_limits(ax, axis, lo, hi, step):
    """Value axis ends ON its outermost labeled tick (the reference's border rule)."""
    ticks = [lo + i * step for i in range(int(round((hi - lo) / step)) + 1)]
    if axis == "x":
        ax.set_xticks(ticks); ax.set_xlim(lo, hi)
    else:
        ax.set_yticks(ticks); ax.set_ylim(lo, hi)
    return ticks


def cap_for(vmax, step, headroom=1.22):
    """Smallest multiple of step that leaves room for an end-of-bar label."""
    return step * math.ceil(vmax * headroom / step)


def band(ax, lo, hi, horizontal=True):
    """Grey aggregate band UNDER gridlines and bars (zorder 0; grid draws at 0.5)."""
    fn = ax.axhspan if horizontal else ax.axvspan
    fn(lo, hi, color=BAND, zorder=0, linewidth=0)


def agg_sep(ax, pos, horizontal=True):
    (ax.axhline if horizontal else ax.axvline)(pos, color="black",
                                               linewidth=AGG_SEP_LW, zorder=2.5)


def lang_sep(ax, pos, horizontal=True):
    (ax.axhline if horizontal else ax.axvline)(pos, color=LANG_SEP, linewidth=0.5,
                                               linestyle=(0, (1, 2.2)), zorder=2.5)


def top_legend(fig, handles, labels, y=1.045, ncol=None, fontsize=8.5):
    for h in handles:
        try:
            h.set_edgecolor("black"); h.set_linewidth(0.5)
        except AttributeError:
            pass
    # centre over the PANEL area, not the canvas: y tick labels / row annotations make the
    # canvas asymmetric, so anchor at the midpoint of the axes' union (finalize layout first)
    try:
        fig.canvas.draw()
        boxes = [ax.get_position() for ax in fig.axes]
        cx = (min(b.x0 for b in boxes) + max(b.x1 for b in boxes)) / 2
    except Exception:
        cx = 0.5
    return fig.legend(handles, labels, ncol=ncol or len(labels), loc="upper center",
                      bbox_to_anchor=(cx, y), frameon=False, fontsize=fontsize,
                      handlelength=1.0, handleheight=1.0, columnspacing=1.4)


def assert_exact(ax, axis="x"):
    """Verification hook: the axis limit must equal the outermost tick (no expansion)."""
    ticks = ax.get_xticks() if axis == "x" else ax.get_yticks()
    lim = ax.get_xlim() if axis == "x" else ax.get_ylim()
    vis = [t for t in ticks if lim[0] - 1e-9 <= t <= lim[1] + 1e-9]
    assert vis and abs(vis[-1] - lim[1]) < 1e-9 and abs(vis[0] - lim[0]) < 1e-9, \
        f"axis {axis}: limits {lim} do not terminate on the outermost ticks {vis}"
