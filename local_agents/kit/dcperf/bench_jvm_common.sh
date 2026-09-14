#!/usr/bin/env bash
# bench_jvm_common.sh — shared launcher for single-JVM benchmark suites (Renaissance, DaCapo).
#
# Both suites run the whole benchmark -- including any embedded "server" and its in-process
# clients (Finagle HTTP, Cassandra, Tomcat, Kafka ...) -- inside ONE JVM. That is why the
# mentor called them "easier and simpler": there is no load generator to keep off the measured
# partition, so the entire JVM is the workload and one fence covers it, exactly as for the
# VideoTranscodeBench batch.
#
# Steady state: JVM start + JIT warm-up is a variable-length ramp, so bench_start waits until
# the fence has been busy above JVM_MIN_CORES for JVM_STABLE_S consecutive seconds, then holds
# a further JVM_WARMUP_S before returning. The 10 Hz poller covers the whole capture, and the
# validator's steady-state gate (D4) checks the drift afterwards rather than trusting this.
JAVA="${JAVA:-java}"
JVM_MIN_CORES="${JVM_MIN_CORES:-1}"       # "busy" means at least this many cores ...
JVM_STABLE_S="${JVM_STABLE_S:-10}"        # ... averaged over this many 1 s samples (moving mean)
JVM_WARMUP_S="${JVM_WARMUP_S:-45}"        # then let the JIT settle for this long
# Why a moving MEAN and not "every sample busy": DaCapo cassandra (2026-09-14) ran perfectly --
# 40 iterations at ~36k req/s -- but each ~7.9 s iteration has a ~2.4 s lightly-loaded gap
# (database reload), so no 8 consecutive seconds were ever busy and the old rule never fired.
# Iteration-structured workloads (DaCapo, Spark stages) need the average, not the minimum.

jvm_launch(){ # $1 OUT, $2 UNIT, $3 logname, $4.. java args (after `java`)
  local OUT="$1" UNIT="$2" LOG="$3"; shift 3
  sudo systemctl stop "$UNIT.scope" 2>/dev/null; sudo systemctl reset-failed "$UNIT.scope" 2>/dev/null
  ( cd "$OUT" && sudo systemd-run --collect --scope --slice=measured.slice --unit="$UNIT" -- \
      taskset -c "$CPUS_MEASURED" "$JAVA" "$@" ) > "$OUT/$LOG" 2>&1 &
  JVM_RUN_PID=$!
  dlog "jvm launched: $JAVA $* (pid $JVM_RUN_PID)"
}

jvm_wait_steady(){ # $1 OUT, $2 UNIT  -> writes .server_cg, returns 0 at steady state
  local OUT="$1" UNIT="$2" CG="measured.slice/$2.scope" i ok=0 prev="" cur rate
  for i in $(seq 1 120); do [ -d "/sys/fs/cgroup/$CG" ] && break; sleep 1; done
  [ -d "/sys/fs/cgroup/$CG" ] || { dlog "jvm scope never appeared"; return 1; }
  echo "$CG" > "$OUT/.server_cg"
  local -a ring=(); local sum=0 n=0 cc
  for i in $(seq 1 900); do
    cur=$(head -3 "/sys/fs/cgroup/$CG/cpu.stat" 2>/dev/null | awk '/usage_usec/{print $2}')
    if [ -n "$prev" ] && [ -n "$cur" ]; then
      cc=$(( (cur - prev) / 10000 ))                  # centi-cores busy over the last ~1 s
      ring+=("$cc"); sum=$((sum + cc)); n=$((n + 1))
      if [ "$n" -gt "$JVM_STABLE_S" ]; then sum=$((sum - ring[0])); ring=("${ring[@]:1}"); n=$JVM_STABLE_S; fi
      if [ "$n" -ge "$JVM_STABLE_S" ] && [ "$sum" -ge $((JVM_STABLE_S * JVM_MIN_CORES * 100)) ]; then
        rate=$((sum / n / 100))
        dlog "jvm busy (~${rate} cores, ${JVM_STABLE_S}s mean); JIT warm-up hold ${JVM_WARMUP_S}s"
        sleep "$JVM_WARMUP_S"
        [ -d "/sys/fs/cgroup/$CG" ] || { dlog "jvm exited during warm-up hold"; return 1; }
        return 0
      fi
    fi
    prev="$cur"
    kill -0 "$JVM_RUN_PID" 2>/dev/null || { dlog "jvm exited before steady state — see $OUT"; return 1; }
    sleep 1
  done
  dlog "jvm never reached steady state"; return 1
}

jvm_stop(){ # $1 OUT, $2 UNIT — stop the scope only; never pkill java machine-wide
  local UNIT="$2"
  sudo systemctl stop "$UNIT.scope" 2>/dev/null
  [ -n "$JVM_RUN_PID" ] && kill -TERM "$JVM_RUN_PID" 2>/dev/null
  sleep 3
}
