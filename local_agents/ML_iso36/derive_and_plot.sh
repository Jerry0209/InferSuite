#!/usr/bin/env bash
# derive_and_plot.sh — refresh the per-window derivations and the two iso36 figure sets
# from whatever the sweep has banked so far. Idempotent; safe to run while the sweep is
# live (reads only completed passes: analyze keys on run_*/l3group.txt).
set -u
PY=/home/thu/miniforge3/envs/infersuite-full/bin/python3
REPO=/home/thu/InferSuite
cd "$REPO"
n=0
for d in local_agents/ML_iso36/data/glm_replay_swe_*/; do
  [ -e "$d" ] || continue
  s=$(basename "$d" | sed 's/glm_replay_swe_//')
  ls "$d"run_*/l3group.txt >/dev/null 2>&1 || continue
  "$PY" local_agents/kit/replay/analyze_l3_windows.py local_agents/ML_iso36/data "$s" \
      >/dev/null 2>&1 && n=$((n+1)) || echo "derive FAIL $s"
done
echo "derived $n task(s)"
"$PY" local_agents/kit/plot/plot_iso36_tma.py
"$PY" local_agents/kit/plot/plot_iso36_grid.py
