#!/usr/bin/env python3
"""realised_clock.py — the clock the measured cores ACTUALLY ran at during a capture.

The shield pins the measured cores (governor performance, no_turbo=1, scaling_min = scaling_max
= base_frequency) and ISO-PROOF verifies the knobs; this tool measures the outcome from the
banked counters instead of trusting the knobs. The `priv` counter group counts, per 100 ms
window and per fence cgroup, `task-clock` (CPU-seconds the fence's tasks were scheduled) and
`cycles:u` + `cycles:k` (unhalted cycles while they ran), so

    realised GHz = (cycles:u + cycles:k) / task-clock

is the mean unhalted clock over the fence's own CPU time. It is 3.19 on a busy pinned core; it
falls below the pin when a workload wakes idle cores constantly (post-idle ramp), which is a
property of the workload under identical settings, not a shield defect -- see
local_agents/DCPerf/README.md §9.

Layouts understood: one-pass-per-group sweeps (<workload>/run_N/l3group.txt == priv, DCPerf and
the JVM suites), shuffled-rotation campaigns (priv windows in every run_N, ML_iso36), and the
SPEC kit (group files directly under <benchmark>/).

    PY=~/miniforge3/envs/infersuite-full/bin/python3
    $PY local_agents/kit/validate/realised_clock.py local_agents/DCPerf/data local_agents/JVMbench/data \
        local_agents/ML_iso36/data ~/spec26-infra/infra/data [--csv out.csv] [--min-windows 20]
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import re
import statistics as st
import sys

NUM = re.compile(r"^\s*([\d,\.]+)\s+(?:msec\s+)?(\S+)\s+(\S+)")
EL = re.compile(r"^\s*([\d\.]+) seconds time elapsed")


def parse_window(path: str):
    """-> (task_clock_ms, cycles_u, cycles_k, ctx_switches) or None."""
    d = {}
    for ln in open(path, errors="replace"):
        if EL.match(ln):
            continue
        m = NUM.match(ln)
        if m:
            try:
                d[m.group(2)] = float(m.group(1).replace(",", ""))
            except ValueError:
                pass
    t, cu, ck = d.get("task-clock"), d.get("cycles:u"), d.get("cycles:k")
    if not t or cu is None or ck is None or t < 1.0:   # <1 ms of fence time: no clock to speak of
        return None
    return t, cu, ck, d.get("context-switches")


def family_of(root: str) -> str:
    """DCPerf/data -> DCPerf, ML_iso36/data -> ML_iso36, spec26-infra/infra/data -> spec26."""
    root = os.path.abspath(os.path.expanduser(root))
    fam = os.path.basename(root)
    if fam == "data":
        fam = os.path.basename(os.path.dirname(root))
    return "spec26" if fam == "infra" else fam


def workload_dirs(root: str):
    root = os.path.expanduser(root)
    fam = family_of(root)
    for wl in sorted(glob.glob(os.path.join(root, "*"))):
        if not os.path.isdir(wl):
            continue
        files = glob.glob(os.path.join(wl, "run_*", "group_priv_w*.txt")) or \
            glob.glob(os.path.join(wl, "group_priv_w*.txt"))
        if files:
            yield fam, os.path.basename(wl), files


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("roots", nargs="+", help="data roots whose children are workload dirs")
    ap.add_argument("--csv", help="also write one row per workload here")
    ap.add_argument("--min-windows", type=int, default=20)
    a = ap.parse_args()
    rows = []
    for root in a.roots:
        for fam, wl, files in workload_dirs(root):
            cyc = tc = ctx = 0.0
            n = 0
            for f in files:
                w = parse_window(f)
                if not w:
                    continue
                t, cu, ck, cs = w
                cyc += cu + ck
                tc += t
                ctx += cs or 0.0
                n += 1
            if n < a.min_windows:
                continue
            rows.append({"family": fam, "workload": wl, "priv_windows": n,
                         "fence_cpu_s": round(tc / 1000, 1),
                         "realised_GHz": round(cyc / (tc * 1e6), 3),
                         "ctx_per_cpu_s": round(ctx / (tc / 1000), 0)})
    if not rows:
        print("no priv windows found", file=sys.stderr)
        return 1
    print(f"{'family':12s} {'workload':42s} {'windows':>7s} {'CPU-s':>8s} {'GHz':>6s} {'ctx/CPU-s':>10s}")
    for r in rows:
        print(f"{r['family']:12s} {r['workload']:42s} {r['priv_windows']:7d} {r['fence_cpu_s']:8.1f} "
              f"{r['realised_GHz']:6.3f} {r['ctx_per_cpu_s']:10.0f}")
    print()
    for fam in dict.fromkeys(r["family"] for r in rows):
        g = [r["realised_GHz"] for r in rows if r["family"] == fam]
        print(f"{fam:12s} n={len(g):2d}  realised GHz median {st.median(g):.3f}  min {min(g):.3f}  max {max(g):.3f}")
    if a.csv:
        with open(a.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
