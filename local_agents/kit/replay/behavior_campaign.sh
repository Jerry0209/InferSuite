#!/usr/bin/env bash
# behavior_campaign.sh — execute the ⟨language, behavioural type⟩ plan (Report 17) with the
# falsification-first design its correction demands.
#
# Premise under test: all 13 banked episodes realize as SEARCH-dominated by action count, so
# the behavioural axis may belong to the agent, not the task. Therefore:
#   phase 1  PROBES: the 3 plan rows statically most likely to realize non-S. If NONE realizes
#            its intended type, STOP — the honest deliverable is the finding, not 17 more
#            episodes of the same label. (Override: BREAKER=0.)
#   phase 2  the remaining plan rows, same per-cell pipeline.
#
# Per cell:  image check -> live episode -> realized behavioural label from its own trajectory
#            (cells are credited by REALIZED type; a mismatch burns the episode but not the
#            ~50 min of profiling) -> ownership+adequacy gate probe -> 10 more passes.
#            One bounded runner-up retry per cell, and only for episode-failure or realized
#            mismatch. Two consecutive <5-step episodes abort everything (credit-starvation
#            signature: empty turns, not errors).
#
# Dirs: SWE_SHORT_SUFFIX="-b<TYPE>" keeps each cell's data separate from the language pilots
# and from sibling cells of the same repo owner (glm_swe_phpoffice-bT/...).
#
#   BREAKER=<n> PLAN=<tsv> DATA_ROOT=<dir> ./behavior_campaign.sh
set -o pipefail
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$KIT/../../.." && pwd)"
PLAN="${PLAN:-$REPO/local_agents/ML_multiling/sampling_frame/behavior_plan.tsv}"
DATA_ROOT="${DATA_ROOT:-$REPO/local_agents/ML_multiling/data}"
LEDGER="${LEDGER:-$REPO/local_agents/ML_multiling/sampling_frame/behavior_ledger.tsv}"
BREAKER="${BREAKER:-1}"
PY="${PY:-$HOME/miniforge3/envs/infersuite-full/bin/python3}"
PROBES="phpoffice__phpspreadsheet-3940 preactjs__preact-4152 hashicorp__terraform-35543"
log(){ printf '[bcamp %s] %s\n' "$(date +%H:%M:%S)" "$*"; }

[ -f "$LEDGER" ] || printf 'when\tlanguage\ttype\tinstance\tshort\tstatus\tdetail\n' > "$LEDGER"
mark(){ printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$(date +%F.%T)" "$1" "$2" "$3" "$4" "$5" "$6" >> "$LEDGER"; }
# Only `profiled` is terminal. no-image was observed to be TRANSIENT (a Docker Hub blip marked
# an image that is present locally as missing), and realized-mismatch/gate-fail can flip when the
# label rule or a gate threshold is corrected — so they must not permanently retire a cell.
done_status(){ awk -F'\t' -v i="$1" '$4==i && $6=="profiled" {s=$6} END{print s}' "$LEDGER"; }

# realized behavioural label of a freshly captured episode, via behavior_classify's own rules
realized_of(){ # $1 = short(with suffix)  $2 = intended type -> "<label> <credit:yes|no> <mix>"
  "$PY" - "$DATA_ROOT" "$1" "$2" <<'PYEOF'
import sys, glob, importlib.util
data, short, intended = sys.argv[1], sys.argv[2], sys.argv[3]
spec = importlib.util.spec_from_file_location("bc", "/home/thu/InferSuite/local_agents/kit/replay/behavior_classify.py")
bc = importlib.util.module_from_spec(spec); spec.loader.exec_module(bc)
trajs = [p for p in glob.glob(f"{data}/glm_swe_{short}/run_1/traj/*/*.traj") if not p.endswith(".local.traj")]
if not trajs: print("NOTRAJ no -"); raise SystemExit
lab, c, tot = bc.episode_label(trajs[0])
mix = " ".join(f"{k}={100*c.get(k,0)/max(tot,1):.0f}%" for k in "SETB")
# credit on CO-DOMINANCE, not on the hard label: an S=49/T=47 episode does exercise the
# verify loop, and refusing it would discard the only non-S behaviour the suite offers.
print(lab, ("yes" if bc.credits(intended, c) else "no"), mix)
PYEOF
}

gate_of(){ # $1 = short(with suffix)  $2 = language  -> "PASS|FAIL pct windows ginstr"
  "$PY" - "$DATA_ROOT" "$1" "$2" <<'PYEOF'
import sys, csv, re, glob, collections, os
data, short, lang = sys.argv[1:4]
PROBE = {"Rust": r"\bcargo\b|\brustc\b|\bld\b|/target/(debug|release)/",
         "C": r"\bcc1\b|\bgcc\b|\bcc\b|\bmake\b|\bld\b",
         "Go": r"\bgo\b|pkg/tool/|/tmp/go-build",
         "Java": r"\bjava\b|\bjavac\b|\bmvn\b|maven|surefire|\bgradle",
         "Ruby": r"\bruby\b|\brspec\b|\brake\b|\bbundle\b|/bundle/bin/",
         "PHP": r"\bphp\b|phpunit|composer",
         "JavaScript": r"\bnode\b|jest|yarn|npm|esbuild",
         "TypeScript": r"\bnode\b|vitest|\bjest\b|\btsc\b|pnpm|yarn|npm|esbuild",
         "C++": r"cc1plus|/c\+\+|\bg\+\+|\bmake\b"}
rx = PROBE[lang]
cl = collections.defaultdict(list)
for p in glob.glob(f"{data}/glm_replay_swe_{short}/run_*/cmdlog.tsv"):
    run = "run_" + re.search(r"run_(\d+)", p).group(1)
    for ln in open(p):
        f = ln.rstrip("\n").split("\t", 2)
        if len(f) < 3 or not f[2].strip(): continue
        try: cl[run].append((float(f[0]), f[2]))
        except ValueError: pass
csvp = f"{data}/l3_study/all_windows_{short}.csv"
if not os.path.exists(csvp): print("FAIL no-csv 0 0"); raise SystemExit
seen = set(); tot = hit = 0.0; nw = 0; per = collections.Counter()
for d in csv.DictReader(open(csvp)):
    if d["fence"] != "tool": continue
    k = (d["group"], d["run"], d["win"])
    if k in seen: continue
    seen.add(k)
    I = float(d["instructions"]); t0, dur = float(d["t0"]), float(d["dur"])
    has = any(t0 <= tm < t0 + dur and re.search(rx, a) for tm, a in cl.get(d["run"], []))
    tot += I; nw += 1; per[(d["group"], d["run"])] += 1
    if has: hit += I
npass = len(per) or 1
pct = 100 * hit / tot if tot else 0.0
wpp, gpp = nw / npass, tot / 1e9 / npass
ok = pct >= 50.0 and wpp >= 20 and gpp >= 150
print(("PASS" if ok else "FAIL"), f"{pct:.1f}% {wpp:.0f}w {gpp:.0f}G")
PYEOF
}

run_cell(){ # $1 lang $2 type $3 instance $4 attempt-tag -> sets CELL_RESULT
  local LANG="$1" TYPE="$2" INST="$3" TAG="${4:-}"
  local OWNER="${INST%%__*}" SHORT="${INST%%__*}-b$2$TAG"
  CELL_RESULT="episode-fail"
  local IMG="swebench/sweb.eval.x86_64.$(echo "$INST" | sed 's/__/_1776_/'):latest"
  # A locally-present image needs no registry at all; only then consult the registry, and retry —
  # a single transient manifest failure previously retired a cell whose image was already pulled.
  local HAVE=0
  docker image inspect "$IMG" >/dev/null 2>&1 && HAVE=1
  if [ "$HAVE" = 0 ]; then
    for _try in 1 2 3; do
      docker manifest inspect "$IMG" >/dev/null 2>&1 && { HAVE=1; break; }
      sleep $((_try * 5))
    done
  fi
  if [ "$HAVE" = 0 ]; then
    log "cell $LANG/$TYPE $INST: image missing"; mark "$LANG" "$TYPE" "$INST" "$SHORT" no-image "$IMG"
    CELL_RESULT="no-image"; return; fi
  if [ -f "$DATA_ROOT/glm_swe_$SHORT/run_1/DONE" ]; then
    log "cell $LANG/$TYPE $INST: reusing banked episode $SHORT (no new API spend)"
  else
  log "cell $LANG/$TYPE: episode $INST (short=$SHORT)"
  SWE_SUBSET=multilingual SWE_INSTANCES="$INST" REPEATS=1 SWE_SHORT_SUFFIX="-b$TYPE$TAG" \
    DATA_ROOT="$DATA_ROOT" "$REPO/measure.sh" agents-swe campaign \
    > "$DATA_ROOT/../sampling_frame/log_${SHORT}.log" 2>&1
  local RC=$?
  local STEPS; STEPS=$(grep -aoE 'STEP [0-9]+' "$DATA_ROOT/glm_swe_$SHORT/run_1/agent.log" 2>/dev/null | awk '{if($2+0>m)m=$2+0}END{print m+0}')
  if [ "$RC" != 0 ] || [ ! -f "$DATA_ROOT/glm_swe_$SHORT/run_1/DONE" ]; then
    log "cell $LANG/$TYPE $INST: episode failed (rc=$RC steps=${STEPS:-0})"
    mark "$LANG" "$TYPE" "$INST" "$SHORT" episode-fail "rc=$RC steps=${STEPS:-0}"
    [ "${STEPS:-0}" -lt 5 ] && STARVED=$((STARVED+1)) || STARVED=0
    return; fi
  fi
  STARVED=0
  local RL; RL=$(realized_of "$SHORT" "$TYPE")
  local LAB CRED; LAB=$(echo "$RL" | awk '{print $1}'); CRED=$(echo "$RL" | awk '{print $2}')
  log "cell $LANG/$TYPE $INST: realized=$RL"
  if [ "$CRED" != yes ]; then
    mark "$LANG" "$TYPE" "$INST" "$SHORT" realized-mismatch "$RL"
    CELL_RESULT="realized-mismatch"; return; fi
  SHORT="$SHORT" SRC=1 DATA_ROOT="$DATA_ROOT" WINSEC=2 PROF_GROUPS="fe_miss" \
    "$KIT/replay_l3_profile.sh" >> "$DATA_ROOT/../sampling_frame/log_${SHORT}.log" 2>&1
  "$PY" "$KIT/analyze_l3_windows.py" "$DATA_ROOT" "$SHORT" >/dev/null 2>&1
  local G; G=$(gate_of "$SHORT" "$LANG"); log "cell $LANG/$TYPE $INST: gate=$G"
  if [ "${G%% *}" != PASS ]; then
    mark "$LANG" "$TYPE" "$INST" "$SHORT" gate-fail "$G"; CELL_RESULT="gate-fail"; return; fi
  SHORT="$SHORT" SRC=1 DATA_ROOT="$DATA_ROOT" WINSEC=2 \
    PROF_GROUPS="fe_miss fe_lat fe fpbr cache mlp core_ports dram_bw mem_bound fe_l3x priv" \
    "$KIT/replay_l3_profile.sh" >> "$DATA_ROOT/../sampling_frame/log_${SHORT}.log" 2>&1
  "$PY" "$KIT/analyze_l3_windows.py" "$DATA_ROOT" "$SHORT" --plot >/dev/null 2>&1
  mark "$LANG" "$TYPE" "$INST" "$SHORT" profiled "realized=$LAB credit=$CRED mix=[${RL#* * }] gate=$G"
  CELL_RESULT="profiled"
}

STARVED=0; NONS_REALIZED=0; PROBED=0
# plan rows, probes first
ROWS=$(tail -n +2 "$PLAN")
ORDERED=$( { for p in $PROBES; do echo "$ROWS" | awk -F'\t' -v i="$p" '$3==i'; done
             echo "$ROWS" | awk -F'\t' -v ps="$PROBES" 'BEGIN{split(ps,a," ");for(k in a)P[a[k]]=1} !($3 in P)'; } )
while IFS=$'\t' read -r LANG TYPE INST REPO_ WHY RUNUP; do
  [ -n "$INST" ] || continue
  ST=$(done_status "$INST")
  [ -n "$ST" ] && { log "skip $LANG/$TYPE $INST — already $ST"; continue; }
  run_cell "$LANG" "$TYPE" "$INST"
  if [ "$CELL_RESULT" != profiled ] && [ "$CELL_RESULT" != no-image ] && [ -n "$RUNUP" ]; then
    log "cell $LANG/$TYPE: retrying with runner-up $RUNUP"
    run_cell "$LANG" "$TYPE" "$RUNUP" r
  fi
  [ "$CELL_RESULT" = profiled ] && NONS_REALIZED=$((NONS_REALIZED+1))
  if [ "$STARVED" -ge 2 ]; then log "ABORT: two consecutive <5-step episodes — credit starvation signature"; exit 3; fi
  case " $PROBES " in *" $INST "*) PROBED=$((PROBED+1));; esac
  if [ "$BREAKER" = 1 ] && [ "$PROBED" -ge 3 ] && [ "$NONS_REALIZED" -eq 0 ]; then
    log "BREAKER: all 3 probes realized S (or failed) — premise falsified, stopping before the sweep."
    log "Override with BREAKER=0 to run the remaining plan rows anyway."
    exit 2
  fi
done <<< "$ORDERED"
log "PLAN COMPLETE — see $LEDGER"
