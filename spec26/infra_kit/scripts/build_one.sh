#!/usr/bin/env bash
# build_one.sh <benchmark> — build ONE SPEC CPU 2026 benchmark, base tuning only.
#
# Concurrency: SPEC supports simultaneous runcpu builds (Docs/runcpu.txt:588 —
# each concurrent build gets its own numbered build dir). We still throttle,
# because 26 unthrottled builds x make -j would thrash a 24-thread box: a
# flock-based semaphore of BUILD_SLOTS slots, each build using
# make -j BUILD_NCPUS. Default 6 x 4 = 24 = logical CPUs.
#
# Builds run OUTSIDE the measurement fence and BEFORE any isolation is applied
# — the measured episode must contain the benchmark binary and nothing else.
#
# Usage:  scripts/build_one.sh 782.lbm_r
#         BUILD_NCPUS=8 BUILD_SLOTS=3 scripts/build_one.sh 735.gem5_r
#
# Exit 0 = binary exists afterwards. Anything else = build failed; the log path
# is printed on the last line either way.
set -o pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$HERE/spec_env.sh"

B="${1:?usage: build_one.sh <benchmark>}"
LOG="$INFRA/logs/build_${B}.log"
LOCKDIR="$INFRA/.buildslots"
mkdir -p "$LOCKDIR" "$INFRA/logs"

[ -d "$SPEC_ROOT/benchspec/CPU/$B" ] || { echo "FATAL: unknown benchmark $B"; exit 2; }

# ---- already built? (idempotent: agents may be retried) ----------------------
if bench_is_built "$B" && [ "${FORCE_REBUILD:-0}" != 1 ]; then
  echo "ALREADY-BUILT $B -> $(ls "$(bench_exe_dir "$B")"/*_base."$SPEC_LABEL"* 2>/dev/null | tr '\n' ' ')"
  echo "LOG=$LOG"
  exit 0
fi

# ---- concurrency slot --------------------------------------------------------
SLOT=""
acquire_slot() {
  local i fd waited=0
  while :; do
    for i in $(seq 1 "$BUILD_SLOTS"); do
      exec {fd}>"$LOCKDIR/slot.$i" || continue
      if flock -n "$fd"; then SLOT="$i"; return 0; fi
      exec {fd}>&-
    done
    sleep 5; waited=$((waited+5))
    [ $((waited % 300)) -eq 0 ] && echo "  ...$B waiting for a build slot (${waited}s)"
  done
}
acquire_slot
echo "[$(date +%H:%M:%S)] $B: slot $SLOT/$BUILD_SLOTS, make -j$BUILD_NCPUS"

# ---- build -------------------------------------------------------------------
spec_shell
{
  echo "=== build_one.sh $B  $(date -Is) ==="
  echo "=== config=$CFG_NAME label=$SPEC_LABEL build_ncpus=$BUILD_NCPUS slot=$SLOT ==="
  cd "$SPEC_ROOT" || exit 3
  runcpu --config="$CFG_NAME" \
         --action=build \
         --tune=base \
         --define build_ncpus="$BUILD_NCPUS" \
         "$B"
  echo "=== runcpu exit=$? $(date -Is) ==="
} > "$LOG" 2>&1
RC=$?

# ---- verify: the ONLY thing that counts is a binary on disk -------------------
# ignore_errors=1 lets runcpu exit 0 past a failed compile, so never trust $RC.
if bench_is_built "$B"; then
  echo "BUILD-OK $B  ($(ls "$(bench_exe_dir "$B")"/*_base."$SPEC_LABEL"* | wc -l) binary/binaries)"
  ls -l "$(bench_exe_dir "$B")"/*_base."$SPEC_LABEL"* 2>/dev/null | sed 's/^/    /'
  echo "LOG=$LOG"
  exit 0
fi

echo "BUILD-FAIL $B (runcpu rc=$RC, no base binary produced)"
echo "--- last 40 lines of $LOG ---"
tail -40 "$LOG"
# the real compiler error lives in the per-build make.out, not the runcpu log
MK="$(ls -t "$SPEC_ROOT/benchspec/CPU/$B/build/build_base_${SPEC_LABEL}"*/make.out 2>/dev/null | head -1)"
if [ -n "$MK" ]; then
  echo "--- first errors in $MK ---"
  grep -nE 'error:|Error [0-9]|undefined reference|No such file' "$MK" | head -25
  echo "MAKEOUT=$MK"
fi
echo "LOG=$LOG"
exit 1
