#!/usr/bin/env bash
# bench_neo4j.sh — realistic-dataset Neo4j module for run_dcperf_profile.sh (2026-09-20).
#
# The SERVER (Neo4j 5.26 community, standalone, JDK 21) runs inside measured.slice on the
# measured cores with the SNAP LiveJournal follow graph (4.85 M users, 69 M edges) as its
# database; the CLIENT (neo4j_client.py, closed loop, short/long/mutating Cypher mix) runs on
# the HOUSEKEEPING cores -- the FeedSim arrangement, and the one the DaCapo/Renaissance
# benchmarks could not offer (their clients are in-process). Built with
# setup_neo4j_livejournal.sh once; every pass starts a fresh server on the same store.
#
# Steady state: server up (bolt answers) -> client starts -> NEO_WARMUP_S of page-cache and
# JIT warm-up -> the fence must be busy (>= NEO_MIN_CORES over the last 10 s) -> capture. The
# client outlives the capture by 60 s and writes per-second throughput/latency; bench_stop
# summarises the capture window into neo4j_receipt.json (the workload's own receipt).
INFRA="${REALDATA_INFRA:-$HOME/realdata-infra}"
NEO_HOME="$INFRA/neo4j"
NEO_DB="${NEO_DB:-livejournal}"
NEO_JAVA_HOME="${NEO_JAVA_HOME:-/usr/lib/jvm/java-21-openjdk-amd64}"
NEO_DS="$INFRA/datasets/$NEO_DB"
CLIENT_PY="$INFRA/venv/bin/python"
NEO_WARMUP_S="${NEO_WARMUP_S:-150}"
NEO_MIN_CORES="${NEO_MIN_CORES:-1}"
CLIENT_PROCS="${CLIENT_PROCS:-5}"
CLIENT_SESSIONS="${CLIENT_SESSIONS:-5}"
# query mix: short (1-hop / 2-hop) : long (bounded shortest path / 3-hop reach) : mutating.
# 0.80/0.12/0.08 since 2026-09-20: with long at 0.03 the server cost 0.26 ms per request
# against the Python client's 0.6 ms and sat at 2.8 of 8 cores; the 3-hop class is where
# the server does real graph work per request
NEO_P_SHORT="${NEO_P_SHORT:-0.80}"
NEO_P_LONG="${NEO_P_LONG:-0.12}"

bench_preflight(){
  [ -x "$NEO_HOME/bin/neo4j" ] || { dlog "neo4j not installed at $NEO_HOME"; return 1; }
  [ -f "$NEO_DS/SETUP_DONE" ] || { dlog "database not built: run setup_neo4j_livejournal.sh"; return 1; }
  [ -d "$NEO_HOME/data/databases/$NEO_DB" ] || { dlog "store missing: $NEO_HOME/data/databases/$NEO_DB"; return 1; }
  "$CLIENT_PY" -c "import neo4j" 2>/dev/null || { dlog "client venv lacks the neo4j driver"; return 1; }
  pgrep -f "$NEO_HOME" >/dev/null && { dlog "a neo4j process from $NEO_HOME is already running"; return 1; }
  NEO_NODES=$(python3 -c "import json;print(json.load(open('$NEO_DS/dataset.json'))['max_id']+1)")
  dlog "neo4j preflight OK ($NEO_DB: $(python3 -c "import json;d=json.load(open('$NEO_DS/dataset.json'));print(d['nodes'],'users,',d['edges'],'edges')"), store $(du -sh "$NEO_HOME/data/databases/$NEO_DB" | cut -f1), client ${CLIENT_PROCS}x${CLIENT_SESSIONS} sessions)"
}

bench_start(){ # $1 OUT, $2 UNIT
  local OUT="$1" UNIT="$2" CG="measured.slice/$2.scope" i
  local dur=$((NEO_WARMUP_S + CAPTURE_S + 60))
  sudo systemctl stop "$UNIT.scope" 2>/dev/null; sudo systemctl reset-failed "$UNIT.scope" 2>/dev/null
  echo "{\"server\":\"neo4j-community-5.26.12\",\"database\":\"$NEO_DB\",\"dataset\":\"SNAP soc-LiveJournal1\",\"nodes\":$NEO_NODES,\"heap\":\"8g\",\"pagecache\":\"12g\",\"client\":{\"procs\":$CLIENT_PROCS,\"sessions\":$CLIENT_SESSIONS,\"mix\":\"short $NEO_P_SHORT / long $NEO_P_LONG / mut $(python3 -c "print(round(1-$NEO_P_SHORT-$NEO_P_LONG,2))")\",\"duration_s\":$dur},\"warmup_s\":$NEO_WARMUP_S}" > "$OUT/.load_json"
  # server into the fence (console mode = foreground JVM, so the scope holds exactly it)
  ( sudo systemd-run --collect --scope --slice=measured.slice --unit="$UNIT" \
      -E JAVA_HOME="$NEO_JAVA_HOME" -E NEO4J_HOME="$NEO_HOME" -E NEO4J_CONF="$NEO_HOME/conf" \
      -- taskset -c "$CPUS_MEASURED" "$NEO_HOME/bin/neo4j" console ) > "$OUT/neo4j.log" 2>&1 &
  NEO_RUN_PID=$!
  dlog "neo4j launched (pid $NEO_RUN_PID)"
  for i in $(seq 1 120); do [ -d "/sys/fs/cgroup/$CG" ] && break; sleep 1; done
  [ -d "/sys/fs/cgroup/$CG" ] || { dlog "neo4j scope never appeared"; return 1; }
  echo "$CG" > "$OUT/.server_cg"
  for i in $(seq 1 180); do
    "$CLIENT_PY" - <<'PY' 2>/dev/null && break
import socket; s=socket.create_connection(("127.0.0.1",7687),timeout=1); s.close()
PY
    kill -0 "$NEO_RUN_PID" 2>/dev/null || { dlog "neo4j exited during start-up (see $OUT/neo4j.log)"; return 1; }
    sleep 1
  done
  sleep 5
  # client on the housekeeping cores, outliving the capture
  ( taskset -c "$CPUS_HOUSE" "$CLIENT_PY" "$KITD/neo4j_client.py" --database "$NEO_DB" --nodes "$NEO_NODES" \
      --duration "$dur" --procs "$CLIENT_PROCS" --sessions "$CLIENT_SESSIONS" --window "$CAPTURE_S" \
      --p-short "$NEO_P_SHORT" --p-long "$NEO_P_LONG" \
      --out "$OUT/client" ) > "$OUT/client.log" 2>&1 &
  CLIENT_PID=$!
  dlog "client launched (pid $CLIENT_PID, ${CLIENT_PROCS}x${CLIENT_SESSIONS} sessions, ${dur}s); warm-up ${NEO_WARMUP_S}s"
  sleep "$NEO_WARMUP_S"
  kill -0 "$CLIENT_PID" 2>/dev/null || { dlog "client died during warm-up (see $OUT/client.log)"; return 1; }
  [ -d "/sys/fs/cgroup/$CG" ] || { dlog "neo4j died during warm-up"; return 1; }
  # the fence must actually be busy: mean cores over the last 10 s
  local u0 u1; u0=$(awk '/usage_usec/{print $2}' "/sys/fs/cgroup/$CG/cpu.stat"); sleep 10
  u1=$(awk '/usage_usec/{print $2}' "/sys/fs/cgroup/$CG/cpu.stat")
  local cc=$(( (u1 - u0) / 100000 ))     # centi-cores over 10 s
  [ "$cc" -ge $((NEO_MIN_CORES * 100)) ] || { dlog "server fence only $((cc/100)).$((cc%100)) cores busy after warm-up"; return 1; }
  dlog "server busy ~$((cc/100)).$((cc%100)) cores; client $(tail -1 "$OUT/client.p0.csv" 2>/dev/null | cut -d, -f2-4)"
  return 0
}

bench_stop(){ # $1 OUT, $2 UNIT
  local OUT="$1" UNIT="$2"
  [ -n "${CLIENT_PID:-}" ] && kill -TERM "$CLIENT_PID" 2>/dev/null
  local i; for i in $(seq 1 40); do kill -0 "${CLIENT_PID:-0}" 2>/dev/null || break; sleep 1; done
  "$CLIENT_PY" "$KITD/neo4j_client.py" --summarize --window "$CAPTURE_S" --out "$OUT/client" > /dev/null 2>&1 \
    && cp "$OUT/client.receipt.json" "$OUT/neo4j_receipt.json" 2>/dev/null
  sudo systemctl stop "$UNIT.scope" 2>/dev/null
  [ -n "${NEO_RUN_PID:-}" ] && kill -TERM "$NEO_RUN_PID" 2>/dev/null
  for i in $(seq 1 30); do pgrep -f "$NEO_HOME" >/dev/null || break; sleep 1; done
  pgrep -f "$NEO_HOME" >/dev/null && sudo pkill -f "$NEO_HOME" 2>/dev/null
  sleep 3
}
