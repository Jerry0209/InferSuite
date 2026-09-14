#!/usr/bin/env bash
# derive_dcperf.sh — turn a banked external-suite capture into the shared metric vocabulary.
#
# Runs the SAME analyzer the 36 agentic tasks use (analyze_l3_windows.py), pointed at the
# suite's run dirs via two environment overrides rather than a forked copy:
#   L3_BASE_PREFIX=<suite>_        run dirs are <DATA>/<suite>_<workload>/run_N
#   L3_FENCES={"server":"<suite>-"} one fence: the server scope under measured.slice
# ("both", the merged fence the figures use, therefore equals the server fence here.)
# Then exports the whole suite's rows (every workload derived so far) for the plots.
#
#   ./derive_dcperf.sh feedsim                                  # SUITE=dcperf (default)
#   SUITE=renaissance DATA=local_agents/JVMbench/data ./derive_dcperf.sh finagle-http
set -euo pipefail
KITD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$KITD/../../.." && pwd)"
WL="${1:?workload, e.g. feedsim | finagle-http | cassandra}"
SUITE="${SUITE:-dcperf}"
PY="$HOME/miniforge3/envs/infersuite-full/bin/python3"
DATA="${DATA:-$REPO/local_agents/DCPerf/data}"
case "$DATA" in /*) ;; *) DATA="$REPO/$DATA" ;; esac

L3_BASE_PREFIX="${SUITE}_" L3_FENCES="{\"server\":\"${SUITE}-\"}" \
  "$PY" "$REPO/local_agents/kit/replay/analyze_l3_windows.py" "$DATA" "$WL"
"$PY" "$REPO/local_agents/kit/plot/export_dcperf_rows.py" --suite "$SUITE" --data "$DATA"
