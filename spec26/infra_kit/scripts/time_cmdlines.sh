#!/usr/bin/env bash
# time_cmdlines.sh <bench> [...] — time EVERY ref command line of each benchmark, under
# the same conditions an episode runs in (measured cores, one copy, one thread).
#
# Why this exists: picking "the longest ref command line" by reading the arguments does
# not work. Measured 2026-08-05, guessing from argument text got 1 of 9 right —
# 753.ns3_r's --simulationEndTime=500 ran SHORTER than its default line, 737.gmsh_r's
# finest-mesh line ran shorter than its first, and 748.flightdm_r's orbital script came
# out identical to its first. Runtime is not predictable from the command line, so it
# has to be measured.
#
# No perf, no counter groups: this is a stopwatch, and it exists to choose an index
# BEFORE spending a full profiled episode on it.
set -uo pipefail
INFRA="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KIT="$INFRA/scripts"
source "$KIT/spec_env.sh"
source "$INFRA/campaign.conf"

CAP="${CAP:-200}"           # per-line fuse; anything this long is already plenty
MSLICE="${MSLICE:-measured.slice}"
CPUS_MEASURED="${CPUS_MEASURED:-4-11}"
OUT="$INFRA/cmdline_times.tsv"

[ -f "$OUT" ] || printf 'benchmark\tindex\tseconds\tstatus\n' > "$OUT"

for B in "$@"; do
  RD="$SPEC_ROOT/benchspec/CPU/$B/run/run_base_${SPEC_SIZE}_${SPEC_LABEL}.0000"
  [ -d "$RD" ] || { echo "$B: no run dir"; continue; }
  TMP="$(mktemp -d)"
  SPEC_ROOT="$SPEC_ROOT" python3 "$KIT/extract_cmd.py" "$RD" "$TMP" >/dev/null || { echo "$B: extract failed"; continue; }
  N=$(cat "$TMP/n_cmds")
  echo "=== $B ($N command lines) ==="
  for ((i=0; i<N; i++)); do
    CMD="$(sed -n "$((i+1))p" "$TMP/speccmds_all.txt")"
    [ -n "$CMD" ] || continue
    U="spectime-$$-$i"
    sudo systemctl stop "$U.scope" 2>/dev/null
    t0=$EPOCHREALTIME
    sudo timeout "$CAP" systemd-run --collect --scope --slice="$MSLICE" --unit="$U" \
        -p AllowedCPUs="$CPUS_MEASURED" -- \
        runuser -u "$USER" -- bash -c "cd '$RD' && set -a && . '$TMP/env.sh' && set +a && exec $CMD" \
        >/dev/null 2>&1
    rc=$?
    t1=$EPOCHREALTIME
    d=$(awk -v a="$t0" -v b="$t1" 'BEGIN{printf "%.1f", b-a}')
    st=ok; [ $rc -eq 124 ] && st="capped(>=${CAP}s)"; [ $rc -ne 0 ] && [ $rc -ne 124 ] && st="rc=$rc"
    # windows a full 11-group rotation would get at the configured WINSEC
    w=$(awk -v d="$d" -v w="$WINSEC" 'BEGIN{printf "%d", d/w}')
    printf '  [%d] %6.1fs  -> %2d windows @ WINSEC=%s  %s\n' "$i" "$d" "$w" "$WINSEC" "$st"
    printf '%s\t%d\t%s\t%s\n' "$B" "$i" "$d" "$st" >> "$OUT"
  done
  rm -rf "$TMP"
done
echo
echo "wrote $OUT"
