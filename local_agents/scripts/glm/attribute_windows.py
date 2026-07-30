#!/usr/bin/env python3
"""attribute_windows.py — attribute per-window microarchitecture metrics to tasks, command
tags, and the actual programs that ran, from banked l3_study CSVs + replay command logs.

Answers "why is metric M high for task T?" with traceable numbers instead of priors. Every
section below is one claim family in Report 15; run with no arguments to reproduce all of them.

    python3 attribute_windows.py [section ...]

    sections:  table    cross-task median + instruction-WEIGHTED episode ratio, both fences
               tags     per-command-tag medians (tool fence), per task
               mix      per-PASS instruction share by tag  (composition, per counter group)
               probe    instruction share of windows containing a given program family
               churn    the two rejected hypotheses: concurrent-PID and new-PID vs BTB_MPKI
               work     ground-truth workload per task from the REPLAYED trajectory

Key conventions (violating them produces wrong numbers):
  * An MPKI is a RATIO. The episode-level aggregate is Σevent/Σinstructions, obtained here by
    weighting each window's value by that window's instructions — NOT the median of windows,
    which weights a 30-Ginstr window the same as a 0.6-Ginstr one. Both are printed; they
    agree on the headline gaps and that agreement is the check.
  * Each metric comes from exactly ONE dedicated-group pass per task (cache group -> run_4,
    fe_miss -> run_11, ...). There is no within-task replicate, so cross-task gaps narrower
    than the IQR are unresolved. `table` prints p25/median/p75 so that is visible.
  * Metrics from DIFFERENT groups live in DIFFERENT windows, so they can never be correlated
    window-by-window. Only same-group quantities (e.g. BTB_MPKI and its own pass's command
    log) may be joined per window. `churn` relies on that.
  * The command tag is the highest-TAG_PRIORITY program seen by the 2 Hz poll inside the
    window; a 2-s window can hold several programs. Tags are suggestive, instructions are not.
"""
import csv, os, re, sys, glob, collections, statistics as st

ROOT = "/home/thu/InferSuite/local_agents"
# Per-task l3_study root: the three Python tasks come from the reproduced superseded_40min
# campaign, the two multilingual tasks only exist in the certified SWE_clean campaign.
CAMPAIGN = {"scikit-learn": "superseded_40min", "astropy": "superseded_40min",
            "sympy": "superseded_40min", "babel": "SWE_clean", "fmtlib": "SWE_clean",
            # SWE-bench Multilingual pilots (keys are the campaign's SHORT = instance owner).
            # They live in their own tree until they pass the ownership gate in `probe`; only
            # then is a language a candidate for promotion into the certified campaign.
            "tokio-rs": "ML_multiling", "jqlang": "ML_multiling", "gin-gonic": "ML_multiling",
            "prometheus": "ML_multiling", "php-cs-fixer": "ML_multiling",
            "google": "ML_multiling", "rubocop": "ML_multiling",
            "briannesbitt": "ML_multiling", "vuejs": "ML_multiling", "phpoffice-bT": "ML_multiling"}
LANG = {"scikit-learn": "Python", "astropy": "Python", "sympy": "Python",
        "babel": "JavaScript", "fmtlib": "C++",
        "tokio-rs": "Rust", "jqlang": "C", "gin-gonic": "Go", "prometheus": "Go",
        "google": "Java", "php-cs-fixer": "PHP",
        "rubocop": "Ruby", "briannesbitt": "PHP", "vuejs": "TypeScript",
        "phpoffice-bT": "PHP"}
TASKS = [t for t in CAMPAIGN
         if os.path.exists(f"{ROOT}/{CAMPAIGN[t]}/data/l3_study/all_windows_{t}.csv")]

HEADLINE = ["L1D_MPKI", "L2_MPKI", "LLC_MPKI", "AMAT_cyc", "MLP", "branchDir_MPKI",
            "branchInd_MPKI", "BTB_MPKI", "uopCache_MPKI", "DSB_pct", "MITE_pct", "MS_pct",
            "codeRead_MPKI_L1I", "IPC", "vecFP_pct", "tma_dram_bound_pct"]


def rows(task):
    p = f"{ROOT}/{CAMPAIGN[task]}/data/l3_study/all_windows_{task}.csv"
    out = []
    for d in csv.DictReader(open(p)):
        d["value"] = float(d["value"]); d["instructions"] = float(d["instructions"])
        d["t0"] = float(d["t0"]); d["dur"] = float(d["dur"])
        out.append(d)
    return out


ALL = {t: rows(t) for t in TASKS}


def cmdlog(task):
    """run -> sorted [(epoch, pid, argv)] from every replay pass of this task.

    windows.tsv t_start and the tagger's timestamps are the SAME epoch clock (both
    `date +%s.%N` on the host), so a window [t0, t0+dur) joins directly. Do not "align"
    them — that hazard belongs to perf-record lane samples, not to this pair.
    """
    per = collections.defaultdict(list)
    for p in glob.glob(f"{ROOT}/{CAMPAIGN[task]}/data/glm_replay_swe_{task}/run_*/cmdlog.tsv"):
        run = "run_" + re.search(r"run_(\d+)", p).group(1)   # CSV stores "run_N", not "N"
        for ln in open(p):
            f = ln.rstrip("\n").split("\t", 2)
            if len(f) < 3 or not f[2].strip(): continue
            try: per[run].append((float(f[0]), f[1], f[2]))
            except ValueError: pass
    for r in per: per[r].sort()
    return per


def sel(task, metric, fence="tool"):
    return [r for r in ALL[task] if r["metric"] == metric and r["fence"] == fence]


def wmean(rr):
    """instruction-weighted episode ratio — the correct aggregate for an MPKI."""
    I = sum(r["instructions"] for r in rr)
    return sum(r["value"] * r["instructions"] for r in rr) / I if I else float("nan")


def quant(v, p):
    v = sorted(v); i = (len(v) - 1) * p; lo = int(i)
    return v[lo] if lo == i else v[lo] + (v[lo + 1] - v[lo]) * (i - lo)


def spearman(xs, ys):
    def rk(v):
        s = sorted(range(len(v)), key=lambda i: v[i]); r = [0] * len(v)
        for pos, i in enumerate(s): r[i] = pos
        return r
    rx, ry = rk(xs), rk(ys)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** .5
    return num / den if den else float("nan")


def uniq_windows(rr):
    """one row per (group, run, win) so instructions are never double-counted across the
    several metrics a single pass emits from the same window."""
    seen, out = set(), []
    for r in rr:
        k = (r["group"], r["run"], r["win"])
        if k in seen: continue
        seen.add(k); out.append(r)
    return out


# ---------------------------------------------------------------- sections
def s_table():
    for fence in ("tool", "harness"):
        # Two blocks rather than one wide one: the weighted ratio is the number to quote, the
        # median+IQR is what decides whether a cross-task gap is resolved at all.
        print(f"\n=== {fence.upper()} fence — instruction-WEIGHTED episode ratio (the aggregate to quote) ===")
        print(f"{'metric':<20}" + "".join(f"{t[:13]:>14}" for t in TASKS))
        for m in HEADLINE:
            line = f"{m:<20}"
            for t in TASKS:
                rr = sel(t, m, fence)
                line += f"{wmean(rr):>14.2f}" if len(rr) >= 3 else f"{'-':>14}"
            print(line)
        print(f"{'Ginstr (fe_miss)':<20}" + "".join(
            f"{sum(r['instructions'] for r in sel(t,'BTB_MPKI',fence))/1e9:>14.0f}" for t in TASKS))
        print(f"\n--- {fence} fence — median [p25-p75] (n windows): gaps narrower than the IQR "
              f"are UNRESOLVED (one pass per metric) ---")
        print(f"{'metric':<20}" + "".join(f"{t[:13]:>24}" for t in TASKS))
        for m in HEADLINE:
            line = f"{m:<20}"
            for t in TASKS:
                rr = sel(t, m, fence)
                if len(rr) < 3: line += f"{'-':>24}"; continue
                v = [r["value"] for r in rr]
                line += f"{st.median(v):>8.2f}[{quant(v,.25):>5.2f}-{quant(v,.75):<5.2f}]({len(v):>3})"
            print(line)


def s_tags():
    for t in TASKS:
        rr = [r for r in ALL[t] if r["fence"] == "tool"]
        keep = [tg for tg, _ in collections.Counter(r["tag"] for r in rr).most_common()]
        print(f"\n#### {t} ({LANG[t]}) — TOOL fence median by command tag (>=3 windows shown)")
        print(f"{'metric':<20}" + "".join(f"{tg[:15]:>17}" for tg in keep))
        for m in HEADLINE:
            line = f"{m:<20}"
            for tg in keep:
                v = [r["value"] for r in rr if r["tag"] == tg and r["metric"] == m]
                line += f"{st.median(v):>11.2f}({len(v):>3})" if len(v) >= 3 else f"{'-':>17}"
            print(line)


def s_mix():
    for t in TASKS:
        tool = [r for r in ALL[t] if r["fence"] == "tool"]
        groups = sorted({r["group"] for r in tool})
        print(f"\n#### {t} ({LANG[t]}) — per-PASS tool-fence instruction share by tag")
        for g in groups:
            w = uniq_windows([r for r in tool if r["group"] == g])
            I = collections.Counter()
            for r in w: I[r["tag"]] += r["instructions"]
            tot = sum(I.values())
            if not tot: continue
            run = sorted({r["run"] for r in w})[0]
            mix = " ".join(f"{k}={100*v/tot:.0f}%" for k, v in I.most_common())
            print(f"  {g:<11} {run:<7}{tot/1e9:>7.0f} Ginstr  n={len(w):>3}  {mix}")


# Per-task regex for "this language's own toolchain was running". Deliberately WIDE: it must catch
# the compiler, the test runner AND the package/build driver, because the heavy windows can belong
# to any of them (babel's weight is in jest, fmt's in cc1plus). Too narrow a probe under-credits a
# language and would fail the ownership gate for the wrong reason — the mistake that nearly made me
# "correct" a report that was right.
PROBE = {"babel": r"\bnode\b|jest|yarn|npm", "fmtlib": r"cc1plus|/c\+\+|\bg\+\+",
         "sympy": r"python", "astropy": r"python", "scikit-learn": r"python",
         "tokio-rs":     r"\bcargo\b|\brustc\b|\bld\b|/target/(debug|release)/",
         "jqlang":       r"\bcc1\b|\bgcc\b|\bcc\b|\bmake\b|\bld\b|\bjq\b",
         "gin-gonic":    r"\bgo\b|pkg/tool/|/tmp/go-build",
         "prometheus":   r"\bgo\b|pkg/tool/|/tmp/go-build",
         "php-cs-fixer": r"\bphp\b|phpunit|composer|php-cs-fixer",
         "phpoffice-bT":  r"\bphp\b|phpunit|composer",
         "google":       r"\bjava\b|\bjavac\b|\bmvn\b|maven|surefire|\bgradle",
         "rubocop":      r"\bruby\b|\brspec\b|\brake\b|\bbundle\b",
         "briannesbitt": r"\bphp\b|phpunit|composer",
         "vuejs":        r"\bnode\b|vitest|\bjest\b|\btsc\b|pnpm|yarn|npm"}
# The gate from Report 15 insight 7: below this share of tool-fence instructions, the fence is not
# measuring the language and the task must not be presented on a language axis.
OWNERSHIP_GATE_PCT = 50.0
# ADEQUACY is a SEPARATE criterion, added 2026-07-29 after Go (gin-3741) passed ownership at
# 74.8 % on a fence of 137 Ginstr / 15 windows — two orders of magnitude below the C++ column it
# would have sat next to. Ownership says the right program ran; adequacy says enough of it ran to
# support a per-window distribution. A task must clear BOTH. The floor is set at babel, the
# weakest task already accepted into the deck (~190 Ginstr and 20 windows per pass), so nothing
# previously published is retroactively invalidated by the new criterion.
ADEQUACY_MIN_WINDOWS_PER_PASS = 20
ADEQUACY_MIN_GINSTR_PER_PASS = 150


def s_probe():
    print("Instruction share of windows in which the task's own toolchain was OBSERVED.\n"
          "Presence is an upper bound on that program's share (other processes coexist in a\n"
          "2-s window), but it bounds the OPPOSITE error: a language cannot be credited for\n"
          "work in windows where its runtime never appeared.")
    for t in TASKS:
        cl = cmdlog(t); rx = PROBE[t]
        w = uniq_windows([r for r in ALL[t] if r["fence"] == "tool"])
        tot = hit = 0.0; nw = nh = 0
        for r in w:
            has = any(r["t0"] <= tm < r["t0"] + r["dur"] and re.search(rx, a)
                      for tm, _, a in cl.get(r["run"], []))
            tot += r["instructions"]; nw += 1
            if has: hit += r["instructions"]; nh += 1
        pct = 100 * hit / tot if tot else 0.0
        npass = len({(r["group"], r["run"]) for r in w}) or 1
        wpp, gpp = nw / npass, tot / 1e9 / npass
        own = pct >= OWNERSHIP_GATE_PCT
        adeq = wpp >= ADEQUACY_MIN_WINDOWS_PER_PASS and gpp >= ADEQUACY_MIN_GINSTR_PER_PASS
        verdict = ("PASS" if adeq else "OWNED but TOO SMALL — insufficient for a language column") \
                  if own else "FAIL — not a language measurement"
        print(f"  {t:<14} {LANG[t]:<11} windows {nh:>4}/{nw:<4} ({100*nh/nw if nw else 0:>3.0f}%)   "
              f"instr {pct:>5.1f}%  of {tot/1e9:>6.0f} Ginstr   "
              f"per-pass {wpp:>4.0f}w/{gpp:>5.0f}G   [{verdict}]")


def s_churn():
    print("Two hypotheses for the BTB_MPKI spread, both REJECTED. A cold BTB after a context\n"
          "switch or exec is a real microarchitectural effect, but neither proxy tracks it here:\n"
          "the per-task signs disagree, so no single mechanism is supported.\n")
    for label, newonly in (("concurrent PIDs in window", False), ("newly-appearing PIDs", True)):
        pooled_x, pooled_y = [], []
        print(f"  -- {label} vs BTB_MPKI (same pass, so a legal per-window join) --")
        for t in TASKS:
            cl = cmdlog(t)
            first = {}
            for run, s in cl.items():
                for tm, pid, _ in s: first.setdefault((run, pid), tm)
            xs, ys = [], []
            for r in sel(t, "BTB_MPKI"):
                a, b = r["t0"], r["t0"] + r["dur"]
                if newonly:
                    n = sum(1 for (run, pid), tm in first.items()
                            if run == r["run"] and a <= tm < b)
                else:
                    n = len({pid for tm, pid, _ in cl.get(r["run"], []) if a <= tm < b})
                xs.append(n); ys.append(r["value"])
            if len(xs) >= 8:
                print(f"     {t:<14} Spearman = {spearman(xs,ys):+.3f}   n={len(xs)}")
            pooled_x += xs; pooled_y += ys
        print(f"     {'POOLED':<14} Spearman = {spearman(pooled_x,pooled_y):+.3f}   "
              f"n={len(pooled_x)}\n")


# The trajectory actually replayed per task (metadata.json extra.traj of any pass). Hardcoded
# because it is evidence: the astropy and sympy L3 study replayed run_2, NOT run_1, and reading
# run_1 misattributes the workload.
def traj_of(task):
    for p in sorted(glob.glob(f"{ROOT}/{CAMPAIGN[task]}/data/glm_replay_swe_{task}/run_*/metadata.json")):
        import json
        d = json.load(open(p))
        tj = (d.get("extra") or {}).get("traj") or d.get("traj")
        if tj: return tj
    return None


WORK = [("tests(pytest)", r"-m pytest|\bpytest\b|py\.test|runtests"),
        ("tests(js)", r"\bjest\b|\bmocha\b|yarn |npm "),
        ("compile", r"\bg\+\+|\bgcc\b|\bmake\b|cmake|ninja|\bclang"),
        ("run-binary", r"\./bin/|\./reproduce|\bnode \w"),
        ("python -c snippet", r"python3? -c"), ("editor", r"str_replace_editor"),
        ("search/read", r"\bgrep\b|\bfind\b|\bls\b|\bcat\b|\bsed\b|head |tail "),
        ("git", r"\bgit\b")]


def s_work():
    import json
    print("Ground truth: what each REPLAYED episode actually does. Action counts describe the\n"
          "agent's behaviour; the instruction share in `mix`/`probe` describes where CPU went.\n"
          "They differ a lot (babel: 72% of actions are searches, 77% of instructions are JS).")
    for t in TASKS:
        tj = traj_of(t)
        if not tj or not os.path.exists(tj):
            print(f"\n#### {t}: trajectory not found ({tj})"); continue
        d = json.load(open(tj))
        acts = [(s.get("action") or "").strip() for s in (d.get("trajectory") or [])]
        acts = [a for a in acts if a]
        # strip the harness's `cd <repo> && ` prefix or every action reads as "cd"
        acts = [re.sub(r"^cd\s+\S+\s*&&\s*", "", a, flags=re.S).strip() for a in acts]
        cnt = collections.Counter()
        for a in acts:
            for name, rx in WORK:
                if re.search(rx, a): cnt[name] += 1; break
            else: cnt["other"] += 1
        inst = os.path.basename(os.path.dirname(tj))
        print(f"\n#### {t} ({LANG[t]}) — {inst}, replayed from {os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(tj))))}"
              f"\n     {len(acts)} actions: " +
              ", ".join(f"{k} {100*v/len(acts):.0f}%" for k, v in cnt.most_common(6)))
        polls = collections.Counter()
        for _, _, a in [x for run in cmdlog(t).values() for x in run]:
            if "swerex" in a or a.strip() == "bash" or a.startswith("/bin/sh -c /root"): continue
            polls[re.sub(r"\s+", " ", a).strip()[:78]] += 1
        for k, v in polls.most_common(4):
            print(f"       {v:>5} polls  {k}")


SECTIONS = {"table": s_table, "tags": s_tags, "mix": s_mix, "probe": s_probe,
            "churn": s_churn, "work": s_work}

if __name__ == "__main__":
    want = [a for a in sys.argv[1:] if not a.startswith("-")] or list(SECTIONS)
    for name in want:
        if name not in SECTIONS:
            sys.exit(f"unknown section {name!r}; pick from {', '.join(SECTIONS)}")
        print(f"\n{'='*100}\n== {name}\n{'='*100}")
        SECTIONS[name]()
