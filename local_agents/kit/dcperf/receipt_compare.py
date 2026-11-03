#!/usr/bin/env python3
"""receipt_compare.py — did a new pass SERVE its workload, at a throughput comparable to the banked
counter passes? Parsing only, over files already on disk: it never starts, stops or profiles anything.

    python3 local_agents/kit/dcperf/receipt_compare.py <new_run_dir> <banked_workload_dir> [--out F] [--ref DIR]...

Written for the frontend_footprint LBR passes (<root>/data/frontend_footprint/<suite>_<workload>/run_1),
whose contract asks that the "client receipt shows the workload served, with throughput comparable to the
existing passes' receipts". <banked_workload_dir> holds run_1..run_9; when <new_run_dir> is one of them it
is left out of the banked set, so any banked run can be replayed as "new". --ref adds reference runs.

WORKLOAD: metadata.json extra.bench / extra.workload (config for the DCPerf passes, which predate
extra.suite/workload), else the receipt files present. New and banked must agree, or the verdict is null.

CAPTURE WINDOW = [ts_start, ts_start + extra.capture_s] (metadata.json; ts_start is stamped just before the
capture starts, and the banked cpustat/windows.tsv spans agree with it to <1 s).

METRIC PER WORKLOAD (the first is the headline; GATE metrics decide the verdict, the rest are shown):
  feedsim      achieved QPS of the FIXED-QPS row of feedsim_results.txt (requested_qps > 0); GATE, plus
               p95 <= 500 ms on that row. The requested_qps == 0 row is the unpaced 120 s warm-up
               (saturation) load test that precedes the capture: shown, not gated. The nine banked sweep
               passes were torn down before the fixed-QPS row was written (DCPerf README sec. 4), so when no
               banked run has one, the reference is the confirmation receipt data/confirm/<name>/run_*
               (the convention validate_dcperf.py gate D6 already uses).
  cassandra    YCSB OVERALL Throughput(ops/sec), cassandra_receipt.json (whole client run, warm-up
               included); GATE. Shown: ops/s inside the window from the cumulative operation counts of the
               10 s status lines in ycsb_run.log.
  kafka        consumer total MB/s inside the window (sum over consumer_*.log of d(cumulative MB)/dt); GATE.
               Producer total records/s (kafka_receipt.json: sum of the producers' final summaries); GATE.
               The receipt's consumer_total_MB_per_s_last is ONE 5 s interval, often the truncated last
               one: shown only.
  neo4j        ops/s, all classes, from the receipt's last_<capture_s>s block (neo4j_receipt.json, else
               client.receipt.json). The client is stopped when the capture closes, so that block IS the
               window; GATE.
  spark        mean seconds per pass over passes lying wholly inside the window; GATE. "[rd] pass N done at
               T s" counts from the script's start; it is anchored at the SparkContext start in spark.log
               ("app id = local-<epoch ms>"), which precedes the script by <= ~2 s (checked against log4j
               stamps). T is printed in whole seconds, hence span/passes and never a median of 2-3 s steps.
  dacapo       mean iteration time (ms) over iterations wholly inside the window; GATE. Runs are sized to
               outlast the capture and never reach the timed iteration, so there is no "PASSED in N msec":
               every iteration is "completed warmup N in X msec". dacapo.log has no clock; iteration k is
               placed by the k-th /manager/text/start request in tomcat's access log (scratch/*/logs,
               1 s stamps, taken as +0.5 s), cross-checked against the matching stop request. Shown: mean
               requests/s from the "processed N requests" lines.
  renaissance  mean operation time (ms) over operations wholly inside the window; GATE. renaissance.csv
               has vm_start_unix_ms + uptime_ns (operation start) and duration_ns: exact wall clock.
  video        NONE. vtb_run.log only reaches the "Running M<preset>" stage marker: DCPerf's runner prints
               per-level elapsed time when the whole batch ends, and 4K lp=1 encodes do not end inside a
               pass. comparable = null with that reason; the fence load is shown as the only evidence.
FALLBACK when the new run's window cannot be placed (no metadata window, no access log, no app id, nothing
wholly inside): steady state = drop the first N units (dacapo 5 iterations, renaissance 10 operations,
spark 2 passes) and use the rest. Whichever rule the NEW run needs is applied to every banked run too.
Log stamps without a zone (YCSB, kafka consumer) are read in the local zone (P7 = the zone they were
written in).

FENCE LOAD: mean cores = d(usage_usec)/dt over the whole cpustat_scope1.tsv ("epoch usage_usec N ...",
"-1" sentinels dropped; a counter reset is summed piecewise and noted). Same band; shown, never gated.

VERDICT: see VERDICT_RULE. Two-sided on purpose: a pass much FASTER than the banked ones is not the same
operating point either. Always exits 0: it is a reporting tool and the caller reads the JSON.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import statistics as st
import sys
import time
from datetime import datetime

KITD = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(KITD, "..", "..", ".."))
TOL_MED, TOL_LO, TOL_HI = 0.15, 0.95, 1.05
SLA_P95_MS = 500.0                                     # feedsim: DCPerf's own objective
DROP = {"dacapo": 5, "renaissance": 10, "spark": 2}    # steady-state fallback: leading units dropped
HI, LO = "higher_is_better", "lower_is_better"
VERDICT_RULE = ("comparable = true iff every GATE metric of the new pass lies within +/-15 % of the banked "
                "median OR inside [banked min x 0.95, banked max x 1.05]; feedsim additionally needs the new "
                "pass's fixed-QPS p95 <= 500 ms. null (with reason) when the new receipt is missing or "
                "unparsable, when no banked run has one, or when new and banked are different workloads. "
                "Fence cores use the same band but never gate.")

BENCH_KIND = {"feedsim": "feedsim", "dacapo": "dacapo", "renaissance": "renaissance", "cassandra": "cassandra",
              "kafka": "kafka", "neo4j": "neo4j", "spark": "spark", "video_transcode": "video"}
FILE_KIND = [("feedsim_results.txt", "feedsim"), ("cassandra_receipt.json", "cassandra"), ("ycsb_run.log", "cassandra"),
             ("kafka_receipt.json", "kafka"), ("neo4j_receipt.json", "neo4j"), ("client.receipt.json", "neo4j"),
             ("spark_receipt.txt", "spark"), ("spark.log", "spark"), ("dacapo.log", "dacapo"),
             ("renaissance.csv", "renaissance"), ("vtb_run.log", "video")]
# key, name, unit, direction, gate
SPECS = {
    "feedsim": [("fixed_qps", "achieved QPS, fixed-QPS experiment row", "queries/s", HI, True),
                ("warmup_qps", "achieved QPS, unpaced warm-up row (pre-capture)", "queries/s", HI, False)],
    "cassandra": [("overall", "YCSB OVERALL Throughput(ops/sec)", "ops/s", HI, True),
                  ("window_ops", "YCSB ops/s inside the capture window", "ops/s", HI, False)],
    "kafka": [("consumer_window", "consumer total MB/s inside the capture window", "MB/s", HI, True),
              ("producer_rps", "producer total records/s (final summaries)", "records/s", HI, True),
              ("consumer_last", "receipt consumer_total_MB_per_s_last (one 5 s interval)", "MB/s", HI, False)],
    "neo4j": [("ops", "client ops/s, all classes, capture window", "ops/s", HI, True)],
    "spark": [("s_per_pass", "mean seconds per pass", "s", LO, True)],
    "dacapo": [("iter_ms", "mean iteration time", "ms", LO, True),
               ("req_per_s", "mean requests/s per iteration", "requests/s", HI, False)],
    "renaissance": [("op_ms", "mean operation time", "ms", LO, True)],
    "video": [("throughput", "throughput receipt (none exists in vtb_run.log)", None, None, True)],
}


class NoReceipt(Exception):
    """receipt missing or unparsable: the reason goes into the JSON, never a made-up number"""


def val(v, rule, notes=(), **detail):
    return {"value": v, "rule": rule, "notes": list(notes), "detail": detail}


def miss(why, fallback=False, notes=(), **detail):
    return {"value": None, "why": why, "fallback": fallback, "notes": list(notes), "detail": detail}


def rd(path):
    with open(path, errors="replace") as fh:
        return fh.read()


def meta_of(run):
    try:
        with open(os.path.join(run, "metadata.json")) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def window_of(meta):
    try:
        t0 = float(meta["ts_start"])
        return t0, t0 + float(meta["extra"]["capture_s"])
    except (KeyError, TypeError, ValueError):
        return None


def local_epoch(s):  # "YYYY-mm-dd HH:MM:SS", no zone in the log -> local zone
    return time.mktime(time.strptime(s, "%Y-%m-%d %H:%M:%S"))


def wtxt(win):
    return f"capture window [ts_start, ts_start + {win[1] - win[0]:.0f} s]"


def identify(run):
    """-> (kind, workload) from metadata, else from the receipt files / the <suite>_<workload> dir name"""
    m = meta_of(run)
    ex = m.get("extra") or {}
    kind = BENCH_KIND.get(ex.get("bench") or "")
    if not kind:
        kind = next((k for f, k in FILE_KIND if os.path.exists(os.path.join(run, f))), None)
    wl = ex.get("workload") or m.get("config")
    if not wl:
        parent = os.path.basename(os.path.dirname(os.path.abspath(run)))
        wl = parent.split("_", 1)[1] if "_" in parent else None
    return kind, (re.sub(r"^(dcperf|dacapo|renaissance|realdata)_", "", wl) if wl else None)


# ---------------------------------------------------------------- per-workload parsers
def p_feedsim(run, meta, win, steady):
    f = os.path.join(run, "feedsim_results.txt")
    if not os.path.exists(f):
        raise NoReceipt("feedsim_results.txt missing")
    try:
        with open(f) as fh:
            rows = [{k: float(v) for k, v in r.items()} for r in csv.DictReader(fh)]
        fixed = [r for r in rows if r["requested_qps"] > 0]
        warm = [r for r in rows if r["requested_qps"] == 0]
    except (TypeError, ValueError, KeyError, AttributeError):
        raise NoReceipt("feedsim_results.txt unparsable")
    out = {}
    if fixed:
        r = fixed[-1]
        out["fixed_qps"] = val(r["achieved_qps"], "fixed-QPS experiment row (whole experiment; it spans the capture)",
                               requested_qps=r["requested_qps"], duration_s=r["duration_secs"],
                               queries=r["total_queries"], p95_ms=r["95p_ms"], p99_ms=r["99p_ms"])
    else:
        out["fixed_qps"] = miss("feedsim_results.txt has no fixed-QPS row (requested_qps > 0), only the unpaced "
                                "warm-up row: the pass was torn down before the experiment wrote its row")
    if warm:
        r = warm[-1]
        out["warmup_qps"] = val(r["achieved_qps"], "unpaced warm-up row (before the capture)",
                                duration_s=r["duration_secs"], p95_ms=r["95p_ms"])
    else:
        out["warmup_qps"] = miss("no warm-up row (requested_qps == 0)")
    return out


YCSB_STATUS = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d):(\d{3}) \d+ sec: (\d+) operations;", re.M)


def p_cassandra(run, meta, win, steady):
    out = {}
    f = os.path.join(run, "cassandra_receipt.json")
    try:
        with open(f) as fh:
            rec = json.load(fh)
        thr = float(rec["OVERALL"]["Throughput(ops/sec)"])
        det, notes = {"runtime_s": rec["OVERALL"].get("RunTime(ms)", 0) / 1e3}, []
        for op in ("READ", "UPDATE", "INSERT", "SCAN", "READ-MODIFY-WRITE"):
            if op in rec:
                d = rec[op]
                det[op] = {"ops": d.get("Operations"), "p95_us": d.get("95thPercentileLatency(us)"),
                           "p99_us": d.get("99thPercentileLatency(us)")}
                bad = {k: v for k, v in d.items() if k.startswith("Return=") and k != "Return=OK"}
                if bad:
                    notes.append(f"YCSB {op} non-OK returns {bad}")
        out["overall"] = val(thr, "YCSB OVERALL, whole client run (warm-up + capture + tail)", notes, **det)
    except OSError:
        out["overall"] = miss("cassandra_receipt.json missing")
    except (ValueError, KeyError, TypeError):
        out["overall"] = miss("cassandra_receipt.json has no OVERALL Throughput(ops/sec)")
    # in-window from the cumulative operation counts of the status lines
    y = os.path.join(run, "ycsb_run.log")
    if win is None:
        out["window_ops"] = miss("no capture window in metadata.json")
    elif not os.path.exists(y):
        out["window_ops"] = miss("ycsb_run.log missing")
    else:
        pts = [(local_epoch(m.group(1)) + int(m.group(2)) / 1e3, int(m.group(3))) for m in YCSB_STATUS.finditer(rd(y))]
        sel = [p for p in pts if win[0] <= p[0] <= win[1]]
        if len(sel) < 2:
            out["window_ops"] = miss(f"{len(sel)} YCSB status line(s) inside the window")
        else:
            out["window_ops"] = val((sel[-1][1] - sel[0][1]) / (sel[-1][0] - sel[0][0]),
                                    f"{wtxt(win)}: d(operations)/dt between the first and last status line inside",
                                    span_s=round(sel[-1][0] - sel[0][0], 1))
    return out


KAFKA_CONS = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d):(\d{3}), *\d+, *([0-9.]+), ", re.M)


def p_kafka(run, meta, win, steady):
    out = {}
    files = sorted(glob.glob(os.path.join(run, "consumer_*.log")))
    if win is None:
        out["consumer_window"] = miss("no capture window in metadata.json")
    elif not files:
        out["consumer_window"] = miss("no consumer_*.log")
    else:
        per, bad = {}, []
        for f in files:
            pts = [(local_epoch(m.group(1)) + int(m.group(2)) / 1e3, float(m.group(3))) for m in KAFKA_CONS.finditer(rd(f))]
            sel = [p for p in pts if win[0] <= p[0] <= win[1]]
            if len(sel) < 2:
                bad.append(f"{os.path.basename(f)}: {len(sel)} interval line(s) inside the window")
            else:
                per[os.path.basename(f)] = round((sel[-1][1] - sel[0][1]) / (sel[-1][0] - sel[0][0]), 2)
        out["consumer_window"] = (miss("; ".join(bad)) if bad else
                                  val(round(sum(per.values()), 2), f"{wtxt(win)}: sum over consumers of d(cumulative MB)/dt",
                                      consumers=per))
    try:
        with open(os.path.join(run, "kafka_receipt.json")) as fh:
            rec = json.load(fh)
    except OSError:
        out["producer_rps"] = out["consumer_last"] = miss("kafka_receipt.json missing")
        return out
    except ValueError:
        out["producer_rps"] = out["consumer_last"] = miss("kafka_receipt.json unparsable")
        return out
    if rec.get("producers") and rec.get("producer_total_records_per_s") is not None:
        out["producer_rps"] = val(float(rec["producer_total_records_per_s"]), "sum of the producers' final perf-test summaries (whole run)",
                                  producers=rec["producers"], last_final_p95_ms=(rec.get("producer_final") or {}).get("p95_ms"))
    else:
        out["producer_rps"] = miss("kafka_receipt.json has no producer final summary (producers stopped before finishing?)")
    if rec.get("consumers"):
        out["consumer_last"] = val(rec.get("consumer_total_MB_per_s_last"), "receipt: each consumer's last 5 s interval, summed",
                                   n_consumers=len(rec["consumers"]))
    else:
        out["consumer_last"] = miss("kafka_receipt.json has no consumer entries")
    # consumers that drained the backlog tail the head at exactly the produce rate: say so
    cw, pr = out["consumer_window"].get("value"), out["producer_rps"].get("value")
    rb = (((meta.get("extra") or {}).get("load") or {}).get("client") or {}).get("record_bytes")
    if cw and pr and rb and files:
        tail = pr * rb / 2 ** 20 * len(files)
        out["consumer_window"]["detail"]["vs_produce_rate_x_consumers"] = round(cw / tail, 3)
        if abs(cw / tail - 1) < 0.03:
            out["consumer_window"]["notes"].append(
                "consumers tail the log head at the produce rate for the whole capture (backlog drained before the "
                "window): consumer MB/s = consumers x produce rate, so it confirms service, not broker headroom")
    return out


def p_neo4j(run, meta, win, steady):
    for name in ("neo4j_receipt.json", "client.receipt.json"):
        f = os.path.join(run, name)
        if os.path.exists(f):
            break
    else:
        raise NoReceipt("neo4j_receipt.json and client.receipt.json missing")
    try:
        with open(f) as fh:
            rec = json.load(fh)
    except ValueError:
        raise NoReceipt(f"{name} unparsable")
    if "error" in rec:
        raise NoReceipt(f"{name}: {rec['error']}")
    cap = (meta.get("extra") or {}).get("capture_s")
    keys = [k for k in rec if re.fullmatch(r"last_\d+s", k)]
    key = f"last_{int(cap)}s" if cap and f"last_{int(cap)}s" in rec else (keys[0] if len(keys) == 1 else None)
    if not key:
        raise NoReceipt(f"{name} has no last_<capture_s>s block")
    notes = [] if cap and key == f"last_{int(cap)}s" else [f"receipt window {key} != capture_s {cap}"]
    blk = rec[key]
    try:
        v = float(blk["all"]["ops_per_s"])
    except (KeyError, TypeError, ValueError):
        raise NoReceipt(f"{name}: {key}.all.ops_per_s missing")
    cls = {c: {"ops_per_s": d.get("ops_per_s"), "p95_ms": d.get("p95_ms_count_weighted"), "errors": d.get("errors", 0)}
           for c, d in blk.items() if c != "all"}
    errs = sum(d["errors"] or 0 for d in cls.values())
    if errs:
        notes.append(f"{errs} client errors in {key}")
    return {"ops": val(v, f"receipt block {key} (client stops when the capture closes: this block is the window)", notes,
                       source=name, span_s=blk["all"].get("span_s"), errors=errs, classes=cls)}


RD_PASS = re.compile(r"^\[rd\] pass (\d+) done at (\d+) s", re.M)
RD_LOAD = re.compile(r"^\[rd\] (?:graph|corpus) loaded: .*? in ([0-9.]+) s", re.M)
SPARK_APP = re.compile(r"app id = local-(\d{13})")


def p_spark(run, meta, win, steady):
    lg, rc = os.path.join(run, "spark.log"), os.path.join(run, "spark_receipt.txt")
    if os.path.exists(lg):
        txt = rd(lg).replace("\r", "\n")
    elif os.path.exists(rc):
        txt = rd(rc)
    else:
        raise NoReceipt("spark.log and spark_receipt.txt missing")
    passes = [(int(n), int(t)) for n, t in RD_PASS.findall(txt)]
    if not passes:
        raise NoReceipt("no '[rd] pass N done at T s' line")
    if [n for n, _ in passes] != list(range(1, len(passes) + 1)):
        raise NoReceipt("'[rd] pass' lines are not numbered 1..N")
    lm = RD_LOAD.search(txt)
    ends = [t for _, t in passes]
    spans = list(zip([float(lm.group(1)) if lm else None] + ends[:-1], ends))   # pass k = [previous done, done]
    if not steady:
        am = SPARK_APP.search(txt)
        why = ("no capture window in metadata.json" if win is None else
               "no 'app id = local-<epoch ms>' anchor in spark.log" if not am else None)
        if not why:
            a = int(am.group(1)) / 1e3
            sel = [(s, e) for s, e in spans if s is not None and a + s >= win[0] and a + e <= win[1]]
            if sel:
                return {"s_per_pass": val((sel[-1][1] - sel[0][0]) / len(sel),
                                          f"{wtxt(win)}: passes wholly inside (anchor = SparkContext start, <= ~2 s early)",
                                          n=len(sel), passes_logged=len(passes),
                                          passes=f"{passes[spans.index(sel[0])][0]}..{passes[spans.index(sel[-1])][0]}")}
            why = "no pass lies wholly inside the capture window"
        return {"s_per_pass": miss(why, fallback=True)}
    k = DROP["spark"]
    sel = [sp for sp in spans[k:] if sp[0] is not None]
    if not sel:
        return {"s_per_pass": miss(f"fewer than {k + 1} passes logged")}
    return {"s_per_pass": val((sel[-1][1] - sel[0][0]) / len(sel), f"steady state: passes {k + 1}..{len(passes)} (first {k} dropped)",
                              n=len(sel), passes_logged=len(passes))}


DC_ITER = re.compile(r"^===== DaCapo \S+ \S+ (?:completed warmup \d+ in (\d+) msec|PASSED in (\d+) msec) =====")
DC_REQ = re.compile(r"^===== DaCapo processed \d+ requests in \d+ msec, (\d+) requests per second")
DC_FAIL = re.compile(r"^===== DaCapo \S+ \S+ FAILED", re.M)


def tomcat_markers(run):
    """-> (start epochs, stop epochs) of the per-iteration webapp load/unload, or None"""
    logs = sorted(glob.glob(os.path.join(run, "scratch", "*", "logs", "localhost_access_log*.txt")))
    if not logs:
        return None
    starts, stops = [], []
    for f in logs:
        with open(f, "rb") as fh:
            for ln in fh:
                if b"/manager/text/st" not in ln:
                    continue
                i, j = ln.find(b"["), ln.find(b"]")
                t = datetime.strptime(ln[i + 1:j].decode(), "%d/%b/%Y:%H:%M:%S %z").timestamp()
                if b"/manager/text/start" in ln:
                    starts.append(t)
                elif b"/manager/text/stop" in ln:
                    stops.append(t)
    return starts, stops


def p_dacapo(run, meta, win, steady):
    f = os.path.join(run, "dacapo.log")
    if not os.path.exists(f):
        raise NoReceipt("dacapo.log missing")
    txt = rd(f)
    iters = []
    for ln in txt.splitlines():
        m = DC_ITER.match(ln)
        if m:
            iters.append({"ms": int(m.group(1) or m.group(2)), "timed": m.group(2) is not None})
            continue
        m = DC_REQ.match(ln)
        if m and iters and "rps" not in iters[-1]:
            iters[-1]["rps"] = int(m.group(1))
    if not iters:
        raise NoReceipt("no completed iteration in dacapo.log")
    notes = ["no timed ('PASSED in N msec') iteration: the run outlasts the capture, every logged iteration is a "
             "'completed warmup' one"] if not any(i["timed"] for i in iters) else []
    if DC_FAIL.search(txt):
        notes.append("dacapo.log reports a FAILED iteration")
    if not steady:
        mk = tomcat_markers(run) if win else None
        why = None
        if win is None:
            why = "no capture window in metadata.json"
        elif mk is None:
            why = "no tomcat access log (scratch/*/logs/localhost_access_log*) to place iterations in time"
        elif len(mk[0]) < len(iters) or len(mk[1]) < len(iters):
            why = f"access log has {len(mk[0])} start / {len(mk[1])} stop markers for {len(iters)} iterations"
        elif any(abs(mk[1][k] - mk[0][k] - it["ms"] / 1e3) > 2 for k, it in enumerate(iters)):
            why = "access-log start/stop markers do not line up with dacapo.log iteration times"
        if not why:
            sel = [it for k, it in enumerate(iters)
                   if mk[0][k] + 0.5 >= win[0] and mk[0][k] + 0.5 + it["ms"] / 1e3 <= win[1]]
            rule = f"{wtxt(win)}: iterations wholly inside (placed by tomcat access-log start markers, +-0.5 s)"
            if not sel:
                why = "no iteration lies wholly inside the capture window"
        if why:
            return {"iter_ms": miss(why, fallback=True, notes=notes), "req_per_s": miss(why)}
    else:
        k = DROP["dacapo"]
        sel, rule = iters[k:], f"steady state: iterations {k + 1}..{len(iters)} (first {k} dropped)"
        if not sel:
            return {"iter_ms": miss(f"fewer than {k + 1} iterations logged", notes=notes), "req_per_s": miss("no iterations")}
    ms = [it["ms"] for it in sel]
    rps = [it["rps"] for it in sel if "rps" in it]
    return {"iter_ms": val(st.mean(ms), rule, notes, n=len(ms), iterations_logged=len(iters), median_ms=st.median(ms)),
            "req_per_s": val(st.mean(rps), rule, n=len(rps)) if rps else miss("no 'processed N requests' lines")}


def p_renaissance(run, meta, win, steady):
    f = os.path.join(run, "renaissance.csv")
    if not os.path.exists(f):
        raise NoReceipt("renaissance.csv missing")
    try:
        with open(f) as fh:
            rows = list(csv.DictReader(fh))
        dur = [int(r["duration_ns"]) / 1e6 for r in rows]
    except (KeyError, TypeError, ValueError):
        raise NoReceipt("renaissance.csv unparsable (no duration_ns)")
    if not dur:
        raise NoReceipt("renaissance.csv has no operation")
    if not steady:
        why = None
        try:
            t = [int(r["vm_start_unix_ms"]) / 1e3 + int(r["uptime_ns"]) / 1e9 for r in rows]
        except (KeyError, TypeError, ValueError):
            why = "renaissance.csv lacks vm_start_unix_ms/uptime_ns"
        if win is None:
            why = "no capture window in metadata.json"
        if not why:
            sel = [d for s, d in zip(t, dur) if s >= win[0] and s + d / 1e3 <= win[1]]
            rule = f"{wtxt(win)}: operations wholly inside (renaissance.csv wall clock)"
            if not sel:
                why = "no operation lies wholly inside the capture window"
        if why:
            return {"op_ms": miss(why, fallback=True)}
    else:
        k = DROP["renaissance"]
        sel, rule = dur[k:], f"steady state: operations {k + 1}..{len(dur)} (first {k} dropped)"
        if not sel:
            return {"op_ms": miss(f"fewer than {k + 1} operations logged")}
    return {"op_ms": val(st.mean(sel), rule, n=len(sel), ops_logged=len(dur), median_ms=st.median(sel))}


def p_video(run, meta, win, steady):
    f = os.path.join(run, "vtb_run.log")
    if not os.path.exists(f):
        raise NoReceipt("vtb_run.log missing")
    txt = rd(f)
    stages = re.findall(r"^Running (M\d+)", txt, re.M)
    return {"throughput": miss("vtb_run.log has no per-encode completion, fps or elapsed-time line (stage markers only: "
                               f"{', '.join('Running ' + s for s in stages) or 'none'}); DCPerf's runner reports per-level "
                               "elapsed time only when the whole batch ends, and the pass is torn down at capture end",
                               encode_stage_reached=bool(stages), stages=stages)}


PARSE = {"feedsim": p_feedsim, "cassandra": p_cassandra, "kafka": p_kafka, "neo4j": p_neo4j, "spark": p_spark,
         "dacapo": p_dacapo, "renaissance": p_renaissance, "video": p_video}


def parse_run(kind, run, steady):
    meta = meta_of(run)
    win = window_of(meta)
    try:
        got, why = PARSE[kind](run, meta, win, steady), "not reported"
    except NoReceipt as e:
        got, why = {}, str(e)
    except (OSError, UnicodeDecodeError) as e:
        got, why = {}, f"unreadable: {e}"
    return {k: got.get(k) or miss(why) for k, *_ in SPECS[kind]}


def fence_cores(run):
    """mean cores = d(usage_usec)/dt over the whole cpustat_scope1.tsv -> (value, note)"""
    f = os.path.join(run, "cpustat_scope1.tsv")
    if not os.path.exists(f):
        return None, "cpustat_scope1.tsv missing"
    pts = []
    with open(f, errors="replace") as fh:
        for ln in fh:
            p = ln.split()
            if len(p) >= 3 and p[1] == "usage_usec" and p[2] != "-1":
                try:
                    pts.append((float(p[0]), int(p[2])))
                except ValueError:
                    pass
    if len(pts) < 2 or pts[-1][0] <= pts[0][0]:
        return None, "cpustat_scope1.tsv has < 2 valid samples"
    used, resets = 0, 0
    for (_, a), (_, b) in zip(pts, pts[1:]):
        if b >= a:
            used += b - a
        else:
            resets += 1            # counter restarted (new cgroup): count from its new origin
            used += b
    return used / 1e6 / (pts[-1][0] - pts[0][0]), (f"{resets} usage_usec reset(s), summed piecewise" if resets else None)


# ---------------------------------------------------------------- comparison
def band(new, banked):
    vals = list(banked.values())
    b = {"new": new, "banked": banked, "banked_values": vals, "banked_n": len(vals)}
    if not vals:
        return {**b, "banked_median": None, "banked_min": None, "banked_max": None, "ratio": None, "in_band": None}
    med, lo, hi = st.median(vals), min(vals), max(vals)
    ok = None if new is None else (abs(new - med) <= TOL_MED * abs(med) or lo * TOL_LO <= new <= hi * TOL_HI)
    return {**b, "banked_median": med, "banked_min": lo, "banked_max": hi,
            "ratio": (new / med if new is not None and med else None), "in_band": ok}


def spread_notes(label, vals):
    """large spread / monotone drift across the banked passes (vals in run order)"""
    out = []
    if len(vals) < 3:
        return out
    med = st.median(vals)
    sp = (max(vals) - min(vals)) / med if med else 0
    if sp > 0.20:
        out.append(f"banked {label}: large spread {100 * sp:.0f} % of the median (min {min(vals):.4g}, max {max(vals):.4g})")
    if len(vals) >= 4 and sp > 0.10 and len(set(vals)) > 1:
        r = st.correlation(list(range(len(vals))), vals)
        if abs(r) > 0.8:
            out.append(f"banked {label}: {'declines' if r < 0 else 'rises'} across passes in run order "
                       f"(r = {r:+.2f}, {vals[0]:.4g} -> {vals[-1]:.4g}): passes are not exchangeable")
    return out


def fmt(x):
    return "null" if x is None else f"{x:.4g}"


def compare(new_dir, banked_dir, refs):
    new_dir, banked_dir = os.path.abspath(new_dir), os.path.abspath(banked_dir)
    notes = []
    kind, wl = identify(new_dir)
    res = {"workload": wl, "kind": kind, "new_run": new_dir, "banked_dir": banked_dir}
    runs = sorted((d for d in glob.glob(os.path.join(banked_dir, "run_*")) if os.path.isdir(d)),
                  key=lambda d: int(re.sub(r"\D", "", os.path.basename(d)) or 0))
    me = os.path.realpath(new_dir)
    excl = [os.path.basename(d) for d in runs if os.path.realpath(d) == me]
    runs = [d for d in runs if os.path.realpath(d) != me]
    refs = [os.path.abspath(r) for r in refs if os.path.realpath(r) != me]
    res.update(banked_runs=[os.path.basename(d) for d in runs], excluded_from_banked=excl)
    if not runs and not refs:
        return {**res, "comparable": None, "reason": f"no banked run_* under {banked_dir}", "notes": notes}
    bkind, bwl = identify(runs[0] if runs else refs[0])
    if kind is None:
        kind, res["kind"] = bkind, bkind
        notes.append("new run: workload not identifiable from metadata or receipt files; taken from the banked dir")
    if kind is None:
        return {**res, "comparable": None, "reason": "workload not identifiable (no metadata, no known receipt file)", "notes": notes}
    if bkind != kind or (wl and bwl and wl != bwl):
        return {**res, "comparable": None, "reason": f"workload mismatch: new {kind}/{wl} vs banked {bkind}/{bwl}", "notes": notes}
    res["workload"] = wl or bwl
    win = window_of(meta_of(new_dir))
    res["capture_window"] = {"t0": win[0], "t1": win[1], "s": round(win[1] - win[0], 1)} if win else None

    # the rule the NEW run can support decides the rule for everyone
    new = parse_run(kind, new_dir, False)
    steady = bool(new[SPECS[kind][0][0]].get("fallback"))
    if steady:
        notes.append(f"window rule not applicable to the new run ({new[SPECS[kind][0][0]]['why']}); "
                     f"steady-state rule applied to the new and every banked run")
        new = parse_run(kind, new_dir, True)
    lab = lambda d: os.path.relpath(d, os.path.dirname(banked_dir)) if not d.startswith(banked_dir + os.sep) else os.path.basename(d)
    bank = {os.path.basename(d): parse_run(kind, d, steady) for d in runs}
    bank.update({lab(r): parse_run(kind, r, steady) for r in refs})
    for d in runs:
        if not os.path.exists(os.path.join(d, "DONE")):
            notes.append(f"banked {os.path.basename(d)} has no DONE marker")

    # feedsim: the sweep passes carry no fixed-QPS row -> the documented confirmation receipt
    auto = {}
    if kind == "feedsim" and not any(b["fixed_qps"]["value"] is not None for b in bank.values()):
        cdirs = [d for d in sorted(glob.glob(os.path.join(os.path.dirname(banked_dir), "confirm", os.path.basename(banked_dir), "run_*")))
                 if os.path.realpath(d) != me]
        auto = {lab(d): parse_run(kind, d, steady) for d in cdirs}
        auto = {k: v for k, v in auto.items() if v["fixed_qps"]["value"] is not None}
        notes.append("no banked pass carries a fixed-QPS row (sweep passes were torn down before the experiment wrote "
                     "it; their only row is the unpaced warm-up) -> fixed-QPS reference = "
                     + (", ".join(auto) if auto else "none found under ../confirm/"))

    blocks = []
    for key, name, unit, direction, gate in SPECS[kind]:
        src = {**bank, **auto} if key == "fixed_qps" else bank
        got = {k: b[key]["value"] for k, b in src.items() if b[key]["value"] is not None}
        lack = {k: b[key].get("why") for k, b in src.items() if b[key]["value"] is None and k not in auto}
        blk = {"key": key, "name": name, "unit": unit, "direction": direction, "gate": gate,
               "rule": new[key].get("rule"), **band(new[key]["value"], got)}
        if new[key]["value"] is None:
            blk["why_new_missing"] = new[key].get("why")
        blk["detail"] = new[key].get("detail") or {}
        blocks.append(blk)
        if lack and gate and (key != "fixed_qps" or not auto):
            whys = sorted(set(lack.values()))
            notes.append(f"{len(lack)}/{len(src)} banked runs lack '{key}': " + " | ".join(whys)
                         if len(whys) == 1 else f"banked runs lacking '{key}': " + "; ".join(f"{k}: {w}" for k, w in lack.items()))
        if gate:
            notes += spread_notes(key, [src[k][key]["value"] for k in src if src[k][key]["value"] is not None])
        notes += [f"new: {n}" for n in new[key].get("notes", [])]
        agg = {}
        for k, b in bank.items():
            for n in b[key].get("notes", []):
                agg.setdefault(n, []).append(k)
        notes += [f"banked ({len(ks)}/{len(bank)}): {n}" for n, ks in agg.items()]

    # fence load
    nc, nn = fence_cores(new_dir)
    bc = {}
    for d in runs + refs:
        v, n = fence_cores(d)
        if v is not None:
            bc[lab(d)] = round(v, 4)
        if n:
            notes.append(f"{lab(d)} fence: {n}")
    if nn:
        notes.append(f"new fence: {nn}")
    cores = {"name": "mean fence load (cpustat_scope1.tsv, whole file)", "unit": "cores", "direction": None, "gate": False,
             **band(round(nc, 4) if nc is not None else None, bc)}
    notes += spread_notes("fence cores", list(bc.values()))
    if cores["in_band"] is False:
        notes.append(f"fence load outside the band: new {fmt(nc)} vs banked median {fmt(cores['banked_median'])} cores")

    # SLA (feedsim)
    sla = None
    if kind == "feedsim":
        p95 = new["fixed_qps"].get("detail", {}).get("p95_ms") if new["fixed_qps"]["value"] is not None else None
        sla = {"metric": "p95 latency, fixed-QPS row", "limit_ms": SLA_P95_MS, "p95_ms": p95,
               "ok": None if p95 is None else p95 <= SLA_P95_MS}

    # verdict
    gates = [b for b in blocks if b["gate"]]
    comp, reason = True, []
    for b in gates:
        if b["new"] is None:
            comp, reason = None, reason + [f"new pass: {b.get('why_new_missing')}"]
        elif not b["banked_n"]:
            comp, reason = None, reason + [f"no banked receipt for '{b['key']}'"]
        elif comp is not None and not b["in_band"]:
            comp = False
            reason.append(f"'{b['key']}' {fmt(b['new'])} outside the band (banked median {fmt(b['banked_median'])}, "
                          f"min {fmt(b['banked_min'])}, max {fmt(b['banked_max'])})")
    if sla and comp is not None and sla["ok"] is False:
        comp = False
        reason.append(f"SLA violated: p95 {sla['p95_ms']:.1f} ms > {SLA_P95_MS:.0f} ms")
    if kind == "video":
        notes.append("no throughput receipt exists for this workload; the fence load is the only evidence it ran")

    prim = blocks[0]
    res.update(metric=prim, other_metrics=blocks[1:], sla=sla, fence_cores=cores,
               comparable=comp, reason="; ".join(reason) or None, verdict_rule=VERDICT_RULE, notes=notes)
    res["summary"] = (f"{res['workload']} | {prim['name']} | new {fmt(prim['new'])} {prim['unit'] or ''} | banked median "
                      f"{fmt(prim['banked_median'])} (n={prim['banked_n']}) | ratio {fmt(prim['ratio'])} | cores "
                      f"{fmt(cores['new'])}/{fmt(cores['banked_median'])} | comparable={json.dumps(comp)}")
    return res


class _AP(argparse.ArgumentParser):
    def error(self, message):  # usage errors are reported as JSON too, with exit 0
        print(json.dumps({"comparable": None, "reason": f"usage: {message}", "verdict_rule": VERDICT_RULE, "notes": []}, indent=1))
        sys.exit(0)


def resolve(p):  # accept paths relative to the cwd or to the repo root
    return p if os.path.exists(p) or os.path.isabs(p) else (os.path.join(REPO, p) if os.path.exists(os.path.join(REPO, p)) else p)


def main():
    ap = _AP(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("new_run_dir")
    ap.add_argument("banked_workload_dir")
    ap.add_argument("--out", help="also write the JSON here")
    ap.add_argument("--ref", action="append", default=[], help="extra reference run dir (repeatable)")
    a = ap.parse_args()
    try:
        if not os.path.isdir(resolve(a.new_run_dir)):
            raise NoReceipt(f"new run dir not found: {a.new_run_dir}")
        if not os.path.isdir(resolve(a.banked_workload_dir)):
            raise NoReceipt(f"banked dir not found: {a.banked_workload_dir}")
        res = compare(resolve(a.new_run_dir), resolve(a.banked_workload_dir), [resolve(r) for r in a.ref])
    except Exception as e:  # a reporting tool: never crash, never exit non-zero
        res = {"comparable": None, "reason": f"{type(e).__name__}: {e}", "verdict_rule": VERDICT_RULE, "notes": []}
    res.setdefault("verdict_rule", VERDICT_RULE)
    res.setdefault("summary", f"{res.get('workload')} | comparable=null | {res.get('reason')}")
    s = json.dumps(res, indent=1)
    print(s)
    if a.out:
        try:
            with open(a.out, "w") as fh:
                fh.write(s + "\n")
        except OSError as e:
            print(f"receipt_compare: cannot write {a.out}: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
