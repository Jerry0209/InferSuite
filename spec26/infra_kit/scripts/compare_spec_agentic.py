#!/usr/bin/env python3
"""compare_spec_agentic.py — put the SPEC CPU 2026 campaign next to the banked agentic
(SWE-agent x GLM) campaign on the eight CERTIFIED shared counter groups.

Two rules this file exists to enforce
-------------------------------------
1. BOTH SIDES ARE COMPUTED BY THE SAME CODE. Every number here comes from
   extract_metrics.py's own load_episode()/metrics(), run over each side's raw window
   files. If SPEC and the agents differ, it is because the workloads differ — not
   because two scripts implemented brMPKI slightly differently.

2. ONLY THE SHARED EIGHT GROUPS ARE USED. SPEC rotates 11 groups (the certified 8 plus
   mem_bound/fe_l3x/fe_miss); the agentic campaign rotated 8. Loading all 11 on the SPEC
   side would make whole-episode aggregates — IPC above all, which is total instructions
   over total cycles across ALL windows — sample a different group mix than the agentic
   side. Per-event ratios are immune because their denominators are already co-counted
   per group, but IPC is not, so the restriction is applied to both sides.

Nothing is written into the agentic data tree: it is read-only banked evidence, and its
metrics are computed in memory.

Standing caveats, printed with every run because they change interpretation:
  * SMT. The agentic runs are SMT-ON (measured 2-11,14-23; siblings share cores). SPEC
    is SMT-OFF (measured 4-11, siblings offlined). Cycle-normalised metrics — IPC, port
    utilisation, frontend bandwidth shares — cross that boundary badly. Per-instruction
    rates (brMPKI, the MPKIs) survive it far better.
  * CONTENTION. SPEC runs copies=1: one core, uncontended L3 and DRAM. The agentic
    workload ran many concurrent processes across the measured set and DID contend.
  * LLC_MPKI IS A DEMAND-MISS METRIC, NOT A MEMORY-BOUNDEDNESS METRIC. It counts
    retired loads that missed L3. Prefetch-friendly streaming code (SPEC FP) can move
    GB/s while reading ~0 here: 782.lbm_r measured 4.2 GB/s of DRAM reads against 3.4M
    demand misses over 27.5B L1 hits. Use DRAM_read_GBs and TMA mem_bound for memory
    pressure, and read LLC_MPKI as "how often the prefetcher failed".

usage: compare_spec_agentic.py <spec_data_dir> <agentic_run_dir> [<agentic_run_dir> ...]
"""
from __future__ import annotations

import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_metrics import load_episode, load_tma, metrics  # noqa: E402

# The shared rotation grew to NINE groups on 2026-08-21: the ML_iso36 campaign added
# fe_miss (BTB / uop-cache / branch-direction split) to the agentic side, which SPEC has
# always rotated. Including it here keeps IPC's window mix identical on both sides. NOTE
# for the RETIRED SWE_iso8 12-task population (8 groups, no fe_miss): re-running against
# those dirs adds SPEC fe_miss windows to IPC's denominator that the agentic side lacks —
# use the banked comparison_iso8.json for that population, don't recompute it.
SHARED8 = {"fpbr", "cache", "mlp", "fe", "fe_lat", "core_ports", "dram_bw", "priv", "fe_miss"}

# The metrics that are defined on the shared groups alone. Drill-group metrics
# (div_active_pct, stalls_*, ...) have no agentic counterpart and are excluded.
COMPARABLE = [
    ("IPC", "insn/cycle", 3),
    ("brMPKI", "misp/1000 insn", 2),
    ("DSB_pct", "% uops", 1),
    ("MITE_pct", "% uops", 1),
    ("MS_pct", "% uops", 1),
    ("LSD_pct", "% uops", 1),
    ("L1I_MPKI", "/1000 insn", 2),
    ("L1D_MPKI", "/1000 insn", 2),
    ("LLC_MPKI", "/1000 insn", 3),
    ("AMAT_cyc", "cycles", 2),
    ("MLP", "outstanding", 2),
    ("kernel_pct", "% cycles", 1),
    ("vecFP_pct", "% FP ops", 1),
    ("DRAM_read_GBs", "GB/s", 2),
    # 2026-08-21 additions: the fe_miss trio (previously unprofiled on the agentic side),
    # the L2/miss-rate ladder and icache-stall parity keys, and the context-switch rate.
    ("branchDir_MPKI", "misp/1000 insn", 2),
    ("baclears_MPKI", "/1000 insn", 3),
    ("dsb_miss_MPKI", "/1000 insn", 2),
    ("L2_MPKI", "/1000 insn", 2),
    ("L1D_missrate_pct", "% loads", 1),
    ("L2_missrate_pct", "% L1D misses", 1),
    ("LLC_missrate_pct", "% L2 misses", 1),
    ("icache_data_stall_pct", "% cycles", 2),
    ("ctx_per_cpu_s", "/CPU-s", 1),
]


def one(d: str) -> dict | None:
    """Shared-8 metrics for a single episode directory, computed in memory."""
    S, coI, coC, secs, wins, defects = load_episode(d, only_groups=SHARED8)
    if not S or not wins:
        return None
    M = metrics(S, coI, coC, secs)
    meta = {}
    mp = os.path.join(d, "metadata.json")
    if os.path.exists(mp):
        try:
            meta = json.load(open(mp))
        except Exception:
            meta = {}
    tma = load_tma(d)
    return {
        "dir": d,
        "name": meta.get("benchmark") or os.path.basename(os.path.dirname(d.rstrip("/"))) + "/" + os.path.basename(d.rstrip("/")),
        "metrics": M,
        "tma_l1": tma.get("l1", {}),
        "tma_l2": tma.get("l2", {}),
        "n_windows": sum(wins.values()),
        "groups": sorted(wins),
        "winsec": meta.get("winsec"),
        "smt": meta.get("smt"),
        "cpus_measured": meta.get("cpus_measured"),
        "defects": defects,
    }


def summarize(rows: list[dict], key: str):
    vals = [r["metrics"].get(key) for r in rows]
    vals = [v for v in vals if v is not None and v == v]
    if not vals:
        return None
    return {"n": len(vals), "median": statistics.median(vals),
            "min": min(vals), "max": max(vals)}


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    spec_root, agentic_dirs = sys.argv[1], sys.argv[2:]

    spec_rows = []
    for name in sorted(os.listdir(spec_root)):
        d = os.path.join(spec_root, name)
        if os.path.isdir(d):
            r = one(d)
            if r:
                spec_rows.append(r)

    ag_rows = []
    for d in agentic_dirs:
        if os.path.isdir(d):
            r = one(d)
            if r:
                ag_rows.append(r)

    if not spec_rows or not ag_rows:
        print(f"need both sides: spec={len(spec_rows)} agentic={len(ag_rows)}")
        return 1

    # --- provenance: state the conditions rather than assume they match
    def conds(rows, label):
        ws = sorted({r["winsec"] for r in rows})
        smt = sorted({str(r["smt"]) for r in rows})
        cpus = sorted({str(r["cpus_measured"]) for r in rows})
        print(f"  {label:<8} n={len(rows):<3} winsec={ws} smt={smt} measured={cpus}")

    print("=" * 100)
    print("SPEC CPU 2026 vs agentic (SWE-agent x GLM) — shared 8 counter groups only")
    print("=" * 100)
    conds(spec_rows, "SPEC")
    conds(ag_rows, "agentic")

    defect_n = sum(len(r["defects"]) for r in spec_rows + ag_rows)
    print(f"  defects across all episodes: {defect_n}"
          + ("  <-- INVESTIGATE" if defect_n else "  (clean)"))

    print("\n" + "-" * 112)
    print(f"{'metric':<16}{'unit':<15}{'SPEC median':>13}{'n':>5}{'agentic median':>16}{'n':>5}"
          f"{'ratio':>9}   {'SPEC range':>22}")
    print("-" * 112)
    out = {}
    n_spec_total, n_ag_total = len(spec_rows), len(ag_rows)
    for key, unit, prec in COMPARABLE:
        s, a = summarize(spec_rows, key), summarize(ag_rows, key)
        if not s or not a:
            print(f"{key:<16}{unit:<15}{'—':>13}{'0':>5}{'—':>16}{'0':>5}"
                  f"{'':>9}   never measured on one side")
            continue
        ratio = (s["median"] / a["median"]) if a["median"] else float("nan")
        out[key] = {"spec": s, "agentic": a, "ratio": ratio,
                    "spec_n_of": n_spec_total, "agentic_n_of": n_ag_total}
        # n is shown per metric, not once for the table: a metric whose counter group
        # never got a window in some episodes is a median over FEWER episodes, and that
        # must be visible rather than implied to cover the whole set.
        smark = "" if s["n"] == n_spec_total else "*"
        amark = "" if a["n"] == n_ag_total else "*"
        print(f"{key:<16}{unit:<15}{s['median']:>13.{prec}f}{str(s['n'])+smark:>5}"
              f"{a['median']:>16.{prec}f}{str(a['n'])+amark:>5}"
              f"{ratio:>9.2f}x   [{s['min']:.{prec}f}, {s['max']:.{prec}f}]")
    if any(o["spec"]["n"] != n_spec_total or o["agentic"]["n"] != n_ag_total
           for o in out.values()):
        print(f"\n  * median covers fewer than all episodes (SPEC {n_spec_total}, "
              f"agentic {n_ag_total}): that metric's counter group never got a window "
              f"in the rest.")

    # --- TMA, the least SMT-sensitive of the whole-workload views
    print("\n" + "-" * 100)
    print("TMA level 1 (share of pipeline slots)")
    print("-" * 100)
    print(f"{'level':<16}{'SPEC median':>14}{'agentic median':>16}")
    for k in ("retiring", "bad_spec", "fe_bound", "be_bound"):
        sv = [r["tma_l1"].get(k) for r in spec_rows if r["tma_l1"].get(k) is not None]
        av = [r["tma_l1"].get(k) for r in ag_rows if r["tma_l1"].get(k) is not None]
        if sv and av:
            print(f"{k:<16}{statistics.median(sv):>13.1f}%{statistics.median(av):>15.1f}%")
            out.setdefault("tma_l1", {})[k] = {"spec": statistics.median(sv),
                                               "agentic": statistics.median(av)}

    print("\n" + "=" * 100)
    print("READ WITH THESE CONDITIONS ATTACHED")
    print("=" * 100)
    print("  SMT        agentic SMT-ON vs SPEC SMT-OFF. IPC / port / frontend-bandwidth")
    print("             shares cross that boundary badly; per-instruction rates survive it.")
    print("  CONTENTION SPEC copies=1 is uncontended (one core owns L3 + DRAM); the agentic")
    print("             workload ran many concurrent processes and DID contend.")
    print("  LLC_MPKI   demand-load L3 misses, NOT memory-boundedness. Prefetch-friendly SPEC")
    print("             FP code reads ~0 while streaming GB/s. Use DRAM_read_GBs / TMA mem_bound.")

    # SPEC_COMPARISON_OUT lets a second agentic population be compared without clobbering the
    # first: the 2026-08-07 re-capture put the agentic replays on the SPEC configuration
    # (cores 4-11 SMT-off, 100 ms windows), and both files are needed to show what the old
    # SMT-on / 5 s caveat was actually worth.
    outp = os.environ.get("SPEC_COMPARISON_OUT") or os.path.join(spec_root, "..", "comparison.json")
    json.dump({"spec": spec_rows, "agentic": ag_rows, "comparison": out},
              open(outp, "w"), indent=1)
    print(f"\nwrote {os.path.normpath(outp)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
