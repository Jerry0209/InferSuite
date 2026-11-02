#!/usr/bin/env python3
"""plot_llc_dram_violins.py [OUT_DIR] — campaign vs cross-check, per-window distributions.

One figure per metric, two half-violins per benchmark:

  LLC   campaign  LLC_MPKI = mem_load_retired.l3_miss / inst      (data/, `cache` windows)
        re-run    longest_lat_cache.miss / inst                   (x_llc windows)
  DRAM  campaign  DRAM_read_GBs = offcore_requests.data_rd x 64 B (data/, `dram_bw` windows)
        re-run    IMC unc_m_cas_count.rd + .wr x 64 B, 0.5 s system-wide intervals inside
                  the episode, minus the idle rate measured just before it and minus the
                  capture stack's own traffic (same subtraction as xcheck_report.py)

nest inputs 1 and 2 were never run by the campaign, so they get a re-run half only.
Writes llc_violin.png, dram_violin.png, per_window.csv and summary.csv to OUT_DIR
(default infra/plots/llc_dram_compare). Needs matplotlib + numpy.
"""
from __future__ import annotations

import csv
import importlib
import json
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

KIT = os.path.dirname(os.path.abspath(__file__))
INFRA = os.path.dirname(KIT)
sys.path.insert(0, KIT)
from extract_metrics import parse_window  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(INFRA, "plots", "llc_dram_compare")
ORIG = os.path.join(INFRA, "data")
ROOTS = {"data_llc_xcheck": ["782.lbm_r", "749.fotonik3d_r", "765.roms_r", "772.marian_r",
                             "710.omnetpp_r", "767.nest_r"],
         "data_llc_xcheck_nest": ["767.nest_r@1", "767.nest_r@2"]}
LABEL = {"767.nest_r": "767.nest_r\n[input 0]", "767.nest_r@1": "767.nest_r\n[input 1]",
         "767.nest_r@2": "767.nest_r\n[input 2]"}
LINE = 64
BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def xr_for(root: str):
    """xcheck_report bound to one DATA_ROOT (it reads the root from argv at import)."""
    sys.argv = [sys.argv[0], os.path.join(INFRA, root)]
    import xcheck_report
    return importlib.reload(xcheck_report)


def x_llc_windows(d: str) -> list[float]:
    out = []
    for fn in sorted(os.listdir(d)):
        if re.match(r"^group_x_llc_w\d+\.txt$", fn):
            v, _ = parse_window(os.path.join(d, fn))
            if v.get("instructions"):
                out.append(1000 * v["longest_lat_cache.miss"] / v["instructions"])
    return out


def imc_windows(xr, b: str, d: str, stack: dict) -> list[float]:
    meta = json.load(open(os.path.join(d, "metadata.json")))
    imc, M = xr.all_imc(), xr.marks()
    t0, t1 = meta["ts_start"], meta["ts_end"]
    i0, i1 = xr.idle_before(b, t0, M)
    base = xr.rates(imc, i0, i1)
    floor = (base.get(xr.RD, 0) + base.get(xr.WR, 0)) * LINE / 1e9 + stack["rd_GBs"] + stack["wr_GBs"]
    return [(dd.get(xr.RD, 0) + dd.get(xr.WR, 0)) * LINE / 1e9 / (hi - lo) - floor
            for lo, hi, dd in imc if lo >= t0 and hi <= t1]


def campaign_windows(b: str, group: str, metric: str) -> list[float]:
    w = json.load(open(os.path.join(ORIG, b, "windows_metrics.json")))
    return [x[metric] for x in w if x["group"] == group and x.get(metric) is not None]


def collect():
    rows, summ = [], []
    for root, benches in ROOTS.items():
        xr = xr_for(root)
        S = json.load(open(os.path.join(INFRA, root, "xcheck_summary.json")))
        for b in benches:
            d = os.path.join(INFRA, root, b)
            e = S["episodes"][b]
            base = b.split("@")[0]
            ran = e["cmd_index"] == json.load(open(os.path.join(ORIG, base, "metadata.json")))["cmd_index"]
            r = {"bench": b, "cmd_index": e["cmd_index"],
                 "llc_new": x_llc_windows(d), "dram_new": imc_windows(xr, b, d, S["stack_control"]),
                 "llc_old": campaign_windows(base, "cache", "LLC_MPKI") if ran else [],
                 "dram_old": campaign_windows(base, "dram_bw", "DRAM_read_GBs") if ran else [],
                 # episode aggregates, as in xcheck_summary.json / metrics.json
                 "llc_new_ep": e["llc_miss_PKI"], "llc_old_ep": e["LLC_MPKI_original"],
                 "dram_new_ep": e["imc_rd_GBs_bench"] + e["imc_wr_GBs_bench"],
                 "dram_old_ep": e["DRAM_read_GBs_original"],
                 # the campaign's own definitions, re-measured in the re-run
                 "llc_same": e["LLC_MPKI"], "dram_same": e["DRAM_read_GBs"]}
            summ.append(r)
            for k, src in (("llc_old", "campaign LLC_MPKI (demand loads)"),
                           ("llc_new", "re-run longest_lat_cache.miss PKI"),
                           ("dram_old", "campaign DRAM_read_GBs (offcore data_rd)"),
                           ("dram_new", "re-run IMC rd+wr GB/s, net")):
                rows += [(b, e["cmd_index"], src, i, v) for i, v in enumerate(r[k])]
    return summ, rows


def violin(ax, summ, key, ylab, title, lo_clip, ticks, top):
    pos = np.arange(len(summ))
    for side, k, color in (("low", f"{key}_old", BLUE), ("high", f"{key}_new", ORANGE)):
        for p, r in zip(pos, summ):
            v = np.asarray(r[k], float)
            if v.size < 2:
                continue
            lv = np.log10(np.clip(v, lo_clip, None))
            # bandwidth at least 0.04 decades, so very steady benchmarks (lbm) still show a body
            sd = lv.std()
            bw = max(0.3, 0.04 / sd) if sd > 0 else 1.0
            if sd == 0:
                lv = lv + np.random.default_rng(0).normal(0, 0.01, lv.size)
            parts = ax.violinplot(lv, [p], widths=0.82, side=side, showextrema=False,
                                  points=300, bw_method=bw)
            for pc in parts["bodies"]:
                pc.set_facecolor(color); pc.set_edgecolor(SURF); pc.set_linewidth(1.5); pc.set_alpha(0.85)
            # episode aggregate (what the summary tables quote): short tick on that half
            agg = r[f"{k}_ep"]
            x0, x1 = (p - 0.36, p) if side == "low" else (p, p + 0.36)
            ax.plot([x0, x1], [np.log10(max(agg, lo_clip))] * 2, color=INK, lw=1.6, solid_capstyle="butt")
    for p, r in zip(pos, summ):
        if not r[f"{key}_old"]:
            ax.text(p - 0.2, ticks[0][0] + 0.15, "not run\nby campaign", ha="center", va="bottom",
                    fontsize=7.5, color=INK2, rotation=90)
    ax.set_xticks(pos, [LABEL.get(r["bench"], r["bench"]) for r in summ], fontsize=8.5)
    ax.set_yticks(*ticks)
    ax.set_ylim(ticks[0][0], top)
    ax.set_ylabel(ylab, color=INK2)
    ax.set_title(title, loc="left", fontsize=11.5, color=INK, pad=26)
    ax.axvline(5.5, color=GRID, lw=1, ls=(0, (3, 3)))
    ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2, length=0)
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    ax.legend(handles=[Patch(color=BLUE, label=f"campaign ({'LLC_MPKI' if key == 'llc' else 'DRAM_read_GBs'})"),
                       Patch(color=ORANGE, label="re-run, corrected metric"),
                       Line2D([], [], color=INK, lw=2, label="episode value")],
              loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, frameon=False, fontsize=8.5,
              labelcolor=INK2, borderaxespad=0.2)


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    summ, rows = collect()
    with open(os.path.join(OUT, "per_window.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["benchmark", "cmd_index", "series", "window", "value"])
        w.writerows(rows)
    with open(os.path.join(OUT, "summary.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["benchmark", "cmd_index",
                    "LLC_MPKI_campaign", "LLC_MPKI_rerun_same_def", "llc_miss_PKI_rerun", "n_win_llc_campaign", "n_win_llc_rerun",
                    "DRAM_read_GBs_campaign", "DRAM_read_GBs_rerun_same_def", "imc_rdwr_GBs_rerun", "n_win_dram_campaign", "n_imc_samples_rerun"])
        for r in summ:
            w.writerow([r["bench"], r["cmd_index"], r["llc_old_ep"], r["llc_same"], r["llc_new_ep"], len(r["llc_old"]),
                        len(r["llc_new"]), r["dram_old_ep"], r["dram_same"], r["dram_new_ep"], len(r["dram_old"]), len(r["dram_new"])])

    plt.rcParams.update({"font.family": "DejaVu Sans", "figure.facecolor": SURF, "axes.facecolor": SURF})
    lt = [-3, -2, -1, 0, 1, 2]
    fig, ax = plt.subplots(figsize=(11, 5.2), dpi=150)
    violin(ax, summ, "llc", "L3 misses per 1000 instructions (log)",
           "LLC: campaign LLC_MPKI (retired demand loads) vs all core L3 misses (longest_lat_cache.miss)",
           1e-3, (lt, ["≤0.001", "0.01", "0.1", "1", "10", "100"]), 2.25)
    fig.text(0.01, 0.01, "Per 100 ms window. Campaign: data/, `cache` group (live 1 window in 11). "
             "Re-run: data_llc_xcheck*/, `x_llc` group (1 in 5). Windows at 0 are drawn at the 0.001 floor.",
             fontsize=7.5, color=INK2)
    fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(os.path.join(OUT, "llc_violin.png")); plt.close(fig)

    dt = [-2, -1, 0, 1, 2]
    fig, ax = plt.subplots(figsize=(11, 5.2), dpi=150)
    violin(ax, summ, "dram", "GB/s (log)",
           "DRAM: campaign DRAM_read_GBs (L2→uncore reads) vs memory-controller read+write traffic",
           1e-2, (dt[:-1], ["≤0.01", "0.1", "1", "10"]), 1.5)
    fig.text(0.01, 0.01, "Campaign: per 100 ms `dram_bw` window. Re-run: IMC CAS rd+wr per 0.5 s, system-wide, "
             "minus idle and capture-stack traffic; samples ≤0.01 (noise floor) are drawn at 0.01.",
             fontsize=7.5, color=INK2)
    fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(os.path.join(OUT, "dram_violin.png")); plt.close(fig)

    for r in summ:
        print(f"{r['bench']:16s} llc old n={len(r['llc_old']):4d} ep={r['llc_old_ep'] or 0:.3f}  "
              f"new n={len(r['llc_new']):4d} ep={r['llc_new_ep']:.3f} | dram old n={len(r['dram_old']):4d} "
              f"ep={r['dram_old_ep'] or 0:.3f}  new n={len(r['dram_new']):4d} ep={r['dram_new_ep']:.3f} "
              f"neg={sum(v <= 0.01 for v in r['dram_new'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
