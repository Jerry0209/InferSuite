#!/usr/bin/env python3
"""xcheck_report.py [DATA_ROOT] — analyse an llc_dram_crosscheck.sh session.

Writes DATA_ROOT/xcheck_summary.json and prints markdown tables:

  calibration  known-traffic kernels: kernel-reported GB/s vs IMC CAS vs core OCR counts
  episodes     per benchmark, the campaign's two metrics (original run AND this quiet
               re-run, same definitions) against wider LLC definitions and against the
               DRAM traffic the memory controllers actually saw

DRAM traffic comes from unc_m_cas_count.{rd,wr}, which is system-wide: each episode's
rate has the idle rate measured in the 15 s gap just before it subtracted, and then the
capture stack's own traffic, measured once on an empty fence (stack_control). Several
driver invocations (_session, _session.2, ...) are stitched together by wall-clock time;
calibration and stack control come from the latest session that has them. Per-KI values
divide by the episode's instruction total, IPC (all windows) x cycles (continuous TMA
slots / 6: the census runs at 100% duty, the windows only ~83%).
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
from extract_metrics import load_episode, load_tma, parse_window  # noqa: E402

INFRA = os.path.dirname(KIT)
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(INFRA, "data_llc_xcheck")
SESSIONS = sorted((os.path.join(ROOT, d) for d in os.listdir(ROOT)
                   if re.fullmatch(r"_session(\.\d+)?", d)),
                  key=lambda p: float(open(os.path.join(p, "imc.t0")).read())
                  if os.path.exists(os.path.join(p, "imc.t0")) else 0.0)
ORIG = os.path.join(INFRA, "data")
LINE = 64
SLOTS_PER_CYCLE = 6          # Golden Cove issue width, as the TMA census counts it
RD, WR = "unc_m_cas_count.rd", "unc_m_cas_count.wr"


def series(csv: str, t0: float):
    """perf stat -I -x, output -> [(t_lo, t_hi, {event: count})] in epoch seconds."""
    rows: dict[float, dict[str, float]] = defaultdict(dict)
    for ln in open(csv, errors="replace"):
        if ln.startswith("#") or not ln.strip():
            continue
        p = ln.strip().split(",")
        try:
            t, v = float(p[0]), float(p[1])
        except (ValueError, IndexError):
            continue
        rows[t][p[3]] = rows[t].get(p[3], 0.0) + v
    out, prev = [], 0.0
    for t in sorted(rows):
        out.append((t0 + prev, t0 + t, rows[t]))
        prev = t
    return out


def rates(ser, a: float, b: float) -> dict[str, float]:
    """Per-second rate of every event over the intervals lying wholly inside [a, b]."""
    tot: dict[str, float] = defaultdict(float)
    secs = 0.0
    for lo, hi, d in ser:
        if lo >= a and hi <= b:
            secs += hi - lo
            for k, v in d.items():
                tot[k] += v
    return {k: v / secs for k, v in tot.items()} if secs else {}


def latest(sub: str) -> str | None:
    """The most recent session directory that contains `sub`."""
    hits = [s for s in SESSIONS if os.path.exists(os.path.join(s, sub))]
    return hits[-1] if hits else None


def all_imc():
    out = []
    for s in SESSIONS:
        if os.path.exists(os.path.join(s, "imc.csv")):
            out += series(os.path.join(s, "imc.csv"), float(open(os.path.join(s, "imc.t0")).read()))
    return sorted(out, key=lambda x: x[0])


def marks() -> list[tuple[str, str, float]]:
    out = []
    for ln in (ln for s in SESSIONS if os.path.exists(os.path.join(s, "marks.tsv"))
               for ln in open(os.path.join(s, "marks.tsv"))):
        p = ln.split("\t")
        if len(p) == 3:
            out.append((p[0], p[1], float(p[2])))
    return out


def idle_before(tag: str, t: float, M) -> tuple[float, float]:
    """The last idle gap marked for `tag` that ended before time t."""
    s = [x[2] for x in M if x[0] == tag and x[1] == "idle_start" and x[2] < t]
    e = [x[2] for x in M if x[0] == tag and x[1] == "idle_end" and x[2] <= t]
    return (s[-1], e[-1]) if s and e else (float("nan"), float("nan"))


def kernel_log(path: str) -> dict:
    txt = open(path).read()
    return {k: float(v) for k, v in re.findall(r"(t_start|t_end|GBps|bytes)=([\d.]+)", txt)}


def group_events(d: str) -> dict[str, set[str]]:
    ev: dict[str, set[str]] = {}
    for fn in sorted(os.listdir(d)):
        m = re.match(r"^group_(.+)_w\d+\.txt$", fn)
        if m and m.group(1) not in ev:
            vals, _ = parse_window(os.path.join(d, fn))
            if vals:
                ev[m.group(1)] = set(vals)
    return ev


def calibration(imc, M) -> dict:
    out = {}
    SESS = latest("calib_read_x_ocr1")
    if SESS is None:
        return out
    out["session"] = os.path.basename(SESS)
    k0 = kernel_log(os.path.join(SESS, "calib_read_x_ocr1", "kernel.log"))
    i0, i1 = idle_before("calib", k0["t_start"], M)
    base = rates(imc, i0, i1)
    out["idle_GBs"] = {"rd": base.get(RD, 0) * LINE / 1e9, "wr": base.get(WR, 0) * LINE / 1e9}
    for mode in ("read", "write"):
        d = os.path.join(SESS, f"calib_{mode}_x_ocr1")
        if not os.path.isdir(d):
            continue
        k = kernel_log(os.path.join(d, "kernel.log"))
        a, b = k["t_start"] + 0.5, k["t_end"] - 0.5           # clear of the region edges
        r_imc = rates(imc, a, b)
        core = series(os.path.join(d, "core.csv"), float(open(os.path.join(d, "core.t0")).read()))
        r_core = rates(core, a, b)
        gbs = lambda r, ev: r.get(ev, 0.0) * LINE / 1e9
        out[mode] = {
            "kernel_GBs": k["GBps"],
            "imc_rd_GBs": gbs(r_imc, RD) - out["idle_GBs"]["rd"],
            "imc_wr_GBs": gbs(r_imc, WR) - out["idle_GBs"]["wr"],
            **{f"{ev}_GBs": gbs(r_core, ev) for ev in (
                "ocr.reads_to_core.l3_miss", "ocr.demand_rfo.l3_miss",
                "offcore_requests.data_rd", "l2_lines_out.non_silent")},
        }
    d = os.path.join(SESS, "calib_read_rotate")
    if os.path.isdir(d):
        k = kernel_log(os.path.join(d, "kernel.log"))
        rot, defects = {"kernel_GBs": k.get("GBps")}, []
        for fn in sorted(os.listdir(d)):
            m = re.match(r"^group_(.+)_w\d+\.txt$", fn)
            if not m:
                continue
            vals, defs = parse_window(os.path.join(d, fn))
            defects += [f"{fn}: {x}" for x in defs]
            for ev, v in vals.items():
                # line-granular events only; mem_load_retired.* counts load uops (two
                # 32 B loads per line in this kernel), reported per streamed line instead
                if ev.startswith(("longest_lat", "ocr.", "offcore_requests.data_rd")):
                    rot[f"{m.group(1)}:{ev}_GBs"] = v / 1.5 * LINE / 1e9
                elif ev.startswith("mem_load_retired.") and k.get("GBps"):
                    rot[f"{m.group(1)}:{ev}_per_line"] = v / 1.5 / (k["GBps"] * 1e9 / LINE)
        rot["defects"] = defects
        out["rotate"] = rot
    return out


def stack_control(imc, M) -> dict:
    """DRAM traffic of the capture stack alone: an empty fence with the full stack on it."""
    st = [x[2] for x in M if x[:2] == ("stack", "start")]
    en = [x[2] for x in M if x[:2] == ("stack", "end")]
    if not st or not en:
        return {}
    a, b = st[-1], en[-1]
    i0, i1 = idle_before("stack", a, M)
    base, run = rates(imc, i0, i1), rates(imc, a + 1, b - 1)
    return {"seconds": b - a,
            "rd_GBs": (run.get(RD, 0) - base.get(RD, 0)) * LINE / 1e9,
            "wr_GBs": (run.get(WR, 0) - base.get(WR, 0)) * LINE / 1e9,
            "idle_GBs": {"rd": base.get(RD, 0) * LINE / 1e9, "wr": base.get(WR, 0) * LINE / 1e9}}


def episode(b: str, imc, M, stack: dict) -> dict:
    d = os.path.join(ROOT, b)
    meta = json.load(open(os.path.join(d, "metadata.json")))
    S, coI, coC, secs, wins, defects = load_episode(d)
    tma = load_tma(d)
    gev = group_events(d)
    ev_secs: dict[str, float] = defaultdict(float)
    for g, evs in gev.items():
        for ev in evs:
            ev_secs[ev] += secs.get(g, 0.0)

    def pki(ev):
        return 1000 * S[ev] / coI[ev] if coI.get(ev) and ev in S else None

    ipc = S["instructions"] / S["cycles"]
    cycles = tma["slots"] / SLOTS_PER_CYCLE
    inst = ipc * cycles
    t0, t1 = meta["ts_start"], meta["ts_end"]
    wall = t1 - t0
    i0, i1 = idle_before(b, t0, M)
    base = rates(imc, i0, i1)
    ep = rates(imc, t0, t1)
    net = {ev: ep.get(ev, 0.0) - base.get(ev, 0.0) for ev in (RD, WR)}
    stk = {RD: stack.get("rd_GBs", 0.0) * 1e9 / LINE, WR: stack.get("wr_GBs", 0.0) * 1e9 / LINE}
    net_s = {ev: net[ev] - stk[ev] for ev in (RD, WR)}
    inst_rate = inst / wall

    # The campaign ran one ref input per benchmark: compare against it only when this
    # episode ran the same one ("<bench>@<k>" episodes may not).
    od = os.path.join(ORIG, b.split("@")[0])
    if json.load(open(os.path.join(od, "metadata.json"))).get("cmd_index") == meta.get("cmd_index"):
        o = json.load(open(os.path.join(od, "metrics.json")))
        om = o["metrics"]
        o_inst = om["IPC"] * o["tma"]["slots"] / SLOTS_PER_CYCLE
    else:
        om, o_inst = {}, None

    r = {
        "cmd_index": meta.get("cmd_index"), "command": meta.get("command"),
        "wall_s": wall, "inst_G": inst / 1e9, "inst_G_original": o_inst / 1e9 if o_inst else None,
        "IPC": ipc, "IPC_original": om.get("IPC"),
        "windows_per_group": wins, "defects": len(defects),
        "foreign_witness": meta.get("foreign_witness"),
        "mean_cores": meta.get("mean_cores"),
        "LLC_MPKI_original": om.get("LLC_MPKI"),
        "LLC_MPKI": pki("mem_load_retired.l3_miss"),
        "fb_hit_PKI": pki("mem_load_retired.fb_hit"),
        "llc_miss_PKI": pki("longest_lat_cache.miss"),
        "llc_ref_PKI": pki("longest_lat_cache.reference"),
        "ocr_demand_data_rd_l3_miss_PKI": pki("ocr.demand_data_rd.l3_miss"),
        "ocr_reads_to_core_l3_miss_PKI": pki("ocr.reads_to_core.l3_miss"),
        "ocr_demand_rfo_l3_miss_PKI": pki("ocr.demand_rfo.l3_miss"),
        "ocr_hwpf_l3_l3_miss_PKI": pki("ocr.hwpf_l3.l3_miss"),
        "offcore_data_rd_PKI": pki("offcore_requests.data_rd"),
        "l2_lines_out_non_silent_PKI": pki("l2_lines_out.non_silent"),
        "DRAM_read_GBs_original": om.get("DRAM_read_GBs"),
        "DRAM_read_GBs": (S["offcore_requests.data_rd"] * LINE / ev_secs["offcore_requests.data_rd"] / 1e9
                          if ev_secs.get("offcore_requests.data_rd") else None),
        "imc_idle_GBs": {"rd": base.get(RD, 0) * LINE / 1e9, "wr": base.get(WR, 0) * LINE / 1e9},
        "imc_rd_GBs": net[RD] * LINE / 1e9,
        "imc_wr_GBs": net[WR] * LINE / 1e9,
        "imc_rd_PKI": 1000 * net[RD] / inst_rate,
        "imc_wr_PKI": 1000 * net[WR] / inst_rate,
        # minus the capture stack's own traffic (stack_control); None when not measured
        "imc_rd_GBs_bench": net_s[RD] * LINE / 1e9 if stack else None,
        "imc_wr_GBs_bench": net_s[WR] * LINE / 1e9 if stack else None,
        "imc_rd_PKI_bench": 1000 * net_s[RD] / inst_rate if stack else None,
        "imc_wr_PKI_bench": 1000 * net_s[WR] / inst_rate if stack else None,
    }
    return r


def f(v, p=2):
    if v is None:
        return "—"
    if abs(v) >= 100:
        return f"{v:.0f}"
    return f"{v:.{p}f}" if abs(v) >= 0.1 or v == 0 else f"{v:.3f}"


def main() -> int:
    imc = all_imc()
    M = marks()
    stack = stack_control(imc, M)
    benches = [x for x in sorted(os.listdir(ROOT))
               if re.match(r"^\d{3}\.\w+(@\d+)?$", x) and os.path.exists(os.path.join(ROOT, x, "metadata.json"))]
    out = {"calibration": calibration(imc, M), "stack_control": stack, "episodes": {}}
    for b in benches:
        try:
            out["episodes"][b] = episode(b, imc, M, stack)
        except (OSError, KeyError, ZeroDivisionError) as e:
            out["episodes"][b] = {"error": repr(e)}
    json.dump(out, open(os.path.join(ROOT, "xcheck_summary.json"), "w"), indent=1)

    c = out["calibration"]
    print(f"idle DRAM: rd {f(c['idle_GBs']['rd'])} GB/s, wr {f(c['idle_GBs']['wr'])} GB/s\n")
    print("| kernel | kernel GB/s | IMC rd | IMC wr | ocr.reads_to_core.l3_miss | ocr.demand_rfo.l3_miss | offcore data_rd | L2 non-silent evict |")
    print("|---|---|---|---|---|---|---|---|")
    for mode in ("read", "write"):
        if mode in c:
            x = c[mode]
            print(f"| {mode} | {f(x['kernel_GBs'])} | {f(x['imc_rd_GBs'])} | {f(x['imc_wr_GBs'])} | "
                  f"{f(x['ocr.reads_to_core.l3_miss_GBs'])} | {f(x['ocr.demand_rfo.l3_miss_GBs'])} | "
                  f"{f(x['offcore_requests.data_rd_GBs'])} | {f(x['l2_lines_out.non_silent_GBs'])} |")
    if "rotate" in c:
        print(f"\nrotation check on the read kernel ({f(c['rotate']['kernel_GBs'])} GB/s): "
              f"{len(c['rotate']['defects'])} defects")
        for k, v in c["rotate"].items():
            if k.endswith("_GBs") and k != "kernel_GBs":
                print(f"  {k:60s} {f(v)} GB/s as 64 B lines")
            elif k.endswith("_per_line"):
                print(f"  {k:60s} {f(v)} per streamed line")

    st = out["stack_control"]
    if st:
        print(f"\ncapture stack alone (empty fence, {st['seconds']:.0f} s): DRAM rd {f(st['rd_GBs'])} GB/s, "
              f"wr {f(st['wr_GBs'])} GB/s above idle ({f(st['idle_GBs']['rd'])} / {f(st['idle_GBs']['wr'])})")
    sub = (lambda r, k: r.get(f"{k}_bench")) if st else (lambda r, k: r[k])
    tag = " minus stack" if st else ""
    E = out["episodes"]
    print(f"\n| benchmark | inst (G) orig / now | LLC_MPKI orig / now | fb_hit PKI | LLC miss PKI (all core reqs) | + L3-pf miss PKI | DRAM rd lines/KI (IMC{tag}) | DRAM wr lines/KI (IMC{tag}) |")
    print("|---|---|---|---|---|---|---|---|")
    for b, r in E.items():
        if "error" in r:
            print(f"| {b} | error: {r['error']} |")
            continue
        print(f"| {b} | {f(r['inst_G_original'],0)} / {f(r['inst_G'],0)} | {f(r['LLC_MPKI_original'])} / {f(r['LLC_MPKI'])} | "
              f"{f(r['fb_hit_PKI'])} | {f(r['llc_miss_PKI'])} | {f(r['ocr_hwpf_l3_l3_miss_PKI'])} | "
              f"{f(sub(r, 'imc_rd_PKI'))} | {f(sub(r, 'imc_wr_PKI'))} |")
    print(f"\n| benchmark | DRAM_read_GBs orig / now | IMC read GB/s{tag} | IMC write GB/s{tag} | offcore data_rd PKI | ocr reads_to_core L3-miss PKI | ocr demand RFO L3-miss PKI | foreign CPU (mean %, rows flagged) |")
    print("|---|---|---|---|---|---|---|---|")
    for b, r in E.items():
        if "error" in r:
            continue
        w = r["foreign_witness"] or {}
        print(f"| {b} | {f(r['DRAM_read_GBs_original'])} / {f(r['DRAM_read_GBs'])} | {f(sub(r, 'imc_rd_GBs'))} | {f(sub(r, 'imc_wr_GBs'))} | "
              f"{f(r['offcore_data_rd_PKI'])} | {f(r['ocr_reads_to_core_l3_miss_PKI'])} | {f(r['ocr_demand_rfo_l3_miss_PKI'])} | "
              f"{w.get('mean_foreign_cpu_pct','?')} %, {w.get('rows_with_foreign_task','?')}/{w.get('witness_rows','?')} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
