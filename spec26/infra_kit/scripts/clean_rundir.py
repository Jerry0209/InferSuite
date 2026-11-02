#!/usr/bin/env python3
"""clean_rundir.py <rundir> — remove a benchmark's GENERATED files so an episode starts
from a pristine run directory.

Why this exists
---------------
SPEC run directories are reused across episodes, and some benchmarks APPEND to their
output rather than truncating it. Measured 2026-08-05 on 737.gmsh_r: after three runs at
index 0 (first campaign, the command-line timing sweep, then the 100 ms campaign) its
`choi.val` held 15 lines against a 5-line reference — exactly 3x — and specdiff correctly
reported a miscompare. The benchmark was fine; the directory was dirty.

Left unfixed this is worse than a failed check: a benchmark that reads leftover state
could shift its microarchitectural behaviour without any output check noticing.

What gets deleted
-----------------
Only files this benchmark PRODUCES, identified from SPEC's own command files:
  * every `-o` / `-e` redirect target in speccmds.cmd  (stdout/stderr per workload)
  * every specdiff "actual" argument in compare.cmd    (the validated outputs)
  * their .cmp / .mis comparison reports
Inputs are never touched — they are not named as outputs anywhere in those files.

Prints the number of files removed.
"""
import os
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_output import DIRECTIVE_PREFIXES, actual_file_of, split_cmdfile  # noqa: E402


def redirect_targets(rundir: str) -> set[str]:
    """`-o NAME` and `-e NAME` targets of every workload line in speccmds.cmd."""
    out: set[str] = set()
    p = os.path.join(rundir, "speccmds.cmd")
    if not os.path.exists(p):
        return out
    _pro, work = split_cmdfile(p)
    for line in work:
        try:
            toks = shlex.split(line)
        except ValueError:
            continue
        for i, t in enumerate(toks):
            if t in ("-o", "-e") and i + 1 < len(toks):
                out.add(os.path.basename(toks[i + 1]))
    return out


def compare_targets(rundir: str) -> set[str]:
    out: set[str] = set()
    p = os.path.join(rundir, "compare.cmd")
    if not os.path.exists(p):
        return out
    _pro, work = split_cmdfile(p)
    for line in work:
        af = actual_file_of(line)
        if af:
            out.add(os.path.basename(af))
    return out


def main() -> int:
    rundir = sys.argv[1]
    names = redirect_targets(rundir) | compare_targets(rundir)
    # comparison reports produced by our own verification step
    names |= {n + ext for n in set(names) for ext in (".cmp", ".mis")}
    removed = 0
    for n in sorted(names):
        fp = os.path.join(rundir, n)
        if os.path.isfile(fp):
            try:
                os.unlink(fp)
                removed += 1
            except OSError:
                pass
    print(removed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
