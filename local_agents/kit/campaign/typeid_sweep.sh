#!/usr/bin/env bash
# typeid_sweep.sh — resumable serial driver for the ML_typeid classification sweep.
#
# Per instance: ensure the SWE-bench image (3 pull retries — a transient Docker Hub blip
# once retired a cell whose image was already local), run ONE typeid episode
# (run_glm_campaign.sh typeid-one: no isolation, no perf; cpu.stat + cmdlog + usage JSONL),
# classify it into the typing ledger, then remove the image (KEEP_IMAGES=1 to keep).
#
# Halt conditions:
#   - two consecutive starved/short episodes  -> exit 3 (credit-starvation signature;
#     empty assistant turns, zero received tokens — do NOT debug the harness)
#   - free disk below MIN_FREE_GB even after image GC -> exit 4
#   - STOP file present at ML_typeid/STOP -> clean stop between episodes
#
#   LIMIT=<n>          stop after n episodes this invocation (0 = all remaining)
#   KEEP_IMAGES=1      don't docker-rmi after each episode
#   MIN_FREE_GB=40     disk floor before pulling the next image
set -o pipefail
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$KIT/../../.." && pwd)"
ML="$REPO/local_agents/ML_typeid"
export DATA_ROOT="${DATA_ROOT:-$ML/data}"
export SWE_SUBSET="${SWE_SUBSET:-multilingual}" SWE_TEMP="${SWE_TEMP:-0.6}"
export LOOP_GUARD_N="${LOOP_GUARD_N:-12}" REPEATS=1 SWE_DRAIN_S="${SWE_DRAIN_S:-2400}"
LIMIT="${LIMIT:-0}"; MIN_FREE_GB="${MIN_FREE_GB:-40}"
CLS="$KIT/typeid_classify.py"
mkdir -p "$DATA_ROOT" "$ML/logs"
log(){ printf '[sweep %s] %s\n' "$(date +%F.%T)" "$*" | tee -a "$ML/sweep.log"; }

free_gb(){ df --output=avail -BG "$DATA_ROOT" | tail -1 | tr -dc 0-9; }

img_of(){ echo "swebench/sweb.eval.x86_64.$(echo "$1" | sed 's/__/_1776_/'):latest"; }

gc_images(){ # remove typeid-pulled swebench images not in use (cheapest disk lever)
  docker images --format '{{.Repository}}:{{.Tag}}' 'swebench/*' 2>/dev/null | \
    xargs -r docker rmi >/dev/null 2>&1
  docker image prune -f >/dev/null 2>&1 || true   # the dangling swe-rex parents (see below)
  docker builder prune -f >/dev/null 2>&1 || true
}

"$KIT/run_glm_campaign.sh" typeid-preflight || exit 1

STARVED=0; N=0
python3 "$CLS" remaining | while read -r INST; do
  [ -f "$ML/STOP" ] && { log "STOP file present — stopping cleanly"; exit 0; }
  [ "$LIMIT" -gt 0 ] && [ "$N" -ge "$LIMIT" ] && { log "LIMIT=$LIMIT reached"; exit 0; }
  # Full instance-derived short (owner__repo-num -> owner-repo-num). The first sweep used
  # owner-tNUM, which COLLIDED: apache__druid-13704 and apache__lucene-13704 mapped to the
  # same run dir, and lucene was silently skipped as "banked" (found 2026-08-17). The 284
  # first-sweep dirs keep their old names; instance identity lives in metadata/ledger.
  SHORT="${INST%%__*}-${INST#*__}"
  OUT="$DATA_ROOT/glm_swe_$SHORT/run_1"
  if [ -f "$OUT/DONE" ] && [ -f "$OUT/episode_summary.json" ]; then
    log "skip $INST (banked + classified)"; continue
  fi

  if [ "$(free_gb)" -lt "$MIN_FREE_GB" ]; then
    log "disk low ($(free_gb)G) — GC swebench images"
    gc_images
    [ "$(free_gb)" -lt "$MIN_FREE_GB" ] && { log "ABORT: disk still low after GC"; exit 4; }
  fi

  IMG="$(img_of "$INST")"
  if ! docker image inspect "$IMG" >/dev/null 2>&1; then
    ok=0
    for try in 1 2 3; do
      log "pull $IMG (try $try)"
      docker pull -q "$IMG" >/dev/null 2>&1 && { ok=1; break; }
      sleep $((try * 10))
    done
    if [ "$ok" = 0 ]; then
      python3 "$CLS" mark "$INST" no-image "$IMG" --ledger | tee -a "$ML/sweep.log"
      continue
    fi
  fi

  log "episode $INST (short=$SHORT)"
  SWE_INSTANCES="$INST" SWE_SHORT_SUFFIX="-${INST#*__}" \
    "$KIT/run_glm_campaign.sh" typeid-one "$INST" > "$ML/logs/${SHORT}.log" 2>&1
  RC=$?

  if [ -d "$OUT" ]; then
    LINE=$(python3 "$CLS" episode "$OUT" --ledger --instance "$INST")
  else
    python3 "$CLS" mark "$INST" episode-fail "rc=$RC no-run-dir" --ledger >/dev/null
    LINE="STATUS episode-fail $INST rc=$RC"
  fi
  log "$LINE (rc=$RC)"

  case "$LINE" in
    "STATUS starved"*|*"steps=0"*) STARVED=$((STARVED+1)) ;;
    "STATUS classified"*)          STARVED=0 ;;
  esac
  if [ "$STARVED" -ge 2 ]; then
    log "ABORT: two consecutive starved episodes — credit-starvation signature (check GLM balance)"
    exit 3
  fi

  [ "${KEEP_IMAGES:-0}" = 1 ] || docker rmi "$IMG" >/dev/null 2>&1
  # rmi only UNTAGS the base — swe-rex builds a derived image on top, so the entry survives
  # as dangling and accumulated ~271 GB in the first sweep (2026-08-12). Prune it here,
  # never between episodes (a prune could race swe-rex's next image build).
  [ "${KEEP_IMAGES:-0}" = 1 ] || docker image prune -f >/dev/null 2>&1
  N=$((N+1))
done
RC=$?
log "sweep loop ended (rc=$RC)"
python3 "$CLS" matrix | tee -a "$ML/sweep.log"
exit $RC
