#!/usr/bin/env bash
# run_liverep4.sh — dedicated-group replays of the NEW P7 live trajectories of the 4
# resolution-revision picks (PI directive 2026-08-27): the same-trajectory live/replay
# pairs for the live-vs-replay comparison at temp 0.6.
#
# Source trajectories: ML_iso36/data_live/glm_swe_<short>/run_1/traj (the 0.6 live
# episodes; the parked *.greedy_bak dirs are never read). Output:
# ML_iso36/data_liverep/glm_replay_swe_<short>/run_{1..9}. Machine time only.
set -o pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
KIT="$REPO/local_agents/kit/replay/replay_l3_profile.sh"
export DATA_ROOT="$HERE/data_liverep"
export TIER_PREFIX=glm WINSEC=0.1 SKIP_K3S=1
export CPUS_MEASURED="${CPUS_MEASURED:-4-11}" CPUS_HOUSE="${CPUS_HOUSE:-0-3,12-15}"
export PROF_GROUPS="fpbr cache mlp fe fe_lat core_ports dram_bw priv fe_miss"
NG=$(echo $PROF_GROUPS | wc -w)
LOG="${LOG:-$HERE/liverep_sweep.log}"
log(){ printf '[liverep %s] %s\n' "$(date +%H:%M:%S)" "$*" | tee -a "$LOG"; }
mkdir -p "$DATA_ROOT"

PAIRS="redis-t10068|redis__redis-10068
fluent-t3328|fluent__fluentd-3328
vuejs-t11870|vuejs__core-11870
axios-t5892|axios__axios-5892"

log "LIVEREP SWEEP START: 4 tasks x $NG groups @ ${WINSEC}s (trajs = the 0.6 live episodes)"
for row in $PAIRS; do
  SHORT="${row%%|*}"; INST="${row##*|}"
  [ -f "$HERE/STOP" ] && { log "STOP seen"; exit 0; }
  if [ -f "$DATA_ROOT/glm_replay_swe_${SHORT}/run_${NG}/DONE" ]; then
    log "skip $SHORT — all $NG passes DONE"; continue
  fi
  SRC_TRAJ=$(find "$HERE/data_live/glm_swe_${SHORT}/run_1/traj" -name "${INST}.traj" \
             ! -name "*.local.traj" 2>/dev/null | head -1)
  [ -n "$SRC_TRAJ" ] || { log "SKIP $SHORT — no 0.6 live trajectory yet"; continue; }
  LOCAL=$(python3 "$REPO/local_agents/kit/replay/localize_traj.py" "$SRC_TRAJ" --repo "$REPO" 2>/dev/null | tail -1)
  [ -f "$LOCAL" ] || LOCAL="$SRC_TRAJ"
  log "===== $SHORT ($INST) — $NG groups on the live-P7 trajectory ====="
  SHORT="$SHORT" SRC=1 TRAJ_OVERRIDE="$LOCAL" bash "$KIT" 2>&1 | tee -a "$LOG" \
    | grep -E "pass [0-9]+ \(|ALL PASSES|FATAL|FAILED|STOP at pass"
  rc=${PIPESTATUS[0]}
  [ "$rc" = 3 ] && { log "SWEEP STOPPED — foreign perf on the box"; exit 3; }
  log "----- $SHORT done -----"
done
log "LIVEREP SWEEP COMPLETE"
