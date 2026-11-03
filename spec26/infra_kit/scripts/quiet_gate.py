#!/usr/bin/env python3
"""quiet_gate.py — is anybody else using this SHARED machine right now?

The isolation shield (apply_isolation) keeps other work OFF the measured cores, but the
L3 and the memory controllers are shared by every core. A colleague's job on the house
cores therefore still pollutes LLC and DRAM measurements, and the system-wide IMC
counters (unc_m_cas_count.*) cannot be attributed to a cgroup at all. So before and
during an LLC/DRAM capture we need the whole machine quiet, not just the partition.

"Foreign" = every process that is not in the measurement fence (MSLICE) and not a
descendant of --mine (the capture driver: perf, pollers, this script) or an ancestor of
this script (the operator's own shell/agent). Interactive
sessions (editors, shells, idle agents) sit at ~1% each and are tolerated; a TASK is a
process above --proc-max percent of one CPU, or a total above --total-max.

  quiet_gate.py check   [--sample S]                     one sample, exit 0 if quiet
  quiet_gate.py wait    [--hold H] [--poll P]            block until quiet for H seconds
  quiet_gate.py witness --out FILE [--poll P]            log every P s until killed
"""
import argparse
import os
import pwd
import sys
import time

HZ = os.sysconf("SC_CLK_TCK")


def descendants(root: int) -> set[int]:
    kids: dict[int, list[int]] = {}
    for p in os.listdir("/proc"):
        if not p.isdigit():
            continue
        try:
            ppid = int(open(f"/proc/{p}/stat").read().rsplit(")", 1)[1].split()[1])
        except (OSError, IndexError, ValueError):
            continue
        kids.setdefault(ppid, []).append(int(p))
    out, todo = set(), [root]
    while todo:
        n = todo.pop()
        if n in out:
            continue
        out.add(n)
        todo += kids.get(n, [])
    return out


def ancestors(pid: int) -> set[int]:
    """The shells and agent that launched us are the operator, not a foreign task."""
    out = set()
    while pid > 1:
        out.add(pid)
        try:
            pid = int(open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[1])
        except (OSError, IndexError, ValueError):
            break
    return out


def snap(mslice: str, mine: set[int]) -> dict[int, tuple[float, str, str]]:
    d = {}
    for p in os.listdir("/proc"):
        if not p.isdigit():
            continue
        pid = int(p)
        if pid in mine:
            continue
        try:
            raw = open(f"/proc/{p}/stat").read()
            comm = raw[raw.index("(") + 1:raw.rindex(")")]
            f = raw.rsplit(")", 1)[1].split()
            ticks = int(f[11]) + int(f[12])          # utime + stime
            if f"/{mslice}/" in open(f"/proc/{p}/cgroup").read():
                continue
            uid = os.stat(f"/proc/{p}").st_uid
        except (OSError, ValueError, IndexError):
            continue
        try:
            user = pwd.getpwuid(uid).pw_name
        except KeyError:
            user = str(uid)
        d[pid] = (ticks / HZ, user, comm)
    return d


def sample(secs: float, mslice: str, mine_root: int | None):
    mine = descendants(mine_root) if mine_root else set()
    mine |= ancestors(os.getpid())
    a = snap(mslice, mine)
    time.sleep(secs)
    if mine_root:
        mine |= descendants(mine_root)
    b = snap(mslice, mine)
    busy = []
    for pid, (t1, user, comm) in b.items():
        t0 = a.get(pid, (t1, user, comm))[0]          # new process: count from now
        pct = 100 * (t1 - t0) / secs
        if pct > 0.5:
            busy.append((pct, pid, user, comm))
    busy.sort(reverse=True)
    return sum(x[0] for x in busy), busy


def verdict(total, busy, proc_max, total_max):
    tasks = [x for x in busy if x[0] > proc_max]
    return (not tasks and total <= total_max), tasks


def fmt(busy, n=4):
    return " ".join(f"{u}:{c}[{pid}]={pct:.0f}%" for pct, pid, u, c in busy[:n]) or "-"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["check", "wait", "witness"])
    ap.add_argument("--sample", type=float, default=5.0)
    ap.add_argument("--hold", type=float, default=180.0)
    ap.add_argument("--poll", type=float, default=10.0)
    ap.add_argument("--proc-max", type=float, default=10.0)
    ap.add_argument("--total-max", type=float, default=40.0)
    ap.add_argument("--mslice", default="measured.slice")
    ap.add_argument("--mine", type=int, default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    if a.mode == "check":
        total, busy = sample(a.sample, a.mslice, a.mine)
        ok, tasks = verdict(total, busy, a.proc_max, a.total_max)
        print(f"{'QUIET' if ok else 'BUSY'} foreign_total={total:.0f}% top: {fmt(busy)}")
        return 0 if ok else 1

    if a.mode == "wait":
        quiet_since = None
        while True:
            total, busy = sample(a.poll, a.mslice, a.mine)
            ok, _ = verdict(total, busy, a.proc_max, a.total_max)
            now = time.time()
            quiet_since = (quiet_since or now) if ok else None
            held = now - quiet_since if quiet_since else 0
            print(f"{time.strftime('%H:%M:%S')} {'quiet' if ok else 'BUSY '} "
                  f"held={held:4.0f}s foreign_total={total:.0f}% top: {fmt(busy)}", flush=True)
            if ok and held >= a.hold:
                return 0

    # witness: append one row per poll until killed; analysed after the capture
    with open(a.out, "a") as fh:
        while True:
            total, busy = sample(a.poll, a.mslice, a.mine)
            fh.write(f"{time.time():.3f}\t{total:.1f}\t{fmt(busy, 5)}\n")
            fh.flush()


if __name__ == "__main__":
    sys.exit(main())
