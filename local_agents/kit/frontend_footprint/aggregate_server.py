#!/usr/bin/env python3
"""aggregate_server.py — aggregation step of the Server front-end footprint study (contract v1.1).

Reads finished passes; never captures. Stdlib only: run it with the system python3. The SPEC
aggregation (aggregate.py, same directory) is imported, not forked: its metric list, long-CSV
value formatting, convergence rule (sampling_limited if a unique count grows > 2 % from 75 % to
100 % of the samples) and helpers are used as they are. Its V1/V2/V3 and August parts are
SPEC-only: V1-V3 validate the analyzer and the period, which the Server shares, so they are
pointed to, not re-run.

  python3 aggregate_server.py [--roots DIR [DIR ...]] [--run-name run_1] [--index-csv CSV]
                              [--out DIR] [--expect W [W ...]] [--spec-csv-from-git REF|none]

Inputs: for each workload of --index-csv with in_realistic_server_set = 1 (or --expect), the
pass <root>/<family>_<workload>/<run-name>/ under one of --roots (default: the DCPerf, JVMbench
and RealData frontend_footprint data areas), as written by local_agents/kit/dcperf/lbr_pass.sh:
DONE, summary.json (lbr_pass_gates.py: analyzer output + workload, capture, exact_counts,
gates_v4) and {objects,lines,edges}.tsv[.zst]. Only a dir named exactly <run-name> is read;
siblings such as run_1.smoke_nonroot_unmapped are defect evidence, listed in gates.csv, never
aggregated. The banked counter passes next to each data area (<root>/../<family>_<workload>/
run_*/metadata.json) give the reference capture length. SPEC's committed outputs are read with
`git show REF:spec26/frontend_footprint_x86/...`, never from a checkout.

Writes into --out:
  <workload>/summary.json                 copies of the aggregated passes' summary.json
  frontend_footprint_rows_long.csv        workload,family,subgroup,metric,value,analyzer_sha,period,capture_s
  gates.csv                               one row per expected workload: gates_v4 flattened, convergence, status
  gates_global.csv                        analyzer and contract identity; V1-V3 pointers to SPEC
  spec26_rows_long.csv                    byte copy of SPEC's long CSV at REF (unless REF = none)
  MANIFEST.md                             definitions, Server caveats with numbers, how to regenerate
Exit 2 if the passes carry more than one analyzer SHA (nothing is written then).
"""
import argparse
import collections
import csv
import datetime
import hashlib
import io
import os
import shutil
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import aggregate as A  # noqa: E402  (constants and functions only: no side effects at import)

REPO = A.REPO
ROOTS = [os.path.join(REPO, "local_agents", x, "data", "frontend_footprint") for x in ("DCPerf", "JVMbench", "RealData")]
INDEX = os.path.join(REPO, "local_agents/RealData/data/l3_study/workload_index.csv")
OUT = os.path.join(REPO, "local_agents/frontend_footprint_x86")
SPEC_REF = "origin/spec-x86"
SPEC_DIR = "spec26/frontend_footprint_x86"
SPEC_REPORT = "docs/reports/23_spec26_frontend_footprint_x86.md"
SRC_SHA256 = "298e417a3dc3dbd0591380ccc36f6986b6c3aeb2e83c4d5a582759bcbd2dce22"  # analyzer source of the SPEC run
FAMILY_ORDER = ["dcperf", "dacapo", "renaissance", "realdata"]
KINDS = ("file", "special", "anon", "kernel")
LONG_COLS = A.LONG_COLS + ["capture_s"]
PATH_ARGS = ("roots", "index_csv", "out")

GATE_DOCS = [
    ("workload", "workload name as in `workload_index.csv`"),
    ("family", "`workload_index.csv` family (dcperf / dacapo / renaissance / realdata); the pass dir is `<family>_<workload>`"),
    ("subgroup", "`workload_index.csv` subgroup"),
    ("status", "ok = DONE exists, `gates_v4.all_ok` is true, the event/period/filter match the contract and the analyzer "
               "source is SPEC's (only these reach the long CSV); gate_failed = summary.json present but any of those "
               "fails; incomplete = run dir without summary.json (pass running, or aborted before its gates); "
               "missing = no run dir"),
    ("why", "reasons for a status other than ok, `;`-separated (failed `gates_v4.*_ok` keys by name)"),
    ("in_long_csv", "1 if the workload's rows are in the long CSV"),
    ("pass_dir", "the pass directory read"),
    ("ignored_dirs", "sibling dirs not named exactly `--run-name` (e.g. a failed smoke kept as defect evidence); never read"),
    ("done", "1 if `DONE` exists (lbr_pass.sh writes it only when every gate passed)"),
    ("analyzer_sha", "`analyzer_sha` in summary.json (the analyzer commit)"),
    ("analyzer_src_ok", f"1 if `analyzer_src_sha256` = `{SRC_SHA256}` (the SPEC run's analyzer source)"),
    ("event", "sampling event, `capture.frontend_footprint.event`"),
    ("period", "sampling period, `capture.frontend_footprint.period`"),
    ("branch_filter", "LBR filter, `capture.frontend_footprint.branch_filter`"),
    ("contract_ok", f"1 if event = `{A.CONTRACT_EVENT}`, period = {A.CONTRACT_PERIOD} and filter = `{A.CONTRACT_FILTER}`"),
    ("capture_s", "CAPTURE_S of the pass: the steady-state window requested, s"),
    ("window_s", "measured window: `ts_end - ts_start` of the perf enable/disable acknowledgements, s"),
    ("capture_s_banked", "CAPTURE_S of the workload's banked counter passes (`<family>_<workload>/run_*/metadata.json`), `;`-separated if several"),
    ("capture_s_match", "1 if capture_s equals every banked value (the guide's comparability rule; reported, not gated)"),
    ("samples", "LBR samples (`diagnostics.samples`)"),
    ("lost_pct", "lost samples / (samples + lost), %"),
    ("lost_ok", "lost_pct < 1"),
    ("sample_coverage", "samples x period / exact `br_inst_retired.near_taken` (perf stat, same fence, nested window); 1 = no sample dropped"),
    ("coverage_ok", "abs(sample_coverage - 1) <= lbr_pass_gates.py `--cover-tol` (0.005 unless overridden; the value used is not banked)"),
    ("throttle_events", "THROTTLE records in `perf report --stats` (lbr_pass_gates.py sums both of its sections)"),
    ("throttle_ok", "0 THROTTLE records and the stats were read"),
    ("alive_ok", "the server fence existed for the whole window"),
    ("unmapped_pct", "LBR entries at a user address no mapping covers, % of entries"),
    ("discontinuity_rate", "share of candidate straight-line ranges skipped (not in one mapping, negative or > 4096 B)"),
    ("mapped_ok", "unmapped_pct < 1"),
    ("d4_first_fifth_cores", "D4: mean fence load over the first fifth of the window (10 s means of the 10 Hz cpu.stat), cores"),
    ("d4_last_fifth_cores", "D4: same, last fifth"),
    ("d4_drift_pct", "D4: 100 x abs(last - first) / max(first, last)"),
    ("d4_mean_cores", "D4: mean fence load over the window, cores"),
    ("d4_ok", "drift <= 25 % and mean load >= 0.10 cores"),
    ("d5_partition_core_s", "D5: measured-partition busy time over the window (/proc/stat), core-s"),
    ("d5_fence_core_s", "D5: fence CPU time over the window (cpu.stat), core-s"),
    ("d5_residual_pct", "D5: partition busy not explained by the fence, % of partition busy"),
    ("d5_ok", "residual <= 20 %"),
    ("witness_rows", "2 s whole-machine witness rows in the window"),
    ("witness_foreign_rows", "witness rows with a foreign task above 10 % CPU (root kernel threads not counted)"),
    ("witness_mean_foreign_cpu_pct", "mean foreign CPU over the witness rows, %"),
    ("witness_clean", "aggregate.py's rule recomputed: rows > 0, foreign rows <= 5 % of rows, mean foreign CPU <= 25 %"),
    ("witness_ok", "`gates_v4.witness_ok` (the same rule, from the pass)"),
    ("receipt_metric", "the workload's throughput receipt (receipt_compare.py)"),
    ("receipt_unit", "its unit"),
    ("receipt_new", "this pass's value"),
    ("receipt_banked_median", "median over the banked counter passes"),
    ("receipt_banked_n", "number of banked passes with a receipt"),
    ("receipt_ratio", "receipt_new / receipt_banked_median"),
    ("receipt_comparable", "receipt_compare.py verdict (rule in `gates_v4.receipt.rule`)"),
    ("receipt_basis", "`workload receipt`, or `fence-load proxy` for a batch without a receipt by design (video-4k)"),
    ("overrides", "gates accepted by a recorded human decision (`<run>/receipt_override.json`); the gate's own column stays false"),
    ("override_by", "who decided the override"),
    ("override_reason", "why, as recorded in the run directory"),
    ("receipt_ok", "receipt comparable (or, for the fence-load proxy, fence load in band)"),
    ("fence_cores_new", "mean fence load of this pass (whole cpu.stat file), cores"),
    ("fence_cores_banked_median", "same, median over the banked counter passes"),
    ("fence_cores_in_band", "fence load within the receipt band (never gates, except as the proxy)"),
    ("iso_proof_present", "1 if an ISO-PROOF line is recorded"),
    ("analyzer_ok", "analyzer exit 0 and no `error` key"),
    ("all_ok", "`gates_v4.all_ok`: every gate above"),
] + [(c, d) for m in A.UNIQUE for c, d in (
    (f"conv_growth_pct_{m}", f"100 x ({m} at 100 % of samples - at 75 %) / value at 100 %"),
    (f"conv_{m}", "sampling_limited if conv_growth_pct > 2, else converged"))] + [
    ("sampling_limited", "the unique metrics marked sampling_limited, `;`-separated"),
    ("instructions", "exact instructions, `perf stat` on the fence over the window"),
    ("cycles", "exact cycles, same"),
    ("ipc", "instructions / cycles"),
    ("processes_with_samples", "processes with at least one LBR sample"),
    ("top_process", "comm of the process with most samples"),
    ("top_process_share_pct", "its share of the samples, %"),
    ("kernel_footprint_pct", "100 x footprint_bytes_kernel / footprint_bytes"),
    ("kernel_branches_pct", "100 x unique_taken_branches_kernel / unique_taken_branches"),
    ("file_footprint_pct", "share of the footprint in file-backed code (kinds file + special: keyed by (path, inode) + offset), %"),
    ("anon_footprint_pct", "share of the footprint in anonymous code (JIT, unmapped; keyed by (pid, address)), %"),
    ("anon_branches_pct", "share of the unique taken branches in anonymous code, %"),
    ("anon_processes", "processes with anonymous code in the footprint"),
    ("objects_source", "top_objects (exact: the list holds every object hit) or tables (recomputed from "
                       "objects/lines/edges.tsv[.zst]); empty = neither available"),
]
GATE_COLS = [c for c, _ in GATE_DOCS]
GLOBAL_COLS = A.GLOBAL_COLS


def warn(msg):
    print(f"aggregate_server: WARNING {msg}", file=sys.stderr)


def pct_of(a, b):
    a, b = A.num(a), A.num(b)
    return 100.0 * a / b if a is not None and b else None


# ---- inputs ----------------------------------------------------------------------------------
def read_index(path):
    """-> ({workload: (family, subgroup)} for every Server row, [default expected workloads])"""
    info, expect = {}, []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if r.get("side") != "Server" and r.get("family") not in FAMILY_ORDER:
                continue
            if r["workload"] in info:
                warn(f"{path}: workload {r['workload']} listed twice; the first row is used")
                continue
            info[r["workload"]] = (r["family"], r.get("subgroup", ""))
            if r.get("in_realistic_server_set") == "1":
                expect.append(r["workload"])
    rank = lambda w: (FAMILY_ORDER.index(info[w][0]) if info[w][0] in FAMILY_ORDER else len(FAMILY_ORDER), w)
    return info, sorted(expect, key=rank)


def find_pass(roots, fam, wl, run_name):
    """-> (pass dir or None, [ignored sibling dirs], root the workload dir was found under)"""
    hits = [os.path.join(r, f"{fam}_{wl}") for r in roots if os.path.isdir(os.path.join(r, f"{fam}_{wl}"))]
    if not hits:
        return None, [], None
    if len(hits) > 1:
        warn(f"{fam}_{wl} exists under several roots: {hits}; the first is read")
    base = hits[0]
    ignored = sorted(n for n in os.listdir(base) if n != run_name and os.path.isdir(os.path.join(base, n)))
    d = os.path.join(base, run_name)
    return (d if os.path.isdir(d) else None), ignored, os.path.dirname(base)


def banked_capture(roots, fam, wl):
    """CAPTURE_S of the banked counter passes (<root>/../<fam>_<wl>/run_*/metadata.json)."""
    vals = set()
    for r in roots:
        b = os.path.join(os.path.dirname(r), f"{fam}_{wl}")
        if not os.path.isdir(b):
            continue
        for n in sorted(os.listdir(b)):
            if n.startswith("run_") and n[4:].isdigit():
                v = A.num(A.get(A.load_json(os.path.join(b, n, "metadata.json")) or {}, "extra", "capture_s"))
                if v is not None:
                    vals.add(int(v) if v.is_integer() else v)
    return sorted(vals)


def evaluate(wl, d, a):
    """Read one pass dir and judge whether it may be aggregated."""
    ep = {"dir": d, "done": False, "s": {}, "why": [], "status": "missing", "event": None, "period": None,
          "filter": None, "contract_ok": None, "src_ok": None}
    if not d:
        return ep
    ep["done"] = os.path.exists(os.path.join(d, "DONE"))
    s = A.load_json(os.path.join(d, "summary.json"))
    if s is None:
        ep.update(status="incomplete", why=["no summary.json (pass running, or aborted before its gates)"])
        return ep
    ep["s"] = s
    if s.get("workload") not in (None, wl):
        warn(f"{d}: summary.json says workload {s.get('workload')!r}; using {wl!r}")
    g = s.get("gates_v4") if isinstance(s.get("gates_v4"), dict) else {}
    ff = A.get(s, "capture", "frontend_footprint") or {}
    p = A.num(ff.get("period", A.get(s, "meta", "period")))
    ep.update(event=ff.get("event"), period=int(p) if p is not None else None, filter=ff.get("branch_filter"))
    ep["contract_ok"] = ep["event"] == a.event and ep["period"] == a.period and ep["filter"] == A.CONTRACT_FILTER
    ep["src_ok"] = s.get("analyzer_src_sha256") == a.analyzer_src
    why = []
    if not ep["done"]:
        why.append("no DONE")
    if "error" in s:
        why.append("analyzer error")
    if "all_ok" not in g:
        why.append("no gates_v4.all_ok")
    else:
        # a gate named in gates_v4.overrides was accepted by a recorded human decision
        # (<run>/receipt_override.json): not a failure, but carried into gates.csv and the MANIFEST
        ov = set(g.get("overrides") or [])
        failed = [k for k, v in g.items() if k.endswith("_ok") and k != "all_ok" and v is not True and k[:-3] not in ov]
        why += failed
        if g["all_ok"] is not True and not failed:
            why.append("all_ok not true")
    if not ep["contract_ok"]:
        why.append(f"contract mismatch (event {ep['event']}, period {ep['period']}, filter {ep['filter']})")
    if not ep["src_ok"]:
        why.append(f"analyzer source {str(s.get('analyzer_src_sha256'))[:12]} is not SPEC's")
    ep.update(status="gate_failed" if why else "ok", why=why, overrides=sorted(g.get("overrides") or []),
              override_reason=(g.get("receipt_override") or {}).get("reason"),
              override_by=(g.get("receipt_override") or {}).get("decided_by"))
    return ep


def table_iter(d, name):
    """Stream the rows of an analyzer table (plain or .zst), header skipped; None if absent.
    Streams, unlike aggregate.table_rows: a JVM server's edges table can hold millions of rows."""
    p = os.path.join(d, name)
    if os.path.exists(p):
        fh, proc = open(p), None
    elif os.path.exists(p + ".zst"):
        proc = subprocess.Popen(["zstd", "-dcq", p + ".zst"], stdout=subprocess.PIPE, text=True)
        fh = proc.stdout
    else:
        return None

    def rows():
        with fh:
            next(fh, None)
            for ln in fh:
                yield ln.rstrip("\n").split("\t")
        if proc is not None and proc.wait() != 0:
            raise RuntimeError(f"zstd failed on {p}.zst")
    return rows()


def object_split(s, d):
    """Footprint bytes and unique taken branches per object kind (file / special / anon / kernel) and
    the processes with anonymous code. Exact from top_objects_by_footprint when it lists every object
    hit (< aggregate.TOP_N entries), else recomputed from the tables; None if neither is possible."""
    b, br, pids = dict.fromkeys(KINDS, 0), dict.fromkeys(KINDS, 0), set()
    objs = s.get("top_objects_by_footprint")
    if isinstance(objs, list) and len(objs) < A.TOP_N:
        for o in objs:
            k = o.get("kind", "?")
            b[k] = b.get(k, 0) + int(A.num(o.get("footprint_bytes")) or 0)
            br[k] = br.get(k, 0) + int(A.num(o.get("unique_taken_branches")) or 0)
            if k == "anon" and A.num(o.get("footprint_bytes")):
                pids.add(o.get("pid"))
        src = "top_objects"
    else:
        names = ("objects.tsv", "lines.tsv", "edges.tsv")
        if not d or not all(os.path.exists(os.path.join(d, x)) or os.path.exists(os.path.join(d, x + ".zst"))
                            for x in names):
            return None
        kind, pid = {}, {}
        for r in table_iter(d, "objects.tsv"):
            if len(r) >= 5:
                kind[r[0]] = r[1]
                pid[r[0]] = r[4]
        anon_objs = set()
        for r in table_iter(d, "lines.tsv"):
            if r and r[0]:
                k = kind.get(r[0], "?")
                b[k] = b.get(k, 0) + 64
                if k == "anon":
                    anon_objs.add(r[0])
        seen = set()
        for r in table_iter(d, "edges.tsv"):
            if len(r) > 4 and r[4] in A.NEAR and (r[0], r[1]) not in seen:
                seen.add((r[0], r[1]))
                k = kind.get(r[0], "?")
                br[k] = br.get(k, 0) + 1
        pids = {pid[o] for o in anon_objs}
        src = "tables"
    fb, ub = A.num(s.get("footprint_bytes")), A.num(s.get("unique_taken_branches"))
    if fb is not None and sum(b.values()) != fb:
        warn(f"{s.get('workload')}: object split sums to {sum(b.values())} B, footprint_bytes is {fb:g} ({src})")
    if ub is not None and sum(br.values()) != ub:
        warn(f"{s.get('workload')}: object split sums to {sum(br.values())} branches, unique_taken_branches is {ub:g} ({src})")
    return {"bytes": b, "branches": br, "anon_processes": len(pids), "source": src}


def long_values(s):
    """(metric, value) rows of one summary: the metric set, order and formatting of aggregate.py's
    long CSV (the same lines as its main(), which builds them inline)."""
    bt = A.get(s, "unique_taken_branches_by_type", "all") or {}
    vals = {m: s.get(m) for m in A.UNIQUE + A.WAVG}
    vals.update({m: s[m] for m in A.COMPANIONS if m in s})
    vals.update({f"unique_taken_branches_{t}": bt.get(t, 0) for t in A.TYPES})
    for t in sorted(set(bt) - set(A.TYPES)):
        vals[f"unique_taken_branches_{t}"] = bt[t]
    out = []
    for m in [m for m in A.METRICS if m in vals] + sorted(set(vals) - set(A.METRICS)):
        v = vals.get(m)
        v = v if isinstance(v, (int, float)) and not isinstance(v, bool) else A.num(v)
        out.append((m, A.fmt(v)))
    return out


# ---- SPEC reference, from git ----------------------------------------------------------------
def git(*args):
    try:
        r = subprocess.run(["git", "-C", REPO, *args], capture_output=True)
    except OSError:
        return None
    return r.stdout if r.returncode == 0 else None


def spec_reference(ref):
    sp = {"ref": ref, "commit": None, "csv": None, "rows": [], "gates": [], "global": [], "report": False}
    if not ref or ref.lower() == "none":
        return sp
    c = git("rev-parse", "--verify", "--quiet", ref + "^{commit}")
    if not c:
        warn(f"git ref {ref!r} not found: no spec26_rows_long.csv, no SPEC comparison")
        return sp
    sp["commit"] = c.decode().strip()
    rd = lambda name: git("show", f"{sp['commit']}:{SPEC_DIR}/{name}")
    sp["csv"] = rd("frontend_footprint_rows_long.csv")
    if sp["csv"] is None:
        warn(f"{ref}:{SPEC_DIR}/frontend_footprint_rows_long.csv not found")
    parse = lambda x: list(csv.DictReader(io.StringIO(x.decode()))) if x else []
    sp["rows"], sp["gates"], sp["global"] = parse(sp["csv"]), parse(rd("gates.csv")), parse(rd("gates_global.csv"))
    sp["report"] = git("cat-file", "-e", f"{sp['commit']}:{SPEC_REPORT}") is not None
    return sp


def spec_global(sp, gate, name, metric):
    return next((r["value"] for r in sp["global"] if (r["gate"], r["name"], r["metric"]) == (gate, name, metric)), None)


def spec_share(sp, part, whole):
    by = collections.defaultdict(dict)
    for r in sp["rows"]:
        by[r["workload"]][r["metric"]] = r["value"]
    return [v for v in (pct_of(m.get(part), m.get(whole)) for m in by.values()) if v is not None]


# ---- MANIFEST --------------------------------------------------------------------------------
def mr(vals, unit="", p=2):
    """median and range of the non-None values, with n."""
    vals = [v for v in vals if v is not None]
    if not vals:
        return "n/a (n=0)"
    return (f"median {statistics.median(vals):.{p}f}{unit}, range {min(vals):.{p}f}-{max(vals):.{p}f}{unit} "
            f"(n={len(vals)})")


def grouped(pairs):
    """[(value, workload)] -> 'v1 s: w, w; v2 s: w' (values in descending order)."""
    g = collections.defaultdict(list)
    for v, w in pairs:
        g[v].append(w)
    return "; ".join(f"{A.fmt(v)} s: {', '.join(ws)}" for v, ws in sorted(g.items(), key=lambda x: -(A.num(x[0]) or 0)))


def manifest(M):
    a, sp = M["args"], M["spec"]
    ok = [r for r in M["gates"] if r["status"] == "ok"]
    n_ok, L = len(ok), []
    P = L.append
    spec_at = f"`{sp['ref']}` @ `{sp['commit'][:12]}`" if sp["commit"] else "unavailable (no git ref)"
    spec_file = lambda f: f"`{SPEC_DIR}/{f}` on {spec_at}"
    P("# Front-end footprint, x86, Server set — MANIFEST\n")
    P(f"Generated {M['generated']} by `local_agents/kit/frontend_footprint/aggregate_server.py` from "
      + ", ".join(f"`{A.tilde(r)}`" for r in a.roots) + f" (pass dirs `<family>_<workload>/{a.run_name}`). "
      "Do not edit by hand: regenerate (last section).\n")
    P("Three numbers per workload, for Rahul's front-end question: instruction footprint, unique taken "
      "branches, and the weighted average number of targets per taken branch, for the realistic Server set. "
      "The method is `docs/handoff/execution/frontend_footprint_method.md` (the contract), the capture "
      "`docs/handoff/execution/x86_server_footprint.md`. The analyzer, the metric definitions and the long-CSV "
      f"schema are SPEC's ({spec_file('MANIFEST.md')}; report `{SPEC_REPORT}` there).\n")

    P("## Population\n")
    P(f"* Expected: {len(M['gates'])} workloads ("
      + ("`--expect`" if a.expect else f"`in_realistic_server_set = 1` in `{A.tilde(a.index_csv)}`") + ").")
    byf = collections.Counter(r["family"] for r in ok)
    P(f"* Aggregated (status ok): {n_ok}. By family: "
      + (", ".join(f"{f} {byf[f]}" for f in sorted(byf, key=lambda f: (FAMILY_ORDER + [f]).index(f))) or "none") + ".")
    for st in ("gate_failed", "incomplete", "missing"):
        rs = [r for r in M["gates"] if r["status"] == st]
        if rs:
            P(f"* {st}: {len(rs)} — " + ", ".join(r["workload"] + (f" ({r['why']})" if r["why"] else "") for r in rs) + ".")
    ign = [(r["workload"], r["ignored_dirs"]) for r in M["gates"] if r["ignored_dirs"]]
    P("* Sibling dirs not named `" + a.run_name + "` (never read): "
      + ("; ".join(f"{w}: {d}" for w, d in ign) if ign else "none") + ".\n")

    P("## Contract and analyzer\n")
    P("| Parameter | Value |\n|---|---|")
    P(f"| Contract | {A.CONTRACT_VERSION} (2026-11-03) |")
    seen = lambda k: ", ".join(f"`{x}`" for x in sorted(M["seen"][k], key=str)) or "n/a"
    P(f"| Event | `{A.CONTRACT_EVENT}` (PEBS; user + kernel). Seen: {seen('event')} |")
    P(f"| Period | `-c {A.CONTRACT_PERIOD}`. Seen: {seen('period')} |")
    P(f"| Branch filter | `-j {A.CONTRACT_FILTER}`. Seen: {seen('filter')} |")
    P("| Scope | the server's fence cgroup, `perf record -a -C <measured> --cgroup=<fence>`; client outside the "
      f"fence as in the counter passes; measured cores {seen('cpus')} |")
    P(f"| Window | steady state, after the liveness check, for CAPTURE_S s (caveat 1). Seen: {seen('capture_s')} s |")
    P(f"| Analyzer SHA | `{M['sha'] or 'none (no data)'}` (one SHA across every pass with a summary; checked). "
      f"SPEC's: `{M['spec_sha'] or 'n/a'}` |")
    P(f"| Analyzer source sha256 | required `{a.analyzer_src}` (SPEC's). Seen: {seen('src')} |")
    P(f"| perf | {seen('perf')} |")
    P(f"| JDK on PATH | {seen('java')} |\n")

    P("## Validation gates V1-V3: SPEC's, not re-run\n")
    P("V1 (synthetic truth) and V2 (exact Intel PT cross-check) validate the analyzer; V3 (period 5003 vs "
      "20011) validates the period. The Server runs the same analyzer source (sha256 checked per pass, "
      "`analyzer_src_ok`) at the same period, so their results carry over unchanged. They are not copied here: "
      f"see {spec_file('gates_global.csv')}, the lower-bound section of {spec_file('MANIFEST.md')}, and report "
      f"`{SPEC_REPORT}` on the same commit" + ("" if sp["report"] or not sp["commit"] else " (WARNING: not found there)")
      + ". V4 (capture hygiene) is per pass: `gates.csv`.\n")

    P("## Caveats (Server-specific; numbers from the aggregated passes)\n")
    P("Every unique count is a sampled LOWER BOUND, and the literal `wavg_targets_*` too (its T_b is a unique "
      "count); `weff_targets_*` and `wavg_targets_ge1pct_*` are frequency-weighted. Same sampling and analyzer "
      "as SPEC, so SPEC's V2 measurement of that bias applies (see above). In addition:\n")
    caps = [(r["capture_s"], r["workload"]) for r in ok]
    banked = [(r["capture_s_banked"], r["workload"]) for r in M["gates"] if r["capture_s_banked"]]
    sw = [A.num(r.get("wall_s")) for r in sp["gates"] if r.get("status") == "ok"]
    c = M["conv"]
    P("1. **The window is a steady state, not a whole run.** Each pass samples the server for CAPTURE_S "
      "seconds after the liveness check (the same window and length as the workload's banked counter "
      "passes), not from start to exit. Aggregated passes: "
      + (grouped(caps) if caps else "none yet") + "; measured window "
      + mr([r["window_s"] for r in ok], " s", 1) + ". Capture length equal to the banked counter passes' on "
      f"{sum(1 for r in ok if r['capture_s_match'])} of the {sum(1 for r in ok if r['capture_s_match'] is not None)} "
      "aggregated passes with banked passes. Banked CAPTURE_S of the expected set: "
      + (grouped(banked) or "n/a") + ". SPEC's numbers cover whole runs of "
      + (mr(sw, " s", 0) if sw else "n/a") + f" ({spec_file('gates.csv')}, `wall_s`). Unique counts grow "
      "with the window: over the last quarter of the samples, `footprint_bytes` grew "
      f"{c['footprint_bytes']['desc']} and `unique_taken_branches` {c['unique_taken_branches']['desc']} "
      f"(sampling_limited on {c['footprint_bytes']['n_lim']} and {c['unique_taken_branches']['n_lim']} of "
      f"{c['footprint_bytes']['n']}). So Server and SPEC footprints and unique-branch counts are not comparable "
      "in absolute terms unless it is said that one is a fixed steady-state window and the other a whole run. "
      "The literal `wavg_targets_*` also accumulates (T_b); `weff_targets_*` and `wavg_targets_ge1pct_*` are "
      "averages over executions, not counts." + sample_matched_note(a.out))
    multi = sorted((r for r in ok if (r["processes_with_samples"] or 0) > 1), key=lambda r: -r["processes_with_samples"])
    P("2. **Several processes in one fence: file-backed code is canonicalised by (path, inode).** A binary or "
      "library that runs in many processes (video-4k's `ffmpeg` processes, a JVM's helper processes) counts "
      "once: its key is (path, inode) + file offset, not the virtual address. Processes with samples: "
      + (", ".join(f"{r['workload']} {r['processes_with_samples']} (top: {r['top_process']} "
                   f"{A.f3(r['top_process_share_pct'], 1)} % of samples; " + M["comms"][r["workload"]] + ")"
                   for r in multi) if multi else "every aggregated pass has one process" if ok else "n/a (no aggregated pass)")
      + (f"; one process: {', '.join(r['workload'] for r in ok if r['processes_with_samples'] == 1)}"
         if multi and any(r["processes_with_samples"] == 1 for r in ok) else "")
      + ". Share of the footprint in file-backed code: " + mr([r["file_footprint_pct"] for r in ok], " %", 1) + ".")
    anon = sorted((r for r in ok if r["anon_footprint_pct"] is not None), key=lambda r: -r["anon_footprint_pct"])
    P("3. **JIT code is keyed per process.** Anonymous executable memory (the JVM's JIT code cache, and any "
      "user address no mapping covers) is keyed (pid, address) and never merged across processes; each exec "
      "starts a new key space. Within a process the key is the address, so code the JIT recompiles or moves "
      "counts again at each new address, and different code later placed at a freed address counts once: "
      "neither is visible from LBR addresses. Share of the footprint in anonymous code: "
      + (", ".join(f"{r['workload']} {A.f3(r['anon_footprint_pct'], 1)} % ({A.f3(r['anon_branches_pct'], 1)} % "
                   f"of the branches, {r['anon_processes']} process(es))" for r in anon) or "n/a")
      + ". Unmapped user entries, also keyed as anonymous, are bounded by gate `mapped_ok` (< 1 % of entries): "
      + mr([r["unmapped_pct"] for r in ok], " %", 3) + ".")
    kf = [r["kernel_footprint_pct"] for r in ok]
    kb = [r["kernel_branches_pct"] for r in ok]
    P("4. **Kernel share.** Kernel share of the footprint, Server: " + mr(kf, " %", 1) + "; SPEC: "
      + mr(spec_share(sp, "footprint_bytes_kernel", "footprint_bytes"), " %", 1)
      + ". Of the unique taken branches, Server: " + mr(kb, " %", 1) + "; SPEC: "
      + mr(spec_share(sp, "unique_taken_branches_kernel", "unique_taken_branches"), " %", 1)
      + " (`spec26_rows_long.csv`). Only kernel code run while a fence task is current is sampled (`--cgroup` "
      "filters on the running task): its system calls, page faults, and interrupts that land on it. Kernel "
      "threads (kworker, ksoftirqd, ...) belong to no fence and are not sampled, nor is work done on the "
      "house cores (the client's side of the network stack). Measured-partition busy time not explained by "
      "the fence (D5 residual): " + mr([r["d5_residual_pct"] for r in ok], " %", 1) + ".")
    proxy = [r["workload"] for r in M["gates"] if r["receipt_basis"] and r["receipt_basis"] != "workload receipt"]
    P("5. **Receipt basis.** The workload served as in the banked counter passes (`receipt_ok`); "
      + (f"for {', '.join(proxy)} the evidence is the fence load (a batch without a throughput receipt by design)."
         if proxy else "every pass with a summary has a workload receipt." if any(r["receipt_basis"] for r in M["gates"])
         else "no pass with a summary yet.")
      + " Receipt ratio new / banked median: " + mr([r["receipt_ratio"] for r in ok], "", 3) + "."
      + "".join(f" **{r['workload']}: receipt gate failed (ratio {A.fmt(r['receipt_ratio'])}) and was accepted by a "
                f"recorded decision of {r['override_by']}** (`receipt_override.json` in its run dir): {r['override_reason']}"
                for r in M["gates"] if r.get("overrides"))
      + "\n")
    P(f"Convergence (the SPEC rule): each unique count is recomputed at 75 % and 100 % of the samples; growth "
      f"over the last quarter above {a.conv_threshold:g} % marks it `sampling_limited`. Over the {n_ok} "
      "aggregated passes:\n")
    for m in A.UNIQUE:
        P(f"* `{m}`: sampling_limited on {c[m]['n_lim']} of {c[m]['n']}; growth {c[m]['desc']}.")
    P("")
    if ok:
        P("Per aggregated pass:\n")
        P("| Workload | Family | CAPTURE_S | window s | footprint KB | kernel % | file-backed % | anonymous % | "
          "processes | top process | unmapped % | footprint growth, last quarter |")
        P("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r in ok:
            P(f"| {r['workload']} | {r['family']} | {A.fmt(r['capture_s'])} | {A.f3(r['window_s'], 1)} | "
              f"{A.f3((A.num(r['_s'].get('footprint_bytes')) or 0) / 1000, 1)} | {A.f3(r['kernel_footprint_pct'], 1)} | "
              f"{A.f3(r['file_footprint_pct'], 1)} | {A.f3(r['anon_footprint_pct'], 1)} | "
              f"{A.fmt(r['processes_with_samples'])} | {r['top_process'] or 'n/a'} | {A.f3(r['unmapped_pct'], 3)} | "
              f"{A.pct(r['conv_growth_pct_footprint_bytes'], 2)} |")
        P("")

    P("## Files\n")
    P("| File | What |\n|---|---|")
    P("| `<workload>/summary.json` | the pass's summary.json, copied (aggregated passes only): analyzer output plus "
      "`workload`, `capture`, `exact_counts`, `gates_v4` (lbr_pass_gates.py) |")
    P("| `frontend_footprint_rows_long.csv` | one row per (workload, metric); aggregated passes only |")
    P("| `gates.csv` | one row per expected workload: gates_v4 flattened, convergence, composition, status |")
    P("| `gates_global.csv` | analyzer and contract identity; pointers to SPEC's V1-V3 |")
    P("| `spec26_rows_long.csv` | " + (f"byte copy of `{SPEC_DIR}/frontend_footprint_rows_long.csv` at `{sp['ref']}` = "
                                       f"commit `{sp['commit']}` (sha256 `{M['spec_csv_sha256']}`), so the "
                                       "combined figure regenerates on this branch |"
                                       if M["spec_csv_sha256"] else "not written (no git ref; `--spec-csv-from-git none`?) |"))
    if os.path.exists(os.path.join(a.out, "sample_matched.csv")):
        P("| `sample_matched.csv` | each pass's footprint and unique taken branches over its first N samples, N = SPEC's "
          "median and maximum samples per run (`sample_matched.py`, from the tables' `first_seen`; not written here) |")
    if os.path.isdir(os.path.join(a.out, "plots")):
        P("| `plots/` | violins from `plot_frontend_footprint.py`: `server_by_family/` (`--group family`), "
          "`spec_vs_server/` (`--group side`, SPEC + Server); on log panels the diamond is the geometric mean (not written here) |")
    P("")

    P("## `frontend_footprint_rows_long.csv`\n")
    P("Columns: `" + ",".join(LONG_COLS) + "`: SPEC's schema plus `capture_s` (the pass's window, s; the "
      "plotter ignores extra columns). `family`/`subgroup` as in `workload_index.csv`. The metric names, "
      "their order, and the value formatting are SPEC's (aggregate.py), so one plotting script reads SPEC, "
      "Server and Agentic. An empty `value` = undefined (no branch of that kind was sampled). Bytes are B; "
      "KB in the text and plots = 1000 B.\n")
    P("| Metric | Definition |\n|---|---|")
    for m, doc in A.METRIC_DOCS:
        P(f"| `{m}` | {doc} |")
    P("\nCanonical addresses: file-backed code is keyed by (path, inode) + file offset, so a shared library "
      "counts once across processes; kernel by address; anonymous/JIT code by (pid, address).\n")

    P("## `gates.csv`\n")
    P("Booleans are 1/0; empty = not available. Gate thresholds are lbr_pass_gates.py's.\n")
    P("| Column | Meaning |\n|---|---|")
    done = set()
    for col, doc in GATE_DOCS:
        for pre, pat, d in (("conv_growth_pct_", "conv_growth_pct_<m>", "100 x (m at 100 % of the samples - m at 75 %) / m at 100 %"),
                            ("conv_", "conv_<m>", f"sampling_limited if conv_growth_pct_<m> > {a.conv_threshold:g}, else converged")):
            if col.startswith(pre):
                if pat not in done:
                    done.add(pat)
                    P(f"| `{pat}` | {d}; m in " + ", ".join(f"`{x}`" for x in A.UNIQUE) + " |")
                break
        else:
            P(f"| `{col}` | {doc} |")
    P("\n## `gates_global.csv`\n")
    P("Columns: `" + ",".join(GLOBAL_COLS) + "`. Gates: `analyzer` (one SHA across the passes; source sha256 = "
      "SPEC's; SPEC's own SHA and source, read from its gates_global.csv), `contract` (event, period, filter "
      "seen), `V1`/`V2`/`V3` (NOT_RERUN: a pointer to SPEC's rows), `reference` (the commit and sha256 of "
      "`spec26_rows_long.csv`).\n")

    P("## Regenerate\n")
    P("```bash")
    P(f"python3 local_agents/kit/frontend_footprint/aggregate_server.py {M['cmdline']}".rstrip())
    out = A.tilde(a.out)
    P("~/miniforge3/envs/infersuite-full/bin/python3 local_agents/kit/frontend_footprint/plot_frontend_footprint.py \\")
    P(f"    {out}/spec26_rows_long.csv {out}/frontend_footprint_rows_long.csv [AGENTIC_CSV] \\")
    P(f"    --group side --out {out}/plots")
    P("```")
    return "\n".join(L) + "\n"


# ---- main ------------------------------------------------------------------------------------
def sample_matched_note(out):
    """One sentence from sample_matched.csv (if present): the gap at SPEC's own sample counts."""
    f = os.path.join(out, "sample_matched.csv")
    if not os.path.exists(f):
        return ""
    rows = [r for r in csv.DictReader(ln for ln in open(f) if not ln.startswith("#"))]
    if not rows:
        return ""
    med = lambda k: statistics.median(float(r[k]) for r in rows)
    n = rows[0]["N_spec_median"]
    return (f" Sample-matched (`sample_matched.csv`, n={len(rows)}): over each pass's first {int(n):,} samples, SPEC's "
            f"median samples per run, the Server medians are footprint {med('footprint_bytes_at_spec_median') / 1e3:,.0f} KB "
            f"and unique taken branches {med('unique_taken_branches_at_spec_median'):,.0f}, against "
            f"{med('footprint_bytes') / 1e3:,.0f} KB and {med('unique_taken_branches'):,.0f} over the whole window.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--roots", nargs="+", default=ROOTS, help="data areas holding <family>_<workload>/<run-name>")
    ap.add_argument("--run-name", default="run_1", help="the only pass dir name read")
    ap.add_argument("--index-csv", default=INDEX)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--expect", nargs="+", help="expected workloads (Server rows of --index-csv; space or comma "
                    "separated); default: in_realistic_server_set = 1")
    ap.add_argument("--spec-csv-from-git", default=SPEC_REF, metavar="REF",
                    help="git ref holding SPEC's outputs; 'none' skips the copy and the SPEC comparisons")
    ap.add_argument("--analyzer-src", default=SRC_SHA256, help="required analyzer_src_sha256 (SPEC's)")
    ap.add_argument("--event", default=A.CONTRACT_EVENT)
    ap.add_argument("--period", type=int, default=A.CONTRACT_PERIOD)
    ap.add_argument("--conv-threshold", type=float, default=2.0, help="sampling_limited above this %% growth")
    a = ap.parse_args()
    a.roots = [os.path.abspath(os.path.expanduser(r)) for r in a.roots]
    a.index_csv, a.out = (os.path.abspath(os.path.expanduser(p)) for p in (a.index_csv, a.out))

    info, default_expect = read_index(a.index_csv)
    expect = list(dict.fromkeys(w for x in a.expect for w in x.split(",") if w)) if a.expect else default_expect
    unknown = [w for w in expect if w not in info]
    if unknown:
        print(f"aggregate_server: ERROR not Server workloads of {a.index_csv}: {', '.join(unknown)}", file=sys.stderr)
        return 1
    for r in a.roots:
        if not os.path.isdir(r):
            warn(f"root {r} does not exist (yet)")

    E = {}
    for w in expect:
        fam, sub = info[w]
        d, ignored, _ = find_pass(a.roots, fam, w, a.run_name)
        ep = evaluate(w, d, a)
        ep.update(family=fam, subgroup=sub, ignored=ignored, banked=banked_capture(a.roots, fam, w))
        E[w] = ep

    shas = collections.defaultdict(list)
    for w, ep in E.items():
        if ep["s"]:
            shas[ep["s"].get("analyzer_sha")].append(w)
    if len(shas) > 1:
        print("aggregate_server: ERROR the passes carry more than one analyzer SHA:", file=sys.stderr)
        for k, v in shas.items():
            print(f"  {k!r}: {', '.join(v)}", file=sys.stderr)
        print("aggregate_server: nothing written; re-analyze with one analyzer commit", file=sys.stderr)
        return 2
    sha = next(iter(shas), None)
    if shas and sha in ("uncommitted", "test", "", None):
        warn(f"analyzer_sha is {sha!r}, not a commit")

    sp = spec_reference(a.spec_csv_from_git)
    gates, long_rows, comms = [], [], {}
    seen = collections.defaultdict(set)
    for w, ep in E.items():
        s, st = ep["s"], ep["status"]
        g = s.get("gates_v4") if isinstance(s.get("gates_v4"), dict) else {}
        cap = s.get("capture") or {}
        ff = cap.get("frontend_footprint") or {}
        rc = g.get("receipt") or {}
        wit = g.get("witness")
        r = {c: None for c in GATE_COLS}
        cs = A.num(cap.get("capture_s", ff.get("capture_s")))
        cs = int(cs) if cs is not None and cs.is_integer() else cs
        r.update(workload=w, family=ep["family"], subgroup=ep["subgroup"], status=st, why="; ".join(ep["why"]),
                 in_long_csv=st == "ok", pass_dir=A.tilde(ep["dir"]) if ep["dir"] else "",
                 ignored_dirs=";".join(ep["ignored"]), done=ep["done"] if ep["dir"] else None,
                 capture_s=cs, capture_s_banked=";".join(A.fmt(v) for v in ep["banked"]),
                 capture_s_match=(all(v == cs for v in ep["banked"]) if ep["banked"] and cs is not None else None),
                 _s=s)
        if s:
            ex = s.get("exact_counts") or {}
            d4, d5 = g.get("d4") or {}, g.get("d5") or {}
            procs = s.get("top_processes") or []
            r.update(analyzer_sha=s.get("analyzer_sha"), analyzer_src_ok=ep["src_ok"], event=ep["event"],
                     period=ep["period"], branch_filter=ep["filter"], contract_ok=ep["contract_ok"],
                     window_s=A.num(ff.get("window_s")), samples=A.get(s, "diagnostics", "samples"),
                     lost_pct=A.num(g.get("lost_pct")), lost_ok=g.get("lost_ok"),
                     sample_coverage=A.num(g.get("sample_coverage")), coverage_ok=g.get("coverage_ok"),
                     throttle_events=g.get("throttle_events"), throttle_ok=g.get("throttle_ok"),
                     alive_ok=g.get("alive_ok"), unmapped_pct=A.num(g.get("unmapped_pct")),
                     discontinuity_rate=A.num(g.get("discontinuity_rate")), mapped_ok=g.get("mapped_ok"),
                     d4_first_fifth_cores=A.num(d4.get("first_fifth_cores")),
                     d4_last_fifth_cores=A.num(d4.get("last_fifth_cores")),
                     d4_drift_pct=A.num(d4.get("drift_pct")), d4_mean_cores=A.num(d4.get("mean_cores")),
                     d4_ok=g.get("d4_ok"), d5_partition_core_s=A.num(d5.get("partition_core_s")),
                     d5_fence_core_s=A.num(d5.get("fence_core_s")), d5_residual_pct=A.num(d5.get("residual_pct")),
                     d5_ok=g.get("d5_ok"), witness_rows=A.get(wit, "witness_rows"),
                     witness_foreign_rows=A.get(wit, "rows_with_foreign_task"),
                     witness_mean_foreign_cpu_pct=A.get(wit, "mean_foreign_cpu_pct"),
                     witness_clean=A.witness_clean(wit), witness_ok=g.get("witness_ok"),
                     receipt_metric=rc.get("metric"), receipt_unit=rc.get("unit"), receipt_new=A.num(rc.get("new")),
                     receipt_banked_median=A.num(rc.get("banked_median")), receipt_banked_n=rc.get("banked_n"),
                     receipt_ratio=A.num(rc.get("ratio")), receipt_comparable=rc.get("comparable"),
                     receipt_basis=rc.get("basis"), receipt_ok=g.get("receipt_ok"),
                     overrides=";".join(ep.get("overrides") or []), override_by=ep.get("override_by"),
                     override_reason=ep.get("override_reason"),
                     fence_cores_new=A.num(rc.get("fence_cores_new")),
                     fence_cores_banked_median=A.num(rc.get("fence_cores_banked_median")),
                     fence_cores_in_band=rc.get("fence_cores_in_band"),
                     iso_proof_present=bool(g.get("iso_proof") or ff.get("iso_proof")),
                     analyzer_ok=g.get("analyzer_ok"), all_ok=g.get("all_ok"),
                     instructions=A.num(ex.get("instructions")), cycles=A.num(ex.get("cycles")),
                     processes_with_samples=s.get("processes_with_samples"),
                     top_process=procs[0].get("comm") if procs else None,
                     top_process_share_pct=100.0 * A.num(procs[0].get("share")) if procs and A.num(procs[0].get("share")) is not None else None,
                     kernel_footprint_pct=pct_of(s.get("footprint_bytes_kernel"), s.get("footprint_bytes")),
                     kernel_branches_pct=pct_of(s.get("unique_taken_branches_kernel"), s.get("unique_taken_branches")))
            r["ipc"] = A.ratio(r["instructions"], r["cycles"])
            for m, (gr, verdict) in A.convergence(s, a.conv_threshold).items():
                r[f"conv_growth_pct_{m}"], r[f"conv_{m}"] = gr, verdict
            r["sampling_limited"] = ";".join(m for m in A.UNIQUE if r[f"conv_{m}"] == "sampling_limited")
            try:
                osp = object_split(s, ep["dir"])
            except (OSError, RuntimeError) as e:
                warn(f"{w}: object split failed: {e}")
                osp = None
            if osp:
                fb, ub = s.get("footprint_bytes"), s.get("unique_taken_branches")
                r.update(file_footprint_pct=pct_of(osp["bytes"]["file"] + osp["bytes"]["special"], fb),
                         anon_footprint_pct=pct_of(osp["bytes"]["anon"], fb),
                         anon_branches_pct=pct_of(osp["branches"]["anon"], ub),
                         anon_processes=osp["anon_processes"], objects_source=osp["source"])
            cc = collections.Counter(p.get("comm") for p in procs)
            comms[w] = (", ".join(f"{k} x{v}" for k, v in cc.most_common()) + f" among the {len(procs)} busiest") if procs else ""
            for k, v in (("event", ep["event"]), ("period", ep["period"]), ("filter", ep["filter"]),
                         ("src", s.get("analyzer_src_sha256")), ("perf", ff.get("perf_version")),
                         ("cpus", cap.get("cpus_measured")), ("java", ff.get("java_on_path"))):
                if v is not None:
                    seen[k].add(v)
        if st == "ok":
            seen["capture_s"].add(cs)
            for m, v in long_values(s):
                long_rows.append([w, ep["family"], ep["subgroup"], m, v, s.get("analyzer_sha") or "",
                                  A.fmt(ep["period"]), A.fmt(cs)])
        gates.append(r)

    ok_rows = [r for r in gates if r["status"] == "ok"]
    conv = {}
    for m in A.UNIQUE:  # the same summary as aggregate.py's
        vals = [(r[f"conv_growth_pct_{m}"], r["workload"]) for r in ok_rows if r[f"conv_growth_pct_{m}"] is not None]
        conv[m] = {"n": len(vals), "n_lim": sum(1 for r in ok_rows if r[f"conv_{m}"] == "sampling_limited"),
                   "desc": (f"median {statistics.median(v for v, _ in vals):.2f} %, max {max(vals)[0]:.2f} % "
                            f"({max(vals)[1]})" if vals else "n/a")}

    # ---- global identity rows ----
    spec_sha = spec_global(sp, "analyzer", "production", "analyzer_sha")
    spec_src = spec_global(sp, "analyzer", "production", "analyzer_src_sha256")
    srcs = sorted(seen["src"])
    spec_csv_sha = hashlib.sha256(sp["csv"]).hexdigest() if sp["csv"] is not None else None
    at = f"{sp['ref']}@{sp['commit'][:12]}" if sp["commit"] else "n/a"
    glob = [
        ["analyzer", "server", "analyzer_sha", sha or "", "one SHA across every pass with a summary",
         "OK" if sha else "no data", "summary.json of each pass"],
        ["analyzer", "server", "analyzer_src_sha256", ";".join(srcs), f"= {a.analyzer_src}",
         "no data" if not srcs else "OK" if srcs == [a.analyzer_src] else "MISMATCH", "summary.json of each pass"],
        ["analyzer", "spec26", "analyzer_sha", spec_sha or "", "= server analyzer_sha",
         "n/a" if not spec_sha or not sha else "same" if spec_sha == sha else "DIFFERENT (source sha256 decides)",
         f"{at}:{SPEC_DIR}/gates_global.csv"],
        ["analyzer", "spec26", "analyzer_src_sha256", spec_src or "", f"= {a.analyzer_src}",
         "n/a" if not spec_src else "same" if spec_src == a.analyzer_src else "DIFFERENT",
         f"{at}:{SPEC_DIR}/gates_global.csv"],
    ]
    for k, want in (("event", a.event), ("period", a.period), ("filter", A.CONTRACT_FILTER)):
        vs = sorted(seen[k], key=str)
        glob.append(["contract", "server", "branch_filter" if k == "filter" else k, ";".join(map(str, vs)), str(want),
                     "no data" if not vs else "OK" if vs == [want] else "MISMATCH",
                     "capture.frontend_footprint of each pass"])
    for gate, what in (("V1", "synthetic truth (analyzer)"), ("V2", "exact Intel PT cross-check (analyzer)"),
                       ("V3", "period sensitivity 5003 vs 20011 (period)")):
        n = sum(1 for x in sp["global"] if x.get("gate") == gate)
        glob.append([gate, "spec26", what, "", "", "NOT_RERUN",
                     f"{at}:{SPEC_DIR}/gates_global.csv ({n} {gate} rows there); {SPEC_REPORT}"])
    glob.append(["reference", "spec26_rows_long.csv", "source_commit", sp["commit"] or "", "",
                 "COPIED" if spec_csv_sha else "unavailable",
                 f"git show {sp['ref']}:{SPEC_DIR}/frontend_footprint_rows_long.csv" if sp["commit"] else
                 f"not copied (--spec-csv-from-git {sp['ref'] or 'none'})"])
    glob.append(["reference", "spec26_rows_long.csv", "sha256", spec_csv_sha or "", "", "COPIED" if spec_csv_sha else "unavailable", ""])

    # ---- write ----
    os.makedirs(a.out, exist_ok=True)
    for r in gates:
        dst_dir = os.path.join(a.out, r["workload"])
        dst = os.path.join(dst_dir, "summary.json")
        if r["status"] == "ok":
            os.makedirs(dst_dir, exist_ok=True)
            shutil.copyfile(os.path.join(E[r["workload"]]["dir"], "summary.json"), dst)
        elif os.path.exists(dst):  # a pass that no longer qualifies leaves no stale copy
            os.remove(dst)
            if not os.listdir(dst_dir):
                os.rmdir(dst_dir)
    with open(os.path.join(a.out, "frontend_footprint_rows_long.csv"), "w", newline="") as f:
        cw = csv.writer(f, lineterminator="\n")
        cw.writerow(LONG_COLS)
        cw.writerows(long_rows)
    with open(os.path.join(a.out, "gates.csv"), "w", newline="") as f:
        cw = csv.writer(f, lineterminator="\n")
        cw.writerow(GATE_COLS)
        for r in gates:
            cw.writerow([A.fmt(r[c]) for c in GATE_COLS])
    with open(os.path.join(a.out, "gates_global.csv"), "w", newline="") as f:
        cw = csv.writer(f, lineterminator="\n")
        cw.writerow(GLOBAL_COLS)
        for row in glob:
            cw.writerow([A.fmt(x) if not isinstance(x, str) else x for x in row])
    spec_dst = os.path.join(a.out, "spec26_rows_long.csv")
    if sp["csv"] is not None:
        with open(spec_dst, "wb") as f:
            f.write(sp["csv"])
    elif os.path.exists(spec_dst):
        warn(f"{spec_dst} left as it was (not refreshed: no git ref)")
    cmd = []  # the regenerate command: every flag that differs from its default
    for act in ap._actions:
        if act.dest in ("help", "expect"):
            continue
        v, d = getattr(a, act.dest), act.default
        if act.dest == "roots":
            d = [os.path.abspath(os.path.expanduser(x)) for x in d]
            if v != d:
                cmd.append("--roots " + " ".join(A.tilde(x) for x in v))
            continue
        if act.dest in PATH_ARGS:
            d = os.path.abspath(os.path.expanduser(d))
        if v != d:
            cmd.append(f"{act.option_strings[0]} {A.tilde(v)}")
    if a.expect:
        cmd.append("--expect " + " ".join(expect))
    M = {"args": a, "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
         "gates": gates, "seen": seen, "sha": sha, "spec": sp, "spec_sha": spec_sha, "conv": conv, "comms": comms,
         "spec_csv_sha256": spec_csv_sha, "cmdline": " ".join(cmd)}
    with open(os.path.join(a.out, "MANIFEST.md"), "w") as f:
        f.write(manifest(M))

    # ---- console summary ----
    cnt = collections.Counter(r["status"] for r in gates)
    print(f"aggregate_server: {len(gates)} workloads: " + ", ".join(f"{k} {v}" for k, v in sorted(cnt.items())))
    for st in ("gate_failed", "incomplete", "missing"):
        ws = [r["workload"] + (f" ({r['why']})" if r["why"] else "") for r in gates if r["status"] == st]
        if ws:
            print(f"aggregate_server: {st}: " + ", ".join(ws))
    lim = [r["workload"] for r in ok_rows if r["conv_unique_taken_branches"] == "sampling_limited"]
    print(f"aggregate_server: unique_taken_branches sampling_limited on {len(lim)} of {len(ok_rows)}"
          + (f": {', '.join(lim)}" if lim else ""))
    print(f"aggregate_server: analyzer_sha {sha!r}; source sha256 " + (", ".join(s[:12] for s in srcs) or "n/a")
          + f"; SPEC reference {at}" + (f" (spec26_rows_long.csv {len(sp['rows'])} rows)" if spec_csv_sha else ""))
    print(f"aggregate_server: wrote {a.out}/ ({len(ok_rows)} summaries, {len(long_rows)} long rows, "
          f"gates.csv {len(gates)} rows, gates_global.csv {len(glob)} rows, MANIFEST.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
