#!/usr/bin/env bash
# run_iso8_languages.sh — re-capture the agentic replays for the FULL task set under the SPEC
# configuration, so the SPEC-vs-agentic comparison stops resting on two non-Python tasks.
#
#   configuration: measured cores 4-11 with SMT OFF, house 0-3,12-15, WINSEC=0.1
#                  8 shared counter groups (the ones SPEC and the agent both rotate)
#   cost:          machine time only — replays re-execute a recorded trajectory and never
#                  call the model. Whole set ~4.2 h.
#
# Task set = the 12 workloads of the per-window distribution figure:
#   Python      scikit-learn · astropy · sympy        (reproduced superseded_40min campaign)
#   JavaScript  babel        C++ fmtlib               (certified SWE_clean campaign)  [DONE]
#   TypeScript  vuejs        Java gson                (SWE-bench Multilingual pilots)
#   Rust        tokio-rs     Go   prometheus
#   C           jqlang       Ruby rubocop             PHP php-cs-fixer
#
# SHARED MACHINE. Another user profiles the same cores. `replay_l3_profile.sh` now refuses to
# start a PASS while a foreign perf is live (exit 3); this driver stops the whole sweep when
# that happens rather than moving to the next task. Completed passes are DONE-marked, so
# re-running resumes exactly where it stopped. Never kill another user's collectors.
set -o pipefail
REPO=/home/thu/InferSuite
KIT="$REPO/local_agents/kit/replay/replay_l3_profile.sh"
export DATA_ROOT="$REPO/local_agents/SWE_iso8/data"
export TIER_PREFIX=glm WINSEC=0.1 SKIP_K3S=1
export CPUS_MEASURED=4-11 CPUS_HOUSE=0-3,12-15
# Overridable so a later pass can APPEND a group without re-running the eight already banked.
# Order is load-bearing: replay_l3_profile.sh maps group i -> run_i, and runs 1-8 skip only
# because their DONE marker and l3group.txt still match this order. Never reorder it.
export PROF_GROUPS="${PROF_GROUPS:-fpbr cache mlp fe fe_lat core_ports dram_bw priv}"
LOG="${LOG:-$REPO/local_agents/SWE_iso8/sweep.log}"

# task|source tree|trajectory basename   (ordered short-first so a stop loses the least work)
TASKS="
vuejs|ML_multiling|vuejs__core-11915
rubocop|ML_multiling|rubocop__rubocop-13668
google|ML_multiling|google__gson-2061
tokio-rs|ML_multiling|tokio-rs__tokio-6551
jqlang|ML_multiling|jqlang__jq-2681
scikit-learn|superseded_40min|scikit-learn__scikit-learn-25232
php-cs-fixer|ML_multiling|php-cs-fixer__php-cs-fixer-7523
astropy|superseded_40min|astropy__astropy-14096
sympy|superseded_40min|sympy__sympy-14248
prometheus|ML_multiling|prometheus__prometheus-9248
"

log(){ printf '[sweep %s] %s\n' "$(date +%H:%M:%S)" "$*" | tee -a "$LOG"; }

for row in $TASKS; do
  SHORT="${row%%|*}"; rest="${row#*|}"; TREE="${rest%%|*}"; TRAJ_BASE="${rest##*|}"
  NG=$(echo $PROF_GROUPS | wc -w)
  if [ -f "$DATA_ROOT/${TIER_PREFIX}_replay_swe_${SHORT}/run_${NG}/DONE" ]; then
    log "skip $SHORT — already complete"; continue
  fi
  T="$REPO/local_agents/$TREE/data/${TIER_PREFIX}_swe_${SHORT}/run_1/traj"
  TRAJ="$(find "$T" -name "${TRAJ_BASE}.local.traj" 2>/dev/null | head -1)"
  [ -n "$TRAJ" ] || TRAJ="$(find "$T" -name "${TRAJ_BASE}.traj" 2>/dev/null | head -1)"
  [ -n "$TRAJ" ] || { log "SKIP $SHORT — no trajectory under $T"; continue; }
  log "===== $SHORT ($TREE) — $NG groups @ ${WINSEC}s on $CPUS_MEASURED ====="
  SHORT="$SHORT" SRC=1 TRAJ_OVERRIDE="$TRAJ" bash "$KIT" 2>&1 | tee -a "$LOG" \
    | grep -E "pass [0-9]+ \(|ALL PASSES|FATAL|FAILED|STOP at pass"
  rc=${PIPESTATUS[0]}
  if [ "$rc" = 3 ]; then
    log "SWEEP STOPPED — the box is in use by another user. Re-run this script to resume."
    exit 3
  fi
  log "----- $SHORT done -----"
done
log "SWEEP COMPLETE"
