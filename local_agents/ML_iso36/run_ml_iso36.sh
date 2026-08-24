#!/usr/bin/env bash
# run_ml_iso36.sh — profile the 36 count-view picks under the SPEC configuration:
# 9 dedicated-group replay passes per task (shared 8 + fe_miss), 100 ms windows,
# measured cores 4-11 SMT off. Replays never call the model — machine time only.
#
# Resumable at two levels: replay_l3_profile.sh DONE-marks each pass, and this driver
# skips a task whose 9th pass is DONE. Stop cleanly between tasks: touch ML_iso36/STOP.
#
# SHARED MACHINE. replay_l3_profile.sh refuses to start a pass while a foreign perf is
# live (exit 3); this driver then stops the whole sweep. Never kill another user's
# collectors.
set -o pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
KIT="$REPO/local_agents/kit/replay/replay_l3_profile.sh"
SEL="$REPO/local_agents/ML_typeid/selection_36_count.tsv"
# banked census tree (full ws02 mirror, 2026-08-21) first, staged partial copies second
TRAJ_SRC="${TRAJ_SRC:-$REPO/local_agents/ML_typeid/data}"
export DATA_ROOT="$HERE/data"
export TIER_PREFIX=glm WINSEC=0.1 SKIP_K3S=1
export CPUS_MEASURED="${CPUS_MEASURED:-4-11}" CPUS_HOUSE="${CPUS_HOUSE:-0-3,12-15}"
export PROF_GROUPS="${PROF_GROUPS:-fpbr cache mlp fe fe_lat core_ports dram_bw priv fe_miss}"
NG=$(echo $PROF_GROUPS | wc -w)
LOG="${LOG:-$HERE/sweep.log}"
log(){ printf '[iso36 %s] %s\n' "$(date +%H:%M:%S)" "$*" | tee -a "$LOG"; }

img_of(){ echo "swebench/sweb.eval.x86_64.$(echo "$1" | sed 's/__/_1776_/'):latest"; }
free_gb(){ df -BG --output=avail "$HERE" 2>/dev/null | tail -1 | tr -dc '0-9'; }
gc_images(){
  docker images --format '{{.Repository}}:{{.Tag}}' 'swebench/*' 2>/dev/null | while read -r i; do
    docker ps -a --format '{{.Image}}' | grep -qF "$i" || docker rmi "$i" >/dev/null 2>&1
  done
}
ensure_image(){ # $1 instance
  local IMG; IMG=$(img_of "$1")
  if [ "$(free_gb)" -lt "${MIN_FREE_GB:-40}" ]; then
    log "disk low ($(free_gb)G) — GC swebench images"; gc_images
    [ "$(free_gb)" -lt "${MIN_FREE_GB:-40}" ] && { log "ABORT: disk still low"; exit 4; }
  fi
  docker image inspect "$IMG" >/dev/null 2>&1 && return 0
  local t
  for t in 1 2 3; do
    timeout 900 docker pull "$IMG" >/dev/null 2>&1 && return 0
    log "pull retry $t/3 $IMG"; sleep $((t * 20))
  done
  return 1
}

# Work list: selection order re-sorted fence-ascending, so a mid-sweep stop loses the
# least work and the smoke/calibration tasks come first.
WORK=$(awk -F'\t' 'NR>1 && $2 ~ /__/ {print $9 "\t" $2 "\t" $3}' "$SEL" | sort -n)
TOTAL=$(echo "$WORK" | wc -l)
log "SWEEP START: $TOTAL tasks x $NG groups @ ${WINSEC}s on $CPUS_MEASURED (groups: $PROF_GROUPS)"

done_n=0
echo "$WORK" | while IFS=$'\t' read -r fence inst short; do
  [ -f "$HERE/STOP" ] && { log "STOP seen — stopping cleanly"; exit 0; }
  if [ -f "$DATA_ROOT/${TIER_PREFIX}_replay_swe_${short}/run_${NG}/DONE" ]; then
    log "skip $short — all $NG passes DONE"; continue
  fi
  # instance ids are globally unique — accept any layout under traj_src (fetch_trajs.sh's
  # per-short dirs, or a straight rsync of the ws02 tree)
  SRC_TRAJ=$(find "$TRAJ_SRC" -name "${inst}.traj" ! -name "*.local.traj" 2>/dev/null | head -1)
  [ -n "$SRC_TRAJ" ] || { log "SKIP $short — no staged trajectory (run fetch_trajs.sh)"; continue; }
  # localize: rewrites recorded-on-ws02 paths and strips harness-abort tail turns; returns
  # the input path when nothing needs fixing.
  LOCAL=$(python3 "$REPO/local_agents/kit/replay/localize_traj.py" "$SRC_TRAJ" --repo "$REPO" 2>/dev/null | tail -1)
  [ -f "$LOCAL" ] || LOCAL="$SRC_TRAJ"
  ensure_image "$inst" || { log "FAIL $short — image pull"; continue; }
  log "===== $short ($inst, fence ${fence}s) — $NG groups ====="
  SHORT="$short" SRC=1 TRAJ_OVERRIDE="$LOCAL" bash "$KIT" 2>&1 | tee -a "$LOG" \
    | grep -E "pass [0-9]+ \(|ALL PASSES|FATAL|FAILED|STOP at pass"
  rc=${PIPESTATUS[0]}
  if [ "$rc" = 3 ]; then
    log "SWEEP STOPPED — foreign perf on the box. Re-run this script to resume."
    exit 3
  fi
  [ "${KEEP_IMAGES:-0}" = 1 ] || docker rmi "$(img_of "$inst")" >/dev/null 2>&1
  done_n=$((done_n + 1))
  log "----- $short done ($done_n this session) -----"
done
rc=$?
[ "$rc" = 0 ] && log "SWEEP COMPLETE"
exit $rc
