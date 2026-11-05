#!/usr/bin/env bash
# run_server.sh — ARM Server-set capture: Jef's families, one dedicated perf pass per
# <workload, family>, server fenced on the 8 measured cores (8-15), client on 0-7.
#
# ARM port of local_agents/kit/dcperf/run_dcperf_profile.sh. Kept: the bench_*.sh module
# contract (bench_preflight / bench_start OUT UNIT -> OUT/.server_cg / bench_stop OUT UNIT),
# the foreign-perf guard, CAPTURE_S per workload, 20 s settle. Replaced: the Intel groups,
# TMA and x86 shield -> arm_shield.sh (applied ONCE for the campaign, ISO-PROOF before every
# pass) + arm_server.py (perf -C 8-15 -G <scope>, gates). Each pass runs in its own subshell,
# so module state (pids, scopes) cannot leak into the next pass.
#
#   FAMILIES="tlb-data tlb-code" WORKLOADS="finagle-http" arm/kit/server/run_server.sh
#   SHIELD=0 ...   skip apply/restore (plumbing tests only; such passes are not valid captures)
set -o pipefail
export KITD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARMK="$(cd "$KITD/.." && pwd)"
export REPO="$(cd "$ARMK/../.." && pwd)"
export CPUS_MEASURED=8-15 CPUS_HOUSE=0-7 MSLICE=jerryserver.slice
export SCOPE_PROPS="-p AllowedCPUs=8-15 -p AllowedMemoryNodes=0"
RAW="${RAW:-$ARMK/../data/raw/server}"
LOG="${LOG:-$ARMK/../data/interim/server/campaign.log}"
FAMILIES="${FAMILIES:?families, e.g. 'tlb-data tlb-code'}"
WORKLOADS="${WORKLOADS:-tomcat feedsim finagle-chirper finagle-http cassandra-ycsb20m kafka-20g naivebayes-rcv1 neo4j-livejournal pagerank-livejournal video-4k}"
SHIELD="${SHIELD:-1}"
mkdir -p "$RAW" "$(dirname "$LOG")"
for f in "$KITD"/env_*.sh; do [ -f "$f" ] && source "$f"; done
source "$KITD/lib.sh"
dlog(){ printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*" | tee -a "$LOG"; }
export -f dlog; export LOG

# workload -> module and its x86 knobs (arm_server_profiling.md §3; CAPTURE_S as on x86)
wl_env(){ case "$1" in
  tomcat)               echo "BENCH=dacapo SUITE=dacapo WORKLOAD=tomcat CAPTURE_S=180" ;;
  feedsim)              echo "BENCH=feedsim SUITE=dcperf CAPTURE_S=300" ;;
  finagle-chirper)      echo "BENCH=renaissance SUITE=renaissance WORKLOAD=finagle-chirper CAPTURE_S=180" ;;
  finagle-http)         echo "BENCH=renaissance SUITE=renaissance WORKLOAD=finagle-http CAPTURE_S=180" ;;
  cassandra-ycsb20m)    echo "BENCH=cassandra SUITE=realdata WORKLOAD=cassandra-ycsb20m CAPTURE_S=180" ;;
  kafka-20g)            echo "BENCH=kafka SUITE=realdata WORKLOAD=kafka-20g CAPTURE_S=180" ;;
  naivebayes-rcv1)      echo "BENCH=spark SUITE=realdata WORKLOAD=naivebayes-rcv1 CAPTURE_S=180" ;;
  neo4j-livejournal)    echo "BENCH=neo4j SUITE=realdata WORKLOAD=neo4j-livejournal CAPTURE_S=180" ;;
  pagerank-livejournal) echo "BENCH=spark SUITE=realdata WORKLOAD=pagerank-livejournal CAPTURE_S=180" ;;
  selftest)             echo "BENCH=selftest SUITE=selftest WORKLOAD=selftest CAPTURE_S=${SELFTEST_S:-20}" ;;
  video-4k)             echo "BENCH=video_transcode SUITE=dcperf WORKLOAD=video-4k CAPTURE_S=180" ;;
  *) return 1 ;;
esac; }

foreign_perf(){ local pp; for pp in $(pgrep -x perf 2>/dev/null); do
  [ "$(stat -c %u "/proc/$pp" 2>/dev/null)" != "$(id -u)" ] && { echo "$pp"; return 0; }; done; return 1; }
slice_busy(){ [ -n "$(cat /sys/fs/cgroup/$MSLICE/*/cgroup.procs 2>/dev/null)" ]; }

one_pass(){ # $1 workload $2 family $3 OUT -> 0 valid, 2 invalid, 4 could not start
  local WL="$1" FAM="$2" OUT="$3" UNIT="jerry-$1-$2-$(basename "$3")"
  rm -rf "$OUT"; mkdir -p "$OUT"
  ( export PASS_ROOT=$BASHPID; eval "export $(wl_env "$WL")"
    source "$KITD/bench_${BENCH}.sh"
    bench_preflight >>"$OUT/driver.log" 2>&1 || { dlog "$WL: preflight FAILED (see $OUT/driver.log)"; exit 4; }
    if [ "$SHIELD" = 1 ]; then python3 "$ARMK/arm_server.py" isoproof --out "$OUT/iso.json" || exit 5
    else echo '{"iso_proof": "skipped (SHIELD=0: plumbing test, not a valid capture)"}' > "$OUT/iso.json"; fi
    if ! bench_start "$OUT" "$UNIT"; then
      dlog "$WL $FAM: did not reach steady state"; bench_stop "$OUT" "$UNIT"; exit 4
    fi
    CG="$(cat "$OUT/.server_cg")"
    python3 "$ARMK/arm_server.py" capture --family "$FAM" --cg "$CG" --seconds "$CAPTURE_S" --out "$OUT" | tee -a "$LOG"
    bench_stop "$OUT" "$UNIT"
    read -r R WHY < <(python3 "$ARMK/arm_server.py" receipt --bench "$BENCH" --out "$OUT")
    res=$(python3 "$ARMK/arm_server.py" finish --out "$OUT" --receipt "$R" --receipt-why "$WHY"); dlog "$WL $FAM $(basename "$OUT"): $res"
    [[ $res == VALID* ]] || exit 2 ) </dev/null
  local rc=$?
  slice_busy && { dlog "WARN: $MSLICE still has processes after $WL/$FAM — stopping our scopes";
                  for u in $(systemctl list-units --plain --no-legend "jerry-*.scope" | awk '{print $1}'); do sudo systemctl stop "$u"; done; }
  return $rc
}

APPLIED=0
cleanup(){ for u in $(systemctl list-units --plain --no-legend "jerry-*.scope" 2>/dev/null | awk '{print $1}'); do sudo systemctl stop "$u"; done
           [ "$APPLIED" = 1 ] && "$ARMK/arm_shield.sh" restore 2>&1 | tee -a "$LOG"; APPLIED=0; }
trap cleanup EXIT
trap 'exit 130' INT TERM HUP

if fp=$(foreign_perf); then dlog "STOP: foreign perf pid $fp on the box — refusing to compete"; exit 3; fi
if [ "$SHIELD" = 1 ]; then APPLIED=1; "$ARMK/arm_shield.sh" apply 2>&1 | tee -a "$LOG" || exit 1; fi
dlog "campaign: families=[$FAMILIES] workloads=[$WORKLOADS] shield=$SHIELD"
for FAM in $FAMILIES; do
  dlog "======== family $FAM"
  for WL in $WORKLOADS; do
    wl_env "$WL" >/dev/null || { dlog "unknown workload $WL"; continue; }
    D="$RAW/$WL/$FAM"; [ -f "$D/DONE" ] && continue
    [ -f "$RAW/$WL/ABORTED" ] && { dlog "$WL: skipped (ABORTED: $(cat "$RAW/$WL/ABORTED"))"; continue; }
    NFAIL=0
    for A in 1 2 3; do
      if fp=$(foreign_perf); then dlog "STOP: foreign perf pid $fp appeared — leaving banked passes"; exit 3; fi
      one_pass "$WL" "$FAM" "$D/a$A"; rc=$?
      dlog "$WL $FAM a$A rc=$rc"
      [ $rc = 0 ] && { echo "a$A" > "$D/DONE"; sleep 20; break; }
      [ $rc = 5 ] && { dlog "ISO-PROOF did not hold — aborting campaign"; exit 5; }
      # abort the workload only after TWO start failures (first run: one failure after a valid-but-
      # rejected attempt aborted pagerank, 2026-11-04)
      [ $rc = 4 ] && NFAIL=$((NFAIL + 1))
      if [ $NFAIL -ge 2 ]; then echo "could not start twice ($FAM)" > "$RAW/$WL/ABORTED"; break; fi
      sleep 20
    done
  done
done
dlog "campaign finished"
