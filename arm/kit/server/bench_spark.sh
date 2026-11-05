#!/usr/bin/env bash
# ARM port of local_agents/kit/dcperf/bench_spark.sh (dcperf-arm): measured.slice -> $MSLICE + $SCOPE_PROPS (AllowedCPUs=8-15, mems 0), JDK -amd64 -> $(dpkg --print-architecture), machine-wide pkill -> kill_desc (own process tree only).
# bench_spark.sh — realistic-input Spark jobs for run_dcperf_profile.sh (2026-09-21).
# WORKLOAD=pagerank-livejournal  Spark PageRank on the SNAP LiveJournal edge list (69 M edges)
# WORKLOAD=naivebayes-rcv1       Spark ML Naive Bayes on RCV1-v2 (518 k documents)
# One JVM (spark-shell, local[8]) is the whole workload = one fence, exactly like the Renaissance
# benchmarks these replace; the job loops its computation until the capture is over.
# Steady state via the shared JVM helpers (10 s moving mean >= 1 core, then the JIT hold).
source "$KITD/bench_jvm_common.sh"
INFRA="${REALDATA_INFRA:-$HOME/realdata-infra}"
SPARK_HOME="$INFRA/spark"; JAVA="${SPARK_JAVA:-/usr/lib/jvm/java-21-openjdk-$(dpkg --print-architecture)/bin/java}"
SPARK_DRIVER_MEM="${SPARK_DRIVER_MEM:-24g}"
case "$WL" in
  pagerank-livejournal) RD_SCRIPT="$KITD/spark/pagerank.scala"; RD_INPUT="$INFRA/datasets/livejournal/soc-LiveJournal1.txt";;
  naivebayes-rcv1)      RD_SCRIPT="$KITD/spark/naivebayes.scala"; RD_INPUT="$INFRA/datasets/rcv1/rcv1_test.multiclass";;
  *) echo "unknown spark WORKLOAD '$WL'"; exit 1;;
esac

bench_preflight(){
  [ -x "$SPARK_HOME/bin/spark-shell" ] || { dlog "spark not installed at $SPARK_HOME"; return 1; }
  [ -s "$RD_INPUT" ] || { dlog "input missing: $RD_INPUT"; return 1; }
  dlog "spark preflight OK ($WL: $(du -h "$RD_INPUT" | cut -f1) input, driver $SPARK_DRIVER_MEM, local[8])"
}
bench_start(){ # $1 OUT, $2 UNIT
  local OUT="$1" UNIT="$2"
  local secs=$((JVM_WARMUP_S + CAPTURE_S + 600))
  echo "{\"engine\":\"spark-3.5.9 local[8]\",\"script\":\"$(basename "$RD_SCRIPT")\",\"input\":\"$(basename "$RD_INPUT")\",\"input_bytes\":$(stat -c %s "$RD_INPUT"),\"driver_mem\":\"$SPARK_DRIVER_MEM\",\"iters\":\"${RD_ITERS:-3}\"}" > "$OUT/.load_json"
  # ARM port: spark-shell sometimes exits within ~1 s of launch with no output at all (2 of 4
  # launches on 2026-11-04, both before the JVM printed anything; the next launch always worked).
  # A launch that dies before the input-loaded marker and within 30 s is relaunched, up to 3
  # tries; nothing is being counted yet (the capture starts after load + the JVM rule).
  local try t0
  for try in 1 2 3; do
  t0=$SECONDS
  sudo systemctl stop "$UNIT.scope" 2>/dev/null; sudo systemctl reset-failed "$UNIT.scope" 2>/dev/null
  ( cd "$OUT" && { sudo systemd-run --collect --scope --slice="$MSLICE" $SCOPE_PROPS --unit="$UNIT" \
      -E JAVA_HOME="$(dirname "$(dirname "$JAVA")")" -E SPARK_HOME="$SPARK_HOME" -E RD_EDGES="$RD_INPUT" -E RD_LIBSVM="$RD_INPUT" \
      -E RD_ITERS="${RD_ITERS:-3}" -E RD_SECONDS="$secs" -E SPARK_LOCAL_DIRS="$OUT/spark-tmp" -E PATH="$(dirname "$JAVA"):/usr/bin:/bin" \
      -- taskset -c "$CPUS_MEASURED" "$SPARK_HOME/bin/spark-shell" --master "local[8]" --driver-memory "$SPARK_DRIVER_MEM" \
         --conf spark.ui.enabled=false --conf spark.driver.host=127.0.0.1 --conf spark.sql.shuffle.partitions=64 \
         --conf spark.default.parallelism=64 -i "$RD_SCRIPT"; echo "[launch] spark-shell exit status $?"; } ) >> "$OUT/spark.log" 2>&1 &
  JVM_RUN_PID=$!
  dlog "spark-shell launched (pid $JVM_RUN_PID): $(basename "$RD_SCRIPT") on $(basename "$RD_INPUT") for ${secs}s"
  # the input load (parse + shuffle + cache) is a one-off stage that must not be what the
  # capture sees: wait for the script's "loaded" marker (up to 15 min), then the JVM rule
  local i
  for i in $(seq 1 900); do
    tr '\r' '\n' < "$OUT/spark.log" 2>/dev/null | grep -qE '\[rd\] (graph|corpus) loaded' && break
    kill -0 "$JVM_RUN_PID" 2>/dev/null || break
    sleep 1
  done
  tr '\r' '\n' < "$OUT/spark.log" | grep -qE '\[rd\] (graph|corpus) loaded' && break
  if kill -0 "$JVM_RUN_PID" 2>/dev/null || [ $((SECONDS - t0)) -ge 30 ]; then break; fi
  dlog "spark-shell died $((SECONDS - t0)) s after launch try $try ($(grep -o 'exit status [0-9]*' "$OUT/spark.log" | tail -1)); relaunching"
  sudo systemctl stop "$UNIT.scope" 2>/dev/null; sudo systemctl reset-failed "$UNIT.scope" 2>/dev/null; sleep 2
  done
  tr '\r' '\n' < "$OUT/spark.log" | grep -qE '\[rd\] (graph|corpus) loaded' || { dlog "input never finished loading"; return 1; }
  dlog "input loaded: $(tr '\r' '\n' < "$OUT/spark.log" | grep -E '\[rd\] (graph|corpus) loaded' | tail -1 | cut -c1-100)"
  jvm_wait_steady "$OUT" "$UNIT"
}
bench_stop(){ jvm_stop "$1" "$2"; tr '\r' '\n' < "$1/spark.log" | grep -E '\[rd\]' > "$1/spark_receipt.txt" 2>/dev/null; sudo systemctl stop "$2.scope" 2>/dev/null; }
