#!/usr/bin/env bash
# replay_l3_profile.sh — per-window TMA-L1..L3 distribution study over deterministic replays.
#
# For each counter group: ONE dedicated-group replay (GORDER_OVERRIDE => every window is that
# group => continuous-grade per-window series) at small WINSEC, plus a host-side command tagger
# that polls the tool cgroup's processes at 2 Hz from the HOUSEKEEPING cores (zero pollution of
# the measured fences) -> cmdlog.tsv (epoch \t pid \t argv). Replays call NO model: free.
#
#   SHORT=scikit-learn SRC=1 DATA_ROOT=.../superseded_40min/data ./replay_l3_profile.sh
#
# Passes are strictly serialized (GP counters are a shared resource).
set -o pipefail
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHORT="${SHORT:?task short name, e.g. scikit-learn}"
SRC="${SRC:?live source run number}"
export DATA_ROOT="${DATA_ROOT:?}"
export TIER_PREFIX="${TIER_PREFIX:-glm}"
export WINSEC="${WINSEC:-2}"
# TRAJ_OVERRIDE: pass a specific (e.g. localize_traj.py-localized) trajectory to every pass —
# required when the source campaign was recorded on another workstation. See run_glm_campaign.sh.
[ -n "${TRAJ_OVERRIDE:-}" ] && export TRAJ_OVERRIDE
PROF_GROUPS="${PROF_GROUPS:-fe_lat fe fpbr cache mlp core_ports dram_bw mem_bound fe_l3x priv}"
log(){ printf '[l3prof %s] %s\n' "$(date +%H:%M:%S)" "$*"; }

NG=$(echo $PROF_GROUPS | wc -w); n=0
for g in $PROF_GROUPS; do
  n=$((n+1))
  OUT="$DATA_ROOT/${TIER_PREFIX}_replay_swe_${SHORT}/run_${n}"
  if [ -f "$OUT/DONE" ] && [ -f "$OUT/l3group.txt" ] && [ "$(cat "$OUT/l3group.txt")" = "$g" ]; then
    log "skip pass $n ($g) — DONE"; continue
  fi
  grep -q "^GRP\[$g\]=" "$KIT/run_glm_campaign.sh" || { log "FATAL: unknown group '$g'"; exit 1; }
  log "===== pass $n/$NG: group=$g -> run_$n ====="
  rm -rf "$OUT"
  sleep 30   # settle: let the previous pass's teardown fully drain before ISO-PROOF

  # ---- host-side command tagger (housekeeping cores; starts once tool_cg is known) ----
  (
    for i in $(seq 1 600); do [ -f "$OUT/metadata.json" ] && break; sleep 1; done
    TCG=$(python3 -c "
import json,sys
d=json.load(open('$OUT/metadata.json'))
print(d.get('tool_cg') or d.get('extra',{}).get('tool_cg') or '')" 2>/dev/null)
    [ -n "$TCG" ] || exit 0
    PROCS="/sys/fs/cgroup/$TCG/cgroup.procs"
    while [ -e "$PROCS" ] && [ ! -f "$OUT/DONE" ]; do
      ts=$(date +%s.%N)
      for p in $(cat "$PROCS" 2>/dev/null); do
        cmd=$(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null)
        [ -n "$cmd" ] && printf '%s\t%s\t%s\n' "$ts" "$p" "$cmd"
      done >> "$OUT/cmdlog.tsv"
      sleep 0.5
    done
  ) &
  TAGGER=$!
  taskset -pc 0,1,12,13 $TAGGER >/dev/null 2>&1

  GORDER_OVERRIDE="$g" "$KIT/run_glm_campaign.sh" replay-one "$SHORT" "$SRC" "$n"
  rc=$?
  kill "$TAGGER" 2>/dev/null; wait "$TAGGER" 2>/dev/null
  if [ $rc -eq 0 ] && [ -f "$OUT/DONE" ]; then
    echo "$g" > "$OUT/l3group.txt"
    nw=$(($(wc -l < "$OUT/windows.tsv" 2>/dev/null) - 1))
    log "pass $n ($g) OK — $nw windows, cmdlog $(wc -l < "$OUT/cmdlog.tsv" 2>/dev/null || echo 0) rows"
  else
    log "pass $n ($g) FAILED (rc=$rc) — continuing with next group"
  fi
done
log "ALL PASSES DONE for $SHORT"
