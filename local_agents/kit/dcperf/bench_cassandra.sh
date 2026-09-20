#!/usr/bin/env bash
# bench_cassandra.sh — realistic-dataset Cassandra module for run_dcperf_profile.sh (2026-09-20).
#
# SERVER: a standalone Apache Cassandra 5.0 node (JDK 17) inside measured.slice on the measured
# cores, opening the YCSB store built by setup_cassandra_ycsb.sh (RECORDS x 1 KB rows, settled).
# CLIENT: YCSB 0.17 (the version DaCapo bundles) on the HOUSEKEEPING cores, closed loop,
# CoreWorkload A (50 % read / 50 % update, zipfian) by default -- the same workload definition
# as the DaCapo benchmark, at 2 000x its row count and with the client outside the fence.
#
# Steady state: node up (nodetool status UN) -> client starts -> CAS_WARMUP_S -> fence busy
# check -> capture. The client outlives the capture by 60 s; its final YCSB summary (overall
# throughput, per-operation p95/p99) is the receipt, parsed into cassandra_receipt.json.
INFRA="${REALDATA_INFRA:-$HOME/realdata-infra}"
CAS_HOME="$INFRA/cassandra"; YCSB_HOME="$INFRA/ycsb"; CAS_DS="$INFRA/datasets/cassandra-ycsb"
CAS_JAVA_HOME="${CAS_JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"
YCSB_JAVA_HOME="${YCSB_JAVA_HOME:-/usr/lib/jvm/java-21-openjdk-amd64}"
CAS_HEAP="${CAS_HEAP:-8G}"; CAS_NEW="${CAS_NEW:-2G}"
CAS_WORKLOAD="${CAS_WORKLOAD:-workloada}"
CAS_THREADS="${CAS_THREADS:-24}"
CAS_WARMUP_S="${CAS_WARMUP_S:-120}"
CAS_MIN_CORES="${CAS_MIN_CORES:-1}"

bench_preflight(){
  [ -x "$CAS_HOME/bin/cassandra" ] || { dlog "cassandra not installed at $CAS_HOME"; return 1; }
  [ -f "$CAS_DS/SETUP_DONE" ] || { dlog "store not built: run setup_cassandra_ycsb.sh"; return 1; }
  [ -x "$CAS_JAVA_HOME/bin/java" ] || { dlog "JDK 17 missing at $CAS_JAVA_HOME"; return 1; }
  [ -f "$YCSB_HOME/bin/ycsb.sh" ] || { dlog "YCSB missing at $YCSB_HOME"; return 1; }
  pgrep -f "$CAS_HOME" >/dev/null && { dlog "a cassandra process from $CAS_HOME is already running"; return 1; }
  CAS_RECORDS=$(sed -nE 's/.*records=([0-9]+).*/\1/p' "$CAS_DS/SETUP_DONE")
  dlog "cassandra preflight OK ($(cat "$CAS_DS/SETUP_DONE" | cut -c1-80); $CAS_WORKLOAD, $CAS_THREADS client threads)"
}

bench_start(){ # $1 OUT, $2 UNIT
  local OUT="$1" UNIT="$2" CG="measured.slice/$2.scope" i
  local dur=$((CAS_WARMUP_S + CAPTURE_S + 60))
  sudo systemctl stop "$UNIT.scope" 2>/dev/null; sudo systemctl reset-failed "$UNIT.scope" 2>/dev/null
  echo "{\"server\":\"apache-cassandra-5.0.9\",\"jdk\":\"17\",\"heap\":\"$CAS_HEAP\",\"records\":$CAS_RECORDS,\"row_bytes\":1000,\"client\":{\"tool\":\"YCSB 0.17\",\"workload\":\"$CAS_WORKLOAD\",\"threads\":$CAS_THREADS,\"duration_s\":$dur},\"warmup_s\":$CAS_WARMUP_S}" > "$OUT/.load_json"
  ( sudo systemd-run --collect --scope --slice=measured.slice --unit="$UNIT" \
      -E JAVA_HOME="$CAS_JAVA_HOME" -E CASSANDRA_HOME="$CAS_HOME" -E CASSANDRA_CONF="$CAS_HOME/conf" \
      -E MAX_HEAP_SIZE="$CAS_HEAP" -E HEAP_NEWSIZE="$CAS_NEW" -E PATH="$CAS_JAVA_HOME/bin:/usr/bin:/bin" \
      -- taskset -c "$CPUS_MEASURED" "$CAS_HOME/bin/cassandra" -f -R ) > "$OUT/cassandra.log" 2>&1 &
  CAS_RUN_PID=$!
  dlog "cassandra launched (pid $CAS_RUN_PID)"
  for i in $(seq 1 120); do [ -d "/sys/fs/cgroup/$CG" ] && break; sleep 1; done
  [ -d "/sys/fs/cgroup/$CG" ] || { dlog "cassandra scope never appeared"; return 1; }
  echo "$CG" > "$OUT/.server_cg"
  for i in $(seq 1 240); do
    JAVA_HOME="$CAS_JAVA_HOME" "$CAS_HOME/bin/nodetool" -h 127.0.0.1 status 2>/dev/null | grep -q '^UN' && break
    kill -0 "$CAS_RUN_PID" 2>/dev/null || { dlog "cassandra exited during start-up (see $OUT/cassandra.log)"; return 1; }
    sleep 2
  done
  JAVA_HOME="$CAS_JAVA_HOME" "$CAS_HOME/bin/nodetool" -h 127.0.0.1 status 2>/dev/null | grep -q '^UN' || { dlog "node never reached UN"; return 1; }
  sleep 5
  ( cd "$YCSB_HOME" && taskset -c "$CPUS_HOUSE" env JAVA_HOME="$YCSB_JAVA_HOME" PATH="$YCSB_JAVA_HOME/bin:$PATH" \
      bash bin/ycsb.sh run cassandra-cql -P "workloads/$CAS_WORKLOAD" -p recordcount="$CAS_RECORDS" \
      -p operationcount=2000000000 -p maxexecutiontime="$dur" -p hosts=127.0.0.1 \
      -p cassandra.readconsistencylevel=ONE -p cassandra.writeconsistencylevel=ONE \
      -threads "$CAS_THREADS" -s ) > "$OUT/ycsb_run.log" 2>&1 &
  CLIENT_PID=$!
  dlog "YCSB client launched (pid $CLIENT_PID, $CAS_WORKLOAD, $CAS_THREADS threads, ${dur}s); warm-up ${CAS_WARMUP_S}s"
  sleep "$CAS_WARMUP_S"
  kill -0 "$CLIENT_PID" 2>/dev/null || { dlog "client died during warm-up (see $OUT/ycsb_run.log)"; return 1; }
  [ -d "/sys/fs/cgroup/$CG" ] || { dlog "cassandra died during warm-up"; return 1; }
  local u0 u1; u0=$(awk '/usage_usec/{print $2}' "/sys/fs/cgroup/$CG/cpu.stat"); sleep 10
  u1=$(awk '/usage_usec/{print $2}' "/sys/fs/cgroup/$CG/cpu.stat")
  local cc=$(( (u1 - u0) / 100000 ))
  [ "$cc" -ge $((CAS_MIN_CORES * 100)) ] || { dlog "server fence only $((cc/100)).$((cc%100)) cores busy after warm-up"; return 1; }
  dlog "server busy ~$((cc/100)).$((cc%100)) cores; client: $(grep -oE '[0-9.]+ current ops/sec' "$OUT/ycsb_run.log" | tail -1)"
  return 0
}

bench_stop(){ # $1 OUT, $2 UNIT
  local OUT="$1" UNIT="$2" i
  # let YCSB reach its own end (maxexecutiontime) so it prints the summary = the receipt
  for i in $(seq 1 120); do kill -0 "${CLIENT_PID:-0}" 2>/dev/null || break; sleep 1; done
  kill -TERM "${CLIENT_PID:-0}" 2>/dev/null
  python3 - "$OUT/ycsb_run.log" "$OUT/cassandra_receipt.json" <<'PY'
import re, sys, json
txt = open(sys.argv[1], errors="replace").read()
rec = {}
for m in re.finditer(r'^\[(OVERALL|READ|UPDATE|INSERT|SCAN|READ-MODIFY-WRITE)\], ([^,]+), ([0-9.]+)', txt, re.M):
    rec.setdefault(m.group(1), {})[m.group(2).strip()] = float(m.group(3))
rates = [float(x) for x in re.findall(r'([0-9.]+) current ops/sec', txt)]
rec["status_lines"] = {"n": len(rates), "median_ops_per_s": sorted(rates)[len(rates)//2] if rates else None,
                       "last_10_mean_ops_per_s": sum(rates[-10:])/len(rates[-10:]) if rates else None}
json.dump(rec, open(sys.argv[2], "w"), indent=1)
PY
  JAVA_HOME="$CAS_JAVA_HOME" "$CAS_HOME/bin/nodetool" -h 127.0.0.1 drain >/dev/null 2>&1 || true
  sudo systemctl stop "$UNIT.scope" 2>/dev/null
  [ -n "${CAS_RUN_PID:-}" ] && kill -TERM "$CAS_RUN_PID" 2>/dev/null
  for i in $(seq 1 60); do pgrep -f "$CAS_HOME" >/dev/null || break; sleep 1; done
  pgrep -f "$CAS_HOME" >/dev/null && sudo pkill -f "$CAS_HOME" 2>/dev/null
  sleep 3
}
