#!/usr/bin/env bash
# setup_neo4j_livejournal.sh — ONE-TIME build of the realistic Neo4j workload's database:
# SNAP soc-LiveJournal1 (4.85 M users, 69 M directed FOLLOWS edges, ~1 GB text) bulk-imported
# into a standalone Neo4j 5.26 community server as (:User {id})-[:FOLLOWS]->(:User), plus an
# index on User(id). Nothing here is measured; it prepares the store the profiling runs open.
#   INFRA=~/realdata-infra bash local_agents/kit/dcperf/setup_neo4j_livejournal.sh
set -euo pipefail
INFRA="${INFRA:-$HOME/realdata-infra}"
export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-21-openjdk-amd64}"
NEO="$INFRA/neo4j"; DS="$INFRA/datasets/livejournal"; DB=livejournal
mkdir -p "$DS"
log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$INFRA/logs/setup_livejournal.log"; }

# 1. edge list -> import CSVs (streaming; keeps a bitmap of seen ids so the node file is exact)
if [ ! -s "$DS/edges.csv" ] || [ ! -s "$DS/dataset.json" ]; then
  log "converting soc-LiveJournal1.txt.gz -> nodes.csv + edges.csv"
  python3 - "$INFRA/downloads/soc-LiveJournal1.txt.gz" "$DS" <<'PY'
import gzip, json, sys, time
src, out = sys.argv[1], sys.argv[2]
t0 = time.time(); n_edges = 0; max_id = -1
seen = bytearray(5_000_000)
with gzip.open(src, "rt") as f, open(f"{out}/edges.csv", "w") as e:
    e.write(":START_ID,:END_ID\n")
    for ln in f:
        if ln[0] == "#": continue
        a, b = ln.split()
        a = int(a); b = int(b)
        if a >= len(seen) or b >= len(seen):
            seen.extend(bytearray(max(a, b) + 1 - len(seen)))
        seen[a] = 1; seen[b] = 1
        if a > max_id: max_id = a
        if b > max_id: max_id = b
        e.write(f"{a},{b}\n"); n_edges += 1
n_nodes = 0
with open(f"{out}/nodes.csv", "w") as n:
    n.write("id:ID\n")
    for i in range(max_id + 1):
        if seen[i]:
            n.write(f"{i}\n"); n_nodes += 1
contiguous = (n_nodes == max_id + 1)
json.dump({"dataset": "SNAP soc-LiveJournal1", "url": "https://snap.stanford.edu/data/soc-LiveJournal1.html",
           "nodes": n_nodes, "edges": n_edges, "max_id": max_id, "ids_contiguous": contiguous,
           "node_label": "User", "rel_type": "FOLLOWS", "convert_s": round(time.time() - t0, 1)},
          open(f"{out}/dataset.json", "w"), indent=1)
print(f"nodes={n_nodes} edges={n_edges} max_id={max_id} contiguous={contiguous} in {time.time()-t0:.0f}s")
PY
  log "converted: $(cat "$DS/dataset.json" | tr -d '\n ' | cut -c1-200)"
else
  log "CSVs present, skipping conversion"
fi

# 2. server configuration (the profiling runs use the same file): fixed heap, page cache large
#    enough to hold the whole store, bolt only, no auth, our database as the default
cat > "$NEO/conf/neo4j.conf" <<CONF
server.directories.data=$NEO/data
server.directories.logs=$NEO/logs
initial.dbms.default_database=$DB
server.memory.heap.initial_size=8g
server.memory.heap.max_size=8g
server.memory.pagecache.size=12g
dbms.security.auth_enabled=false
server.default_listen_address=127.0.0.1
server.bolt.enabled=true
server.bolt.listen_address=127.0.0.1:7687
server.http.enabled=false
server.https.enabled=false
db.logs.query.enabled=OFF
dbms.usage_report.enabled=false
CONF

# 3. bulk import (offline), ~69 M relationships
if [ ! -d "$NEO/data/databases/$DB" ]; then
  log "importing into database '$DB' (neo4j-admin database import full)"
  HEAP_SIZE=8G "$NEO/bin/neo4j-admin" database import full "$DB" \
    --nodes=User="$DS/nodes.csv" --relationships=FOLLOWS="$DS/edges.csv" \
    --id-type=INTEGER --overwrite-destination >> "$INFRA/logs/setup_livejournal.log" 2>&1
  log "import done; store size: $(du -sh "$NEO/data/databases/$DB" | cut -f1)"
else
  log "database '$DB' present ($(du -sh "$NEO/data/databases/$DB" | cut -f1)), skipping import"
fi

# 4. index on User(id): start the server once, create the index, wait for it, stop
log "starting server to build the User(id) index"
"$NEO/bin/neo4j" start >> "$INFRA/logs/setup_livejournal.log" 2>&1
for i in $(seq 1 120); do "$NEO/bin/cypher-shell" -a bolt://127.0.0.1:7687 "RETURN 1" >/dev/null 2>&1 && break; sleep 2; done
"$NEO/bin/cypher-shell" -a bolt://127.0.0.1:7687 "CREATE INDEX user_id IF NOT EXISTS FOR (u:User) ON (u.id)" >> "$INFRA/logs/setup_livejournal.log" 2>&1
"$NEO/bin/cypher-shell" -a bolt://127.0.0.1:7687 "CALL db.awaitIndexes(1800)" >> "$INFRA/logs/setup_livejournal.log" 2>&1
log "index online; counts: $("$NEO/bin/cypher-shell" -a bolt://127.0.0.1:7687 --format plain "MATCH (u:User) RETURN count(u) AS users" | tail -1) users, $("$NEO/bin/cypher-shell" -a bolt://127.0.0.1:7687 --format plain "MATCH ()-[r:FOLLOWS]->() RETURN count(r) AS follows" | tail -1) follows"
"$NEO/bin/neo4j" stop >> "$INFRA/logs/setup_livejournal.log" 2>&1
log "SETUP DONE: store $(du -sh "$NEO/data/databases/$DB" | cut -f1), csv $(du -sh "$DS" | cut -f1)"
touch "$DS/SETUP_DONE"
