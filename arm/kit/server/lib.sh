#!/usr/bin/env bash
# lib.sh — helpers shared by run_server.sh and calibrate_feedsim.sh (ARM Server kit).
# Never pkill machine-wide (the box is shared): the x86 modules' `sudo pkill -f X` became
# kill_desc X = TERM only processes matching X that descend from this pass's shell (PASS_ROOT).
is_desc(){ local p="$1"; while [ -n "$p" ] && [ "$p" -gt 1 ]; do
  [ "$p" = "${PASS_ROOT:?}" ] && return 0; p=$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' '); done; return 1; }
kill_desc(){ local p; for p in $(pgrep -f -- "$1"); do
  [ "$p" != "$BASHPID" ] && is_desc "$p" && sudo kill -TERM "$p" 2>/dev/null; done; return 0; }
export -f is_desc kill_desc
