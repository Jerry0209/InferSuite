#!/usr/bin/env python3
"""build_metric_gallery.py — one self-contained HTML gallery per task: every per-window
metric with (tag-split tool-fence box, harness-fence box, tag-colored tool timeline).

Inputs:  figures produced by analyze_l3_windows.py --plot under <l3_study>/plots/
Output:  gallery_<task>.html per task in --out (default: alongside the plots)

Images are embedded as base64 data URIs (self-contained page, ~4-5 MB per task).
Usage: build_metric_gallery.py [--plots DIR] [--out DIR] [task ...]
"""
import base64, os, html, sys

PD = "/home/thu/InferSuite/local_agents/superseded_40min/data/l3_study/plots"
OUT = None
args = [a for a in sys.argv[1:]]
if "--plots" in args: PD = args[args.index("--plots") + 1]
if "--out" in args: OUT = args[args.index("--out") + 1]
TASKS = [a for a in args if not a.startswith("--") and a not in (PD, OUT or "")] \
        or ["scikit-learn", "astropy", "sympy"]
OUT = OUT or PD

ORDER = ["IPC", "branch_MPKI", "branchDir_MPKI", "branchInd_MPKI", "BTB_MPKI",
         "uopCache_MPKI", "DSB_pct", "MITE_pct", "MS_pct", "codeRead_MPKI_L1I",
         "icache_data_stall_pct", "itlb_tag_stall_pct", "itlb_walk_pct",
         "branch_resteer_pct", "tma_dsb_switches_pct", "ms_switches_PKI",
         "L1D_MPKI", "L2_MPKI", "LLC_MPKI", "AMAT_cyc", "MLP",
         "tma_l1_bound_pct", "tma_l2_bound_pct", "tma_l3_bound_pct",
         "tma_dram_bound_pct", "tma_store_bound_pct", "dram_bw_bound_pct",
         "dram_read_occ_pct", "divider_pct", "ports0_pct", "ports1_pct",
         "ports2_pct", "vecFP_pct", "kernel_pct"]

CSS = """body{margin:0;font-family:system-ui,Segoe UI,Roboto,sans-serif;background:#f5f8f6;color:#12201b}
@media(prefers-color-scheme:dark){body{background:#0e1512;color:#e8efeb}.card{background:#16201c!important;border-color:#26332d!important}.nav a{color:#2fc294!important}}
.wrap{max-width:1180px;margin:0 auto;padding:24px}
h1{font-size:26px;margin:8px 0} h2{font-size:19px;margin:34px 0 6px;border-bottom:2px solid #159f77;padding-bottom:4px}
.nav{font-size:12.5px;line-height:2;margin:10px 0 18px}
.nav a{color:#0b5c44;text-decoration:none;margin-right:12px;white-space:nowrap}
.card{background:#fff;border:1px solid #dde6e1;border-radius:10px;padding:10px;margin:10px 0}
.card img{width:100%;height:auto;display:block}
.row{display:grid;grid-template-columns:1fr 1fr;gap:10px}
@media(max-width:800px){.row{grid-template-columns:1fr}}
.note{font-size:12.5px;color:#5c6b64;margin:6px 0 20px;line-height:1.5}
"""

def uri(p):
    return "data:image/png;base64," + base64.b64encode(open(p, "rb").read()).decode()

for t in TASKS:
    parts = [f"<title>Per-window gallery — {t}</title><style>{CSS}</style><div class='wrap'>"]
    parts.append(f"<h1>Per-window gallery — {t} (tool + harness fences)</h1>")
    parts.append("<p class='note'>Every metric, per 2-s window, from dedicated-group deterministic "
                 "replays. Box = IQR, orange = median, ▲ = mean, whiskers = 5–95%, ○ = outliers; "
                 "(Nw) = windows owning that tag. Timeline color = command tag (2 Hz cgroup process "
                 "poll). Data: l3_study/all_windows_*.csv.</p>")
    metrics = [m for m in ORDER if os.path.exists(f"{PD}/box_{t}_{m}.png")]
    parts.append("<div class='nav'>" + " ".join(f"<a href='#{m}'>{m}</a>" for m in metrics) + "</div>")
    for m in metrics:
        parts.append(f"<h2 id='{m}'>{html.escape(m)}</h2>")
        b, tl, hb = f"{PD}/box_{t}_{m}.png", f"{PD}/timeline_{t}_{m}.png", f"{PD}/hbox_{t}_{m}.png"
        parts.append("<div class='row'>")
        parts.append(f"<div class='card'><img loading='lazy' alt='tool box {m}' src='{uri(b)}'></div>")
        if os.path.exists(hb):
            parts.append(f"<div class='card'><img loading='lazy' alt='harness box {m}' src='{uri(hb)}'></div>")
        parts.append("</div>")
        if os.path.exists(tl):
            parts.append(f"<div class='card'><img loading='lazy' alt='tool timeline {m}' src='{uri(tl)}'></div>")
    parts.append("</div>")
    out = f"{OUT}/gallery_{t}.html"
    open(out, "w").write("\n".join(parts))
    print(out, f"{os.path.getsize(out)/1e6:.1f} MB, {len(metrics)} metrics")
