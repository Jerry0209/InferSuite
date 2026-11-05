#!/usr/bin/env bash
# bench_selftest.sh — driver plumbing check (not a workload): a 2-thread busy "server" in the
# fence and a light client on the house cores.  WORKLOADS=selftest SHIELD=0 run_server.sh
bench_preflight(){ command -v python3 >/dev/null; }
bench_start(){ # $1 OUT $2 UNIT
  ( sudo systemd-run --collect --scope --slice="$MSLICE" $SCOPE_PROPS --unit="$2" -- \
      taskset -c "$CPUS_MEASURED" python3 -c 'import threading
def spin():
    while True: pass
[threading.Thread(target=spin).start() for _ in range(2)]' ) > "$1/server.log" 2>&1 &
  local i; for i in $(seq 1 50); do [ -d "/sys/fs/cgroup/$MSLICE/$2.scope" ] && break; sleep 0.2; done
  echo "$MSLICE/$2.scope" > "$1/.server_cg"
  ( taskset -c "$CPUS_HOUSE" sh -c 'while sleep 1; do date +%s; done' > "$1/client.log" ) & echo $! > "$1/.client_pid"
  sleep 3; [ -d "/sys/fs/cgroup/$MSLICE/$2.scope" ]
}
bench_stop(){ sudo systemctl stop "$2.scope" 2>/dev/null; kill "$(cat "$1/.client_pid" 2>/dev/null)" 2>/dev/null; true; }
