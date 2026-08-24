#!/usr/bin/env bash
# fetch_trajs.sh — stage the 36 selected census trajectories from ws02 onto the P7.
#
# Reads selection_36_count.tsv + .replay_map.tsv, rsyncs each pick's banked traj dir
# (traj/<inst>/<inst>.traj and nothing else) into data/traj_src/<short>/, checksum mode.
# The ws02 source is read-only evidence: no --delete, no writes back.
#
#   WS02=network@bz-network-ws02.local WS02_REPO='~/InferSuite-Jerry' ./fetch_trajs.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
ML="$REPO/local_agents/ML_typeid"
SEL="$ML/selection_36_count.tsv"
MAP="$ML/.replay_map.tsv"
DST="$HERE/data/traj_src"
WS02="${WS02:-network@bz-network-ws02.local}"
WS02_REPO="${WS02_REPO:-~/InferSuite-Jerry}"
mkdir -p "$DST"

ok=0; fail=0; missing=""
while IFS=$'\t' read -r _n inst short _rest; do
  [ "$_n" = "#" ] && continue
  case "$inst" in *__*) ;; *) continue ;; esac
  dirb=$(awk -F'\t' -v i="$inst" '$1==i{print $2; exit}' "$MAP")
  if [ -z "$dirb" ]; then echo "NO-MAP   $inst"; fail=$((fail+1)); missing="$missing $inst"; continue; fi
  if find "$DST/$short" -name "${inst}.traj" 2>/dev/null | grep -q .; then
    echo "HAVE     $short"; ok=$((ok+1)); continue
  fi
  mkdir -p "$DST/$short"
  if rsync -ac --include='*/' --include="${inst}.traj" --exclude='*' \
       "$WS02:$WS02_REPO/local_agents/ML_typeid/data/$dirb/run_1/traj/" "$DST/$short/"; then
    f=$(find "$DST/$short" -name "${inst}.traj" | head -1)
    if [ -n "$f" ]; then
      echo "FETCHED  $short  $(du -h "$f" | cut -f1)"; ok=$((ok+1))
    else
      echo "EMPTY    $short (rsync ok but no ${inst}.traj under $dirb/run_1/traj/)"
      fail=$((fail+1)); missing="$missing $inst"
    fi
  else
    echo "RSYNC-FAIL $short"; fail=$((fail+1)); missing="$missing $inst"
  fi
done < "$SEL"

echo "----"
echo "staged $ok/36, failed $fail"
[ -n "$missing" ] && echo "missing:$missing"
[ "$ok" -eq 36 ] && echo "ALL 36 TRAJECTORIES STAGED" || exit 1
