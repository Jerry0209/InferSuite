#!/usr/bin/env bash
# setup_kafka.sh — ONE-TIME build of the realistic Kafka workload's log: a standalone Apache
# Kafka 4.x broker (KRaft combined mode, JDK 21) with a 12-partition topic pre-filled with
# MESSAGES x 1 KB records (default 20 M = ~20 GB of log on disk, far beyond any cache and in
# the regime where a broker serves consumers from its own log rather than from the page cache
# of what it just wrote). Nothing here is measured.
#   MESSAGES=20000000 INFRA=~/realdata-infra bash local_agents/kit/dcperf/setup_kafka.sh
set -euo pipefail
INFRA="${INFRA:-$HOME/realdata-infra}"
KAFKA="$INFRA/kafka"; DS="$INFRA/datasets/kafka"
MESSAGES="${MESSAGES:-20000000}"; RECORD_BYTES="${RECORD_BYTES:-1024}"; PARTITIONS="${PARTITIONS:-12}"
TOPIC="${TOPIC:-realdata}"
CPUS_MEASURED="${CPUS_MEASURED:-4-11}"; CPUS_HOUSE="${CPUS_HOUSE:-0-3,12-15}"
export JAVA_HOME="${KAFKA_JAVA_HOME:-/usr/lib/jvm/java-21-openjdk-amd64}"; export PATH="$JAVA_HOME/bin:$PATH"
export KAFKA_HEAP_OPTS="${KAFKA_HEAP_OPTS:--Xms6g -Xmx6g}"
mkdir -p "$DS" "$KAFKA/data"
log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$INFRA/logs/setup_kafka.log"; }
CONF="$KAFKA/config/infersuite-server.properties"
if [ ! -f "$CONF" ]; then
  sed -e "s|^log.dirs=.*|log.dirs=$KAFKA/data/kraft-combined-logs|" \
      -e "s|^num.partitions=.*|num.partitions=$PARTITIONS|" \
      -e "s|^listeners=.*|listeners=PLAINTEXT://127.0.0.1:9092,CONTROLLER://127.0.0.1:9093|" \
      -e "s|^controller.quorum.bootstrap.servers=.*|controller.quorum.bootstrap.servers=127.0.0.1:9093|" \
      "$KAFKA/config/server.properties" > "$CONF"
  # keep the broker honest about disk: no deletion during the study, segments of 1 GB
  printf '\nlog.retention.hours=-1\nlog.segment.bytes=1073741824\nnum.io.threads=8\nnum.network.threads=4\n' >> "$CONF"
  log "broker config written ($CONF)"
fi
if [ -f "$DS/SETUP_DONE" ]; then log "already built ($(cat "$DS/SETUP_DONE"))"; exit 0; fi
if [ ! -f "$KAFKA/data/kraft-combined-logs/meta.properties" ]; then
  UUID=$("$KAFKA/bin/kafka-storage.sh" random-uuid)
  "$KAFKA/bin/kafka-storage.sh" format -t "$UUID" -c "$CONF" --standalone >> "$INFRA/logs/setup_kafka.log" 2>&1
  log "storage formatted (cluster $UUID)"
fi
start_broker(){
  sudo systemctl stop realdata-kafka-setup.scope 2>/dev/null || true; sudo systemctl reset-failed realdata-kafka-setup.scope 2>/dev/null || true
  ( sudo systemd-run --collect --scope --slice=measured.slice --unit=realdata-kafka-setup \
      -E JAVA_HOME="$JAVA_HOME" -E KAFKA_HEAP_OPTS="$KAFKA_HEAP_OPTS" -E PATH="$JAVA_HOME/bin:/usr/bin:/bin" \
      -E LOG_DIR="$KAFKA/logs" \
      -- taskset -c "$CPUS_MEASURED" "$KAFKA/bin/kafka-server-start.sh" "$CONF" ) > "$INFRA/logs/kafka_setup_broker.log" 2>&1 &
  BROKER_PID=$!
  local i; for i in $(seq 1 90); do "$KAFKA/bin/kafka-broker-api-versions.sh" --bootstrap-server 127.0.0.1:9092 >/dev/null 2>&1 && break; sleep 2; done
  "$KAFKA/bin/kafka-broker-api-versions.sh" --bootstrap-server 127.0.0.1:9092 >/dev/null 2>&1 || { log "broker did not come up"; return 1; }
  log "broker up (pid $BROKER_PID)"
}
stop_broker(){ sudo systemctl stop realdata-kafka-setup.scope 2>/dev/null || true; kill -TERM "$BROKER_PID" 2>/dev/null || true
  local i; for i in $(seq 1 60); do pgrep -f "$KAFKA/bin" >/dev/null || break; sleep 1; done; }
start_broker
"$KAFKA/bin/kafka-topics.sh" --bootstrap-server 127.0.0.1:9092 --create --if-not-exists --topic "$TOPIC" \
  --partitions "$PARTITIONS" --replication-factor 1 >> "$INFRA/logs/setup_kafka.log" 2>&1
log "topic '$TOPIC' ($PARTITIONS partitions)"
log "pre-filling: $MESSAGES x $RECORD_BYTES B (producer on the housekeeping cores)"
( taskset -c "$CPUS_HOUSE" "$KAFKA/bin/kafka-producer-perf-test.sh" --topic "$TOPIC" --num-records "$MESSAGES" \
    --record-size "$RECORD_BYTES" --throughput -1 --producer-props bootstrap.servers=127.0.0.1:9092 acks=1 \
    linger.ms=5 batch.size=131072 compression.type=none buffer.memory=134217728 ) > "$INFRA/logs/kafka_prefill.log" 2>&1 \
  || { log "pre-fill FAILED"; stop_broker; exit 1; }
log "pre-fill done: $(tail -1 "$INFRA/logs/kafka_prefill.log" | cut -c1-150)"
sleep 5; stop_broker
echo "messages=$MESSAGES record_bytes=$RECORD_BYTES partitions=$PARTITIONS topic=$TOPIC log=$(du -sh "$KAFKA/data" | cut -f1) built=$(date -Is)" > "$DS/SETUP_DONE"
log "SETUP DONE: $(cat "$DS/SETUP_DONE")"
