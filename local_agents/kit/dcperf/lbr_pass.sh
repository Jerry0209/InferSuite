#!/usr/bin/env bash
# lbr_pass.sh — the front-end footprint pass (pseudo-group "lbr") for run_dcperf_profile.sh.
# Sourced by the orchestrator; functions only.
#
# Contract: docs/handoff/execution/frontend_footprint_method.md v1.1 (Rahul's three metrics),
# the same event, period, branch filter, scope and analyzer as the SPEC run on spec-x86
# (spec26/infra_kit/scripts/frontend_footprint_episode.sh). Change nothing the contract fixes.
#
# What differs from a counter pass is only the instruments. Everything around them is the
# orchestrator's, unchanged: apply_isolation + ISO-PROOF, bench_start (server in the fence,
# client on the house cores, liveness check), the 10 Hz pollers, bench_stop (receipt),
# restore_isolation. Over the same steady-state window a counter pass would rotate groups in,
# one LBR sampling record and one exact perf stat run on the server fence. Both start
# DISABLED and are switched on and off through their control FIFOs (each must ack), so the
# two instruments cover the same CAPTURE_S seconds: the coverage gate (samples x period vs
# the exact taken-branch count) compares like with like.
#
# After the pass: perf script | lbr_footprint, then lbr_pass_gates.py judges lost records,
# coverage, throttling, D4 drift, D5 residual, the foreign-process witness and the client
# receipt against the banked counter passes. Only if all pass is the pass DONE and lbr.data
# deleted; otherwise lbr.data is kept for inspection.
FF_EVENT="br_inst_retired.near_taken:pp"     # contract v1.1: PEBS, LBR written at the overflow
FF_PERIOD="${FF_PERIOD:-20011}"              # prime; identical for SPEC, Server and Agentic
FF_FILTER="any,save_type"
FF_MMAP="${FF_MMAP:-512M}"
# Fallback ring sizes (2026-11-03): -m 512M needs a 1 MB physically contiguous page-pointer array
# per CPU (order-8 kmalloc); under a heavily cached, fragmented memory map that fails with ENOMEM
# ("failed to mmap with 12", kafka-20g). Buffer size is not a contract parameter -- the lost and
# coverage gates judge whether it sufficed -- so retry smaller and record what was used.
FF_MMAP_FALLBACK="${FF_MMAP_FALLBACK:-256M 128M}"
FF_THREADS="${FF_THREADS:-0}"                # perf record --threads: NOT usable here. perf 6.8.12
                                             # in threaded mode never acks the control FIFO's
                                             # enable and ignores SIGINT (probed 2026-11-03);
                                             # one reader, big -m, and the lost/coverage gates
FF_STAT_EVENTS="cycles,instructions,br_inst_retired.near_taken"
FF_COVER_TOL="${FF_COVER_TOL:-0.005}"
FF_ANALYZER="${FF_ANALYZER:-$REPO/local_agents/kit/frontend_footprint/lbr_footprint}"
# The SPEC run recorded the spec-x86 commit that introduced the analyzer; dcperf carries it
# as a cherry-pick with byte-identical source (src sha256 checked in lbr_preflight).
FF_ANALYZER_SHA="${FF_ANALYZER_SHA:-31c492b25f13b5178b1dfd91aeb2dbe4cbe1fd86}"
FF_ANALYZER_SRC_SHA="298e417a3dc3dbd0591380ccc36f6986b6c3aeb2e83c4d5a582759bcbd2dce22"
FF_MINE_PID="${FF_MINE_PID:-$$}"             # witness: our descendants are not foreign
FF_REC_PID=""; FF_STAT_PID=""; FF_WIT_PID=""

lbr_preflight(){
  [ -x "$FF_ANALYZER" ] || { dlog "FATAL: analyzer $FF_ANALYZER missing (make -C local_agents/kit/frontend_footprint)"; return 1; }
  "$FF_ANALYZER" --version | grep -q "$FF_ANALYZER_SRC_SHA" \
    || { dlog "FATAL: analyzer source sha256 is not the contract's $FF_ANALYZER_SRC_SHA"; return 1; }
  command -v zstd >/dev/null || { dlog "FATAL: zstd not on PATH"; return 1; }
  dlog "lbr preflight OK ($FF_EVENT -c $FF_PERIOD -j $FF_FILTER; analyzer $FF_ANALYZER_SHA)"
}

ff_cmd(){ # $1 fifo prefix, $2 command: send it, require perf's "ack"
  timeout 60 bash -c 'echo "$2" > "$1.ctl" && read -r a < "$1.ack" && [ "$a" = ack ]' _ "$1" "$2"
}
ff_stop_instruments(){ # SIGINT: perf record writes its file, perf stat its final counts
  local p
  [ -n "$FF_WIT_PID" ] && kill "$FF_WIT_PID" 2>/dev/null; FF_WIT_PID=""
  # perf record runs under sudo: signal sudo's own perf child, by parent PID and exact name
  [ -n "$FF_REC_PID" ] && for p in $(pgrep -P "$FF_REC_PID" -x perf); do sudo -n kill -INT "$p" 2>/dev/null; done
  [ -n "$FF_STAT_PID" ] && kill -INT "$FF_STAT_PID" 2>/dev/null
  [ -n "$FF_REC_PID" ]  && { wait "$FF_REC_PID" 2>/dev/null;  FF_REC_RC=$?; }
  [ -n "$FF_STAT_PID" ] && { wait "$FF_STAT_PID" 2>/dev/null; FF_STAT_RC=$?; }
  FF_REC_PID=""; FF_STAT_PID=""
}

lbr_capture(){ # $1 OUT, $2 server cgroup, $3 seconds -> 0 if the window ran to the end
  local OUT="$1" CG="$2" S="$3" f thr=()
  FF_T0=""; FF_T1=""; FF_REC_RC=""; FF_STAT_RC=""
  [ "$FF_THREADS" = 1 ] && thr=(--threads)
  for f in rec.ctl rec.ack stat.ctl stat.ack; do rm -f "$OUT/$f"; mkfifo "$OUT/$f" || return 1; done
  local MAXRATE0 PCT0; MAXRATE0=$(cat /proc/sys/kernel/perf_event_max_sample_rate); PCT0=$(cat /proc/sys/kernel/perf_cpu_time_max_percent)
  local mm; FF_MMAP_USED=""
  FF_REC_CMD="sudo $PERF record -z -m <FF_MMAP_USED> ${thr[*]} -e $FF_EVENT -c $FF_PERIOD -j $FF_FILTER -a -C $CPUS_MEASURED --cgroup=$CG -D -1 --control=fifo:rec.ctl,rec.ack -o lbr.data"
  FF_STAT_CMD="$PERF stat -x, -a -C $CPUS_MEASURED -e $FF_STAT_EVENTS --for-each-cgroup=$CG -D -1 --control=fifo:stat.ctl,stat.ack -o exact_counts.csv"
  # AS ROOT (2026-11-03): the servers run as root and are already up when the window opens, so
  # perf learns their code mappings only by reading /proc/<pid>/maps at start -- which a
  # non-root perf may not do for a root process. It then records FORK/COMM but no MMAP, and
  # every user-space address is unmapped: no straight-line ranges, no canonical keys
  # (feedsim smoke: 98 % of entries unmapped, footprint read 2.1 MB). SPEC never hit this:
  # its benchmark ran as the user and started after perf.
  for mm in $FF_MMAP $FF_MMAP_FALLBACK; do
    sudo -n taskset -c "$CPUS_HOUSE" "$PERF" record -z -m "$mm" "${thr[@]}" -e "$FF_EVENT" -c "$FF_PERIOD" -j "$FF_FILTER" \
        -a -C "$CPUS_MEASURED" --cgroup="$CG" -D -1 --control="fifo:$OUT/rec.ctl,$OUT/rec.ack" \
        -o "$OUT/lbr.data" > "$OUT/perf_record.log" 2>&1 &
    FF_REC_PID=$!
    # a failed mmap makes perf exit within a second; a working one waits on the control FIFO
    sleep 3
    if kill -0 "$FF_REC_PID" 2>/dev/null; then FF_MMAP_USED="$mm"; break; fi
    wait "$FF_REC_PID" 2>/dev/null
    dlog "lbr: perf record -m $mm failed ($(head -1 "$OUT/perf_record.log")); trying a smaller ring"
    cat "$OUT/perf_record.log" >> "$OUT/perf_record_failed_attempts.log"; FF_REC_PID=""
  done
  [ -n "$FF_MMAP_USED" ] || { dlog "lbr: perf record could not start at any ring size"; return 1; }
  FF_REC_CMD="${FF_REC_CMD/<FF_MMAP_USED>/$FF_MMAP_USED}"
  taskset -c "$CPUS_HOUSE" "$PERF" stat -x, -a -C "$CPUS_MEASURED" -e "$FF_STAT_EVENTS" \
      --for-each-cgroup="$CG" -D -1 --control="fifo:$OUT/stat.ctl,$OUT/stat.ack" \
      -o "$OUT/exact_counts.csv" > "$OUT/perf_stat.log" 2>&1 &
  FF_STAT_PID=$!
  # whole-machine witness: any other user's task busy during the window is recorded
  taskset -c "$CPUS_HOUSE" python3 "$KITD/quiet_gate.py" witness --out "$OUT/witness.tsv" --poll 2 \
      --mine "$FF_MINE_PID" >/dev/null 2>&1 &
  FF_WIT_PID=$!
  # enable record first and disable it last: the exact count's window sits inside the sampled one
  if ! ff_cmd "$OUT/rec" enable || ! ff_cmd "$OUT/stat" enable; then
    dlog "lbr: perf did not acknowledge enable (perf_record.log / perf_stat.log)"; ff_stop_instruments; return 1
  fi
  FF_T0=$EPOCHREALTIME
  dlog "lbr: sampling $CG for ${S}s ($FF_EVENT -c $FF_PERIOD, ${thr[*]:-single reader})"
  local end rem alive=1
  end=$(awk -v t="$FF_T0" -v s="$S" 'BEGIN{printf "%.3f", t + s}')
  while :; do
    rem=$(awk -v e="$end" -v n="$EPOCHREALTIME" 'BEGIN{r = e - n; if (r <= 0) print 0; else printf "%.3f", (r > 1 ? 1 : r)}')
    [ "$rem" = 0 ] && break
    [ -d "/sys/fs/cgroup/$CG" ] || { alive=0; break; }
    sleep "$rem"
  done
  ff_cmd "$OUT/stat" disable; ff_cmd "$OUT/rec" disable
  FF_T1=$EPOCHREALTIME
  ff_stop_instruments
  sudo -n chown "$(id -u):$(id -g)" "$OUT/lbr.data" 2>/dev/null
  rm -f "$OUT"/rec.ctl "$OUT"/rec.ack "$OUT"/stat.ctl "$OUT"/stat.ack
  [ "$alive" = 1 ] || dlog "lbr: WARN server fence disappeared mid-window"
  OUT="$OUT" T0="$FF_T0" T1="$FF_T1" S="$S" ALIVE="$alive" PERIOD="$FF_PERIOD" EV="$FF_EVENT" FILT="$FF_FILTER" \
  MMAPUSED="$FF_MMAP_USED" STATEV="$FF_STAT_EVENTS" REC_CMD="$FF_REC_CMD" STAT_CMD="$FF_STAT_CMD" REC_RC="${FF_REC_RC:-?}" STAT_RC="${FF_STAT_RC:-?}" \
  PERFV="$("$PERF" --version)" MAXRATE0="$MAXRATE0" PCT0="$PCT0" CG="$CG" \
  MAXRATE1="$(cat /proc/sys/kernel/perf_event_max_sample_rate)" PCT1="$(cat /proc/sys/kernel/perf_cpu_time_max_percent)" \
  JAVAV="$("${JAVA:-java}" -version 2>&1 | head -1)" ISO="$(tail -n 60 "$KIT/campaign.log" 2>/dev/null | grep -E 'ISO-PROOF.*quiet-check|ISOLATION: PROVEN' | tail -2 | tr '\n' ' ')" \
  python3 - <<'PY'
import json, os
E = os.environ
p = f"{E['OUT']}/metadata.json"
m = json.load(open(p))
t0, t1 = float(E["T0"]), float(E["T1"])
# write_metadata describes the counter-pass instrument set; overwrite what does not apply.
m.update(gorder=None, rotation=None, tma_cont=False, winsec=None,
         instruments=["LBR perf record (server fence, measured cores)",
                      "perf stat exact counts (same fence, same window)",
                      "cpu.stat 10Hz", "procstat partition witness", "foreign-process witness 0.5 Hz"])
m["frontend_footprint"] = {
    "contract": "docs/handoff/execution/frontend_footprint_method.md v1.1",
    "event": E["EV"], "period": int(E["PERIOD"]), "branch_filter": E["FILT"],
    "scope": "perf record -a -C <measured> --cgroup=<server fence>", "server_cg": E["CG"],
    "stat_events": E["STATEV"],
    "window": "steady state: both perf instances enabled (acked) after bench_start's liveness check, "
              "disabled CAPTURE_S later; perf stat's window nested inside perf record's",
    "capture_s": int(E["S"]), "ts_start": t0, "ts_end": t1, "window_s": t1 - t0,
    "server_alive_through_window": E["ALIVE"] == "1",
    "perf_version": E["PERFV"], "perf_record_cmd": E["REC_CMD"], "perf_stat_cmd": E["STAT_CMD"],
    "perf_record_rc": E["REC_RC"], "perf_stat_rc": E["STAT_RC"], "perf_record_mmap": E["MMAPUSED"],
    "perf_event_max_sample_rate": [int(E["MAXRATE0"]), int(E["MAXRATE1"])],
    "perf_cpu_time_max_percent": [int(E["PCT0"]), int(E["PCT1"])],
    "java_on_path": E["JAVAV"], "iso_proof": E["ISO"].strip(),
}
json.dump(m, open(p, "w"), indent=1)
PY
  [ "$alive" = 1 ]
}

lbr_finish(){ # $1 OUT -> 0 and DONE if every gate passed; lbr.data deleted only then
  local OUT="$1" t0=$EPOCHREALTIME
  [ -s "$OUT/lbr.data" ] || [ -d "$OUT/lbr.data" ] || { dlog "lbr: FAIL no lbr.data"; return 1; }
  dlog "lbr: analysing $(du -sh "$OUT/lbr.data" | cut -f1) of samples"
  taskset -c "$CPUS_HOUSE" "$PERF" report -i "$OUT/lbr.data" --stats > "$OUT/perf_report_stats.txt" 2>&1
  taskset -c "$CPUS_HOUSE" "$PERF" script -i "$OUT/lbr.data" -F pid,brstack \
      --show-mmap-events --show-task-events --show-lost-events 2> "$OUT/perf_script.err" \
    | taskset -c "$CPUS_HOUSE" "$FF_ANALYZER" --mode lbr --analyzer-sha "$FF_ANALYZER_SHA" \
      --summary "$OUT/analyzer.json" --edges "$OUT/edges.tsv" --objects "$OUT/objects.tsv" \
      --lines "$OUT/lines.tsv" --meta workload="$WL" --meta period="$FF_PERIOD" \
      > "$OUT/analyzer.log" 2>&1
  local arc=$?
  dlog "lbr: analysis rc=$arc in $(awk -v a="$t0" -v b="$EPOCHREALTIME" 'BEGIN{printf "%.0f", b - a}') s"
  local BANKED; BANKED="$(dirname "$DATA_ROOT")/${SUITE}_${WL}"
  [ -f "$KITD/receipt_compare.py" ] && [ -d "$BANKED" ] \
    && python3 "$KITD/receipt_compare.py" "$OUT" "$BANKED" --out "$OUT/receipt_compare.json" > /dev/null 2>&1
  python3 "$KITD/lbr_pass_gates.py" "$OUT" --analyzer-rc "$arc" --period "$FF_PERIOD" \
      --cover-tol "$FF_COVER_TOL" --measured "$CPUS_MEASURED" 2>&1 | while read -r l; do dlog "lbr: $l"; done
  if [ "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["gates_v4"]["all_ok"])' "$OUT/summary.json" 2>/dev/null)" != True ]; then
    dlog "lbr: PASS-FAIL $SUITE/$WL (lbr.data kept for inspection)"; return 1
  fi
  local f
  for f in edges.tsv objects.tsv lines.tsv; do [ -f "$OUT/$f" ] && zstd -q -f --rm -T2 "$OUT/$f"; done
  rm -rf "${OUT:?}/lbr.data"
  dlog "lbr: PASS-OK $SUITE/$WL"; return 0
}
