#!/usr/bin/env bash
# llc_dram_crosscheck.sh — independent check of the campaign's LLC_MPKI and DRAM_read_GBs.
#
# Both metrics are narrower than their names:
#   LLC_MPKI      = mem_load_retired.l3_miss / inst. RETIRED DEMAND LOADS only: loads that
#                   find their line already in flight (fill-buffer hits), HW prefetches,
#                   RFOs and code reads are not in it.
#   DRAM_read_GBs = offcore_requests.data_rd x 64 B / s. L2 -> uncore data reads: it
#                   INCLUDES L3 hits and EXCLUDES RFOs and writebacks.
# This re-runs selected benchmarks under the SAME fence, shield and shuffled rotation
# (the functions are sourced from run_spec_campaign.sh, not copied), with the original
# cache/dram_bw groups plus three wider-definition groups, while the memory controllers'
# CAS counters record actual DRAM traffic for the whole session.
#
#   ./llc_dram_crosscheck.sh [bench...]    default: lbm fotonik3d roms marian omnetpp nest
#   ./llc_dram_crosscheck.sh --control-only  calibration + stack control, no benchmarks
#   ./llc_dram_crosscheck.sh 767.nest_r@0 767.nest_r@1 767.nest_r@2
#                                          "<bench>@<k>" runs ref command line k and keeps
#                                          the episode as $DATA_ROOT/<bench>@<k>
#
# The L3 and the memory controllers are shared by EVERY core, so the whole machine must
# be quiet, not only the measured partition. quiet_gate.py blocks until no other user's
# process is busy, a witness logs foreign CPU every 2 s, and an episode that overlapped
# foreign work is set aside and re-run (up to 3 tries). Output: $DATA_ROOT (default
# data_llc_xcheck/); analyse with xcheck_report.py.
set -o pipefail
XKIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export DATA_ROOT="${DATA_ROOT:-$(cd "$XKIT/.." && pwd)/data_llc_xcheck}"
# The runner's own dispatch runs on source; "help" makes it print usage, discarded here.
# shellcheck disable=SC1091
source "$XKIT/run_spec_campaign.sh" help >/dev/null
LOGF="$INFRA/logs/llc_dram_crosscheck.log"

# restore_isolation() puts back each slice's systemd AllowedCPUs snapshot, and turns an
# EMPTY snapshot into "all online CPUs". On this box the house split (0-3,12-15) is
# written straight to cgroupfs by the agentic boot services, so systemd reports
# AllowedCPUs empty and the restore WIDENS system/user/init to 0-15 (observed
# 2026-10-26). Record the EFFECTIVE cpusets before the shield and put back any the
# campaign's restore changed.
eval "campaign_restore_isolation() $(declare -f restore_isolation | tail -n +2)"
restore_isolation(){
  campaign_restore_isolation
  local sl want now
  [ -f "$SESS/pre_cpuset.tsv" ] || return 0
  while read -r sl want; do
    now=$(cat "/sys/fs/cgroup/$sl/cpuset.cpus.effective" 2>/dev/null)
    if [ -n "$want" ] && [ "$now" != "$want" ]; then
      sudo systemctl set-property --runtime "$sl" AllowedCPUs="$want"
      log "ISOLATION: $sl effective cpuset $now -> $want (its pre-shield value)"
    fi
  done < "$SESS/pre_cpuset.tsv"
}

# ---- extra groups: each <= 4 GP and <= 2 OCR events (two OFFCORE_RSP MSRs per core) ----
GRP[x_llc]="cycles,instructions,longest_lat_cache.miss,longest_lat_cache.reference,mem_load_retired.fb_hit,mem_load_retired.l3_miss"
GRP[x_ocr1]="cycles,instructions,ocr.reads_to_core.l3_miss,ocr.demand_rfo.l3_miss,offcore_requests.data_rd,l2_lines_out.non_silent"
GRP[x_ocr2]="cycles,instructions,ocr.demand_data_rd.l3_miss,ocr.hwpf_l3.l3_miss,longest_lat_cache.miss,mem_load_retired.l3_miss"
GORDER="cache dram_bw x_llc x_ocr1 x_ocr2"
IMC_EVENTS="unc_m_cas_count.rd,unc_m_cas_count.wr"

if [ "${1:-}" = --control-only ]; then
  BENCHES=()
else
  BENCHES=("$@")
  [ ${#BENCHES[@]} -gt 0 ] || BENCHES=(782.lbm_r 749.fotonik3d_r 765.roms_r 772.marian_r 710.omnetpp_r 767.nest_r)
fi
# One session directory per invocation: imc.csv is rewritten by every run, and the report
# stitches all sessions together by wall-clock time.
SESS="$DATA_ROOT/_session"; n=2
while [ -e "$SESS" ]; do SESS="$DATA_ROOT/_session.$n"; n=$((n+1)); done
mkdir -p "$SESS"
GATE=(python3 "$XKIT/quiet_gate.py")
IMC_PID=""; WIT_PID=""

xc_cleanup(){
  [ -n "$WIT_PID" ] && kill "$WIT_PID" 2>/dev/null
  [ -n "$IMC_PID" ] && { kill -INT "$IMC_PID" 2>/dev/null; wait "$IMC_PID" 2>/dev/null; }
  sudo systemctl stop 'spec-xcal-*.scope' 2>/dev/null
}
trap 'rc=$?; xc_cleanup; (exit $rc); cleanup' EXIT

quiet_wait(){ # $1 seconds of continuous quiet required
  log "QUIET-GATE: waiting until no other user's process is busy for $1 s"
  "${GATE[@]}" wait --hold "$1" --poll 10 --mine $$ >> "$SESS/quiet.log" 2>&1
  log "QUIET-GATE: $(tail -1 "$SESS/quiet.log")"
}

mark(){ printf '%s\t%s\t%s\n' "$1" "$2" "$EPOCHREALTIME" >> "$SESS/marks.tsv"; }

# Known-traffic kernel inside the fence. $1 read|write, $2 seconds, $3 group counted
# continuously at 250 ms, or "rotate" for one 1.5 s window of every GORDER group (the
# zero-multiplexing check for the new groups).
calib(){
  local mode="$1" secs="$2" what="$3" tag="calib_${1}_${3}"
  local unit="spec-xcal-$mode" cg="$MSLICE/spec-xcal-$mode.scope" out="$SESS/$tag"
  mkdir -p "$out"
  sudo systemd-run --collect --scope --slice="$MSLICE" --unit="$unit" \
       -p AllowedCPUs="$CPUS_MEASURED" -- \
       runuser -u "$USER" -- "$STATE/xcheck_calib" "$mode" "$secs" > "$out/kernel.log" 2>&1 &
  local lp=$! i pp=""
  for i in $(seq 1 40); do [ -d "/sys/fs/cgroup/$cg" ] && break; sleep 0.25; done
  mark "$tag" start
  if [ "$what" = rotate ]; then
    sleep 2                                   # past the first-touch pass
    local g w=0
    for g in $GORDER; do
      taskset -c "$CPUS_HOUSE" "$PERF" stat -a -e "${GRP[$g]}" --for-each-cgroup="$cg" \
        -- sleep 1.5 2> "$out/group_${g}_w$(printf '%03d' $w).txt"
      w=$((w+1))
    done
  else
    echo "$EPOCHREALTIME" > "$out/core.t0"
    taskset -c "$CPUS_HOUSE" "$PERF" stat -I 250 -x, -a -e "${GRP[$what]}" \
      --for-each-cgroup="$cg" -o "$out/core.csv" -- sleep 600 >/dev/null 2>&1 &
    pp=$!
  fi
  wait "$lp"
  [ -n "$pp" ] && { kill -INT "$pp" 2>/dev/null; wait "$pp" 2>/dev/null; }
  mark "$tag" end
  log "  calib $tag: $(cat "$out/kernel.log" | tr -d '\n')"
}

# Did foreign work overlap [t0, t1]? Judged from the witness rows, and banked into the
# episode's metadata.json when one is given. t0 is the START of the idle baseline, because
# a polluted baseline corrupts the DRAM subtraction as surely as a polluted episode.
contaminated(){ # $1 t0, $2 t1, [$3 metadata.json] -> exit 0 contaminated, 1 clean
  python3 - "$1" "$2" "$SESS/witness.tsv" "${3:-}" <<'PY'
import json, re, sys
t0, t1, wit, meta = float(sys.argv[1]), float(sys.argv[2]), sys.argv[3], sys.argv[4]
rows = []
for ln in open(wit):
    p = ln.rstrip("\n").split("\t")
    if len(p) == 3 and t0 <= float(p[0]) <= t1 + 2:
        top = max([float(x) for x in re.findall(r"=(\d+(?:\.\d+)?)%", p[2])] or [0])
        rows.append((float(p[1]), top, p[2]))
n = len(rows)
flag = [r for r in rows if r[1] > 10.0]
mean_tot = sum(r[0] for r in rows) / n if n else float("nan")
worst = max(rows, key=lambda r: r[0])[2] if rows else "-"
s = {"witness_rows": n, "rows_with_foreign_task": len(flag),
     "mean_foreign_cpu_pct": round(mean_tot, 1), "worst_row": worst}
if meta:
    m = json.load(open(meta))
    m["foreign_witness"] = s
    json.dump(m, open(meta, "w"), indent=1)
bad = n == 0 or len(flag) > 0.05 * n or mean_tot > 25
print(("CONTAMINATED " if bad else "clean ") + json.dumps(s))
sys.exit(0 if bad else 1)
PY
}

# Idle baseline + the three known-traffic kernels, redone if foreign work overlapped them.
calibrate(){
  local try t0 v crc d
  for try in 1 2 3; do
    quiet_wait 60
    mark calib idle_start; t0=$EPOCHREALTIME; sleep 15; mark calib idle_end
    calib read 10 x_ocr1
    calib write 10 x_ocr1
    calib read 12 rotate
    v="$(contaminated "$t0" "$EPOCHREALTIME")"; crc=$?
    log "  calibration witness: $v"
    [ $crc = 1 ] && return 0
    for d in calib_read_x_ocr1 calib_write_x_ocr1 calib_read_rotate; do
      mv "$SESS/$d" "$SESS/$d.contaminated.$try"
    done
    log "  calibration set aside (foreign work overlapped on attempt $try of 3)"
  done
  return 1
}

# The capture stack itself runs on the house cores and moves memory: a perf relaunch every
# 120 ms, 100 Hz pollers, a 99 Hz call-graph record. The memory controllers see that traffic
# and the idle baseline (taken with no stack running) does not, so measure it once on an
# EMPTY fence (a scope that only sleeps) with exactly the episode's capture stack.
stack_control(){ # $1 seconds
  local OUT="$SESS/stack_control" UNIT="spec-xstack" CG="$MSLICE/spec-xstack.scope"
  local try t0 v crc lp i
  for try in 1 2 3; do
    quiet_wait 60
    rm -rf "$OUT"; mkdir -p "$OUT"
    mark stack idle_start; t0=$EPOCHREALTIME; sleep 15; mark stack idle_end
    sudo systemd-run --collect --scope --slice="$MSLICE" --unit="$UNIT" \
         -p AllowedCPUs="$CPUS_MEASURED" -- runuser -u "$USER" -- sleep "$1" >/dev/null 2>&1 &
    lp=$!
    for i in $(seq 1 40); do [ -d "/sys/fs/cgroup/$CG" ] && break; sleep 0.25; done
    mark stack start
    start_pollers "$OUT" "$CG"; start_records "$OUT" "$CG"; start_tma_cont "$OUT" "$CG"
    cycle_stats "$OUT" "$CG" "systemctl is-active --quiet $UNIT.scope" "$(( $1 + 30 ))"
    stop_tma_cont; stop_records; stop_pollers "$OUT"
    wait "$lp"
    mark stack end
    v="$(contaminated "$t0" "$EPOCHREALTIME")"; crc=$?
    log "  stack control witness: $v"
    [ $crc = 1 ] && return 0
    mv "$OUT" "$OUT.contaminated.$try"
  done
  return 1
}

# ---------------- run ----------------------------------------------------------------
log "================ LLC/DRAM cross-check: ${BENCHES[*]} ================"
log "groups: $GORDER   imc: $IMC_EVENTS   data: $DATA_ROOT"
for b in "${BENCHES[@]}"; do setup_bench "${b%@*}" || exit 1; done
[ -x "$STATE/xcheck_calib" ] || gcc -O3 -march=native -fno-tree-loop-distribute-patterns \
  -o "$STATE/xcheck_calib" "$XKIT/xcheck_calib.c" || exit 1

quiet_wait 180
for sl in system.slice user.slice init.scope "$MSLICE"; do
  printf '%s\t%s\n' "$sl" "$(cat "/sys/fs/cgroup/$sl/cpuset.cpus.effective")"
done > "$SESS/pre_cpuset.tsv"
apply_isolation || { log "ABORT: isolation could not be applied"; exit 1; }
RAN_WORK=1

# Memory-controller traffic for the WHOLE session (uncore: system-wide, not attributable
# to a cgroup). Started after apply_isolation, whose own-perf sweep would kill it. The
# idle gaps marked in marks.tsv give the background to subtract.
echo "$EPOCHREALTIME" > "$SESS/imc.t0"
taskset -c "$CPUS_HOUSE" "$PERF" stat -a -I 500 -x, -e "$IMC_EVENTS" -o "$SESS/imc.csv" \
  -- sleep 100000 >/dev/null 2>&1 &
IMC_PID=$!
"${GATE[@]}" witness --poll 2 --mine $$ --out "$SESS/witness.tsv" &
WIT_PID=$!

calibrate || { log "ABORT: no clean calibration in 3 attempts — machine too busy"; exit 1; }
stack_control 60 || log "WARN: no clean stack control in 3 attempts; DRAM rates are not stack-corrected"

# "<bench>@<k>": run_episode always writes $DATA_ROOT/<bench> and takes its index from
# cmd_index.tsv, else SPEC_CMD_INDEX. Set the latter per item, refuse when a cmd_index.tsv
# row would override it, and move the episode to $DATA_ROOT/<bench>@<k> so the next input
# of the same benchmark starts clean. Marks are tagged with the item, matching the dir.
IDX_DEFAULT="$SPEC_CMD_INDEX"
for item in "${BENCHES[@]}"; do
  b="${item%@*}"; idx=""; [ "$item" != "$b" ] && idx="${item#*@}"
  SPEC_CMD_INDEX="${idx:-$IDX_DEFAULT}"
  if [ -n "$idx" ] && [ "$(cmd_index_for "$b")" != "$idx" ]; then
    log "  $item: SKIP, cmd_index.tsv pins $b to index $(cmd_index_for "$b")"; continue
  fi
  if [ -n "$idx" ] && [ -f "$DATA_ROOT/$item/DONE" ]; then log "skip $item (DONE)"; continue; fi
  for try in 1 2 3; do
    quiet_wait 60
    mark "$item" idle_start; t0=$EPOCHREALTIME; sleep 15; mark "$item" idle_end
    run_episode "$b"
    mark "$item" episode_end
    [ -f "$DATA_ROOT/$b/metadata.json" ] || { log "  $item: no metadata.json, episode failed before capture"; break; }
    v="$(contaminated "$t0" "$EPOCHREALTIME" "$DATA_ROOT/$b/metadata.json")"; crc=$?
    log "  witness: $v"
    if [ $crc = 0 ]; then
      rm -f "$DATA_ROOT/$b/DONE"; mv "$DATA_ROOT/$b" "$DATA_ROOT/$item.contaminated.$try"
      log "  $item set aside (foreign work overlapped on attempt $try of 3)"
      continue
    fi
    [ -n "$idx" ] && mv "$DATA_ROOT/$b" "$DATA_ROOT/$item"
    break
  done
done
SPEC_CMD_INDEX="$IDX_DEFAULT"
mark session idle2_start; sleep 15; mark session idle2_end
log "================ LLC/DRAM cross-check done ================"
