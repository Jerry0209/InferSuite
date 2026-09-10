#!/usr/bin/env bash
# calibrate_feedsim.sh — find FeedSim's operating point ON OUR MEASURED PARTITION.
#
# DCPerf's stock job searches for the maximum QPS holding p95 <= 500 ms, and its README asks
# for CPU boost to be ON. Our measurement contract fixes the clock (no_turbo=1, performance
# governor) for cross-workload comparability, and the workload gets 8 physical cores rather
# than a whole socket, so the stock search would converge somewhere unrepresentative (and the
# README warns it may not converge at all without boost). Instead we sweep a few FIXED QPS
# points under the exact isolation the profiling passes use, and pick the highest point that
# still meets the 500 ms p95 SLA. That point is then used for every counter pass.
#
#   QPS_LIST=4,8,12,16,20 ./calibrate_feedsim.sh
set -o pipefail
KITD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$KITD/../../.." && pwd)"
export DCPERF_ROOT="${DCPERF_ROOT:-$HOME/dcperf-infra/DCPerf}"
export SKIP_DOCKER=1
QPS_LIST="${QPS_LIST:-4,8,12,16,20}"
DUR="${DUR:-60}"; WARM="${WARM:-30}"
OUTD="${OUTD:-$REPO/local_agents/DCPerf/data/calibration}"
mkdir -p "$OUTD"

source "$REPO/local_agents/kit/campaign/run_glm_campaign.sh" noop
FS_DIR="$DCPERF_ROOT/benchmarks/feedsim"
dlog(){ printf '[calib %s] %s\n' "$(date +%H:%M:%S)" "$*"; }

sudo python3 "$KITD/patch_run_sh.py" "$FS_DIR/run.sh" "$FS_DIR/run_infersuite.sh" || exit 1
RAN_WORK=1
apply_isolation || { dlog "isolation failed"; exit 1; }
UNIT="dcperf-feedsim-calib"
sudo systemctl stop "$UNIT.scope" 2>/dev/null; sudo systemctl reset-failed "$UNIT.scope" 2>/dev/null
sudo rm -f /tmp/feedsim_log.txt "$FS_DIR/feedsim_calib.txt"

dlog "sweeping QPS=$QPS_LIST (${DUR}s each, ${WARM}s warm-up) on measured=$CPUS_MEASURED"
IS_LEAF_UNIT="$UNIT" IS_CPUS_HOUSE="$CPUS_HOUSE" IS_CPUS_MEASURED="$CPUS_MEASURED" \
  sudo -E bash "$FS_DIR/run_infersuite.sh" -q "$QPS_LIST" -d "$DUR" -w "$WARM" \
    ${FEEDSIM_THREADS:--t 8 -c 6 -s 4} -o "feedsim_calib.txt" > "$OUTD/calibrate.log" 2>&1
rc=$?
sudo systemctl stop "$UNIT.scope" 2>/dev/null; sudo pkill -f LeafNodeRank 2>/dev/null
sudo cp "$FS_DIR/feedsim_calib.txt" "$OUTD/feedsim_calibration.csv" 2>/dev/null
sudo cp /tmp/feedsim_log.txt "$OUTD/feedsim_calibration_phases.txt" 2>/dev/null
sudo chown "$(id -u):$(id -g)" "$OUTD"/* 2>/dev/null
restore_isolation
dlog "sweep rc=$rc — results:"
python3 - "$OUTD/feedsim_calibration.csv" <<'PY'
import csv, sys
try:
    rows = list(csv.DictReader(open(sys.argv[1])))
except OSError:
    sys.exit("no calibration csv produced")
print(f"{'req_qps':>8} {'achieved':>9} {'p95_ms':>9} {'p99_ms':>9}  SLA(p95<=500)")
ok = []
for r in rows:
    try:
        req, ach = float(r["requested_qps"]), float(r["achieved_qps"])
        p95, p99 = float(r["95p_ms"]), float(r["99p_ms"])
    except (KeyError, ValueError):
        continue
    good = p95 <= 500
    print(f"{req:>8.1f} {ach:>9.2f} {p95:>9.1f} {p99:>9.1f}  {'PASS' if good else 'FAIL'}")
    if good:
        ok.append((req, ach, p95))
if ok:
    best = max(ok, key=lambda x: x[0])
    print(f"\nhighest SLA-compliant point: requested {best[0]:.0f} QPS "
          f"(achieved {best[1]:.2f}, p95 {best[2]:.0f} ms)  -> use FEEDSIM_QPS={best[0]:.0f}")
else:
    print("\nno point met the 500 ms p95 SLA — sweep lower")
PY
