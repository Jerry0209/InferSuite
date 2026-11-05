#!/usr/bin/env python3
"""tlb_server_aggregate.py — the x86 TLB hierarchy of the 10 realistic Server workloads.

Reads the tlb_d / tlb_i passes (frontend_footprint_server.sh with FF_GROUPS="tlb_d tlb_i"
FF_SUBDIR=tlb_x86) and writes local_agents/tlb_x86/:
  server_tlb_x86.csv   one row per workload: each metric as a RATIO OF SUMS over the pass's
                       windows (the SPEC metrics.json convention, report 18) plus the window
                       median and IQR from analyze_l3_windows.py's per-window rows
  gates.csv            one row per pass: counter_pass_gates.py's verdicts and numbers
Formulas are extract_metrics.py's TLB block (spec-x86), restated here over the same events:
  dTLB_L1_MPKI  = 1000 (dlh + dlw + dsh + dsw) / I    dTLB_walk_MPKI = 1000 (dlw + dsw) / I
  iTLB_L1_MPKI  = 1000 (ih + iw) / I                  iTLB_walk_MPKI = 1000 iw / I
  dTLB_STLB_hit_pct = 100 (dlh + dsh) / (dlh + dlw + dsh + dsw), iTLB_STLB_hit_pct likewise
  itlb_walk_pct / dtlb_load_walk_pct = 100 walk_active / cycles;  STLB_MPKI = dTLB + iTLB walks
I and cycles are each group's own (co-counted), never summed across the two passes.

  python3 tlb_server_aggregate.py [--out local_agents/tlb_x86]
Stdlib only. Run analyze_l3_windows.py first (derive step in the report's recipe).
"""
import argparse
import csv
import glob
import json
import os
import re
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
WLS = [("DCPerf", "dcperf", "feedsim"), ("JVMbench", "dacapo", "tomcat"),
       ("JVMbench", "renaissance", "finagle-chirper"), ("JVMbench", "renaissance", "finagle-http"),
       ("RealData", "realdata", "cassandra-ycsb20m"), ("RealData", "realdata", "kafka-20g"),
       ("RealData", "realdata", "naivebayes-rcv1"), ("RealData", "realdata", "neo4j-livejournal"),
       ("RealData", "realdata", "pagerank-livejournal"), ("RealData", "realdata", "video-4k")]
LINE = re.compile(r"^\s*([\d,]+|<not counted>|<not supported>)\s+(\S+)\s+(\S+)")
METRICS = ["dTLB_L1_MPKI", "dTLB_L1_load_MPKI", "dTLB_L1_store_MPKI", "dTLB_walk_MPKI", "dTLB_STLB_hit_pct",
           "iTLB_L1_MPKI", "iTLB_walk_MPKI", "iTLB_STLB_hit_pct", "STLB_MPKI", "itlb_walk_pct", "dtlb_load_walk_pct"]


def sums(run, cg):
    """Event sums over the pass's windows, server fence only. A window with any event <not counted>
    is dropped whole (numerators and denominators: the co-counted rule), never read as zero."""
    S, n, dropped = {}, 0, []
    for f in sorted(glob.glob(f"{run}/group_*_w*.txt")):
        n += 1
        w = {}
        for ln in open(f):
            m = LINE.match(ln)
            if m and cg in m.group(3):
                w[m.group(2)] = m.group(1)
        if any(v.startswith("<") for v in w.values()):
            dropped.append(f.rsplit("_w", 1)[1][:-4])
            continue
        for ev, v in w.items():
            S[ev] = S.get(ev, 0.0) + float(v.replace(",", ""))
    return S, n, dropped


def ratios(d, i):
    g = lambda e: d.get(e, 0.0)  # noqa: E731
    out = {}
    if d:
        I = g("instructions")
        dlh, dlw, dsh, dsw = (g("dtlb_load_misses.stlb_hit"), g("dtlb_load_misses.walk_completed"),
                              g("dtlb_store_misses.stlb_hit"), g("dtlb_store_misses.walk_completed"))
        out.update(dTLB_L1_MPKI=1000 * (dlh + dlw + dsh + dsw) / I, dTLB_L1_load_MPKI=1000 * (dlh + dlw) / I,
                   dTLB_L1_store_MPKI=1000 * (dsh + dsw) / I, dTLB_walk_MPKI=1000 * (dlw + dsw) / I,
                   dTLB_STLB_hit_pct=100 * (dlh + dsh) / (dlh + dlw + dsh + dsw) if dlh + dlw + dsh + dsw else None)
    if i:
        I, C = i["instructions"], i["cycles"]
        ih, iw = i.get("itlb_misses.stlb_hit", 0.0), i.get("itlb_misses.walk_completed", 0.0)
        out.update(iTLB_L1_MPKI=1000 * (ih + iw) / I, iTLB_walk_MPKI=1000 * iw / I,
                   iTLB_STLB_hit_pct=100 * ih / (ih + iw) if ih + iw else None,
                   itlb_walk_pct=100 * i.get("itlb_misses.walk_active", 0.0) / C,
                   dtlb_load_walk_pct=100 * i.get("dtlb_load_misses.walk_active", 0.0) / C)
    if d and i:
        out["STLB_MPKI"] = out["dTLB_walk_MPKI"] + out["iTLB_walk_MPKI"]
    return out


def windows(fam, suite, wl, drop):
    """analyze_l3_windows.py rows for the server fence -> metric -> [values]; windows in drop
    ({(run, win)}: an event <not counted>, which the per-window derivation would read as 0) left out."""
    p = f"{REPO}/local_agents/{fam}/data/tlb_x86/l3_study/all_windows_{wl}.csv"
    v = {}
    if os.path.exists(p):
        for r in csv.DictReader(open(p)):
            if r["fence"] == "server" and (r["run"], r["win"]) not in drop:
                v.setdefault(r["metric"], []).append(float(r["value"]))
    return v


def q(vals, k):
    if len(vals) < 4:
        return None
    return st.quantiles(vals, n=4)[k]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=f"{REPO}/local_agents/tlb_x86")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rows, grows = [], []
    for fam, suite, wl in WLS:
        base = f"{REPO}/local_agents/{fam}/data/tlb_x86/{suite}_{wl}"
        per, ok, drop = {}, True, set()
        for run in sorted(glob.glob(f"{base}/run_*")):
            if not os.path.exists(f"{run}/l3group.txt"):
                continue
            grp = open(f"{run}/l3group.txt").read().strip()
            cg = open(f"{run}/.server_cg").read().strip()
            gj = json.load(open(f"{run}/gates.json")) if os.path.exists(f"{run}/gates.json") else {}
            done = os.path.exists(f"{run}/DONE")
            ok = ok and done and bool(gj.get("all_ok"))
            S, n, dr = sums(run, cg)
            per[grp] = S
            drop |= {(os.path.basename(run), w) for w in dr}
            rc = gj.get("receipt", {})
            grows.append({"workload": wl, "suite": suite, "run": os.path.basename(run), "group": grp, "done": done,
                          "all_ok": gj.get("all_ok"), "overrides": ";".join(gj.get("overrides", [])),
                          "n_windows": gj.get("n_windows"), "span_s": gj.get("span_s"), "pitch_s": gj.get("pitch_s"),
                          "counted_ok": gj.get("counted_ok"), "windows_multiplexed": gj.get("windows_multiplexed"),
                          "alive_ok": gj.get("alive_ok"), "active_ok": gj.get("active_ok"),
                          "d4_drift_pct": (gj.get("d4") or {}).get("drift_pct"),
                          "load_cores": (gj.get("d4") or {}).get("mean_cores"),
                          "d5_residual_pct": (gj.get("d5") or {}).get("residual_pct"),
                          "witness_clean": (gj.get("witness") or {}).get("clean"),
                          "receipt_metric": rc.get("metric"), "receipt_ratio": rc.get("ratio"),
                          "receipt_comparable": rc.get("comparable"), "receipt_basis": rc.get("basis"),
                          "fence_cores_new": rc.get("fence_cores_new"),
                          "windows_dropped_not_counted": len(dr),
                          "instructions": S.get("instructions"), "files": n})
        r = {"workload": wl, "suite": suite, "family": fam, "all_passes_ok": ok and len(per) == 2}
        rs = ratios(per.get("tlb_d"), per.get("tlb_i"))
        wv = windows(fam, suite, wl, drop)
        for m in METRICS:
            r[m] = rs.get(m)
            r[f"{m}_win_p25"], r[f"{m}_win_median"], r[f"{m}_win_p75"] = (
                q(wv.get(m, []), 0), st.median(wv[m]) if wv.get(m) else None, q(wv.get(m, []), 2))
        rows.append(r)
    for name, data in (("server_tlb_x86.csv", rows), ("gates.csv", grows)):
        with open(f"{a.out}/{name}", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(data[0]))
            w.writeheader()
            for x in data:
                w.writerow({k: (round(v, 6) if isinstance(v, float) else v) for k, v in x.items()})
    for r in rows:
        print(f"{r['workload']:22s} ok={r['all_passes_ok']!s:5s} " + " ".join(
            f"{m}={r[m]:.4g}" if r[m] is not None else f"{m}=-" for m in METRICS[:4] + METRICS[5:7] + METRICS[9:]))
    print(f"wrote {a.out}/server_tlb_x86.csv, gates.csv")


if __name__ == "__main__":
    main()
