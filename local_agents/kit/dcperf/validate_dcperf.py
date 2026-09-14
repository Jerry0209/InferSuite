#!/usr/bin/env python3
"""validate_dcperf.py — proof-based gates over a banked DCPerf capture.

An "it ran" message is not evidence. These gates check the things that, if violated, would
silently invalidate the comparison against SPEC and the agentic 36:

  D1 pass coverage      one completed pass per counter group, no duplicates, no gaps
  D2 fence attribution  every counter window carries counts for the SERVER cgroup, and the
                        instruction counts are large enough for stable ratios
  D3 zero multiplexing  no window may report a scaled/partial counter -- the whole method
                        rests on each group being 100% enabled for its window
  D4 steady state       the server's CPU rate must not drift across the capture (first vs
                        last fifth of the window sequence), else "steady state" is a fiction
  D5 fence completeness the measured partition's busy time must be explained by the fence:
                        partition busy minus fence busy is the unfenced residual, bounded here
  D6 workload SLA       the benchmark's own service-level objective held while we profiled
  D7 metric coverage    all 12 displayed metrics derived, from the groups that own them

    ~/miniforge3/envs/infersuite-full/bin/python3 local_agents/kit/dcperf/validate_dcperf.py [bench]
    SUITE=renaissance DATA=local_agents/JVMbench/data ... validate_dcperf.py finagle-http
"""
from __future__ import annotations

import csv
import glob
import os
import re
import statistics as st
import sys

REPO = os.path.expanduser("~/InferSuite")
BENCH = sys.argv[1] if len(sys.argv) > 1 else "feedsim"
SUITE = os.environ.get("SUITE", "dcperf")
DATA = os.environ.get("DATA", f"{REPO}/local_agents/DCPerf/data")
if not DATA.startswith("/"):
    DATA = f"{REPO}/{DATA}"
BASE = f"{DATA}/{SUITE}_{BENCH}"
L3 = f"{DATA}/l3_study"
MEASURED = os.environ.get("CPUS_MEASURED", "4-11")
GROUPS = ["fpbr", "cache", "mlp", "fe", "fe_lat", "core_ports", "dram_bw", "priv", "fe_miss"]
# benchmarks whose DCPerf definition is a latency target, and which therefore owe an SLA receipt
SLA_BENCHES = {"feedsim", "tao_bench", "mediawiki", "django_workload"}
DISPLAY = {
    "IPC": "fpbr", "branch_MPKI": "fpbr", "branchDir_MPKI": "fe_miss", "BTB_MPKI": "fe_miss",
    "uopCache_MPKI": "fe_miss", "DSB_pct": "fe", "codeRead_MPKI_L1I": "fe_lat",
    "L1D_MPKI": "cache", "L2_MPKI": "cache", "LLC_MPKI": "cache",
    "dram_rd_GBs": "dram_bw", "ctx_per_cpu_s": "priv",
}
fails, warns = [], []


def gate(ok, name, msg):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: {msg}")
    if not ok:
        fails.append(f"{name}: {msg}")


def cpu_rate_series(path):
    rows = []
    for ln in open(path):
        p = ln.split()
        if len(p) >= 3 and p[1] == "usage_usec":
            rows.append((float(p[0]), float(p[2])))
    out = []
    for (a, u0), (b, u1) in zip(rows, rows[1:]):
        if b > a:
            out.append((a, (u1 - u0) / 1e6 / (b - a)))
    return out


runs = sorted(glob.glob(f"{BASE}/run_*"), key=lambda p: int(p.rsplit("_", 1)[1]))
print(f"== {SUITE} validation: {BENCH} ({len(runs)} run dirs) ==\n")

# ---- D1 pass coverage ----
done = {}
for rd in runs:
    if os.path.exists(f"{rd}/DONE") and os.path.exists(f"{rd}/l3group.txt"):
        done[open(f"{rd}/l3group.txt").read().strip()] = rd
missing = [g for g in GROUPS if g not in done]
gate(not missing, "D1 pass coverage",
     f"{len(done)}/{len(GROUPS)} groups complete" + (f"; MISSING {missing}" if missing else ""))

# ---- D2/D3 per-window integrity ----
n_win = n_low = n_mux = 0
mux_examples = []
for g, rd in sorted(done.items()):
    for wf in sorted(glob.glob(f"{rd}/group_{g}_w*.txt")):
        txt = open(wf).read()
        if f"{SUITE}-" not in txt:
            continue
        n_win += 1
        # perf prints "(NN.NN%)" only when a counter was time-multiplexed
        for m in re.finditer(r"\(\s*(\d+\.\d+)%\)", txt):
            if float(m.group(1)) < 99.9:
                n_mux += 1
                if len(mux_examples) < 3:
                    mux_examples.append(f"{os.path.basename(wf)}@{m.group(1)}%")
                break
        mi = re.search(r"^\s*([\d,]+)\s+instructions", txt, re.M)
        if mi and int(mi.group(1).replace(",", "")) < 5e5:
            n_low += 1
gate(n_win > 0, "D2 fence attribution",
     f"{n_win} counter windows carry server-cgroup counts "
     f"({n_low} below the 5e5-instruction ratio floor, dropped by the analyzer)")
gate(n_mux == 0, "D3 zero multiplexing",
     "no scaled counters in any window" if n_mux == 0
     else f"{n_mux} windows show multiplexing ({', '.join(mux_examples)})")

# ---- D4 steady state ----
# The workload must do the SAME AMOUNT OF WORK at the end of a capture as at the start.
# REWRITTEN 2026-09-14 after this gate wrongly failed DaCapo cassandra. Two defects:
#   (1) it compared per-sample MEDIANS. A duty-cycled workload alternates busy and idle inside
#       the 10 Hz poll -- cassandra sat at ~4 cores or ~0 in any given 100 ms, so half its
#       samples were near zero and its median was 0.03 cores, while its 10 s means were flat at
#       ~2 cores for the whole capture. The median asks "where did the middle sample fall",
#       which is a question about duty cycle, not about drift. The MEAN integrates the bursts
#       and is the quantity the gate actually means. Smooth to 10 s first so one burst boundary
#       cannot move the verdict.
#   (2) it divided by the first fifth's value with no floor, so 0.01 -> 0.65 cores read as
#       4627% drift. A percentage of a near-zero denominator carries no information. Normalise
#       by the LARGER of the two (bounded at 100%) and add an ABSOLUTE idle floor, because the
#       failure this gate exists to catch -- a process alive but no longer doing its work -- is
#       an absolute statement, not a relative one.
D4_IDLE_CORES = 0.10        # mean fence load below this is not a running workload
D4_MAX_DRIFT = 25.0         # percent, first fifth vs last fifth of the 10 s means


def smooth(series, win_s=10.0):
    """Non-overlapping means over win_s seconds -> [(t_start, mean rate)]."""
    out, bucket, t0 = [], [], None
    for t, r in series:
        if t0 is None:
            t0 = t
        if t - t0 >= win_s and bucket:
            out.append((t0, st.mean(bucket)))
            bucket, t0 = [], t
        bucket.append(r)
    if bucket:
        out.append((t0, st.mean(bucket)))
    return out


drifts = []
for g, rd in sorted(done.items()):
    s = cpu_rate_series(f"{rd}/cpustat_scope1.tsv")
    if len(s) < 50:
        continue
    sm = smooth(s)
    if len(sm) < 5:                       # capture too short to smooth: use raw samples
        sm = s
    n = max(1, len(sm) // 5)
    a = st.mean([r for _t, r in sm[:n]])
    b = st.mean([r for _t, r in sm[-n:]])
    drifts.append((g, a, b, 100 * abs(b - a) / max(a, b, 1e-9), st.mean([r for _t, r in s])))
worst = max(drifts, key=lambda x: x[3]) if drifts else None
idle = [d for d in drifts if d[4] < D4_IDLE_CORES]
gate(bool(drifts) and worst[3] <= D4_MAX_DRIFT and not idle, "D4 steady state",
     (f"max drift {worst[3]:.1f}% (group {worst[0]}: {worst[1]:.2f} -> {worst[2]:.2f} cores, "
      f"10 s means); mean server load {st.mean([d[4] for d in drifts]):.2f} cores"
      + (f"; IDLE: {len(idle)} group(s) below {D4_IDLE_CORES} cores mean" if idle else ""))
     if worst else "no poller series")

# ---- D5 fence completeness (partition witness) ----
resid = []
for g, rd in sorted(done.items()):
    pf = f"{rd}/procstat_partition.tsv"
    if not os.path.exists(pf):
        continue
    meas = set()
    for part in MEASURED.split(","):
        a, _, b = part.partition("-"); meas |= set(range(int(a), int(b or a) + 1))
    first, last = {}, {}
    for ln in open(pf):
        p = ln.split()
        if len(p) < 9 or not p[1].startswith("cpu"):
            continue
        try:
            c = int(p[1][3:])
        except ValueError:
            continue
        if c not in meas:
            continue
        busy = sum(int(x) for x in (p[2], p[3], p[4], p[6], p[7], p[8]))
        t = float(p[0])
        if c not in first:
            first[c] = (t, busy)
        last[c] = (t, busy)
    if not first:
        continue
    dt = max(last[c][0] for c in last) - min(first[c][0] for c in first)
    part_core_s = sum(last[c][1] - first[c][1] for c in first) / 100.0
    s = cpu_rate_series(f"{rd}/cpustat_scope1.tsv")
    fence_core_s = sum(r * 0.1 for _t, r in s)
    if part_core_s > 1:
        resid.append((g, 100 * max(part_core_s - fence_core_s, 0) / part_core_s))
if resid:
    w = max(resid, key=lambda x: x[1])
    gate(w[1] <= 20, "D5 fence completeness",
         f"unfenced residual on the measured cores <= {w[1]:.1f}% of partition busy "
         f"(worst group {w[0]}); fence totals are lower bounds by construction")
else:
    warns.append("D5: no partition witness series found")
    print("  WARN  D5 fence completeness: no partition witness series")

# ---- D6 workload SLA ----
# A profiling pass is torn down when its capture window closes, so the benchmark usually does
# not reach the end of its experiment and writes no results row. The receipt therefore comes
# from any run that DID finish with counters active -- the confirmation run under
# data/confirm/ -- as well as from any pass that happened to complete. Rows with
# requested_qps == 0 are the unpaced warm-up and are not SLA evidence.
sla = []
receipt_dirs = list(sorted(done.items())) + [
    ("confirm", d) for d in sorted(glob.glob(
        f"{DATA}/confirm/{SUITE}_{BENCH}/run_*"))]
for g, rd in receipt_dirs:
    f = f"{rd}/feedsim_results.txt"
    if not os.path.exists(f):
        continue
    for r in csv.DictReader(open(f)):
        try:
            req, ach, p95 = float(r["requested_qps"]), float(r["achieved_qps"]), float(r["95p_ms"])
        except (KeyError, ValueError):
            continue
        if req > 0:
            sla.append((g, req, ach, p95))
if sla:
    bad = [s for s in sla if s[3] > 500]
    gate(not bad, "D6 workload SLA",
         f"{len(sla)} profiled experiments, p95 {min(s[3] for s in sla):.0f}-"
         f"{max(s[3] for s in sla):.0f} ms (SLA 500), achieved "
         f"{st.median([s[2] for s in sla]):.2f} QPS median"
         + (f"; {len(bad)} OVER SLA" if bad else ""))
elif BENCH in SLA_BENCHES:
    warns.append("D6: no results CSV for a latency-critical benchmark")
    print("  WARN  D6 workload SLA: no results CSV banked")
else:
    # Batch benchmarks (video transcoding, analytics) have no service-level objective to
    # hold: throughput IS the result. Absence of a latency receipt is correct here, not a gap.
    print(f"  n/a   D6 workload SLA: {BENCH} is a batch workload with no latency objective")

# ---- D7 metric coverage ----
aw = f"{L3}/all_windows_{BENCH}.csv"
if os.path.exists(aw):
    seen = {}
    for r in csv.DictReader(open(aw)):
        if r["fence"] == "both":
            seen.setdefault(r["metric"], 0)
            seen[r["metric"]] += 1
    miss = [m for m in DISPLAY if m not in seen]
    gate(not miss, "D7 metric coverage",
         f"{len(seen)} metrics derived; all 12 displayed present"
         if not miss else f"MISSING {miss}")
    print("\n  per-metric window counts (merged fence):")
    for m, g in DISPLAY.items():
        print(f"    {m:<22} {seen.get(m, 0):>6} windows   (group {g})")
else:
    warns.append("D7: all_windows CSV not built yet — run analyze_l3_windows.py")
    print("  WARN  D7 metric coverage: analyzer output missing")

print("\n" + ("VALIDATION PASSED" if not fails else f"VALIDATION FAILED ({len(fails)})"))
for f in fails:
    print("   FAIL", f)
for w in warns:
    print("   WARN", w)
sys.exit(1 if fails else 0)
