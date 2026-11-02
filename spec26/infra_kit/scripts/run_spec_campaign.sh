#!/usr/bin/env bash
# run_spec_campaign.sh — SPEC CPU 2026 microarchitectural capture, following the
# InferSuite agentic-campaign methodology so the two datasets are comparable.
#
#   ./run_spec_campaign.sh [stage] [args]
#     preflight              environment checks (no state change, no capture)
#     dryrun                 zero-multiplexing gate: every group 100% enabled, TMA
#                            coexistence, and new-event semantic spot-checks
#     isolation-test         apply the shield, verify every knob, revert, re-verify
#     setup <bench>...       create ref run dirs + extract command lines (no capture)
#     episode <bench>        ONE benchmark, ONE iteration, full capture stack
#     campaign [bench...]    episodes for every benchmark given (default: all 26 rate)
#     status                 what is built / set up / captured so far
#
# Contract, inherited verbatim from the agentic kit:
#   cgroups-not-PIDs; same-window --for-each-cgroup; whole-episode group rotation,
#   SHUFFLED each cycle; zero multiplexing; continuous TMA on dedicated hardware;
#   isolation restored by trap on ANY exit including Ctrl-C; provenance metadata.json.
#
# SPEC-specific rules (PI decisions, 2026-08-04):
#   - SPECrate, copies = 1, threads = 1, ONE benchmark at a time, never concurrent.
#   - ref input size, always.
#   - benchmarks with several ref command lines run exactly ONE (SPEC_CMD_INDEX);
#     the others are banked for provenance.
#   - builds and run-dir setup happen OUTSIDE the fence and before the shield.
set -o pipefail

KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA="$(cd "$KIT/.." && pwd)"; export INFRA
# shellcheck disable=SC1091
source "$KIT/spec_env.sh"
# shellcheck disable=SC1091
source "$INFRA/campaign.conf"
STATE="$KIT/.state"; mkdir -p "$STATE" "$DATA_ROOT"
LOGF="$INFRA/logs/campaign.log"

log(){ printf '[spec %s] %s\n' "$(date +%H:%M:%S)" "$*" | tee -a "$LOGF"; }

# ---------------- CPU partition resolution -----------------------------------------
# Disabling SMT in BIOS renumbers the logical CPUs (24 -> 12), which silently
# invalidates a hardcoded "2-11,14-23". Resolve the partition against the CPUs that
# are actually online, and refuse to start if the requested set is not.
SMT_STATE="unknown"
resolve_partition(){
  local tpc; tpc=$(lscpu | awk -F: '/^Thread\(s\) per core/{gsub(/ /,"",$2); print $2}')
  # SMT_HOST is what lscpu says about the MACHINE. It is NOT what matters for the data:
  # SMT can be disabled per-core by offlining siblings, so the host can read "on" while
  # every measured core is single-threaded (2026-08-05: CPUs 16-23 offlined => cores
  # 4-11 SMT-free, cores 0-3 not). SMT_STATE below is recomputed over the measured set
  # and is what goes into metadata.json, because the SMT-on agentic baseline vs SMT-off
  # SPEC comparability argument turns on the measured cores, not on lscpu's summary.
  SMT_HOST=$([ "${tpc:-1}" -gt 1 ] && echo on || echo off)
  SMT_STATE="$SMT_HOST"
  if [ "$PARTITION_PROFILE" = auto ] && [ -z "${CPUS_MEASURED:-}" ]; then
    if [ "$SMT_HOST" = on ]; then
      CPUS_MEASURED="2-11,14-23"; CPUS_HOUSE="0-1,12-13"
    else
      CPUS_MEASURED="2-11";       CPUS_HOUSE="0-1"
    fi
  fi
  CPUS_MEASURED="${CPUS_MEASURED:-2-11,14-23}"; CPUS_HOUSE="${CPUS_HOUSE:-0-1,12-13}"
  # Derive the IRQ mask from the house set instead of trusting a hand-written hex
  # constant that nobody re-checks after the partition changes.
  local derived
  derived=$(python3 - "$CPUS_HOUSE" "$CPUS_MEASURED" "$(cat /sys/devices/system/cpu/online)" <<'PY'
import sys
def parse(s):
    out = set()
    for part in s.split(","):
        if not part: continue
        a, _, b = part.partition("-")
        out |= set(range(int(a), int(b or a) + 1))
    return out
house, meas, online = map(parse, sys.argv[1:4])
bad = (house | meas) - online
if bad:
    print("OFFLINE " + ",".join(map(str, sorted(bad)))); raise SystemExit
if house & meas:
    print("OVERLAP " + ",".join(map(str, sorted(house & meas)))); raise SystemExit
m = 0
for c in house: m |= 1 << c

# Per-core SMT verdict over the MEASURED set only: a core is SMT-live iff it has more
# than one ONLINE thread sibling. Offlining a sibling makes the core single-threaded
# even while lscpu still reports 2 threads/core for the machine.
smt_live = []
for c in sorted(meas):
    try:
        with open(f"/sys/devices/system/cpu/cpu{c}/topology/thread_siblings_list") as f:
            sibs = parse(f.read().strip())
    except OSError:
        continue
    if len(sibs & online) > 1:
        smt_live.append(c)
verdict = "on" if len(smt_live) == len(meas) else ("off" if not smt_live else "mixed")
print(f"{m:x} {verdict} {','.join(map(str, smt_live))}")
PY
)
  case "$derived" in
    OFFLINE*) log "FATAL: partition names CPUs that are not online: ${derived#OFFLINE }"
              log "       online = $(cat /sys/devices/system/cpu/online); host SMT is $SMT_HOST"
              log "       set PARTITION_PROFILE=auto or pass CPUS_MEASURED/CPUS_HOUSE"; exit 1 ;;
    OVERLAP*) log "FATAL: measured and house sets overlap on ${derived#OVERLAP }"; exit 1 ;;
  esac
  local smt_live_cpus
  read -r derived SMT_STATE smt_live_cpus <<<"$derived"
  HOUSE_IRQ_MASK="${HOUSE_IRQ_MASK_OVERRIDE:-$derived}"
  # A 'mixed' measured set means some measured cores share a physical core and some do
  # not — the resulting profile would be an uncontrolled blend of SMT and non-SMT cores.
  if [ "$SMT_STATE" = mixed ]; then
    log "FATAL: measured set has SMT-live cores ($smt_live_cpus) alongside SMT-free ones."
    log "       That blends two different microarchitectural conditions in one profile."
    log "       Narrow CPUS_MEASURED to one or the other."; exit 1
  fi
  log "partition: SMT=$SMT_STATE (measured cores; host reports $SMT_HOST) measured=$CPUS_MEASURED house=$CPUS_HOUSE irq_mask=$HOUSE_IRQ_MASK"
}
resolve_partition

# Some knobs vanish depending on BIOS/driver state — e.g. disabling DVFS in BIOS can
# remove intel_pstate entirely. Writing to a missing path must warn, not abort a
# multi-hour campaign.
wr(){ # $1 value, $2 path, $3 label
  if [ -e "$2" ]; then echo "$1" | sudo tee "$2" >/dev/null 2>&1 && return 0; fi
  log "  note: $3 not settable ($2 absent or read-only) — leaving as the firmware set it"
  return 1
}

# ---------------- counter groups ---------------------------------------------------
# The 8 CERTIFIED groups are byte-identical to the agentic campaign — that identity is
# what makes the cross-workload comparison legitimate. Each fits the per-thread GP
# budget (<=4 GP + the two fixed counters), so exactly one group is live per window at
# 100% enabled time and nothing is ever multiplexed.
declare -A GRP
GRP[fpbr]="cycles,instructions,fp_arith_inst_retired.scalar,fp_arith_inst_retired.vector,branches,branch-misses"
GRP[cache]="cycles,instructions,mem_load_retired.l1_hit,mem_load_retired.l2_hit,mem_load_retired.l3_hit,mem_load_retired.l3_miss"
GRP[mlp]="cycles,instructions,l1d_pend_miss.pending,l1d_pend_miss.pending_cycles"
GRP[fe]="cycles,instructions,idq.dsb_uops,idq.mite_uops,idq.ms_uops,lsd.uops"
GRP[fe_lat]="cycles,instructions,icache_data.stalls,icache_tag.stalls,int_misc.clear_resteer_cycles,l2_rqsts.all_code_rd"
GRP[core_ports]="cycles,instructions,exe_activity.1_ports_util,exe_activity.2_ports_util,exe_activity.exe_bound_0_ports,arith.div_active"
GRP[dram_bw]="cycles,instructions,cpu/offcore_requests_outstanding.data_rd,cmask=4/,offcore_requests_outstanding.cycles_with_data_rd,offcore_requests.data_rd"
GRP[priv]="task-clock,context-switches,cpu-migrations,page-faults,cycles:u,cycles:k,instructions:u,instructions:k"
# The 3 DRILL groups. Not part of the agentic rotation: SPEC episodes are long enough
# to absorb the dilution, and mem_bound is the strongest available evidence for the
# "this workload is memory-bound" claim the methodology is meant to reproduce.
# Cross-workload figures must still use ONLY the shared 8.
GRP[mem_bound]="cycles,instructions,exe_activity.bound_on_loads,memory_activity.stalls_l1d_miss,memory_activity.stalls_l2_miss,memory_activity.stalls_l3_miss"
GRP[fe_l3x]="cycles,instructions,dsb2mite_switches.penalty_cycles,idq.ms_switches,exe_activity.bound_on_stores,itlb_misses.walk_active"
GRP[fe_miss]="cycles,instructions,baclears.any,frontend_retired.any_dsb_miss,br_misp_retired.cond,br_misp_retired.indirect"

GORDER_SHARED8="fpbr cache mlp fe fe_lat core_ports dram_bw priv"
GORDER="${GORDER_OVERRIDE:-$GORDER_SHARED8 mem_bound fe_l3x fe_miss}"
TMA_EVENTS="slots,topdown-retiring,topdown-bad-spec,topdown-fe-bound,topdown-be-bound,topdown-heavy-ops,topdown-br-mispredict,topdown-fetch-lat,topdown-mem-bound"

# ---------------- cleanup trap -----------------------------------------------------
POLL_PIDS=(); REC_PID=""; TMACONT_PID=""; CUR_UNIT=""; RAN_WORK=0
cleanup(){
  local rc=$?
  if [ "$RAN_WORK" = 1 ]; then
    [ -n "$TMACONT_PID" ] && kill -INT "$TMACONT_PID" 2>/dev/null
    [ -n "$REC_PID" ]     && kill -TERM "$REC_PID"    2>/dev/null
    [ ${#POLL_PIDS[@]} -gt 0 ] && kill "${POLL_PIDS[@]}" 2>/dev/null
    [ -n "$CUR_UNIT" ] && sudo systemctl stop "$CUR_UNIT.scope" 2>/dev/null
    sudo systemctl stop 'spec-*.scope' 2>/dev/null
  fi
  [ -f "$STATE/iso_applied" ] && restore_isolation
  log "cleanup done (exit $rc)"
}
trap cleanup EXIT
trap 'exit 130' INT TERM       # Ctrl-C does not fire EXIT by itself — route it

# ---------------- isolation --------------------------------------------------------
# Single-sample primitive, threshold and method unchanged from the agentic kit:
# >2.0% non-idle on ANY measured core over 1.5 s fails.
iso_quiet_sample(){
  python3 - "$CPUS_MEASURED" <<'PY'
import sys, time
def parse(spec):
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return out
meas = parse(sys.argv[1])
def snap():
    d = {}
    for ln in open("/proc/stat"):
        if ln.startswith("cpu") and ln[3:4].isdigit():
            p = ln.split(); d[int(p[0][3:])] = (sum(map(int, p[1:11])), int(p[4]) + int(p[5]))
    return d
a = snap(); time.sleep(1.5); b = snap()
noisy = {c: 100*((b[c][0]-a[c][0])-(b[c][1]-a[c][1]))/max(b[c][0]-a[c][0], 1) for c in meas}
bad = {c: round(v, 1) for c, v in noisy.items() if v > 2.0}
print(f"  ISO-PROOF quiet-check: max busy {max(noisy.values()):.1f}% on measured cores" +
      (f" — NOISY: {bad}" if bad else " (silent)"))
sys.exit(1 if bad else 0)
PY
}

# Expand the kernel's online-CPU list ("0-3,12-15") into "0 1 2 3 12 13 14 15".
# Offline CPUs keep cpufreq/ nodes that reject writes with EBUSY, so every per-CPU sysfs
# write has to be aimed at this list rather than a cpu* glob.
online_cpus(){
  python3 - <<'PYX'
s = open('/sys/devices/system/cpu/online').read().strip()
out = []
for part in s.split(','):
    if not part: continue
    a, _, b = part.partition('-')
    out += list(range(int(a), int(b or a) + 1))
print(' '.join(map(str, out)))
PYX
}

ISO_AMBIENT=""
apply_isolation(){
  if [ -f "$STATE/iso_applied" ]; then
    log "ISOLATION: iso_applied present — keeping existing baseline snapshot (crash-rerun safe)"
  else
    log "ISOLATION: snapshotting baseline -> $STATE"
    # Each of these can be absent depending on BIOS/driver state (disabling DVFS in
    # firmware can remove intel_pstate). Snapshot only what exists, restore only what
    # was snapshotted.
    rm -f "$STATE/governor" "$STATE/no_turbo" "$STATE"/gov_cpu*
    # PER-CPU governor snapshot. Reading cpu0 and writing that one value back to every
    # CPU flattens a per-core policy: measured 2026-08-05, cpu0 was powersave while the
    # workload cores 4-11 were performance, and a single-value restore silently
    # downgraded them.
    for gc in $(online_cpus); do
      [ -e "/sys/devices/system/cpu/cpu$gc/cpufreq/scaling_governor" ] && \
        cat "/sys/devices/system/cpu/cpu$gc/cpufreq/scaling_governor" > "$STATE/gov_cpu$gc"
    done
    [ -e /sys/devices/system/cpu/intel_pstate/no_turbo ] && \
      cat /sys/devices/system/cpu/intel_pstate/no_turbo          > "$STATE/no_turbo"
    # The ORIGINAL slice cpusets. Restoring these to "all online CPUs" would destroy a
    # housekeeping partition someone else configured (measured 2026-08-05: it reset the
    # operator's 0-3,12-15 split to 0-15, letting OS work back onto the measured cores).
    for sl in system.slice user.slice init.scope "$MSLICE"; do
      systemctl show "$sl" -p AllowedCPUs --value 2>/dev/null > "$STATE/cpuset_${sl%%.*}"
    done
    grep -o '\[.*\]' /sys/kernel/mm/transparent_hugepage/enabled | tr -d '[]' > "$STATE/thp"
    grep -o '\[.*\]' /sys/kernel/mm/transparent_hugepage/defrag  | tr -d '[]' > "$STATE/thp_defrag"
    cat /proc/sys/kernel/nmi_watchdog                           > "$STATE/nmi"
    systemctl is-active k3s                                     > "$STATE/k3s" 2>/dev/null || true
    cat /proc/irq/default_smp_affinity                          > "$STATE/irq_default"
    local f n
    for f in /proc/irq/*/smp_affinity; do
      n=${f#/proc/irq/}; n=${n%%/*}
      cat "$f" > "$STATE/irq_$n" 2>/dev/null || true
    done
    touch "$STATE/iso_applied"      # BEFORE mutations: a crash mid-apply must still restore
  fi
  log "ISOLATION: applying"
  if compgen -G "/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor" >/dev/null; then
    # ONLINE cpus only: offline CPUs keep a cpufreq node that rejects writes with
    # EBUSY, and that noise would mask a genuine failure to set the governor.
    for gc in $(online_cpus); do
      [ -e "/sys/devices/system/cpu/cpu$gc/cpufreq/scaling_governor" ] && \
        echo performance | sudo tee "/sys/devices/system/cpu/cpu$gc/cpufreq/scaling_governor" >/dev/null
    done
  else
    log "  note: no cpufreq governor interface — DVFS is presumably fixed in firmware"
  fi
  wr 1     /sys/devices/system/cpu/intel_pstate/no_turbo    "no_turbo"
  wr never /sys/kernel/mm/transparent_hugepage/enabled      "THP enabled"
  wr never /sys/kernel/mm/transparent_hugepage/defrag       "THP defrag"
  wr 0     /proc/sys/kernel/nmi_watchdog                    "NMI watchdog"
  wr "$HOUSE_IRQ_MASK" /proc/irq/default_smp_affinity       "default IRQ affinity"
  local f
  for f in /proc/irq/*/smp_affinity; do
    echo "$HOUSE_IRQ_MASK" | sudo tee "$f" >/dev/null 2>&1 || true
  done
  # measured.slice is a TOP-LEVEL slice: cpusets are hierarchical, so the fence cannot
  # live under system.slice/user.slice once those are pinned to the house cores.
  sudo systemctl set-property --runtime "$MSLICE" AllowedCPUs="$CPUS_MEASURED"
  sudo systemctl set-property --runtime system.slice AllowedCPUs="$CPUS_HOUSE"
  sudo systemctl set-property --runtime user.slice   AllowedCPUs="$CPUS_HOUSE"
  if [ "${SKIP_K3S:-0}" != 1 ] && grep -q '^active' "$STATE/k3s" 2>/dev/null; then
    sudo systemctl stop k3s
    # stopping k3s leaves the PODS alive under kubepods.slice (cpuset 0-23, OUTSIDE the
    # slice shield) — killall reaps them; k3s start respawns them on restore.
    sudo /usr/local/bin/k3s-killall.sh >/dev/null 2>&1
    sudo systemctl set-property --runtime kubepods.slice AllowedCPUs="$CPUS_HOUSE" 2>/dev/null
    log "ISOLATION: k3s stopped + pods killed (auto-respawn on restore)"
  fi
  # Orphaned perf holds the PMU and forces <not counted>. The inherited single-user form
  # of this line was `sudo pkill -9 -x perf`, which on a SHARED machine SIGKILLs another
  # user's in-flight capture. Kill only OUR OWN, and refuse to run if someone else holds
  # HARDWARE counters (software-only perf provably cannot multiplex us — dryrun gate).
  pkill -9 -x -u "$(id -u)" perf 2>/dev/null
  local census fhw
  census="$(python3 "$KIT/perf_census.py" 2>/dev/null || echo '{}')"
  fhw=$(printf '%s' "$census" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("foreign_hw",0))' 2>/dev/null || echo 0)
  if [ "${fhw:-0}" -gt 0 ]; then
    log "ISOLATION ABORT: $fhw perf process(es) owned by ANOTHER USER hold hardware counters."
    printf '%s' "$census" | python3 -c '
import json, sys
for p in json.load(sys.stdin)["procs"]:
    if p["hw"] and not p["mine"]:
        print("        pid %s user %s events %s" % (p["pid"], p["user"], ",".join(p["hw"])[:60]))' \
      | while read -r l; do log "$l"; done
    log "                 They would force counter multiplexing. Coordinate — do not kill them."
    return 1
  fi
  log "ISOLATION: applied (measured=$CPUS_MEASURED house=$CPUS_HOUSE)"

  # ---- PROOF: applied != verified. Check EFFECTIVE values and actual silence. ----
  local iso_fail=0
  [ "$(cat /sys/fs/cgroup/system.slice/cpuset.cpus.effective)" = "$CPUS_HOUSE" ] || { log "ISO-PROOF FAIL: system.slice cpuset"; iso_fail=1; }
  [ "$(cat /sys/fs/cgroup/user.slice/cpuset.cpus.effective)"   = "$CPUS_HOUSE" ] || { log "ISO-PROOF FAIL: user.slice cpuset"; iso_fail=1; }
  # Frequency knobs are only asserted where the interface exists. If DVFS was fixed in
  # firmware the file is gone and there is nothing to verify — that is banked as a
  # stated condition rather than silently passing as if we had checked it.
  GOV_STATE="firmware-fixed"; TURBO_STATE="firmware-fixed"
  if [ -e /sys/devices/system/cpu/cpu2/cpufreq/scaling_governor ]; then
    GOV_STATE="$(cat /sys/devices/system/cpu/cpu2/cpufreq/scaling_governor)"
    [ "$GOV_STATE" = performance ] || { log "ISO-PROOF FAIL: governor=$GOV_STATE"; iso_fail=1; }
  else
    log "  ISO-PROOF: no cpufreq interface — recording governor as firmware-fixed"
  fi
  if [ -e /sys/devices/system/cpu/intel_pstate/no_turbo ]; then
    TURBO_STATE="$(cat /sys/devices/system/cpu/intel_pstate/no_turbo)"
    [ "$TURBO_STATE" = 1 ] || { log "ISO-PROOF FAIL: no_turbo=$TURBO_STATE"; iso_fail=1; }
  else
    log "  ISO-PROOF: no intel_pstate/no_turbo — recording turbo as firmware-fixed"
  fi
  local QUIET_OUT QUIET_TRIES="${ISO_QUIET_TRIES:-8}" qi=1
  while :; do
    if QUIET_OUT=$(iso_quiet_sample); then
      [ "$qi" -gt 1 ] && log "ISO-PROOF quiet after $qi attempt(s)${QUIET_OUT}"
      break
    fi
    if [ "$qi" -ge "$QUIET_TRIES" ]; then
      log "ISO-PROOF FAIL: measured cores not quiet after $qi attempts ${QUIET_OUT}"; iso_fail=1; break
    fi
    log "  ISO-PROOF not quiet (attempt $qi/$QUIET_TRIES), settling 4 s${QUIET_OUT}"
    qi=$((qi+1)); sleep 4
  done
  ISO_AMBIENT="$(printf '%s' "$QUIET_OUT" | tr -d '\n' | sed 's/^ *//')"
  log "ISO-PROOF ${QUIET_OUT}"     # bank the measured ambient bound, not just a verdict
  [ $iso_fail = 0 ] && log "ISOLATION: PROVEN quiet (slices pinned, knobs set, partition silent)" \
    || { log "ISOLATION: PROOF FAILED — aborting before any capture"; exit 1; }
}

restore_isolation(){
  log "ISOLATION: restoring"
  local gf gc
  for gf in "$STATE"/gov_cpu*; do
    [ -f "$gf" ] || continue
    gc=${gf##*/gov_cpu}
    sudo tee "/sys/devices/system/cpu/cpu$gc/cpufreq/scaling_governor" < "$gf" >/dev/null 2>&1 || true
    rm -f "$gf"
  done
  [ -f "$STATE/no_turbo" ]   && sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo         < "$STATE/no_turbo" >/dev/null
  [ -f "$STATE/thp" ]        && sudo tee /sys/kernel/mm/transparent_hugepage/enabled           < "$STATE/thp" >/dev/null
  [ -f "$STATE/thp_defrag" ] && sudo tee /sys/kernel/mm/transparent_hugepage/defrag            < "$STATE/thp_defrag" >/dev/null
  [ -f "$STATE/nmi" ]        && sudo tee /proc/sys/kernel/nmi_watchdog                         < "$STATE/nmi" >/dev/null
  [ -f "$STATE/irq_default" ] && sudo tee /proc/irq/default_smp_affinity                       < "$STATE/irq_default" >/dev/null
  local f n
  for f in "$STATE"/irq_[0-9]*; do
    [ -f "$f" ] || continue
    n=${f##*/irq_}
    sudo tee "/proc/irq/$n/smp_affinity" < "$f" >/dev/null 2>&1 || true
    rm -f "$f"
  done
  # Restore the cpusets we SNAPSHOTTED. The previous form reset them to the full online
  # range, which is only correct on a machine nobody else has partitioned.
  local sl sf want
  for sl in system.slice user.slice init.scope "$MSLICE"; do
    sf="$STATE/cpuset_${sl%%.*}"
    [ -f "$sf" ] || continue
    want=$(tr -d '\n' < "$sf")
    if [ -n "$want" ]; then
      sudo systemctl set-property --runtime "$sl" AllowedCPUs="$want" 2>/dev/null
    else
      # empty snapshot = the unit had no explicit cpuset; AllowedCPUs="" is not honoured
      # as a reset, so fall back to the online range for that unit only.
      sudo systemctl set-property --runtime "$sl" AllowedCPUs="$(cat /sys/devices/system/cpu/online)" 2>/dev/null
    fi
    rm -f "$sf"
  done
  if grep -q '^active' "$STATE/k3s" 2>/dev/null && [ "${SKIP_K3S:-0}" != 1 ]; then
    sudo systemctl start k3s && log "ISOLATION: k3s restarted"
  fi
  rm -f "$STATE/iso_applied"
  log "ISOLATION: restored"
}

# ---------------- capture stack ----------------------------------------------------
start_pollers(){ # $1 out, $2 fence cgroup
  local OUT="$1" CG="$2"
  # Poll at least 10x faster than the window. The pollers are the INDEPENDENT instrument
  # gate E3 checks the PMU against; at a fixed 10 Hz they matched a 100 ms window
  # one-sample-per-window, i.e. right at the Nyquist limit, and E3 failed with 0.141
  # dCPUs of pure interpolation error. Scaling with WINSEC keeps the cross-check
  # meaningful instead of relaxing its threshold.
  local PIV; PIV=$(awk -v w="${WINSEC:-5}" 'BEGIN{p=w/10; if(p>0.1)p=0.1; if(p<0.005)p=0.005; printf "%.4f", p}')
  log "  pollers at ${PIV}s interval (WINSEC=${WINSEC}s)"
  touch "$OUT/.polling"
  ( exec taskset -c "$CPUS_HOUSE" bash -c '
      while [ -f "'"$OUT"'/.polling" ]; do
        u=$(head -3 "/sys/fs/cgroup/'"$CG"'/cpu.stat" 2>/dev/null | tr "\n" " ")
        echo "$EPOCHREALTIME ${u:-usage_usec -1}"
        sleep '"$PIV"' 
      done >> "'"$OUT/cpustat_scope1.tsv"'" ' ) &
  POLL_PIDS+=($!)
  # Partition-wide residual witness: kernel threads (writeback, irq) belong to no
  # cgroup, so fence totals are a LOWER BOUND. This bounds the unfenced residual.
  ( exec taskset -c "$CPUS_HOUSE" bash -c '
      while [ -f "'"$OUT"'/.polling" ]; do
        t=$EPOCHREALTIME
        grep -E "^cpu[0-9]+" /proc/stat | while read -r c u n sy id io irq sirq _; do
          echo "$t $c $u $n $sy $id $io $irq $sirq"
        done
        sleep '"$PIV"' 
      done >> "'"$OUT/procstat_partition.tsv"'" ' ) &
  POLL_PIDS+=($!)
}
stop_pollers(){ rm -f "$1/.polling"; sleep 0.3; POLL_PIDS=(); }

start_records(){ # $1 out, $2 fence — 99 Hz, attribution ONLY, never rates
  taskset -c "$CPUS_HOUSE" "$PERF" record -e task-clock -a --cgroup="$2" -g -F 99 \
    -o "$1/rec_scope1.data" >/dev/null 2>&1 &
  REC_PID=$!
}
stop_records(){ [ -n "$REC_PID" ] && kill -TERM "$REC_PID" 2>/dev/null; wait "$REC_PID" 2>/dev/null; REC_PID=""; }

start_tma_cont(){ # $1 out, $2 fence — CONTINUOUS whole-episode TMA L1/L2 census.
  # PERF_METRICS register + fixed slots only: ZERO GP counters, so it coexists with
  # whichever windowed group is live. -I 10000 is a READ cadence; events stay installed.
  taskset -c "$CPUS_HOUSE" "$PERF" stat -I 10000 -x, -a -e "$TMA_EVENTS" \
    --for-each-cgroup="$2" -o "$1/tma_cont.csv" -- sleep 100000 >/dev/null 2>&1 &
  TMACONT_PID=$!
}
stop_tma_cont(){ # SIGINT makes perf stat emit the final partial interval and exit cleanly
  [ -n "$TMACONT_PID" ] && kill -INT "$TMACONT_PID" 2>/dev/null
  wait "$TMACONT_PID" 2>/dev/null; TMACONT_PID=""
}

cycle_stats(){ # $1 out, $2 fence, $3 alive-predicate, $4 max seconds
  local OUT="$1" CG="$2" ALIVE="$3" MAX="$4" t0=$SECONDS w=0 g ws a
  printf 'win\tgroup\tt_start\tt_end\talive_after\n' > "$OUT/windows.tsv"
  while eval "$ALIVE" 2>/dev/null && [ $((SECONDS - t0)) -lt "$MAX" ]; do
    # SHUFFLED rotation: a fixed order is systematic sampling without a random start
    # and phase-locks with the benchmark's own periodicity. The realized order is
    # banked in windows.tsv = full provenance.
    for g in $(shuf -e $GORDER); do
      eval "$ALIVE" 2>/dev/null || break
      ws=$EPOCHREALTIME
      taskset -c "$CPUS_HOUSE" "$PERF" stat -a -e "${GRP[$g]}" --for-each-cgroup="$CG" \
        -- sleep "$WINSEC" 2> "$OUT/group_${g}_w$(printf '%03d' $w).txt"
      a=1; eval "$ALIVE" 2>/dev/null || a=0     # sampled AFTER the window
      printf '%03d\t%s\t%s\t%s\t%d\n' "$w" "$g" "$ws" "$EPOCHREALTIME" "$a" >> "$OUT/windows.tsv"
      w=$((w+1))
    done
  done
  echo "$w" > "$OUT/n_windows"
}

kit_rev(){ cat "$KIT"/*.sh "$KIT"/*.py "$INFRA/campaign.conf" "$INFRA/config/$CFG_NAME.cfg" 2>/dev/null | sha256sum | cut -c1-12; }

# ---------------- SPEC run-dir preparation (OUTSIDE the fence) ---------------------
rundir_of(){ echo "$SPEC_ROOT/benchspec/CPU/$1/run/run_base_${SPEC_SIZE}_${SPEC_LABEL}.0000"; }

# Which of a benchmark's ref command lines to run. PI rule: exactly ONE, defaulting to
# SPEC's first. 18 of the 26 benchmarks list several, and they are not interchangeable
# (777.zstd_r's eight lines are eight compression levels; 710.omnetpp_r's ten are ten
# simulation configs), so any deviation from index 0 is recorded in cmd_index.tsv
# rather than being passed as a one-off env var nobody can reconstruct later.
# Format: "<benchmark>\t<index>\t<why>", '#' comments allowed.
# Per-benchmark WINSEC. Three benchmarks' longest ref command line is shorter than one
# 11-group rotation at the default 5 s; a shorter window is the only way to give them
# full group coverage. Safe because every metric is an episode-SUM ratio, invariant to
# how the same counting time is sliced. Recorded per episode in metadata.json.
winsec_for(){
  # Falls back to WINSEC_DEFAULT, never to WINSEC. run_episode declares a LOCAL WINSEC
  # for the episode, and `local WINSEC; WINSEC="$(winsec_for ...)"` shadows the global
  # BEFORE the command substitution runs — so reading $WINSEC here returned the empty
  # local and produced `sleep ""`. Measured 2026-08-05: 4493 junk windows and no
  # metadata.json before the gates caught it.
  local f="$INFRA/winsec.tsv" w=""
  [ -f "$f" ] && w=$(awk -v b="$1" '$1==b && $1 !~ /^#/ {print $2; exit}' "$f")
  echo "${w:-${WINSEC_DEFAULT:-5}}"
}

cmd_index_for(){
  local f="$INFRA/cmd_index.tsv" i=""
  [ -f "$f" ] && i=$(awk -v b="$1" '$1==b && $1 !~ /^#/ {print $2; exit}' "$f")
  echo "${i:-$SPEC_CMD_INDEX}"
}

setup_bench(){ # $1 bench — create the ref run dir; safe to re-run
  local B="$1"
  bench_is_built "$B" || { log "SETUP SKIP $B: not built"; return 1; }
  if [ -d "$(rundir_of "$B")" ] && [ -f "$(rundir_of "$B")/speccmds.cmd" ]; then
    log "SETUP $B: run dir already present"; return 0
  fi
  log "SETUP $B: creating $SPEC_SIZE run dir"
  ( spec_shell; cd "$SPEC_ROOT" && runcpu --config="$CFG_NAME" --action=setup \
      --size="$SPEC_SIZE" --tune=base --nobuild --iterations=1 "$B" ) \
      > "$INFRA/logs/setup_${B}.log" 2>&1
  [ -f "$(rundir_of "$B")/speccmds.cmd" ] || { log "SETUP FAIL $B (see logs/setup_${B}.log)"; return 1; }
  return 0
}

# ---------------- one episode ------------------------------------------------------
run_episode(){ # $1 bench
  local B="$1" SHORT="${1#*.}"; SHORT="${SHORT%_r}"
  local OUT="$DATA_ROOT/$B"
  [ -f "$OUT/DONE" ] && { log "skip $B (DONE)"; return 0; }
  bench_is_built "$B" || { log "EPISODE SKIP $B: no binary"; return 1; }
  setup_bench "$B" || return 1

  local RD; RD="$(rundir_of "$B")"
  mkdir -p "$OUT"; rm -rf "${OUT:?}"/*
  local NC; NC="$(SPEC_ROOT="$SPEC_ROOT" python3 "$KIT/extract_cmd.py" "$RD" "$OUT")" || {
    log "EPISODE FAIL $B: command extraction failed"; return 1; }
  CUR_IDX="$(cmd_index_for "$B")"
  local _ws; _ws="$(winsec_for "$B")"          # compute BEFORE shadowing the global
  [ -n "$_ws" ] || { log "EPISODE FAIL $B: winsec_for returned empty"; return 1; }
  local WINSEC="$_ws"                          # per-episode window length
  [ "$WINSEC" = "${WINSEC_DEFAULT:-5}" ] || log "  WINSEC override: ${WINSEC}s (see winsec.tsv)"
  local CMD; CMD="$(sed -n "$((CUR_IDX + 1))p" "$OUT/speccmds_all.txt")"
  [ -n "$CMD" ] || { log "EPISODE FAIL $B: no command at index $CUR_IDX (n=$NC)"; return 1; }
  log "================ $B ($NC ref command line(s), running index $CUR_IDX) ================"
  [ "$NC" -gt 1 ] && log "  NOTE: $((NC - 1)) other ref command line(s) NOT run — see speccmds_all.txt"

  # Reset the run dir before capture. SPEC run dirs are REUSED across episodes and some
  # benchmarks APPEND rather than truncate: 737.gmsh_r's choi.val held 15 lines against a
  # 5-line reference after three runs (exactly 3x), and specdiff correctly called it a
  # miscompare. Deleting only SPEC-declared outputs (speccmds -o/-e targets and compare
  # targets) leaves every input untouched.
  local NCLEAN; NCLEAN="$(python3 "$KIT/clean_rundir.py" "$RD" 2>/dev/null || echo 0)"
  [ "${NCLEAN:-0}" = 0 ] || log "  run dir reset: removed $NCLEAN generated file(s) from previous runs"

  local UNIT="spec-${SHORT}" CG="$MSLICE/spec-${SHORT}.scope"
  sudo systemctl stop "$UNIT.scope" 2>/dev/null
  sudo systemctl reset-failed "$UNIT.scope" 2>/dev/null

  RAN_WORK=1; CUR_UNIT="$UNIT"
  # The fence holds the benchmark and nothing else: `exec` makes bash BECOME the
  # benchmark rather than lingering as a parent. runuser drops back to the invoking
  # user (the run dir is user-owned) and costs no measurable CPU; the 99 Hz record
  # quantifies fence composition rather than us assuming it.
  sudo systemd-run --collect --scope --slice="$MSLICE" --unit="$UNIT" \
       -p AllowedCPUs="$CPUS_MEASURED" -p CPUAccounting=yes -p MemoryAccounting=yes -- \
       runuser -u "$USER" -- bash -c "cd '$RD' && set -a && . '$OUT/env.sh' && set +a && exec $CMD" \
       > "$OUT/bench.log" 2>&1 &
  local LAUNCH_PID=$!

  local ALIVE="systemctl is-active --quiet $UNIT.scope" i
  for i in $(seq 1 60); do [ -d "/sys/fs/cgroup/$CG" ] && break; sleep 0.5; done
  [ -d "/sys/fs/cgroup/$CG" ] || { log "EPISODE FAIL $B: scope never appeared"; tail -5 "$OUT/bench.log"; CUR_UNIT=""; return 1; }

  local T_START=$EPOCHREALTIME
  write_metadata "$OUT" "$B" "$CG" "$NC" "$CMD" "$T_START"
  start_pollers "$OUT" "$CG"; start_records "$OUT" "$CG"; start_tma_cont "$OUT" "$CG"
  cycle_stats "$OUT" "$CG" "$ALIVE" "$EPISODE_MAX_S"
  stop_tma_cont; stop_records; stop_pollers "$OUT"
  local T_END=$EPOCHREALTIME
  # The benchmark's own exit status. Without it a segfault 30s in still produces a full
  # set of windows that are indistinguishable from a good episode.
  local BRC=0; wait "$LAUNCH_PID" 2>/dev/null || BRC=$?
  sudo systemctl stop "$UNIT.scope" 2>/dev/null; CUR_UNIT=""
  [ "$BRC" = 0 ] && log "  exit status: 0" || log "  WARN: benchmark exited $BRC (see $OUT/bench.log)"

  # SPEC's own correctness check for the ONE workload we ran. Run OUTSIDE the fence and
  # after all counters are stopped, so specdiff's own CPU time never lands in the data.
  local VJ; VJ="$(SPEC_ROOT="$SPEC_ROOT" python3 "$KIT/verify_output.py" "$RD" "$T_START" "$CUR_IDX" 2>/dev/null)" || VJ='{"status":"error"}'
  case "$VJ" in
    *'"status": "pass"'*) log "  output check: PASS (specdiff clean on $(printf '%s' "$VJ" | sed -n 's/.*"n_checked": \([0-9]*\).*/\1/p') file(s))" ;;
    *'"status": "fail"'*) log "  WARN: output check FAILED — specdiff reports a mismatch" ;;
    *)                    log "  output check: $(printf '%s' "$VJ" | head -c 200)" ;;
  esac

  python3 - "$OUT" "$T_START" "$T_END" "$BRC" "$VJ" <<'PY'
import json, sys
out, t0, t1, rc, vj = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
m = json.load(open(f"{out}/metadata.json")); m["ts_end"] = t1; m["wall_s"] = t1 - t0
m["bench_exit_status"] = rc
try:
    m["output_check"] = json.loads(vj)
except Exception:
    m["output_check"] = {"status": "error", "detail": vj[:200]}
json.dump(m, open(f"{out}/metadata.json", "w"), indent=1)
PY
  episode_ok "$OUT" "$B"
}

write_metadata(){ # $1 out, $2 bench, $3 fence, $4 n_cmds, $5 cmd, $6 t_start
  local BIN; BIN="$(ls "$(bench_exe_dir "$2")"/*_base."$SPEC_LABEL"* 2>/dev/null | head -1)"
  OUT="$1" BENCH="$2" FENCE="$3" NCMDS="$4" CMD="$5" TSTART="$6" BINPATH="$BIN" \
  KITREV="$(kit_rev)" ISOAMB="$ISO_AMBIENT" GORDERV="$GORDER" \
  SMT_STATE="$SMT_STATE" SMT_HOST="${SMT_HOST:-unknown}" \
  GOV_STATE="${GOV_STATE:-unknown}" TURBO_STATE="${TURBO_STATE:-unknown}" \
  CPUS_MEASURED="$CPUS_MEASURED" CPUS_HOUSE="$CPUS_HOUSE" WINSEC="$WINSEC" \
  SPEC_SIZE="$SPEC_SIZE" SPEC_CMD_INDEX="${CUR_IDX:-$SPEC_CMD_INDEX}" SPEC_LABEL="$SPEC_LABEL" \
  CFG_NAME="$CFG_NAME" SPEC_ROOT="$SPEC_ROOT" \
  python3 - <<'PY'
import hashlib, json, os, subprocess
E = os.environ
b = E["BINPATH"]
sha = hashlib.sha256(open(b, "rb").read()).hexdigest()[:16] if b and os.path.exists(b) else None
def read(p, d=""):
    try: return open(p).read().strip()
    except OSError: return d
json.dump({
  "suite": "SPEC CPU 2026 v1.0.1", "benchmark": E["BENCH"], "size": E["SPEC_SIZE"],
  "tune": "base", "label": E["SPEC_LABEL"], "config": E["CFG_NAME"],
  "copies": 1, "threads": 1,
  "n_ref_cmds": int(E["NCMDS"]), "cmd_index": int(E["SPEC_CMD_INDEX"]), "command": E["CMD"],
  "binary": b, "binary_sha256_16": sha,
  "compiler": "gcc/g++/gfortran 14.2.0 (Ubuntu 24.04)",
  "base_optimize": "-g -O3 -march=native",
  "fence_cgroup": E["FENCE"],
  "cpus_measured": E["CPUS_MEASURED"], "cpus_house": E["CPUS_HOUSE"],
  # float, not int: WINSEC is 0.1 s. int("0.1") raises ValueError, which killed
  # write_metadata before it wrote anything — leaving an episode with 1468 good windows
  # but no metadata.json, so exit status and the output check read as "?" downstream.
  "winsec": float(E["WINSEC"]), "gorder": E["GORDERV"], "rotation": "shuffled",
  "tma_cont": True, "instruments": ["cpu.stat 10Hz", "windowed groups", "continuous TMA", "record 99Hz", "procstat witness"],
  "kernel": os.uname().release, "cmdline": read("/proc/cmdline"),
  # "smt" is the verdict over the MEASURED cores; "smt_host" is lscpu's machine-wide
  # answer. They differ when SMT is disabled by offlining siblings rather than in BIOS,
  # and only the former describes the cores this profile was collected on.
  "smt": E["SMT_STATE"], "smt_host": E["SMT_HOST"],
  "governor": E["GOV_STATE"], "no_turbo": E["TURBO_STATE"],
  "online_cpus": read("/sys/devices/system/cpu/online"),
  "offline_cpus": read("/sys/devices/system/cpu/offline"),
  "thp": read("/sys/kernel/mm/transparent_hugepage/enabled"),
  "nohz_full_boot": "nohz_full" in read("/proc/cmdline"),
  "iso_proof": E["ISOAMB"], "kit_rev": E["KITREV"],
  "ts_start": float(E["TSTART"]),
}, open(f"{E['OUT']}/metadata.json", "w"), indent=1)
PY
}

episode_ok(){ # $1 out, $2 name — window count + record size + single-thread occupancy
  local OUT="$1" NAME="$2"
  local nw; nw=$(cat "$OUT/n_windows" 2>/dev/null || echo 0)
  local sz; sz=$(stat -c%s "$OUT/rec_scope1.data" 2>/dev/null || echo 0)
  local occ; occ=$(python3 - "$OUT" <<'PY'
import sys
rows = []
try:
    for ln in open(f"{sys.argv[1]}/cpustat_scope1.tsv"):
        p = ln.split()
        if len(p) >= 3 and p[1] == "usage_usec":
            v = int(p[2])
            # The poller emits `usage_usec -1` once the scope is torn down and cpu.stat
            # stops being readable. Those sentinels MUST be dropped: differencing a real
            # first sample against a trailing -1 yields a NEGATIVE occupancy, which then
            # trivially satisfies `occ <= MAX_MEAN_CORES` and makes this gate vacuous —
            # it would pass a 20-thread benchmark. Measured 2026-08-05 on 782.lbm_r:
            # 81 trailing sentinels turned a true 1.000 cores into -0.003.
            if v >= 0:
                rows.append((float(p[0]), v))
except OSError:
    pass
print(f"{(rows[-1][1]-rows[0][1])/1e6/(rows[-1][0]-rows[0][0]):.3f}"
      if len(rows) > 1 and rows[-1][0] > rows[0][0] else "nan")
PY
)
  log "  windows=$nw record=${sz}B mean_occupancy=${occ} cores"
  local bad=0
  if [ "${nw:-0}" -lt "$MIN_WINDOWS" ]; then
    log "  FAIL: $nw windows, need >= $MIN_WINDOWS (one full rotation of $(echo $GORDER | wc -w) groups)"
    local nc; nc=$(cat "$OUT/n_cmds" 2>/dev/null || echo 1)
    if [ "${nc:-1}" -gt 1 ]; then
      # This is the escalation the PI asked for: the chosen ref command line was too
      # short to complete a rotation, so a longer one has to characterise this
      # benchmark. Record the choice in cmd_index.tsv and re-run just this episode.
      log "  ESCALATE: this benchmark has $nc ref command lines; index $CUR_IDX is too short."
      log "            Pick a longer one (see $OUT/speccmds_all.txt), then:"
      log "              echo -e '$(basename "$OUT")\\t<idx>\\ttoo short at idx $CUR_IDX' >> $INFRA/cmd_index.tsv"
      log "              rm -rf $OUT && ./scripts/run_spec_campaign.sh episode $(basename "$OUT")"
    fi
    bad=1
  fi
  [ "${sz:-0}" -gt 50000 ] || { log "  FAIL: record too small"; bad=1; }
  awk -v o="$occ" -v m="$MAX_MEAN_CORES" 'BEGIN{exit !(o==o && o<=m)}' </dev/null 2>/dev/null \
    || log "  WARN: mean occupancy $occ > $MAX_MEAN_CORES cores — benchmark is NOT single-threaded; treat its uarch profile as a blend"

  # Did the benchmark actually run to completion and produce CORRECT output? Counter
  # windows look identical whether it finished or died a minute in, so this is the only
  # thing standing between us and a clean-looking profile of a crashed run.
  local rc st; rc=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("bench_exit_status","?"))' "$OUT/metadata.json" 2>/dev/null || echo "?")
  st=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("output_check",{}).get("status","?"))' "$OUT/metadata.json" 2>/dev/null || echo "?")
  [ "$rc" = 0 ] || { log "  FAIL: benchmark exit status $rc — episode does not describe a completed run"; bad=1; }
  case "$st" in
    pass) : ;;
    fail) log "  FAIL: SPEC output check reports a miscompare — results are WRONG, not just slow"; bad=1 ;;
    # The benchmark ran and wrote output, but this benchmark's compare inputs are built
    # by a post-processing step outside every ref command line, so specdiff cannot be
    # applied when running one command line directly. The uarch data is still valid;
    # discarding it would throw away a good episode over an untestable output.
    unavailable) log "  WARN: output not specdiff-testable for this benchmark (compare inputs" \
                 ; log "        come from a post-processing step outside the ref command lines)."
                 log "        Episode KEPT — uarch data valid, correctness simply unverified." ;;
    nothing_written) log "  FAIL: the run wrote no files at all — not a completed run"; bad=1 ;;
    *)    log "  WARN: output check inconclusive ($st) — episode kept but NOT certified correct" ;;
  esac
  python3 - "$OUT" "$occ" <<'PY'
import json, sys
m = json.load(open(f"{sys.argv[1]}/metadata.json")); m["mean_cores"] = sys.argv[2]
json.dump(m, open(f"{sys.argv[1]}/metadata.json", "w"), indent=1)
PY
  if [ $bad = 0 ]; then log "EPISODE-OK $NAME"; touch "$OUT/DONE"; return 0; fi
  log "EPISODE-FAIL $NAME"; return 1
}

# ---------------- stages -----------------------------------------------------------
stage_preflight(){
  local fail=0
  log "PREFLIGHT"
  [ -n "$PERF" ] && [ -x "$PERF" ] && log "  perf: $PERF" || { log "  FAIL: no perf binary (glob /usr/lib/linux-tools-6.8*/perf)"; fail=1; }
  local par; par=$(cat /proc/sys/kernel/perf_event_paranoid)
  [ "$par" = "-1" ] && log "  perf_event_paranoid = -1" || { log "  FAIL: perf_event_paranoid=$par (need -1: sudo sysctl kernel.perf_event_paranoid=-1)"; fail=1; }
  # Any live perf holds PMU resources and can force multiplexing on us. But this is a
  # SHARED machine: never suggest a blind pkill, which would silently destroy another
  # user's in-flight campaign. Report the owners and let a human decide.
  # Not every live perf threatens us. Software events (task-clock, context-switches,
  # page-faults, ...) are counted by the kernel and occupy NO general-purpose PMU
  # counter, so they cannot force multiplexing on our 4-GP-event groups. Only a perf
  # holding HARDWARE events competes for the counters this methodology depends on.
  # Treating every perf as fatal would block indefinitely on a harmless leftover; the
  # dryrun gate is what proves the conclusion empirically.
  local pmuj; pmuj=$(python3 "$KIT/perf_census.py" 2>/dev/null || echo '{}')
  local nperf nhw
  nperf=$(printf '%s' "$pmuj" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("total",0))')
  nhw=$(printf '%s' "$pmuj" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("hw",0))')
  if [ "$nperf" = 0 ]; then
    log "  no other perf processes"
  else
    # %-formatting, not an f-string: this source is embedded in a single-quoted shell
    # string, so nested double quotes inside {} would arrive escaped and fail to parse.
    printf '%s' "$pmuj" | python3 -c '
import json, sys
for p in json.load(sys.stdin)["procs"]:
    kind = ("HARDWARE: " + ",".join(p["hw"])[:60]) if p["hw"] else "software-only (no GP counters)"
    print("        pid %7s  user %-10s %2d event(s)  %s" % (p["pid"], p["user"], p["n_ev"], kind))' \
      | while read -r l; do log "$l"; done
    if [ "$nhw" -gt 0 ]; then
      log "  FAIL: $nhw of $nperf live perf process(es) hold HARDWARE counters — multiplexing risk"
      log "        DO NOT pkill another user's capture. Wait, or coordinate."
      fail=1
    else
      log "  WARN: $nperf live perf process(es), all software-event only — no GP counters held."
      log "        Harmless in principle; the dryrun gate proves it (every group 100% enabled)."
    fi
  fi
  grep -q nohz_full /proc/cmdline && log "  nohz_full boot hardening present" || log "  WARN: no nohz_full on the kernel cmdline"
  local avail; avail=$(df -BG --output=avail "$DATA_ROOT" | tail -1 | tr -dc '0-9')
  [ "${avail:-0}" -ge 20 ] && log "  disk: ${avail}G free" || { log "  FAIL: only ${avail}G free"; fail=1; }
  sudo -n true 2>/dev/null && log "  sudo: passwordless" || { log "  FAIL: sudo needs a password"; fail=1; }
  local g; for g in $GORDER; do
    "$PERF" stat -e "${GRP[$g]}" -- true 2>&1 | grep -qiE 'not supported|unknown|Bad event' \
      && { log "  FAIL: group $g does not resolve"; fail=1; }
  done
  "$PERF" stat -e "$TMA_EVENTS" -- true 2>&1 | grep -qiE 'not supported|unknown|Bad event' \
    && { log "  FAIL: TMA events do not resolve"; fail=1; }
  [ $fail = 0 ] && log "  all $(echo $GORDER | wc -w) groups + TMA resolve"
  local nb=0 b
  for b in "${SPEC_RATE_BENCHES[@]}"; do bench_is_built "$b" || nb=$((nb+1)); done
  log "  benchmarks built: $(( ${#SPEC_RATE_BENCHES[@]} - nb )) / ${#SPEC_RATE_BENCHES[@]}"
  [ $fail = 0 ] && log "PREFLIGHT OK" || { log "PREFLIGHT FAILED"; return 1; }
}

dry_build(){
  mkdir -p "$STATE"
  [ -x "$STATE/dryload" ] && [ "$STATE/dryload" -nt "$KIT/dryload.c" ] && return 0
  gcc -O2 -march=native -o "$STATE/dryload" "$KIT/dryload.c" -lm 2>"$STATE/dryload.build.log" \
    || { log "DRYRUN FAIL: could not build dryload.c (see $STATE/dryload.build.log)"; return 1; }
}

dry_scope(){ # $1 unit, $2 kernel, $3 seconds -> echoes the cgroup path
  # Ask systemd for the scope's cgroup instead of hunting for the process. `pgrep -f
  # "dryload $2 "` also matches the systemd-run LAUNCHER, whose own command line
  # contains that string — and the launcher lives in the caller's session scope, not in
  # the new scope. Measured 2026-08-05: that made the div control report the SHELL's
  # counters (0.4% divider) instead of the div kernel's (~99%), failing a good event.
  systemd-run --user --scope --unit="$1" --collect -- "$STATE/dryload" "$2" "$3" >/dev/null 2>&1 &
  local i cg=""
  for i in $(seq 1 60); do
    cg=$(systemctl --user show "$1.scope" -p ControlGroup --value 2>/dev/null)
    [ -n "$cg" ] && [ -d "/sys/fs/cgroup$cg" ] && break
    cg=""; sleep 0.25
  done
  [ -n "$cg" ] || return 1
  # and wait until the workload is actually inside it, not merely that it exists.
  # NOTE: cgroup.procs is a kernfs file and always stat()s as size 0, so `[ -s ]` is
  # false even when the cgroup holds processes — the content has to be read.
  local procs=""
  for i in $(seq 1 60); do
    procs=$(cat "/sys/fs/cgroup$cg/cgroup.procs" 2>/dev/null)
    [ -n "$procs" ] && break
    sleep 0.25
  done
  [ -n "$procs" ] || return 1
  printf '%s\n' "${cg#/}"
}

stage_dryrun(){
  log "DRYRUN: $(echo $GORDER | wc -w) groups vs a busy dummy scope"
  dry_build || return 1
  local CG; CG=$(dry_scope "spec-dryrun-$$" mixed 240) || { log "DRYRUN FAIL: dummy did not start"; return 1; }
  log "  dummy cgroup: $CG"
  local fail=0 g
  for g in $GORDER; do
    "$PERF" stat -a -e "${GRP[$g]}" --for-each-cgroup="$CG" -- sleep 3 2> "$STATE/dry_$g.txt"
    # a trailing "( 63.42% )" is perf's multiplex-scaling annotation: the thing this
    # gate exists to forbid.
    if grep -qE "<not counted>|<not supported>|Bad event|unknown" "$STATE/dry_$g.txt" \
       || grep -qE '\(\s*[0-9]+[.,][0-9]+%\s*\)\s*$' "$STATE/dry_$g.txt"; then
      log "  FAIL group $g (see $STATE/dry_$g.txt)"; fail=1
    else log "  $g OK (100% enabled)"; fi
  done

  log "DRYRUN: continuous-TMA + windowed-group coexistence"
  "$PERF" stat -I 2000 -a -e "$TMA_EVENTS" --for-each-cgroup="$CG" -o "$STATE/dry_tmacont.txt" \
    -- sleep 12 >/dev/null 2>&1 &
  local TCP=$!
  sleep 1
  for g in fpbr core_ports mem_bound; do
    "$PERF" stat -a -e "${GRP[$g]}" --for-each-cgroup="$CG" -- sleep 3 2> "$STATE/dry_coex_$g.txt"
  done
  wait "$TCP" 2>/dev/null
  local cf
  for cf in "$STATE/dry_tmacont.txt" "$STATE"/dry_coex_*.txt; do
    if grep -qE "<not counted>|<not supported>" "$cf" || grep -qE '\(\s*[0-9]+[.,][0-9]+%\s*\)\s*$' "$cf"; then
      log "  FAIL coexistence ($cf)"; fail=1
    fi
  done
  [ $fail = 0 ] && log "  coexistence OK (continuous TMA + windowed groups, all 100%-enabled)"
  systemctl --user stop "spec-dryrun-$$.scope" 2>/dev/null

  # ---- semantics: exotic counters carry errata; prove each fires where it should
  # and stays quiet where it should not (divider vs streaming, mutual controls).
  log "DRYRUN: new-event semantics microbenchmarks"
  local DCG SCG
  DCG=$(dry_scope "spec-drydiv-$$"    div    45) || { log "  FAIL: div kernel did not start"; return 1; }
  SCG=$(dry_scope "spec-drystream-$$" stream 45) || { log "  FAIL: stream kernel did not start"; return 1; }
  sleep 6      # let the stream kernel finish its first-touch page faults
  "$PERF" stat -a -e "${GRP[core_ports]}" --for-each-cgroup="$DCG,$SCG" -- sleep 5 2> "$STATE/dry_sem_div.txt"
  "$PERF" stat -a -e "${GRP[dram_bw]}"    --for-each-cgroup="$DCG,$SCG" -- sleep 5 2> "$STATE/dry_sem_dram.txt"
  "$PERF" stat -a -e "${GRP[fpbr]}"       --for-each-cgroup="$DCG,$SCG" -- sleep 5 2> "$STATE/dry_sem_fp.txt"
  python3 - "$STATE" "$DCG" "$SCG" <<'PY' || fail=1
import re, sys
state, dcg, scg = sys.argv[1:4]
def load(f):
    d = {}
    for ln in open(f"{state}/{f}"):
        m = re.match(r"^\s+([\d.,]+)\s+(\S+)\s+(\S+)", ln)
        if m:
            try: d[(m.group(3), m.group(2))] = float(m.group(1).replace(",", ""))
            except ValueError: pass
    return d
div, dram, fp = load("dry_sem_div.txt"), load("dry_sem_dram.txt"), load("dry_sem_fp.txt")
ok = True
def chk(label, cond, detail):
    global ok
    print(f"  {'OK  ' if cond else 'FAIL'} {label}: {detail}")
    ok = ok and cond
ds = div.get((dcg, 'arith.div_active'), 0) / max(div.get((dcg, 'cycles'), 1), 1)
ss = div.get((scg, 'arith.div_active'), 0) / max(div.get((scg, 'cycles'), 1), 1)
chk("arith.div_active", ds > 0.02 and ds > 5 * max(ss, 1e-9),
    f"div-kernel {100*ds:.1f}% vs stream {100*ss:.2f}% of cycles")
dd = dram.get((dcg, 'offcore_requests.data_rd'), 0)
sd = dram.get((scg, 'offcore_requests.data_rd'), 0)
chk("offcore_requests.data_rd", sd > 5 * max(dd, 1),
    f"stream {sd:,.0f} vs div-kernel {dd:,.0f} DRAM read requests")
fv = fp.get((dcg, 'fp_arith_inst_retired.vector'), 0) + fp.get((dcg, 'fp_arith_inst_retired.scalar'), 0)
chk("fp_arith_inst_retired", fv > 0, f"div-kernel retired {fv:,.0f} FP ops")
sys.exit(0 if ok else 1)
PY
  systemctl --user stop "spec-drydiv-$$.scope" "spec-drystream-$$.scope" 2>/dev/null
  [ $fail = 0 ] && { log "DRYRUN OK — zero multiplexing, TMA coexists, event semantics verified"; return 0; }
  log "DRYRUN FAILED"; return 1
}

stage_status(){
  printf '%-18s %-7s %-7s %-6s %-8s %s\n' BENCHMARK BUILT RUNDIR EPISODE WINDOWS CORES
  local b built rd done nw mc
  for b in "${SPEC_RATE_BENCHES[@]}"; do
    bench_is_built "$b" && built=yes || built=NO
    [ -f "$(rundir_of "$b")/speccmds.cmd" ] && rd=yes || rd=no
    [ -f "$DATA_ROOT/$b/DONE" ] && done=DONE || done=-
    nw=$(cat "$DATA_ROOT/$b/n_windows" 2>/dev/null || echo -)
    mc=$(python3 -c "import json,sys;print(json.load(open('$DATA_ROOT/$b/metadata.json')).get('mean_cores','-'))" 2>/dev/null || echo -)
    printf '%-18s %-7s %-7s %-6s %-8s %s\n' "$b" "$built" "$rd" "$done" "$nw" "$mc"
  done
}

stage_campaign(){
  local benches=("$@")
  [ ${#benches[@]} -eq 0 ] && benches=("${SPEC_RATE_BENCHES[@]}")
  local runnable=() b
  for b in "${benches[@]}"; do bench_is_built "$b" && runnable+=("$b") || log "SKIP $b: not built"; done
  [ ${#runnable[@]} -gt 0 ] || { log "nothing to run"; return 1; }
  log "CAMPAIGN: ${#runnable[@]} episode(s), one at a time: ${runnable[*]}"
  # Run dirs are created BEFORE the shield goes up: setup is file copying, it is not
  # part of the measurement, and it must not run on the measured partition.
  for b in "${runnable[@]}"; do setup_bench "$b"; done
  # A failed shield must ABORT, never fall through to capturing unshielded data that
  # looks exactly like shielded data.
  apply_isolation || { log "CAMPAIGN ABORT: isolation could not be applied"; return 1; }
  local okc=0 failc=0
  for b in "${runnable[@]}"; do
    if run_episode "$b"; then okc=$((okc+1)); else failc=$((failc+1)); fi
  done
  log "CAMPAIGN DONE: $okc ok, $failc failed"
  [ $failc -eq 0 ]
}

# ---------------- dispatch ---------------------------------------------------------
case "${1:-help}" in
  preflight)      stage_preflight ;;
  dryrun)         stage_preflight && stage_dryrun ;;
  isolation-test) apply_isolation && sleep 2; restore_isolation ;;
  setup)          shift; for b in "$@"; do setup_bench "$b"; done ;;
  episode)        shift; [ -n "${1:-}" ] || { echo "usage: $0 episode <bench>"; exit 2; }
                  setup_bench "$1"
                  apply_isolation || { log "ABORT: isolation could not be applied"; exit 1; }
                  run_episode "$1" ;;
  campaign)       shift; stage_campaign "$@" ;;
  status)         stage_status ;;
  help|*)         sed -n '2,30p' "${BASH_SOURCE[0]}" ;;
esac
