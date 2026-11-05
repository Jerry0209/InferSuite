#!/usr/bin/env bash
# frontend_footprint_server.sh — Rahul's front-end footprint metrics for the realistic Server
# set on x86 (docs/handoff/execution/x86_server_footprint.md, contract v1.1). One LBR pass per
# workload through run_dcperf_profile.sh (PROF_GROUPS=lbr, lbr_pass.sh), strictly one at a time.
#
#   ./frontend_footprint_server.sh feedsim tomcat ...       workloads, in the given order
#   ./frontend_footprint_server.sh all                      the 10 realistic-set workloads
#   FF_GROUPS="tlb_d tlb_i" FF_SUBDIR=tlb_x86 ./frontend_footprint_server.sh all
#                         counter groups instead of the LBR pass (2026-11-04, the TLB hierarchy):
#                         one dedicated-group pass per group, PASS_GATES=1, no sysctl pin needed
#
# Per workload, around the orchestrator (which owns the shield, ISO-PROOF and the pass):
#   - wait until no perf owned by another user exists (never killed) and the whole machine is
#     quiet (quiet_gate.py wait: no other user's task busy for FF_QUIET_HOLD s);
#   - disk floor (FF_DISK_MIN_G; video-4k needs ~16 GB of scratch on top);
#   - snapshot every knob the shield touches (machine_state), run the pass with the workload's
#     banked env, a FRESH DATA_ROOT (<family>/data/frontend_footprint) and a timeout;
#   - afterwards: stop a leftover server scope, give measured.slice back its pre-shield state
#     (no AllowedCPUs; stopped if it was inactive), undo video-4k's dataset swap and scratch,
#     then RESTORE-VERIFY: the snapshot taken again must equal the one taken before.
# Opt-in: FF_MAX_SAMPLE_RATE / FF_CPU_TIME_PCT pin the kernel's perf sampling limits for the
# session (the kernel lowers perf_event_max_sample_rate itself when PMIs run long; throttled
# samples fail the coverage gate). Snapshotted and restored (percent first) on exit.
set -o pipefail
KITD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$KITD/../../.." && pwd)"
MSLICE="measured.slice"
FF_GROUPS="${FF_GROUPS:-lbr}"                 # PROF_GROUPS for every workload
FF_SUBDIR="${FF_SUBDIR:-frontend_footprint}"  # DATA_ROOT = <family>/data/$FF_SUBDIR (fresh)
NG=$(echo $FF_GROUPS | wc -w)
FF_QUIET_HOLD="${FF_QUIET_HOLD:-180}"
FF_DISK_MIN_G="${FF_DISK_MIN_G:-30}"
FF_MAX_SAMPLE_RATE="${FF_MAX_SAMPLE_RATE:-}"
FF_CPU_TIME_PCT="${FF_CPU_TIME_PCT:-}"
VT_DIR="${DCPERF_ROOT:-$HOME/dcperf-infra/DCPerf}/benchmarks/video_transcode_bench"
ALL=(feedsim tomcat finagle-chirper finagle-http cassandra-ycsb20m kafka-20g naivebayes-rcv1
     neo4j-livejournal pagerank-livejournal video-4k)

SESS="$REPO/local_agents/DCPerf/data/$FF_SUBDIR/_session"; n=2
while [ -e "$SESS" ]; do SESS="$REPO/local_agents/DCPerf/data/$FF_SUBDIR/_session.$n"; n=$((n+1)); done
mkdir -p "$SESS"
LOGF="$SESS/wrapper.log"
log(){ printf '[ffs %s] %s\n' "$(date +%H:%M:%S)" "$*" | tee -a "$LOGF"; }

# workload -> "family_dir|timeout|env..." (the banked counter passes' configuration)
wl_spec(){
  case "$1" in
    feedsim)              echo "DCPerf|7200|SUITE=dcperf BENCH=feedsim FEEDSIM_QPS=16 CAPTURE_S=300";;
    tomcat)               echo "JVMbench|7200|SUITE=dacapo BENCH=dacapo WORKLOAD=tomcat CAPTURE_S=180 D_ITERS=80";;
    finagle-chirper)      echo "JVMbench|7200|SUITE=renaissance BENCH=renaissance WORKLOAD=finagle-chirper CAPTURE_S=180";;
    finagle-http)         echo "JVMbench|7200|SUITE=renaissance BENCH=renaissance WORKLOAD=finagle-http CAPTURE_S=180";;
    cassandra-ycsb20m)    echo "RealData|7200|SUITE=realdata BENCH=cassandra WORKLOAD=cassandra-ycsb20m CAPTURE_S=180 CAS_WARMUP_S=120";;
    kafka-20g)            echo "RealData|7200|SUITE=realdata BENCH=kafka WORKLOAD=kafka-20g CAPTURE_S=180 KAFKA_WARMUP_S=90";;
    naivebayes-rcv1)      echo "RealData|7200|SUITE=realdata BENCH=spark WORKLOAD=naivebayes-rcv1 CAPTURE_S=180";;
    neo4j-livejournal)    echo "RealData|7200|SUITE=realdata BENCH=neo4j WORKLOAD=neo4j-livejournal CAPTURE_S=180 NEO_WARMUP_S=150";;
    pagerank-livejournal) echo "RealData|7200|SUITE=realdata BENCH=spark WORKLOAD=pagerank-livejournal CAPTURE_S=180";;
    video-4k)             echo "RealData|10800|SUITE=realdata BENCH=video_transcode WORKLOAD=video-4k VT_CUTS=$HOME/realdata-infra/datasets/video4k VT_LEVELS=6:6 CAPTURE_S=180";;
    *) return 1;;
  esac
}

# Every knob the shield (and this wrapper) touches, "key<TAB>value" per line.
machine_state(){
  local c sl f
  for f in /sys/devices/system/cpu/cpu[0-9]*; do
    c=${f##*cpu}
    printf 'online_cpu%s\t%s\n' "$c" "$(cat "$f/online" 2>/dev/null || echo 1)"
    [ -e "$f/cpufreq/scaling_governor" ] || continue
    printf 'gov_cpu%s\t%s\n' "$c" "$(cat "$f/cpufreq/scaling_governor")"
    printf 'freq_cpu%s\t%s-%s\n' "$c" "$(cat "$f/cpufreq/scaling_min_freq")" "$(cat "$f/cpufreq/scaling_max_freq")"
  done
  printf 'no_turbo\t%s\n'    "$(cat /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null)"
  printf 'thp\t%s\n'         "$(cat /sys/kernel/mm/transparent_hugepage/enabled)"
  printf 'thp_defrag\t%s\n'  "$(cat /sys/kernel/mm/transparent_hugepage/defrag)"
  printf 'nmi\t%s\n'         "$(cat /proc/sys/kernel/nmi_watchdog)"
  printf 'wq_cpumask\t%s\n'  "$(cat /sys/devices/virtual/workqueue/cpumask)"
  printf 'irq_default\t%s\n' "$(cat /proc/irq/default_smp_affinity)"
  for sl in system.slice user.slice init.scope "$MSLICE"; do
    printf 'eff_%s\t%s\n'     "$sl" "$(cat "/sys/fs/cgroup/$sl/cpuset.cpus.effective" 2>/dev/null)"
    printf 'allowed_%s\t%s\n' "$sl" "$(systemctl show "$sl" -p AllowedCPUs --value 2>/dev/null)"
  done
  printf 'active_%s\t%s\n' "$MSLICE" "$(systemctl is-active "$MSLICE" 2>/dev/null)"
  printf 'k3s\t%s\n'    "$(systemctl is-active k3s 2>/dev/null)"
  printf 'docker\t%s\n' "$(systemctl is-active docker 2>/dev/null)"
  printf 'daemon_json\t%s\n' "$(sha256sum /etc/docker/daemon.json 2>/dev/null | cut -c1-16)"
  printf 'perf_event_max_sample_rate\t%s\n' "$(cat /proc/sys/kernel/perf_event_max_sample_rate)"
  printf 'perf_cpu_time_max_percent\t%s\n'  "$(cat /proc/sys/kernel/perf_cpu_time_max_percent)"
  printf 'vt_cuts\t%s\n' "$( [ -L "$VT_DIR/datasets/cuts" ] && echo "symlink->$(readlink "$VT_DIR/datasets/cuts")" || echo dir)"
  for f in /proc/irq/*/smp_affinity; do
    printf 'irq_%s\t%s\n' "$(basename "$(dirname "$f")")" "$(cat "$f" 2>/dev/null)"
  done
}
verify_restored(){ # $1 pre-state file -> 0 if identical now
  machine_state > "$1.post"
  local d; d="$(diff "$1" "$1.post")"
  if [ -z "$d" ]; then log "RESTORE-VERIFY: PASS — every snapshotted knob reads its pre-run value"; return 0; fi
  log "RESTORE-VERIFY: FAIL — differences (pre < > post):"
  printf '%s\n' "$d" | head -40 | while read -r l; do log "    $l"; done
  return 1
}

foreign_perf(){ local p; for p in $(pgrep -x perf 2>/dev/null); do
  [ "$(stat -c %u "/proc/$p" 2>/dev/null)" != "$(id -u)" ] && { echo "$p"; return 0; }; done; return 1; }
foreign_perf_wait(){
  local p; p=$(foreign_perf) || return 0
  log "PERF-GATE: perf pid $p belongs to another user — waiting (never killed)"
  while foreign_perf >/dev/null; do sleep 30; done
  log "PERF-GATE: foreign perf gone"
}
quiet_wait(){
  log "QUIET-GATE: waiting until no other user's task is busy for ${FF_QUIET_HOLD}s"
  python3 "$KITD/quiet_gate.py" wait --hold "$FF_QUIET_HOLD" --poll 10 --mine $$ >> "$SESS/quiet.log" 2>&1
  log "QUIET-GATE: $(tail -1 "$SESS/quiet.log")"
}

sysctl_apply(){
  [ -n "$FF_MAX_SAMPLE_RATE$FF_CPU_TIME_PCT" ] || return 0
  printf 'perf_event_max_sample_rate\t%s\nperf_cpu_time_max_percent\t%s\n' \
    "$(cat /proc/sys/kernel/perf_event_max_sample_rate)" "$(cat /proc/sys/kernel/perf_cpu_time_max_percent)" > "$SESS/pre_sysctl.tsv"
  # rate before percent: the kernel refuses a rate write once dynamic throttling is disabled
  [ -n "$FF_MAX_SAMPLE_RATE" ] && sudo sysctl -q -w kernel.perf_event_max_sample_rate="$FF_MAX_SAMPLE_RATE"
  [ -n "$FF_CPU_TIME_PCT" ]    && sudo sysctl -q -w kernel.perf_cpu_time_max_percent="$FF_CPU_TIME_PCT"
  log "SYSCTL: perf_event_max_sample_rate=$(cat /proc/sys/kernel/perf_event_max_sample_rate) perf_cpu_time_max_percent=$(cat /proc/sys/kernel/perf_cpu_time_max_percent) for this session"
}
sysctl_restore(){
  [ -f "$SESS/pre_sysctl.tsv" ] || return 0
  local k v
  # percent first, then rate (reverse of the apply order)
  while read -r k v; do sudo sysctl -q -w "kernel.$k=$v" >/dev/null; done < <(tac "$SESS/pre_sysctl.tsv")
  log "SYSCTL: restored ($(tr '\n\t' ' =' < "$SESS/pre_sysctl.tsv"))"
  rm -f "$SESS/pre_sysctl.tsv"
}

mslice_restore(){ # $1 pre-state file
  if [ -z "$(sed -n "s/^allowed_$MSLICE\t//p" "$1")" ] && [ -n "$(systemctl show "$MSLICE" -p AllowedCPUs --value)" ]; then
    sudo systemctl revert "$MSLICE" >/dev/null 2>&1 && log "ISOLATION: $MSLICE reverted to no AllowedCPUs (its pre-run state)"
  fi
  if [ "$(sed -n "s/^active_$MSLICE\t//p" "$1")" = inactive ] \
     && [ -z "$(find "/sys/fs/cgroup/$MSLICE" -name cgroup.procs -exec cat {} + 2>/dev/null)" ]; then
    sudo systemctl stop "$MSLICE" 2>/dev/null && log "ISOLATION: $MSLICE stopped (inactive before the run)"
  fi
}

leftovers(){ # $1 suite, $2 workload: our scope and our client processes, if the pass died
  local u p
  for u in $(systemctl list-units --type=scope --no-legend --plain "$1-$2-r*.scope" 2>/dev/null | awk '{print $1}'); do
    log "LEFTOVER: stopping $u"; sudo systemctl stop "$u"
  done
  for p in $(pgrep -u "$(id -u)" -f 'realdata-infra/(ycsb|kafka)|neo4j_client.py|DriverNodeRank' 2>/dev/null); do
    [ "$p" = $$ ] && continue
    log "LEFTOVER: client pid $p ($(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null | cut -c1-80))"; kill -TERM "$p" 2>/dev/null
  done
}

video_cleanup(){
  if [ -L "$VT_DIR/datasets/cuts" ] && [ -d "$VT_DIR/datasets/cuts_1080p_xiph" ]; then
    sudo rm -f "$VT_DIR/datasets/cuts" && sudo mv "$VT_DIR/datasets/cuts_1080p_xiph" "$VT_DIR/datasets/cuts" \
      && log "VIDEO: datasets/cuts restored to the original 1080p directory"
  fi
  if [ -n "$(ls -A "$VT_DIR/resized_clips" 2>/dev/null)" ]; then
    log "VIDEO: removing $(du -sh "$VT_DIR/resized_clips" | cut -f1) of resized_clips scratch (empty before the run)"
    sudo find "$VT_DIR/resized_clips" -mindepth 1 -delete
  fi
}

trap 'sysctl_restore' EXIT
trap 'exit 130' INT TERM

WLS=("$@"); [ "${WLS[0]:-}" = all ] && WLS=("${ALL[@]}")
[ ${#WLS[@]} -gt 0 ] || { sed -n '2,20p' "$0"; exit 1; }
for w in "${WLS[@]}"; do wl_spec "$w" >/dev/null || { echo "unknown workload $w"; exit 1; }; done
log "================ Server passes [$FF_GROUPS] -> $FF_SUBDIR: ${WLS[*]} (session $SESS) ================"
sysctl_apply
okc=0; failc=0
for w in "${WLS[@]}"; do
  IFS='|' read -r fam tmo envs <<< "$(wl_spec "$w")"
  DR="$REPO/local_agents/$fam/data/$FF_SUBDIR"
  suite=$(sed -n 's/.*SUITE=\([^ ]*\).*/\1/p' <<< "$envs")
  avail=$(df -BG --output=avail "$REPO" | tail -1 | tr -dc '0-9')
  if [ "${avail:-0}" -lt "$FF_DISK_MIN_G" ]; then log "STOP: only ${avail}G free (< ${FF_DISK_MIN_G}G) before $w"; break; fi
  if [ -f "$DR/${suite}_$w/run_$NG/DONE" ] && [ "$(ls "$DR/${suite}_$w"/run_*/DONE 2>/dev/null | wc -l)" = "$NG" ]; then
    log "skip $w — DONE"; okc=$((okc+1)); continue; fi
  foreign_perf_wait
  quiet_wait
  PRE="$SESS/pre_state.$w.tsv"; machine_state > "$PRE"
  # inputs as found (the stores carry the counter campaign's updates; recorded, not rebuilt)
  case "$w" in
    cassandra-ycsb20m) inp="$(sudo du -sb "$HOME/realdata-infra/cassandra/data" | cut -f1) B cassandra/data";;
    kafka-20g)         inp="$(sudo du -sb "$HOME/realdata-infra/kafka/data" | cut -f1) B kafka/data";;
    neo4j-livejournal) inp="$(sudo du -sb "$HOME/realdata-infra/neo4j/data/databases/livejournal" | cut -f1) B neo4j store";;
    *) inp="";;
  esac
  [ -n "$inp" ] && { log "INPUT STATE $w: $inp"; mkdir -p "$DR"; printf '%s\t%s\t%s\n' "$(date -Is)" "$w" "$inp" >> "$DR/input_state.tsv"; }
  log "---------------- $w ($envs, DATA_ROOT=${DR#$REPO/}, timeout ${tmo}s) ----------------"
  # shellcheck disable=SC2086
  pg=0; [ "$FF_GROUPS" = lbr ] || pg=1
  env $envs PROF_GROUPS="$FF_GROUPS" PASS_GATES=$pg DATA_ROOT="$DR" FF_MINE_PID=$$ \
    timeout "$tmo" bash "$KITD/run_dcperf_profile.sh" >> "$SESS/orchestrator.$w.log" 2>&1
  rc=$?
  log "$w: orchestrator exit $rc"
  leftovers "$suite" "$w"
  [ "$w" = video-4k ] && video_cleanup
  mslice_restore "$PRE"
  verify_restored "$PRE" || { log "STOP: machine not restored after $w — fix before continuing"; exit 1; }
  if [ "$(ls "$DR/${suite}_$w"/run_*/DONE 2>/dev/null | wc -l)" = "$NG" ]; then okc=$((okc+1)); log "PASS-OK $w"
  else failc=$((failc+1)); log "PASS-FAIL $w (see $SESS/orchestrator.$w.log and $DR/${suite}_$w/run_*)"; fi
done
log "================ done: $okc ok, $failc failed ================"
