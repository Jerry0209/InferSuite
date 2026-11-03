#!/usr/bin/env bash
# run_v2.sh — gate V2 of the front-end footprint contract: exact Intel PT vs the LBR estimate
# for ONE short deterministic command, both captured on house core 1.
#
#   run_v2.sh <name> <outdir> [--cwd DIR] [--env-file FILE] -- <cmd...>
#
#  1. PT capture (user only):  perf record -e intel_pt/cyc=0,mtc=0,tsc=0,noretcomp=0/u -m ,256M
#     decoded with `perf script --itrace=be` STREAMED into `lbr_footprint --mode pt` (the text
#     is ~80 B per branch, i.e. tens of GB for a 1 s program, so it is never stored);
#     pt.data is deleted as soon as the PT summary and tables exist (disk is scarce).
#  2. LBR capture with the contract settings (-e br_inst_retired.near_taken:pp -c 20011
#     -j any,save_type), analyzed in lbr mode; lbr.data is deleted after (KEEP_LBR=1 keeps it).
#  3. compare_v2.py on the two table sets -> <outdir>/compare.json + one summary line.
# The two captures are separate executions; canonical keys are ASLR-independent, and the
# command must be deterministic (e.g. PYTHONHASHSEED=0). Its stdout is hashed in both runs
# as a cheap same-work check.
#
# Expect ~1 M branches/s of PT decode: a 1 s program (~300 M taken branches) takes ~5 min.
# Refuses to start if any perf process is already running (LBR/PT are per-core hardware;
# a concurrent capture corrupts both). --env-file is sourced with `set -a` before the command
# (SPEC's specinvoke environment); commands with redirections go through `bash -c '...'`.
#
# Env: PERF (default: newest /usr/lib/linux-tools-6.8*/perf), V2_CORE (1), CPUS_HOUSE
# (0-3,12-15: decode + analysis), PT_EVENT (see below), PT_AUX (256M; one AUX buffer per online
# CPU, so this much locked memory times the CPU count), KEEP_LBR (0), ANALYZER_SHA (default: git HEAD
# if lbr_footprint.cpp is committed and clean, else "uncommitted"), SKIP_CAPTURE=1 (re-analyze
# existing <outdir>/{pt/pt.data,lbr/lbr.data}; used to test this script without capturing).
set -u -o pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
KIT=$(dirname "$HERE")
ANALYZER="$KIT/lbr_footprint"
PERF="${PERF:-$(ls -d /usr/lib/linux-tools-6.8*/perf 2>/dev/null | tail -1)}"
CORE="${V2_CORE:-1}"
HOUSE="${CPUS_HOUSE:-0-3,12-15}"
PT_AUX="${PT_AUX:-256M}"
LBR_EVENT="${LBR_EVENT:-br_inst_retired.near_taken:pp}"   # contract v1.1 (PEBS-captured LBR)
# tsc=0 (the contract's setting) makes perf decode "timelessly": no context-switch sideband,
# so it is only valid when ONE process runs the traced code. Commands that fork (g++ -> cc1plus
# -> as; `bash -c 'cmd > f'` forks too, `bash -c 'exec cmd > f'` does not) need TSC on:
# PT_EVENT='intel_pt/cyc=0,mtc=0,noretcomp=0/u'. compare_v2.py flags a wrong choice.
PT_EVENT="${PT_EVENT:-intel_pt/cyc=0,mtc=0,tsc=0,noretcomp=0/u}"
usage(){ echo "usage: $0 <name> <outdir> [--cwd DIR] [--env-file FILE] -- <cmd...>" >&2; exit 2; }
[ $# -ge 3 ] || usage
NAME=$1; OUT=$2; shift 2
CWD=$PWD; ENVF=
while [ $# -gt 0 ]; do
  case $1 in
    --cwd) CWD=$2; shift 2 ;;
    --env-file) ENVF=$(cd "$(dirname "$2")" && pwd)/$(basename "$2"); shift 2 ;;
    --) shift; break ;;
    *) usage ;;
  esac
done
[ $# -gt 0 ] || usage
[ -x "$PERF" ] || { echo "ABORT: perf not found ($PERF)" >&2; exit 2; }
if pgrep -x perf >/dev/null; then
  echo "ABORT: a perf process is already running; V2 must not capture concurrently:" >&2
  pgrep -a -x perf >&2; exit 3
fi
mkdir -p "$OUT/pt" "$OUT/lbr" || exit 2
OUT=$(cd "$OUT" && pwd)
LOG="$OUT/run_v2.log"
log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG" >&2; }
[ -x "$ANALYZER" ] || taskset -c "$HOUSE" make -s -C "$KIT" lbr_footprint || { log "ABORT: analyzer build failed"; exit 2; }
if [ -z "${ANALYZER_SHA:-}" ]; then
  if git -C "$KIT" ls-files --error-unmatch lbr_footprint.cpp >/dev/null 2>&1 &&
     git -C "$KIT" diff --quiet HEAD -- lbr_footprint.cpp 2>/dev/null; then
    ANALYZER_SHA=$(git -C "$KIT" log -1 --format=%H -- lbr_footprint.cpp)
  else
    ANALYZER_SHA=uncommitted
  fi
fi
log "V2 $NAME: cwd=$CWD env=${ENVF:-none} cmd=$* perf=$PERF analyzer_sha=$ANALYZER_SHA"

# Runs perf record (pinned with the workload to $CORE) on the command, in $CWD with $ENVF.
capture(){ # $1 = role dir, rest = perf record options
  local role=$1; shift
  local t0=$EPOCHREALTIME
  ( cd "$CWD" || exit 125
    if [ -n "$ENVF" ]; then set -a; . "$ENVF"; set +a; fi
    exec taskset -c "$CORE" "$PERF" record "$@" -- "${CMD[@]}"
  ) > "$OUT/$role/cmd.stdout" 2> "$OUT/$role/record.stderr"
  local rc=$?
  echo "$rc $(awk -v a="$t0" -v b="$EPOCHREALTIME" 'BEGIN{printf "%.3f", b-a}')"
}
CMD=("$@")
META=(--meta "v2_name=$NAME" --meta "pt_event=$PT_EVENT" --meta "cmd=$*" --meta "cwd=$CWD" --meta "env_file=${ENVF:-}"
      --meta "perf_version=$("$PERF" version 2>/dev/null)")

# ---- 1. PT (exact reference) ----
if [ "${SKIP_CAPTURE:-0}" != 1 ]; then
  log "PT capture on core $CORE ($PT_EVENT, AUX $PT_AUX) ..."
  read -r PT_RC PT_WALL < <(capture pt -e "$PT_EVENT" -m ",$PT_AUX" -o "$OUT/pt/pt.data")
  log "PT capture: rc=$PT_RC wall=${PT_WALL}s size=$(du -h "$OUT/pt/pt.data" 2>/dev/null | cut -f1)"
else
  PT_RC=skipped; PT_WALL=0
fi
PT_WARN=$(grep -iE 'lost|gap|collision|error|truncat' "$OUT/pt/record.stderr" 2>/dev/null | grep -v '^\[ perf record' | head -5)
[ -n "$PT_WARN" ] && log "PT record warnings: $PT_WARN"
[ -s "$OUT/pt/pt.data" ] || { log "ABORT: no pt.data"; exit 1; }
log "PT decode -> analyzer (streamed; ~1 M branches/s) ..."
taskset -c "$HOUSE" "$PERF" script -i "$OUT/pt/pt.data" --itrace=be -F pid,tid,ip,addr,flags \
    --show-mmap-events --show-task-events 2> "$OUT/pt/script.stderr" \
  | taskset -c "$HOUSE" "$ANALYZER" --mode pt --analyzer-sha "$ANALYZER_SHA" "${META[@]}" --meta role=pt_reference \
      --summary "$OUT/pt/summary.json" --edges "$OUT/pt/edges.tsv" --objects "$OUT/pt/objects.tsv" \
      --lines "$OUT/pt/lines.tsv" 2> "$OUT/pt/analyzer.log"
PS=("${PIPESTATUS[@]}")
log "PT analysis: perf script rc=${PS[0]} analyzer rc=${PS[1]}: $(tail -1 "$OUT/pt/analyzer.log")"
grep -iE 'error|lost|warning' "$OUT/pt/script.stderr" | head -5 | while read -r l; do log "  perf script: $l"; done
if [ "${PS[1]}" = 0 ] && [ -s "$OUT/pt/summary.json" ] && [ -s "$OUT/pt/edges.tsv" ]; then
  rm -f "$OUT/pt/pt.data" && log "pt.data deleted"
else
  log "KEEPING $OUT/pt/pt.data ($(du -h "$OUT/pt/pt.data" | cut -f1)) for inspection: PT analysis failed"
fi

# ---- 2. LBR (the contract's estimate) ----
if [ "${SKIP_CAPTURE:-0}" != 1 ]; then
  if pgrep -x perf >/dev/null; then log "ABORT: a perf process appeared before the LBR capture"; exit 3; fi
  log "LBR capture on core $CORE ..."
  read -r LBR_RC LBR_WALL < <(capture lbr -e "$LBR_EVENT" -c 20011 -j any,save_type -o "$OUT/lbr/lbr.data")
  log "LBR capture: rc=$LBR_RC wall=${LBR_WALL}s size=$(du -h "$OUT/lbr/lbr.data" 2>/dev/null | cut -f1)"
else
  LBR_RC=skipped; LBR_WALL=0
fi
[ -s "$OUT/lbr/lbr.data" ] || { log "ABORT: no lbr.data"; exit 1; }
taskset -c "$HOUSE" "$PERF" report -i "$OUT/lbr/lbr.data" --stats > "$OUT/lbr/report_stats.txt" 2>&1
taskset -c "$HOUSE" "$PERF" script -i "$OUT/lbr/lbr.data" -F pid,brstack --show-mmap-events --show-task-events \
    --show-lost-events 2> "$OUT/lbr/script.stderr" \
  | taskset -c "$HOUSE" "$ANALYZER" --mode lbr --analyzer-sha "$ANALYZER_SHA" "${META[@]}" --meta role=lbr_estimate \
      --meta period=20011 --summary "$OUT/lbr/summary.json" --edges "$OUT/lbr/edges.tsv" \
      --objects "$OUT/lbr/objects.tsv" --lines "$OUT/lbr/lines.tsv" 2> "$OUT/lbr/analyzer.log"
LS=("${PIPESTATUS[@]}")
log "LBR analysis: perf script rc=${LS[0]} analyzer rc=${LS[1]}: $(tail -1 "$OUT/lbr/analyzer.log")"
log "LBR record stats: $(grep -E 'SAMPLE|LOST|THROTTLE' "$OUT/lbr/report_stats.txt" | tr -s ' ' | tr '\n' ';')"
if [ "${LS[1]}" = 0 ] && [ -s "$OUT/lbr/summary.json" ] && [ "${KEEP_LBR:-0}" != 1 ]; then
  rm -f "$OUT/lbr/lbr.data" && log "lbr.data deleted"
fi

# ---- 3. compare ----
SAME_OUT=no
cmp -s "$OUT/pt/cmd.stdout" "$OUT/lbr/cmd.stdout" && SAME_OUT=yes
log "command rc: PT $PT_RC, LBR $LBR_RC; identical stdout in both runs: $SAME_OUT"
python3 "$HERE/compare_v2.py" --pt "$OUT/pt" --lbr "$OUT/lbr" --name "$NAME" --json "$OUT/compare.json" | tee -a "$LOG"
CRC=${PIPESTATUS[0]}
NAME="$NAME" OUT="$OUT" PT_RC="$PT_RC" LBR_RC="$LBR_RC" PT_WALL="$PT_WALL" LBR_WALL="$LBR_WALL" SAME_OUT="$SAME_OUT" \
PT_WARN="$PT_WARN" CWD="$CWD" ENVF="${ENVF:-}" CMDSTR="$*" python3 - <<'PY'
import json, os
E = os.environ
p = f"{E['OUT']}/compare.json"
c = json.load(open(p)) if os.path.exists(p) else {}
c["run"] = {"name": E["NAME"], "cmd": E["CMDSTR"], "cwd": E["CWD"], "env_file": E["ENVF"],
            "pt_cmd_rc": E["PT_RC"], "lbr_cmd_rc": E["LBR_RC"], "pt_wall_s": E["PT_WALL"], "lbr_wall_s": E["LBR_WALL"],
            "identical_stdout": E["SAME_OUT"] == "yes", "pt_record_warnings": E["PT_WARN"]}
json.dump(c, open(p, "w"), indent=1)
PY
# keep the tables, compressed (they are what V2 numbers are recomputed from)
for f in "$OUT"/pt/*.tsv "$OUT"/lbr/*.tsv; do [ -f "$f" ] && zstd -q -f --rm -T2 "$f"; done
log "done: $OUT/compare.json"
exit "$CRC"
