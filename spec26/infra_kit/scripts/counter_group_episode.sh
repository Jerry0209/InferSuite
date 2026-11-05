#!/usr/bin/env bash
# counter_group_episode.sh — SPEC CPU 2026 episodes for a chosen set of counter groups, under
# the footprint run's session discipline (2026-11-04, the x86 TLB hierarchy for Jef).
#
#   GORDER_OVERRIDE="tlb_d tlb_i" DATA_ROOT=$INFRA/data_tlb ./counter_group_episode.sh [bench...]
#                                                default: all 26 rate benchmarks, index 0
#
# The episode is the campaign's own, unchanged: run_episode() from run_spec_campaign.sh (fence,
# 10 Hz pollers, 99 Hz attribution record, continuous TMA, the shuffled zero-multiplexing
# rotation over GORDER_OVERRIDE, SPEC's output check, episode_ok). What this adds is what
# frontend_footprint_episode.sh wraps around its LBR episodes, copied from it unchanged: the
# foreign-perf and 180 s whole-machine quiet gates, the knob snapshot, the shield, the 2 s
# witness with the contaminated() rule (an episode overlapped by foreign work is set aside and
# re-run, up to 3 attempts), and the restore VERIFIED against the snapshot on any exit.
# DATA_ROOT and GORDER_OVERRIDE are required: a fresh root, never the banked campaign data.
set -o pipefail
XKIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${GORDER_OVERRIDE:?set the counter groups, e.g. GORDER_OVERRIDE=\"tlb_d tlb_i\"}"
: "${DATA_ROOT:?set a fresh DATA_ROOT}"
export DATA_ROOT GORDER_OVERRIDE
# The runner's own dispatch runs on source; "help" makes it print usage, discarded here.
# shellcheck disable=SC1091
source "$XKIT/run_spec_campaign.sh" help >/dev/null
LOGF="$INFRA/logs/counter_group_episode.log"
DISK_MIN_G="${DISK_MIN_G:-35}"

if [ "${1:-}" = -h ] || [ "${1:-}" = --help ]; then sed -n '2,16p' "${BASH_SOURCE[0]}"; exit 0; fi
for g in $GORDER; do [ -n "${GRP[$g]:-}" ] || { echo "unknown counter group $g"; exit 2; }; done
BENCHES=("$@")
[ ${#BENCHES[@]} -gt 0 ] || BENCHES=("${SPEC_RATE_BENCHES[@]}")
SESS="$DATA_ROOT/_session"; n=2
while [ -e "$SESS" ]; do SESS="$DATA_ROOT/_session.$n"; n=$((n+1)); done
mkdir -p "$SESS"
GATE=(python3 "$XKIT/quiet_gate.py")
WIT_PID=""

# ---- copied from frontend_footprint_episode.sh, unchanged ---------------------------
eval "campaign_restore_isolation() $(declare -f restore_isolation | tail -n +2)"
restore_isolation(){
  campaign_restore_isolation
  local sl want now
  if [ -f "$SESS/pre_cpuset.tsv" ]; then
    while read -r sl want; do
      now=$(cat "/sys/fs/cgroup/$sl/cpuset.cpus.effective" 2>/dev/null)
      if [ -n "$want" ] && [ "$now" != "$want" ]; then
        sudo systemctl set-property --runtime "$sl" AllowedCPUs="$want"
        log "ISOLATION: $sl effective cpuset $now -> $want (its pre-shield value)"
      fi
    done < "$SESS/pre_cpuset.tsv"
  fi
  if [ -f "$SESS/pre_mslice_allowed" ] && [ ! -s "$SESS/pre_mslice_allowed" ] \
     && [ -f "$SESS/pre_mslice_dropins" ] && [ ! -s "$SESS/pre_mslice_dropins" ]; then
    sudo systemctl revert "$MSLICE" >/dev/null 2>&1 \
      && log "ISOLATION: $MSLICE reverted to no AllowedCPUs (its pre-shield state)"
  fi
  if [ "$(cat "$SESS/pre_mslice_active" 2>/dev/null)" = inactive ] \
     && [ -z "$(find "/sys/fs/cgroup/$MSLICE" -name cgroup.procs -exec cat {} + 2>/dev/null)" ]; then
    sudo systemctl stop "$MSLICE" 2>/dev/null && log "ISOLATION: $MSLICE stopped (inactive before the shield)"
  fi
}
machine_state(){
  local c sl
  for c in $(online_cpus); do
    printf 'gov_cpu%s\t%s\n' "$c" "$(cat "/sys/devices/system/cpu/cpu$c/cpufreq/scaling_governor" 2>/dev/null)"
  done
  printf 'no_turbo\t%s\n'    "$(cat /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null)"
  printf 'thp\t%s\n'         "$(cat /sys/kernel/mm/transparent_hugepage/enabled)"
  printf 'thp_defrag\t%s\n'  "$(cat /sys/kernel/mm/transparent_hugepage/defrag)"
  printf 'nmi\t%s\n'         "$(cat /proc/sys/kernel/nmi_watchdog)"
  printf 'irq_default\t%s\n' "$(cat /proc/irq/default_smp_affinity)"
  for sl in system.slice user.slice init.scope "$MSLICE"; do
    printf 'eff_%s\t%s\n'     "$sl" "$(cat "/sys/fs/cgroup/$sl/cpuset.cpus.effective" 2>/dev/null)"
    printf 'allowed_%s\t%s\n' "$sl" "$(systemctl show "$sl" -p AllowedCPUs --value 2>/dev/null)"
  done
  printf 'k3s\t%s\n' "$(systemctl is-active k3s 2>/dev/null)"
  printf 'perf_event_max_sample_rate\t%s\n' "$(cat /proc/sys/kernel/perf_event_max_sample_rate)"
  printf 'perf_cpu_time_max_percent\t%s\n'  "$(cat /proc/sys/kernel/perf_cpu_time_max_percent)"
  for c in /proc/irq/*/smp_affinity; do
    printf 'irq_%s\t%s\n' "$(basename "$(dirname "$c")")" "$(cat "$c" 2>/dev/null)"
  done
}
verify_restored(){
  [ -f "$SESS/pre_state.tsv" ] || return 0
  machine_state > "$SESS/post_state.tsv"
  local d; d="$(diff "$SESS/pre_state.tsv" "$SESS/post_state.tsv")"
  if [ -z "$d" ]; then
    log "RESTORE-VERIFY: PASS — every snapshotted knob reads its pre-shield value"
  else
    log "RESTORE-VERIFY: FAIL — differences (pre < > post):"
    printf '%s\n' "$d" | head -40 | while read -r l; do log "    $l"; done
  fi
}
trap 'rc=$?; [ -n "$WIT_PID" ] && kill "$WIT_PID" 2>/dev/null; (exit $rc); cleanup; verify_restored' EXIT

quiet_wait(){ # $1 seconds of continuous quiet required
  log "QUIET-GATE: waiting until no other user's process is busy for $1 s"
  "${GATE[@]}" wait --hold "$1" --poll 10 --mine $$ >> "$SESS/quiet.log" 2>&1
  log "QUIET-GATE: $(tail -1 "$SESS/quiet.log")"
}
foreign_hw_perf(){
  python3 "$KIT/perf_census.py" 2>/dev/null \
    | python3 -c 'import json,sys;print(json.load(sys.stdin).get("foreign_hw",0))' 2>/dev/null || echo 0
}
foreign_perf_wait(){
  local n; n=$(foreign_hw_perf)
  [ "${n:-0}" = 0 ] && return 0
  log "PERF-GATE: $n foreign perf process(es) hold hardware counters — waiting (never killed)"
  while [ "$(foreign_hw_perf)" != 0 ]; do sleep 30; done
  log "PERF-GATE: foreign perf gone"
}
contaminated(){ # $1 t0, $2 t1, [$3 metadata.json] -> exit 0 contaminated, 1 clean
  python3 - "$1" "$2" "$SESS/witness.tsv" "${3:-}" <<'PY'
import json, re, sys
t0, t1, wit, meta = float(sys.argv[1]), float(sys.argv[2]), sys.argv[3], sys.argv[4]
rows = []
for ln in open(wit):
    p = ln.rstrip("\n").split("\t")
    if len(p) == 3 and t0 <= float(p[0]) <= t1 + 2:
        top = max([float(x) for x in re.findall(r"=(\d+(?:\.\d+)?)%", p[2])] or [0])
        rows.append((float(p[1]), top, p[2]))
n = len(rows)
flag = [r for r in rows if r[1] > 10.0]
mean_tot = sum(r[0] for r in rows) / n if n else float("nan")
worst = max(rows, key=lambda r: r[0])[2] if rows else "-"
s = {"witness_rows": n, "rows_with_foreign_task": len(flag),
     "mean_foreign_cpu_pct": round(mean_tot, 1), "worst_row": worst}
if meta:
    m = json.load(open(meta))
    m["foreign_witness"] = s
    json.dump(m, open(meta, "w"), indent=1)
bad = n == 0 or len(flag) > 0.05 * n or mean_tot > 25
print(("CONTAMINATED " if bad else "clean ") + json.dumps(s))
sys.exit(0 if bad else 1)
PY
}
disk_ok(){
  local avail; avail=$(df -BG --output=avail "$DATA_ROOT" | tail -1 | tr -dc '0-9')
  [ "${avail:-0}" -ge "$DISK_MIN_G" ] && return 0
  log "ABORT: only ${avail}G free under $DATA_ROOT (need >= ${DISK_MIN_G}G)"; return 1
}

# ---------------- run ----------------------------------------------------------------
log "================ counter groups [$GORDER]: ${BENCHES[*]} ================"
log "data: $DATA_ROOT  perf: $PERF  session: $SESS"
disk_ok || exit 1
for b in "${BENCHES[@]}"; do setup_bench "$b" || exit 1; done

foreign_perf_wait
quiet_wait 180
machine_state > "$SESS/pre_state.tsv"
for sl in system.slice user.slice init.scope "$MSLICE"; do
  printf '%s\t%s\n' "$sl" "$(cat "/sys/fs/cgroup/$sl/cpuset.cpus.effective" 2>/dev/null)"
done > "$SESS/pre_cpuset.tsv"
systemctl show "$MSLICE" -p AllowedCPUs --value > "$SESS/pre_mslice_allowed" 2>/dev/null
systemctl show "$MSLICE" -p DropInPaths --value > "$SESS/pre_mslice_dropins" 2>/dev/null
systemctl is-active "$MSLICE" > "$SESS/pre_mslice_active" 2>/dev/null
sed -i '/^$/d' "$SESS/pre_mslice_allowed" "$SESS/pre_mslice_dropins"
apply_isolation || { log "ABORT: isolation could not be applied"; exit 1; }
RAN_WORK=1
"${GATE[@]}" witness --poll 2 --mine $$ --out "$SESS/witness.tsv" &
WIT_PID=$!

okc=0; failc=0
for b in "${BENCHES[@]}"; do
  [ -f "$DATA_ROOT/$b/DONE" ] && { log "skip $b (DONE)"; okc=$((okc+1)); continue; }
  disk_ok || { failc=$((failc+1)); break; }
  done_ok=0
  for try in 1 2 3; do
    foreign_perf_wait
    quiet_wait 60
    t0=$EPOCHREALTIME
    run_episode "$b"; erc=$?
    t1=$EPOCHREALTIME
    [ -f "$DATA_ROOT/$b/metadata.json" ] || { log "  $b: no metadata.json, episode failed before capture"; break; }
    v="$(contaminated "$t0" "$t1" "$DATA_ROOT/$b/metadata.json")"; crc=$?
    log "  witness: $v"
    np=$(foreign_hw_perf)
    if [ $crc = 0 ] || [ "${np:-0}" != 0 ]; then
      [ "${np:-0}" != 0 ] && log "  a foreign perf holding hardware counters appeared during the episode"
      rm -f "$DATA_ROOT/$b/DONE"
      mv "$DATA_ROOT/$b" "$DATA_ROOT/$b.contaminated.$try"
      log "  $b set aside (foreign work overlapped on attempt $try of 3)"
      continue
    fi
    [ $erc = 0 ] && done_ok=1
    break
  done
  [ $done_ok = 1 ] && okc=$((okc+1)) || failc=$((failc+1))
done
log "================ counter groups done: $okc ok, $failc failed ================"
[ $failc = 0 ]
