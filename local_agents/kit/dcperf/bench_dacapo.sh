#!/usr/bin/env bash
# bench_dacapo.sh — DaCapo Chopin module (single JAR, single JVM per benchmark).
#   SUITE=dacapo BENCH=dacapo WORKLOAD=cassandra ./run_dcperf_profile.sh
# DaCapo runs `-n N` iterations of the benchmark; N is set high enough to outlast the capture
# window and the scope is stopped afterwards. `--no-validation` skips the post-run output
# check (irrelevant to profiling, and it fails spuriously on some JDKs).
source "$KITD/bench_jvm_common.sh"
DJAR="${DACAPO_JAR:-$HOME/jvmbench-infra/dacapo-23.11-MR2-chopin.jar}"
DWL="${WORKLOAD:?dacapo benchmark id (cassandra|tomcat|kafka ...)}"
D_ITERS="${D_ITERS:-40}"
D_SIZE="${D_SIZE:-default}"

bench_preflight(){
  [ -f "$DJAR" ] || { dlog "dacapo jar missing: $DJAR"; return 1; }
  dlog "dacapo preflight OK ($DWL, -n $D_ITERS -s $D_SIZE, $("$JAVA" -version 2>&1 | head -1))"
}
bench_start(){ # $1 OUT, $2 UNIT
  echo "{\"jar\":\"$(basename "$DJAR")\",\"benchmark\":\"$DWL\",\"iterations\":$D_ITERS,\"size\":\"$D_SIZE\",\"java\":\"$("$JAVA" -version 2>&1 | head -1 | tr -d '"')\"}" > "$1/.load_json"
  jvm_launch "$1" "$2" dacapo.log -jar "$DJAR" -n "$D_ITERS" -s "$D_SIZE" --no-validation "$DWL"
  jvm_wait_steady "$1" "$2"
}
bench_stop(){ jvm_stop "$1" "$2"; }
