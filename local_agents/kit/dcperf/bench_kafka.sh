#!/usr/bin/env bash
# bench_kafka.sh — realistic-dataset Kafka module for run_dcperf_profile.sh (2026-09-21).
#
# SERVER: a standalone Apache Kafka 4.x broker (KRaft, JDK 21) inside measured.slice on the
# measured cores, holding the pre-filled topic (setup_kafka.sh: 20 M x 1 KB records, ~20 GB).
# CLIENTS on the HOUSEKEEPING cores, sustained for the whole capture: one producer at a fixed
# rate (KAFKA_PRODUCE_RPS records/s of 1 KB) and one consumer group reading the topic from its
# beginning at full speed -- so the broker serves reads from the deep log, not from what it
# just wrote, while ingesting. This replaces DaCapo kafka's 1 M-message bursts on an empty
# broker with the produce+consume steady state a broker actually runs in.
#
# Receipt: the producer's and consumer's own perf-test summaries (records/s, MB/s, latency
# percentiles) parsed into kafka_receipt.json.
INFRA="${REALDATA_INFRA:-$HOME/realdata-infra}"
KAFKA_HOME="$INFRA/kafka"; KAFKA_DS="$INFRA/datasets/kafka"
KAFKA_JAVA_HOME="${KAFKA_JAVA_HOME:-/usr/lib/jvm/java-21-openjdk-amd64}"
KAFKA_CONF="$KAFKA_HOME/config/infersuite-server.properties"
KAFKA_TOPIC="${KAFKA_TOPIC:-realdata}"
KAFKA_PRODUCERS="${KAFKA_PRODUCERS:-3}"              # producer processes, each at KAFKA_PRODUCE_RPS
KAFKA_PRODUCE_RPS="${KAFKA_PRODUCE_RPS:-40000}"      # 3 x 40 k x 1 KB = ~120 MB/s ingest into a
                                                     # 21 GB retention window (setup_kafka.sh)
KAFKA_CONSUMERS="${KAFKA_CONSUMERS:-6}"              # consumer groups reading the 20 GB backlog
KAFKA_WARMUP_S="${KAFKA_WARMUP_S:-90}"
KAFKA_MIN_CCORES="${KAFKA_MIN_CCORES:-50}"           # steady-state floor in centi-cores: a broker is
                                                     # I/O-bound by design (zero-copy fetches), 0.5 core
                                                     # of request handling is a running broker
# First smoke (2026-09-21): 1 producer at 50 k/s + 2 consumers with a mis-parsed --from-latest
# left the consumers tailing the head at the produce rate and the broker at 0.12 cores.

bench_preflight(){
  [ -x "$KAFKA_HOME/bin/kafka-server-start.sh" ] || { dlog "kafka not installed at $KAFKA_HOME"; return 1; }
  [ -f "$KAFKA_DS/SETUP_DONE" ] || { dlog "log not built: run setup_kafka.sh"; return 1; }
  [ -f "$KAFKA_CONF" ] || { dlog "broker config missing"; return 1; }
  pgrep -f "$KAFKA_HOME" >/dev/null && { dlog "a kafka process from $KAFKA_HOME is already running"; return 1; }
  dlog "kafka preflight OK ($(cat "$KAFKA_DS/SETUP_DONE" | cut -c1-90); produce ${KAFKA_PRODUCE_RPS}/s, $KAFKA_CONSUMERS consumers)"
}

bench_start(){ # $1 OUT, $2 UNIT
  local OUT="$1" UNIT="$2" CG="measured.slice/$2.scope" i
  local dur=$((KAFKA_WARMUP_S + CAPTURE_S + 60))
  sudo systemctl stop "$UNIT.scope" 2>/dev/null; sudo systemctl reset-failed "$UNIT.scope" 2>/dev/null
  echo "{\"server\":\"apache-kafka-4.3.1 (KRaft)\",\"jdk\":\"21\",\"heap\":\"6g\",\"prefill\":\"$(cat "$KAFKA_DS/SETUP_DONE" | cut -c1-80)\",\"client\":{\"producers\":$KAFKA_PRODUCERS,\"producer_rps_each\":$KAFKA_PRODUCE_RPS,\"record_bytes\":1024,\"consumers_from_earliest\":$KAFKA_CONSUMERS,\"duration_s\":$dur},\"warmup_s\":$KAFKA_WARMUP_S}" > "$OUT/.load_json"
  ( sudo systemd-run --collect --scope --slice=measured.slice --unit="$UNIT" \
      -E JAVA_HOME="$KAFKA_JAVA_HOME" -E KAFKA_HEAP_OPTS="-Xms6g -Xmx6g" -E PATH="$KAFKA_JAVA_HOME/bin:/usr/bin:/bin" -E LOG_DIR="$OUT" \
      -- taskset -c "$CPUS_MEASURED" "$KAFKA_HOME/bin/kafka-server-start.sh" "$KAFKA_CONF" ) > "$OUT/kafka.log" 2>&1 &
  KAFKA_RUN_PID=$!
  dlog "kafka broker launched (pid $KAFKA_RUN_PID)"
  for i in $(seq 1 120); do [ -d "/sys/fs/cgroup/$CG" ] && break; sleep 1; done
  [ -d "/sys/fs/cgroup/$CG" ] || { dlog "kafka scope never appeared"; return 1; }
  echo "$CG" > "$OUT/.server_cg"
  for i in $(seq 1 90); do
    JAVA_HOME="$KAFKA_JAVA_HOME" "$KAFKA_HOME/bin/kafka-broker-api-versions.sh" --bootstrap-server 127.0.0.1:9092 >/dev/null 2>&1 && break
    kill -0 "$KAFKA_RUN_PID" 2>/dev/null || { dlog "broker exited during start-up (see $OUT/kafka.log)"; return 1; }
    sleep 2
  done
  sleep 3
  # consumers: fresh group each pass, from the beginning of the 20 GB log, no message cap, timed
  local c; CONSUMER_PIDS=""; PRODUCER_PIDS=""
  printf 'auto.offset.reset=earliest\nfetch.min.bytes=1\nmax.partition.fetch.bytes=4194304\n' > "$OUT/consumer.properties"
  for c in $(seq 1 "$KAFKA_CONSUMERS"); do
    # a fresh group per pass and consumer, no --from-latest: the group has no committed offset,
    # so auto.offset.reset=earliest starts it at the beginning of the pre-filled log
    ( taskset -c "$CPUS_HOUSE" env JAVA_HOME="$KAFKA_JAVA_HOME" "$KAFKA_HOME/bin/kafka-consumer-perf-test.sh" \
        --bootstrap-server 127.0.0.1:9092 --topic "$KAFKA_TOPIC" --group "realdata-$UNIT-$c" \
        --messages 2000000000 --timeout $((dur * 1000)) --show-detailed-stats --reporting-interval 5000 \
        --consumer.config "$OUT/consumer.properties" ) > "$OUT/consumer_$c.log" 2>&1 &
    CONSUMER_PIDS="$CONSUMER_PIDS $!"
  done
  for c in $(seq 1 "$KAFKA_PRODUCERS"); do
    ( taskset -c "$CPUS_HOUSE" env JAVA_HOME="$KAFKA_JAVA_HOME" "$KAFKA_HOME/bin/kafka-producer-perf-test.sh" --topic "$KAFKA_TOPIC" \
        --num-records $((KAFKA_PRODUCE_RPS * dur)) --record-size 1024 --throughput "$KAFKA_PRODUCE_RPS" \
        --producer-props bootstrap.servers=127.0.0.1:9092 acks=1 linger.ms=5 batch.size=131072 compression.type=none \
      ) > "$OUT/producer_$c.log" 2>&1 &
    PRODUCER_PIDS="$PRODUCER_PIDS $!"
  done
  PRODUCER_PID=${PRODUCER_PIDS## }; PRODUCER_PID=${PRODUCER_PID%% *}
  dlog "clients launched: $KAFKA_PRODUCERS producers x ${KAFKA_PRODUCE_RPS} rec/s, $KAFKA_CONSUMERS consumers from earliest; warm-up ${KAFKA_WARMUP_S}s"
  sleep "$KAFKA_WARMUP_S"
  kill -0 "$PRODUCER_PID" 2>/dev/null || { dlog "producer died during warm-up (see $OUT/producer.log)"; return 1; }
  [ -d "/sys/fs/cgroup/$CG" ] || { dlog "broker died during warm-up"; return 1; }
  local u0 u1; u0=$(awk '/usage_usec/{print $2}' "/sys/fs/cgroup/$CG/cpu.stat"); sleep 10
  u1=$(awk '/usage_usec/{print $2}' "/sys/fs/cgroup/$CG/cpu.stat")
  local cc=$(( (u1 - u0) / 100000 ))
  [ "$cc" -ge "$KAFKA_MIN_CCORES" ] || { dlog "broker fence only $((cc/100)).$((cc%100)) cores busy after warm-up"; return 1; }
  dlog "broker busy ~$((cc/100)).$((cc%100)) cores; producer 1: $(grep -oE '[0-9.]+ records/sec \([0-9.]+ MB/sec\)' "$OUT/producer_1.log" | tail -1); consumer 1: $(tail -1 "$OUT/consumer_1.log" | cut -d, -f4 | tr -d ' ') MB/s"
  return 0
}

bench_stop(){ # $1 OUT, $2 UNIT
  local OUT="$1" UNIT="$2" i
  for i in $(seq 1 90); do kill -0 "${PRODUCER_PID:-0}" 2>/dev/null || break; sleep 1; done
  for p in $PRODUCER_PIDS $CONSUMER_PIDS; do kill -TERM "$p" 2>/dev/null; done; sleep 3
  python3 - "$OUT" <<'PY'
import re, sys, json, glob
out = sys.argv[1]; rec = {}
p = "\n".join(open(f, errors="replace").read() for f in sorted(glob.glob(f"{out}/producer_*.log")))
m = re.findall(r'([0-9.]+) records sent, ([0-9.]+) records/sec \(([0-9.]+) MB/sec\), ([0-9.]+) ms avg latency, ([0-9.]+) ms max latency(?:, ([0-9]+) ms 50th, ([0-9]+) ms 95th, ([0-9]+) ms 99th, ([0-9]+) ms 99.9th)?', p)
if m:
    last = m[-1]
    finals = [x for x in m if x[5]]     # the summary line of each producer carries percentiles
    rec["producers"] = len(finals)
    rec["producer_total_records_per_s"] = round(sum(float(x[1]) for x in finals), 1)
    rec["producer_final"] = {"records": float(last[0]), "records_per_s": float(last[1]), "MB_per_s": float(last[2]),
                             "avg_ms": float(last[3]), "max_ms": float(last[4]),
                             "p50_ms": last[5] and int(last[5]), "p95_ms": last[6] and int(last[6]), "p99_ms": last[7] and int(last[7])}
    rates = [float(x[1]) for x in m[:-1]] or [float(last[1])]
    rec["producer_status"] = {"n": len(rates), "median_records_per_s": sorted(rates)[len(rates)//2]}
cons = {}
for f in sorted(glob.glob(f"{out}/consumer_*.log")):
    lines = [l for l in open(f, errors="replace").read().splitlines() if re.match(r'^\d{4}-', l)]
    if lines:
        parts = [x.strip() for x in lines[-1].split(",")]
        cons[f.split("/")[-1]] = {"MB_consumed": float(parts[2]), "MB_per_s_last": float(parts[3]),
                                  "msgs_per_s_last": float(parts[5]), "intervals": len(lines)}
rec["consumer_total_MB_per_s_last"] = round(sum(c["MB_per_s_last"] for c in cons.values()), 1)
rec["consumers"] = cons
json.dump(rec, open(f"{out}/kafka_receipt.json", "w"), indent=1)
PY
  sudo systemctl stop "$UNIT.scope" 2>/dev/null
  [ -n "${KAFKA_RUN_PID:-}" ] && kill -TERM "$KAFKA_RUN_PID" 2>/dev/null
  for i in $(seq 1 60); do pgrep -f "$KAFKA_HOME" >/dev/null || break; sleep 1; done
  pgrep -f "$KAFKA_HOME" >/dev/null && sudo pkill -f "$KAFKA_HOME" 2>/dev/null
  sleep 3
}
