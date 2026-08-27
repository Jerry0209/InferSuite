#!/usr/bin/env bash
# run_live36.sh — LIVE P7 episodes of the 36 count-view picks with the full instrument
# stack (PI directive 2026-08-27): ISO-PROOF-gated isolation, litellm proxy, shuffled
# zero-mux rotation over NINE groups (shared 8 + fe_miss => all 18 metrics live),
# continuous TMA census, 100 ms windows on cores 4-11 SMT-off — the same configuration as
# the replays, so live-vs-replay is a per-task instrument comparison.
#
# COSTS API TOKENS: every episode calls GLM live. Order: the 4 resolution-revision picks
# first (they also just received their replay profiles), then the other 32 by ascending
# census fence. LIMIT=n bounds a batch (LIMIT=4 = the pilot four). Resumable: an episode
# with DONE is skipped; touch ML_iso36/STOP_LIVE to stop cleanly between episodes.
# Two consecutive episode failures abort the sweep (credit-starvation signature — check
# the GLM balance, don't debug the harness).
#
# NOTE the live trajectory is a NEW episode (an agent never repeats its actions), so the
# live-vs-replay comparison here is per-TASK (same instance, two episodes, two
# instruments), not same-trajectory. The same-trajectory validation is the 12-pair study
# (deck slide 43); this campaign adds the live side the 36 never had.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
CAMP="$REPO/local_agents/kit/campaign/run_glm_campaign.sh"
SEL="$REPO/local_agents/ML_typeid/selection_36_count.tsv"
export DATA_ROOT="$HERE/data_live"
export TIER_PREFIX=glm WINSEC=0.1 SWE_SUBSET=multilingual SKIP_K3S=1
export CPUS_MEASURED="${CPUS_MEASURED:-4-11}" CPUS_HOUSE="${CPUS_HOUSE:-0-3,12-15}"
export GORDER_OVERRIDE="fpbr cache mlp fe fe_lat core_ports dram_bw priv fe_miss"
export LOOP_GUARD_N="${LOOP_GUARD_N:-12}" REPEATS=1
export SWE_IMG_PREPULL=1 SWE_IMG_GC="${SWE_IMG_GC:-1}"
LOG="${LOG:-$HERE/live_sweep.log}"
mkdir -p "$DATA_ROOT"
log(){ printf '[live36 %s] %s\n' "$(date +%H:%M:%S)" "$*" | tee -a "$LOG"; }

free_gb(){ df -BG --output=avail "$HERE" 2>/dev/null | tail -1 | tr -dc '0-9'; }

# The 4 resolution-revision picks lead; then the 32 by ascending fence.
NEW4="redis__redis-10068 fluent__fluentd-3328 vuejs__core-11870 axios__axios-5892"
WORK=$(
  for i in $NEW4; do awk -F'\t' -v i="$i" 'NR>1 && $2==i {print 0 "\t" $2 "\t" $3}' "$SEL"; done
  awk -F'\t' 'NR>1 && $2 ~ /__/ {print $9 "\t" $2 "\t" $3}' "$SEL" | sort -n | \
    grep -vE "redis__redis-10068|fluent__fluentd-3328|vuejs__core-11870|axios__axios-5892"
)
TOTAL=$(echo "$WORK" | wc -l)
log "LIVE SWEEP START: $TOTAL tasks (LIMIT=${LIMIT:-none}) @ ${WINSEC}s x 9 groups on $CPUS_MEASURED"

# stage gates once (dryrun + smoke certify the PMU + proxy before any token is spent)
STATE="$REPO/local_agents/kit/campaign/.state"
if [ ! -f "$STATE/smoke_ok" ] || [ ! -f "$STATE/dryrun_ok" ]; then
  log "running stage gates (preflight -> dryrun -> smoke)"
  bash "$CAMP" smoke 2>&1 | tee -a "$LOG" | grep -E "PREFLIGHT|DRYRUN|SMOKE|FAIL|OK$" || true
  [ -f "$STATE/smoke_ok" ] || { log "ABORT: smoke gate did not pass"; exit 1; }
fi

n=0 fails=0
echo "$WORK" | while IFS=$'\t' read -r _fence inst short; do
  [ -f "$HERE/STOP_LIVE" ] && { log "STOP_LIVE seen — stopping cleanly"; exit 0; }
  [ -n "${LIMIT:-}" ] && [ "$n" -ge "$LIMIT" ] && { log "LIMIT=$LIMIT reached"; exit 0; }
  if [ -f "$DATA_ROOT/glm_swe_${short}/run_1/DONE" ]; then
    log "skip $short — DONE"; continue
  fi
  if [ "$(free_gb)" -lt "${MIN_FREE_GB:-8}" ]; then
    log "ABORT: disk low ($(free_gb)G)"; exit 4
  fi
  SUF="${short#"${inst%%__*}"}"
  log "===== LIVE $short ($inst) ====="
  SWE_INSTANCES="$inst" SWE_SHORT_SUFFIX="$SUF" bash "$CAMP" campaign swe \
    >> "$LOG" 2>&1
  if [ -f "$DATA_ROOT/glm_swe_${short}/run_1/DONE" ]; then
    n=$((n + 1)); fails=0
    log "----- $short live done ($n this session) -----"
  else
    fails=$((fails + 1))
    log "EPISODE FAILED $short (consecutive fails: $fails)"
    [ "$fails" -ge 2 ] && { log "ABORT: two consecutive failures — check GLM balance / harness"; exit 5; }
  fi
done
rc=$?
[ "$rc" = 0 ] && log "LIVE SWEEP COMPLETE"
exit $rc
