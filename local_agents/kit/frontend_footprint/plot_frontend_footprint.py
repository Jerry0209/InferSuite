#!/usr/bin/env python3
"""plot_frontend_footprint.py — one violin per headline front-end metric, from long CSVs only.

  ~/miniforge3/envs/infersuite-full/bin/python3 plot_frontend_footprint.py CSV [CSV ...]
        [--out DIR] [--group subgroup|family] [--color FAMILY=#hex ...] [--fmt png[,pdf]]

Each CSV has the columns workload,family,subgroup,metric,value[,analyzer_sha,period,...]
(aggregate.py's frontend_footprint_rows_long.csv; the Server and Agentic CSVs use the same
schema, extra columns are ignored). Hue = family (lab convention: SPEC blue, Server green,
Agentic red); lightness = subgroup within the family. Footprint and unique branches are drawn on
a log axis. Titles are short; the definitions live in the MANIFEST next to the CSV.
"""
import argparse
import collections
import csv
import math
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter  # noqa: E402

# metric, title, y label, scale factor, log axis
HEADLINE = [
    ("footprint_bytes", "Instruction footprint", "KB (sampled lower bound)", 1e-3, True),
    ("unique_taken_branches", "Unique taken branches", "count (sampled lower bound)", 1.0, True),
]
# metric 3 in three forms (literal = sampled lower bound; weff, ge1pct = frequency weighted), each for
# all near taken branches, returns excluded, and indirect branches only. Absent metrics are skipped.
for _key, _form, _ylab in (("wavg_targets_{}", "Distinct targets", "targets (sampled lower bound)"),
                           ("weff_targets_{}", "Effective targets", "inverse Simpson"),
                           ("wavg_targets_ge1pct_{}", "Targets \u2265 1 %", "targets \u2265 1 % of executions")):
    for _scope, _what in (("all", "per taken branch"), ("noret", "per taken branch, no returns"),
                          ("indirect", "per indirect branch")):
        HEADLINE.append((_key.format(_scope), f"{_form} {_what}", _ylab, 1.0, False))
# lab palette (local_agents/kit/plot/theme_paper.R + plot_paper_agg_compact_server.R): dark, light
SIDE_COLORS = {"SPEC": ("#2166ac", "#92c5de"), "Server": ("#1a9850", "#a6d96a"), "Agentic": ("#b2182b", "#f4a582")}
SIDE_ORDER = ["SPEC", "Server", "Agentic"]
SUBGROUP_ORDER = ["SPEC-int", "SPEC-fp"]
INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"


def side_of(family):
    f = family.lower()
    return "SPEC" if f.startswith("spec") else "Agentic" if f.startswith("agentic") else "Server"


def blend(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def read(paths):
    data = collections.defaultdict(dict)  # (family, subgroup) -> {metric: {workload: value}}
    seen, shas, periods = {}, collections.defaultdict(set), collections.defaultdict(set)
    for p in paths:
        with open(p, newline="") as f:
            rd = csv.DictReader(f)
            miss = {"workload", "family", "subgroup", "metric", "value"} - set(rd.fieldnames or [])
            if miss:
                sys.exit(f"plot: {p} lacks columns {sorted(miss)}")
            for r in rd:
                key = (r["family"], r["workload"], r["metric"])
                if key in seen:
                    sys.exit(f"plot: {key} appears in both {seen[key]} and {p}")
                seen[key] = p
                if r.get("analyzer_sha"):
                    shas[r["analyzer_sha"]].add(r["family"])
                if r.get("period"):
                    periods[r["period"]].add(r["family"])
                if r["value"] == "":
                    continue
                data[(r["family"], r["subgroup"])].setdefault(r["metric"], {})[r["workload"]] = float(r["value"])
    return data, shas, periods


def log_ticks(lo, hi):
    """Major ticks in log10 space: decades if >= 2 fit, else the 1-2-5 series."""
    k0, k1 = math.floor(lo), math.ceil(hi)
    dec = [k for k in range(k0, k1 + 1) if lo - 1e-9 <= k <= hi + 1e-9]
    if len(dec) >= 2:
        return dec
    return [k + math.log10(m) for k in range(k0, k1 + 1) for m in (1, 2, 5)
            if lo - 1e-9 <= k + math.log10(m) <= hi + 1e-9]


def human(y, _pos=None):
    v = 10 ** y
    return f"{v:,.0f}" if v >= 1 else f"{v:.2g}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("csv", nargs="+")
    ap.add_argument("--out", default="plots")
    ap.add_argument("--group", choices=("subgroup", "family"), default="subgroup",
                    help="one violin per family x subgroup (default) or per family")
    ap.add_argument("--color", action="append", default=[], metavar="FAMILY=#hex",
                    help="override a family's dark hue (its light variant is derived)")
    ap.add_argument("--fmt", default="png")
    a = ap.parse_args()
    data, shas, periods = read(a.csv)
    if not data:
        print("plot: no rows with values; nothing to plot")
        return 0
    if len(periods) > 1:
        print(f"plot: WARNING several sampling periods in the input: {dict(periods)}; the contract needs one", file=sys.stderr)
    if len(shas) > 1:
        print(f"plot: WARNING several analyzer SHAs in the input: {dict(shas)}; the contract needs one", file=sys.stderr)
    override = dict(c.split("=", 1) for c in a.color)

    if a.group == "family":  # pool the subgroups
        pooled = collections.defaultdict(dict)
        for (fam, _sub), ms in data.items():
            for m, vals in ms.items():
                pooled[(fam, "")].setdefault(m, {}).update(vals)
        data = pooled
    fams = sorted({f for f, _ in data}, key=lambda f: (SIDE_ORDER.index(side_of(f)), f))
    groups, colors = [], {}
    for f in fams:
        subs = sorted({s for ff, s in data if ff == f},
                      key=lambda s: (SUBGROUP_ORDER.index(s) if s in SUBGROUP_ORDER else len(SUBGROUP_ORDER), s))
        dark, light = SIDE_COLORS[side_of(f)]
        if f in override:
            dark, light = override[f], blend(override[f], "#ffffff", 0.55)
        for i, s in enumerate(subs):
            groups.append((f, s))
            colors[(f, s)] = dark if len(subs) == 1 else blend(dark, light, i / (len(subs) - 1))
    multi_family = len(fams) > 1

    os.makedirs(a.out, exist_ok=True)
    rng = np.random.default_rng(0)
    written = []
    print(f"{'metric':34s} {'group':24s} {'n':>3s} {'median':>12s} {'min':>12s} {'max':>12s}")
    for metric, title, ylab, k, logy in HEADLINE:
        cols = [(g, np.array(sorted(data[g].get(metric, {}).values())) * k) for g in groups]
        cols = [(g, v) for g, v in cols if len(v)]
        if not cols:
            print(f"plot: {metric} absent from the input; skipped")
            continue
        fig, ax = plt.subplots(figsize=(1.6 + 1.1 * len(cols), 3.4))
        for x, (g, v) in enumerate(cols):
            print(f"{metric:34s} {(g[0] + ' ' + g[1]).strip():24s} {len(v):3d} {np.median(v):12.4g} {v.min():12.4g} {v.max():12.4g}")
            y = np.log10(v) if logy else v
            if len(y) >= 3 and np.ptp(y) > 0:
                vp = ax.violinplot([y], positions=[x], widths=0.78, showextrema=False)
                for b in vp["bodies"]:
                    b.set_facecolor(colors[g])
                    b.set_edgecolor("black")
                    b.set_linewidth(0.3)
                    b.set_alpha(0.75)
            ax.scatter(x + rng.uniform(-0.2, 0.2, len(y)), y, s=9, color=INK2, alpha=0.7, linewidths=0, zorder=3)
            if len(y) >= 2:
                ax.boxplot([y], positions=[x], widths=0.12, whis=(5, 95), showcaps=False, showfliers=False,
                           patch_artist=True, zorder=4,
                           boxprops=dict(facecolor="white", edgecolor="#262626", linewidth=0.6),
                           whiskerprops=dict(color="#262626", linewidth=0.6),
                           medianprops=dict(color="black", linewidth=1.4))
            else:
                ax.hlines(y, x - 0.08, x + 0.08, color="black", linewidth=1.4, zorder=4)
            ax.scatter([x], [y.mean()], marker="D", s=16, facecolor="white", edgecolor="black", linewidths=0.6, zorder=5)
        ax.set_xticks(range(len(cols)))
        ax.set_xticklabels([f"{g[1] or g[0]}\n(n={len(v)})" for g, v in cols], color=INK2, fontsize=8.5)
        ax.set_xlim(-0.6, len(cols) - 0.4)
        if logy:
            ys = np.concatenate([np.log10(v) for _, v in cols])
            pad = max(0.08, 0.06 * (ys.max() - ys.min()))
            lo, hi = ys.min() - pad, ys.max() + pad
            ax.set_ylim(lo, hi)
            ax.yaxis.set_major_locator(FixedLocator(log_ticks(lo, hi)))
            ax.yaxis.set_major_formatter(FuncFormatter(human))
            ax.yaxis.set_minor_locator(FixedLocator([kk + math.log10(m) for kk in range(math.floor(lo), math.ceil(hi) + 1)
                                                     for m in range(2, 10)]))
            ax.yaxis.set_minor_formatter(NullFormatter())
        ax.set_title(title, color=INK, fontsize=10.5, loc="left")
        ax.set_ylabel(ylab, color=INK2, fontsize=8.5)
        ax.tick_params(axis="both", colors=MUTED, labelcolor=INK2, labelsize=8)
        ax.grid(axis="y", color=GRID, linewidth=0.5, zorder=0)
        ax.set_axisbelow(True)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        for sp in ("left", "bottom"):
            ax.spines[sp].set_color(AXIS)
        sides = list(dict.fromkeys(side_of(f) for f, _ in (g for g, _ in cols)))
        if multi_family and len(sides) > 1:  # hue = side; the x labels already name each family
            first = {sd: next(g for g, _ in cols if side_of(g[0]) == sd) for sd in sides}
            ax.legend(handles=[Patch(facecolor=colors[first[sd]], edgecolor="black", linewidth=0.3, label=sd)
                               for sd in sides],
                      frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(1.0, 1.0))
        fig.tight_layout()
        for ext in a.fmt.split(","):
            fig.savefig(os.path.join(a.out, f"{metric}.{ext}"), dpi=200)
        plt.close(fig)
        written.append(metric)
    print(f"plot: wrote {len(written)} figure(s) to {a.out}/ ({', '.join(written)}; {a.fmt})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
