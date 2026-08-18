#!/usr/bin/env python3
"""pidcpu_poll.py — 2 Hz PER-PROCESS CPU sampler for one cgroup.

Why this exists: the TYPEID instrument set banks exact fence CPU (`cpu.stat`) and an argv
witness (`cmdlog.tsv`), but never joins them — `witness_cov` is a fraction of TICKS and
`top_progs` is a COUNT, so "which process burned the fence, for how long" is not derivable.
Splitting the fence delta across the PIDs observed alive in a tick does NOT recover it: on
the nine tasks with instruction-weighted ground truth that estimator keeps the leader on
only 6/9 and inflates `search` 1.5-66x, because a cheap grep alive during a heavy compile
takes an equal share. Presence is not consumption.

This samples consumption directly: utime+stime out of /proc/<pid>/stat, per PID, on the same
2 Hz tick as cmdlog, so the join is exact rather than estimated. No perf, no isolation, no
elevated privileges — it works under the TYPEID constraints.

Output `pidcpu.tsv`, one row per (tick, pid):   epoch \t pid \t utime_ticks \t stime_ticks
Cumulative counters, exactly like cpu.stat: take deltas between consecutive ticks. Divide by
os.sysconf('SC_CLK_TCK') (100 on this kernel) for seconds.

KNOWN LIMIT — the same one cmdlog carries: a process that lives and dies entirely between two
0.5 s samples is never seen, and its CPU lands in the residual. Per-tick residual is therefore
banked too: a `-` pid row carries the cgroup's own cpu.stat usage_usec at that instant, so the
consumer can bound what per-PID attribution missed (fence total minus sum-of-PIDs). Short
compiler processes (cc1, as, collect2) are exactly the population at risk; if the residual is
large, the fix is exit-time accounting (taskstats netlink), not a faster poll.
"""
import os
import sys
import time

CLK = os.sysconf("SC_CLK_TCK")


def read_pid(pid):
    """utime, stime in clock ticks. /proc/<pid>/stat field 2 (comm) may contain spaces and
    parentheses, so parse from the LAST ')' — fields after it start at `state`, making
    utime the 12th and stime the 13th token."""
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            raw = f.read()
    except (OSError, ValueError):
        return None
    cut = raw.rfind(b")")
    if cut < 0:
        return None
    rest = raw[cut + 2:].split()
    if len(rest) < 13:
        return None
    try:
        return int(rest[11]), int(rest[12])
    except ValueError:
        return None


def cg_usage(cg):
    try:
        with open(f"/sys/fs/cgroup/{cg}/cpu.stat") as f:
            for ln in f:
                if ln.startswith("usage_usec"):
                    return int(ln.split()[1])
    except OSError:
        pass
    return -1


def main():
    if len(sys.argv) < 4:
        sys.exit("usage: pidcpu_poll.py <cgroup-rel-path> <out.tsv> <stopfile> [interval_s]")
    cg, out, stopfile = sys.argv[1], sys.argv[2], sys.argv[3]
    iv = float(sys.argv[4]) if len(sys.argv) > 4 else 0.5
    procs = f"/sys/fs/cgroup/{cg}/cgroup.procs"
    os.nice(19)
    with open(out, "a", buffering=1) as fh:
        while os.path.exists(stopfile):
            t = time.time()
            try:
                with open(procs) as f:
                    pids = f.read().split()
            except OSError:
                pids = []
            rows = []
            for p in pids:
                v = read_pid(p)
                if v:
                    rows.append(f"{t:.6f}\t{p}\t{v[0]}\t{v[1]}\n")
            rows.append(f"{t:.6f}\t-\t{cg_usage(cg)}\t0\n")   # fence total, for the residual
            fh.writelines(rows)
            time.sleep(max(0.0, iv - (time.time() - t)))


if __name__ == "__main__":
    main()
