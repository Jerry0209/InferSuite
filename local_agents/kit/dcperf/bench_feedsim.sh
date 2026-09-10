#!/usr/bin/env bash
# bench_feedsim.sh — FeedSim module for run_dcperf_profile.sh.
#
# FeedSim (DCPerf) is a two-binary workload:
#   LeafNodeRank    the ranking/aggregation SERVER  -> the workload under test
#   DriverNodeRank  the closed-loop load generator  -> the client
# so it maps onto our fence discipline without inventing anything: the server goes into
# measured.slice (one cgroup fence, "server"), the driver stays on the HOUSEKEEPING cores,
# exactly where the litellm proxy sits during agent campaigns.
#
# DCPerf's own run.sh launches both. We do not rewrite it — we generate a patched COPY with
# exactly two edits (the patch generator is patch_run_sh.py, kept in this kit for provenance):
#   1. the control shell pins itself to CPUS_HOUSE, so run.sh, search_qps.sh and the driver
#      never touch the measured partition;
#   2. the LeafNodeRank launch is wrapped in `systemd-run --scope --slice=measured.slice`
#      (the same mechanism the agent campaign uses for the harness scope) with an explicit
#      taskset to CPUS_MEASURED.
# Every DCPerf flag, thread count and workload parameter is left as DCPerf sets it.
#
# Steady state: run.sh -> 90 s leaf start-up -> warm-up load test -> the fixed-QPS experiment.
# search_qps.sh writes phase markers to /tmp/feedsim_log.txt; "after warmup" is the trigger,
# then the driver takes ~7 s to come up before the experiment proper. We start windowing
# after that, so every counter window lands in the fixed-QPS steady state.
FS_DIR="$DCPERF_ROOT/benchmarks/feedsim"
FS_QPS="${FEEDSIM_QPS:-100}"          # fixed-QPS operating point (see the study README)
FS_WARMUP="${FEEDSIM_WARMUP:-120}"
# THREAD SIZING. run.sh derives its pool sizes from `nproc` and /sys/devices/system/cpu/smt/active.
# Neither reads our split partition correctly: nproc reflects the CALLER's affinity (the
# housekeeping set), and smt/active is 1 because the housekeeping cores keep their siblings,
# even though the MEASURED partition runs with its siblings offlined. Left alone, FeedSim would
# size itself with the SMT branch (2 ranking threads for 8 cores) and idle the partition.
# So we pass DCPerf's OWN non-SMT formula, evaluated for the 8-core measured partition:
#   -t min(8,216)=8 thrift · -c 8*15/20=6 ranking · -s min(8*11/20,55)=4 serialization
FS_THREADS="${FEEDSIM_THREADS:--t 8 -c 6 -s 4}"
FS_PHASELOG=/tmp/feedsim_log.txt

bench_preflight(){
  [ -x "$FS_DIR/src/build/workloads/ranking/LeafNodeRank" ] || {
    dlog "feedsim not installed: $FS_DIR/src/build/workloads/ranking/LeafNodeRank missing"; return 1; }
  [ -x "$FS_DIR/src/build/workloads/ranking/DriverNodeRank" ] || {
    dlog "feedsim DriverNodeRank missing"; return 1; }
  sudo python3 "$KITD/patch_run_sh.py" "$FS_DIR/run.sh" "$FS_DIR/run_infersuite.sh" || return 1
  dlog "feedsim preflight OK (patched runner regenerated)"
}

bench_start(){ # $1 OUT, $2 UNIT
  local OUT="$1" UNIT="$2"
  local dur=$((CAPTURE_S + 60))       # experiment must outlast the capture window
  # NOTE: fs.protected_regular blocks root from O_CREAT-ing a file it does not own inside
  # a sticky world-writable dir, so the phase log must be REMOVED here and created by the
  # (root) benchmark itself -- pre-creating it as our user makes run.sh die on startup.
  sudo rm -f "$FS_PHASELOG"
  sudo systemctl stop "$UNIT.scope" 2>/dev/null; sudo systemctl reset-failed "$UNIT.scope" 2>/dev/null
  echo "{\"qps\":$FS_QPS,\"warmup_s\":$FS_WARMUP,\"exp_s\":$dur,\"threads\":\"$FS_THREADS\"}" > "$OUT/.load_json"

  ( IS_LEAF_UNIT="$UNIT" IS_CPUS_HOUSE="$CPUS_HOUSE" IS_CPUS_MEASURED="$CPUS_MEASURED" \
    sudo -E bash "$FS_DIR/run_infersuite.sh" -q "$FS_QPS" -d "$dur" -w "$FS_WARMUP" \
      $FS_THREADS -o "feedsim_results_infersuite.txt" ) > "$OUT/feedsim_run.log" 2>&1 &
  FS_RUN_PID=$!
  dlog "feedsim launched (qps=$FS_QPS warmup=${FS_WARMUP}s exp=${dur}s) pid $FS_RUN_PID"

  # the server fence appears when systemd creates the scope
  local CG="measured.slice/$UNIT.scope" i
  for i in $(seq 1 180); do [ -d "/sys/fs/cgroup/$CG" ] && break; sleep 1; done
  [ -d "/sys/fs/cgroup/$CG" ] || { dlog "leaf scope never appeared"; return 1; }
  echo "$CG" > "$OUT/.server_cg"
  dlog "leaf scope up: $CG — waiting for warm-up to finish"

  # wait for the warm-up load test to complete, then let the real driver come up (~7 s)
  for i in $(seq 1 900); do
    grep -q "after warmup" "$FS_PHASELOG" 2>/dev/null && break
    kill -0 "$FS_RUN_PID" 2>/dev/null || { dlog "feedsim exited during warm-up"; return 1; }
    sleep 1
  done
  grep -q "after warmup" "$FS_PHASELOG" 2>/dev/null || { dlog "warm-up never completed"; return 1; }
  sleep 12
  [ -d "/sys/fs/cgroup/$CG" ] || { dlog "leaf died before steady state"; return 1; }
  return 0
}

bench_stop(){ # $1 OUT, $2 UNIT
  local OUT="$1" UNIT="$2"
  # SLA RECEIPT: search_qps.sh writes its results row only when the experiment RUNS OUT, so
  # killing the benchmark the moment the capture window closes leaves no evidence that the
  # workload met its own p95 target while we were profiling it. The experiment is sized to
  # outlast the capture by 60 s, so wait (bounded) for it to finish and write that row.
  local i
  for i in $(seq 1 "${FEEDSIM_DRAIN_S:-180}"); do
    kill -0 "$FS_RUN_PID" 2>/dev/null || break
    sleep 1
  done
  [ -n "$FS_RUN_PID" ] && sudo kill -TERM "$FS_RUN_PID" 2>/dev/null
  sudo pkill -f DriverNodeRank 2>/dev/null
  sudo systemctl stop "$UNIT.scope" 2>/dev/null
  sudo pkill -f LeafNodeRank 2>/dev/null
  cp "$FS_PHASELOG" "$OUT/feedsim_phases.txt" 2>/dev/null
  cp "$FS_DIR/feedsim_results_infersuite.txt" "$OUT/feedsim_results.txt" 2>/dev/null
  sleep 3
}
