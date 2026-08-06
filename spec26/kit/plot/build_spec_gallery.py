#!/usr/bin/env python3
"""build_spec_gallery.py — one self-contained HTML page per SPEC benchmark: every per-window
metric, distribution beside timeline, with the episode value drawn on both.

    /home/thu/miniforge3/envs/infersuite-full/bin/python spec26/kit/plot/build_spec_gallery.py [bench ...]

Inputs:  the PNGs written by plot_spec_windows.py under SPEC_WIN.
Output:  gallery_<bench>.html in the same directory (~3-6 MB each; images inlined as base64
         data URIs so a published page needs no external host — Artifact pages are served
         under a CSP that blocks every outside request).

Sibling of local_agents/kit/plot/build_metric_gallery.py, which does the same job for the
agentic campaign. The section structure is deliberately the same so the two galleries can be
read side by side; what differs is the fence story — the agentic galleries split every metric
into a tool fence and a harness fence, whereas SPEC has exactly one program in one cgroup, so
there is one panel pair per metric and no command-tag colouring.
"""
from __future__ import annotations

import base64
import html
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from spec_common import GALLERY_ORDER, WINDOW_METRICS, WINOUT, episodes  # noqa: E402

SECTIONS = [
    ("Instruction supply", "How uops reach the core, and what it costs to fetch them.",
     ["DSB_pct", "MITE_pct", "MS_pct", "LSD_pct", "dsb_miss_MPKI", "dsb2mite_penalty_pct",
      "ms_switches_PKI", "L1I_MPKI", "icache_data_stall_pct", "icache_tag_stall_pct",
      "itlb_walk_pct"]),
    ("Branches and speculation", "What the predictor gets wrong and what that costs.",
     ["brMPKI", "baclears_MPKI", "misp_indirect_pct", "resteer_pct"]),
    ("Memory hierarchy", "The load ladder, its modelled latency, and real DRAM traffic. "
     "LLC_MPKI counts DEMAND loads only — prefetch-friendly code streams GB/s while reading "
     "~0 here.",
     ["L1D_MPKI", "L2_MPKI", "LLC_MPKI", "AMAT_cyc", "MLP", "bound_on_loads_pct",
      "stalls_l1d_miss_pct", "stalls_l2_miss_pct", "stalls_l3_miss_pct", "bound_on_stores_pct",
      "DRAM_read_GBs", "dram_read_occ_pct"]),
    ("Execution core", "How many ports retire work, and which arithmetic runs.",
     ["IPC", "ports_0_pct", "ports_1_pct", "ports_2_pct", "div_active_pct", "vecFP_pct"]),
    ("System", "Time the kernel took, and how often the program left user space.",
     ["kernel_pct", "ctx_switch_PKI", "pagefault_PKI"]),
]
# Every gallery metric must live in exactly one section, or it silently disappears from the page.
_placed = [k for _t, _d, ks in SECTIONS for k in ks]
_missing = [k for k in GALLERY_ORDER if k not in _placed]
assert not _missing, f"metrics not assigned to a section: {_missing}"

CSS = """body{margin:0;font-family:system-ui,Segoe UI,Roboto,sans-serif;background:#f5f8f6;color:#12201b}
@media(prefers-color-scheme:dark){body{background:#0e1512;color:#e8efeb}
 .card{background:#16201c!important;border-color:#26332d!important}
 .nav a{color:#5fb0e8!important}.meta{background:#16201c!important;border-color:#26332d!important}}
:root[data-theme="dark"] body{background:#0e1512;color:#e8efeb}
.wrap{max-width:1180px;margin:0 auto;padding:24px}
h1{font-size:26px;margin:8px 0 2px} h2{font-size:19px;margin:34px 0 4px;border-bottom:2px solid #1b6ca8;padding-bottom:4px}
h3{font-size:15px;margin:22px 0 4px;color:#1b6ca8;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.nav{font-size:12.5px;line-height:2;margin:10px 0 18px}
.nav a{color:#12507d;text-decoration:none;margin-right:12px;white-space:nowrap}
.card{background:#fff;border:1px solid #dde6e1;border-radius:10px;padding:10px;margin:8px 0}
.card img{width:100%;height:auto;display:block}
.row{display:grid;grid-template-columns:0.42fr 1fr;gap:10px;align-items:start}
@media(max-width:820px){.row{grid-template-columns:1fr}}
.note{font-size:12.5px;color:#5c6b64;margin:6px 0 18px;line-height:1.55}
.meta{background:#fff;border:1px solid #dde6e1;border-radius:10px;padding:12px 14px;margin:14px 0;
 font-size:12.5px;line-height:1.7}
.meta b{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.sec{font-size:13px;color:#5c6b64;margin:2px 0 10px}
"""


def uri(p: str) -> str:
    return "data:image/png;base64," + base64.b64encode(open(p, "rb").read()).decode()


def main() -> int:
    only = set(sys.argv[1:])
    eps = [e for e in episodes() if not only or e["short"] in only or e["benchmark"] in only]
    for e in eps:
        b, meta, M = e["short"], e["meta"], e["metrics"]
        have = [k for k in GALLERY_ORDER
                if os.path.exists(os.path.join(WINOUT, f"box_{b}_{k}.png"))]
        if not have:
            print(f"  ! {b}: no per-window figures — run plot_spec_windows.py first")
            continue
        P = [f"<title>Per-window gallery — {e['benchmark']}</title><style>{CSS}</style>",
             "<div class='wrap'>",
             f"<h1>Per-window gallery — {html.escape(e['benchmark'])}</h1>",
             f"<p class='sec'>SPEC CPU 2026 · {'floating-point' if e['fp'] else 'integer'} rate "
             f"· every metric at 100 ms resolution</p>"]
        P.append(
            "<div class='meta'>"
            f"input size <b>{meta.get('size')}</b> (ref) · command line index "
            f"<b>{meta.get('cmd_index')}</b> of {meta.get('n_ref_cmds')} · copies "
            f"<b>{meta.get('copies')}</b>, threads <b>{meta.get('threads')}</b><br>"
            f"episode wall <b>{e['wall_s']:.1f} s</b> · <b>{e['n_windows']:,}</b> windows of "
            f"<b>{meta.get('winsec')} s</b> · fence <b>{meta.get('fence_cgroup')}</b><br>"
            f"measured CPUs <b>{meta.get('cpus_measured')}</b> (SMT <b>{meta.get('smt')}</b>) · "
            f"governor <b>{meta.get('governor')}</b> · no_turbo <b>{meta.get('no_turbo')}</b> · "
            f"THP <b>never</b><br>"
            f"output check <b>{(e.get('output_check') or meta.get('output_check') or {}).get('status', 'n/a')}</b>"
            f" · binary sha256[16] <b>{meta.get('binary_sha256_16')}</b> · kit rev "
            f"<b>{meta.get('kit_rev')}</b>"
            "</div>")
        P.append(
            "<p class='note'><b>How to read this.</b> Exactly one counter group is installed per "
            "window, so each metric's distribution is over the windows that carried its own group "
            "— about 1/11 of the episode, scattered across the whole run by the shuffled rotation, "
            "never a contiguous slice. <b>IPC is the exception</b>: cycles and instructions ride in "
            "every group, so IPC has every window. Box = IQR, orange = median, ▲ = mean, whiskers = "
            "5–95 %, ○ = outliers. The dashed blue line is the <b>episode</b> value — a ratio of "
            "sums, which is <i>not</i> the median of the per-window ratios; where the two disagree "
            "the program has phases, and that gap is the finding, not an error. Nothing here was "
            "multiplexed: every group fits the per-thread counter budget and ran at 100 % enabled "
            "time.</p>")
        P.append("<div class='nav'>" + " ".join(
            f"<a href='#{k}'>{k}</a>" for k in have) + "</div>")

        for title, blurb, keys in SECTIONS:
            ks = [k for k in keys if k in have]
            if not ks:
                continue
            P.append(f"<h2>{html.escape(title)}</h2><p class='sec'>{html.escape(blurb)}</p>")
            for k in ks:
                grp, unit = WINDOW_METRICS[k]
                ev = M.get(k)
                epv = "n/a" if ev is None else f"{ev:.4g}"
                P.append(f"<h3 id='{k}'>{html.escape(k)} "
                         f"<span style='font-weight:400;color:#5c6b64;font-family:inherit'>"
                         f"— {html.escape(unit)} · group <code>{grp}</code> · episode value "
                         f"{epv}</span></h3>")
                P.append("<div class='row'>")
                P.append("<div class='card'><img loading='lazy' alt='distribution "
                         f"{k}' src='{uri(os.path.join(WINOUT, f'box_{b}_{k}.png'))}'></div>")
                tl = os.path.join(WINOUT, f"timeline_{b}_{k}.png")
                if os.path.exists(tl):
                    P.append(f"<div class='card'><img loading='lazy' alt='timeline {k}' "
                             f"src='{uri(tl)}'></div>")
                P.append("</div>")
        P.append("<p class='note'>Generated by <code>spec26/kit/plot/build_spec_gallery.py</code> "
                 "from <code>spec26/kit/plot/plot_spec_windows.py</code> output. Raw windows: "
                 "<code>~/spec26-infra/infra/data/" + html.escape(e["benchmark"]) +
                 "/</code> (outside the repo).</p></div>")
        out = os.path.join(WINOUT, f"gallery_{b}.html")
        open(out, "w").write("\n".join(P))
        print(f"  {out}  {os.path.getsize(out)/1e6:.1f} MB, {len(have)} metrics")
    return 0


if __name__ == "__main__":
    sys.exit(main())
