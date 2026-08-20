#!/usr/bin/env python3
"""typeid_cpu_matrix.py — build the ⟨language × measured-CPU-type⟩ matrix from the
receipt-instrumented replay sweep (typeid_replay_sweep.sh output).

Inputs per replay dir (DATA/glm_replay_swe_*/run_1): cpustat_scope2.tsv (exact fence),
cmdlog.tsv (2 Hz argv), pidcpu.tsv (2 Hz per-PID CPU), taskstats.tsv (exit receipts).

Two compositions per episode, both over B/T/S coarse classes (E is structurally ~0 in CPU):
  OWNERSHIP — a receipt's CPU belongs to the nearest enclosing driver front-end
    (make/configure/cargo test/phpunit...), walked self-upward through the receipt ppid
    graph; argv beats comm when the 2 Hz cmdlog saw the pid. This is the l3 window
    ontology: validated <=9 pt against the P7 instruction-weighted truth on the three
    strict cases (jq/tokio/php-cs-fixer, 2026-08-17). THE MATRIX AND SELECTION USE THIS.
  PROCESS — a receipt's CPU belongs to its own comm (thread-name fixups applied). The
    mechanism view: exact per-process physics (rustc really burned X core-s), but its
    coarse S/T/B projection is context-blind for driver children (configure's sed storms)
    and repo-payload binaries (jq) — report it, do not select on it alone.

Type label per view: argmax class if it leads by >= MARGIN (10 pts), else M (mixed) —
same rule as behavior_classify. Accounting uses P receipts only (each task dies exactly
once; G aggregates double-count). Coverage = (receipts + alive-at-end pidcpu) / fence;
low coverage or low classified share flags the label, never silently.

Usage:
  typeid_cpu_matrix.py build   [--data DIR]   # scan replays -> cpu_matrix.tsv
  typeid_cpu_matrix.py matrix  [--data DIR]   # print the language x type matrices
"""
import collections
import csv
import glob
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ML = f"{REPO}/local_agents/ML_typeid"
CLK = os.sysconf("SC_CLK_TCK")
MARGIN = 10.0
BOOT_RX = re.compile(r"apt-get |/usr/lib/apt/|\bdpkg\b|pip3? install|python3? -m pip install")
BOOT_CAP_S = 300.0
# LEAFCOUNT — the count-weighted alternative to time weighting (piloted 2026-08-19 on 151
# PHP/Ruby/JS/TS/C episodes): label the episode by the class with the most *leaf commands*
# instead of the most CPU. Banked as columns for comparison; labels/matrix/selection stay
# time-weighted. 21 of 151 labels flip (13 T->S), because a counted `search` costs 1.1 ms
# against 22 ms for a test command and 50 ms for a build one — the flips are the toolchain's
# own shell plumbing (configure's sed probes; a `sort|uniq|wc` pipeline run 4500x by vue's
# build), not agent searches, which live on Axis 2. A leaf command = an in-fence receipt with
# a voting tag that spawned nothing; thread receipts are excluded by name shape.
THREADISH = re.compile(
    r"[ :/]"                                                   # spaces, '::', paths
    r"|^(tokio-runtime|runtime-worker|blocking|rayon)"         # rust runtime threads
    r"|^(GC|G1|C1|C2|VM|Finalizer|Reference|CompilerThr|PmdThread|Common-Cleaner|Thread-\d)"  # JVM
    r"|^(ThreadPool|Chrome_|Compositor|VizCompositor|ServiceWorker|chrome_crashpad)"          # chromium
    r"|^(coordinator|event_loop|flush_thread|socket_manager|enqueue_thread)$")

# ---- process tagger (same vocabulary as the pilot; comm- and argv-tolerant) -----------
COMPILER = {"cc1", "cc1plus", "cc", "c++", "gcc", "g++", "clang", "clang++", "rustc",
            "javac", "as", "ld", "ld.lld", "collect2", "lto1", "lto-wrapper", "lto2",
            "tsc", "cpp", "ar", "ranlib", "objcopy", "strip", "nasm",
            "esbuild", "swc"}          # JS/TS transpilers: class N's transpile term (136 core-s)
GO_TOOL = {"compile", "link", "asm", "cgo", "buildid", "pack", "vet"}
DRIVER = {"make", "gmake", "cmake", "ninja", "cargo", "mvn", "gradle", "gradlew",
          "meson", "scons", "libtool", "autoconf", "automake", "configure", "rake", "m4"}
PKG = {"apt", "apt-get", "dpkg", "pip", "pip3", "composer", "bundler", "gem",
       "py3compile", "localedef"}      # dpkg post-install work (bytecode, locales)
TESTRUN = {"pytest", "jest", "vitest", "mocha", "rspec", "phpunit", "gotestsum", "ctest",
           "karma", "ava", "tap", "tclsh", "tclsh8.6", "surefire", "minitest", "cucumber",
           "playwright", "puppeteer", "chrome", "chromium", "headless_shell"}
RUNTIME = {"java", "node", "php", "ruby", "python3", "python", "perl", "deno", "bun",
           "valkey-server", "redis-server"}
SEARCH = {"grep", "rg", "egrep", "fgrep", "find", "cat", "ls", "head", "tail", "tree",
          "wc", "sed", "awk", "tr", "sort", "uniq", "cut", "diff", "less", "file", "stat", "du",
          "javap", "nm", "strings", "objdump", "readelf"}   # artifact inspection = reading
SCAFFOLD = {"dd", "cmp", "uname",                           # shell helpers inside jq's shtest
            "sh", "bash", "dash", "sleep", "timeout", "env", "which", "tee", "xargs",
            "dirname", "basename", "true", "false", "echo", "printf", "date", "id",
            "mkdir", "rm", "cp", "mv", "touch", "chmod", "ln", "readlink", "pwd", "kill",
            "ps", "sudo", "su", "tar", "gzip", "unzip", "curl", "wget", "nproc", "stty"}
TEST_BIN = re.compile(r"\.test$|\.tes$|^test[_-]|[_-]test$|-[0-9a-f]{16}$|_test$")  # .tes = comm cut at 15
NPM_BUILD = re.compile(r"\b(install|ci|add|update|download|fetch)\b")
THREAD_FIX = [
    (re.compile(r"^(tokio-runtime|runtime-worker|blocking|rayon)"), "test-run"),
    (re.compile(r"^(opt [a-z0-9_.]+|lto cgu|coordinator|rustc|build-script-bu)"), "compile"),
    (re.compile(r"^(GC |G1 |C1 |C2 |VM |Finalizer|Reference|CompilerThr)"), "test-run"),
    # census of `other` comms over 141 receipt episodes (2026-08-18):
    (re.compile(r"^PmdThread"), "lint"),              # PMD static analysis under maven (apache: 1364 core-s)
    (re.compile(r"^(Sweeper thread|ThreadedStreamC|Parallel Class|fork-\d+-event)"), "test-run"),  # surefire/JVM
    (re.compile(r"::tests?::|^regextest$"), "test-run"),   # Rust test threads named after the test path
    (re.compile(r"^(event_loop|flush_thread|socket_manager|enqueue_thread)"), "test-run"),  # fluentd under test
    (re.compile(r"^(Compact Index|Parallel Instal)"), "pkg"),  # bundler resolver
    (re.compile(r"^gulp "), "build-drv"),
    (re.compile(r"^(git-remote-http|git-upload-pack)"), "vcs"),
    (re.compile(r"^(apt-cache|apt-config)$"), "pkg"),
    (re.compile(r"^(_state_anthropi|submit|store|str_replace_edi|http)$"), None),  # SWE-agent tool plumbing = scaffold
    # census of `other` comms over 297 receipt episodes (2026-08-19). `comm` is 15 chars, so
    # the long names below are truncations the exact-match sets above can never see:
    (re.compile(r"^lto1?[ -]"), "compile"),           # GCC/rustc LTO workers: lto1-ltrans, lto1-wpa,
                                                      # `lto <hash>` (482 core-s, redis/valkey LTO builds)
    (re.compile(r"^(cargo-clippy|clippy-driver|rustfmt|cargo-fmt)"), "lint"),
    (re.compile(r"^(ThreadPool|Chrome_|Compositor|VizCompositor|ServiceWorker|chrome_crashpad)"),
     "test-run"),                                     # headless chromium driven by playwright/puppeteer
    # Rust names its test threads after the test path (`runtime::tests:`, `axum/src/routin`).
    # The pattern MUST be anchored and space-free: matched against a full argv it would tag
    # every compile whose command line mentions a /src/ path as test-run (caught 2026-08-19:
    # `ld -o redis-server …/src/…` and `c++ -I /testbed/src/…` both flipped BUILD to TEST).
    (re.compile(r"^(?!/)[^ ]*(::|/src/)|^rust_out$"), "test-run"),
]
# REPO PAYLOAD REGISTRY — the repo's own binary, run as the program under test. No generic
# rule can recognise these (`jq` looks like nothing; `rg` looks like SEARCH), yet in their own
# repo they are the verification payload. Process view without this bucket loses e.g. 27% of
# jq's fence to `other`; ownership view is unaffected (their ancestor is the test/make front).
# Registered names are tagged test-run. Names that ALSO appear in SEARCH (rg) win here.
PAYLOAD_BIN = {"jq", "shtest",                           # jqlang/jq — tests/shtest drives jq
                                                         # (its dd/cmp helpers stay `other`: generic names)
               "rg",                                     # burntsushi/ripgrep
               "bat",                                    # sharkdp/bat
               "hugo",                                   # gohugoio/hugo
               "caddy",                                  # caddyserver/caddy
               "terraform",                              # hashicorp/terraform
               "nu",                                     # nushell/nushell
               "coreutils",                              # uutils/coreutils multicall binary
               "ruff", "ruff_dev",                       # astral-sh/ruff
               "gin",                                    # gin-gonic (examples)
               "redis-server", "redis-cli", "redis-benchmark", "valkey-server", "valkey-cli",
               "micropython", "mpy-cross",               # micropython
               "fmt", "json_unit",                       # fmtlib / nlohmann test binaries are TEST_BIN mostly
               "rubocop", "fluentd", "fastlane", "jekyll", "fpm", "faker",  # ruby CLIs
               "php-cs-fixer", "artisan",                # php CLIs
               "lombok", "delombok"}                     # projectlombok
COARSE = {"compile": "BUILD", "build-drv": "BUILD", "pkg": "BUILD",
          "test-run": "TEST", "runtime": "TEST", "lint": "TEST",
          "search": "SEARCH"}          # vcs (git clone/checkout) is not "search": left unclassified
OWNER_CLASSES = {"test-run", "build-drv", "pkg"}


def tag_of(a):
    a = a.strip()
    toks = a.split()
    if not toks:
        return None
    exe = toks[0].rsplit("/", 1)[-1]
    al = a.lower()
    if "swerex-remote" in al or exe.startswith("python3.1"):
        return None
    if BOOT_RX.search(a):
        return "pkg"
    for rx, tg in THREAD_FIX:
        if rx.search(a):
            return tg                       # may be None -> scaffold (agent tool plumbing)
    if exe in PAYLOAD_BIN:                  # before SEARCH: `rg` in ripgrep is the payload
        return "test-run"
    if exe in COMPILER:
        return "compile"
    if exe in GO_TOOL and (len(toks) == 1 or "pkg/tool" in a or "/go-build" in a):
        return "compile" if exe != "vet" else "lint"
    if exe in PKG:
        return "pkg"
    if exe in ("npm", "pnpm", "yarn", "bundle", "composer"):
        return "pkg" if NPM_BUILD.search(al) else "test-run"
    if exe == "go":
        return "test-run" if re.search(r"\bgo\s+test\b", al) else "build-drv"
    if exe == "cargo":
        return "test-run" if re.search(r"\bcargo\s+test\b", al) else "build-drv"
    if exe in DRIVER:
        return "build-drv"
    if exe in TESTRUN or TEST_BIN.search(exe):
        return "test-run"
    if exe in RUNTIME:
        if re.search(r"phpunit|jest|vitest|mocha|rspec|pytest|surefire|junit|\btest\b", al):
            return "test-run"
        return "runtime"
    if exe in SEARCH:
        return "search"
    if exe == "git":
        return "vcs"
    if exe in SCAFFOLD:
        return None
    return "other"


def read_fence(rd):
    v = []
    try:
        for ln in open(f"{rd}/cpustat_scope2.tsv"):
            f = ln.split()
            if len(f) >= 3 and f[1] == "usage_usec" and float(f[2]) >= 0:
                v.append((float(f[0]), float(f[2])))
    except OSError:
        return 0.0, 0.0
    if len(v) < 2:
        return 0.0, 0.0
    return (v[-1][1] - v[0][1]) / 1e6, v[-1][0] - v[0][0]


def analyze_dir(rd):
    argvmap, roots, ticks = {}, set(), []
    for ln in open(f"{rd}/cmdlog.tsv", errors="replace"):
        f = ln.rstrip("\n").split("\t", 2)
        if len(f) >= 3 and f[1].strip().isdigit():
            argvmap[int(f[1])] = f[2]
            roots.add(int(f[1]))
            try:
                ticks.append((float(f[0]), f[2]))
            except ValueError:
                pass
    alive_last = {}
    for ln in open(f"{rd}/pidcpu.tsv", errors="replace"):
        f = ln.rstrip("\n").split("\t")
        if len(f) >= 4 and f[1].strip().isdigit():
            roots.add(int(f[1]))
            try:
                alive_last[int(f[1])] = (int(f[2]) + int(f[3])) / CLK
            except ValueError:
                pass

    rec, seen = [], set()
    for ln in open(f"{rd}/taskstats.tsv", errors="replace"):
        f = ln.rstrip("\n").split("\t")
        if len(f) >= 10 and f[1] == "P":
            try:
                key = (f[2], f[9])                # (pid, btime): a task dies once
                if key in seen:
                    continue                      # duplicate row (dir replayed twice)
                seen.add(key)
                rec.append((int(f[2]), int(f[3]), f[5], (int(f[6]) + int(f[7])) / 1e6))
            except ValueError:
                pass
    parent = {p: pp for p, pp, _, _ in rec}
    comm_of = {p: c for p, pp, c, _ in rec}
    memo = {}

    def infence(p, d=0):
        if p in memo:
            return memo[p]
        if p in roots:
            memo[p] = True
            return True
        if d > 60 or p not in parent:
            memo[p] = False
            return False
        memo[p] = infence(parent[p], d + 1)
        return memo[p]

    # Front-end class from CHILDREN, not from argv (defect found 2026-08-18): `go test ./...`
    # is not one long-lived process — bash spawns thousands of ~500 ms `go` children, one per
    # package, that the 2 Hz cmdlog never sees (98% of `go` receipts, 539 core-s over 141
    # episodes). Falling back to comm alone made every one of them `build-drv`, and their
    # `vet` / `*.test` children were then owned by BUILD. A front-end that spawned a test
    # runner IS a test invocation, whatever its argv said or didn't say.
    kids = collections.defaultdict(list)
    for p, pp, comm, cpu in rec:
        kids[pp].append(comm)
    TEST_CHILD = ("vet", "test-run")
    kind_memo = {}

    def frontend_kind(p):
        """None if p is not a front-end; else its class, children-corrected."""
        if p in kind_memo:
            return kind_memo[p]
        src = argvmap.get(p) or comm_of.get(p)
        tg = tag_of(src) if src else None
        # payload binaries (jq, rg, shtest…) are tagged test-run for the PROCESS view but are
        # NOT drivers: they never spawn on the agent's behalf, `make check` invoked them. Letting
        # them own children pulled jq's fence from 90/9 to 61/38 against the P7 truth 92/0.
        exe = (src or "").split()[0].rsplit("/", 1)[-1] if src else ""
        if exe in PAYLOAD_BIN:
            tg = None
        if tg in OWNER_CLASSES:
            if tg == "build-drv":
                for c in kids.get(p, ()):
                    ct = tag_of(c)
                    if ct in TEST_CHILD or c.endswith(".test"):
                        tg = "test-run"
                        break
        else:
            tg = None
        kind_memo[p] = tg
        return tg

    def owner(p, d=0):
        if d > 60:
            return None
        k = frontend_kind(p)
        if k:
            return k
        return owner(parent[p], d + 1) if p in parent else None

    proc, own, receipts_in = collections.Counter(), collections.Counter(), 0.0
    leaf_cnt = collections.Counter()            # COUNT weighting, see LEAFCOUNT note above
    for p, pp, comm, cpu in rec:
        if not infence(p):
            continue
        receipts_in += cpu
        tg = tag_of(comm)
        proc[tg or "(scaffold)"] += cpu
        own[owner(p) or tg or "(scaffold)"] += cpu
        cls = COARSE.get(tg or "")
        if cls and p not in kids and not THREADISH.search(comm.strip()):
            leaf_cnt[cls] += 1                  # a leaf command: executed, spawned nothing

    dead = set(parent)
    alive = 0.0
    for p, v in alive_last.items():
        if p in dead:
            continue
        alive += v
        tg = tag_of(argvmap.get(p, ""))
        proc[tg or "(scaffold)"] += v
        own[tg or "(scaffold)"] += v

    # container bootstrap (apt/pip lineage in the first 300 s) — magnitude correction only
    boot_s = 0.0
    if ticks:
        t0 = ticks[0][0]
        boot_ts = [t for t, a in ticks if BOOT_RX.search(a) and t - t0 <= BOOT_CAP_S]
        boot_s = (max(boot_ts) - t0) if boot_ts else 0.0

    fence, wall = read_fence(rd)

    def shares(counter):
        cc = collections.Counter()
        for k, v in counter.items():
            c = COARSE.get(k)
            if c:
                cc[c] += v
        s = sum(cc.values())
        return ({k: 100 * v / s for k, v in cc.items()}, s) if s else ({}, 0.0)

    own_sh, own_cls = shares(own)
    proc_sh, proc_cls = shares(proc)

    def label(sh, cls_cs):
        # low-evidence gate: <50% of the fence classified, or <10 classified core-s
        # (an 11 core-s fence that is all swerex bootstrap + bash never verified anything)
        if not sh or cls_cs < 10.0 or (fence > 0 and cls_cs / fence < 0.5):
            return "?"
        o = sorted(sh, key=sh.get, reverse=True)
        if len(o) == 1 or sh[o[0]] - sh[o[1]] >= MARGIN:
            return o[0][0]          # B / T / S
        return "M"

    n_leaf = sum(leaf_cnt.values())
    leaf_sh = {k: 100 * v / n_leaf for k, v in leaf_cnt.items()} if n_leaf else {}

    def label_counts(sh, n):
        # Counting is far more fragile than summing: one lost receipt does not just subtract
        # its CPU, it can turn a driver into a "leaf" (its children's receipts are gone) and
        # so mis-file every command under it. A 95% coverage floor — much stricter than the
        # 50% the CPU views use — keeps the count column off any episode with receipt loss.
        cov = 100 * (receipts_in + alive) / max(fence, 1e-9)
        if not sh or n < 20 or cov < 95.0:      # too few commands, or incomplete receipts
            return "?"
        o = sorted(sh, key=sh.get, reverse=True)
        if len(o) == 1 or sh[o[0]] - sh[o[1]] >= MARGIN:
            return o[0][0]
        return "M"

    top = "  ".join(f"{k}={v:.1f}" for k, v in proc.most_common(6) if k != "(scaffold)")
    return dict(fence=round(fence, 1), wall=round(wall, 1), boot_s=round(boot_s, 1),
                coverage=round(100 * (receipts_in + alive) / max(fence, 1e-9), 1),
                classified_pct=round(100 * own_cls / max(fence, 1e-9), 1),
                own_B=round(own_sh.get("BUILD", 0)), own_T=round(own_sh.get("TEST", 0)),
                own_S=round(own_sh.get("SEARCH", 0)), own_label=label(own_sh, own_cls),
                proc_B=round(proc_sh.get("BUILD", 0)), proc_T=round(proc_sh.get("TEST", 0)),
                proc_S=round(proc_sh.get("SEARCH", 0)), proc_label=label(proc_sh, proc_cls),
                n_leaf=n_leaf, leaf_B=round(leaf_sh.get("BUILD", 0)),
                leaf_T=round(leaf_sh.get("TEST", 0)), leaf_S=round(leaf_sh.get("SEARCH", 0)),
                leaf_label=label_counts(leaf_sh, n_leaf),
                n_receipts=len(rec), top_procs=top)


COLS = ["instance", "language", "mech", "short", "fence", "live_ratio", "boot_s", "coverage",
        "classified_pct", "own_B", "own_T", "own_S", "own_label",
        "proc_B", "proc_T", "proc_S", "proc_label",
        "n_leaf", "leaf_B", "leaf_T", "leaf_S", "leaf_label",
        "flags", "n_receipts", "top_procs"]


def ledger_info():
    out = {}
    try:
        for r in csv.DictReader(open(f"{ML}/typing_ledger.tsv"), delimiter="\t"):
            out[r["instance"]] = r
    except OSError:
        pass
    return out


def inv_lang():
    out = {}
    p = f"{REPO}/local_agents/ML_multiling/sampling_frame/task_inventory.csv"
    try:
        for r in csv.DictReader(open(p)):
            out[r["instance_id"]] = (r["language"], r["mech_class"])
    except OSError:
        pass
    return out


def cmd_build(data):
    led, inv = ledger_info(), inv_lang()
    rows = []
    for rd in sorted(glob.glob(f"{data}/glm_replay_swe_*/run_1")):
        if not (os.path.exists(f"{rd}/DONE") and os.path.getsize(f"{rd}/taskstats.tsv") > 0
                if os.path.exists(f"{rd}/taskstats.tsv") else False):
            continue
        meta = {}
        mp = f"{rd}/metadata.json"
        if os.path.exists(mp):
            meta = (json.load(open(mp)).get("extra") or {})
        inst = meta.get("instance", "")
        short = os.path.basename(os.path.dirname(rd)).replace("glm_replay_swe_", "")
        a = analyze_dir(rd)
        lang, mech = inv.get(inst, ("?", "?"))
        lrow = led.get(inst, {})
        flags = lrow.get("flags", "")
        try:
            live = float(lrow.get("tool_cs_raw", "nan"))
            ratio = a["fence"] / live if live > 1 else float("nan")
        except (TypeError, ValueError):
            ratio = float("nan")
        a["live_ratio"] = round(ratio, 2) if ratio == ratio else ""
        if ratio == ratio and not (0.5 <= ratio <= 2.0):
            flags = (flags + "," if flags else "") + f"replay-invalid(ratio={ratio:.2f})"
            a["own_label"] = a["proc_label"] = a["leaf_label"] = "?"
        rows.append({**a, "instance": inst, "language": lang, "mech": mech,
                     "short": short, "flags": flags})
    out = f"{ML}/cpu_matrix.tsv"
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"wrote {out}: {len(rows)} episodes")
    return rows


def cmd_matrix(data):
    rows = list(csv.DictReader(open(f"{ML}/cpu_matrix.tsv"), delimiter="\t"))
    for view in ("own_label", "proc_label"):
        cells = collections.Counter((r["language"], r[view]) for r in rows if r["language"] != "?")
        langs = sorted({l for l, _ in cells})
        labs = ["B", "T", "S", "M", "?"]
        print(f"\n=== ⟨language × CPU-type⟩, view = {view} (n={len(rows)}) ===")
        print(f"{'':<12}" + "".join(f"{c:>6}" for c in labs))
        for l in langs:
            print(f"{l:<12}" + "".join(f"{cells.get((l, c), 0):>6}" for c in labs))


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "build"
    data = f"{ML}/data"
    if "--data" in sys.argv:
        data = sys.argv[sys.argv.index("--data") + 1]
    if what == "build":
        cmd_build(data)
    elif what == "matrix":
        cmd_matrix(data)
    else:
        sys.exit(__doc__)
