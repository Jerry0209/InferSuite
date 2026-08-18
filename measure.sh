#!/usr/bin/env bash
# measure.sh — one command for every measurement campaign in this repo.
#
# Each subcommand is a thin, documented wrapper over a proven campaign kit (it sets the
# right data root / env and calls the kit's own staged runner). Nothing is reimplemented
# here; this is the single entry point so you don't have to remember four script locations.
#
#   ./measure.sh <campaign> <stage> [args]
#
# CAMPAIGNS
#   agents-swe   SWE-agent x GLM-5.2, long-horizon (SWE_clean: django/sympy/babel/fmt)
#   plots        regenerate every figure set from banked data (no capture, no spend)
#   validate     run every validator over banked data
#
# REMOVED (repo narrowed to SWE-agent profiling; restore from git history):
#   2026-08-04: the `service` campaign (local_service/ + src/ + deploy/), the banked
#   OC_clean data/figures, and the OpenClaw harness (agentic/openclaw). The litellm proxy
#   venv the SWE campaign needs moved into the kit (gitignored; exact pins in the kit's
#   litellm_venv_freeze.txt). 2026-08-05: the OC code paths in the kit (oc_episode,
#   watchers, OC plotters) and this script's agents-oc stub.
#
# STAGES (run in this order the first time)
#   preflight    fail-fast environment checks (no spend, no state change)
#   dryrun       counter-group multiplexing gate
#   smoke        one short episode end-to-end (agents only)
#   campaign     the real capture (honors the per-campaign env below)
#   validate     3-layer validator over the campaign's data
#
# EXAMPLES
#   ./measure.sh agents-swe preflight
#   SWE_INSTANCES="django__django-16560" SWE_DRAIN_S=5400 ./measure.sh agents-swe campaign
#   ./measure.sh plots agents-swe
#   ./measure.sh plots            # all figure sets
#   ./measure.sh plots agents-swe # one set
#
# Per-campaign env (defaults are the certified values; override on the command line):
#   agents-swe : SWE_INSTANCES SWE_SUBSET(verified) SWE_TEMP(0.6) SWE_DRAIN_S LOOP_GUARD_N(12) REPEATS(1)
set -o pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT="$REPO/local_agents/kit"
# Plotting python: matplotlib/numpy moved out of the system interpreter into the
# `infersuite-full` conda env (2026-07) — bare python3 breaks every plotter and the dryrun gate.
PY="${PY:-$HOME/miniforge3/envs/infersuite-full/bin/python3}"
"$PY" -c "import matplotlib" 2>/dev/null || PY=python3   # last-resort fallback

usage(){ sed -n '2,37p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }
[ $# -ge 1 ] || usage 1
CAMP="$1"; STAGE="${2:-}"; shift $(( $# >= 2 ? 2 : 1 ))

case "$CAMP" in
  agents-swe)
    : "${SWE_TEMP:=0.6}" "${LOOP_GUARD_N:=12}" "${REPEATS:=1}" "${WINSEC:=5}"
    export SWE_TEMP LOOP_GUARD_N REPEATS SWE_SUBSET SWE_INSTANCES SWE_DRAIN_S WINSEC
    export DATA_ROOT="${DATA_ROOT:-$REPO/local_agents/SWE_clean/data}"
    [ -n "$STAGE" ] || { echo "need a stage (preflight|dryrun|smoke|campaign|validate)"; exit 1; }
    [ "$STAGE" = campaign ] && set -- swe "$@"
    exec "$KIT/campaign/run_glm_campaign.sh" "$STAGE" "$@" ;;

  typeid)
    # ML_typeid: first-live-run TYPE IDENTIFICATION over SWE-bench Multilingual on a
    # non-P7 machine — no isolation, no perf; classification instruments only.
    # Stages: preflight | one <instance> | sweep | remaining | matrix
    : "${SWE_TEMP:=0.6}" "${LOOP_GUARD_N:=12}" "${SWE_SUBSET:=multilingual}"
    export SWE_TEMP LOOP_GUARD_N SWE_SUBSET SWE_INSTANCES SWE_DRAIN_S SWE_SHORT_SUFFIX
    export DATA_ROOT="${DATA_ROOT:-$REPO/local_agents/ML_typeid/data}"
    case "${STAGE:-}" in
      preflight)        exec "$KIT/campaign/run_glm_campaign.sh" typeid-preflight ;;
      one)              exec "$KIT/campaign/run_glm_campaign.sh" typeid-one "$@" ;;
      replay)           exec "$KIT/campaign/run_glm_campaign.sh" typeid-replay "$@" ;;
      sweep)            exec "$KIT/campaign/typeid_sweep.sh" "$@" ;;
      replay-sweep)     exec "$KIT/campaign/typeid_replay_sweep.sh" "$@" ;;
      remaining|matrix) exec python3 "$KIT/campaign/typeid_classify.py" "$STAGE" "$@" ;;
      *) echo "typeid stages: preflight | one <instance> | replay <instance> | sweep | replay-sweep | remaining | matrix"; exit 1 ;;
    esac ;;

  plots)
    which="${STAGE:-all}"
    case "$which" in agents-swe|all) ;; *) echo "unknown plot set: $which"; exit 1 ;; esac
    echo "[plots] SWE_clean"
    for P in plot_glm_results plot_call_structure plot_internal_tools plot_calls_vs_bursts; do
      env PLOT_SPEC="$REPO/local_agents/SWE_clean/plot_spec.json" $PY "$KIT/plot/$P.py"
    done ;;

  validate)
    which="${STAGE:-all}"
    case "$which" in agents-swe|all) ;; *) echo "unknown validate set: $which"; exit 1 ;; esac
    echo "[validate] SWE_clean"
    $PY "$KIT/validate/validate_glm_agents.py" "$REPO/local_agents/SWE_clean/data" glm ;;

  -h|--help|help) usage 0 ;;
  *) echo "unknown campaign: $CAMP"; echo; usage 1 ;;
esac
