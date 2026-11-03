#!/usr/bin/env python3
"""lbr_pass_gates.py — hygiene gates of one Server front-end footprint pass (contract v1.1 §5 V4).

Reads a finished pass directory (lbr_pass.sh output) and writes <run>/summary.json: the
analyzer's summary plus `workload`, `capture`, `exact_counts` and `gates_v4`, the same layout
as the SPEC episodes, so one aggregation and plotting path reads both. Every verdict is banked,
pass or fail; the pass is DONE only if `gates_v4.all_ok`.

  lbr_pass_gates.py <run_dir> --analyzer-rc N [--period 20011] [--cover-tol 0.005] [--measured 4-11]

Gates (a gate whose input is missing FAILS; nothing is assumed):
  analyzer_ok   lbr_footprint exited 0 and wrote its summary
  contract_ok   the recorded event, period and branch filter are the contract's (v1.1)
  lost_ok       lost samples < 1 % of samples (contract §3)
  coverage_ok   samples x period / exact br_inst_retired.near_taken (perf stat, same fence,
                window nested inside the record's) within +-cover-tol. Detects ring-buffer loss
                and kernel throttling, from two independent subsystems
  throttle_ok   zero THROTTLE records (perf report --stats): throttling drops samples in the hot
                phases and biases the unique counts
  alive_ok      the server fence existed for the whole window
  mapped_ok     < 1 % of LBR entries at addresses perf knows no mapping for. Unmapped user code
                yields no ranges and no canonical keys; a non-root perf facing a root server
                left 98 % unmapped and every other gate passed (feedsim smoke, 2026-11-03)
  d4_ok         steady state, the validator's D4 rule (validate_dcperf.py): 10 s means of the
                fence's cpu.stat rate over the window, first fifth vs last fifth, drift <= 25 %
                of the larger, and mean load >= 0.10 cores
  d5_ok         fence completeness, D5 rule: measured-partition busy (/proc/stat) not explained
                by the fence's cpu.stat <= 20 % of partition busy
  witness_ok    no other user's task busy on the machine during the window (the SPEC rule from
                llc_dram_crosscheck.sh: <= 5 % of 2 s rows with a task > 10 % of a CPU, mean
                foreign load <= 25 %); root kernel threads are not counted as such a task
  receipt_ok    receipt_compare.py: the workload's own throughput receipt is comparable with
                the 9 banked counter passes (rule in that script). video-4k only: no receipt
                exists by design (none of its banked passes has one), the fence load is the proxy.
                A failed receipt can be accepted only by a recorded human decision,
                <run>/receipt_override.json; receipt_ok stays False and gates_v4.overrides names it
"""
import argparse
import csv
import json
import os
import re
import statistics as st
import sys

D4_IDLE_CORES, D4_MAX_DRIFT, D5_MAX_RESID = 0.10, 25.0, 20.0
CONTRACT_EVENT, CONTRACT_FILTER = "br_inst_retired.near_taken:pp", "any,save_type"   # contract v1.1


def cpus(spec):
    out = set()
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out |= set(range(int(a), int(b or a) + 1))
    return out


def rate_series(path, t0, t1):
    """10 Hz cpu.stat -> [(t, cores)] restricted to [t0, t1]; -1 sentinels (no cgroup) dropped."""
    rows = []
    try:
        for ln in open(path):
            p = ln.split()
            if len(p) >= 3 and p[1] == "usage_usec" and float(p[2]) >= 0 and t0 <= float(p[0]) <= t1:
                rows.append((float(p[0]), float(p[2])))
    except OSError:
        return []
    return [(a, (u1 - u0) / 1e6 / (b - a)) for (a, u0), (b, u1) in zip(rows, rows[1:]) if b > a]


def fence_core_s(path, t0, t1):
    """Fence CPU time over [t0, t1] from the first and last cpu.stat sample inside it."""
    rows = []
    try:
        for ln in open(path):
            p = ln.split()
            if len(p) >= 3 and p[1] == "usage_usec" and float(p[2]) >= 0 and t0 <= float(p[0]) <= t1:
                rows.append(float(p[2]))
    except OSError:
        return None
    return (rows[-1] - rows[0]) / 1e6 if len(rows) > 1 else None


def smooth(series, win_s=10.0):
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


def d4(series):
    if len(series) < 50:
        return None
    sm = smooth(series)
    if len(sm) < 5:
        sm = series
    n = max(1, len(sm) // 5)
    a, b = st.mean([r for _t, r in sm[:n]]), st.mean([r for _t, r in sm[-n:]])
    return {"first_fifth_cores": round(a, 3), "last_fifth_cores": round(b, 3),
            "drift_pct": round(100 * abs(b - a) / max(a, b, 1e-9), 2),
            "mean_cores": round(st.mean([r for _t, r in series]), 3)}


def d5(path, fence_core_s, meas, t0, t1):
    first, last = {}, {}
    try:
        for ln in open(path):
            p = ln.split()
            if len(p) < 9 or not p[1].startswith("cpu"):
                continue
            t = float(p[0])
            if not t0 <= t <= t1:
                continue
            try:
                c = int(p[1][3:])
            except ValueError:
                continue
            if c not in meas:
                continue
            busy = sum(int(x) for x in (p[2], p[3], p[4], p[6], p[7], p[8]))
            first.setdefault(c, (t, busy))
            last[c] = (t, busy)
    except OSError:
        return None
    if not first:
        return None
    part = sum(last[c][1] - first[c][1] for c in first) / 100.0          # USER_HZ = 100
    span = max(last[c][0] for c in last) - min(first[c][0] for c in first)
    if part <= 1 or fence_core_s is None:
        return None
    return {"partition_core_s": round(part, 1), "fence_core_s": round(fence_core_s, 1), "span_s": round(span, 1),
            "residual_pct": round(100 * max(part - fence_core_s, 0) / part, 2)}


# Root kernel threads (writeback, journal, softirq ...) are not a colleague's task: on the I/O
# servers they run on the house cores on behalf of OUR server (Kafka's log flush, Cassandra's
# compaction writes). They stay in the banked rows; only the "task > 10 %" test skips them.
KTHREAD = re.compile(r"^(kworker|ksoftirqd|kswapd|jbd2|migration|rcu|irq/|nvme|kcompactd|khugepaged|"
                     r"kthreadd|writeback|kblockd|cpuhp|idle_inject|watchdog|scsi|loop|dm-|md)")


def witness(path, t0, t1):
    rows = []
    try:
        for ln in open(path):
            p = ln.rstrip("\n").split("\t")
            if len(p) == 3 and t0 <= float(p[0]) <= t1 + 2:
                top = max([float(pct) for user, comm, pct in
                           re.findall(r"(\S+?):(.+?)\[\d+\]=(\d+(?:\.\d+)?)%", p[2])
                           if not (user == "root" and KTHREAD.match(comm))] or [0])
                rows.append((float(p[1]), top, p[2]))
    except OSError:
        pass
    n = len(rows)
    flag = [r for r in rows if r[1] > 10.0]
    mean_tot = sum(r[0] for r in rows) / n if n else None
    s = {"witness_rows": n, "rows_with_foreign_task": len(flag),
         "mean_foreign_cpu_pct": round(mean_tot, 1) if mean_tot is not None else None,
         "worst_row": max(rows, key=lambda r: r[0])[2] if rows else "-"}
    s["clean"] = n > 0 and len(flag) <= 0.05 * n and mean_tot <= 25
    return s


def receipt_summary(rc):
    mt, fc = rc.get("metric") or {}, rc.get("fence_cores") or {}
    return {"metric": mt.get("name"), "unit": mt.get("unit"), "new": mt.get("new"),
            "banked_median": mt.get("banked_median"), "banked_n": mt.get("banked_n"), "ratio": mt.get("ratio"),
            "comparable": rc.get("comparable"), "reason": rc.get("reason"), "rule": rc.get("verdict_rule"),
            "sla": rc.get("sla"), "fence_cores_new": fc.get("new"), "fence_cores_banked_median": fc.get("banked_median"),
            "fence_cores_in_band": fc.get("in_band"), "basis": receipt_basis(rc), "notes": rc.get("notes")}


def receipt_basis(rc):
    # video-4k is a batch whose runner reports nothing until the whole 4K batch ends, which no
    # pass (counter or LBR) reaches: none of the 9 banked passes has a throughput receipt either.
    # Its only evidence of doing the work is the saturated encode pool, so the fence load is the
    # proxy -- for that workload only, and named as such in summary.json.
    if rc.get("kind") == "video" and rc.get("comparable") is None:
        return "fence-load proxy (batch without a receipt by design)"
    return "workload receipt"


def receipt_ok(rc):
    if receipt_basis(rc).startswith("fence-load"):
        return (rc.get("fence_cores") or {}).get("in_band") is True
    return rc.get("comparable") is True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--analyzer-rc", type=int, required=True)
    ap.add_argument("--period", type=int, default=20011)
    ap.add_argument("--cover-tol", type=float, default=0.005)
    ap.add_argument("--measured", default="4-11")
    a = ap.parse_args()
    out = a.run
    m = json.load(open(f"{out}/metadata.json"))
    ff = m.get("frontend_footprint", {})
    t0, t1 = ff.get("ts_start"), ff.get("ts_end")
    try:
        an = json.load(open(f"{out}/analyzer.json"))
    except Exception as e:  # noqa: BLE001 — any failure to read is a failed gate
        an = {"error": str(e)}
    exact = {}
    try:
        for row in csv.reader(open(f"{out}/exact_counts.csv")):
            if len(row) > 3 and row[0] and not row[0].startswith("#"):
                try:
                    exact[row[2]] = float(row[0])
                except ValueError:
                    exact[row[2]] = None
                if len(row) > 3 and row[3]:            # cgroup column of --for-each-cgroup
                    exact.setdefault("_cgroup", row[3])
    except OSError:
        pass
    stats, section = {}, None
    try:
        for ln in open(f"{out}/perf_report_stats.txt"):
            if ln.rstrip().endswith("stats:"):
                section = ln.strip()
                continue
            p = ln.split()
            # the "Aggregated stats:" section only: the per-event section repeats SAMPLE
            if section == "Aggregated stats:" and len(p) >= 3 and p[1] == "events:" and p[2].isdigit():
                stats[p[0]] = int(p[2])
    except OSError:
        pass
    d = an.get("diagnostics", {})
    samples, lost = d.get("samples"), d.get("lost_samples", 0) or 0
    taken = exact.get("br_inst_retired.near_taken")
    cover = samples * a.period / taken if samples and taken else None
    lost_pct = 100.0 * lost / (samples + lost) if samples else None
    unm = 100.0 * d["unmapped_entries"] / d["entries"] if d.get("entries") and "unmapped_entries" in d else None
    series = rate_series(f"{out}/cpustat_scope1.tsv", t0, t1) if t0 else []
    g4 = d4(series)
    g5 = d5(f"{out}/procstat_partition.tsv", fence_core_s(f"{out}/cpustat_scope1.tsv", t0, t1),
            cpus(a.measured), t0, t1) if t0 else None
    wit = witness(f"{out}/witness.tsv", t0, t1) if t0 else {"clean": False}
    try:
        rc = json.load(open(f"{out}/receipt_compare.json"))
    except Exception:  # noqa: BLE001
        rc = {"comparable": None, "reason": "receipt_compare.json missing or unreadable"}
    g = {
        "analyzer_ok": a.analyzer_rc == 0 and "error" not in an,
        "lost_pct": lost_pct, "lost_ok": lost_pct is not None and lost_pct < 1.0,
        "sample_coverage": cover,
        "coverage_ok": cover is not None and abs(cover - 1) <= a.cover_tol,
        "perf_record_stats": stats,
        "throttle_events": stats.get("THROTTLE", 0),
        "throttle_ok": stats.get("THROTTLE", 0) == 0 and bool(stats),
        "alive_ok": bool(ff.get("server_alive_through_window")),
        "unmapped_pct": unm, "discontinuity_rate": d.get("discontinuity_rate"),
        "mapped_ok": unm is not None and unm < 1.0,
        "d4": g4, "d4_ok": bool(g4) and g4["drift_pct"] <= D4_MAX_DRIFT and g4["mean_cores"] >= D4_IDLE_CORES,
        "d5": g5, "d5_ok": bool(g5) and g5["residual_pct"] <= D5_MAX_RESID,
        "witness": wit, "witness_ok": bool(wit.get("clean")),
        "receipt": receipt_summary(rc),
        "receipt_ok": receipt_ok(rc),
        "contract": {k: ff.get(k) for k in ("event", "period", "branch_filter")},
        "contract_ok": (ff.get("event"), ff.get("period"), ff.get("branch_filter"))
                       == (CONTRACT_EVENT, a.period, CONTRACT_FILTER),
        "iso_proof": ff.get("iso_proof"),
        "perf_event_max_sample_rate": ff.get("perf_event_max_sample_rate"),
        "thresholds": {"lost_pct_lt": 1.0, "coverage_tol": a.cover_tol, "throttle_eq": 0, "unmapped_pct_lt": 1.0,
                       "d4_max_drift_pct": D4_MAX_DRIFT, "d4_min_cores": D4_IDLE_CORES,
                       "d5_max_residual_pct": D5_MAX_RESID,
                       "witness": "<= 5 % of rows with a non-kernel-thread task > 10 %, mean foreign <= 25 %",
                       "receipt": "receipt_compare.py verdict_rule (copied in receipt.rule)"},
    }
    # An override is a recorded human decision, never a default: <run>/receipt_override.json
    # (decided_by, date, reason, evidence). receipt_ok itself stays False; all_ok accepts it and
    # names it in `overrides`, so every consumer can see the pass was accepted by decision.
    try:
        ov = json.load(open(f"{out}/receipt_override.json"))
    except (OSError, ValueError):
        ov = None
    g["receipt_override"] = ov
    g["overrides"] = ["receipt"] if ov and not g["receipt_ok"] else []
    g["all_ok"] = all(g[k] for k in ("analyzer_ok", "contract_ok", "lost_ok", "coverage_ok", "throttle_ok", "alive_ok", "mapped_ok",
                                     "d4_ok", "d5_ok", "witness_ok")) and (g["receipt_ok"] or bool(g["overrides"]))
    s = dict(an)
    ex = m.get("extra", {})
    s["workload"] = ex.get("workload")
    s["capture"] = {"suite": ex.get("suite"), "bench": ex.get("bench"), "workload": ex.get("workload"),
                    "server_cg": ex.get("server_cg"), "capture_s": ex.get("capture_s"), "load": ex.get("load"),
                    "cpus_measured": m.get("cpus_measured"), "repo_rev": m.get("repo_rev"),
                    "kernel": m.get("kernel"), "frontend_footprint": ff,
                    "mean_cores": g4["mean_cores"] if g4 else None}
    s["exact_counts"] = exact
    s["gates_v4"] = g
    json.dump(s, open(f"{out}/summary.json", "w"), indent=1)

    def f(v, p):
        return (p % v) if isinstance(v, (int, float)) else str(v)
    print(f"samples={samples} lost={f(lost_pct, '%.3f')}% coverage={f(cover, '%.5f')} "
          f"throttle={g['throttle_events']} unmapped={f(unm, '%.3f')}% D4 drift={f(g4 and g4['drift_pct'], '%.1f')}% "
          f"load={f(g4 and g4['mean_cores'], '%.2f')} D5 resid={f(g5 and g5['residual_pct'], '%.1f')}% "
          f"witness={'clean' if wit.get('clean') else 'CONTAMINATED/none'} "
          f"receipt={f(g['receipt'].get('ratio'), '%.3f')} ({g['receipt'].get('comparable')}; cores {g['receipt'].get('fence_cores_new')}) "
          f"-> {('ALL OK (override: ' + ','.join(g['overrides']) + ')') if g['all_ok'] and g['overrides'] else 'ALL OK' if g['all_ok'] else 'GATE FAILED: ' + ','.join(k for k in g if k.endswith('_ok') and not g[k])}")
    print(f"footprint={s.get('footprint_bytes')} B (kernel {s.get('footprint_bytes_kernel')}) "
          f"unique_taken={s.get('unique_taken_branches')} weff_all={s.get('weff_targets_all')} "
          f"wavg_all={s.get('wavg_targets_all')}")
    return 0 if g["all_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
