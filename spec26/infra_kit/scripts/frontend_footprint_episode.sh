#!/usr/bin/env bash
# frontend_footprint_episode.sh — Rahul's three front-end metrics for SPEC CPU 2026, under
# the campaign's fence and shield: instruction footprint (unique 64 B lines x 64), unique
# taken branches, and the execution-weighted average number of targets per taken branch.
# The contract (event, period, branch filter, scope, analyzer) is fixed in InferSuite
# docs/handoff/execution/frontend_footprint_method.md and shared with the Server and
# Agentic runs; change nothing here that the contract fixes.
#
#   ./frontend_footprint_episode.sh [bench...]   default: all 26 rate benchmarks, index 0
#   ./frontend_footprint_episode.sh 767.nest_r@1 "<bench>@<k>" runs ref command line k and
#                                                keeps the episode as $DATA_ROOT/<bench>@<k>
#   PERIOD=5003 DATA_ROOT=<other root> ./frontend_footprint_episode.sh <bench>...
#                                                V3 period sensitivity
#
# Reused, by sourcing run_spec_campaign.sh: the partition, the shield + ISO-PROOF
# (apply_isolation), restore_isolation, setup_bench, extract_cmd.py, clean_rundir.py,
# verify_output.py, write_metadata and the cpu.stat pollers. Copied from
# llc_dram_crosscheck.sh (it runs on source): the pre_cpuset.tsv restore wrapper,
# quiet_wait, the 2 s witness and the contaminated() rule.
# What differs is only the instruments, and how the benchmark starts. The fence first
# holds a bash parked on a FIFO; one LBR sampling record and one exact perf stat are
# started DISABLED on the fence, enabled and acknowledged through their control FIFOs,
# and only then is the benchmark released. The window is therefore benchmark start to
# exit, with nothing of the benchmark executed before the counters were live. No
# windowed rotation, no 99 Hz record, no continuous TMA: fewer PMU users, cleaner LBR.
#
# After each episode: SPEC's output check, metadata.json, the witness verdict, then
# perf script | lbr_footprint, the hygiene gates (lost < 1 %, samples x period matches the
# exact taken-branch count, occupancy, exit status), and only if all passed is lbr.data
# deleted. The shield is restored on any exit and the restore is then VERIFIED against a
# snapshot taken before the shield went up.
set -o pipefail
XKIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export DATA_ROOT="${DATA_ROOT:-$(cd "$XKIT/.." && pwd)/data_frontend_footprint}"
# The runner's own dispatch runs on source; "help" makes it print usage, discarded here.
# shellcheck disable=SC1091
source "$XKIT/run_spec_campaign.sh" help >/dev/null
LOGF="$INFRA/logs/frontend_footprint.log"

# ---- the contract (frontend_footprint_method.md §3) ----------------------------------
PERIOD="${PERIOD:-20011}"                    # prime; same for SPEC, Server and Agentic
FF_EVENT="br_inst_retired.near_taken:pp"     # no :u/:k — user + kernel. :pp (contract v1.1): the
# LBR snapshot is written by PEBS at the overflowing branch, not at the skidded PMI; without it
# gate V1 read the weighted averages 1.8-3.7 % low (skid in instructions spans more branches in
# branch-dense code, so some 32-branch windows were systematically more likely than others).
FF_FILTER="any,save_type"
FF_MMAP="${FF_MMAP:-512M}"
# cycles is a fixed counter (no GP cost); it is added to the contract's pair so an IPC
# cross-check against the August campaign exists for the output-unverifiable benchmarks.
STAT_EVENTS="cycles,instructions,br_inst_retired.near_taken"
LOST_MAX_PCT=1
# |samples x period / exact taken - 1|. 0.005: production (n=26) and clean V3 sat within 0.001,
# while the throttled V3 attempt read 0.9896-0.9993 and still passed the original 0.02.
COVER_TOL="${COVER_TOL:-0.005}"
DISK_MIN_G="${DISK_MIN_G:-20}"               # one episode's perf.data is 1-3 GB
ANALYZER="${ANALYZER:-$INFRA/bin/lbr_footprint}"
ANALYZER_SHA="${ANALYZER_SHA:-$(cat "$ANALYZER.sha" 2>/dev/null)}"
ZSTD="$(command -v zstd)"
# The kernel throttles any sampling event above perf_event_max_sample_rate/HZ samples per
# tick (100 at the default 100000 and HZ=1000) and lowers that rate itself when PMIs take
# more than perf_cpu_time_max_percent of CPU. A loop retiring one taken branch per cycle
# at 3.2 GHz is 160 k samples/s at -c 20011 (640 k at -c 5003): throttling would drop
# samples exactly in hot phases and bias the unique counts. Opt-in override for the
# session, snapshotted, restored and verified like every shield knob; the
# samples x period vs exact-count gate detects throttling either way.
FF_MAX_SAMPLE_RATE="${FF_MAX_SAMPLE_RATE:-}"
FF_CPU_TIME_PCT="${FF_CPU_TIME_PCT:-}"

if [ "${1:-}" = -h ] || [ "${1:-}" = --help ]; then sed -n '2,30p' "${BASH_SOURCE[0]}"; exit 0; fi
BENCHES=("$@")
[ ${#BENCHES[@]} -gt 0 ] || BENCHES=("${SPEC_RATE_BENCHES[@]}")
SESS="$DATA_ROOT/_session"; n=2
while [ -e "$SESS" ]; do SESS="$DATA_ROOT/_session.$n"; n=$((n+1)); done
mkdir -p "$SESS"
GATE=(python3 "$XKIT/quiet_gate.py")
WIT_PID=""; FF_REC_PID=""; FF_STAT_PID=""

# restore_isolation() puts back each slice's systemd AllowedCPUs snapshot, and turns an
# EMPTY snapshot into "all online CPUs" (validation doc §1.5): it widened system/user/init
# to 0-15 on 2026-10-26. Put back any effective cpuset the restore changed, and give
# measured.slice back the "no AllowedCPUs at all" it had before the shield (the stock
# restore leaves it pinned to 0-15) by reverting its set-property drop-in.
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
  # It was not even active before the shield (no cgroup). Our scopes have exited by now;
  # stop the slice only if nothing at all is left in it.
  if [ "$(cat "$SESS/pre_mslice_active" 2>/dev/null)" = inactive ] \
     && [ -z "$(find "/sys/fs/cgroup/$MSLICE" -name cgroup.procs -exec cat {} + 2>/dev/null)" ]; then
    sudo systemctl stop "$MSLICE" 2>/dev/null && log "ISOLATION: $MSLICE stopped (inactive before the shield)"
  fi
}

# Every knob the shield touches, one "key<TAB>value" per line. Snapshotted before the
# shield and compared after the restore: "restored" is a claim that needs evidence.
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

ff_cleanup(){
  [ -n "$WIT_PID" ] && kill "$WIT_PID" 2>/dev/null
  ff_stop_instruments
  if [ -f "$SESS/pre_sysctl.tsv" ]; then
    local k v
    # percent first: the kernel refuses a rate write while dynamic throttling is disabled (0/100)
    while read -r k v; do sudo sysctl -q -w "kernel.$k=$v" >/dev/null; done < <(tac "$SESS/pre_sysctl.tsv")
    log "SYSCTL: perf sampling limits restored ($(tr '\n' ' ' < "$SESS/pre_sysctl.tsv"))"
    rm -f "$SESS/pre_sysctl.tsv"
  fi
}
trap 'rc=$?; ff_cleanup; (exit $rc); cleanup; verify_restored' EXIT

quiet_wait(){ # $1 seconds of continuous quiet required
  log "QUIET-GATE: waiting until no other user's process is busy for $1 s"
  "${GATE[@]}" wait --hold "$1" --poll 10 --mine $$ >> "$SESS/quiet.log" 2>&1
  log "QUIET-GATE: $(tail -1 "$SESS/quiet.log")"
}

# A perf owned by another user holding hardware counters shares our cores' PMU, and LBR
# is per-core hardware: both captures would be corrupted. Wait it out; never kill it.
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

# Did foreign work overlap [t0, t1]? Copied from llc_dram_crosscheck.sh, unchanged.
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

# ---- instruments --------------------------------------------------------------------
ff_enable(){ # $1 fifo prefix: write "enable", require perf's "ack" (it is then counting)
  timeout 60 bash -c 'echo enable > "$1.ctl" && read -r a < "$1.ack" && [ "$a" = ack ]' _ "$1"
}
ff_stop_instruments(){ # SIGINT: perf record writes its file, perf stat its final counts
  local p
  for p in $FF_REC_PID $FF_STAT_PID; do kill -INT "$p" 2>/dev/null; done
  [ -n "$FF_REC_PID" ]  && { wait "$FF_REC_PID" 2>/dev/null;  FF_REC_RC=$?; }
  [ -n "$FF_STAT_PID" ] && { wait "$FF_STAT_PID" 2>/dev/null; FF_STAT_RC=$?; }
  FF_REC_PID=""; FF_STAT_PID=""
}

# ---- one capture (no analysis) --------------------------------------------------------
# Mirrors run_episode() in run_spec_campaign.sh step for step, except for the gate and
# the instruments. Sets FF_T0/FF_T1 (release, exit) for the witness verdict.
ff_capture(){ # $1 bench
  local B="$1" SHORT="${1#*.}"; SHORT="${SHORT%_r}"
  local OUT="$DATA_ROOT/$B"
  FF_T0=""; FF_T1=""; FF_REC_RC=""; FF_STAT_RC=""
  bench_is_built "$B" || { log "EPISODE SKIP $B: no binary"; return 1; }
  setup_bench "$B" || return 1
  local RD; RD="$(rundir_of "$B")"
  mkdir -p "$OUT"; rm -rf "${OUT:?}"/*
  local NC; NC="$(SPEC_ROOT="$SPEC_ROOT" python3 "$KIT/extract_cmd.py" "$RD" "$OUT")" || {
    log "EPISODE FAIL $B: command extraction failed"; return 1; }
  CUR_IDX="$(cmd_index_for "$B")"
  local CMD; CMD="$(sed -n "$((CUR_IDX + 1))p" "$OUT/speccmds_all.txt")"
  [ -n "$CMD" ] || { log "EPISODE FAIL $B: no command at index $CUR_IDX (n=$NC)"; return 1; }
  log "================ $B ($NC ref command line(s), running index $CUR_IDX, period $PERIOD) ================"
  local NCLEAN; NCLEAN="$(python3 "$KIT/clean_rundir.py" "$RD" 2>/dev/null || echo 0)"
  [ "${NCLEAN:-0}" = 0 ] || log "  run dir reset: removed $NCLEAN generated file(s) from previous runs"

  local UNIT="spec-${SHORT}" CG="$MSLICE/spec-${SHORT}.scope" f
  sudo systemctl stop "$UNIT.scope" 2>/dev/null
  sudo systemctl reset-failed "$UNIT.scope" 2>/dev/null
  for f in go rec.ctl rec.ack stat.ctl stat.ack; do mkfifo "$OUT/$f" || return 1; done

  RAN_WORK=1; CUR_UNIT="$UNIT"
  # open() of a FIFO blocks until a writer appears: the fence holds one sleeping bash and
  # executes nothing until the counters are live. Then the same exec chain as run_episode.
  sudo systemd-run --collect --scope --slice="$MSLICE" --unit="$UNIT" \
       -p AllowedCPUs="$CPUS_MEASURED" -p CPUAccounting=yes -p MemoryAccounting=yes -- \
       runuser -u "$USER" -- bash -c "read -r _ < '$OUT/go'; cd '$RD' && set -a && . '$OUT/env.sh' && set +a && exec $CMD" \
       > "$OUT/bench.log" 2>&1 &
  local LAUNCH_PID=$! i
  for i in $(seq 1 60); do [ -d "/sys/fs/cgroup/$CG" ] && break; sleep 0.5; done
  [ -d "/sys/fs/cgroup/$CG" ] || { log "EPISODE FAIL $B: scope never appeared"; CUR_UNIT=""; return 1; }

  FF_REC_CMD="$PERF record -z -m $FF_MMAP -e $FF_EVENT -c $PERIOD -j $FF_FILTER -a -C $CPUS_MEASURED --cgroup=$CG -D -1 --control=fifo:rec.ctl,rec.ack -o lbr.data"
  FF_STAT_CMD="$PERF stat -x, -a -C $CPUS_MEASURED -e $STAT_EVENTS --for-each-cgroup=$CG -D -1 --control=fifo:stat.ctl,stat.ack -o exact_counts.csv"
  taskset -c "$CPUS_HOUSE" "$PERF" record -z -m "$FF_MMAP" -e "$FF_EVENT" -c "$PERIOD" -j "$FF_FILTER" \
      -a -C "$CPUS_MEASURED" --cgroup="$CG" -D -1 --control="fifo:$OUT/rec.ctl,$OUT/rec.ack" \
      -o "$OUT/lbr.data" > "$OUT/perf_record.log" 2>&1 &
  FF_REC_PID=$!
  taskset -c "$CPUS_HOUSE" "$PERF" stat -x, -a -C "$CPUS_MEASURED" -e "$STAT_EVENTS" \
      --for-each-cgroup="$CG" -D -1 --control="fifo:$OUT/stat.ctl,$OUT/stat.ack" \
      -o "$OUT/exact_counts.csv" > "$OUT/perf_stat.log" 2>&1 &
  FF_STAT_PID=$!
  if ! ff_enable "$OUT/rec" || ! ff_enable "$OUT/stat"; then
    log "EPISODE FAIL $B: perf did not acknowledge enable (perf_record.log / perf_stat.log)"
    ff_stop_instruments; sudo systemctl stop "$UNIT.scope" 2>/dev/null
    wait "$LAUNCH_PID" 2>/dev/null; CUR_UNIT=""; return 1
  fi
  write_metadata "$OUT" "$B" "$CG" "$NC" "$CMD" "$EPOCHREALTIME"
  WINSEC=1 start_pollers "$OUT" "$CG"           # WINSEC=1 -> 10 Hz, as the contract says
  FF_T0=$EPOCHREALTIME
  timeout 10 bash -c 'echo go > "$1"' _ "$OUT/go" || {
    log "EPISODE FAIL $B: could not release the benchmark"
    ff_stop_instruments; stop_pollers "$OUT"; sudo systemctl stop "$UNIT.scope" 2>/dev/null
    wait "$LAUNCH_PID" 2>/dev/null; CUR_UNIT=""; return 1; }

  local ALIVE="systemctl is-active --quiet $UNIT.scope" t0=$SECONDS
  while eval "$ALIVE" 2>/dev/null && [ $((SECONDS - t0)) -lt "$EPISODE_MAX_S" ]; do sleep 0.2; done
  FF_T1=$EPOCHREALTIME
  ff_stop_instruments; stop_pollers "$OUT"
  local BRC=0; wait "$LAUNCH_PID" 2>/dev/null || BRC=$?
  sudo systemctl stop "$UNIT.scope" 2>/dev/null; CUR_UNIT=""
  rm -f "$OUT/go" "$OUT"/rec.ctl "$OUT"/rec.ack "$OUT"/stat.ctl "$OUT"/stat.ack
  [ "$BRC" = 0 ] && log "  exit status: 0" || log "  WARN: benchmark exited $BRC (see $OUT/bench.log)"

  # SPEC's own correctness check, outside the fence and after every counter stopped.
  local VJ; VJ="$(SPEC_ROOT="$SPEC_ROOT" python3 "$KIT/verify_output.py" "$RD" "$FF_T0" "$CUR_IDX" 2>/dev/null)" || VJ='{"status":"error"}'
  case "$VJ" in
    *'"status": "pass"'*) log "  output check: PASS" ;;
    *'"status": "fail"'*) log "  WARN: output check FAILED — specdiff reports a mismatch" ;;
    *)                    log "  output check: $(printf '%s' "$VJ" | head -c 200)" ;;
  esac
  OUT="$OUT" T0="$FF_T0" T1="$FF_T1" BRC="$BRC" VJ="$VJ" PERIOD="$PERIOD" \
  REC_RC="${FF_REC_RC:-?}" STAT_RC="${FF_STAT_RC:-?}" REC_CMD="$FF_REC_CMD" STAT_CMD="$FF_STAT_CMD" \
  PERFV="$("$PERF" --version)" EV="$FF_EVENT" FILT="$FF_FILTER" STATEV="$STAT_EVENTS" \
  MAXRATE="$(cat /proc/sys/kernel/perf_event_max_sample_rate)" python3 - <<'PY'
import json, os
E = os.environ
p = f"{E['OUT']}/metadata.json"
m = json.load(open(p))
t0, t1 = float(E["T0"]), float(E["T1"])
m.update(ts_start=t0, ts_end=t1, wall_s=t1 - t0, bench_exit_status=int(E["BRC"]))
try:
    m["output_check"] = json.loads(E["VJ"])
except Exception:
    m["output_check"] = {"status": "error", "detail": E["VJ"][:200]}
# write_metadata describes the August instrument set; overwrite what does not apply here.
m.update(winsec=None, gorder=None, rotation=None, tma_cont=False,
         instruments=["LBR perf record (fence cgroup, measured cores)",
                      "perf stat exact counts (same fence, same interval)",
                      "cpu.stat 10Hz", "procstat witness"])
m["frontend_footprint"] = {
    "contract": "docs/handoff/execution/frontend_footprint_method.md v1.1",
    "event": E["EV"], "period": int(E["PERIOD"]), "branch_filter": E["FILT"],
    "scope": "perf record -a -C <measured> --cgroup=<fence>", "stat_events": E["STATEV"],
    "window": "benchmark released from a FIFO gate after both perf instances acknowledged enable, to scope exit",
    "perf_version": E["PERFV"], "perf_record_cmd": E["REC_CMD"], "perf_stat_cmd": E["STAT_CMD"],
    "perf_record_rc": E["REC_RC"], "perf_stat_rc": E["STAT_RC"],
    "perf_event_max_sample_rate": int(E["MAXRATE"]),
}
json.dump(m, open(p, "w"), indent=1)
PY
  return 0
}

# ---- analysis + hygiene gates ---------------------------------------------------------
ff_finish(){ # $1 bench dir name -> 0 and DONE if every gate passed
  local OUT="$DATA_ROOT/$1" t0=$EPOCHREALTIME
  [ -s "$OUT/lbr.data" ] || { log "  FAIL: no lbr.data"; return 1; }
  taskset -c "$CPUS_HOUSE" "$PERF" report -i "$OUT/lbr.data" --stats > "$OUT/perf_report_stats.txt" 2>&1
  taskset -c "$CPUS_HOUSE" "$PERF" script -i "$OUT/lbr.data" -F pid,brstack \
      --show-mmap-events --show-task-events --show-lost-events 2> "$OUT/perf_script.err" \
    | taskset -c "$CPUS_HOUSE" "$ANALYZER" --mode lbr --analyzer-sha "$ANALYZER_SHA" \
      --summary "$OUT/analyzer.json" --edges "$OUT/edges.tsv" --objects "$OUT/objects.tsv" \
      --lines "$OUT/lines.tsv" --meta workload="${1%@*}" --meta period="$PERIOD" \
      > "$OUT/analyzer.log" 2>&1
  local arc=$?
  log "  analysis: rc=$arc in $(awk -v a="$t0" -v b="$EPOCHREALTIME" 'BEGIN{printf "%.0f", b-a}') s"
  local occ; occ=$(python3 - "$OUT" <<'PY'
import sys
rows = []
try:
    for ln in open(f"{sys.argv[1]}/cpustat_scope1.tsv"):
        p = ln.split()
        if len(p) >= 3 and p[1] == "usage_usec" and int(p[2]) >= 0:   # drop the -1 sentinels
            rows.append((float(p[0]), int(p[2])))
except OSError:
    pass
print(f"{(rows[-1][1]-rows[0][1])/1e6/(rows[-1][0]-rows[0][0]):.3f}"
      if len(rows) > 1 and rows[-1][0] > rows[0][0] else "nan")
PY
)
  # Merge capture metadata, exact counts and the analyzer's summary into summary.json and
  # judge the hygiene gates (contract §5 V4). Every verdict is banked, pass or fail.
  OUT="$OUT" ARC="$arc" OCC="$occ" PERIOD="$PERIOD" LOSTMAX="$LOST_MAX_PCT" TOL="$COVER_TOL" \
  MAXC="$MAX_MEAN_CORES" python3 - <<'PY'
import csv, json, os, sys
E = os.environ; out = E["OUT"]
m = json.load(open(f"{out}/metadata.json"))
try:
    a = json.load(open(f"{out}/analyzer.json"))
except Exception as e:
    a = {"error": str(e)}
exact = {}
for row in csv.reader(open(f"{out}/exact_counts.csv")):
    if len(row) > 3 and row[0] and not row[0].startswith("#"):
        try: exact[row[2]] = float(row[0])
        except ValueError: exact[row[2]] = None
period = int(E["PERIOD"])
# perf's own record counts: THROTTLE means the kernel suppressed samples (hot phases
# under-sampled), LOST means the ring buffer overflowed. Both bias the unique counts.
stats = {}
try:
    for ln in open(f"{out}/perf_report_stats.txt"):
        p = ln.split()
        if len(p) >= 3 and p[1] == "events:" and p[2].isdigit():
            stats[p[0]] = int(p[2])
except OSError:
    pass
d = a.get("diagnostics", a)
samples = d.get("samples")
lost = d.get("lost_samples", 0) or 0
taken = exact.get("br_inst_retired.near_taken")
cover = samples * period / taken if samples and taken else None
lost_pct = 100.0 * lost / (samples + lost) if samples else None
occ = float(E["OCC"]) if E["OCC"] != "nan" else None
oc = m.get("output_check", {}).get("status")
g = {
  "analyzer_ok": E["ARC"] == "0" and "error" not in a,
  "exit_status_0": m.get("bench_exit_status") == 0,
  "output_check": oc,
  "output_ok": oc in ("pass", "unavailable"),
  "lost_pct": lost_pct, "lost_ok": lost_pct is not None and lost_pct < float(E["LOSTMAX"]),
  "sample_coverage": cover,
  "coverage_ok": cover is not None and abs(cover - 1) <= float(E["TOL"]),
  "mean_cores": occ, "occupancy_ok": occ is not None and occ <= float(E["MAXC"]),
  "perf_record_stats": stats,
  "throttle_events": stats.get("THROTTLE", 0),
  "throttle_ok": stats.get("THROTTLE", 0) == 0 and bool(stats),
  "witness": m.get("foreign_witness"),
  "iso_proof": m.get("iso_proof"),
}
g["all_ok"] = all(g[k] for k in ("analyzer_ok", "exit_status_0", "output_ok", "lost_ok",
                                 "coverage_ok", "occupancy_ok", "throttle_ok"))
m["mean_cores"] = E["OCC"]
json.dump(m, open(f"{out}/metadata.json", "w"), indent=1)
s = dict(a)
s["workload"] = m["benchmark"] + ("" if m.get("cmd_index", 0) == 0 else f"@{m['cmd_index']}")
s["capture"] = {k: m.get(k) for k in ("benchmark", "cmd_index", "command", "wall_s", "ts_start",
                "ts_end", "bench_exit_status", "output_check", "binary_sha256_16", "kit_rev",
                "cpus_measured", "governor", "no_turbo", "smt", "iso_proof", "foreign_witness",
                "frontend_footprint")}
s["exact_counts"] = exact
s["gates_v4"] = g
json.dump(s, open(f"{out}/summary.json", "w"), indent=1)
fmt = lambda v, f: (f % v) if isinstance(v, (int, float)) else str(v)
print(f"lost={fmt(lost_pct,'%.3f')}% coverage={fmt(cover,'%.4f')} cores={E['OCC']} "
      f"throttle={g['throttle_events']} output={oc} exit={m.get('bench_exit_status')} analyzer={'ok' if g['analyzer_ok'] else 'FAIL'}"
      f" -> {'ALL OK' if g['all_ok'] else 'GATE FAILED'}")
sys.exit(0 if g["all_ok"] else 1)
PY
  local grc=$?
  log "  gates: $(python3 -c 'import json,sys;g=json.load(open(sys.argv[1]))["gates_v4"];print({k:g[k] for k in ("lost_pct","sample_coverage","throttle_events","mean_cores","output_check","all_ok")})' "$OUT/summary.json" 2>/dev/null)"
  python3 - "$OUT/summary.json" <<'PY' | while read -r l; do log "  $l"; done
import json, sys
s = json.load(open(sys.argv[1]))
def g(*ks):
    v = s
    for k in ks:
        v = v.get(k) if isinstance(v, dict) else None
    return v
print(f"footprint={g('footprint_bytes')} B (user {g('footprint_bytes_user')}, kernel {g('footprint_bytes_kernel')})"
      f" unique_taken={g('unique_taken_branches')} wavg_all={g('wavg_targets_all')}"
      f" wavg_noret={g('wavg_targets_noret')} wavg_ind={g('wavg_targets_indirect')}")
c = g("convergence")
if c:
    print(f"convergence: {json.dumps(c)[:300]}")
PY
  [ $grc = 0 ] || { log "  EPISODE-FAIL $1 (lbr.data kept for inspection)"; return 1; }
  local f
  for f in edges.tsv objects.tsv lines.tsv; do
    [ -f "$OUT/$f" ] && "$ZSTD" -q -f --rm -T2 "$OUT/$f"
  done
  rm -f "$OUT/lbr.data"
  log "EPISODE-OK $1"; touch "$OUT/DONE"; return 0
}

disk_ok(){
  local avail; avail=$(df -BG --output=avail "$DATA_ROOT" | tail -1 | tr -dc '0-9')
  [ "${avail:-0}" -ge "$DISK_MIN_G" ] && return 0
  log "ABORT: only ${avail}G free under $DATA_ROOT (need >= ${DISK_MIN_G}G)"; return 1
}

# ---------------- run ----------------------------------------------------------------
log "================ front-end footprint: ${BENCHES[*]} (period $PERIOD) ================"
log "data: $DATA_ROOT  analyzer: $ANALYZER @ ${ANALYZER_SHA:-UNKNOWN}  perf: $PERF"
[ -x "$ANALYZER" ] || { log "ABORT: analyzer $ANALYZER missing"; exit 1; }
[ -n "$ANALYZER_SHA" ] || { log "ABORT: no analyzer SHA ($ANALYZER.sha) — commit the analyzer first"; exit 1; }
[ -n "$ZSTD" ] || { log "ABORT: zstd not on PATH"; exit 1; }
disk_ok || exit 1
for b in "${BENCHES[@]}"; do setup_bench "${b%@*}" || exit 1; done

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
if [ -n "$FF_MAX_SAMPLE_RATE$FF_CPU_TIME_PCT" ]; then
  printf 'perf_event_max_sample_rate\t%s\nperf_cpu_time_max_percent\t%s\n' \
    "$(cat /proc/sys/kernel/perf_event_max_sample_rate)" "$(cat /proc/sys/kernel/perf_cpu_time_max_percent)" \
    > "$SESS/pre_sysctl.tsv"
  # rate first: the kernel refuses a rate write while dynamic throttling is disabled
  [ -n "$FF_MAX_SAMPLE_RATE" ] && sudo sysctl -q -w kernel.perf_event_max_sample_rate="$FF_MAX_SAMPLE_RATE"
  [ -n "$FF_CPU_TIME_PCT" ]    && sudo sysctl -q -w kernel.perf_cpu_time_max_percent="$FF_CPU_TIME_PCT"
  log "SYSCTL: perf_event_max_sample_rate=$(cat /proc/sys/kernel/perf_event_max_sample_rate) perf_cpu_time_max_percent=$(cat /proc/sys/kernel/perf_cpu_time_max_percent) for this session"
fi
"${GATE[@]}" witness --poll 2 --mine $$ --out "$SESS/witness.tsv" &
WIT_PID=$!

# "<bench>@<k>": cmd_index_for() takes the index from cmd_index.tsv, else SPEC_CMD_INDEX.
# Set the latter per item, refuse when a cmd_index.tsv row would override it, and move the
# episode to $DATA_ROOT/<bench>@<k> so the next input of the same benchmark starts clean.
IDX_DEFAULT="$SPEC_CMD_INDEX"; okc=0; failc=0
for item in "${BENCHES[@]}"; do
  b="${item%@*}"; idx=""; [ "$item" != "$b" ] && idx="${item#*@}"
  SPEC_CMD_INDEX="${idx:-$IDX_DEFAULT}"
  if [ -n "$idx" ] && [ "$(cmd_index_for "$b")" != "$idx" ]; then
    log "  $item: SKIP, cmd_index.tsv pins $b to index $(cmd_index_for "$b")"; continue
  fi
  [ -f "$DATA_ROOT/$item/DONE" ] && { log "skip $item (DONE)"; okc=$((okc+1)); continue; }
  disk_ok || { failc=$((failc+1)); break; }
  done_ok=0
  for try in 1 2 3; do
    foreign_perf_wait
    quiet_wait 60
    t0=$EPOCHREALTIME
    ff_capture "$b" || { [ -f "$DATA_ROOT/$b/metadata.json" ] || break; }
    [ -f "$DATA_ROOT/$b/metadata.json" ] || { log "  $item: no metadata.json, episode failed before capture"; break; }
    v="$(contaminated "$t0" "${FF_T1:-$EPOCHREALTIME}" "$DATA_ROOT/$b/metadata.json")"; crc=$?
    log "  witness: $v"
    np=$(foreign_hw_perf)
    if [ $crc = 0 ] || [ "${np:-0}" != 0 ]; then
      [ "${np:-0}" != 0 ] && log "  a foreign perf holding hardware counters appeared during the episode"
      rm -f "$DATA_ROOT/$b/lbr.data"
      mv "$DATA_ROOT/$b" "$DATA_ROOT/$item.contaminated.$try"
      log "  $item set aside (foreign work overlapped on attempt $try of 3)"
      continue
    fi
    [ -n "$idx" ] && mv "$DATA_ROOT/$b" "$DATA_ROOT/$item"
    ff_finish "$item" && done_ok=1
    break
  done
  [ $done_ok = 1 ] && okc=$((okc+1)) || failc=$((failc+1))
done
SPEC_CMD_INDEX="$IDX_DEFAULT"
log "================ front-end footprint done: $okc ok, $failc failed ================"
[ $failc = 0 ]
