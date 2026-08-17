#!/usr/bin/env python3
"""typeid_classify.py — ML_typeid classification sweep: population, per-episode labels, ledger.

The first-live-run TYPE IDENTIFICATION pass over SWE-bench Multilingual (branch
multiling-type-id): every remaining instance gets one cheap live episode on a non-P7
machine (no isolation, no perf), and this tool turns each episode into a record

    mechanism (static repo lookup, argv-WITNESSED)  x  realized behaviour (S/E/T/B/M)
    x  magnitude bin (raw + bootstrap-corrected tool-fence core-s, PROVISIONAL bins)
    x  viability flags (E7-mirror uniqueness, starvation, drain, label support)

Label rules are IMPORTED from behavior_classify.py (act_class/episode_label/credits) —
byte-identical to the rules behind the 16 already-measured episodes; do not fork them.
Magnitude numbers from this machine are ordinal only: the P7 layer-3 stop gate re-judges
any picked task before profiling. Protocol: local_agents/ML_typeid/README.md.

  remaining            print sweep population (inventory minus consumed), language-interleaved
  episode DIR [--ledger] [--instance ID]   summarize one run dir -> episode_summary.json
                       + tokens_steps.tsv; --ledger appends the typing_ledger.tsv row
  mark ID STATUS DETAIL [--ledger]         driver-level event (no-image, pull-fail, ...)
  matrix               <language, realized-type> matrix + progress from the ledger
"""
import csv, glob, importlib.util, json, os, re, sys, time, collections

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
INV = f"{REPO}/local_agents/ML_multiling/sampling_frame/task_inventory.csv"
DATA = os.environ.get("TYPEID_DATA", f"{REPO}/local_agents/ML_typeid/data")
LEDGER = os.environ.get("TYPEID_LEDGER", f"{REPO}/local_agents/ML_typeid/typing_ledger.tsv")

_spec = importlib.util.spec_from_file_location(
    "bc", f"{REPO}/local_agents/kit/replay/behavior_classify.py")
bc = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(bc)

# Consumed by earlier campaigns (banked accepts + parked rejects + behaviour probes).
# The traj-dir scan below catches these too when the data is present; this constant is the
# safety net for the two episodes whose .traj did not survive the workstation migration.
DONE_INSTANCES = {
    "tokio-rs__tokio-6551", "jqlang__jq-2681", "prometheus__prometheus-9248",
    "google__gson-2061", "rubocop__rubocop-13668", "vuejs__core-11915",
    "php-cs-fixer__php-cs-fixer-7523", "babel__babel-15445", "fmtlib__fmt-3248",
    "gin-gonic__gin-3741", "briannesbitt__carbon-2813", "laravel__framework-51890",
    "phpoffice__phpspreadsheet-3940", "preactjs__preact-4152", "hashicorp__terraform-35543",
}

# Per-language toolchain witness regexes. DUPLICATED from behavior_campaign.sh gate_of()
# (a known divergence hazard — classification_protocol.md §5); keep in sync by hand.
PROBE = {"Rust": r"\bcargo\b|\brustc\b|\bld\b|/target/(debug|release)/",
         "C": r"\bcc1\b|\bgcc\b|\bcc\b|\bmake\b|\bld\b",
         "Go": r"\bgo\b|pkg/tool/|/tmp/go-build",
         "Java": r"\bjava\b|\bjavac\b|\bmvn\b|maven|surefire|\bgradle",
         "Ruby": r"\bruby\b|\brspec\b|\brake\b|\bbundle\b|/bundle/bin/",
         "PHP": r"\bphp\b|phpunit|composer",
         "JavaScript": r"\bnode\b|jest|yarn|npm|esbuild",
         "TypeScript": r"\bnode\b|vitest|\bjest\b|\btsc\b|pnpm|yarn|npm|esbuild",
         "C++": r"cc1plus|/c\+\+|\bg\+\+|\bmake\b"}

# Container-bootstrap lineage (swerex image setup, NOT agent tool work): the interval it
# spans is subtracted from the tool fence before the floor bin (taxonomy STEP 5; 15% of
# gin's fence was apt/dpkg). Capped at the first BOOT_CAP_S seconds of the episode.
BOOT_RX = re.compile(r"apt-get |/usr/lib/apt/|\bdpkg\b|pip3? install|python3? -m pip install")
BOOT_CAP_S = 300.0

FLOOR = float(os.environ.get("TYPEID_FLOOR", 10))    # PROVISIONAL bin edges (this-machine
LARGE = float(os.environ.get("TYPEID_LARGE", 60))    # core-s); calibrate vs banked reruns
LOOP_N = int(os.environ.get("LOOP_GUARD_N", 12))

LEDGER_COLS = ["when", "instance", "language", "mech", "status", "realized", "mix",
               "support", "other_pct", "steps", "uniq_frac", "longest_run", "flags",
               "wall_s", "tool_cs_raw", "tool_cs_corr", "harness_cs", "proxy_cs",
               "magnitude_bin", "witness_cov", "tokens_sent", "tokens_received",
               "api_calls", "exit_status", "detail"]


def inv_rows():
    return list(csv.DictReader(open(INV)))


def short_of(inst):
    return inst.split("__")[0] + "-t" + inst.rsplit("-", 1)[-1]


def consumed():
    got = set(DONE_INSTANCES)
    for p in glob.glob(f"{REPO}/local_agents/*/data/glm_swe_*/run_*/traj/*"):
        if os.path.isdir(p) and "__" in os.path.basename(p):
            got.add(os.path.basename(p))
    for r in ledger_rows():
        if r["status"] in ("classified", "starved", "episode-fail"):
            got.add(r["instance"])
    return got


def ledger_rows():
    if not os.path.exists(LEDGER):
        return []
    return list(csv.DictReader(open(LEDGER), delimiter="\t"))


def ledger_append(row):
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    new = not os.path.exists(LEDGER)
    with open(LEDGER, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=LEDGER_COLS, delimiter="\t", extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow({c: row.get(c, "") for c in LEDGER_COLS})


def cmd_remaining():
    done = consumed()
    by_lang = collections.defaultdict(list)
    for r in inv_rows():
        if r["instance_id"] not in done:
            by_lang[r["language"]].append(r["instance_id"])
    for lang in by_lang:
        by_lang[lang].sort()
    langs = sorted(by_lang)          # round-robin: early episodes spread across languages,
    out = []                         # so the matrix populates evenly from the first day
    while any(by_lang[l] for l in langs):
        for l in langs:
            if by_lang[l]:
                out.append(by_lang[l].pop(0))
    for i in out:
        print(i)


# ---- per-episode ----------------------------------------------------------------------
def read_cpustat(path):
    out = []
    try:
        for ln in open(path):
            p = ln.split()
            if len(p) >= 3 and p[1] == "usage_usec" and float(p[2]) >= 0:
                out.append((float(p[0]), float(p[2])))
    except OSError:
        pass
    return out


def cs_total(series):
    return (series[-1][1] - series[0][1]) / 1e6 if len(series) > 1 else 0.0


def cs_over(series, t0, t1):
    """usage delta (core-s) between the samples nearest t0 and t1."""
    if len(series) < 2:
        return 0.0
    def at(t):
        best = min(series, key=lambda s: abs(s[0] - t))
        return best[1]
    return max(0.0, (at(t1) - at(t0)) / 1e6)


def read_cmdlog(path):
    rows = []
    try:
        for ln in open(path, errors="replace"):
            f = ln.rstrip("\n").split("\t", 2)
            if len(f) >= 3 and f[2].strip():
                try:
                    rows.append((float(f[0]), f[2]))
                except ValueError:
                    pass
    except OSError:
        pass
    return rows


def episode_summary(out_dir, instance=None):
    meta = {}
    mp = os.path.join(out_dir, "metadata.json")
    if os.path.exists(mp):
        meta = json.load(open(mp))
    inst = instance or (meta.get("extra") or {}).get("instance", "")
    inv = {r["instance_id"]: r for r in inv_rows()}
    lang = inv[inst]["language"] if inst in inv else ""
    mech = inv[inst]["mech_class"] if inst in inv else ""

    s = {"instance": inst, "language": lang, "mech": mech,
         "when": time.strftime("%F.%T"), "status": "episode-fail", "flags": []}

    trajs = [p for p in glob.glob(f"{out_dir}/traj/*/*.traj") if not p.endswith(".local.traj")]
    tokens = []
    up = os.path.join(out_dir, "proxy_usage.jsonl")
    if os.path.exists(up):
        for ln in open(up):
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if r.get("status") == "success":
                tokens.append(r)
        tokens.sort(key=lambda r: r.get("ts_end", 0))

    if trajs:
        d = json.load(open(trajs[0]))
        acts = [(st.get("action") or "").strip() for st in (d.get("trajectory") or [])]
        acts = [a for a in acts if a]
        lab, c, tot = bc.episode_label(trajs[0])
        sh, _ = bc._shares(c)
        s.update(realized=lab, mix=" ".join(f"{k}={sh[k]:.0f}%" for k in "SETB"),
                 support=tot, other_pct=round(100 * c.get("other", 0) / max(len(acts), 1), 1),
                 steps=len(acts))
        uniq = len(set(acts)) / max(len(acts), 1)
        longest = mx = 1
        for i in range(1, len(acts)):
            mx = mx + 1 if acts[i] == acts[i - 1] else 1
            longest = max(longest, mx)
        s.update(uniq_frac=round(uniq, 3), longest_run=longest)
        if longest >= LOOP_N:
            s["flags"].append("E7-consecutive-loop")
        if uniq < 0.40 and len(acts) >= 10:
            s["flags"].append("E7-cyclic-loop")
        if tot and tot < 10:
            s["flags"].append("low-support")
        info = d.get("info") or {}
        ms = info.get("model_stats") or {}
        s.update(exit_status=info.get("exit_status", ""),
                 tokens_sent=ms.get("tokens_sent", ""),
                 tokens_received=ms.get("tokens_received", ""),
                 api_calls=ms.get("api_calls", ""))
        starved = len(acts) < 5 or ms.get("tokens_received", None) == 0
        s["status"] = "starved" if starved else "classified"

        # per-step token attribution (call i <-> step i; dprompt = context growth charged
        # to the PREVIOUS action's observation)
        if tokens:
            with open(os.path.join(out_dir, "tokens_steps.tsv"), "w") as fh:
                fh.write("call\tts_end\tprompt_tokens\tcompletion_tokens\tdprompt\tact_class\taction\n")
                prev = None
                for i, r in enumerate(tokens):
                    a = acts[i] if i < len(acts) else ""
                    dp = (r.get("prompt_tokens") or 0) - (prev or 0) if prev is not None else ""
                    prev = r.get("prompt_tokens") or 0
                    fh.write(f"{i}\t{r.get('ts_end','')}\t{r.get('prompt_tokens','')}\t"
                             f"{r.get('completion_tokens','')}\t{dp}\t"
                             f"{bc.act_class(a) if a else ''}\t{a[:80]}\n")
            if abs(len(tokens) - len(acts)) > 2:
                s["flags"].append(f"call-step-mismatch({len(tokens)}v{len(acts)})")
    else:
        s["detail"] = "no traj"

    harness = read_cpustat(os.path.join(out_dir, "cpustat_scope1.tsv"))
    tool = read_cpustat(os.path.join(out_dir, "cpustat_scope2.tsv"))
    proxy = read_cpustat(os.path.join(out_dir, "cpustat_scope3.tsv"))
    if tool:
        s["wall_s"] = round(tool[-1][0] - tool[0][0], 1)
    s["tool_cs_raw"] = round(cs_total(tool), 2)
    s["harness_cs"] = round(cs_total(harness), 2)
    s["proxy_cs"] = round(cs_total(proxy), 2)

    cmd = read_cmdlog(os.path.join(out_dir, "cmdlog.tsv"))
    corr = s["tool_cs_raw"]
    if cmd and tool:
        t_start = cmd[0][0]
        boot_ts = [t for t, a in cmd if BOOT_RX.search(a) and t - t_start <= BOOT_CAP_S]
        if boot_ts:
            boot_cs = cs_over(tool, t_start, max(boot_ts))
            corr = max(0.0, s["tool_cs_raw"] - boot_cs)
            s["boot_cs"] = round(boot_cs, 2)
        ticks = sorted({t for t, _ in cmd})
        if lang in PROBE:
            rx = re.compile(PROBE[lang])
            hit = {t for t, a in cmd if rx.search(a)}
            s["witness_cov"] = round(len(hit) / max(len(ticks), 1), 3)
            if not hit:
                s["flags"].append("mechanism-not-witnessed")
        top = collections.Counter(a.split()[0].rsplit("/", 1)[-1] for _, a in cmd)
        s["top_progs"] = top.most_common(10)
    s["tool_cs_corr"] = round(corr, 2)
    s["magnitude_bin"] = ("below-floor" if corr < FLOOR else
                          "measurable" if corr < LARGE else "large")
    s["flags"] = ",".join(s["flags"])
    json.dump(s, open(os.path.join(out_dir, "episode_summary.json"), "w"), indent=1)
    return s


def cmd_episode(out_dir, to_ledger, instance):
    s = episode_summary(out_dir, instance)
    if to_ledger:
        ledger_append(s)
    print(f"STATUS {s['status']} {s.get('instance','?')} realized={s.get('realized','-')} "
          f"mix=[{s.get('mix','-')}] tool_cs={s.get('tool_cs_corr','-')} "
          f"bin={s.get('magnitude_bin','-')} flags=[{s.get('flags','')}]")


def cmd_mark(inst, status, detail, to_ledger):
    inv = {r["instance_id"]: r for r in inv_rows()}
    row = {"when": time.strftime("%F.%T"), "instance": inst,
           "language": inv.get(inst, {}).get("language", ""),
           "mech": inv.get(inst, {}).get("mech_class", ""),
           "status": status, "detail": detail}
    if to_ledger:
        ledger_append(row)
    print(f"STATUS {status} {inst} {detail}")


def cmd_matrix():
    rows = ledger_rows()
    langs = sorted({r["language"] for r in inv_rows()})
    cells = collections.defaultdict(collections.Counter)
    bad = collections.Counter()
    for r in rows:
        if r["status"] == "classified" and r.get("realized"):
            cells[r["language"]][r["realized"]] += 1
        else:
            bad[r["status"]] += 1
    print(f"{'lang':<12}" + "".join(f"{t:>6}" for t in "SETBM"))
    for l in langs:
        print(f"{l:<12}" + "".join(f"{cells[l].get(t, 0):>6}" for t in "SETBM"))
    n_rem = len(cmd_remaining_list())
    print(f"\nledger: {len(rows)} rows ({dict(bad)} non-classified) | remaining: {n_rem}")


def cmd_remaining_list():
    done = consumed()
    return [r["instance_id"] for r in inv_rows() if r["instance_id"] not in done]


if __name__ == "__main__":
    args = sys.argv[1:]
    what = args[0] if args else "matrix"
    if what == "remaining":
        cmd_remaining()
    elif what == "episode":
        inst = args[args.index("--instance") + 1] if "--instance" in args else None
        cmd_episode(args[1], "--ledger" in args, inst)
    elif what == "mark":
        cmd_mark(args[1], args[2], args[3] if len(args) > 3 else "", "--ledger" in args)
    elif what == "matrix":
        cmd_matrix()
    else:
        sys.exit(__doc__)
