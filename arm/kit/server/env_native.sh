# env_native.sh — paths and x86-equal knobs for the two native DCPerf workloads (feedsim,
# video-4k) on the Graviton5 box. Sourced by run_server.sh (env_*.sh). Built by
# install_dcperf.sh; provenance in arm/data/interim/server/prep_native.md.
export DCPERF_ROOT="$HOME/dcperf-infra/DCPerf"                 # same path as x86 (P7)
export SKIP_DOCKER=1

# feedsim (bench_feedsim.sh): x86 pool sizes; icache_iterations stays at run.sh's 1,600,000
# (no -i passed, so NOT DCPerf's ARM job value 400000); MALLOC_CONF is set inside run.sh.
# FEEDSIM_QPS is deliberately NOT set here: it comes from calibrate_feedsim.sh on this box
# (x86 = 16). The module's own default (100) is not an x86 value.
export FEEDSIM_THREADS="-t 8 -c 6 -s 4"
export FEEDSIM_WARMUP=120
export FEEDSIM_BIN="$DCPERF_ROOT/benchmarks/feedsim/src/build/workloads/ranking"
# jemalloc 5.2.1 installed to /usr/local by FeedSim's installer (Cassandra decision 3 candidate)
export DCPERF_JEMALLOC=/usr/local/lib/libjemalloc.so.2

# video-4k (bench_video_transcode.sh): x86 used VT_CUTS=$HOME/realdata-infra/datasets/video4k;
# here the clips live under dcperf-infra (this prep may not write elsewhere). Same two files.
export VT_DIR="$DCPERF_ROOT/benchmarks/video_transcode_bench"
export VT_CUTS="$HOME/dcperf-infra/datasets/video4k"
export VT_ENCODER=svt VT_LEVELS=6:6 VT_PROCS=8 VT_PARALLELISM=1   # x86 captures: 6:6 (module default 6:9 is wrong)
export VT_INPUT_BOAT="$VT_CUTS/Netflix_Boat_4096x2160_60fps_8bit_420.y4m"
export VT_INPUT_FOODMARKET="$VT_CUTS/Netflix_FoodMarket_4096x2160_60fps_8bit_420.y4m"
# 2026-11-04 calibrate_feedsim.sh under the shield (same rule as x86's 16 QPS: highest fixed point
# with p95 <= 500 ms): 8/12/16/20 PASS (p95 367/366/369/446 ms), 24 FAIL (701 ms) -> 20.
export FEEDSIM_QPS=20
