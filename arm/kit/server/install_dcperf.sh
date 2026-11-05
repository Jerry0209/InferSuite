#!/usr/bin/env bash
# install_dcperf.sh — ONE-TIME, non-interactive prep of the two native DCPerf workloads
# (feedsim, video-4k) on the aarch64 Ubuntu 24.04 box. Nothing here is measured.
# Reproduces arm/data/interim/server/prep_native.md. Idempotent: finished steps are skipped
# (benchpress records installs in DCPerf/benchmark_installs.txt; downloads are re-verified).
#   bash arm/kit/server/install_dcperf.sh            # builds on CPUs 16-191 (BUILD_CPUS)
# Writes: ~/dcperf-infra, apt packages, and what DCPerf's installers put in /usr/local
# (boost 1.71, gflags 2.2.2, glog 0.4.0, jemalloc 5.2.1, libevent 2.1.11, gengetopt 2.23).
set -euo pipefail
KITD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$KITD/../../.." && pwd)"
INFRA="${INFRA:-$HOME/dcperf-infra}"
DCPERF_ROOT="$INFRA/DCPerf"; DCPERF_REV=9308c3e3c404e0466f0a2929f15ddcf62b2215f6
V4K="$INFRA/datasets/video4k"; LOGS="${LOGS:-$INFRA/logs}"
BUILD_CPUS="${BUILD_CPUS:-16-191}"
mkdir -p "$LOGS" "$V4K"
log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOGS/install_dcperf.log"; }
need_free_gb(){ local f; f=$(df -BG --output=avail / | tail -1 | tr -dc 0-9)
  [ "$f" -ge "$1" ] || { log "only ${f} GB free on / (need $1): stopping"; exit 3; }; }

# 1. build deps: the union of the two installers' apt lists + benchpress's python deps,
#    pre-installed so the installers' own `apt install` never prompts.
log "apt deps"
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q \
  python3-tabulate python3-click python3-yaml python3-pandas \
  bc cmake ninja-build flex bison texinfo binutils-dev libunwind-dev bzip2 libbz2-dev \
  libsodium-dev libghc-double-conversion-dev libzstd-dev lz4 liblz4-dev xzip libsnappy-dev \
  libtool libssl-dev zlib1g-dev libdwarf-dev libaio-dev libatomic1 patch perl libiberty-dev \
  libfmt-dev sysstat jq autoconf automake meson nasm clang python3-dev pkg-config time \
  parallel p7zip git wget > "$LOGS/apt_install.log" 2>&1

# 2. DCPerf @ 9308c3e (same path as x86)
[ -d "$DCPERF_ROOT/.git" ] || git clone -q https://github.com/facebookresearch/DCPerf.git "$DCPERF_ROOT"
git -C "$DCPERF_ROOT" checkout -q "$DCPERF_REV"

# 3. the only installer edit: the ubuntu-22-compatibility patches for folly/rsocket-cpp are
#    gated on the literal "Ubuntu 22.04"; let 24.04 match too (same edit as x86's
#    install_feedsim_x86_64_ubuntu.sh, docs/handoff/dcperf_bringup.md §4).
FI="$DCPERF_ROOT/packages/feedsim/install_feedsim_aarch64_ubuntu.sh"
sed -i "s/if grep -i 'Ubuntu 22.04' \/etc\/os-release/if grep -iE 'Ubuntu (22|24)\\\\.04' \/etc\/os-release/" "$FI"
grep -q "grep -iE 'Ubuntu (22|24)" "$FI" || { log "installer patch did not apply"; exit 1; }

# 4. build both with the benchpress installers (root, as DCPerf requires)
cd "$DCPERF_ROOT"
need_free_gb 60
for job in feedsim_autoscale video_transcode_bench_svt; do
  log "benchpress install $job (CPUs $BUILD_CPUS)"
  sudo env DEBIAN_FRONTEND=noninteractive taskset -c "$BUILD_CPUS" ./benchpress_cli.py install "$job" \
    >> "$LOGS/install_${job%%_*}.log" 2>&1 || { log "$job install FAILED (see $LOGS)"; exit 1; }
done
test -x benchmarks/feedsim/src/build/workloads/ranking/LeafNodeRank
test -x benchmarks/feedsim/src/build/workloads/ranking/DriverNodeRank
test -x benchmarks/video_transcode_bench/ffmpeg_build/bin/ffmpeg

# 5. the 4K inputs (Xiph; the 8-bit copies live directly under /y4m/, not /y4m/ElFuente/),
#    verified against the x86 checksums (docs/handoff/execution/server_inputs_sha256.txt)
need_free_gb 45
SUMS="$REPO/docs/handoff/execution/server_inputs_sha256.txt"
for f in Netflix_Boat_4096x2160_60fps_8bit_420.y4m Netflix_FoodMarket_4096x2160_60fps_8bit_420.y4m; do
  want=$(awk -v f="$f" '$2 ~ "/"f"$" {print $1}' "$SUMS")
  if [ -f "$V4K/$f" ] && [ "$(sha256sum < "$V4K/$f" | cut -d' ' -f1)" = "$want" ]; then
    log "$f present, sha256 OK"; continue; fi
  log "downloading $f"
  wget -q -c "https://media.xiph.org/video/derf/y4m/$f" -O "$V4K/$f"
  got=$(sha256sum < "$V4K/$f" | cut -d' ' -f1)
  [ "$got" = "$want" ] || { log "$f sha256 MISMATCH: got $got want $want"; exit 1; }
  log "$f sha256 OK"
done

# 6. the run.sh patch (ARM port of the x86 patcher: slice from IS_SLICE, never measured.slice)
#    still applies to this tree; bench_feedsim.sh regenerates the copy on every preflight
sudo python3 "$KITD/patch_run_sh.py" \
  "$DCPERF_ROOT/benchmarks/feedsim/run.sh" "$DCPERF_ROOT/benchmarks/feedsim/run_infersuite.sh"
log "done: source arm/kit/server/env_native.sh"
