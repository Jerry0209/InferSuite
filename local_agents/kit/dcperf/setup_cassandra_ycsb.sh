#!/usr/bin/env bash
# setup_cassandra_ycsb.sh — ONE-TIME build of the realistic Cassandra workload's data: a
# standalone Apache Cassandra 5.0 node (JDK 17) loaded by YCSB 0.17 (the same YCSB version
# DaCapo bundles) with RECORDS x 1 KB rows of the CoreWorkload schema, then flushed and fully
# compacted so the profiling passes open a settled store. Nothing here is measured.
#   RECORDS=20000000 INFRA=~/realdata-infra bash local_agents/kit/dcperf/setup_cassandra_ycsb.sh
set -euo pipefail
INFRA="${INFRA:-$HOME/realdata-infra}"
CAS="$INFRA/cassandra"; YCSB="$INFRA/ycsb"; DS="$INFRA/datasets/cassandra-ycsb"
RECORDS="${RECORDS:-20000000}"
LOAD_THREADS="${LOAD_THREADS:-16}"
CPUS_MEASURED="${CPUS_MEASURED:-4-11}"; CPUS_HOUSE="${CPUS_HOUSE:-0-3,12-15}"
export JAVA_HOME="${CAS_JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"
export PATH="$JAVA_HOME/bin:$PATH"
export CASSANDRA_HOME="$CAS" CASSANDRA_CONF="$CAS/conf"
export MAX_HEAP_SIZE="${CAS_HEAP:-8G}" HEAP_NEWSIZE="${CAS_NEW:-2G}"
mkdir -p "$DS" "$CAS/data"
log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$INFRA/logs/setup_cassandra.log"; }

# 1. node configuration (the profiling passes use the same file): loopback only, one token
#    range, all state under the infra tree, and no hinted-handoff/batchlog noise
if ! grep -q 'infersuite' "$CAS/conf/cassandra.yaml"; then
  python3 - "$CAS/conf/cassandra.yaml" "$CAS" <<'PY'
import re, sys
p, home = sys.argv[1], sys.argv[2]
y = open(p).read()
def setk(y, key, val):
    pat = re.compile(rf'^(#\s*)?{key}:.*$', re.M)
    return pat.sub(f'{key}: {val}', y, count=1) if pat.search(y) else y + f'\n{key}: {val}\n'
y = setk(y, 'cluster_name', "'infersuite-realdata'")
y = setk(y, 'num_tokens', '16')
y = setk(y, 'listen_address', '127.0.0.1')
y = setk(y, 'rpc_address', '127.0.0.1')
y = setk(y, 'hints_directory', f'{home}/data/hints')
y = setk(y, 'saved_caches_directory', f'{home}/data/saved_caches')
y = setk(y, 'commitlog_directory', f'{home}/data/commitlog')
y = re.sub(r'^(#\s*)?data_file_directories:.*\n(\s*(#\s*)?- .*\n)?', f'data_file_directories:\n    - {home}/data/data\n', y, count=1, flags=re.M)
y = setk(y, 'hinted_handoff_enabled', 'false')
y = setk(y, 'auto_snapshot', 'false')
y = setk(y, 'incremental_backups', 'false')
open(p, 'w').write(y + '\n# infersuite: configured by setup_cassandra_ycsb.sh\n')
PY
  log "cassandra.yaml configured"
fi

start_node(){
  ( taskset -c "$CPUS_MEASURED" "$CAS/bin/cassandra" -f -R ) > "$INFRA/logs/cassandra_setup_node.log" 2>&1 &
  CAS_PID=$!
  local i; for i in $(seq 1 180); do "$CAS/bin/nodetool" -h 127.0.0.1 status 2>/dev/null | grep -q '^UN' && break; sleep 2; done
  "$CAS/bin/nodetool" -h 127.0.0.1 status 2>/dev/null | grep -q '^UN' || { log "node did not come up"; return 1; }
  log "node up (pid $CAS_PID)"
}
stop_node(){ "$CAS/bin/nodetool" -h 127.0.0.1 drain >/dev/null 2>&1 || true; kill -TERM "$CAS_PID" 2>/dev/null || true
  local i; for i in $(seq 1 60); do kill -0 "$CAS_PID" 2>/dev/null || break; sleep 1; done; }

if [ -f "$DS/SETUP_DONE" ]; then log "already built ($(cat "$DS/SETUP_DONE"))"; exit 0; fi
start_node
# 2. YCSB schema (CoreWorkload: y_id + field0..field9)
"$CAS/bin/cqlsh" 127.0.0.1 -e "CREATE KEYSPACE IF NOT EXISTS ycsb WITH REPLICATION = {'class':'SimpleStrategy','replication_factor':1};
CREATE TABLE IF NOT EXISTS ycsb.usertable (y_id varchar primary key, field0 varchar, field1 varchar, field2 varchar, field3 varchar, field4 varchar, field5 varchar, field6 varchar, field7 varchar, field8 varchar, field9 varchar);" >> "$INFRA/logs/setup_cassandra.log" 2>&1
log "schema created"
# 3. load RECORDS rows (client on the housekeeping cores, YCSB's own Java client)
log "YCSB load: $RECORDS records x 10 fields x 100 B, $LOAD_THREADS threads"
( cd "$YCSB" && taskset -c "$CPUS_HOUSE" env JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 PATH=/usr/lib/jvm/java-21-openjdk-amd64/bin:$PATH \
    bash bin/ycsb.sh load cassandra-cql -P workloads/workloada -p recordcount="$RECORDS" -p hosts=127.0.0.1 \
    -p cassandra.writeconsistencylevel=ONE -threads "$LOAD_THREADS" -s ) > "$INFRA/logs/ycsb_load.log" 2>&1 \
  || { log "YCSB load FAILED (see logs/ycsb_load.log)"; stop_node; exit 1; }
log "load done: $(grep -E '\[OVERALL\], (RunTime|Throughput)' "$INFRA/logs/ycsb_load.log" | tr '\n' ' ')"
# 4. settle the store: flush memtables, compact fully, so no pass profiles a compaction backlog
"$CAS/bin/nodetool" -h 127.0.0.1 flush >> "$INFRA/logs/setup_cassandra.log" 2>&1
log "compacting"; "$CAS/bin/nodetool" -h 127.0.0.1 compact ycsb >> "$INFRA/logs/setup_cassandra.log" 2>&1 || true
"$CAS/bin/nodetool" -h 127.0.0.1 tablestats ycsb.usertable 2>/dev/null | grep -E 'Space used \(live\)|SSTable count|Number of partitions' | sed 's/^\s*/   /' | tee -a "$INFRA/logs/setup_cassandra.log"
stop_node
echo "records=$RECORDS store=$(du -sh "$CAS/data/data/ycsb" | cut -f1) built=$(date -Is)" > "$DS/SETUP_DONE"
log "SETUP DONE: $(cat "$DS/SETUP_DONE")"
