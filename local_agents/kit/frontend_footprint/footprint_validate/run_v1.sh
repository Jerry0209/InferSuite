#!/usr/bin/env bash
# run_v1.sh — gate V1 (synthetic truth) of the front-end footprint contract, one command:
#
#   run_v1.sh <outdir> [iterations]
#
# Builds the analyzer and v1_synth if needed, captures v1_synth (~4 s) on house core 1 with the
# contract's LBR settings, decodes it straight into the analyzer and runs check_v1.py, which
# derives the expected values from the design + the binary and prints PASS/FAIL per check.
# v1.data is deleted after a successful analysis (KEEP_DATA=1 keeps it).
# Refuses to start if any perf process is already running (LBR is per-core hardware).
# Env: PERF, V1_CORE (1), CPUS_HOUSE (0-3,12-15), ANALYZER_SHA (as in run_v2.sh),
# LBR_EVENT (br_inst_retired.near_taken:pp; the bare event reproduces the contract-v1 skid bias).
set -u -o pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
KIT=$(dirname "$HERE")
ANALYZER="$KIT/lbr_footprint"
PERF="${PERF:-$(ls -d /usr/lib/linux-tools-6.8*/perf 2>/dev/null | tail -1)}"
CORE="${V1_CORE:-1}"
HOUSE="${CPUS_HOUSE:-0-3,12-15}"
# Contract v1.1: PEBS (:pp) so the LBR snapshot is taken at the overflowing branch, not at
# the skidded PMI (without it V1 read the weighted averages 1.8-3.7 % low).
LBR_EVENT="${LBR_EVENT:-br_inst_retired.near_taken:pp}"
[ $# -ge 1 ] || { echo "usage: $0 <outdir> [iterations]" >&2; exit 2; }
OUT=$1; ITERS=${2:-}
[ -x "$PERF" ] || { echo "ABORT: perf not found ($PERF)" >&2; exit 2; }
if pgrep -x perf >/dev/null; then
  echo "ABORT: a perf process is already running; V1 must not capture concurrently:" >&2
  pgrep -a -x perf >&2; exit 3
fi
mkdir -p "$OUT" || exit 2
OUT=$(cd "$OUT" && pwd)
LOG="$OUT/run_v1.log"
log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG" >&2; }
taskset -c "$HOUSE" make -s -C "$KIT" lbr_footprint v1 || { log "ABORT: build failed"; exit 2; }
if [ -z "${ANALYZER_SHA:-}" ]; then
  if git -C "$KIT" ls-files --error-unmatch lbr_footprint.cpp >/dev/null 2>&1 &&
     git -C "$KIT" diff --quiet HEAD -- lbr_footprint.cpp 2>/dev/null; then
    ANALYZER_SHA=$(git -C "$KIT" log -1 --format=%H -- lbr_footprint.cpp)
  else
    ANALYZER_SHA=uncommitted
  fi
fi
BIN="$HERE/v1_synth"
python3 "$HERE/check_v1.py" --binary "$BIN" --expected-only | tee -a "$LOG"
log "capture: $BIN ${ITERS:-(default iterations)} on core $CORE"
t0=$EPOCHREALTIME
taskset -c "$CORE" "$PERF" record -e "$LBR_EVENT" -c 20011 -j any,save_type \
    -o "$OUT/v1.data" -- "$BIN" $ITERS > "$OUT/v1_synth.stdout" 2> "$OUT/record.stderr"
RC=$?
log "capture rc=$RC wall=$(awk -v a="$t0" -v b="$EPOCHREALTIME" 'BEGIN{printf "%.2f", b-a}') s: $(cat "$OUT/v1_synth.stdout")"
[ -s "$OUT/v1.data" ] || { log "ABORT: no v1.data"; exit 1; }
taskset -c "$HOUSE" "$PERF" report -i "$OUT/v1.data" --stats > "$OUT/report_stats.txt" 2>&1
log "record stats: $(grep -E 'SAMPLE|LOST|THROTTLE' "$OUT/report_stats.txt" | tr -s ' ' | tr '\n' ';')"
taskset -c "$HOUSE" "$PERF" script -i "$OUT/v1.data" -F pid,brstack --show-mmap-events --show-task-events \
    --show-lost-events 2> "$OUT/script.stderr" \
  | taskset -c "$HOUSE" "$ANALYZER" --mode lbr --analyzer-sha "$ANALYZER_SHA" --meta gate=V1 --meta period=20011 \
      --meta "perf_version=$("$PERF" version 2>/dev/null)" --summary "$OUT/summary.json" --edges "$OUT/edges.tsv" \
      --objects "$OUT/objects.tsv" --lines "$OUT/lines.tsv" 2> "$OUT/analyzer.log"
PS=("${PIPESTATUS[@]}")
log "analysis: perf script rc=${PS[0]} analyzer rc=${PS[1]}: $(tail -1 "$OUT/analyzer.log")"
[ "${PS[1]}" = 0 ] || { log "ABORT: analyzer failed (v1.data kept)"; exit 1; }
python3 "$HERE/check_v1.py" --binary "$BIN" --tables "$OUT" --json "$OUT/check_v1.json" | tee -a "$LOG"
CRC=${PIPESTATUS[0]}
[ "${KEEP_DATA:-0}" = 1 ] || { rm -f "$OUT/v1.data" && log "v1.data deleted"; }
exit "$CRC"
