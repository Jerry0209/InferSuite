#!/usr/bin/env bash
# arm_shield.sh apply | verify | restore | status — runtime isolation for the ARM SPEC run.
#
# Jef's 8 + 8 layout (online 0-15, housekeeping 0-7, measured 8-15), reimplemented at
# RUNTIME (Jerry, 2026-11-03: no reboot, no GRUB). Boot-flag equivalents:
#   irqaffinity=0-7            -> every /proc/irq/N/smp_affinity_list := 0-7 (+ default mask);
#                                 kernel-managed IRQs refuse, which they also do at boot
#   workqueue.unbound_cpus=0-7 -> /sys/devices/virtual/workqueue/cpumask := 0-7
#   transparent_hugepage=never -> /sys/kernel/mm/transparent_hugepage/enabled := never
#   nmi_watchdog=0             -> checked only (already 0 on this AMI; never changed here)
# plus CPUs 16-191 offline, init/system/user slices AllowedCPUs=0-7, and our own fence
# cgroup /sys/fs/cgroup/jerry-measured (cpuset 8-15, mems 0) with leaf `spec` (cpuset 8).
# Jef's agentic-benchmark cgroup tree and units are never touched.
#
# apply   snapshots EVERY knob it changes into $STATE first, refuses if a snapshot exists.
# restore puts each knob back to its SNAPSHOT value (never to "all CPUs": an empty systemd
#         AllowedCPUs is restored as empty, see spec26_profile_validation.md §1.5), then
#         re-reads every knob and fails loudly on any mismatch.
# verify  is the ISO-PROOF gate (applied != verified). Exit 0 = proof held. JSON on stdout.
set -uo pipefail

HOUSE="${HOUSE:-0-7}"
MEAS="${MEAS:-8-15}"
MEAS_CPU="${MEAS_CPU:-8}"
ONLINE_KEEP="${ONLINE_KEEP:-0-15}"
FENCE=/sys/fs/cgroup/jerry-measured
LEAF="$FENCE/spec"
SLICES=(init.scope system.slice user.slice)
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE="${STATE:-$HERE/../data/interim/shield}"
QUIET="$HERE/../../spec26/infra_kit/scripts/quiet_gate.py"
SYS=/sys/devices/system/cpu

die(){ echo "FATAL: $*" >&2; exit 1; }
in_list(){ python3 -c "import sys
def ex(s):
    o=set()
    for p in s.split(','):
        if p: a,_,b=p.partition('-'); o|=set(range(int(a),int(b or a)+1))
    return o
sys.exit(0 if int(sys.argv[1]) in ex(sys.argv[2]) else 1)" "$1" "$2"; }
eff(){ cat "/sys/fs/cgroup/$1/cpuset.cpus.effective" 2>/dev/null; }
allowed(){ systemctl show -p AllowedCPUs --value "$1"; }

snapshot(){
  mkdir -p "$STATE"
  [ -e "$STATE/snapshot.done" ] && die "snapshot exists ($STATE) — shield already applied; run restore first"
  : > "$STATE/cpu_online.tsv"
  for d in "$SYS"/cpu[0-9]*; do
    n="${d##*cpu}"; [ -f "$d/online" ] && echo -e "$n\t$(cat "$d/online")" >> "$STATE/cpu_online.tsv"
  done
  cat "$SYS/online" > "$STATE/online_list"
  : > "$STATE/slices.tsv"
  # '|' not tab: tab is IFS whitespace, so `read` would collapse an EMPTY AllowedCPUs and shift columns
  for s in "${SLICES[@]}"; do echo "$s|$(allowed "$s")|$(eff "$s")|$(cat "/sys/fs/cgroup/$s/cpuset.cpus")" >> "$STATE/slices.tsv"; done
  systemctl is-active irqbalance > "$STATE/irqbalance" 2>/dev/null || true
  : > "$STATE/irq.tsv"
  for f in /proc/irq/[0-9]*/smp_affinity_list; do
    n="${f#/proc/irq/}"; n="${n%%/*}"; echo -e "$n\t$(cat "$f")" >> "$STATE/irq.tsv"
  done
  cat /proc/irq/default_smp_affinity > "$STATE/irq_default"
  cat /sys/devices/virtual/workqueue/cpumask > "$STATE/wq_cpumask"
  sed 's/.*\[\(.*\)\].*/\1/' /sys/kernel/mm/transparent_hugepage/enabled > "$STATE/thp_enabled"
  cat /proc/sys/kernel/nmi_watchdog > "$STATE/nmi_watchdog"
  [ -d "$FENCE" ] && die "$FENCE already exists — not ours to adopt silently"
  date -Is > "$STATE/snapshot.done"
}

apply(){
  pgrep -a -x perf && die "a perf process is running — someone may be measuring; not applying"
  snapshot
  echo "snapshot -> $STATE"
  # Jef's layout already live? adopt it and change nothing it covers (doc §4.2)
  local adopted=0
  if [ "$(cat "$SYS/online")" = "$ONLINE_KEEP" ] && [ "$(eff user.slice)" = "$HOUSE" ]; then
    adopted=1; echo "Jef's controlled layout is already live: adopting it"
  fi
  echo "$adopted" > "$STATE/adopted"
  if [ "$adopted" = 0 ]; then
    for s in "${SLICES[@]}"; do sudo systemctl set-property --runtime "$s" AllowedCPUs="$HOUSE" || die "slice $s"; done
    local n
    for d in "$SYS"/cpu[0-9]*; do
      n="${d##*cpu}"
      in_list "$n" "$ONLINE_KEEP" && continue
      [ "$(cat "$d/online" 2>/dev/null)" = 1 ] && { echo 0 | sudo tee "$d/online" >/dev/null || echo "WARN: cpu$n would not go offline"; }
    done
  fi
  # irqbalance re-spread NIC/bwctrl IRQs onto 8-15 within ~10 s of the first apply (2026-11-03)
  [ "$(cat "$STATE/irqbalance")" = active ] && { sudo systemctl stop irqbalance || die "stop irqbalance"; }
  : > "$STATE/irq_refused"
  for f in /proc/irq/[0-9]*/smp_affinity_list; do
    n="${f#/proc/irq/}"; n="${n%%/*}"
    echo "$HOUSE" | sudo tee "$f" >/dev/null 2>&1 || echo "$n" >> "$STATE/irq_refused"
  done
  echo "irq: $(wc -l < "$STATE/irq_refused") IRQ(s) refused $HOUSE (kernel-managed); irqbalance was $(cat "$STATE/irqbalance")"
  printf '%x\n' $(( (1 << 8) - 1 )) | sudo tee /proc/irq/default_smp_affinity >/dev/null
  echo ff | sudo tee /sys/devices/virtual/workqueue/cpumask >/dev/null || die "workqueue cpumask"
  echo never | sudo tee /sys/kernel/mm/transparent_hugepage/enabled >/dev/null || die "thp"
  sudo mkdir "$FENCE" "$LEAF" 2>/dev/null || true
  [ -d "$FENCE" ] || die "could not create $FENCE"
  echo "$MEAS" | sudo tee "$FENCE/cpuset.cpus" >/dev/null
  echo 0 | sudo tee "$FENCE/cpuset.mems" >/dev/null
  echo +cpuset | sudo tee "$FENCE/cgroup.subtree_control" >/dev/null
  echo "$MEAS_CPU" | sudo tee "$LEAF/cpuset.cpus" >/dev/null
  echo 0 | sudo tee "$LEAF/cpuset.mems" >/dev/null
  echo "applied: online=$(cat "$SYS/online") user.slice=$(eff user.slice) fence=$(cat "$FENCE/cpuset.cpus.effective") leaf=$(cat "$LEAF/cpuset.cpus.effective")"
}

restore(){
  [ -e "$STATE/snapshot.done" ] || { echo "no snapshot in $STATE — nothing to restore"; return 0; }
  local bad=0 n v want
  # fence first (empty leaf only; a live workload would make rmdir fail, which is reported)
  [ -d "$LEAF" ] && { sudo rmdir "$LEAF" || { echo "ERROR: $LEAF not empty"; bad=1; }; }
  [ -d "$FENCE" ] && { sudo rmdir "$FENCE" || { echo "ERROR: $FENCE not removable"; bad=1; }; }
  while IFS=$'\t' read -r n v; do
    [ "$(cat "$SYS/cpu$n/online")" = "$v" ] || echo "$v" | sudo tee "$SYS/cpu$n/online" >/dev/null || echo "WARN: cpu$n -> $v failed"
  done < "$STATE/cpu_online.tsv"
  local raw
  while IFS='|' read -r s v e raw; do
    sudo systemctl set-property --runtime "$s" AllowedCPUs="$v"
    # systemd does NOT rewrite cpuset.cpus when AllowedCPUs goes back to empty (tested 2026-11-03 on a
    # throwaway unit: raw stayed 0-3), and the kernel refuses an empty write (ENOSPC). So put back the
    # snapshot's raw value, or, when that was empty ("inherit"), the snapshot's EFFECTIVE set.
    [ "$(eff "$s")" = "$e" ] || echo "${raw:-$e}" | sudo tee "/sys/fs/cgroup/$s/cpuset.cpus" >/dev/null
  done < "$STATE/slices.tsv"
  while IFS=$'\t' read -r n v; do
    [ -f "/proc/irq/$n/smp_affinity_list" ] || continue
    [ "$(cat "/proc/irq/$n/smp_affinity_list")" = "$v" ] || echo "$v" | sudo tee "/proc/irq/$n/smp_affinity_list" >/dev/null 2>&1
  done < "$STATE/irq.tsv"
  sudo tee /proc/irq/default_smp_affinity < "$STATE/irq_default" >/dev/null
  [ "$(cat "$STATE/irqbalance" 2>/dev/null)" = active ] && sudo systemctl start irqbalance
  sudo tee /sys/devices/virtual/workqueue/cpumask < "$STATE/wq_cpumask" >/dev/null
  sudo tee /sys/kernel/mm/transparent_hugepage/enabled < "$STATE/thp_enabled" >/dev/null
  # ---- check it actually came back -------------------------------------------------
  [ "$(cat "$SYS/online")" = "$(cat "$STATE/online_list")" ] || { echo "MISMATCH online: $(cat "$SYS/online") != $(cat "$STATE/online_list")"; bad=1; }
  while IFS='|' read -r s v e _; do
    [ "$(allowed "$s")" = "$v" ] && [ "$(eff "$s")" = "$e" ] || { echo "MISMATCH $s: AllowedCPUs='$(allowed "$s")' eff=$(eff "$s") want '$v' eff=$e"; bad=1; }
  done < "$STATE/slices.tsv"
  local irqbad=0
  while IFS=$'\t' read -r n v; do
    [ -f "/proc/irq/$n/smp_affinity_list" ] || continue
    [ "$(cat "/proc/irq/$n/smp_affinity_list")" = "$v" ] || irqbad=$((irqbad+1))
  done < "$STATE/irq.tsv"
  [ "$irqbad" = 0 ] || { echo "MISMATCH: $irqbad IRQ affinities differ from snapshot"; bad=1; }
  for k in "irq_default:/proc/irq/default_smp_affinity" "wq_cpumask:/sys/devices/virtual/workqueue/cpumask"; do
    want="$(cat "$STATE/${k%%:*}")"; [ "$(cat "${k#*:}")" = "$want" ] || { echo "MISMATCH ${k%%:*}"; bad=1; }
  done
  [ "$(systemctl is-active irqbalance)" = "$(cat "$STATE/irqbalance" 2>/dev/null || echo active)" ] || { echo "MISMATCH irqbalance"; bad=1; }
  want="$(cat "$STATE/thp_enabled")"
  grep -q "\[$want\]" /sys/kernel/mm/transparent_hugepage/enabled || { echo "MISMATCH thp"; bad=1; }
  if [ "$bad" = 0 ]; then
    mv "$STATE" "$STATE.restored-$(date +%Y%m%dT%H%M%S)"
    echo "RESTORED and verified: online=$(cat "$SYS/online") user.slice eff=$(eff user.slice)"
  else
    echo "RESTORE INCOMPLETE — snapshot kept in $STATE"; return 1
  fi
}

busy_pct(){  # $1 = cpu list, $2 = seconds -> max busy % over those CPUs (from /proc/stat)
  python3 - "$1" "$2" <<'PY'
import sys, time
def ex(s):
    o=set()
    for p in s.split(','):
        a,_,b=p.partition('-'); o|=set(range(int(a),int(b or a)+1))
    return o
cpus=ex(sys.argv[1])
def rd():
    d={}
    for l in open('/proc/stat'):
        f=l.split()
        if f[0].startswith('cpu') and f[0][3:].isdigit() and int(f[0][3:]) in cpus:
            v=list(map(int,f[1:])); d[int(f[0][3:])]=(sum(v), v[3]+v[4])
    return d
a=rd(); time.sleep(float(sys.argv[2])); b=rd()
print(max(100*(1-(b[c][1]-a[c][1])/max(1,b[c][0]-a[c][0])) for c in a))
PY
}

verify(){  # ISO-PROOF. Prints one JSON line; exit 0 iff every check holds.
  local ok=1 why=() s e t busy=""
  for s in "${SLICES[@]}"; do e="$(eff "$s")"; [ "$e" = "$HOUSE" ] || { ok=0; why+=("$s eff=$e"); }; done
  [ "$(cat "$SYS/online")" = "$ONLINE_KEEP" ] || { ok=0; why+=("online=$(cat "$SYS/online")"); }
  [ "$(cat "$LEAF/cpuset.cpus.effective" 2>/dev/null)" = "$MEAS_CPU" ] || { ok=0; why+=("leaf cpuset"); }
  grep -q '\[never\]' /sys/kernel/mm/transparent_hugepage/enabled || { ok=0; why+=("thp"); }
  [ "$(cat /proc/sys/kernel/nmi_watchdog)" = 0 ] || { ok=0; why+=("nmi_watchdog"); }
  pgrep -x perf >/dev/null && { ok=0; why+=("foreign perf: $(pgrep -a -x perf | tr '\n' ';')"); }
  [ -z "$(cat "$LEAF/cgroup.procs" 2>/dev/null)" ] || { ok=0; why+=("fence not empty"); }
  for t in 1 2 3 4 5; do            # settle-and-retry: measured cores silent over 1.5 s
    busy="$(busy_pct "$MEAS" 1.5)"
    python3 -c "import sys; sys.exit(0 if float('$busy') < 2 else 1)" && break
    sleep 2
  done
  python3 -c "import sys; sys.exit(0 if float('$busy') < 2 else 1)" || { ok=0; why+=("measured cores busy ${busy}%"); }
  local q; q="$(python3 "$QUIET" check --sample 2 --mslice jerry-measured ${MINE:+--mine "$MINE"})" || { ok=0; why+=("machine not quiet: $q"); }
  local managed=0 stray="" n c
  for f in /proc/irq/[0-9]*/effective_affinity_list; do
    c="$(cat "$f" 2>/dev/null)"; [ -n "$c" ] || continue
    in_list "${c%%[-,]*}" "$HOUSE" && continue
    n="${f#/proc/irq/}"; n="${n%%/*}"
    if grep -qx "$n" "$STATE/irq_refused" 2>/dev/null; then managed=$((managed+1)); else stray+="$n:$c "; fi
  done
  [ -z "$stray" ] || { ok=0; why+=("non-managed IRQs on measured cores: $stray"); }
  systemctl is-active --quiet irqbalance && { ok=0; why+=("irqbalance running"); }
  python3 - "$ok" "$busy" "$q" "$managed" "$(cat "$SYS/online")" "${why[*]:-}" <<'PY'
import json, sys, time
ok, busy, q, managed, online, why = sys.argv[1:]
print(json.dumps({"iso_proof": ok == "1", "ts": time.time(), "measured_max_busy_pct_1p5s": float(busy),
                  "quiet": q, "managed_irqs_outside_house": int(managed), "online": online,
                  "why": why}))
PY
  [ "$ok" = 1 ]
}

status(){
  echo "online=$(cat "$SYS/online")"
  for s in "${SLICES[@]}"; do echo "$s AllowedCPUs='$(allowed "$s")' eff=$(eff "$s")"; done
  echo "fence=$( [ -d "$FENCE" ] && cat "$FENCE/cpuset.cpus.effective" || echo absent) thp=$(cat /sys/kernel/mm/transparent_hugepage/enabled) wq=$(cat /sys/devices/virtual/workqueue/cpumask) nmi=$(cat /proc/sys/kernel/nmi_watchdog)"
  echo "snapshot: $( [ -e "$STATE/snapshot.done" ] && echo "present ($STATE)" || echo none)"
}

case "${1:-}" in
  apply) apply ;; restore) restore ;; verify) verify ;; status) status ;;
  *) echo "usage: $0 apply|verify|restore|status" >&2; exit 2 ;;
esac
