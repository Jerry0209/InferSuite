#!/usr/bin/env bash
# sweep_jvm_suites.sh — profile the mentor's JVM server-benchmark list end to end, one
# benchmark after another, each through run_dcperf_profile.sh (9 counter passes, hardened
# isolation, automatic SMT handling), then derive everything into the shared vocabulary.
#
# "Whatever works on first shot, let's just go on with it" (mentor, 2026-09-14): a benchmark
# that fails is logged and skipped, never retried or debugged here.
#
#   nohup ./sweep_jvm_suites.sh > sweep_jvm.log 2>&1 &
set -o pipefail
KITD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$KITD/../../.." && pwd)"
export DATA_ROOT="${DATA_ROOT:-$REPO/local_agents/JVMbench/data}"
export CAPTURE_S="${CAPTURE_S:-180}"
RENAISSANCE="${RENAISSANCE:-finagle-http finagle-chirper page-rank naive-bayes neo4j-analytics}"
DACAPO="${DACAPO:-cassandra tomcat kafka}"
export D_ITERS="${D_ITERS:-80}"
log(){ printf '[jvm-sweep %s] %s\n' "$(date +%H:%M:%S)" "$*"; }
mkdir -p "$DATA_ROOT"
declare -A RC

for wl in $RENAISSANCE; do
  log "===== renaissance/$wl ====="
  SUITE=renaissance BENCH=renaissance WORKLOAD="$wl" timeout 7200 \
    bash "$KITD/run_dcperf_profile.sh"; RC["renaissance/$wl"]=$?
  log "renaissance/$wl rc=${RC[renaissance/$wl]}"
done
for wl in $DACAPO; do
  log "===== dacapo/$wl ====="
  SUITE=dacapo BENCH=dacapo WORKLOAD="$wl" timeout 7200 \
    bash "$KITD/run_dcperf_profile.sh"; RC["dacapo/$wl"]=$?
  log "dacapo/$wl rc=${RC[dacapo/$wl]}"
done

log "===== deriving (machine free now) ====="
for wl in $RENAISSANCE; do
  [ -f "$DATA_ROOT/renaissance_$wl/run_1/DONE" ] && SUITE=renaissance DATA="$DATA_ROOT" bash "$KITD/derive_dcperf.sh" "$wl" 2>&1 | tail -1
done
for wl in $DACAPO; do
  [ -f "$DATA_ROOT/dacapo_$wl/run_1/DONE" ] && SUITE=dacapo DATA="$DATA_ROOT" bash "$KITD/derive_dcperf.sh" "$wl" 2>&1 | tail -1
done
log "===== summary ====="
for k in "${!RC[@]}"; do
  n=$(ls -d "$DATA_ROOT/${k/\//_}"/run_*/DONE 2>/dev/null | wc -l)
  printf '  %-28s rc=%s  passes done=%s\n' "$k" "${RC[$k]}" "$n"
done | sort
log "ALL DONE"
