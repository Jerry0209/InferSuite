#!/usr/bin/env python3
"""arm_server.py — the measurement half of one ARM Server pass (driven by server/run_server.sh).

Same counting as the SPEC profiler (arm_profile.py: Jef's families, ONE dedicated `perf stat`
pass per family, cycle counter + <= 6 events, 100 ms windows, no multiplexing), but for a
SERVER: counted on the 8 measured CPUs (-C 8-15) and filtered to the server's systemd scope
(-G jerryserver.slice/<unit>.scope) for a fixed CAPTURE_S, while the client runs on 0-7.

  arm_server.py isoproof --out FILE
  arm_server.py capture  --family F --cg CG --seconds S --out DIR
  arm_server.py finish   --out DIR --receipt pass|fail|na [--receipt-why TEXT]
  arm_server.py receipt  --bench B --out DIR          prints '<pass|fail|na> <why>'
  arm_server.py rejudge DIR                          re-evaluate a banked pass with the current gates
  arm_server.py summary  [--raw DIR]

Gates (x86 validate_dcperf.py D3/D4/D5 + the SPEC kit's witness), per pass:
  no_mux       every active window counted at pcnt-running >= 99.999
  windows      windows cover >= 95 % of CAPTURE_S, >= 1 active (perf stretches a window
               under load, never drops counts, so coverage — not the window count — is gated)
  frequency    frequency family only: cpu_cycles / cnt_cycles = 3.3 GHz +- 0.1
  steady (D4)  fence CPU rate, first vs last fifth of the 10 s means, drift <= 25 %,
               mean >= 0.10 cores
  fenced (D5)  measured-CPU busy not explained by the fence <= 20 % of measured busy
  witness      no foreign task (not ours, not in the fence) > 10 %, foreign total <= 40 %
  alive        the server scope still exists when the capture ends
  receipt      the workload's own evidence that it served (module-specific, from run_server.sh)
"""
import argparse
import json
import os
import statistics as st
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import arm_profile as ap  # noqa: E402  (PLAN, ev, parse, evaluate, iso_proof, witness_verdict, PERF)

M = ap.M
CPUS = os.environ.get("CPUS_MEASURED", "8-15")
MSLICE = os.environ.get("MSLICE", "jerryserver.slice")
RAW = ap.ARM / "data/raw/server"
OPERATOR_FILE = ap.ARM / "data/interim/server/operator_pids"
D4_IDLE_CORES, D4_MAX_DRIFT, D5_MAX_PCT = 0.10, 25.0, 20.0


def expand(spec):
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += range(int(a), int(b or a) + 1)
    return out


def perf_cmd(fam, cg, out_json):
    evs, env = ap.PLAN["families"][fam]["events"], M["environment"]
    return ["sudo", ap.PERF, "stat", "-j", "-I", str(M["window_ms"]), "-C", CPUS, "-o", str(out_json),
            "-e", "{" + ",".join(ap.ev(e) for e in evs) + "}", "-G", ",".join([cg] * len(evs)),
            "-e", ",".join(env), "-G", ",".join([cg] * len(env)), "--"]


class Poller(threading.Thread):
    """Every `poll` s: fence usage_usec and busy/total jiffies summed over the measured CPUs."""
    def __init__(self, cg, path, poll=0.5):
        super().__init__(daemon=True)
        self.stat = Path("/sys/fs/cgroup") / cg / "cpu.stat"
        self.path, self.poll, self.stop = path, poll, threading.Event()
        self.cpus = {f"cpu{c}" for c in expand(CPUS)}
        self.house = {f"cpu{c}" for c in expand(os.environ.get("CPUS_HOUSE", "0-7"))}

    def sample(self):
        busy = tot = hbusy = htot = 0
        for line in open("/proc/stat"):
            f = line.split()
            if f[0] in self.cpus or f[0] in self.house:
                v = list(map(int, f[1:]))
                if f[0] in self.cpus:
                    tot += sum(v)
                    busy += sum(v) - v[3] - v[4]
                else:
                    htot += sum(v)
                    hbusy += sum(v) - v[3] - v[4]
        try:
            u = int(next(x for x in open(self.stat) if x.startswith("usage_usec")).split()[1])
        except (OSError, StopIteration):
            u = -1
        return time.time(), u, busy, tot, hbusy, htot

    def run(self):
        with open(self.path, "w") as fh:
            fh.write("t\tfence_usage_usec\tmeas_busy_jiffies\tmeas_total_jiffies\thouse_busy_jiffies\thouse_total_jiffies\n")
            while True:
                fh.write("%.3f\t%d\t%d\t%d\t%d\t%d\n" % self.sample())
                fh.flush()
                if self.stop.wait(self.poll):
                    fh.write("%.3f\t%d\t%d\t%d\t%d\t%d\n" % self.sample())
                    return


def steady_and_fenced(path):
    rows = [list(map(float, ln.split("\t"))) for ln in open(path).read().splitlines()[1:]]
    rows = [r for r in rows if r[1] >= 0]
    if len(rows) < 3:
        return {"rows": len(rows)}
    rate = [((b[0] + a[0]) / 2, (b[1] - a[1]) / 1e6 / (b[0] - a[0])) for a, b in zip(rows, rows[1:])]
    sm, bucket, t0 = [], [], None                        # 10 s non-overlapping means (x86 D4)
    for t, r in rate:
        t0 = t if t0 is None else t0
        if t - t0 >= 10 and bucket:
            sm.append(st.mean(bucket))
            bucket, t0 = [], t
        bucket.append(r)
    if bucket:
        sm.append(st.mean(bucket))
    if len(sm) < 5:
        sm = [r for _, r in rate]
    n = max(1, len(sm) // 5)
    a, b = st.mean(sm[:n]), st.mean(sm[-n:])
    hz = os.sysconf("SC_CLK_TCK")
    meas_core_s = (rows[-1][2] - rows[0][2]) / hz
    fence_core_s = (rows[-1][1] - rows[0][1]) / 1e6
    return {"rows": len(rows), "mean_cores": fence_core_s / (rows[-1][0] - rows[0][0]),
            "first_fifth_cores": a, "last_fifth_cores": b,
            "drift_pct": 100 * abs(b - a) / max(a, b, 1e-9),
            "meas_busy_core_s": meas_core_s, "fence_core_s": fence_core_s,
            "house_busy_pct": (100 * (rows[-1][4] - rows[0][4]) / max(1, rows[-1][5] - rows[0][5])) if len(rows[0]) > 5 else None,
            "residual_pct": 100 * max(meas_core_s - fence_core_s, 0) / meas_core_s if meas_core_s > 1 else 0.0}


def hw_mux_bad(fam, wins):
    """Active windows where a HARDWARE family event was not counted 100 % of the time. Only PMU
    counters can be multiplexed; a software environment event (page-faults, ...) with zero
    runtime in a window reads <not counted> and means 0, not multiplexing (pagerank a1, t=0.1)."""
    evs = ap.PLAN["families"][fam]["events"]
    return [w["t"] for w in wins if (w["v"].get("task-clock") or 0) > 0
            and any(w["v"].get(e) is None or w["p"].get(e, 0) < M["pcnt_running_min"] for e in evs)]


def gates(meta, secs):
    sf, w, e = meta["steady_fenced"], meta["witness"], meta
    g = {"perf_rc": meta["perf_rc"] == 0, "no_mux": not meta["hw_mux_bad_t"],
         "windows": e["coverage"] >= 0.95 and e["n_active"] >= 1,
         "steady": sf.get("drift_pct", 1e9) <= D4_MAX_DRIFT and sf.get("mean_cores", 0) >= D4_IDLE_CORES,
         "fenced": sf.get("residual_pct", 1e9) <= D5_MAX_PCT,
         "witness": w["rows"] > 0 and w["dirty_rows"] == 0, "alive": meta["server_alive_at_end"]}
    if meta["family"] == "frequency":
        f = meta.get("ghz_cycles_per_cnt")
        g["frequency"] = f is not None and abs(f - M["nominal_ghz"]) <= M["freq_tolerance_ghz"]
    return g


def capture(fam, cg, secs, out):
    out.mkdir(parents=True, exist_ok=True)
    cgdir = Path("/sys/fs/cgroup") / cg
    assert cgdir.is_dir(), f"no server cgroup {cgdir}"
    # the operator's own agent (this Claude session, pid in OPERATOR_FILE) is tolerated, as
    # quiet_gate tolerates an ancestor; its children (tool calls) are still foreign
    ops = [int(x) for x in OPERATOR_FILE.read_text().split()] if OPERATOR_FILE.exists() else []
    ops = [p for p in ops if Path(f"/proc/{p}").exists()]
    wit = subprocess.Popen([sys.executable, str(ap.QUIET), "witness", "--out", str(out / "witness.tsv"),
                            "--poll", "2", "--mslice", MSLICE, "--mine", str(os.getppid())]
                           + [x for p in ops for x in ("--operator", str(p))])
    pol = Poller(cg, out / "poll.tsv")
    pol.start()
    t0 = time.time()
    try:
        perf_rc = subprocess.run(perf_cmd(fam, cg, out / "perf.json") + ["sleep", str(secs)]).returncode
    finally:
        t1 = time.time()
        pol.stop.set()
        pol.join()
        wit.terminate()
        wit.wait()
    alive = (cgdir / "cgroup.procs").exists() and bool((cgdir / "cgroup.procs").read_text().strip())
    numa = (cgdir / "memory.numa_stat").read_text().splitlines()[:2] if (cgdir / "memory.numa_stat").exists() else []
    wins = ap.parse(out / "perf.json")
    e = ap.evaluate(fam, wins)
    e["coverage"] = (wins[-1]["t"] / secs) if wins else 0.0          # perf's timer stretches windows
    e["max_window_s"] = max((x["win_s"] for x in wins), default=None)  # under load; counts stay complete
    e["hw_mux_bad_t"] = hw_mux_bad(fam, wins)
    w = ap.witness_verdict(out / "witness.tsv", "/nonexistent")       # foreign-task half only
    sf = steady_and_fenced(out / "poll.tsv")
    meta = {"family": fam, "events": ap.PLAN["families"][fam]["events"], "cpus": CPUS, "cgroup": cg,
            "capture_s": secs, "t_start": t0, "t_end": t1, "wall_s": t1 - t0, "perf_rc": perf_rc,
            "server_alive_at_end": alive, "witness_operator_pids": ops, "numa_stat": numa, "witness": w, "steady_fenced": sf, **e}
    if fam == "frequency" and e["sums"].get("cnt_cycles"):
        meta["ghz_cycles_per_cnt"] = e["sums"]["cpu_cycles"] / e["sums"]["cnt_cycles"]
    g = gates(meta, secs)
    meta["gates"] = g
    (out / "capture.json").write_text(json.dumps(meta, indent=1))
    bad = [k for k, v in g.items() if not v]
    print(f"capture {fam}: {e['n_active']}/{e['n_windows']} win, {sf.get('mean_cores', 0):.2f} cores, "
          f"drift {sf.get('drift_pct', -1):.1f}%, resid {sf.get('residual_pct', -1):.1f}%, "
          f"GHz {e['ghz_cycles_per_task_clock'] or 0:.3f} {'OK' if not bad else 'BAD ' + ','.join(bad)}", flush=True)
    return 0 if not bad else 2


def finish(out, receipt, why):
    meta = json.loads((out / "capture.json").read_text())
    meta["receipt"] = {"status": receipt, "why": why}
    meta["gates"]["receipt"] = receipt in ("pass", "na")
    meta["valid"] = all(meta["gates"].values())
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    print("VALID" if meta["valid"] else "INVALID " + ",".join(k for k, v in meta["gates"].items() if not v))
    return 0 if meta["valid"] else 2


def receipt(bench, out):
    """The workload's own evidence that it served while we counted -> (status, why)."""
    def txt(name):
        f = out / name
        return f.read_text(errors="replace") if f.exists() else ""

    def js(name):
        try:
            return json.loads(txt(name))
        except ValueError:
            return {}
    if bench == "renaissance":
        n = txt("renaissance.log").count("completed (")
        return ("pass" if n else "fail"), f"{n} renaissance operations completed"
    if bench == "dacapo":
        n = sum("completed warmup" in ln or "PASSED" in ln for ln in txt("dacapo.log").splitlines())
        return ("pass" if n else "fail"), f"{n} dacapo iterations completed"
    if bench == "cassandra":
        r = js("cassandra_receipt.json").get("status_lines", {})
        ok = (r.get("median_ops_per_s") or 0) > 0
        return ("pass" if ok else "fail"), f"YCSB median {r.get('median_ops_per_s')} ops/s over {r.get('n')} status lines"
    if bench == "kafka":
        r = js("kafka_receipt.json")
        ok = (r.get("producer_total_records_per_s") or 0) > 0 and (r.get("consumer_total_MB_per_s_last") or 0) > 0
        return ("pass" if ok else "fail"), (f"produce {r.get('producer_total_records_per_s')} rec/s, "
                                            f"consume {r.get('consumer_total_MB_per_s_last')} MB/s")
    if bench == "neo4j":
        r = js("neo4j_receipt.json")
        last = next((v for k, v in r.items() if k.startswith("last_")), {})
        ops = (last.get("all") or {}).get("ops_per_s") or 0
        return ("pass" if ops > 0 else "fail"), f"client {ops} ops/s in the last window"
    if bench == "spark":
        n = txt("spark_receipt.txt").count(" done at ")
        return ("pass" if n else "fail"), f"{n} spark passes completed"
    if bench == "feedsim":
        import csv
        rows = []
        if (out / "feedsim_results.txt").exists():
            for r in csv.DictReader(open(out / "feedsim_results.txt")):
                try:
                    if float(r["requested_qps"]) > 0:
                        rows.append((float(r["achieved_qps"]), float(r["95p_ms"])))
                except (KeyError, ValueError):
                    pass
        ok = bool(rows) and all(p95 <= 500 for _, p95 in rows)       # x86 D6: p95 <= 500 ms
        return ("pass" if ok else "fail"), f"{len(rows)} paced experiments, (QPS, p95 ms) = {rows}"
    if bench == "video_transcode":
        ok = "Running M" in txt("vtb_run.log")
        return ("pass" if ok else "fail"), "encode stage running (batch: no SLA)" if ok else "no 'Running M' marker"
    if bench == "selftest":
        n = len(txt("client.log").split())
        return ("pass" if n else "fail"), f"client ran {n} s"
    return "na", f"no receipt rule for {bench}"


def rejudge(out):
    """Re-evaluate a banked pass from its own files with the current gate rules."""
    m = json.loads((out / "capture.json").read_text())
    wins = ap.parse(out / "perf.json")
    m.update(ap.evaluate(m["family"], wins))
    m["coverage"] = (wins[-1]["t"] / m["capture_s"]) if wins else 0.0
    m["hw_mux_bad_t"] = hw_mux_bad(m["family"], wins)
    m["gates"] = gates(m, m["capture_s"])
    m["rejudged"] = time.time()
    (out / "capture.json").write_text(json.dumps(m, indent=1))
    old = json.loads((out / "meta.json").read_text()) if (out / "meta.json").exists() else {}
    r = old.get("receipt") or dict(zip(("status", "why"), receipt(out.parent.parent.name and BENCH_OF.get(out.parent.parent.name, ""), out)))
    return finish(out, r["status"], r["why"])


BENCH_OF = {"tomcat": "dacapo", "feedsim": "feedsim", "finagle-chirper": "renaissance", "finagle-http": "renaissance",
            "cassandra-ycsb20m": "cassandra", "kafka-20g": "kafka", "naivebayes-rcv1": "spark",
            "neo4j-livejournal": "neo4j", "pagerank-livejournal": "spark", "video-4k": "video_transcode", "selftest": "selftest"}


def summary(raw):
    for d in sorted(raw.glob("*/*/DONE")):
        m = json.loads((d.parent / d.read_text().strip() / "meta.json").read_text())
        sf = m["steady_fenced"]
        print(f"{d.parent.parent.name:22s} {m['family']:20s} {d.read_text().strip():3s} inst={m['sums'].get('inst_retired', 0):.3e} "
              f"cores={sf['mean_cores']:.2f} drift={sf['drift_pct']:.1f}% resid={sf['residual_pct']:.1f}% "
              f"GHz={m['ghz_cycles_per_task_clock']:.3f}")


def main():
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd", required=True)
    i = sp.add_parser("isoproof")
    i.add_argument("--out", required=True)
    c = sp.add_parser("capture")
    c.add_argument("--family", required=True)
    c.add_argument("--cg", required=True)
    c.add_argument("--seconds", type=float, required=True)
    c.add_argument("--out", required=True)
    f = sp.add_parser("finish")
    f.add_argument("--out", required=True)
    f.add_argument("--receipt", required=True, choices=["pass", "fail", "na"])
    f.add_argument("--receipt-why", default="")
    r = sp.add_parser("receipt")
    r.add_argument("--bench", required=True)
    r.add_argument("--out", required=True)
    j = sp.add_parser("rejudge")
    j.add_argument("out")
    s = sp.add_parser("summary")
    s.add_argument("--raw", default=str(RAW))
    a = p.parse_args()
    if a.cmd == "isoproof":
        Path(a.out).write_text(json.dumps(ap.iso_proof()))
        return 0
    if a.cmd == "capture":
        assert a.family in ap.PLAN["families"], a.family
        return capture(a.family, a.cg, a.seconds, Path(a.out))
    if a.cmd == "receipt":
        print(*receipt(a.bench, Path(a.out)))
        return 0
    if a.cmd == "rejudge":
        return rejudge(Path(a.out))
    if a.cmd == "finish":
        return finish(Path(a.out), a.receipt, a.receipt_why)
    summary(Path(a.raw))
    return 0


if __name__ == "__main__":
    sys.exit(main())
