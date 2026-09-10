#!/usr/bin/env bash
# derive_dcperf.sh — turn a banked DCPerf capture into the shared metric vocabulary.
#
# Runs the SAME analyzer the 36 agentic tasks use (analyze_l3_windows.py), pointed at the
# DCPerf run dirs via two environment overrides rather than a forked copy:
#   L3_BASE_PREFIX=dcperf_        run dirs are <DATA>/dcperf_<bench>/run_N
#   L3_FENCES={"server":"dcperf-"} one fence: the server scope under measured.slice
# ("both", the merged fence the figures use, therefore equals the server fence here.)
#
#   ./derive_dcperf.sh [bench]        # default: feedsim
set -euo pipefail
KITD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$KITD/../../.." && pwd)"
BENCH="${1:-feedsim}"
PY="$HOME/miniforge3/envs/infersuite-full/bin/python3"
DATA="$REPO/local_agents/DCPerf/data"

L3_BASE_PREFIX=dcperf_ L3_FENCES='{"server":"dcperf-"}' \
  "$PY" "$REPO/local_agents/kit/replay/analyze_l3_windows.py" "$DATA" "$BENCH"
"$PY" "$REPO/local_agents/kit/plot/export_dcperf_rows.py"
