#!/usr/bin/env python3
"""sample_matched.py — Server footprint and unique taken branches at SPEC's sample counts.

Unique counts are sampled lower bounds that keep growing with the number of samples (contract
§2), and a Server pass (8 cores x 180-300 s of steady state) collects far more samples than a
SPEC run (1 core, whole run). So a Server-vs-SPEC gap in the unique counts is partly a sample
count gap. The banked tables carry `first_seen` (the 1-based sample ordinal at which a line or
an edge first appeared, in time order), so each Server metric can be recomputed exactly over
its first N samples, with N set to SPEC's own sample counts. Nothing is re-captured.

  python3 sample_matched.py [--out local_agents/frontend_footprint_x86/sample_matched.csv]
                            [--spec-ref origin/spec-x86]

N = SPEC's median and maximum samples per run (26 runs, read from SPEC's per-benchmark
summaries on --spec-ref). A Server prefix of N samples is a shorter time window, all cores.
Footprint = 64 x lines with first_seen <= N; unique taken branches = distinct (from_obj,
from_off) over near edges with first_seen <= N. Stdlib only, system python3.
"""
import argparse
import csv
import glob
import json
import os
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
ROOTS = [f"{REPO}/local_agents/{f}/data/frontend_footprint" for f in ("DCPerf", "JVMbench", "RealData")]
NEAR = {"COND", "UNCOND", "CALL", "IND_CALL", "IND", "RET"}


def zcat(path):
    p = subprocess.Popen(["zstd", "-dc", path], stdout=subprocess.PIPE, text=True)
    next(p.stdout)                                   # header
    yield from p.stdout
    p.wait()


def spec_samples(ref):
    ls = subprocess.run(["git", "-C", REPO, "ls-tree", "--name-only", f"{ref}:spec26/frontend_footprint_x86/per_benchmark/"],
                        capture_output=True, text=True, check=True).stdout.split()
    out = {}
    for f in ls:
        s = json.loads(subprocess.run(["git", "-C", REPO, "show", f"{ref}:spec26/frontend_footprint_x86/per_benchmark/{f}"],
                                      capture_output=True, text=True, check=True).stdout)
        out[f.split(".summary")[0]] = s["diagnostics"]["samples"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=f"{REPO}/local_agents/frontend_footprint_x86/sample_matched.csv")
    ap.add_argument("--spec-ref", default="origin/spec-x86")
    a = ap.parse_args()
    spec = spec_samples(a.spec_ref)
    ns = {"spec_median": int(statistics.median(spec.values())), "spec_max": max(spec.values())}
    print(f"SPEC samples per run (n={len(spec)}): median {ns['spec_median']}, max {ns['spec_max']}", file=sys.stderr)
    rows = []
    for run in sorted(glob.glob(f"{ROOTS[0]}/*/run_1") + glob.glob(f"{ROOTS[1]}/*/run_1") + glob.glob(f"{ROOTS[2]}/*/run_1")):
        if not os.path.exists(f"{run}/DONE"):
            continue
        s = json.load(open(f"{run}/summary.json"))
        total = s["diagnostics"]["samples"]
        firsts = [int(ln.rsplit("\t", 1)[1]) for ln in zcat(f"{run}/lines.tsv.zst")]
        br = {}
        for ln in zcat(f"{run}/edges.tsv.zst"):
            fo, ff, _to, _tf, ty, _c, fs = ln.rstrip("\n").split("\t")
            if ty in NEAR:
                k = (fo, ff)
                br[k] = min(br.get(k, 1 << 62), int(fs))
        r = {"workload": s["workload"], "samples": total, "capture_s": s["capture"]["capture_s"],
             "footprint_bytes": s["footprint_bytes"], "unique_taken_branches": s["unique_taken_branches"]}
        if len(firsts) * 64 != s["footprint_bytes"] or len(br) != s["unique_taken_branches"]:
            sys.exit(f"{run}: tables do not reproduce the summary ({len(firsts) * 64} B, {len(br)} branches)")
        for tag, n in ns.items():
            n_eff = min(n, total)
            r[f"N_{tag}"] = n_eff
            r[f"footprint_bytes_at_{tag}"] = 64 * sum(1 for f in firsts if f <= n_eff)
            r[f"unique_taken_branches_at_{tag}"] = sum(1 for f in br.values() if f <= n_eff)
        rows.append(r)
        print(f"{r['workload']:22s} full {r['footprint_bytes']:>9d} B {r['unique_taken_branches']:>7d} br | "
              f"@{ns['spec_median']}: {r['footprint_bytes_at_spec_median']:>9d} B {r['unique_taken_branches_at_spec_median']:>7d} br | "
              f"@{ns['spec_max']}: {r['footprint_bytes_at_spec_max']:>9d} B {r['unique_taken_branches_at_spec_max']:>7d} br",
              file=sys.stderr)
    with open(a.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
        fh.write(f"# SPEC reference: {a.spec_ref}, n={len(spec)} runs; N = SPEC median ({ns['spec_median']}) "
                 f"and max ({ns['spec_max']}) samples per run\n")
    print(f"wrote {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
