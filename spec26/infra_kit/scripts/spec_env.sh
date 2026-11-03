#!/usr/bin/env bash
# spec_env.sh — single source of environment for the SPEC CPU 2026 uarch campaign.
# Source it; do not execute it.  Every script and every subagent uses this so the
# SPEC root, config name and label can never drift apart.

INFRA="${INFRA:-/home/thu/spec26-infra/infra}"
export INFRA
export SPEC_ROOT="${SPEC_ROOT:-/home/thu/spec26-infra/cpu2026}"
export CFG_NAME="${CFG_NAME:-uarch-gcc14}"          # $SPEC/config/$CFG_NAME.cfg
export SPEC_LABEL="${SPEC_LABEL:-uarch}"            # must match 'label' in the cfg
export BUILD_NCPUS="${BUILD_NCPUS:-4}"              # make -j inside ONE benchmark build
export BUILD_SLOTS="${BUILD_SLOTS:-6}"              # concurrent benchmark builds
                                                    # 6 x 4 = 24 = logical CPUs

# The 26 SPECrate benchmarks (= the 'specrate' benchset minus 999.specrand_r,
# which is a tools sanity benchmark, not a workload).
SPEC_RATE_BENCHES=(
  706.stockfish_r 707.ntest_r    708.sqlite_r   709.cactus_r  710.omnetpp_r
  714.cpython_r   721.gcc_r      722.palm_r     723.llvm_r    727.cppcheck_r
  729.abc_r       731.astcenc_r  734.vpr_r      735.gem5_r    736.ocio_r
  737.gmsh_r      748.flightdm_r 749.fotonik3d_r 750.sealcrypto_r 753.ns3_r
  765.roms_r      766.femflow_r  767.nest_r     772.marian_r  777.zstd_r
  782.lbm_r
)
export SPEC_RATE_BENCHES

# perf: /usr/bin/perf is a broken wrapper on this box and package updates move
# the real one — always glob, never hardcode.
PERF="$(ls -d /usr/lib/linux-tools-6.8*/perf 2>/dev/null | tail -1)"
PERF="${PERF:-$(command -v perf)}"   # AWS ARM box: /usr/bin/perf (6.17) works
export PERF

spec_shell() {   # put runcpu/specinvoke/specperl on PATH (sources shrc in THIS shell)
  local prev="$PWD"
  cd "$SPEC_ROOT" || return 1
  # shellcheck disable=SC1091
  . ./shrc >/dev/null 2>&1
  cd "$prev" || return 1
}

# Path to a benchmark's built base binary directory.
bench_exe_dir() { echo "$SPEC_ROOT/benchspec/CPU/$1/exe"; }

# True if the benchmark has at least one base binary for our label.
bench_is_built() {
  local d; d="$(bench_exe_dir "$1")"
  [ -d "$d" ] && compgen -G "$d/*_base.$SPEC_LABEL*" >/dev/null 2>&1
}
