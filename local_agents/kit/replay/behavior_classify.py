#!/usr/bin/env python3
"""behavior_classify.py — the BEHAVIOURAL ⟨language, type⟩ sampling frame (Report 17 §next).

The mentor's categories (search- / edit- / test-execution- / build-dominated) are properties of
what the AGENT DOES, not of the language's CPU mechanism (that axis is nested in language and
already saturated — Report 17). This tool:

  labels    realized behavioural label for every banked episode, from its trajectory's action
            mix (ground truth; also what post-hoc cell-crediting uses)
  predict   static prior for all 300 inventory rows + agreement vs the realized labels
  plan      the ⟨language, behaviour⟩ matrix and run list: one candidate + runner-up per
            uncovered cell  ->  <out>/behavior_plan.tsv

Definitions (action-count semantics — stated because babel proved "dominated" is ambiguous:
72 % of its ACTIONS are searches while 77 % of its fence INSTRUCTIONS are jest):
  S search-dominated   locating the fault is the work: view/grep/find/cat/ls dominate
  E edit-dominated     writing the fix is the work: str_replace/create/insert/sed -i dominate
  T test-dominated     the verify loop is the work: test runners + repro snippets dominate
  B build-dominated    build/deps wrangling is the work: make/cmake/installs dominate
An episode's label = argmax over S/E/T/B counts (git/misc excluded), but only if it leads the
runner-up by MARGIN points; otherwise M (mixed) — a 49 %-S/47 %-T episode is not
"search-dominated" in any useful sense (observed: phpspreadsheet-3940). A cell is CREDITED by
`credits()`: the intended type is the leader, or is co-dominant (within MARGIN of it), because a
co-dominant T episode does supply test-execution behaviour even if S edges it.
A cell is only credited by a REALIZED label; the static predictor is a prior (5/9-grade
accuracy on mechanism validation warns against trusting static labels — Report 17 §2.2).

Usage: behavior_classify.py [labels|predict|plan|export] (default: all)
`export` writes sampling_frame/task_inventory.csv — one self-contained row per instance:
static features + mechanism class (axis 1, from classifications.json) + behavioural prior
(axis 2) + realized label where an episode exists. The mentor-packet deliverable.
"""
import csv, json, os, re, sys, glob, collections

REPO = "/home/thu/InferSuite"
INV = f"{REPO}/local_agents/ML_multiling/data/multiling_inventory.csv"
OUT = f"{REPO}/local_agents/ML_multiling/sampling_frame"

# banked episodes: task-short -> (campaign, language). gin/carbon/laravel included: their
# realized labels are informative even though their measurements were rejected.
BANKED = {
    "scikit-learn": ("superseded_40min", "Python"), "astropy": ("superseded_40min", "Python"),
    "sympy": ("superseded_40min", "Python"),
    "babel": ("SWE_clean", "JavaScript"), "fmtlib": ("SWE_clean", "C++"),
    "tokio-rs": ("ML_multiling", "Rust"), "jqlang": ("ML_multiling", "C"),
    "prometheus": ("ML_multiling", "Go"), "google": ("ML_multiling", "Java"),
    "rubocop": ("ML_multiling", "Ruby"), "vuejs": ("ML_multiling", "TypeScript"),
    "php-cs-fixer": ("ML_multiling", "PHP"), "gin-gonic": ("ML_multiling", "Go"),
}

def _base_tokens(a):
    return {t.rsplit("/", 1)[-1] for t in a.split() if not t.startswith("-")}

EDIT_CMDS = {"str_replace", "create", "insert", "write", "append"}

def act_class(a):
    """one agent action -> S/E/T/B/other. Order matters: an action that edits AND greps is an
    edit (the grep is incidental); a test invocation buried in a shell one-liner is a test."""
    a = a.strip()
    m = re.match(r"cd\s+\S+\s*&&\s*(.*)", a, re.S)
    if m: a = m.group(1).strip()
    al = a.lower(); P = _base_tokens(al)
    if al.startswith("str_replace_editor"):
        parts = al.split()
        return "E" if len(parts) > 1 and parts[1] in EDIT_CMDS else "S"   # `view` = reading
    if re.search(r"\bsed\s+-i\b", al) or _has(P, "patch"): return "E"
    if re.search(r"pytest|py\.test|runtests", al) or _has(P, "jest", "vitest", "mocha", "rspec",
        "phpunit", "gotestsum", "ctest") or re.search(r"\b(go|cargo)\s+test\b", al) \
       or re.search(r"\bmvn\b.*\btest\b|gradlew?\b.*\btest\b", al): return "T"
    if re.search(r"\b(python[0-9.]*|node|php|ruby)\s+-[cre]\b", al) \
       or re.search(r"\./(reproduce|repro)", al) or re.search(r"\bnode\s+\S+\.js\b", al) \
       or re.search(r"\bphp\s+\S+\.php\b", al) or re.search(r"\bruby\s+\S+\.rb\b", al): return "T"
    if _has(P, "make", "gmake", "cmake", "ninja", "gcc", "g++", "cc", "javac", "rustc") \
       or re.search(r"\b(go|cargo)\s+build\b", al) \
       or re.search(r"\b(pip3?|npm|pnpm|yarn|bundle|gem|composer|cargo|apt-get|apt)\s+"
                    r"(install|add|update|ci|download)\b", al): return "B"
    if _has(P, "grep", "rg", "find", "cat", "ls", "head", "tail", "tree", "wc") \
       or re.search(r"\bsed\s+-n\b", al): return "S"
    return "other"

def _has(P, *names): return any(n in P for n in names)

def traj_of(short, campaign):
    base = f"{REPO}/local_agents/{campaign}/data/glm_replay_swe_{short}"
    for p in sorted(glob.glob(f"{base}/run_*/metadata.json")):
        t = (json.load(open(p)).get("extra") or {}).get("traj")
        if t and os.path.exists(t): return t
    # rejected instances have no replays; fall back to the live episode's own traj
    for p in sorted(glob.glob(f"{REPO}/local_agents/{campaign}/data/glm_swe_{short}/run_*/traj/*/*.traj")):
        if not p.endswith(".local.traj"): return p
    return None

MARGIN = 10.0   # percentage points of the classified-action mix

def _shares(c):
    core = {k: c.get(k, 0) for k in "SETB"}
    tot = sum(core.values())
    return ({k: 100.0 * v / tot for k, v in core.items()} if tot else
            {k: 0.0 for k in "SETB"}), tot

def episode_label(traj):
    d = json.load(open(traj))
    acts = [(st.get("action") or "").strip() for st in (d.get("trajectory") or [])]
    c = collections.Counter(act_class(a) for a in acts if a)
    sh, tot = _shares(c)
    if not tot: return "M", c, 0
    order = sorted(sh, key=sh.get, reverse=True)
    top, second = order[0], order[1]
    label = top if (sh[top] - sh[second]) >= MARGIN else "M"
    return label, c, tot

def credits(intended, c):
    """does this episode supply behaviour of type `intended`? leader, or co-dominant with it."""
    sh, tot = _shares(c)
    if not tot: return False
    top = max(sh, key=sh.get)
    return intended == top or (sh[top] - sh.get(intended, 0.0)) < MARGIN

def cmd_labels(print_out=True):
    rows = []
    for short, (camp, lang) in BANKED.items():
        t = traj_of(short, camp)
        if not t:
            rows.append((short, lang, "?", {}, 0)); continue
        lab, c, tot = episode_label(t)
        rows.append((short, lang, lab, c, tot))
    if print_out:
        print("=== realized behavioural labels (action-count semantics) ===")
        print(f"{'task':<14}{'lang':<12}{'label':<7}mix (S/E/T/B, % of classified)")
        for short, lang, lab, c, tot in rows:
            mix = "  ".join(f"{k}={100*c.get(k,0)/max(tot,1):.0f}%" for k in "SETB")
            print(f"{short:<14}{lang:<12}{lab:<7}{mix}   (n={sum(c.values())}, other={c.get('other',0)})")
    return {r[0]: r for r in rows}

# ---- static prior over the inventory ---------------------------------------------------
def predict_row(r):
    """ordered, deterministic; returns (label, why). A PRIOR, not a verdict."""
    pf, ph, pa = int(r["patch_files"]), int(r["patch_hunks"]), int(r["patch_add"])
    f2p, p2p = int(r["n_f2p"]), int(r["n_p2p"])
    tb, repro = int(r["ps_has_traceback"]), int(r["ps_has_repro"])
    if int(r["touches_build"]): return "B", "gold patch touches build files"
    if pf >= 3 or pa >= 80 or ph >= 8: return "E", f"large fix ({pf}f/{ph}h/{pa}+)"
    if f2p + p2p >= 25: return "T", f"heavy verify set ({f2p}+{p2p} tests)"
    if pf <= 1 and pa <= 15 and not tb and not repro:
        return "S", f"tiny fix ({pa}+), no traceback/repro to localize from"
    return "M", "no dominant static signal"

ID_OF = {"tokio-rs": "tokio-rs__tokio-6551", "jqlang": "jqlang__jq-2681",
         "prometheus": "prometheus__prometheus-9248", "google": "google__gson-2061",
         "rubocop": "rubocop__rubocop-13668", "vuejs": "vuejs__core-11915",
         "php-cs-fixer": "php-cs-fixer__php-cs-fixer-7523", "babel": "babel__babel-15445",
         "fmtlib": "fmtlib__fmt-3248", "gin-gonic": "gin-gonic__gin-3741"}

def cmd_predict(realized):
    rows = list(csv.DictReader(open(INV)))
    pred = {r["instance_id"]: predict_row(r) for r in rows}
    # agreement vs realized (banked instances present in the inventory: the 8 ML ones)
    id_of = ID_OF
    print("\n=== static prior vs realized (the honesty table) ===")
    agree = n = 0
    for short, iid in id_of.items():
        if short not in realized or iid not in pred: continue
        lab = realized[short][2]; p, why = pred[iid]; n += 1; agree += (p == lab)
        print(f"  {short:<14} realized={lab}  prior={p:<2} ({why})"
              + ("" if p == lab else "   <-- MISS"))
    print(f"  agreement: {agree}/{n} — treat priors as tie-breakers, not truth")
    return rows, pred

# ---- plan -------------------------------------------------------------------------------
def cmd_plan(realized, rows, pred):
    langs = ["Rust", "C", "Go", "Java", "TypeScript", "Ruby", "PHP", "JavaScript", "C++"]
    covered = collections.defaultdict(set)      # lang -> {realized labels of ACCEPTED tasks}
    ACCEPTED = {"tokio-rs", "jqlang", "prometheus", "google", "rubocop", "vuejs",
                "php-cs-fixer", "babel", "fmtlib"}
    for short, (camp, lang) in BANKED.items():
        if short in ACCEPTED and short in realized:
            covered[lang].add(realized[short][2])
    by_lang = collections.defaultdict(list)
    for r in rows: by_lang[r["language"]].append(r)
    plan = []
    print("\n=== <language, behaviour> matrix (candidates; * = covered by realized label) ===")
    print(f"{'lang':<12}" + "".join(f"{t:>10}" for t in "SETB"))
    for lang in langs:
        cnt = collections.Counter(pred[r["instance_id"]][0] for r in by_lang[lang])
        line = f"{lang:<12}"
        for t in "SETB":
            mark = "*" if t in covered[lang] else " "
            line += f"{cnt.get(t,0):>8}{mark} "
        print(line)
        for t in "SETB":
            if t in covered[lang]: continue
            cands = [r for r in by_lang[lang] if pred[r["instance_id"]][0] == t]
            if not cands: continue
            # prefer repos we have NOT profiled (avoid repo confound), then larger verify sets
            done_repos = {"tokio-rs/tokio", "jqlang/jq", "prometheus/prometheus", "google/gson",
                          "rubocop/rubocop", "vuejs/core", "php-cs-fixer/php-cs-fixer",
                          "babel/babel", "fmtlib/fmt", "gin-gonic/gin", "briannesbitt/carbon",
                          "laravel/framework"}
            DONE_INSTANCES = {"tokio-rs__tokio-6551", "jqlang__jq-2681",
                "prometheus__prometheus-9248", "google__gson-2061", "rubocop__rubocop-13668",
                "vuejs__core-11915", "php-cs-fixer__php-cs-fixer-7523", "babel__babel-15445",
                "fmtlib__fmt-3248", "gin-gonic__gin-3741", "briannesbitt__carbon-2813",
                "laravel__framework-51890"}
            # an already-profiled instance is not a candidate at all: re-running it would spend an
            # episode to re-measure a banked one (the PHP/T runner-up did exactly this).
            cands = [r for r in cands if r["instance_id"] not in DONE_INSTANCES]
            if not cands: continue
            cands.sort(key=lambda r: (r["repo"] in done_repos,
                                      -(int(r["n_f2p"]) + int(r["n_p2p"]))))
            rep, ru = cands[0], (cands[1] if len(cands) > 1 else None)
            plan.append({"language": lang, "type": t, "instance": rep["instance_id"],
                         "repo": rep["repo"], "why": pred[rep["instance_id"]][1],
                         "runner_up": ru["instance_id"] if ru else ""})
    os.makedirs(OUT, exist_ok=True)
    with open(f"{OUT}/behavior_plan.tsv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["language", "type", "instance", "repo", "why",
                                           "runner_up"], delimiter="\t")
        w.writeheader(); w.writerows(plan)
    print(f"\nrun list: {len(plan)} cells -> {OUT}/behavior_plan.tsv "
          f"(~{len(plan)*1.5:.0f} h serialized at ~1.5 h/cell)")
    for p in plan:
        print(f"  {p['language']:<12}{p['type']}  {p['instance']:<42} runner-up: {p['runner_up'] or '-'}")
    return plan

# ---- export -----------------------------------------------------------------------------
CLS = f"{REPO}/local_agents/ML_multiling/sampling_frame/classifications.json"
LEDGER = f"{REPO}/local_agents/ML_multiling/sampling_frame/behavior_ledger.tsv"

# mechanism is a total function of language (verified over all 300 rows, report 17 insight 1);
# the raw per-instance `category` strings from classifications.json are kept alongside because
# their granularity varies by language (some carry tier/X- codes, some the bare class letter)
MECH_OF = {"C": "B", "C++": "B", "Rust": "A", "Go": "A", "Java": "J",
           "PHP": "I", "Ruby": "I", "JavaScript": "N", "TypeScript": "N"}

def _mix_str(sh):
    return " ".join(f"{k}={sh[k]:.0f}%" for k in "SETB")

def _label_of_shares(sh):
    order = sorted(sh, key=sh.get, reverse=True)
    return order[0] if (sh[order[0]] - sh[order[1]]) >= MARGIN else "M"

def _probe_realized():
    """realized mixes of the falsification probes, from the campaign ledger (the authoritative
    record of what each probe realized). Label recomputed under the same MARGIN rule as
    episode_label so a 49/47 episode reads M here even though the driver logged its argmax."""
    out = {}
    for row in csv.DictReader(open(LEDGER), delimiter="\t"):
        if row["status"] != "realized-mismatch": continue
        m = re.search(r"S=(\d+)% E=(\d+)% T=(\d+)% B=(\d+)%", row["detail"])
        if not m: continue
        sh = dict(zip("SETB", map(float, m.groups())))
        out[row["instance"]] = (_label_of_shares(sh), _mix_str(sh), f"probe {row['short']}")
    return out

def cmd_export(realized, rows, pred):
    """sampling_frame/task_inventory.csv — the per-instance answer to the mentor's question.
    prior_confidence is a constant 'low' because that is what the prior measured against
    realized labels (1/10, report 17); mechanism confidence is per-row from the sweep."""
    mech = {a["instance_id"]: a
            for e in json.load(open(CLS)) for a in e["assignments"]}
    real_by_id = dict(_probe_realized())
    for short, (_s, _l, lab, c, tot) in ((s, r) for s, r in realized.items() if s in ID_OF):
        if tot and ID_OF[short] not in real_by_id:      # ledger (probe) rows take precedence
            sh, _ = _shares(c)
            real_by_id[ID_OF[short]] = (lab, _mix_str(sh), BANKED[short][0])
    out_rows = []
    for r in sorted(rows, key=lambda r: (r["language"], r["instance_id"])):
        iid = r["instance_id"]; a = mech.get(iid, {})
        lab, mix, src = real_by_id.get(iid, ("", "", ""))
        p, why = pred[iid]
        out_rows.append({
            "instance_id": iid, "repo": r["repo"], "language": r["language"],
            "mech_class": MECH_OF[r["language"]], "mech_category": a.get("category", ""),
            "mech_confidence": a.get("confidence", ""), "mech_secondary": a.get("secondary", ""),
            "mech_why": a.get("why", ""), "mech_risk": a.get("risk", ""),
            "behavior_prior": p, "prior_why": why,
            "prior_confidence": "low (1/10 vs realized labels, report 17)",
            "realized_label": lab, "realized_mix": mix, "realized_source": src,
            **{k: r[k] for k in r if k not in ("instance_id", "repo", "language")},
        })
    os.makedirs(OUT, exist_ok=True)
    p = f"{OUT}/task_inventory.csv"
    with open(p, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0])); w.writeheader(); w.writerows(out_rows)
    n_real = sum(1 for r in out_rows if r["realized_label"])
    print(f"\nwrote {p}: {len(out_rows)} rows, {n_real} with realized labels "
          f"(the other measured episodes are the 3 out-of-corpus Python references)")

if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    realized = cmd_labels()
    if what in ("all", "predict", "plan", "export"):
        rows, pred = cmd_predict(realized)
        if what in ("all", "plan"):
            cmd_plan(realized, rows, pred)
        if what in ("all", "export"):
            cmd_export(realized, rows, pred)
