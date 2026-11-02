#!/usr/bin/env python3
"""perf_census.py — enumerate live `perf` processes and say which ones actually threaten
our measurement. Single source of truth for both the preflight gate and apply_isolation.

Why the distinction matters
---------------------------
This is a SHARED machine. The inherited single-user assumption was "any live perf is an
orphan, kill it" — on a shared box that SIGKILLs a colleague's in-flight capture. And
the converse mistake, "any live perf is fatal", blocks the campaign indefinitely on a
harmless leftover.

The real criterion is which counters a process holds. Software events (task-clock,
context-switches, page-faults, ...) are counted by the kernel and occupy NO
general-purpose PMU counter, so they cannot force multiplexing on our 4-GP-event
groups. Only a perf holding HARDWARE events competes for the counters this methodology
depends on.

Emits JSON: {"total": n, "hw": n, "foreign_hw": n, "procs": [...]}
"""
import glob
import json
import os
import pwd
import re
import sys

# perf's software PMU: counted by the kernel, no GP counter consumed.
SOFT = {
    "task-clock", "cpu-clock", "context-switches", "cs", "cpu-migrations", "migrations",
    "page-faults", "faults", "minor-faults", "major-faults", "alignment-faults",
    "emulation-faults", "dummy", "bpf-output", "cgroup-switches",
}


def events_of(argv: list[str]) -> list[str]:
    evs: list[str] = []
    for i, a in enumerate(argv):
        if a == "-e" and i + 1 < len(argv):
            evs += argv[i + 1].strip("{}").split(",")
        elif a.startswith("--event="):
            evs += a.split("=", 1)[1].strip("{}").split(",")
    # strip modifiers (:u, :k) and PMU-qualified forms (cpu/.../)
    return [re.split(r"[:/]", e.strip("{} "))[0] for e in evs if e.strip("{} ")]


def main() -> int:
    me = os.getuid()
    procs = []
    for d in glob.glob("/proc/[0-9]*"):
        # /proc/<pid>/exe is a permission-denied readlink for another user's process, so
        # keying on it silently skips exactly the processes we most need to see.
        # comm and cmdline are world-readable.
        try:
            if open(d + "/comm").read().strip() != "perf":
                continue
            argv = open(d + "/cmdline", "rb").read().decode(errors="replace").split("\0")
        except OSError:
            continue
        names = events_of(argv)
        hw = sorted({n for n in names if n and n not in SOFT})
        try:
            uid = os.stat(d).st_uid
        except OSError:
            continue
        try:
            user = pwd.getpwuid(uid).pw_name
        except KeyError:
            user = str(uid)
        procs.append({"pid": os.path.basename(d), "uid": uid, "user": user,
                      "n_ev": len(names), "hw": hw, "mine": uid == me})
    out = {
        "total": len(procs),
        "hw": sum(1 for p in procs if p["hw"]),
        "foreign_hw": sum(1 for p in procs if p["hw"] and not p["mine"]),
        "foreign": sum(1 for p in procs if not p["mine"]),
        "procs": procs,
    }
    json.dump(out, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
