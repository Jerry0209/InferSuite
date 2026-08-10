#!/usr/bin/env python3
"""verify_placement.py — prove, from banked data, that a campaign's work actually ran on the
isolated cores and inside its fences. Configuration is a claim; this is the evidence.

    python3 spec26/kit/validate/verify_placement.py <capture-root> [--cpus 4-11] [--json OUT]

Two independent checks, neither of which trusts metadata.json:

  1. PLACEMENT — every 99 Hz `perf record` sample carries the CPU it landed on
     (`scope<N>_cpulanes.tsv`: monotonic-timestamp <TAB> cpu). If any sample sits outside the
     measured set, work escaped the partition. This matters most for the TOOL fence: the
     sandbox container is created by dockerd, not by our systemd-run, so it is fenced only
     because `apply_isolation` swaps docker's `cgroup-parent` to the measured slice. That swap
     is exactly the kind of thing that can silently stop working.

  2. RESIDUAL — per-CPU /proc/stat busy time on the measured cores (`procstat_partition.tsv`)
     minus the fences' own cgroup accounting (`cpustat_scope<N>.tsv`, `usage_usec`). What is
     left ran on the partition without belonging to a fence. Kernel threads belong to no
     cgroup, so the fence totals are a LOWER bound and a small positive residual is expected.

     Per-run residuals come out slightly NEGATIVE (~-0.5 %) and that is not an error:
     cpu.stat counts microseconds while /proc/stat counts 10 ms USER_HZ ticks, so the coarser
     instrument rounds down. Only the aggregate is meaningful.

Exit status: 0 if every sample is on the measured cores, 1 otherwise.
"""
from __future__ import annotations

import collections
import glob
import json
import os
import sys


def parse_cpus(spec: str) -> set[int]:
    out: set[int] = set()
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out |= set(range(int(a), int(b or a) + 1))
    return out


def placement(root: str, meas: set[int]) -> dict:
    per: dict[tuple[str, str], collections.Counter] = collections.defaultdict(collections.Counter)
    files = 0
    for f in sorted(glob.glob(f"{root}/*/run_*/scope*_cpulanes.tsv")):
        task = os.path.basename(os.path.dirname(os.path.dirname(f)))
        scope = os.path.basename(f).split("_")[0]
        files += 1
        for ln in open(f):
            p = ln.split()
            if len(p) < 2:
                continue
            try:
                per[(task, scope)][int(p[1])] += 1
            except ValueError:
                continue
    total = sum(sum(v.values()) for v in per.values())
    off = sum(n for v in per.values() for c, n in v.items() if c not in meas)
    cpus = sorted({c for v in per.values() for c in v})
    return {"cpulanes_files": files, "samples": total, "samples_off_partition": off,
            "cpus_observed": cpus,
            "per_fence": {f"{t}|{s}": {"samples": sum(v.values()), "cpus": sorted(v)}
                          for (t, s), v in sorted(per.items())}}


def residual(root: str, meas: set[int]) -> dict:
    tb = tf = 0.0
    runs = []
    for d in sorted(glob.glob(f"{root}/*/run_*")):
        pp = os.path.join(d, "procstat_partition.tsv")
        if not os.path.exists(pp):
            continue
        prev: dict[int, int] = {}
        busy = 0.0
        for ln in open(pp):
            f = ln.split()
            if len(f) < 9 or not f[1].startswith("cpu") or not f[1][3:].isdigit():
                continue
            c = int(f[1][3:])
            if c not in meas:
                continue
            v = list(map(int, f[2:9]))
            b = sum(v) - v[3]                       # everything except idle
            if c in prev:
                busy += (b - prev[c]) / 100.0       # USER_HZ ticks -> core-seconds
            prev[c] = b
        fenced = 0.0
        for cp in sorted(glob.glob(os.path.join(d, "cpustat_scope*.tsv"))):
            us = [int(p[p.index("usage_usec") + 1]) for p in
                  (ln.split() for ln in open(cp)) if "usage_usec" in p]
            us = [u for u in us if u >= 0]          # -1 is the post-teardown sentinel
            if len(us) > 1:
                fenced += (max(us) - min(us)) / 1e6
        tb += busy
        tf += fenced
        runs.append({"run": os.path.relpath(d, root), "busy_core_s": busy,
                     "fenced_core_s": fenced})
    return {"n_runs": len(runs), "busy_core_s": tb, "fenced_core_s": tf,
            "residual_core_s": tb - tf,
            "residual_pct": (100.0 * (tb - tf) / tb) if tb else None, "runs": runs}


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    root = args[0]
    cpus = args[args.index("--cpus") + 1] if "--cpus" in args else "4-11"
    outp = args[args.index("--json") + 1] if "--json" in args else None
    meas = parse_cpus(cpus)

    pl = placement(root, meas)
    rs = residual(root, meas)
    print(f"capture root : {root}")
    print(f"measured cpus: {cpus}")
    print(f"\nPLACEMENT  {pl['cpulanes_files']} cpulanes files, {pl['samples']:,} samples")
    print(f"           CPUs observed: {pl['cpus_observed']}")
    print(f"           samples off the measured set: {pl['samples_off_partition']:,}")
    print(f"\nRESIDUAL   {rs['n_runs']} runs")
    print(f"           busy on measured cores : {rs['busy_core_s']:>10,.1f} core-s")
    print(f"           accounted by fences    : {rs['fenced_core_s']:>10,.1f} core-s")
    print(f"           residual (unfenced)    : {rs['residual_core_s']:>10,.1f} core-s "
          f"({rs['residual_pct']:.1f} %)")
    ok = pl["samples_off_partition"] == 0
    print(f"\n{'PASS' if ok else 'FAIL'}: "
          + ("every sample ran on the measured cores" if ok else
             f"{pl['samples_off_partition']:,} samples escaped the partition"))
    if outp:
        json.dump({"root": root, "cpus_measured": cpus, "placement": pl, "residual": rs},
                  open(outp, "w"), indent=1)
        print(f"wrote {outp}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
