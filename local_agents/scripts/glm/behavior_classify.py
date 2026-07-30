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
An episode's label = argmax over S/E/T/B counts (git/misc excluded); ties -> M (mixed).
A cell is only credited by a REALIZED label; the static predictor is a prior (5/9-grade
accuracy on mechanism validation warns against trusting static labels — Report 17 §2.2).

Usage: behavior_classify.py [labels|predict|plan] (default: all three)
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

def episode_label(traj):
    d = json.load(open(traj))
    acts = [(st.get("action") or "").strip() for st in (d.get("trajectory") or [])]
    c = collections.Counter(act_class(a) for a in acts if a)
    core = {k: c.get(k, 0) for k in "SETB"}
    tot = sum(core.values())
    if not tot: return "M", c, 0
    best = max(core, key=core.get)
    ties = [k for k, v in core.items() if v == core[best]]
    label = "M" if len(ties) > 1 else best
    return label, c, tot

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

def cmd_predict(realized):
    rows = list(csv.DictReader(open(INV)))
    pred = {r["instance_id"]: predict_row(r) for r in rows}
    # agreement vs realized (banked instances present in the inventory: the 8 ML ones)
    id_of = {"tokio-rs": "tokio-rs__tokio-6551", "jqlang": "jqlang__jq-2681",
             "prometheus": "prometheus__prometheus-9248", "google": "google__gson-2061",
             "rubocop": "rubocop__rubocop-13668", "vuejs": "vuejs__core-11915",
             "php-cs-fixer": "php-cs-fixer__php-cs-fixer-7523", "babel": "babel__babel-15445",
             "fmtlib": "fmtlib__fmt-3248", "gin-gonic": "gin-gonic__gin-3741"}
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

if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    realized = cmd_labels()
    if what in ("all", "predict", "plan"):
        rows, pred = cmd_predict(realized)
        if what in ("all", "plan"):
            cmd_plan(realized, rows, pred)
