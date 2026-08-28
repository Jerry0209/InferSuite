#!/usr/bin/env bash
# retry_until_resolved.sh — bounded retry loop for live episodes that did not resolve
# (PI directive 2026-08-28): re-run each target's live episode at temp 0.6, evaluate the
# new patch with the official SWE-bench harness, and repeat for the still-unresolved,
# up to MAX_ROUNDS. Every attempt is parked as evidence, never deleted.
#
# Resolution is stochastic at temp 0.6 (fluentd needed 3 attempts), so a bounded loop is
# the honest design: expected convergence for most targets within 2-3 rounds.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
SPV="${SWEBENCH_VENV:?path to swebench venv bin/python}"
MAX_ROUNDS="${MAX_ROUNDS:-3}"
LOG="$HERE/retry_resolve.log"
log(){ printf '[retry %s] %s\n' "$(date +%H:%M:%S)" "$*" | tee -a "$LOG"; }

# short|instance — the 7 non-resolved of run live36_06. Override with TARGETS_OVERRIDE
# (same format) for follow-up passes; ROUND_OFFSET shifts the round tag so parked dirs
# and eval run-ids never collide with an earlier invocation's evidence.
TARGETS="${TARGETS_OVERRIDE:-caddyserver-t4774|caddyserver__caddy-4774
fmtlib-t3750|fmtlib__fmt-3750
jordansissel-t1829|jordansissel__fpm-1829
rubocop-t13560|rubocop__rubocop-13560
fmtlib-t3901|fmtlib__fmt-3901
gohugoio-t12579|gohugoio__hugo-12579
php-cs-fixer-t8064|php-cs-fixer__php-cs-fixer-8064}"
ROUND_OFFSET="${ROUND_OFFSET:-0}"

PEND="$TARGETS"
for ROUND in $(seq 1 "$MAX_ROUNDS"); do
  R=$((ROUND + ROUND_OFFSET))
  [ -n "$(echo "$PEND" | tr -d '[:space:]')" ] || break
  log "ROUND $R — pending: $(echo "$PEND" | cut -d'|' -f1 | tr '\n' ' ')"
  # park current attempts so the sweep redoes them
  mkdir -p "$HERE/data_live/_parked"
  for row in $PEND; do
    SHORT="${row%%|*}"
    if [ -d "$HERE/data_live/glm_swe_${SHORT}/run_1" ]; then
      mv "$HERE/data_live/glm_swe_${SHORT}/run_1" \
         "$HERE/data_live/_parked/${SHORT}.run_1.retry_r${R}" 2>/dev/null
    fi
  done
  # live episodes (run_live36 skips every DONE task; only the parked targets run)
  MIN_FREE_GB=10 bash "$HERE/run_live36.sh" >> "$LOG" 2>&1
  # collect patches
  PREDS="$HERE/data_live/_parked/preds_retry_r${R}.jsonl"
  : > "$PREDS"
  EVAL_IDS=""
  for row in $PEND; do
    SHORT="${row%%|*}"; INST="${row##*|}"
    python3 - "$HERE/data_live/glm_swe_${SHORT}/run_1" "$INST" "$PREDS" <<'PY'
import glob, json, sys
d, inst, preds = sys.argv[1], sys.argv[2], sys.argv[3]
tp = [p for p in glob.glob(f"{d}/traj/*/*.traj") if not p.endswith(".local.traj")]
patch = ""
if tp:
    patch = json.load(open(tp[0])).get("info", {}).get("submission") or ""
if patch:
    with open(preds, "a") as f:
        f.write(json.dumps({"model_name_or_path": f"{inst}_retry",
                            "instance_id": inst, "model_patch": patch}) + "\n")
    print("SUBMITTED")
else:
    print("NOSUB")
PY
  done
  if [ ! -s "$PREDS" ]; then
    log "ROUND $R: no submissions at all — all targets pend for next round"
    continue
  fi
  # evaluate (isolation is restored between episodes; PMU free here)
  ( cd "$HERE/data_live/_parked" && \
    "$SPV" -m swebench.harness.run_evaluation -d SWE-bench/SWE-bench_Multilingual -s test \
      -p "$PREDS" --max_workers 3 -id "retry_r${R}" ) >> "$LOG" 2>&1
  RPT=$(ls -t "$HERE/data_live/_parked"/*retry_r${R}*.json 2>/dev/null | head -1)
  [ -n "$RPT" ] || { log "ROUND $R: no eval report — aborting"; exit 1; }
  RESOLVED=$(python3 -c "import json;print(' '.join(json.load(open('$RPT')).get('resolved_ids',[])))")
  log "ROUND $R resolved: ${RESOLVED:-none}"
  # GC eval images
  for i in $(docker images --format '{{.Repository}}:{{.Tag}}' | grep '^swebench/'); do
    docker rmi "$i" >/dev/null 2>&1
  done
  NEWPEND=""
  for row in $PEND; do
    INST="${row##*|}"
    echo "$RESOLVED" | grep -q "$INST" || NEWPEND="$NEWPEND$row
"
  done
  PEND="$NEWPEND"
done
if [ -n "$(echo "$PEND" | tr -d '[:space:]')" ]; then
  log "DONE after $MAX_ROUNDS rounds — STILL UNRESOLVED: $(echo "$PEND" | cut -d'|' -f1 | tr '\n' ' ')"
else
  log "DONE — all targets resolved"
fi
