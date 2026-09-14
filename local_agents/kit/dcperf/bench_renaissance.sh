#!/usr/bin/env bash
# bench_renaissance.sh — Renaissance suite module (single JAR, single JVM per benchmark).
#   SUITE=renaissance BENCH=renaissance WORKLOAD=finagle-http ./run_dcperf_profile.sh
# `-t SECONDS` makes Renaissance repeat the operation for at least that long, so the run is
# sized to outlast the capture window; results (per-operation times) land in renaissance.csv.
source "$KITD/bench_jvm_common.sh"
RJAR="${RENAISSANCE_JAR:-$HOME/jvmbench-infra/renaissance-gpl-0.16.1.jar}"
RWL="${WORKLOAD:?renaissance benchmark id (finagle-http|finagle-chirper|page-rank|naive-bayes|neo4j-analytics ...)}"
R_SECONDS="${R_SECONDS:-$((CAPTURE_S + JVM_WARMUP_S + 90))}"

bench_preflight(){
  [ -f "$RJAR" ] || { dlog "renaissance jar missing: $RJAR"; return 1; }
  "$JAVA" -jar "$RJAR" --list 2>/dev/null | grep -q "^${RWL}\b" \
    || { dlog "renaissance has no benchmark '$RWL' (see: java -jar $RJAR --list)"; return 1; }
  dlog "renaissance preflight OK ($RWL, run >= ${R_SECONDS}s, $("$JAVA" -version 2>&1 | head -1))"
}
bench_start(){ # $1 OUT, $2 UNIT
  echo "{\"jar\":\"$(basename "$RJAR")\",\"benchmark\":\"$RWL\",\"run_seconds\":$R_SECONDS,\"java\":\"$("$JAVA" -version 2>&1 | head -1 | tr -d '"')\"}" > "$1/.load_json"
  jvm_launch "$1" "$2" renaissance.log -jar "$RJAR" -t "$R_SECONDS" --csv "$1/renaissance.csv" "$RWL"
  jvm_wait_steady "$1" "$2"
}
bench_stop(){ jvm_stop "$1" "$2"; }
