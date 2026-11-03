#!/usr/bin/env python3
"""arm_profile.py — SPEC CPU 2026 single-core profile on AWS Graviton (ARM).

Jef's ARM method, reimplemented: ONE dedicated `perf stat` pass per metric family (cycle
counter + <= 6 programmable events, so no multiplexing, no rotation), 100 ms windows,
counted on the measured CPU and filtered to our fence cgroup. Families/events/formulas:
../config/profiling_plan.toml. Isolation: arm_shield.sh (ISO-PROOF before every pass).

  arm_profile.py qualify [--out DIR]
        per-boot gate: count every family for 1.5 s on CPU 8 with a pinned busy probe
        already inside the fence; every row must be counted at pcnt-running >= 99.999.
  arm_profile.py run --families tier1|tier2|<f1,f2> [--bench all|<b1,b2>] [--out DIR] [--shield]
        family-major sweeps; resumable (DONE marker per <bench, family>); --shield applies
        the isolation at start and restores it on ANY exit.
  arm_profile.py check PASS_DIR          re-evaluate one banked pass
  arm_profile.py summary [--out DIR]     DONE passes + cross-pass inst_retired spread

Launch: perf forks the workload; the child writes its own pid into the fence's
cgroup.procs BEFORE exec (no moved-after-fork window), drops to the invoking user and
execs `taskset -c 8 bash run.sh`. run.sh runs SPEC's index-0 ref command line and banks its
exit status (perf 6.17 returns 0 whatever the workload's status is: checked 2026-11-03).
"""
import argparse
import json
import os
import pwd
import shlex
import signal
import subprocess
import sys
import threading
import time
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARM = HERE.parent
REPO = ARM.parent
KIT = REPO / "spec26/infra_kit/scripts"
PLAN = tomllib.load(open(ARM / "config/profiling_plan.toml", "rb"))
M = PLAN["meta"]
CPU = M["measured_cpu"]
CG = M["fence_cgroup"]
LEAF = Path("/sys/fs/cgroup") / CG
SPEC_ROOT = Path(os.environ.get("SPEC_ROOT", "/home/ubuntu/spec26-arm/cpu2026"))
CMDS = ARM / "data/interim/spec/cmds"
RAW = ARM / "data/raw/spec26"
PERF = os.environ.get("PERF", "/usr/bin/perf")
SHIELD = HERE / "arm_shield.sh"
QUIET = KIT / "quiet_gate.py"
EPISODE_MAX_S = float(os.environ.get("EPISODE_MAX_S", 10800))
NO_OUTPUT_CHECK = {"734.vpr_r", "735.gem5_r", "772.marian_r"}   # "unavailable", as on x86


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def benches():
    out = subprocess.run(["bash", "-c", f"source {KIT}/spec_env.sh; echo ${{SPEC_RATE_BENCHES[@]}}"],
                         capture_output=True, text=True, check=True).stdout.split()
    assert len(out) == 26, out
    return out


def families(sel):
    fams = PLAN["families"]
    if sel in ("tier1", "tier2"):
        return [f for f in fams if fams[f]["tier"] == int(sel[-1])]
    out = sel.split(",")
    bad = [f for f in out if f not in fams]
    assert not bad, f"unknown families {bad}"
    return out


def ev(name):
    code = PLAN["raw"].get(name)
    return f"{M['pmu']}/event={code},name={name}/" if code else name


def perf_cmd(fam, out_json, interval=True):
    evs, env = PLAN["families"][fam]["events"], M["environment"]
    return (["sudo", PERF, "stat", "-j"] + (["-I", str(M["window_ms"])] if interval else [])
            + ["-C", str(CPU), "-o", str(out_json),
               "-e", "{" + ",".join(ev(e) for e in evs) + "}", "-G", ",".join([CG] * len(evs)),
               "-e", ",".join(env), "-G", ",".join([CG] * len(env)), "--"])


def as_user(cmd):
    """sh snippet run as root by perf's child: join the fence, then drop to us and exec."""
    pw = pwd.getpwuid(os.getuid())
    env = (f"env -i HOME={pw.pw_dir} USER={pw.pw_name} LOGNAME={pw.pw_name} "
           f"PATH=/usr/local/bin:/usr/bin:/bin LANG={os.environ.get('LANG', 'C.UTF-8')}")
    return (f"echo $$ > {LEAF}/cgroup.procs && exec setpriv --reuid={pw.pw_uid} "
            f"--regid={pw.pw_gid} --init-groups {env} taskset -c {CPU} {cmd}")


def kill_fence():
    if (LEAF / "cgroup.kill").exists():
        subprocess.run(["sudo", "sh", "-c", f"echo 1 > {LEAF}/cgroup.kill"], check=False)


# ---------------------------------------------------------------- perf JSON
def parse(path):
    """perf stat -j [-I] output -> windows [{'t', 'win_s', 'v': {event: float|None}, 'p': {event: pcnt}}].
    Without -I there is one pseudo-window (t = 0). Unparseable counts (<not counted>,
    <not supported>) become None."""
    wins, cur, t_prev = [], None, 0.0
    for line in open(path):
        if not line.startswith("{"):
            continue
        r = json.loads(line)
        t = float(r.get("interval", 0.0))
        if cur is None or t != cur["t"]:
            cur = {"t": t, "win_s": t - t_prev, "v": {}, "p": {}}
            t_prev = t
            wins.append(cur)
        try:
            v = float(r.get("counter-value", ""))
        except ValueError:
            v = None
        cur["v"][r["event"]] = v
        cur["p"][r["event"]] = float(r.get("pcnt-running") or 0)
    return wins


def evaluate(fam, wins):
    """Counting validity over windows. Active window = fence task-clock > 0."""
    evs = PLAN["families"][fam]["events"] + M["environment"]
    active = [w for w in wins if (w["v"].get("task-clock") or 0) > 0]
    bad = [w["t"] for w in active
           if any(w["v"].get(e) is None or w["p"].get(e, 0) < M["pcnt_running_min"] for e in evs)]
    sums = {e: sum(w["v"].get(e) or 0 for w in wins) for e in evs}
    tc_s = sums["task-clock"] / 1e9
    out = {"n_windows": len(wins), "n_active": len(active), "n_mux_bad": len(bad),
           "mux_bad_t": bad[:20], "sums": sums, "task_clock_s": tc_s,
           "min_pcnt_running": min((w["p"].get(e, 0) for w in active for e in evs), default=None),
           "ghz_cycles_per_task_clock": sums["cpu_cycles"] / sums["task-clock"] if sums["task-clock"] else None}
    if fam == "frequency" and sums.get("cnt_cycles"):
        out["ghz_cycles_per_cnt"] = sums["cpu_cycles"] / sums["cnt_cycles"]
    return out


# ---------------------------------------------------------------- witness
class ProcStat(threading.Thread):
    """Per-CPU busy % of CPUs 0-15 every `poll` s (the partition half of the witness)."""
    def __init__(self, path, poll=2.0):
        super().__init__(daemon=True)
        self.path, self.poll, self.stop = path, poll, threading.Event()

    @staticmethod
    def read():
        d = {}
        for line in open("/proc/stat"):
            f = line.split()
            if f[0].startswith("cpu") and f[0][3:].isdigit():
                v = list(map(int, f[1:]))
                d[int(f[0][3:])] = (sum(v), v[3] + v[4])
        return d

    def run(self):
        with open(self.path, "w") as fh:
            a = self.read()
            while not self.stop.wait(self.poll):
                b = self.read()
                row = {c: 100 * (1 - (b[c][1] - a[c][1]) / max(1, b[c][0] - a[c][0])) for c in b if c in a}
                fh.write(f"{time.time():.3f}\t" + "\t".join(f"{c}:{row[c]:.1f}" for c in sorted(row)) + "\n")
                fh.flush()
                a = b


def witness_verdict(wpath, ppath, proc_max=10.0, total_max=40.0, sib_max=10.0):
    """Foreign work overlapping the pass (quiet_gate thresholds) or a busy measured sibling."""
    rows = dirty = 0
    max_total = max_task = 0.0
    for line in open(wpath) if Path(wpath).exists() else []:
        ts, total, top = line.rstrip("\n").split("\t")
        rows += 1
        tasks = [float(x.rsplit("=", 1)[1].rstrip("%")) for x in top.split() if "=" in x]
        mt = max(tasks, default=0.0)
        max_total, max_task = max(max_total, float(total)), max(max_task, mt)
        dirty += float(total) > total_max or mt > proc_max
    sib = []
    cpu8 = []
    for line in open(ppath) if Path(ppath).exists() else []:
        f = dict(x.split(":") for x in line.split("\t")[1:])
        sib.append(max(float(f[str(c)]) for c in range(9, 16) if str(c) in f))
        cpu8.append(float(f.get(str(CPU), "nan")))
    sib_dirty = sum(s > sib_max for s in sib)
    return {"rows": rows, "dirty_rows": dirty, "max_foreign_total_pct": max_total,
            "max_foreign_task_pct": max_task, "siblings_max_pct": max(sib, default=None),
            "siblings_dirty_rows": sib_dirty,
            "cpu8_mean_busy_pct": sum(cpu8) / len(cpu8) if cpu8 else None,
            "clean": rows > 0 and dirty == 0 and sib_dirty == 0}


# ---------------------------------------------------------------- gates
def iso_proof(timeout_s=3600):
    """ISO-PROOF; while it fails because the machine is busy, wait (never kill anything)."""
    t0 = time.time()
    while True:
        p = subprocess.run(["bash", str(SHIELD), "verify"], capture_output=True, text=True,
                           env={**os.environ, "MINE": str(os.getpid())})
        j = json.loads(p.stdout.strip().splitlines()[-1]) if p.stdout.strip() else {"iso_proof": False, "why": p.stderr}
        if j.get("iso_proof"):
            return j
        if time.time() - t0 > timeout_s:
            raise SystemExit(f"ISO-PROOF failed for {timeout_s}s, aborting: {j}")
        log(f"  ISO-PROOF not held ({j.get('why')}), waiting 30 s")
        time.sleep(30)


def qualify(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    iso = iso_proof(600)
    res = {"iso": iso, "ts": time.time(), "families": {}}
    ok_all = True
    for fam in PLAN["families"]:
        probe = subprocess.Popen(["sudo", "sh", "-c", as_user("sh -c 'while :; do :; done'")])
        for _ in range(50):
            if (LEAF / "cgroup.procs").read_text().strip():
                break
            time.sleep(0.05)
        time.sleep(0.3)                                        # probe has exec'd its loop
        js = out / f"qual_{fam}.json"
        rc = subprocess.run(perf_cmd(fam, js, interval=False) + ["sleep", "1.5"]).returncode
        kill_fence()
        probe.wait()
        e = evaluate(fam, parse(js))
        ok = rc == 0 and e["n_active"] == 1 and e["n_mux_bad"] == 0
        ok_all &= ok
        res["families"][fam] = {"ok": ok, "perf_rc": rc, **e}
        extra = f" cnt/task-clock={e['sums']['cnt_cycles'] / e['sums']['task-clock']:.4f} GHz" if fam == "frequency" else ""
        log(f"qualify {fam:22s} {'OK ' if ok else 'BAD'} min_pcnt={e['min_pcnt_running']} "
            f"cyc/task-clock={e['ghz_cycles_per_task_clock']:.4f} GHz{extra}")
    res["ok"] = ok_all
    (out / "qualification.json").write_text(json.dumps(res, indent=1))
    log(f"qualification {'PASSED' if ok_all else 'FAILED'} -> {out / 'qualification.json'}")
    return ok_all


def judge(fam, meta):
    g = {"perf_rc": meta["perf_rc"] == 0, "bench_rc": meta["bench_rc"] == 0,
         "windows": meta["n_active"] >= 1, "no_mux": meta["n_mux_bad"] == 0,
         "output": meta["output_check"].get("status") in ("pass", "unavailable"),
         "witness": meta["witness"]["clean"], "not_timed_out": not meta["timed_out"]}
    if fam == "frequency":
        f = meta.get("ghz_cycles_per_cnt")
        g["frequency"] = f is not None and abs(f - M["nominal_ghz"]) <= M["freq_tolerance_ghz"]
    return g


def one_pass(bench, fam, pdir):
    pdir.mkdir(parents=True, exist_ok=True)
    rd = SPEC_ROOT / f"benchspec/CPU/{bench}/run/run_base_refrate_uarch.0000"
    cmd = (CMDS / bench / "speccmds_all.txt").read_text().splitlines()[0]   # ref command index 0
    iso = iso_proof()
    subprocess.run([sys.executable, str(KIT / "clean_rundir.py"), str(rd)], capture_output=True)
    rc_file = pdir / "bench.rc"
    rc_file.unlink(missing_ok=True)
    (pdir / "run.sh").write_text(
        f"cd {shlex.quote(str(rd))} || exit 97\nset -a; . {shlex.quote(str(CMDS / bench / 'env.sh'))}; set +a\n"
        f"{cmd}\necho $? > {shlex.quote(str(rc_file))}\n")
    wit = subprocess.Popen([sys.executable, str(QUIET), "witness", "--out", str(pdir / "witness.tsv"),
                            "--poll", "2", "--mslice", "jerry-measured", "--mine", str(os.getpid())])
    ps = ProcStat(pdir / "procstat.tsv")
    ps.start()
    t0 = time.time()
    timed_out = False
    try:
        with open(pdir / "bench.log", "w") as bl:
            p = subprocess.Popen(perf_cmd(fam, pdir / "perf.json") + ["sh", "-c", as_user(f"bash {pdir / 'run.sh'}")],
                                 stdout=bl, stderr=subprocess.STDOUT)
            try:
                perf_rc = p.wait(timeout=EPISODE_MAX_S)
            except subprocess.TimeoutExpired:
                timed_out = True
                kill_fence()
                perf_rc = p.wait()
    finally:
        t1 = time.time()
        ps.stop.set()
        ps.join()
        wit.terminate()
        wit.wait()
    bench_rc = int(rc_file.read_text()) if rc_file.exists() else None
    if bench in NO_OUTPUT_CHECK:
        vj = {"status": "unavailable", "why": "no SPEC compare for the index-0 output (as on x86)"}
    else:
        vp = subprocess.run([sys.executable, str(KIT / "verify_output.py"), str(rd), str(t0), "0"],
                            capture_output=True, text=True, env={**os.environ, "SPEC_ROOT": str(SPEC_ROOT)})
        try:
            vj = json.loads(vp.stdout)
        except ValueError:
            vj = {"status": "error", "stderr": vp.stderr[-500:]}
    meta = {"bench": bench, "family": fam, "events": PLAN["families"][fam]["events"],
            "cmd_index": 0, "cmd": cmd, "cpu": CPU, "cgroup": CG, "t_start": t0, "t_end": t1,
            "wall_s": t1 - t0, "perf_rc": perf_rc, "bench_rc": bench_rc, "timed_out": timed_out,
            "output_check": vj, "iso": iso,
            "witness": witness_verdict(pdir / "witness.tsv", pdir / "procstat.tsv"),
            **evaluate(fam, parse(pdir / "perf.json"))}
    meta["gates"] = judge(fam, meta)
    meta["valid"] = all(meta["gates"].values())
    (pdir / "meta.json").write_text(json.dumps(meta, indent=1))
    return meta


def run(fams, bl, out, shield):
    applied = False

    def bail(sig, _frm):
        raise SystemExit(f"signal {sig}")
    for s in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(s, bail)
    try:
        if shield:
            applied = True                 # restore is a no-op without a snapshot, so arm it first
            subprocess.run(["bash", str(SHIELD), "apply"], check=True)
        for fam in fams:
            log(f"======== sweep: family {fam} over {len(bl)} benchmark(s)")
            for b in bl:
                fdir = Path(out) / b / fam
                if (fdir / "DONE").exists():
                    continue
                for attempt in range(1, 4):
                    m = one_pass(b, fam, fdir / f"a{attempt}")
                    bad = [k for k, v in m["gates"].items() if not v]
                    log(f"{b:18s} {fam:20s} a{attempt} {m['wall_s']:7.1f}s inst={m['sums'].get('inst_retired', 0):.4e} "
                        f"GHz={m['ghz_cycles_per_task_clock'] or 0:.3f} win={m['n_active']} "
                        f"out={m['output_check'].get('status')} rc={m['bench_rc']} "
                        f"{'VALID' if m['valid'] else 'INVALID ' + ','.join(bad)}")
                    if m["valid"]:
                        (fdir / "DONE").write_text(f"a{attempt}\n")
                        break
                    if attempt >= 2 and not (m["gates"]["bench_rc"] and m["gates"]["output"]):
                        break                                  # deterministic run failure: record it
    finally:
        kill_fence()
        if applied:
            subprocess.run(["bash", str(SHIELD), "restore"])


def summary(out):
    rows = []
    for d in sorted(Path(out).glob("*/*/DONE")):
        m = json.loads((d.parent / d.read_text().strip() / "meta.json").read_text())
        rows.append((m["bench"], m["family"], m["sums"].get("inst_retired"), m["wall_s"]))
    by = {}
    for b, f, i, w in rows:
        by.setdefault(b, []).append((f, i, w))
    for b, xs in by.items():
        ins = [i for _, i, _ in xs if i]
        spread = (max(ins) - min(ins)) / min(ins) if len(ins) > 1 else 0.0
        flag = "OK " if spread <= M["determinism_tol"] else "BAD"
        print(f"{b:18s} passes={len(xs):2d} inst_spread={100 * spread:.3f}% {flag} "
              f"wall={sum(w for *_, w in xs) / len(xs):.1f}s")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    q = sp.add_parser("qualify")
    q.add_argument("--out", default=str(ARM / "data/raw/qualification" / time.strftime("%Y%m%dT%H%M%S")))
    r = sp.add_parser("run")
    r.add_argument("--families", required=True)
    r.add_argument("--bench", default="all")
    r.add_argument("--out", default=str(RAW))
    r.add_argument("--shield", action="store_true")
    c = sp.add_parser("check")
    c.add_argument("pass_dir")
    s = sp.add_parser("summary")
    s.add_argument("--out", default=str(RAW))
    a = ap.parse_args()
    if getattr(a, "out", None):
        a.out = str(Path(a.out).resolve())      # run.sh cd's into the SPEC run dir before writing bench.rc
    if a.cmd == "qualify":
        return 0 if qualify(a.out) else 1
    if a.cmd == "run":
        bl = benches() if a.bench == "all" else a.bench.split(",")
        run(families(a.families), bl, a.out, a.shield)
    elif a.cmd == "check":
        m = json.loads((Path(a.pass_dir) / "meta.json").read_text())
        m.update(evaluate(m["family"], parse(Path(a.pass_dir) / "perf.json")))
        print(json.dumps({"gates": judge(m["family"], m), "n_active": m["n_active"], "n_mux_bad": m["n_mux_bad"]}, indent=1))
    elif a.cmd == "summary":
        summary(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
