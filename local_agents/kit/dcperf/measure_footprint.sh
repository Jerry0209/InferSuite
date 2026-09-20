#!/usr/bin/env bash
# measure_footprint.sh — the DATA FOOTPRINT of every server benchmark, measured, not assumed
# (mentor question 2026-09-20: what dataset does each workload use, how big is it, is it
# realistic). Runs each benchmark briefly inside a memory-accounted systemd scope on the
# measured cores (no perf, no isolation change) and records:
#   <name>.mem     cgroup memory.peak / memory.current after the run (RSS + page cache)
#   gc-<name>.log  JVM unified GC log; "A->B(C)" gives the LIVE heap after each collection,
#                  which is the honest data-footprint number for a JVM (peak RSS mostly
#                  reflects how far the collector let the heap grow)
# Summarise with: python3 local_agents/kit/dcperf/parse_footprint.py <outdir>
#
#   OUT=/path/to/outdir bash local_agents/kit/dcperf/measure_footprint.sh
# ~9 min for the ten benchmarks + DaCapo's own "large" cassandra size + the FeedSim leaf.
set -u
OUT="${OUT:-$PWD/footprint}"; mkdir -p "$OUT/wd"
J="${JAVA:-/usr/lib/jvm/java-21-openjdk-amd64/bin/java}"
RJ="${RENAISSANCE_JAR:-$HOME/jvmbench-infra/renaissance-gpl-0.16.1.jar}"
DJ="${DACAPO_JAR:-$HOME/jvmbench-infra/dacapo-23.11-MR2-chopin.jar}"
FS="${FEEDSIM_DIR:-$HOME/dcperf-infra/DCPerf/benchmarks/feedsim}"
VT="${VIDEO_DIR:-$HOME/dcperf-infra/DCPerf/benchmarks/video_transcode_bench}"
CPUS="${CPUS_MEASURED:-4-11}"
log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$OUT/footprint.log"; }
cat > "$OUT/wrap.sh" <<'W'
#!/bin/bash
# runs INSIDE the scope: after the workload exits, read the scope's own peak (the cgroup
# still exists while this wrapper lives)
out=$1; shift
CG=/sys/fs/cgroup$(cut -d: -f3 /proc/self/cgroup)
"$@" > "$out.stdout" 2>&1; rc=$?
echo "peak_bytes=$(cat $CG/memory.peak 2>/dev/null) current_bytes=$(cat $CG/memory.current 2>/dev/null) rc=$rc" > "$out.mem"
W
chmod +x "$OUT/wrap.sh"
run_scope(){ local name=$1 wd=$2; shift 2
  sudo systemctl stop "fp-$name.scope" 2>/dev/null; sudo systemctl reset-failed "fp-$name.scope" 2>/dev/null
  log "start $name"
  ( cd "$wd" && sudo systemd-run --quiet --scope -p MemoryAccounting=yes --slice=measured.slice --unit="fp-$name" -- \
      taskset -c "$CPUS" "$OUT/wrap.sh" "$OUT/$name" "$@" )
  log "done  $name: $(cat "$OUT/$name.mem" 2>/dev/null)"
}
if pgrep -x perf >/dev/null; then log "ABORT: a perf process is running on the box"; exit 3; fi
for b in finagle-http finagle-chirper page-rank naive-bayes neo4j-analytics; do
  run_scope "ren-$b" "$OUT/wd" "$J" -Xlog:gc:file="$OUT/gc-ren-$b.log" -jar "$RJ" -r 4 "$b"
done
for b in cassandra tomcat kafka; do
  mkdir -p "$OUT/wd/$b"
  run_scope "dac-$b" "$OUT/wd/$b" "$J" -Djava.security.manager=allow -Xlog:gc:file="$OUT/gc-dac-$b.log" \
    -jar "$DJ" -n 5 -s default --no-validation "$b"
done
mkdir -p "$OUT/wd/cassandra-large"
run_scope dac-cassandra-large "$OUT/wd/cassandra-large" "$J" -Djava.security.manager=allow \
  -Xlog:gc:file="$OUT/gc-dac-cassandra-large.log" -jar "$DJ" -n 3 -s large --no-validation cassandra
# FeedSim leaf node with run.sh's graph parameters (the ones every profiling pass used); it never
# exits, so hold it 150 s (run.sh's own readiness convention is a 90 s sleep) and read the peak
LEAF="$FS/src/build/workloads/ranking/LeafNodeRank"
run_scope feedsim-leaf "$FS/src" env MALLOC_CONF=narenas:20,dirty_decay_ms:5000 timeout -s INT 150 "$LEAF" \
  --port=11222 --monitor_port=10222 --graph_scale=21 --graph_subset=2000000 --threads=8 --cpu_threads=6 \
  --timekeeper_threads=2 --io_threads=4 --srv_threads=8 --srv_io_threads=4 --num_objects=2000 \
  --graph_max_iters=1 --noaffinity --min_icache_iterations=400000
# one SVT-AV1 encode of one substituted 1080p shot at the preset the profiling used (6)
clip=$(ls "$VT"/datasets/cuts/*.y4m | head -1)
run_scope video-svt-1clip "$OUT/wd" "$VT/ffmpeg" -y -nostdin -i "$clip" -c:v libsvtav1 -preset 6 -crf 30 -f ivf /dev/null
log "ALL DONE"; touch "$OUT/DONE"
