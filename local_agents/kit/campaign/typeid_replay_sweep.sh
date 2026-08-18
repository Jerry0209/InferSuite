#!/bin/bash
# typeid_replay_sweep.sh — token-free RE-SWEEP of the banked TYPEID trajectories with the
# full CPU-attribution instrument set (cpu.stat pollers + 2 Hz cmdlog + per-PID sampler +
# taskstats exit receipts). No model is ever called: `sweagent run-replay` re-issues the
# recorded actions. Pilot evidence (2026-08-17): replay reproduces live fence CPU to
# 0.98-1.04 same-machine, receipts cover ~97% of every fence, ownership-aggregated shares
# match the P7 window truth <=9 pt on all three strict cases.
#
# Worklist = every banked ML_typeid live episode with a trajectory (285), keyed by
# metadata.json extra.instance — NEVER by reconstructing the short name (the -t<num> short
# collides for apache druid/lucene; the banked dir name is ground truth). Plus the OLD
# consumed instances whose trajectories are banked in ML_multiling / SWE_clean (localized
# copies; the P7 evidence is never modified). Known gaps, no trajectory anywhere:
# prometheus-9248 (lost in the workstation migration), terraform-35543, carbon-2813,
# laravel-51890.
#
# Resumable: a replay dir with DONE **and a non-empty taskstats.tsv** is skipped; anything
# else (incl. the three pre-receipt pilot replays) is redone. Stop cleanly between episodes:
#   touch local_agents/ML_typeid/STOP_REPLAY
# Env: KEEP_IMAGES=1 (no rmi), MIN_FREE_GB=40, REPLAY_DRAIN_S=2400, LIMIT=n (bounded batch).
set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../../.." && pwd)"
ML="$REPO/local_agents/ML_typeid"
DATA="${DATA_ROOT:-$ML/data}"
mkdir -p "$ML/logs"
LOG="$ML/replay_sweep.log"
log(){ echo "[repsweep $(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

img_of(){ echo "swebench/sweb.eval.x86_64.$(echo "$1" | sed 's/__/_1776_/'):latest"; }
free_gb(){ df -BG --output=avail "$DATA" 2>/dev/null | tail -1 | tr -dc '0-9'; }
gc_images(){
  docker images --format '{{.Repository}}:{{.Tag}}' 'swebench/*' 2>/dev/null | while read -r i; do
    docker ps -a --format '{{.Image}}' | grep -qF "$i" || docker rmi "$i" >/dev/null 2>&1
  done
}
ensure_image(){ # $1 instance -> 0 with image present, else 1
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

DONE_N=0 SKIP_N=0 FAIL_N=0 TOTAL=0
FAILED=""
milestone(){ log "MILESTONE done=$DONE_N skip=$SKIP_N fail=$FAIL_N of $TOTAL"; }

run_one(){ # $1 instance, $2 short-suffix (leading dash), $3 optional TRAJ_OVERRIDE
  local INST="$1" SUF="$2" TRAJ="${3:-}"
  local SHORT="${INST%%__*}${SUF}"
  local RDIR="$DATA/glm_replay_swe_${SHORT}/run_1"
  if [ -f "$RDIR/DONE" ] && [ -s "$RDIR/taskstats.tsv" ]; then
    SKIP_N=$((SKIP_N + 1)); return 0
  fi
  [ -d "$RDIR" ] && rm -rf "$RDIR"      # partial, or pre-receipt pilot: redo with receipts
  ensure_image "$INST" || { log "FAIL no-image $SHORT"; FAIL_N=$((FAIL_N+1)); FAILED="$FAILED $SHORT:no-image"; return 1; }
  local IMG; IMG=$(img_of "$INST")
  SWE_SHORT_SUFFIX="$SUF" TRAJ_OVERRIDE="$TRAJ" REPLAY_DRAIN_S="${REPLAY_DRAIN_S:-2400}" \
    timeout $(( ${REPLAY_DRAIN_S:-2400} + 900 )) \
    "$REPO/measure.sh" typeid replay "$INST" > "$ML/logs/${SHORT}.rep.log" 2>&1
  if [ -f "$RDIR/DONE" ] && [ -s "$RDIR/taskstats.tsv" ]; then
    DONE_N=$((DONE_N + 1))
  elif [ -f "$RDIR/DONE" ]; then
    log "WARN $SHORT done but NO receipts (taskstats probe failed?)"
    DONE_N=$((DONE_N + 1)); FAILED="$FAILED $SHORT:no-receipts"
  else
    log "FAIL episode $SHORT (see logs/${SHORT}.rep.log)"
    FAIL_N=$((FAIL_N + 1)); FAILED="$FAILED $SHORT:episode"
  fi
  [ "${KEEP_IMAGES:-0}" = 1 ] || docker rmi "$IMG" >/dev/null 2>&1
  [ $(( (DONE_N + SKIP_N + FAIL_N) % 25 )) -eq 0 ] && milestone
  return 0
}

# ---- part A: the 285 banked typeid episodes -------------------------------------------
MAP="$ML/.replay_map.tsv"
python3 - "$DATA" > "$MAP" <<'PY'
import glob, json, os, sys
for p in sorted(glob.glob(sys.argv[1] + "/glm_swe_*/run_1/metadata.json")):
    d = os.path.basename(os.path.dirname(os.path.dirname(p)))
    inst = (json.load(open(p)).get("extra") or {}).get("instance")
    if inst and glob.glob(os.path.dirname(p) + "/traj/*/*.traj"):
        print(f"{inst}\t{d}")
PY
TOTAL=$(wc -l < "$MAP")
log "SWEEP START: $TOTAL banked typeid episodes + old consumed set (LIMIT=${LIMIT:-none})"

N=0
while IFS=$'\t' read -r INST DIRB; do
  [ -f "$ML/STOP_REPLAY" ] && { log "STOP_REPLAY seen — stopping cleanly"; break; }
  [ -n "${LIMIT:-}" ] && [ "$N" -ge "$LIMIT" ] && break
  N=$((N + 1))
  REPO_PRE="${INST%%__*}"
  SUF="${DIRB#glm_swe_${REPO_PRE}}"
  # localize: strips harness-abort assistant turns that lack tool_calls (7/285 trajectories
  # end that way and run-replay asserts on them); returns the banked path when nothing to fix
  SRC=$(find "$DATA/$DIRB/run_1/traj" -name "${INST}.traj" ! -name "*.local.traj" 2>/dev/null | head -1)
  LOCAL=$(python3 "$REPO/local_agents/kit/replay/localize_traj.py" "$SRC" --repo "$REPO" 2>/dev/null | tail -1)
  [ -f "$LOCAL" ] || LOCAL=""
  run_one "$INST" "$SUF" "$LOCAL"
done < "$MAP"

# ---- part B: old consumed instances with banked trajectories elsewhere ----------------
# (the three already receipt-replayed as -X2681/-X6551/-X7523 skip via the DONE+receipts check)
OLD="jqlang__jq-2681|ML_multiling/data/glm_swe_jqlang|-X2681
tokio-rs__tokio-6551|ML_multiling/data/glm_swe_tokio-rs|-X6551
php-cs-fixer__php-cs-fixer-7523|ML_multiling/data/glm_swe_php-cs-fixer|-X7523
gin-gonic__gin-3741|ML_multiling/data/glm_swe_gin-gonic|-X3741
google__gson-2061|ML_multiling/data/glm_swe_google|-X2061
phpoffice__phpspreadsheet-3940|ML_multiling/data/glm_swe_phpoffice-bT|-X3940
preactjs__preact-4152|ML_multiling/data/glm_swe_preactjs-bT|-X4152
rubocop__rubocop-13668|ML_multiling/data/glm_swe_rubocop|-X13668
vuejs__core-11915|ML_multiling/data/glm_swe_vuejs|-X11915
babel__babel-15445|SWE_clean/data/glm_swe_babel|-X15445
fmtlib__fmt-3248|SWE_clean/data/glm_swe_fmtlib|-X3248"

if [ ! -f "$ML/STOP_REPLAY" ] && [ -z "${LIMIT:-}" ]; then
  echo "$OLD" | while IFS='|' read -r INST SRCD SUF; do
    [ -f "$ML/STOP_REPLAY" ] && break
    SRC=$(find "$REPO/local_agents/$SRCD"/run_*/traj -name "${INST}.traj" ! -name "*.local.traj" 2>/dev/null | head -1)
    [ -n "$SRC" ] || { log "GAP $INST (no banked trajectory in $SRCD)"; continue; }
    LOCAL=$(python3 "$REPO/local_agents/kit/replay/localize_traj.py" "$SRC" --repo "$REPO" | tail -1)
    [ -f "$LOCAL" ] || { log "FAIL localize $INST"; continue; }
    run_one "$INST" "$SUF" "$LOCAL"
  done
fi

milestone
log "SWEEP COMPLETE done=$DONE_N skip=$SKIP_N fail=$FAIL_N of $TOTAL (+old set)"
[ -n "$FAILED" ] && log "FAILED LIST:$FAILED"
log "GAPS (no trajectory anywhere): prometheus-9248 terraform-35543 carbon-2813 laravel-51890"
