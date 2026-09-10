#!/usr/bin/env bash
# bench_video_transcode.sh — VideoTranscodeBench module for run_dcperf_profile.sh.
#
# Unlike FeedSim this benchmark has no client/server split: it is a BATCH of ffmpeg/SVT-AV1
# encodes run through a process pool. Fencing is therefore trivial — the whole batch goes into
# one measured.slice scope, and there is no load generator to keep off the measured partition.
#
# DATASET DEVIATION (documented in local_agents/DCPerf/README.md): DCPerf specifies the Netflix
# "El Fuente" shots from CDVL, whose download sits behind a manual free registration and so
# cannot be scripted. We substitute shots cut from freely-redistributable Xiph 1080p sequences
# at the same resolution and shot length. The ENCODER, encoding levels, parallelism and pool
# size are DCPerf's; only the source content differs, so absolute encode times are not
# comparable with published DCPerf numbers — the microarchitectural character of AV1 encoding,
# which is what this study reads, is preserved.
VT_DIR="$DCPERF_ROOT/benchmarks/video_transcode_bench"
VT_ENCODER="${VT_ENCODER:-svt}"
VT_LEVELS="${VT_LEVELS:-6:9}"          # SVT-AV1 preset range; higher = faster/cheaper
VT_PROCS="${VT_PROCS:-8}"              # pool size == measured physical cores
VT_PARALLELISM="${VT_PARALLELISM:-1}"  # encoder-internal threads (DCPerf default)

bench_preflight(){
  [ -d "$VT_DIR" ] || { dlog "video_transcode_bench not installed at $VT_DIR"; return 1; }
  local n
  n=$(sudo find "$VT_DIR/datasets/cuts" -name '*.y4m' 2>/dev/null | wc -l)
  [ "$n" -gt 0 ] || { dlog "no .y4m clips in $VT_DIR/datasets/cuts — see the dataset note"; return 1; }
  dlog "video_transcode preflight OK ($n clips, encoder=$VT_ENCODER levels=$VT_LEVELS procs=$VT_PROCS)"
}

bench_start(){ # $1 OUT, $2 UNIT
  local OUT="$1" UNIT="$2" CG="measured.slice/$2.scope" i
  sudo systemctl stop "$UNIT.scope" 2>/dev/null; sudo systemctl reset-failed "$UNIT.scope" 2>/dev/null
  echo "{\"encoder\":\"$VT_ENCODER\",\"levels\":\"$VT_LEVELS\",\"procs\":$VT_PROCS,\"parallelism\":$VT_PARALLELISM}" \
    > "$OUT/.load_json"

  # the whole batch runs inside the measured fence; no client to place elsewhere
  # run.sh resolves ./datasets/cuts and ./generate_commands_all.py RELATIVE to the benchmark
  # directory, and systemd-run --scope inherits the caller's cwd, so the cd is mandatory.
  ( sudo systemd-run --collect --scope --slice=measured.slice --unit="$UNIT" -- \
      taskset -c "$CPUS_MEASURED" bash -c "cd '$VT_DIR' && exec ./run.sh --encoder '$VT_ENCODER' \
        --levels '$VT_LEVELS' --procs '$VT_PROCS' --parallelism '$VT_PARALLELISM'" \
    ) > "$OUT/vtb_run.log" 2>&1 &
  VT_RUN_PID=$!
  dlog "video_transcode launched (pid $VT_RUN_PID)"

  for i in $(seq 1 300); do [ -d "/sys/fs/cgroup/$CG" ] && break; sleep 1; done
  [ -d "/sys/fs/cgroup/$CG" ] || { dlog "encode scope never appeared"; return 1; }
  echo "$CG" > "$OUT/.server_cg"

  # STEADY STATE for a batch workload = the pool is saturated. Wait until the fence has been
  # busy above half the pool for several consecutive samples, rather than assuming a fixed
  # warm-up: command generation and the first ffmpeg spawns take a variable amount of time.
  local ok=0 prev="" cur rate
  for i in $(seq 1 600); do
    cur=$(head -3 "/sys/fs/cgroup/$CG/cpu.stat" 2>/dev/null | awk '/usage_usec/{print $2}')
    if [ -n "$prev" ] && [ -n "$cur" ]; then
      rate=$(( (cur - prev) / 1000000 ))          # cores busy over the 1 s sample
      if [ "$rate" -ge $((VT_PROCS / 2)) ]; then ok=$((ok+1)); else ok=0; fi
      [ "$ok" -ge 8 ] && { dlog "encode pool saturated (~${rate} cores)"; return 0; }
    fi
    prev="$cur"
    kill -0 "$VT_RUN_PID" 2>/dev/null || { dlog "batch exited before saturating"; return 1; }
    sleep 1
  done
  dlog "encode pool never saturated"; return 1
}

bench_stop(){ # $1 OUT, $2 UNIT
  local OUT="$1" UNIT="$2"
  [ -n "$VT_RUN_PID" ] && sudo kill -TERM "$VT_RUN_PID" 2>/dev/null
  sudo systemctl stop "$UNIT.scope" 2>/dev/null
  sudo pkill -f ffmpeg 2>/dev/null
  sleep 3
}
