#!/usr/bin/env python3
"""counter_pass_gates.py — hygiene gates of one dedicated-group counter pass on a Server workload.

The counter-pass counterpart of lbr_pass_gates.py (2026-11-04, the x86 TLB groups): the same
steady-state, completeness, witness and receipt rules, imported from it, plus the counter
instrument's own. Reads a finished pass (run_dcperf_profile.sh with PASS_GATES=1) and writes
<run>/gates.json; the pass is DONE only if `all_ok`.

  counter_pass_gates.py <run_dir> --group tlb_d --events cycles,instructions,... [--capture-s 180]
                        [--measured 4-11] [--winsec 0.1]

Gates (a gate whose input is missing FAILS):
  windows_ok    windows span >= 98 % of capture_s, and pitch <= 1.33 x WINSEC (perf is re-armed
                per window, ~22 ms on this box; a slower pitch means the house cores were starved)
  counted_ok    no window multiplexed (no "(xx.xx%)" annotation), and at most 1 % of windows with an
                event <not counted> / <not supported>: the SPEC validator's S1 rule (such a window is
                dropped by the aggregation, never read as zero; 0.12-0.16 % of SPEC windows)
  alive_ok      the server fence existed after every window (windows.tsv alive_after = 1)
  active_ok     >= 95 % of windows retire >= 5e5 instructions in the fence (the per-window
                analyzer's activity floor; below it a window yields no ratio)
  d4_ok, d5_ok, witness_ok, receipt_ok   lbr_pass_gates.py's rules, over [first window start,
                last window end]; a recorded receipt_override.json is honoured the same way
"""
import argparse
import json
import os
import re
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lbr_pass_gates import (D4_IDLE_CORES, D4_MAX_DRIFT, D5_MAX_RESID, cpus, d4, d5,  # noqa: E402
                            fence_core_s, rate_series, receipt_ok, receipt_summary, witness)

MUX = re.compile(r"\(\s*\d+[.,]\d+%\s*\)\s*$")
LINE = re.compile(r"^\s*([\d,]+|<not counted>|<not supported>)\s+(\S+)\s+(\S+)")
MIN_INSTR = 5e5
MAX_NOT_COUNTED_FRAC = 0.01


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--group", required=True)
    ap.add_argument("--events", required=True, help="the group's event list, as in GRP[...]")
    ap.add_argument("--capture-s", type=float, default=180)
    ap.add_argument("--measured", default="4-11")
    ap.add_argument("--winsec", type=float, default=0.1)
    a = ap.parse_args()
    out = a.run
    cg = open(f"{out}/.server_cg").read().strip()
    want = a.events.split(",")
    wins = []
    for ln in list(open(f"{out}/windows.tsv"))[1:]:
        p = ln.split()
        if len(p) >= 5 and p[1] == a.group:
            wins.append((p[0], float(p[2]), float(p[3]), p[4] == "1"))
    n = len(wins)
    t0, t1 = (wins[0][1], wins[-1][2]) if wins else (None, None)
    span = t1 - t0 if wins else 0.0
    pitch = span / n if n else None
    bad_count, mux, low = [], [], 0
    for w, _a, _b, _alive in wins:
        seen = {}
        for ln in open(f"{out}/group_{a.group}_w{w}.txt"):
            m = LINE.match(ln)
            if not m or cg not in m.group(3):
                continue
            seen[m.group(2)] = m.group(1)
            if MUX.search(ln.rstrip()):
                mux.append(w)
        miss = [e for e in want if not seen.get(e, "<").replace(",", "").isdigit()]
        if miss:
            bad_count.append((w, miss))
        elif float(seen["instructions"].replace(",", "")) < MIN_INSTR:
            low += 1
    series = rate_series(f"{out}/cpustat_scope1.tsv", t0, t1) if wins else []
    g4 = d4(series)
    g5 = d5(f"{out}/procstat_partition.tsv", fence_core_s(f"{out}/cpustat_scope1.tsv", t0, t1),
            cpus(a.measured), t0, t1) if wins else None
    wit = witness(f"{out}/witness.tsv", t0, t1) if wins else {"clean": False}
    try:
        rc = json.load(open(f"{out}/receipt_compare.json"))
    except Exception:  # noqa: BLE001 — unreadable is a failed gate
        rc = {"comparable": None, "reason": "receipt_compare.json missing or unreadable"}
    g = {
        "group": a.group, "events": want, "server_cg": cg, "ts_first_window": t0, "ts_last_window": t1,
        "n_windows": n, "span_s": round(span, 2), "pitch_s": round(pitch, 4) if pitch else None,
        "windows_ok": n > 0 and span >= 0.98 * a.capture_s and pitch <= 1.33 * a.winsec,
        "windows_not_counted": len(bad_count), "not_counted": bad_count,
        "windows_multiplexed": len(set(mux)),
        "counted_ok": n > 0 and not mux and len(bad_count) <= MAX_NOT_COUNTED_FRAC * n,
        "alive_ok": n > 0 and all(w[3] for w in wins),
        "windows_below_activity_floor": low,
        "active_ok": n > 0 and low <= 0.05 * n,
        "d4": g4, "d4_ok": bool(g4) and g4["drift_pct"] <= D4_MAX_DRIFT and g4["mean_cores"] >= D4_IDLE_CORES,
        "d5": g5, "d5_ok": bool(g5) and g5["residual_pct"] <= D5_MAX_RESID,
        "witness": wit, "witness_ok": bool(wit.get("clean")),
        "receipt": receipt_summary(rc), "receipt_ok": receipt_ok(rc),
        "thresholds": {"max_not_counted_frac": MAX_NOT_COUNTED_FRAC, "span_min_frac": 0.98, "pitch_max_x_winsec": 1.33, "active_min_frac": 0.95,
                       "min_instructions_per_window": MIN_INSTR, "d4_max_drift_pct": D4_MAX_DRIFT,
                       "d4_min_cores": D4_IDLE_CORES, "d5_max_residual_pct": D5_MAX_RESID},
    }
    ov = None
    if os.path.exists(f"{out}/receipt_override.json"):
        ov = json.load(open(f"{out}/receipt_override.json"))
    g["receipt_override"] = ov
    g["overrides"] = ["receipt"] if ov and not g["receipt_ok"] else []
    g["all_ok"] = all(g[k] for k in ("windows_ok", "counted_ok", "alive_ok", "active_ok", "d4_ok", "d5_ok",
                                     "witness_ok")) and (g["receipt_ok"] or bool(g["overrides"]))
    json.dump(g, open(f"{out}/gates.json", "w"), indent=1)
    med = st.median([w[2] - w[1] for w in wins]) if wins else None
    print(f"{a.group}: {'OK' if g['all_ok'] else 'FAIL'} windows={n} span={span:.1f}s pitch={pitch or 0:.3f}s "
          f"(median dur {med or 0:.3f}s) not_counted={len(bad_count)} mux={len(set(mux))} low={low} "
          f"D4={g4 and g4['drift_pct']}% load={g4 and g4['mean_cores']} D5={g5 and g5['residual_pct']}% "
          f"witness={'clean' if wit.get('clean') else 'CONTAMINATED/none'} "
          f"receipt={g['receipt'].get('ratio')} ({g['receipt'].get('comparable')})"
          + (f" OVERRIDE {g['overrides']}" if g["overrides"] else ""))
    return 0 if g["all_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
