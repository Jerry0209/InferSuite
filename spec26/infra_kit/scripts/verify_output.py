#!/usr/bin/env python3
"""verify_output.py <rundir> <t_start_epoch> [cmd_index] — run SPEC's OWN correctness
check over exactly the outputs our one workload produced.

Why this exists
---------------
We bypass `runcpu` and exec the benchmark directly inside the measurement fence, so we
also bypass the validation runcpu would normally do. Without it, a benchmark that
segfaulted 30 s in, or that the episode fuse truncated, still yields a full set of
counter windows indistinguishable from a good episode. The uarch numbers would be real
but they would not describe the workload we claim to have measured.

SPEC ships the check: every run dir has `compare.cmd`, one `specdiff` line per output
file, comparing against the expected copy under data/<size>/output.

Selecting the right compare lines
---------------------------------
We run ONE of the benchmark's workloads, so only some outputs exist. Two earlier ideas
both fail on real benchmarks:

  * index-to-index mapping — compare.cmd is not in speccmds order (708.sqlite_r runs
    main,cte,fp but compares cte,fp,main);
  * matching the workload's `-o` stdout name — 8 of 26 validate a GENERATED FILE rather
    than stdout (749.fotonik3d_r writes pscyee.out and compares that, not fotonik3d.log).

So we select by what the episode actually wrote: a compare line is in scope iff its
target file exists AND was modified at or after the episode start. That covers stdout
and generated files alike, needs no mapping table, and cannot be fooled by a stale
output left in the run dir by an earlier episode.

Emits JSON on stdout:
  {"status": "pass"|"fail"|"unmatched"|"missing", "checked": [...], "failed": [...]}
"""
import json
import os
import shlex
import subprocess
import sys
import tempfile

# Lines that configure specinvoke rather than naming a command. NOTE: `-i` is NOT here —
# in speccmds.cmd `-i <file>` is a workload's stdin redirect (722.palm_r, 765.roms_r),
# and treating it as a directive made those benchmarks parse as having zero workloads.
DIRECTIVE_PREFIXES = ("-E ", "-r", "-N ", "-C ", "-S ")

# specdiff flags that consume a following value; everything else starting with '-' is
# a bare flag. Needed to find the trailing <expected> <actual> pair.
VALUE_FLAGS = {"-l", "--abstol", "--reltol", "-a", "-e", "--floatcompare_tol"}


def split_cmdfile(path: str) -> tuple[list[str], list[str]]:
    """-> (prologue directives, command lines)."""
    pro, work = [], []
    with open(path) as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            (pro if line.startswith(DIRECTIVE_PREFIXES) else work).append(line)
    return pro, work


def actual_file_of(line: str) -> str | None:
    """The file a specdiff line VALIDATES (its last positional arg before the redirect).

    specdiff is invoked as `... specdiff <flags> <expected_abs_path> <actual_rel>`.
    """
    if "specdiff" not in line:
        return None
    try:
        toks = shlex.split(line)
    except ValueError:
        return None
    try:
        k = next(i for i, t in enumerate(toks) if t.endswith("specdiff"))
    except StopIteration:
        return None
    pos, skip = [], False
    for t in toks[k + 1:]:
        if skip:
            skip = False
            continue
        if t == ">":
            break
        if t.startswith("-"):
            if t in VALUE_FLAGS:
                skip = True
            continue
        pos.append(t)
    return pos[-1] if pos else None


def main() -> int:
    rundir = sys.argv[1]
    t_start = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    cmd_index = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    spec = os.environ.get("SPEC_ROOT") or os.environ["SPEC"]

    cc = os.path.join(rundir, "compare.cmd")
    if not os.path.exists(cc):
        print(json.dumps({"status": "missing", "detail": "no compare.cmd in run dir"}))
        return 0

    pro, work = split_cmdfile(cc)

    # 2 s of slack: the fence starts a moment before the benchmark opens its outputs,
    # and mtime granularity is coarse on some filesystems.
    cutoff = t_start - 2.0
    selected, stale, absent = [], [], []
    for line in work:
        af = actual_file_of(line)
        if not af:
            continue
        p = af if os.path.isabs(af) else os.path.join(rundir, af)
        if not os.path.exists(p):
            absent.append(af)
        elif os.path.getmtime(p) < cutoff:
            stale.append(af)
        else:
            selected.append((af, line))

    if not selected:
        # Distinguish two situations that are NOT the same thing. Some benchmarks'
        # compare targets are files a POST-PROCESSING step derives from the raw run
        # (734.vpr_r compares compare_*_swap_accepted.out, extracted from its .log).
        # That step is in neither compare.cmd nor any command line we execute, so
        # running one command line directly can never produce them — the benchmark ran
        # fine, its output just is not specdiff-testable this way. Reporting that as
        # "the run produced nothing" is false and sends the reader hunting a phantom.
        wrote = []
        try:
            for fn in os.listdir(rundir):
                fp = os.path.join(rundir, fn)
                if os.path.isfile(fp) and os.path.getmtime(fp) >= cutoff:
                    wrote.append(fn)
        except OSError:
            pass
        if wrote:
            status, detail = "unavailable", (
                f"benchmark wrote {len(wrote)} file(s) but none are specdiff targets — "
                f"this benchmark's compare inputs come from a post-processing step that "
                f"is not part of any ref command line, so output cannot be validated "
                f"when running a single command line directly")
        else:
            status, detail = "nothing_written", (
                f"no file in the run dir was modified since episode start "
                f"({len(absent)} compare targets not produced)")
        print(json.dumps({
            "status": status, "cmd_index": cmd_index, "detail": detail,
            "wrote_files": wrote[:10], "n_wrote": len(wrote),
            "absent": absent[:10], "stale": stale[:10],
        }))
        return 0

    # Clear prior reports so we never read a previous episode's verdict.
    for af, _ in selected:
        for ext in (".cmp", ".mis"):
            c = os.path.join(rundir, os.path.basename(af) + ext)
            if os.path.exists(c):
                os.unlink(c)

    # Fixed name, not tempfile: specinvoke derives its own stdout file from the
    # instruction file's basename, so a random tmpXXXX.cmd leaves a tmpXXXX.out behind
    # in the run dir on every call. A known name can be cleaned up deterministically.
    # Episodes run sequentially, so there is no collision to guard against.
    stem = ".spec_verify"
    tmp = os.path.join(rundir, stem + ".cmd")
    with open(tmp, "w") as tf:
        tf.write("\n".join(pro) + "\n" + "\n".join(l for _, l in selected) + "\n")
    try:
        # specdiff does `unshift @INC, "$ENV{SPEC}/bin/common", "$ENV{SPEC}/bin/harness"`.
        # specinvoke's own `-E` prologue does NOT reach it, so without SPEC set here
        # specdiff dies on `Can't locate compare.pl` before comparing anything — leaving
        # an EMPTY .cmp that an "empty means clean" rule would score as a pass. SPEC's
        # own SPECPERLLIB omits bin/harness, so add it.
        env = dict(os.environ)
        env["SPEC"] = spec
        env["SPECPERLLIB"] = os.pathsep.join([
            os.path.join(spec, "bin", "lib"),
            os.path.join(spec, "bin"),
            os.path.join(spec, "bin", "harness"),
        ])
        # -k: run every comparison even after one fails, so we report all of them.
        r = subprocess.run(
            [os.path.join(spec, "bin", "specinvoke"), "-k", "-E", "-d", rundir, "-f", tmp],
            capture_output=True, text=True, env=env,
        )

        # Ground truth, established against planted good/corrupt outputs:
        #   pass -> rc 0, .cmp == "specdiff run completed", no .mis
        #   fail -> rc 1, .cmp has miscompare lines BEFORE that marker, .mis written
        # An absent or empty .cmp means specdiff never ran: that is an ERROR, never a pass.
        MARKER = "specdiff run completed"
        checked, failed, errors = [], [], []
        for af, _ in selected:
            base = os.path.basename(af)
            cmp_path = os.path.join(rundir, base + ".cmp")
            mis_path = os.path.join(rundir, base + ".mis")
            if not os.path.exists(cmp_path):
                errors.append({"file": af, "why": "no .cmp produced — specdiff did not run"})
                continue
            with open(cmp_path, errors="replace") as f:
                body = f.read().strip()
            if not body:
                errors.append({"file": af, "why": "empty .cmp — specdiff produced no verdict"})
                continue
            checked.append(af)
            residue = body.replace(MARKER, "").strip()
            if residue or os.path.exists(mis_path):
                failed.append({"file": af, "diff": (residue or "see .mis")[:800]})

        status = "error" if errors else ("fail" if failed else "pass")
        if status == "pass" and r.returncode != 0:
            status = "error"
            errors.append({"file": "*", "why": f"specinvoke rc={r.returncode} with clean reports"})
        print(json.dumps({
            "status": status,
            "cmd_index": cmd_index,
            "n_checked": len(checked), "checked": checked[:20],
            "failed": failed[:5], "errors": errors[:5],
            "not_produced": len(absent), "stale_ignored": len(stale),
            "specinvoke_rc": r.returncode,
            "stderr": r.stderr.strip()[:400] if status == "error" else "",
        }))
    finally:
        for junk in (tmp, os.path.join(rundir, stem + ".out"),
                     os.path.join(rundir, stem + ".err")):
            if os.path.exists(junk):
                os.unlink(junk)
    return 0


if __name__ == "__main__":
    sys.exit(main())
