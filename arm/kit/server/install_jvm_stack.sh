#!/usr/bin/env bash
# install_jvm_stack.sh — non-interactive install of the eight JVM Server workloads on the ARM box, in the x86
# layout (~/realdata-infra, ~/jvmbench-infra) so the bench modules' defaults work. Steps 1 and 4 of the prep:
# JDKs + libs (apt), Python 3.13 client venv (uv), every download sha256-checked against the x86 inputs
# (docs/handoff/execution/server_inputs_sha256.txt), unpack, DaCapo pruned to tomcat/cassandra/kafka.
# The stores are built afterwards by setup_cassandra_ycsb.sh, setup_kafka.sh, setup_neo4j_livejournal.sh.
#   bash arm/kit/server/install_jvm_stack.sh          (idempotent: finished steps are skipped)
set -euo pipefail
I="${INFRA:-$HOME/realdata-infra}"; J="${JVMBENCH:-$HOME/jvmbench-infra}"; D="$I/downloads"
mkdir -p "$D" "$I/logs" "$I/datasets"/{livejournal,rcv1,cassandra-ycsb,kafka} "$J"
log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$I/logs/install_jvm_stack.log"; }

# 1. system packages (arm64 builds from Ubuntu 24.04 main)
sudo DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=900 install -y -q \
  openjdk-21-jdk-headless openjdk-17-jdk-headless libjemalloc2 bzip2 unzip curl >> "$I/logs/install_jvm_stack.log" 2>&1

# 2. downloads: url  file  sha256 (x86 value; the DaCapo zip has none on x86, its jar is checked below)
fetch(){ # $1 url $2 dest $3 sha256|-
  [ -s "$2" ] || { log "download $1"; curl -fL --retry 5 --retry-delay 5 -sS -o "$2.part" "$1" && mv "$2.part" "$2"; }
  [ "$3" = - ] && { log "$(basename "$2"): $(sha256sum "$2" | cut -c1-64) (no x86 checksum)"; return; }
  echo "$3  $2" | sha256sum -c --quiet || { log "CHECKSUM MISMATCH $2"; exit 1; }
  log "$(basename "$2"): sha256 OK"
}
fetch https://archive.apache.org/dist/cassandra/5.0.9/apache-cassandra-5.0.9-bin.tar.gz "$D/apache-cassandra-bin.tar.gz" eee1460b47ebe188a29521207230617f22aad7f9e1674f5ea454f10c8f344d61
fetch https://github.com/brianfrankcooper/YCSB/releases/download/0.17.0/ycsb-cassandra-binding-0.17.0.tar.gz "$D/ycsb-cassandra-binding-0.17.0.tar.gz" 071f4b9e25d71c07362c25b5fbed10c73bc70f25889ea640d731116dd1794175
fetch https://archive.apache.org/dist/kafka/4.3.1/kafka_2.13-4.3.1.tgz "$D/kafka.tgz" f118328b2d053497350d5befd82c08db7ffd710327ff52943dd5caaa1b25db21
fetch https://archive.apache.org/dist/spark/spark-3.5.9/spark-3.5.9-bin-hadoop3.tgz "$D/spark-bin-hadoop3.tgz" 31620af875b4b7fbc58422930ada27940c1417fdee3707a029680643b943150f
fetch https://dist.neo4j.org/neo4j-community-5.26.12-unix.tar.gz "$D/neo4j-community.tar.gz" 63a686fc7cd28cbbfeb7cb5a98c6d47569914546f23a571390a9d1a1a65bd286
fetch https://snap.stanford.edu/data/soc-LiveJournal1.txt.gz "$D/soc-LiveJournal1.txt.gz" d7bcd5a87b88c896c35fdb9611e804c3f4033c39b58c4c9ea3ba53c680d516d8
fetch https://www.csie.ntu.edu.tw/~cjlin/libsvmtools/datasets/multiclass/rcv1_test.multiclass.bz2 "$D/rcv1_test.multiclass.bz2" 84dde7848a0d80843580ad0efc128d35231d6a78a02fd19518fd60ef4f34dae0
fetch https://github.com/renaissance-benchmarks/renaissance/releases/download/v0.16.1/renaissance-gpl-0.16.1.jar "$J/renaissance-gpl-0.16.1.jar" 46d23ad03c5fd3dbf4365a5d15ea5a6c7ec682061fa6775a09d39942d80b0bf3

# 3. unpack into the x86 layout (top directory stripped: $I/cassandra/bin/cassandra, ...)
for p in "cassandra apache-cassandra-bin.tar.gz" "ycsb ycsb-cassandra-binding-0.17.0.tar.gz" "kafka kafka.tgz" \
         "spark spark-bin-hadoop3.tgz" "neo4j neo4j-community.tar.gz"; do
  set -- $p
  [ -d "$I/$1/bin" ] || { mkdir -p "$I/$1"; tar -xzf "$D/$2" -C "$I/$1" --strip-components=1; log "unpacked $1"; }
done
LJ="$I/datasets/livejournal/soc-LiveJournal1.txt"; RC="$I/datasets/rcv1/rcv1_test.multiclass"
[ -s "$LJ" ] || gzip -dc "$D/soc-LiveJournal1.txt.gz" > "$LJ"
[ -s "$RC" ] || bzip2 -dc "$D/rcv1_test.multiclass.bz2" > "$RC"
echo "4bfdd9975179fbf180619b99989bc9f4a25e9371a6c8c853f1c5c611240c071b  $LJ" | sha256sum -c --quiet
echo "f47c1efaf6a94700917d9b37a4c9def034fa7bee529431f64778560988c6d3f8  $RC" | sha256sum -c --quiet
log "datasets: LiveJournal edge list + RCV1 test split sha256 OK"

# 4. Neo4j client: Python 3.13 via uv (kept inside the infra tree), driver 6.3.1 + its aarch64 Rust extension
UV="${UV:-$(command -v uv || echo "$HOME/.local/bin/uv")}"
export UV_PYTHON_INSTALL_DIR="$I/python" UV_CACHE_DIR="$I/.uv-cache"
[ -x "$I/venv/bin/python" ] || { "$UV" python install 3.13; "$UV" venv --python 3.13 "$I/venv"; }
"$UV" pip install --python "$I/venv/bin/python" 'neo4j==6.3.1' 'neo4j-rust-ext==6.3.1.0' >> "$I/logs/install_jvm_stack.log" 2>&1
"$I/venv/bin/python" -I -c 'import neo4j; from neo4j._codec.packstream import RUST_AVAILABLE as R; assert neo4j.__version__ == "6.3.1" and R' \
  && log "client venv: neo4j 6.3.1, rust packstream active"

# 5. DaCapo: only the harness jar and what tomcat/cassandra/kafka read (285 MB of the 6.3 GB zip), then drop the zip.
#    unzip's * crosses '/', so jar/*.jar extracts every benchmark's jars: the loop below prunes those again.
P=dacapo-23.11-MR2-chopin
if [ ! -f "$J/$P.jar" ]; then
  fetch "https://download.dacapobench.org/chopin/$P.zip" "$J/$P.zip" -
  ( cd "$J" && unzip -q -o "$P.zip" "$P.jar" "$P/launchers/"{tomcat,cassandra,kafka}.jar "$P/jar/*.jar" \
      "$P/jar/"{lib,tomcat,cassandra,kafka}"/*" "$P/dat/"{tomcat,cassandra,kafka}"/*" "$P/stats/"{tomcat,cassandra,kafka}"/*" )
  for d in "$J/$P/jar"/*/; do case "$(basename "$d")" in lib|tomcat|cassandra|kafka) ;; *) rm -rf "$d";; esac; done
  rm -f "$J/$P.zip"
fi
echo "c488cc61fcd02bb04b87e601fd80517b8b0991c0baf564cae17538fdc1edb792  $J/$P.jar" | sha256sum -c --quiet
log "dacapo jar sha256 OK; data tree $(du -sh "$J/$P" | cut -f1)"

# 6. the suites list the benchmarks the bench modules ask for
JAVA21="/usr/lib/jvm/java-21-openjdk-$(dpkg --print-architecture)/bin/java"
"$JAVA21" -jar "$J/renaissance-gpl-0.16.1.jar" --list | grep -cE '^finagle-(http|chirper)\b' | grep -qx 2
"$JAVA21" -jar "$J/$P.jar" -l 2>&1 | tr ' ' '\n' | grep -cxE 'tomcat|cassandra|kafka' | grep -qx 3
log "INSTALL DONE (renaissance lists finagle-http/-chirper; dacapo lists tomcat/cassandra/kafka)"
