#!/usr/bin/env bash
# run_dcperf_profile.sh — profile a DCPerf benchmark with the EXACT instrument stack used for
# the 36 SWE-bench-Multilingual tasks (ML_iso36), so the two families are directly comparable.
#
# It does not reimplement the method: it SOURCES the agent campaign runner
# (`run_glm_campaign.sh noop`, which defines functions only) and reuses, unchanged:
#   apply_isolation / restore_isolation  — cpuset split, governor, no_turbo, THP, IRQ pinning,
#                                          and the ISO-PROOF quiet gate (<2% busy on measured)
#   GRP[...]                             — the 9 zero-multiplexing counter groups
#   cycle_stats                          — the shuffled per-window perf-stat rotation
#   start_pollers / start_tma_cont       — 10 Hz cgroup cpu.stat + continuous PERF_METRICS TMA
#
# Difference vs an agent episode (documented in local_agents/DCPerf/README.md):
#   - SKIP_DOCKER=1: DCPerf benchmarks are native processes, no tool containers, so the docker
#     cgroup-parent swap is a no-op (and restarting dockerd would bounce unrelated containers).
#   - ONE fence: the benchmark's SERVER process ("server"), in measured.slice. The load
#     generator runs on the HOUSEKEEPING cores — exactly where the litellm proxy runs for the
#     agent campaigns, and for the same reason: it is the client, not the workload under test.
#   - Windows are captured over the benchmark's STEADY-STATE phase only (each bench module
#     defines when that begins), not over a whole episode: DCPerf workloads have an explicit
#     warm-up that an agent episode does not.
#
# One pass per counter group (dedicated-group capture => continuous-grade per-window series
# for that group), strictly serialized because the PMU is a shared resource.
#
#   BENCH=feedsim ./run_dcperf_profile.sh
#   BENCH=feedsim PROF_GROUPS="fpbr" CAPTURE_S=120 ./run_dcperf_profile.sh   # quick bring-up
set -o pipefail
KITD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$KITD/../../.." && pwd)"
BENCH="${BENCH:?bench module (feedsim|video_transcode|renaissance|dacapo)}"
# SUITE names the benchmark family and prefixes run dirs / scope units; WORKLOAD names one
# benchmark inside a multi-benchmark module (renaissance: finagle-http, dacapo: cassandra ...).
# DCPerf modules leave WORKLOAD unset, so their layout is unchanged: dcperf_feedsim/run_N.
SUITE="${SUITE:-dcperf}"
WL="${WORKLOAD:-$BENCH}"
export DCPERF_ROOT="${DCPERF_ROOT:-$HOME/dcperf-infra/DCPerf}"
export DATA_ROOT="${DATA_ROOT:-$REPO/local_agents/DCPerf/data}"
export WINSEC="${WINSEC:-0.1}"
export SKIP_DOCKER=1
PROF_GROUPS="${PROF_GROUPS:-fpbr cache mlp fe fe_lat core_ports dram_bw priv fe_miss}"
CAPTURE_S="${CAPTURE_S:-300}"          # steady-state seconds to window per pass
mkdir -p "$DATA_ROOT"

# functions only — no stage runs. Also installs the cleanup EXIT trap that restores isolation.
source "$REPO/local_agents/kit/campaign/run_glm_campaign.sh" noop
source "$KITD/bench_${BENCH}.sh"

dlog(){ printf '[%s %s] %s\n' "$SUITE" "$(date +%H:%M:%S)" "$*" | tee -a "$KITD/dcperf.log"; }

# SHARED MACHINE GUARD (same rule as replay_l3_profile.sh): the PMU is one shared resource;
# never compete with a colleague's collectors, never kill them. Checked at start (before any
# core is offlined) and again before every pass.
foreign_perf(){ for pp in $(pgrep -x perf 2>/dev/null); do
    [ "$(stat -c %u "/proc/$pp" 2>/dev/null)" != "$(id -u)" ] && { echo "$pp"; return 0; }; done; return 1; }

# SMT SIBLINGS. The iso36 captures ran with the measured cores' SMT siblings OFFLINE (an online
# sibling shares the core's front end and would make the families incomparable). This used to
# be a manual step gated by the check below; it is now done here, remembered, and undone by the
# EXIT trap -- so the environment no longer depends on anyone having prepared the box.
smt_siblings(){ python3 - "$CPUS_MEASURED" <<'PY'
import sys
def expand(spec):
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-"); out += list(range(int(a), int(b or a) + 1))
    return out
meas = set(expand(sys.argv[1])); sib = set()
for c in meas:
    try:
        sib |= set(expand(open(f"/sys/devices/system/cpu/cpu{c}/topology/thread_siblings_list").read().strip()))
    except OSError:
        pass
print(" ".join(str(c) for c in sorted(sib - meas)))
PY
}
SMT_OFFLINED=""
smt_off(){ local c; for c in $(smt_siblings); do
    if [ "$(cat /sys/devices/system/cpu/cpu$c/online 2>/dev/null)" = 1 ]; then
      echo 0 | sudo tee "/sys/devices/system/cpu/cpu$c/online" >/dev/null && SMT_OFFLINED="$SMT_OFFLINED $c"
    fi; done
  [ -n "$SMT_OFFLINED" ] && dlog "SMT siblings offlined:$SMT_OFFLINED (restored on exit)"; return 0; }
smt_restore(){ local c; for c in $SMT_OFFLINED; do echo 1 | sudo tee "/sys/devices/system/cpu/cpu$c/online" >/dev/null; done
  [ -n "$SMT_OFFLINED" ] && dlog "SMT siblings back online:$SMT_OFFLINED"; SMT_OFFLINED=""; return 0; }
trap 'smt_restore; cleanup' EXIT      # cleanup = the sourced kit's isolation restore

if fp=$(foreign_perf); then dlog "STOP: foreign perf pid $fp on the box — refusing to compete"; exit 3; fi
[ "${SMT_OFF:-1}" = 1 ] && smt_off

[ -n "$PERF" ] && [ -x "$PERF" ] || { dlog "FATAL: perf not found"; exit 1; }

# TOPOLOGY GATE — the same condition the agent campaign's preflight enforces, so the DCPerf
# numbers are captured on the identical partition the 36 tasks were: every measured core
# online with NO online SMT sibling (an online sibling shares the core's front end and would
# make the two families incomparable). Offlining is a manual step in this lab (it is for the
# agent campaigns too); this only VERIFIES it, and says how to fix it.
python3 - "$CPUS_MEASURED" <<'TOPO' || exit 1
import sys
def expand(spec):
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-"); out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out
bad = []
for c in expand(sys.argv[1]):
    try:
        if open(f"/sys/devices/system/cpu/cpu{c}/online").read().strip() != "1":
            bad.append(f"measured cpu{c} is OFFLINE"); continue
    except FileNotFoundError:
        pass
    try:
        sibs = open(f"/sys/devices/system/cpu/cpu{c}/topology/thread_siblings_list").read().strip()
    except OSError:
        continue
    for s in expand(sibs):
        if s == c:
            continue
        try:
            if open(f"/sys/devices/system/cpu/cpu{s}/online").read().strip() == "1":
                bad.append(f"measured cpu{c} has ONLINE SMT sibling cpu{s}")
        except OSError:
            pass
if bad:
    print("TOPOLOGY GATE FAIL:"); [print("   ", b) for b in bad]
    print("   fix: for c in <siblings>; do echo 0 | sudo tee /sys/devices/system/cpu/cpu$c/online; done")
    sys.exit(1)
print("topology gate OK: measured cores online, no online SMT siblings")
TOPO
bench_preflight || { dlog "FATAL: $BENCH preflight failed"; exit 1; }

NG=$(echo $PROF_GROUPS | wc -w); n=0
for g in $PROF_GROUPS; do
  n=$((n+1))
  OUT="$DATA_ROOT/${SUITE}_${WL}/run_${n}"
  if [ -f "$OUT/DONE" ] && [ "$(cat "$OUT/l3group.txt" 2>/dev/null)" = "$g" ]; then
    dlog "skip pass $n ($g) — DONE"; continue
  fi
  grep -q "^GRP\[$g\]=" "$REPO/local_agents/kit/campaign/run_glm_campaign.sh" \
    || { dlog "FATAL: unknown counter group '$g'"; exit 1; }

  # SHARED MACHINE GUARD — identical rule to replay_l3_profile.sh: the PMU's GP counters and
  # PERF_METRICS are one shared resource; running against a colleague's collectors corrupts
  # BOTH. Never kill theirs; just stop and leave completed passes banked.
  FOREIGN=$(for pp in $(pgrep -x perf 2>/dev/null); do
              [ "$(stat -c %u "/proc/$pp" 2>/dev/null)" != "$(id -u)" ] && echo "$pp"; done | head -1)
  if [ -n "$FOREIGN" ]; then
    dlog "STOP at pass $n/$NG ($g): foreign perf pid $FOREIGN on the box — refusing to compete"
    exit 3
  fi

  dlog "===== pass $n/$NG: group=$g -> run_$n ====="
  rm -rf "$OUT"; mkdir -p "$OUT"
  RAN_WORK=1
  apply_isolation || { dlog "FATAL: isolation/ISO-PROOF failed"; exit 1; }

  UNIT="${SUITE}-${WL}-r${n}"
  if ! bench_start "$OUT" "$UNIT"; then
    dlog "pass $n ($g) FAILED to reach steady state"; bench_stop "$OUT" "$UNIT"
    restore_isolation
    # "whatever works on first shot": a workload that cannot even reach steady state on its
    # FIRST pass is not going to on the next eight -- abort this workload, leave it undone
    if [ "$n" -eq 1 ]; then dlog "ABORT $SUITE/$WL: first pass could not start (see $OUT)"; exit 4; fi
    continue
  fi
  CG="$(cat "$OUT/.server_cg")"
  dlog "steady state reached; server fence = $CG"

  start_pollers "$OUT" "$CG"
  start_tma_cont "$OUT" "$CG"
  write_metadata "$OUT" "${SUITE}_${WL}" "$WL" "$n" \
    "{\"suite\":\"$SUITE\",\"bench\":\"$BENCH\",\"workload\":\"$WL\",\"server_cg\":\"$CG\",\"capture_s\":$CAPTURE_S,\"group\":\"$g\",\"load\":$(cat "$OUT/.load_json" 2>/dev/null || echo '{}')}"

  GORDER="$g" cycle_stats "$OUT" "$CG" "[ -d /sys/fs/cgroup/$CG ]" "$CAPTURE_S"

  stop_tma_cont; stop_pollers "$OUT"
  bench_stop "$OUT" "$UNIT"
  restore_isolation

  echo "$g" > "$OUT/l3group.txt"
  NW=$(($(wc -l < "$OUT/windows.tsv" 2>/dev/null || echo 1) - 1))
  if [ "$NW" -gt 10 ] && [ -s "$OUT/cpustat_scope1.tsv" ]; then
    : > "$OUT/DONE"; dlog "pass $n ($g) OK — $NW windows"
  else
    dlog "pass $n ($g) INCOMPLETE — $NW windows"
  fi
  sleep 20   # settle before the next pass
done
dlog "ALL PASSES DONE for $SUITE/$WL"
