#!/usr/bin/env bash
# add_bench_flags.sh <benchmark> <cfg-line> [<cfg-line> ...]
#
# Race-free way for the per-benchmark build agents to add config settings while
# other agents' runcpu processes are reading the same file.
#
#   - serialised by flock, so two agents never interleave edits
#   - the new config is written to a temp file and os.replace()d into place, so a
#     concurrent reader always sees a COMPLETE file (old or new, never partial)
#   - each benchmark owns exactly one managed block, re-writing it on repeat
#     calls, so retries don't stack duplicate sections
#
# The authoritative config is $INFRA/config/$CFG_NAME.cfg; it is edited there and
# then copied to $SPEC/config/. Never edit $SPEC/config directly.
#
# Example:
#   scripts/add_bench_flags.sh 737.gmsh_r 'PORTABILITY = -fno-fast-math -fpermissive'
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$HERE/spec_env.sh"

B="${1:?usage: add_bench_flags.sh <benchmark> <cfg-line> [...]}"; shift
[ $# -ge 1 ] || { echo "FATAL: no config lines given"; exit 2; }

SRC="$INFRA/config/$CFG_NAME.cfg"
DST="$SPEC_ROOT/config/$CFG_NAME.cfg"
mkdir -p "$INFRA/.locks"

exec {lfd}>"$INFRA/.locks/config.lock"
flock "$lfd"

python3 - "$SRC" "$DST" "$B" "$@" <<'PY'
import os, sys, tempfile

src, dst, bench, *lines = sys.argv[1:]
begin = f"# >>> managed:{bench} >>>"
end   = f"# <<< managed:{bench} <<<"

text = open(src).read()

# drop any previous managed block for this benchmark (idempotent retries)
if begin in text:
    head, rest = text.split(begin, 1)
    _, tail = rest.split(end, 1)
    text = head + tail

block = [begin, f"{bench}:"]
block += [f"   {ln}" for ln in lines]
block += [end, ""]
text = text.rstrip("\n") + "\n\n" + "\n".join(block) + "\n"

for target in (src, dst):
    d = os.path.dirname(target)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".cfgtmp")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.replace(tmp, target)          # atomic for concurrent readers

print(f"managed block for {bench} now:")
for ln in block[:-1]:
    print("   " + ln)
PY

echo "OK: $SRC and $DST updated"
