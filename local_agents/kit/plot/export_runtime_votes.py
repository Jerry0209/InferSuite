#!/usr/bin/env python3
"""export_runtime_votes.py — ONE value per workload and metric, computed over the workload's
WHOLE RUNTIME (mentor's rule, 2026-09-15): sum the raw counters over every window the
workload was measured in, then take the ratio once. IPC = total instructions / total cycles;
branch MPKI = 1000 x total mispredictions / total instructions co-counted in the same windows;
DRAM GB/s = total bytes / total window seconds; context switches / CPU-s = total switches /
total task-clock. Not the median of per-window values (which weights every 100 ms equally,
busy or idle), and not a pool of windows.

Computed by the SPEC comparison kit's own loader, ~/spec26-infra/infra/scripts/
extract_metrics.py (load_episode + metrics), for all four families, so SPEC, the agentic 36,
DCPerf and the JVM suites go through one implementation. Denominators are co-counted: an
event's instructions are summed over exactly the windows in which that event was counted.

Runs: a SPEC benchmark is one execution with the counter groups rotating inside it (loaded
restricted to the nine groups the other families rotate, as the banked comparison does). An
agentic task, a DCPerf benchmark and a JVM benchmark are nine runs, one per group; their
counters are summed across all nine, so each metric comes from the run that carried its group
and IPC pools every run that counted plain cycles + instructions (all but priv).

Output: <out>/runtime_votes.csv with
    family     spec26 | agentic36 | dcperf | renaissance | dacapo
    subgroup   SPEC-int / SPEC-fp | language | DCPerf / Renaissance / DaCapo
    workload   name as in the figures
    metric     display label (the figures' vocabulary)
    value      the whole-runtime value
    windows    windows that carried the metric's counters
    runs       runs summed

    PY=~/miniforge3/envs/infersuite-full/bin/python3
    $PY local_agents/kit/plot/export_runtime_votes.py [--out DIR]
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import sys

REPO = os.path.expanduser("~/InferSuite")
SPEC_KIT = os.path.expanduser("~/spec26-infra/infra")
sys.path.insert(0, f"{SPEC_KIT}/scripts")
sys.path.insert(0, f"{REPO}/spec26/kit/plot")
from extract_metrics import load_episode, metrics  # noqa: E402
from spec_common import is_fp  # noqa: E402

SHARED9 = {"fpbr", "cache", "mlp", "fe", "fe_lat", "core_ports", "dram_bw", "priv", "fe_miss"}
# (extract_metrics key, display label, owning counter group)
METRICS = [
    ("IPC", "IPC", "all"),
    ("brMPKI", "Branch MPKI", "fpbr"),
    ("branchDir_MPKI", "Branch-direction MPKI", "fe_miss"),
    ("baclears_MPKI", "BTB MPKI (BAClears)", "fe_miss"),
    ("dsb_miss_MPKI", "uop-cache (DSB) MPKI", "fe_miss"),
    ("DSB_pct", "DSB coverage (%)", "fe"),
    ("L1I_MPKI", "L1I MPKI (code-read)", "fe_lat"),
    ("icache_data_stall_pct", "L1I stall (% cycles)", "fe_lat"),
    ("L1D_MPKI", "L1D-load MPKI", "cache"),
    ("L2_MPKI", "L2-load MPKI", "cache"),
    ("LLC_MPKI", "LLC MPKI", "cache"),
    ("L1D_missrate_pct", "L1D miss rate (%)", "cache"),
    ("L2_missrate_pct", "L2-load miss rate (%)", "cache"),
    ("LLC_missrate_pct", "LLC miss rate (%)", "cache"),
    ("DRAM_read_GBs", "DRAM read (GB/s)", "dram_bw"),
    ("ctx_per_cpu_s", "Context switches (/CPU-s)", "priv"),
]


def merged(run_dirs, only_groups=None):
    """load_episode over several run dirs, summing every accumulator."""
    S, coI, coC, secs, wins = {}, {}, {}, {}, {}
    n = 0
    for d in run_dirs:
        s, ci, cc, sc, wn, _defects = load_episode(d, only_groups)
        if not s:
            continue
        n += 1
        for acc, part in ((S, s), (coI, ci), (coC, cc), (secs, sc), (wins, wn)):
            for k, v in part.items():
                acc[k] = acc.get(k, 0) + v
    return S, coI, coC, secs, wins, n


def emit(w, family, subgroup, workload, run_dirs, only_groups=None):
    S, coI, coC, secs, wins, n = merged(run_dirs, only_groups)
    if not S:
        print(f"  skip {family}/{workload}: no windows", file=sys.stderr)
        return 0
    M = metrics(S, coI, coC, secs)
    k = 0
    for key, label, grp in METRICS:
        v = M.get(key)
        if v is None:
            continue
        nw = sum(c for g, c in wins.items() if g != "priv") if grp == "all" else wins.get(grp, 0)
        w.writerow([family, subgroup, workload, label, f"{v:.6g}", nw, n])
        k += 1
    return k


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=f"{REPO}/local_agents/JVMbench/data/l3_study")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    path = f"{a.out}/runtime_votes.csv"
    fh = open(path, "w", newline="")
    w = csv.writer(fh)
    w.writerow(["family", "subgroup", "workload", "metric", "value", "windows", "runs"])
    counts = {}

    # SPEC CPU 2026: one episode per benchmark, restricted to the nine shared groups
    for d in sorted(glob.glob(f"{SPEC_KIT}/data/*/")):
        name = os.path.basename(d.rstrip("/"))
        if not glob.glob(f"{d}/group_*_w*.txt"):
            continue
        sub = "SPEC-fp" if is_fp(name) else "SPEC-int"
        counts["spec26"] = counts.get("spec26", 0) + bool(emit(w, "spec26", sub, name, [d], SHARED9))

    # agentic 36: the count-view picks, nine dedicated-group replays each
    sel = [r for r in csv.DictReader(open(f"{REPO}/local_agents/ML_typeid/selection_36_count.tsv"), delimiter="\t")
           if "__" in r.get("instance", "")]
    for r in sel:
        disp = r["instance"].split("__", 1)[1]
        runs = sorted(glob.glob(f"{REPO}/local_agents/ML_iso36/data/glm_replay_swe_{r['short']}/run_*/"))
        runs = [x for x in runs if os.path.exists(f"{x}/DONE") or glob.glob(f"{x}/group_*_w*.txt")]
        if runs:
            counts["agentic36"] = counts.get("agentic36", 0) + bool(emit(w, "agentic36", r["lang"], disp, runs))

    # external suites profiled with kit/dcperf: nine runs each, EXCLUDED markers honoured
    for family, label, data in (("dcperf", "DCPerf", f"{REPO}/local_agents/DCPerf/data"),
                                ("renaissance", "Renaissance", f"{REPO}/local_agents/JVMbench/data"),
                                ("dacapo", "DaCapo", f"{REPO}/local_agents/JVMbench/data")):
        for d in sorted(glob.glob(f"{data}/{family}_*")):
            wl = os.path.basename(d)[len(family) + 1:]
            if os.path.exists(f"{d}/EXCLUDED"):
                continue
            runs = [x for x in sorted(glob.glob(f"{d}/run_*/")) if os.path.exists(f"{x}/DONE")]
            if runs:
                counts[family] = counts.get(family, 0) + bool(emit(w, family, label, wl, runs))
    fh.close()
    print(f"wrote {path}: workloads per family {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
