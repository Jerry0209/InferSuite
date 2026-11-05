#!/usr/bin/env python3
"""aggregate_spec_tlb.py — the x86 TLB hierarchy of SPEC CPU 2026, next to ARM's.

Reads the tlb_d / tlb_i episodes (counter_group_episode.sh, GORDER_OVERRIDE="tlb_d tlb_i") after
extract_metrics.py and validate_spec.py have run over them, and writes spec26/tlb_x86/:
  spec_tlb_x86.csv     one row per benchmark: the TLB metrics (episode ratios of sums,
                       extract_metrics.py), the cross-check against the banked campaign's
                       itlb_walk_pct (same event, group fe_l3x, report 18), and the episode facts
  arm_vs_x86_tlb.csv   one row per (benchmark, metric pair): ARM ratio of sums (spec-arm,
                       spec26_arm_votes.csv) against the x86 value, with the pairing rule
  per_benchmark/<b>.metrics.json   the episode's metrics.json, as banked

  python3 aggregate_spec_tlb.py --data ~/spec26-infra/infra/data_tlb [--arm-ref origin/spec-arm]
Stdlib only.
"""
import argparse
import csv
import glob
import json
import os
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
METRICS = ["dTLB_L1_MPKI", "dTLB_L1_load_MPKI", "dTLB_L1_store_MPKI", "dTLB_walk_MPKI", "dTLB_STLB_hit_pct",
           "iTLB_L1_MPKI", "iTLB_walk_MPKI", "iTLB_STLB_hit_pct", "STLB_MPKI", "itlb_walk_pct", "dtlb_load_walk_pct"]
# ARM metric -> (x86 metric, pairing). L1D-TLB counts L1 data-TLB refills (loads and stores), the
# x86 L1 misses are STLB hits + completed walks. On Neoverse-V3 L2-TLB MPKI and DTLB-walk MPKI are
# the same count to 0.1 % (report 23 data), so both pair with the x86 data-side STLB misses.
PAIRS = [("L1D-TLB MPKI", "dTLB_L1_MPKI", "analogue: L1 data-TLB misses (x86 excludes aborted walks)"),
         ("L2-TLB MPKI", "dTLB_walk_MPKI", "analogue: data-side second-level TLB misses"),
         ("DTLB-walk MPKI", "dTLB_walk_MPKI", "analogue: completed data page walks"),
         ("L1I-TLB MPKI", "iTLB_L1_MPKI", "analogue: L1 instruction-TLB misses"),
         ("ITLB-walk MPKI", "iTLB_walk_MPKI", "analogue: completed instruction page walks")]


def git_show(ref, path):
    return subprocess.run(["git", "-C", REPO, "show", f"{ref}:{path}"], capture_output=True, text=True,
                          check=True).stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.expanduser("~/spec26-infra/infra/data_tlb"))
    ap.add_argument("--banked", default=f"{REPO}/spec26/infra_kit/x86_results")
    ap.add_argument("--arm-ref", default="origin/spec-arm")
    ap.add_argument("--out", default=f"{REPO}/spec26/tlb_x86")
    a = ap.parse_args()
    os.makedirs(f"{a.out}/per_benchmark", exist_ok=True)
    rows = []
    for d in sorted(glob.glob(f"{a.data}/7*_r")):
        b = os.path.basename(d)
        if not os.path.exists(f"{d}/metrics.json"):
            continue
        mj = json.load(open(f"{d}/metrics.json"))
        md = json.load(open(f"{d}/metadata.json"))
        shutil.copy(f"{d}/metrics.json", f"{a.out}/per_benchmark/{b}.metrics.json")
        m = mj.get("metrics", mj)
        try:
            bk = json.load(open(f"{a.banked}/{b}/metrics.json"))
            bk = bk.get("metrics", bk).get("itlb_walk_pct")
        except OSError:
            bk = None
        r = {"benchmark": b, "done": os.path.exists(f"{d}/DONE"), "wall_s": round(md.get("wall_s", 0), 1),
             "n_windows": int(open(f"{d}/n_windows").read()) if os.path.exists(f"{d}/n_windows") else None,
             "exit_status": md.get("bench_exit_status"), "output_check": (md.get("output_check") or {}).get("status"),
             "witness_rows_flagged": (md.get("foreign_witness") or {}).get("rows_with_foreign_task"),
             "IPC": m.get("IPC")}
        for k in METRICS:
            r[k] = m.get(k)
        r["itlb_walk_pct_banked_fe_l3x"] = bk
        r["itlb_walk_pct_rel_diff"] = (round((m["itlb_walk_pct"] - bk) / bk, 4)
                                       if bk and m.get("itlb_walk_pct") is not None else None)
        rows.append(r)
    with open(f"{a.out}/spec_tlb_x86.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        for x in rows:
            w.writerow({k: (round(v, 6) if isinstance(v, float) else v) for k, v in x.items()})
    arm = {}
    for r in csv.DictReader(git_show(a.arm_ref, "arm/data/processed/spec26/spec26_arm_votes.csv").splitlines()):
        arm[(r["benchmark"], r["metric"])] = float(r["ratio_of_sums"])
    x86 = {r["benchmark"]: r for r in rows}
    out = []
    for b in sorted(x86):
        for am, xm, rule in PAIRS:
            av, xv = arm.get((b, am)), x86[b].get(xm)
            out.append({"benchmark": b, "arm_metric": am, "arm_ratio_of_sums": av, "x86_metric": xm, "x86_value": xv,
                        "x86_over_arm": (xv / av) if av and xv is not None else None, "pairing": rule})
    with open(f"{a.out}/arm_vs_x86_tlb.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        for x in out:
            w.writerow({k: (round(v, 8) if isinstance(v, float) else v) for k, v in x.items()})
        fh.write(f"# ARM reference: {a.arm_ref}:arm/data/processed/spec26/spec26_arm_votes.csv (ratio_of_sums)\n")
    for r in rows:
        print(f"{r['benchmark']:18s} dL1={r['dTLB_L1_MPKI']} dWalk={r['dTLB_walk_MPKI']} iL1={r['iTLB_L1_MPKI']} "
              f"iWalk={r['iTLB_walk_MPKI']} itlb%={r['itlb_walk_pct']} (banked {r['itlb_walk_pct_banked_fe_l3x']})")
    print(f"wrote {a.out}/spec_tlb_x86.csv ({len(rows)} benchmarks), arm_vs_x86_tlb.csv")


if __name__ == "__main__":
    main()
