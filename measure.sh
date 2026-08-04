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
#   agents-oc    stub: prints how to restore the removed OpenClaw harness, exits 1
#   plots        regenerate every figure set from banked data (no capture, no spend)
#   validate     run every validator over banked data
#
# REMOVED 2026-08-04 (repo narrowed to SWE-agent profiling; restore from git history):
#   the `service` campaign (local_service/ + src/ + deploy/), the banked OC_clean
#   data/figures, and the OpenClaw harness (agentic/openclaw). The litellm proxy venv the
#   SWE campaign needs moved to local_agents/scripts/glm/.venv_litellm (gitignored; exact
#   pins recorded in local_agents/scripts/glm/litellm_venv_freeze.txt).
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
#   agents-oc  : (stub — harness removed 2026-08-04; env knobs documented in git history)
set -o pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GLM="$REPO/local_agents/scripts/glm"
# Plotting python: matplotlib/numpy moved out of the system interpreter into the
# `infersuite-full` conda env (2026-07) — bare python3 breaks every plotter and the dryrun gate.
PY="${PY:-$HOME/miniforge3/envs/infersuite-full/bin/python3}"
"$PY" -c "import matplotlib" 2>/dev/null || PY=python3   # last-resort fallback

usage(){ sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }
[ $# -ge 1 ] || usage 1
CAMP="$1"; STAGE="${2:-}"; shift $(( $# >= 2 ? 2 : 1 ))

case "$CAMP" in
  agents-swe)
    : "${SWE_TEMP:=0.6}" "${LOOP_GUARD_N:=12}" "${REPEATS:=1}" "${WINSEC:=5}"
    export SWE_TEMP LOOP_GUARD_N REPEATS SWE_SUBSET SWE_INSTANCES SWE_DRAIN_S WINSEC
    export DATA_ROOT="${DATA_ROOT:-$REPO/local_agents/SWE_clean/data}"
    [ -n "$STAGE" ] || { echo "need a stage (preflight|dryrun|smoke|campaign|validate)"; exit 1; }
    [ "$STAGE" = campaign ] && set -- swe "$@"
    exec "$GLM/run_glm_campaign.sh" "$STAGE" "$@" ;;

  agents-oc)
    echo "agents-oc: the OpenClaw harness (agentic/openclaw) was removed 2026-08-04 —"
    echo "restore it from git history (and its external/WildClawBench checkout) before"
    echo "running an OC capture. The kit code path in run_glm_campaign.sh is unchanged."
    exit 1 ;;

  plots)
    which="${STAGE:-all}"
    swe(){ echo "[plots] SWE_clean"; env PLOT_SPEC="$REPO/local_agents/SWE_clean/plot_spec.json" $PY "$GLM/plot_glm_results.py"
           env PLOT_SPEC="$REPO/local_agents/SWE_clean/plot_spec.json" $PY "$GLM/plot_call_structure.py"
           env PLOT_SPEC="$REPO/local_agents/SWE_clean/plot_spec.json" $PY "$GLM/plot_internal_tools.py"
           env PLOT_SPEC="$REPO/local_agents/SWE_clean/plot_spec.json" $PY "$GLM/plot_calls_vs_bursts.py"; }
    oc(){  if [ -f "$REPO/local_agents/OC_clean/plot_spec.json" ]; then
             echo "[plots] OC_clean"
             env PLOT_SPEC="$REPO/local_agents/OC_clean/plot_spec.json" $PY "$GLM/plot_glm_results.py"
             env PLOT_SPEC="$REPO/local_agents/OC_clean/plot_spec.json" $PY "$GLM/plot_call_structure.py"
           else echo "[plots] OC_clean: removed 2026-08-04 (restore from git history) — skipped"; fi; }
    case "$which" in
      agents-swe) swe ;; agents-oc) oc ;;
      all) swe; oc ;; *) echo "unknown plot set: $which"; exit 1 ;;
    esac ;;

  validate)
    which="${STAGE:-all}"
    va(){ if [ -d "$2" ]; then echo "[validate] $1"; $PY "$GLM/validate_glm_agents.py" "$2" glm
          else echo "[validate] $1: no banked data ($2 removed 2026-08-04?) — skipped"; fi; }
    case "$which" in
      agents-swe) va SWE_clean "$REPO/local_agents/SWE_clean/data" ;;
      agents-oc)  va OC_clean  "$REPO/local_agents/OC_clean/data" ;;
      all) va SWE_clean "$REPO/local_agents/SWE_clean/data"; va OC_clean "$REPO/local_agents/OC_clean/data" ;;
      *) echo "unknown validate set: $which"; exit 1 ;;
    esac ;;

  -h|--help|help) usage 0 ;;
  *) echo "unknown campaign: $CAMP"; echo; usage 1 ;;
esac
