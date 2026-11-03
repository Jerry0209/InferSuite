#!/usr/bin/env python3
"""aggregate.py — aggregation step of the front-end footprint study (contract v1.1).

Reads finished episodes; never captures. Stdlib only: run it with the system python3.

  python3 aggregate.py [--data-root DIR] [--family spec26] [--index-csv CSV] [--out DIR]
                       [--v1-dir DIR] [--v1-defect-dir DIR] [--v2-dir DIR] [--v3-root DIR]
                       [--august-dir DIR] [--expect W [W ...]]

Inputs: <data-root>/<workload>/{DONE,summary.json[,objects|lines|edges.tsv.zst]} (the episode
driver's output). <workload>.contaminated.N dirs are counted, never aggregated; _session* dirs
are logs. V1 = <v1-dir>/check_v1.json, V2 = <v2-dir>/<name>/compare.json, V3 = a second data
root at period 5003, August = <august-dir>/<bench>/metrics.json. Every gate input may be absent.

Writes into --out:
  per_benchmark/<workload>.summary.json  copies of the aggregated episodes' summary.json
  frontend_footprint_rows_long.csv       workload,family,subgroup,metric,value,analyzer_sha,period
  gates.csv                              one row per workload (V4, convergence, August, V3, wrapper)
  gates_global.csv                       V1, V2 per program, V3 per benchmark, analyzer identity
  MANIFEST.md                            definitions, caveats with numbers, how to regenerate
Exit 2 if the aggregated episodes carry more than one analyzer SHA (nothing is written then).
"""
import argparse
import csv
import datetime
import json
import os
import shutil
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
INFRA = os.path.expanduser("~/spec26-infra/infra")
VALID = os.path.join(INFRA, "data_frontend_footprint_validation")

CONTRACT_VERSION = "v1.1"
CONTRACT_EVENT = "br_inst_retired.near_taken:pp"
CONTRACT_PERIOD = 20011
CONTRACT_FILTER = "any,save_type"
TOP_N = 20  # the analyzer lists at most 20 objects; a shorter list holds every object hit
NEAR = {"COND", "UNCOND", "CALL", "IND_CALL", "IND", "RET"}
TYPES = ["COND", "UNCOND", "CALL", "IND_CALL", "IND", "RET"]
UNIQUE = ["footprint_bytes", "footprint_bytes_user", "footprint_bytes_kernel",
          "unique_taken_branches", "unique_taken_branches_user", "unique_taken_branches_kernel"]
SCOPES = ["all", "noret", "indirect"]
LITERAL = [f"wavg_targets_{x}" for x in SCOPES]          # Rahul's metric 3: sampled lower bound (T_b)
WEFF = [f"weff_targets_{x}" for x in SCOPES]             # companion: inverse Simpson, frequency weighted
GE1 = [f"wavg_targets_ge1pct_{x}" for x in SCOPES]       # companion: targets carrying >= 1 % of executions
TARGET_FAMILIES = [("literal", "distinct targets T_b (Rahul's metric)", LITERAL),
                   ("weff", "inverse Simpson (effective targets)", WEFF),
                   ("ge1pct", "targets with >= 1 % of the executions", GE1)]
WAVG = [m + v for m in LITERAL for v in ("", "_user")]
COMPANIONS = [m + v for m in WEFF + GE1 for v in ("", "_user")]  # absent in older summaries: rows omitted
V3_METRICS = UNIQUE + LITERAL + WEFF + GE1
V2_NAMES = ["v2_python", "v2_gcc_train", "v2_gxx"]
V3_BENCHES = ["736.ocio_r", "721.gcc_r", "749.fotonik3d_r"]
NO_PROOF = ["734.vpr_r", "735.gem5_r", "772.marian_r"]  # SPEC output not verifiable as one command

# ---- the long CSV's metrics: stable names, shared with the Server and Agentic CSVs ----------
METRIC_DOCS = [
    ("footprint_bytes", "64 x unique 64 B instruction lines seen executing (user + kernel)"),
    ("footprint_bytes_user", "same, user-space lines only"),
    ("footprint_bytes_kernel", "same, kernel lines only (address >= 0xffff800000000000)"),
    ("unique_taken_branches", "distinct near taken branch instructions (canonical `from`), user + kernel"),
    ("unique_taken_branches_user", "same, user space"),
    ("unique_taken_branches_kernel", "same, kernel"),
] + [(f"unique_taken_branches_{t}", f"unique taken branches of type {t} (user + kernel)") for t in TYPES] + [
    ("wavg_targets_all", "sum(C_b*T_b)/sum(C_b) over all near taken branches; C_b = sampled executions, "
                         "T_b = distinct targets seen (Rahul's literal metric; sampled LOWER BOUND, T_b is a unique count)"),
    ("wavg_targets_all_user", "same, user-space branches only"),
    ("wavg_targets_noret", "same, returns excluded (the return stack predicts them, not the BTB)"),
    ("wavg_targets_noret_user", "same, user space"),
    ("wavg_targets_indirect", "same, indirect jumps and calls only (IND, IND_CALL)"),
    ("wavg_targets_indirect_user", "same, user space"),
    ("weff_targets_all", "sum(C_b*E_b)/sum(C_b), E_b = 1/sum_t(p_bt^2) (inverse Simpson: effective number of "
                         "targets), p_bt = share of branch b's executions that went to target t; all near taken branches"),
    ("weff_targets_all_user", "same, user space"),
    ("weff_targets_noret", "same, returns excluded"),
    ("weff_targets_noret_user", "same, user space"),
    ("weff_targets_indirect", "same, indirect jumps and calls only"),
    ("weff_targets_indirect_user", "same, user space"),
    ("wavg_targets_ge1pct_all", "sum(C_b*K_b)/sum(C_b), K_b = number of targets with p_bt >= 0.01; all near taken branches"),
    ("wavg_targets_ge1pct_all_user", "same, user space"),
    ("wavg_targets_ge1pct_noret", "same, returns excluded"),
    ("wavg_targets_ge1pct_noret_user", "same, user space"),
    ("wavg_targets_ge1pct_indirect", "same, indirect jumps and calls only"),
    ("wavg_targets_ge1pct_indirect_user", "same, user space"),
]
METRICS = [m for m, _ in METRIC_DOCS]
LONG_COLS = ["workload", "family", "subgroup", "metric", "value", "analyzer_sha", "period"]

GATE_DOCS = [
    ("workload", "benchmark (`<bench>@<k>` = ref command line k; extra rows, never replacements)"),
    ("family", "`--family`"),
    ("subgroup", "from `workload_index.csv` (SPEC-int / SPEC-fp)"),
    ("expected", "1 if the workload is in the `--expect` list"),
    ("status", "ok = DONE, every V4 gate passed and the event/period match the contract (only these "
               "reach the long CSV); gate_failed = summary.json without DONE, or a failed gate; "
               "contract_mismatch; incomplete = episode dir without summary.json; missing = no episode dir"),
    ("in_long_csv", "1 if the workload's rows are in the long CSV"),
    ("analyzer_sha", "`analyzer_sha` in summary.json"),
    ("period", "sampling period of the episode"),
    ("event", "sampling event of the episode"),
    ("contract_ok", f"1 if event = `{CONTRACT_EVENT}` and period = {CONTRACT_PERIOD}"),
    ("exit_status", "benchmark exit status"),
    ("output_check", "SPEC output check: pass / fail / unavailable / error"),
    ("output_ok", "pass, or unavailable (the 3 benchmarks SPEC cannot verify as one command)"),
    ("lost_pct", "lost samples / (samples + lost), %"),
    ("lost_ok", "lost_pct < 1"),
    ("sample_coverage", "samples x period / exact `br_inst_retired.near_taken`; 1 = no sample dropped"),
    ("coverage_ok", "abs(sample_coverage - 1) <= 0.02"),
    ("throttle_events", "perf THROTTLE records"),
    ("throttle_ok", "0 THROTTLE records and perf's record stats were read"),
    ("mean_cores", "fence occupancy from the 10 Hz cpu.stat poller, cores"),
    ("occupancy_ok", "mean_cores <= the driver's MAX_MEAN_CORES"),
    ("witness_rows", "2 s whole-machine witness rows during the episode"),
    ("witness_foreign_rows", "witness rows with a foreign task above 10 % CPU"),
    ("witness_mean_foreign_cpu_pct", "mean foreign CPU over the witness rows, %"),
    ("witness_clean", "driver's rule: rows > 0, foreign rows <= 5 % of rows, mean foreign CPU <= 25 %"),
    ("iso_proof_present", "1 if an ISO-PROOF line is recorded"),
    ("analyzer_ok", "analyzer exit 0 and no `error` key"),
    ("v4_all_ok", "driver's `gates_v4.all_ok`"),
    ("contaminated_attempts", "set-aside attempts `<workload>.contaminated.N` (never aggregated)"),
] + [(c, d) for m in UNIQUE for c, d in (
    (f"conv_growth_pct_{m}", f"100 x ({m} at 100 % of samples - at 75 %) / value at 100 %"),
    (f"conv_{m}", "sampling_limited if conv_growth_pct > 2, else converged"))] + [
    ("sampling_limited", "the unique metrics marked sampling_limited, `;`-separated"),
    ("wall_s", "benchmark wall time, release to exit, s"),
    ("aug_wall_s", "August campaign wall time, s"),
    ("wall_dev_pct", "100 x (wall_s / aug_wall_s - 1); LBR sampling overhead"),
    ("wall_within_10pct", "abs(wall_dev_pct) <= 10"),
    ("instructions", "exact instructions, `perf stat` on the fence over the window"),
    ("cycles", "exact cycles, same"),
    ("ipc", "instructions / cycles"),
    ("aug_ipc", "August `metrics.IPC` (windowed)"),
    ("ipc_ratio", "substitute (b): ipc / aug_ipc"),
    ("aug_instructions_extrap", "August `raw_sums.instructions` x wall_s / `raw_sums.seconds` (windowed counts scaled to the run)"),
    ("instr_ratio_extrap", "substitute (a): instructions / aug_instructions_extrap"),
    ("output_unverifiable", "1 for benchmarks whose SPEC output cannot be checked (output_check unavailable)"),
    ("aug_instr_1pct_gate", "guide's 'instructions within 1 % of August' gate: NO_PROOF (August has no "
                            "whole-run instruction total) where output_unverifiable, else not_required"),
    ("wrapper_bash_bytes", "footprint of /usr/bin/bash (the pre-exec shell in the fence), B"),
    ("wrapper_bash_branches", "unique taken branches in /usr/bin/bash"),
    ("wrapper_runuser_bytes", "footprint of the runuser binary plus anonymous code of runuser pids, B"),
    ("wrapper_runuser_branches", "unique taken branches in the same objects"),
    ("wrapper_bytes_pct", "100 x (bash + runuser bytes) / footprint_bytes"),
    ("wrapper_branches_pct", "100 x (bash + runuser branches) / unique_taken_branches"),
    ("runuser_sample_share_pct", "share of LBR samples taken in runuser processes, %"),
    ("wrapper_source", "top_objects (exact: list < 20 entries), tables (recomputed from objects/lines/"
                       "edges.tsv.zst) or top_objects_partial (a wrapper object below the 20th entry counts 0)"),
    ("v3_status", "status of the period-5003 episode (blank = not in the V3 set)"),
    ("v3_contaminated_attempts", "set-aside attempts in the V3 root"),
] + [(f"v3_ratio_{m}", f"{m} at period 5003 / at period 20011") for m in V3_METRICS]
GATE_COLS = [c for c, _ in GATE_DOCS]
GLOBAL_COLS = ["gate", "name", "metric", "value", "threshold", "verdict", "source"]


PATH_ARGS = ("data_root", "index_csv", "out", "v1_dir", "v1_defect_dir", "v2_dir", "v3_root", "august_dir")


def warn(msg):
    print(f"aggregate: WARNING {msg}", file=sys.stderr)


def tilde(p):
    """A path for the MANIFEST: repo-relative inside the repo, ~-relative under $HOME."""
    p = str(p)
    if p.startswith(REPO + os.sep):
        return os.path.relpath(p, REPO)
    home = os.path.expanduser("~")
    return "~" + p[len(home):] if p.startswith(home + os.sep) else p


def load_json(p):
    try:
        with open(p) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def get(d, *ks):
    for k in ks:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def num(v):
    """float(v) or None (strings like "1.000" in metadata are accepted)."""
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def ratio(a, b):
    a, b = num(a), num(b)
    return a / b if a is not None and b else None


def fmt(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if v != v:
            return ""
        return str(int(v)) if v.is_integer() and abs(v) < 1e15 else f"{v:.10g}"
    return str(v)


# ---- episodes -------------------------------------------------------------------------------
def scan_root(root):
    """-> ({workload: dir}, {workload: contaminated attempts}, root exists)"""
    eps, cont = {}, {}
    if not root or not os.path.isdir(root):
        return eps, cont, False
    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name)
        if not os.path.isdir(p) or name.startswith(("_", ".")):
            continue
        if ".contaminated." in name:
            w = name.split(".contaminated.")[0]
            cont[w] = cont.get(w, 0) + 1
        else:
            eps[name] = p
    return eps, cont, True


def evaluate(name, d, exp_event, exp_period):
    """Read one episode dir and judge whether it may be aggregated."""
    s = load_json(os.path.join(d, "summary.json"))
    ep = {"name": name, "dir": d, "done": os.path.exists(os.path.join(d, "DONE")), "s": s or {}}
    if s is None:
        ep.update(status="incomplete", period=None, event=None, contract_ok=None, why="no summary.json")
        return ep
    if s.get("workload") not in (None, name):
        warn(f"{d}: summary.json says workload {s.get('workload')!r}; using the dir name {name!r}")
    ff = get(s, "capture", "frontend_footprint") or {}
    period = ff.get("period", get(s, "meta", "period"))
    period = int(num(period)) if num(period) is not None else None
    event = ff.get("event")
    checks = []
    if event is not None:
        checks.append(event == exp_event)
    if period is not None:
        checks.append(period == exp_period)
    contract_ok = all(checks) if checks else None
    g = s.get("gates_v4")
    why = []
    if not ep["done"]:
        why.append("no DONE")
    if "error" in s:
        why.append("analyzer error")
    if isinstance(g, dict):
        why += [k for k in ("analyzer_ok", "exit_status_0", "output_ok", "lost_ok", "coverage_ok",
                            "occupancy_ok", "throttle_ok") if g.get(k) is False]
        if g.get("all_ok") is False and not why:
            why.append("all_ok false")
    elif ep["done"]:
        warn(f"{d}: no gates_v4 in summary.json; trusting DONE")
    if why:
        status = "gate_failed"
    elif contract_ok is False:
        status = "contract_mismatch"
        why.append(f"event {event} period {period}")
    else:
        status = "ok"
        if contract_ok is None:
            warn(f"{d}: event/period not recorded; contract not verifiable")
    ep.update(status=status, period=period, event=event, contract_ok=contract_ok, why="; ".join(why))
    return ep


def convergence(s, thr):
    pts = {p.get("pct"): p for p in (get(s, "convergence", "points") or []) if isinstance(p, dict)}
    p75, p100 = pts.get(75) or {}, pts.get(100) or {}
    out = {}
    for m in UNIQUE:
        a, b = num(p75.get(m)), num(p100.get(m))
        if a is None or not b:
            out[m] = (None, "n/a")
            continue
        if num(s.get(m)) is not None and num(s.get(m)) != b:
            warn(f"{s.get('workload')}: convergence {m} at 100 % ({b}) != final value ({s.get(m)})")
        g = 100.0 * (b - a) / b
        if g < 0:  # unique counts are first-seen counts: they can only grow
            warn(f"{s.get('workload')}: {m} falls from {a:g} at 75 % to {b:g} at 100 %: inconsistent summary")
        out[m] = (g, "sampling_limited" if g > thr else "converged")
    return out


def table_rows(d, name):
    """Rows of an analyzer table (plain or .zst), header skipped; None if absent."""
    p = os.path.join(d, name)
    if os.path.exists(p):
        with open(p) as f:
            next(f, None)
            return [ln.rstrip("\n").split("\t") for ln in f]
    if not os.path.exists(p + ".zst"):
        return None
    out = subprocess.run(["zstd", "-dcq", p + ".zst"], capture_output=True, text=True)
    if out.returncode != 0:
        return None
    return [ln.split("\t") for ln in out.stdout.splitlines()[1:]]


def wrapper_from_tables(d, ru_pids):
    objs = table_rows(d, "objects.tsv")
    if objs is None:
        return None
    cls = {}
    for o in objs:
        if len(o) < 5:
            continue
        oid, kind, base = o[0], o[1], os.path.basename(o[2])
        if kind == "file" and base in ("bash", "runuser"):
            cls[oid] = base
        elif kind == "anon" and num(o[4]) in ru_pids:
            cls[oid] = "runuser"
    acc = {"bash": [0, 0], "runuser": [0, 0]}
    lines = table_rows(d, "lines.tsv")
    edges = table_rows(d, "edges.tsv")
    if lines is None or edges is None:
        return None
    for r in lines:
        if r and r[0] in cls:
            acc[cls[r[0]]][0] += 64
    seen = set()
    for r in edges:
        if len(r) > 4 and r[0] in cls and r[4] in NEAR and (r[0], r[1]) not in seen:
            seen.add((r[0], r[1]))
            acc[cls[r[0]]][1] += 1
    return acc


def wrapper_share(s, d):
    """The fence holds the runuser parent and the pre-exec bash: their own code, per benchmark."""
    objs = s.get("top_objects_by_footprint") or []
    procs = s.get("top_processes") or []
    ru_pids = {num(p.get("pid")) for p in procs if p.get("comm") == "runuser"}
    ru_share = sum(num(p.get("share")) or 0 for p in procs if p.get("comm") == "runuser")
    acc = {"bash": [0, 0], "runuser": [0, 0]}
    for o in objs:
        base = os.path.basename(str(o.get("path", "")))
        c = None
        if o.get("kind") == "file" and base in ("bash", "runuser"):
            c = base
        elif o.get("kind") == "anon" and num(o.get("pid")) in ru_pids:
            c = "runuser"
        if c:
            acc[c][0] += int(num(o.get("footprint_bytes")) or 0)
            acc[c][1] += int(num(o.get("unique_taken_branches")) or 0)
    src = "top_objects"
    if len(objs) >= TOP_N:
        t = wrapper_from_tables(d, ru_pids)
        if t is not None:
            acc, src = t, "tables"
        else:
            src = "top_objects_partial"
    fb, ub = num(s.get("footprint_bytes")), num(s.get("unique_taken_branches"))
    wb, wu = acc["bash"][0] + acc["runuser"][0], acc["bash"][1] + acc["runuser"][1]
    return {"wrapper_bash_bytes": acc["bash"][0], "wrapper_bash_branches": acc["bash"][1],
            "wrapper_runuser_bytes": acc["runuser"][0], "wrapper_runuser_branches": acc["runuser"][1],
            "wrapper_bytes_pct": 100.0 * wb / fb if fb else None,
            "wrapper_branches_pct": 100.0 * wu / ub if ub else None,
            "runuser_sample_share_pct": 100.0 * ru_share, "wrapper_source": src}


def august(aug_dir, base):
    m = load_json(os.path.join(aug_dir, base, "metrics.json")) if aug_dir else None
    if not m:
        return {}
    return {"wall_s": num(m.get("wall_s")), "ipc": num(get(m, "metrics", "IPC")),
            "instr": num(get(m, "raw_sums", "instructions")), "seconds": num(get(m, "raw_sums", "seconds"))}


def witness_clean(w):
    if not isinstance(w, dict):
        return None
    n, flag, mean = num(w.get("witness_rows")), num(w.get("rows_with_foreign_task")), num(w.get("mean_foreign_cpu_pct"))
    if n is None or flag is None or mean is None:
        return None
    return not (n == 0 or flag > 0.05 * n or mean > 25)


def read_index(path, family):
    sub, order = {}, []
    try:
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                if r.get("family") == family:
                    sub[r["workload"]] = r.get("subgroup", "")
                    order.append(r["workload"])
    except OSError as e:
        warn(f"index {path}: {e}")
    return sub, order


# ---- gates V1 / V2 / V3 ----------------------------------------------------------------------
def v1_rows(d, gate, source_note):
    c = load_json(os.path.join(d, "check_v1.json")) if d else None
    if c is None:
        return [[gate, os.path.basename(d or "") or "V1", "check_v1.json", "", "", "pending", d or ""]], None
    e, o, r, ch = c.get("expected", {}), c.get("observed", {}), c.get("rel_err", {}), c.get("checks", {})
    pv = lambda ok: "PASS" if ok else "FAIL"
    nm = os.path.basename(os.path.normpath(d))
    rows = [
        [gate, nm, "footprint_lines", o.get("footprint_lines"), f"{e.get('footprint_lines')} +- 2 lines",
         pv(ch.get("footprint_within_2_lines")), source_note],
        [gate, nm, "unique_taken_branches", o.get("unique_taken_branches"), f"{e.get('unique_taken_branches')} exact",
         pv(ch.get("unique_taken_branches_exact")), source_note]]
    for m in ("wavg_targets_all", "wavg_targets_noret", "wavg_targets_indirect"):
        rows.append([gate, nm, f"{m}_rel_err", r.get(m), "< 0.01", pv(ch.get(f"{m}_within_1pct")), source_note])
    rows.append([gate, nm, "pass", c.get("pass"), "all checks", pv(c.get("pass")), source_note])
    return rows, c


def v2_load(v2_dir, names):
    out = {}
    for n in names:
        p = os.path.join(v2_dir, n, "compare.json") if v2_dir else ""
        out[n] = load_json(p) if p else None
    return out


def v2_find(c, m):
    """compare.json entry {pt, lbr, rel_err} for target metric m: under "wavg" (compare_v2.py's layout
    for the literal metric) or under any other top-level dict (the companions' layout is not fixed yet)."""
    w = c.get("wavg")
    if isinstance(w, dict) and isinstance(w.get(m), dict):
        return w[m]
    for v in c.values():
        if isinstance(v, dict) and isinstance(v.get(m), dict) and "rel_err" in v[m]:
            return v[m]
    return None


def v2_hybrid(c, m):
    """Relative error of the literal metric with LBR's sampled C_b and PT's exact T_b, if compare.json
    records it: any key containing 'hybrid', inside the metric's entry or as a top-level dict by metric."""
    for k, v in (v2_find(c, m) or {}).items():
        if "hybrid" in k.lower():
            return num(v.get("rel_err")) if isinstance(v, dict) else num(v)
    for k, v in c.items():
        if "hybrid" in k.lower() and isinstance(v, dict) and m in v:
            x = v[m]
            return num(x.get("rel_err")) if isinstance(x, dict) else num(x)
    return None


def v2_rows(v2):
    rows = []
    for n, c in v2.items():
        if c is None:
            rows.append(["V2", n, "compare.json", "", "", "pending", "compare.json absent"])
            continue
        attr = get(c, "processes", "pt_attribution_ok")
        same = get(c, "run", "identical_stdout")
        base = "REPORTED"
        if attr is False:
            base = "INVALID_REFERENCE"
        elif same is False:
            base = "CHECK_DIFFERENT_STDOUT"
        src = "compare.json (user-space file/special objects)"
        R = lambda m, v, t="", verdict=base: rows.append(["V2", n, m, v, t, verdict, src])
        for key, lab in (("footprint_lines", "footprint"), ("unique_taken_branches", "unique_branches"), ("edges", "edges")):
            R(f"{lab}_recall", get(c, key, "recall"))
            pr = num(get(c, key, "precision"))
            R(f"{lab}_precision", pr, ">= 0.99",
              base if pr is None or pr >= 0.99 or base != "REPORTED" else "CHECK_PRECISION")
            R(f"{lab}_pt", get(c, key, "pt"))
            R(f"{lab}_lbr", get(c, key, "lbr"))
        for m in LITERAL + WEFF + GE1:
            e = v2_find(c, m)
            if e is None:
                R(f"{m}_rel_err", None, "", "pending (not in compare.json)")
            else:
                R(f"{m}_rel_err", num(e.get("rel_err")))
        for m in LITERAL:
            h = v2_hybrid(c, m)
            R(f"{m}_rel_err_lbr_C_pt_T", h, "", base if h is not None else "pending (not in compare.json)")
        for p in c.get("recall_vs_lbr_samples") or []:
            if p.get("pct") in (25, 50, 75):
                R(f"footprint_recall_at_{p['pct']}pct", p.get("footprint_recall"))
                R(f"branch_recall_at_{p['pct']}pct", p.get("branch_recall"))
        R("pt_attribution_ok", attr, "true")
        R("identical_stdout", same, "true")
    return rows


# ---- MANIFEST --------------------------------------------------------------------------------
def f3(v, p=3):
    v = num(v)
    return "n/a" if v is None else f"{v:.{p}f}"


def pct(v, p=1, sign=False):
    v = num(v)
    return "n/a" if v is None else (f"{v:+.{p}f} %" if sign else f"{v:.{p}f} %")


def med_range(vals, unit=""):
    vals = [v for v in vals if v is not None]
    if not vals:
        return "n/a", 0
    return f"median {statistics.median(vals):.2f}{unit}, range {min(vals):.2f}-{max(vals):.2f}{unit}", len(vals)


def manifest(A):
    a = A["args"]
    ok = [r for r in A["gates"] if r["status"] == "ok"]
    n_ok, L = len(ok), []
    P = L.append
    P("# Front-end footprint, x86 — MANIFEST\n")
    P(f"Generated {A['generated']} by `local_agents/kit/frontend_footprint/aggregate.py` from "
      f"`{tilde(a.data_root)}`. Do not edit by hand: regenerate (last section).\n")
    P("Three numbers per workload, for Rahul's front-end question: instruction footprint, unique taken "
      "branches, and the weighted average number of targets per taken branch. The method is "
      "`docs/handoff/execution/frontend_footprint_method.md` (the contract); the analyzer is "
      "`local_agents/kit/frontend_footprint/`.\n")

    P("## Population\n")
    exp = [r for r in A["gates"] if r["expected"]]
    P(f"* Expected: {len(exp)} workloads (family `{a.family}`"
      + (f", from `{tilde(a.index_csv)}`)." if not a.expect else ", from `--expect`)."))
    P(f"* Aggregated (status ok): {n_ok}. By subgroup: "
      + (", ".join(f"{k} {v}" for k, v in sorted(A['by_sub'].items())) or "none") + ".")
    for st in ("gate_failed", "contract_mismatch", "incomplete", "missing"):
        rs = [r for r in A["gates"] if r["status"] == st]
        if rs:
            P(f"* {st}: {len(rs)} — " + ", ".join(
                r["workload"] + (f" ({A['why'][r['workload']]})" if A["why"].get(r["workload"]) else "") for r in rs) + ".")
    extra = [r["workload"] for r in A["gates"] if not r["expected"]]
    if extra:
        P(f"* Not in the expected list (extra rows): {', '.join(extra)}.")
    nc = sum(r["contaminated_attempts"] or 0 for r in A["gates"])
    P(f"* Set-aside attempts (`*.contaminated.N`, foreign work overlapped): {nc} in "
      f"{sum(1 for r in A['gates'] if r['contaminated_attempts'])} workload(s). Never aggregated.\n")

    P("## Contract\n")
    P("| Parameter | Value |\n|---|---|")
    P(f"| Contract | {CONTRACT_VERSION} (2026-11-03) |")
    P(f"| Event | `{CONTRACT_EVENT}` (PEBS; user + kernel). Seen in the data: "
      + (", ".join(f"`{e}`" for e in sorted(A["events"])) or "n/a") + " |")
    P(f"| Period | `-c {CONTRACT_PERIOD}`. Seen: " + (", ".join(str(p) for p in sorted(A["periods"])) or "n/a") + " |")
    P(f"| Branch filter | `-j {CONTRACT_FILTER}` |")
    P("| Scope | the benchmark's fence cgroup, `perf record -a -C <measured> --cgroup=<fence>`; measured cores "
      + (", ".join(sorted(A["cpus"])) or "4-11") + " |")
    P("| Window | benchmark released from a FIFO gate after both perf instances acknowledged enable, to scope exit |")
    P(f"| Analyzer SHA | `{A['sha'] or 'none (no data)'}` (one SHA across every aggregated episode, V3 included; checked) |")
    P("| Analyzer source sha256 | " + (", ".join(f"`{x}`" for x in sorted(A["src"])) or "n/a") + " |")
    P("| perf | " + (", ".join(sorted(A["perfv"])) or "n/a") + " |\n")
    if A["stale_label"]:
        P("The driver's `capture.frontend_footprint.contract` string reads `... v1` although the event is "
          "`:pp` (v1.1). The `event` field is authoritative; the label is stale.\n")

    P("## Lower bounds: what each number means\n")
    v2ok = {n: c for n, c in A["v2"].items() if c}
    hyb = [(n, v2_hybrid(c, "wavg_targets_all")) for n, c in v2ok.items() if v2_hybrid(c, "wavg_targets_all") is not None]
    lit = [(n, num(get(v2_find(c, "wavg_targets_all") or {}, "rel_err"))) for n, c in v2ok.items()]
    lit = [(n, x) for n, x in lit if x is not None]
    comp = [(n, m, num((v2_find(c, m) or {}).get("rel_err"))) for n, c in v2ok.items() for m in WEFF + GE1]
    comp = [x for x in comp if x[2] is not None]
    P(f"* Footprint and unique taken branches count only what the samples saw. Each taken-branch execution "
      f"is captured with probability 32/{CONTRACT_PERIOD} (about 0.16 %), so code that runs rarely is "
      "missed. Both are sampled LOWER BOUNDS.")
    P("* `wavg_targets_*` (Rahul's literal metric 3) is a sampled LOWER BOUND too. Its T_b is a unique count, "
      "the number of distinct targets seen, and a rarely taken target is missed like a rarely taken branch. "
      "The contract called metric 3 robust to sampling; V2 refutes that for the literal form"
      + (" (" + ", ".join(f"{pct(100 * x, 1, True)} on {n}" for n, x in lit) + ", all branches)" if lit else "")
      + ". " + ("The weights C_b are not the cause: LBR's sampled C_b with PT's exact T_b gives "
                + ", ".join(f"{pct(100 * x, 1, True)} ({n})" for n, x in hyb) + ", so the error is all in T_b."
                if hyb else "The C_b / T_b split (LBR's C_b with PT's exact T_b) is not in compare.json yet: pending."))
    P("* `weff_targets_*` (inverse Simpson: the effective number of targets) and `wavg_targets_ge1pct_*` "
      "(targets carrying >= 1 % of the branch's executions) estimate frequency-weighted quantities. A target "
      "counts by its share of the executions, so the rare targets that sampling misses carry almost no "
      "weight, and the T_b bias does not arise. "
      + (f"On V2 they are within {max(abs(100 * x) for _, _, x in comp):.1f} % of PT ({len(comp)} values "
         f"over {len({n for n, _, _ in comp})} program(s))." if comp
         else "V2 numbers for them: pending (not in compare.json yet).")
      + {"all": "", "nodata": "", "none": " They are absent from every aggregated summary (an analyzer without them).",
         "some": " WARNING: present in some summaries only (see gates)."}[A["comp_state"]])
    P("* Which of the three target metrics goes in the figure is Rahul's call. All three are in the long CSV.")
    P("* A separate C_b bias existed under contract v1 and is gone in v1.1 (V1 section below).")
    P("* The same period in every family makes the sampling bias comparable across families; it is largest "
      "for flat, tail-heavy profiles.\n")
    P("V2 measures the bias against an exact Intel PT trace of the same command (user-space, file-backed "
      "code). Recall = share of what PT proved executed that LBR also saw.\n")
    P("| Program | LBR samples | Footprint recall | Branch recall | Precision (lines / branches) | PT reference |")
    P("|---|---|---|---|---|---|")
    for n, c in A["v2"].items():
        if c is None:
            P(f"| {n} | pending | pending | pending | pending | pending |")
            continue
        P(f"| {n} | {get(c, 'lbr_diagnostics', 'samples')} | {f3(get(c, 'footprint_lines', 'recall'))} "
          f"(PT {get(c, 'footprint_lines', 'pt')} lines) | {f3(get(c, 'unique_taken_branches', 'recall'))} "
          f"(PT {get(c, 'unique_taken_branches', 'pt')}) | {f3(get(c, 'footprint_lines', 'precision'))} / "
          f"{f3(get(c, 'unique_taken_branches', 'precision'))} | "
          f"{'valid' if get(c, 'processes', 'pt_attribution_ok') is not False else 'INVALID (processes not separated)'} |")
    P("\nRelative error of the target metrics, LBR vs PT (same branches, user space):\n")
    P("| Program | Metric | all | noret | indirect |\n|---|---|---|---|---|")
    for n, c in A["v2"].items():
        if c is None:
            P(f"| {n} | all | pending | pending | pending |")
            continue
        rows = [("literal `wavg_targets_*`", [num((v2_find(c, m) or {}).get("rel_err")) for m in LITERAL]),
                ("literal, LBR C_b x PT T_b", [v2_hybrid(c, m) for m in LITERAL]),
                ("inverse Simpson `weff_targets_*`", [num((v2_find(c, m) or {}).get("rel_err")) for m in WEFF]),
                (">= 1 % `wavg_targets_ge1pct_*`", [num((v2_find(c, m) or {}).get("rel_err")) for m in GE1])]
        for lab, xs in rows:
            P(f"| {n} | {lab} | " + " | ".join(pct(100 * x, 1, True) if x is not None else "pending" for x in xs) + " |")
    P("\nThe V2 programs run 1-4 s. Recall depends on how often code runs, so it is a reference point "
      "for the size of the bias, not a correction factor: do not scale the numbers by it.\n")
    conv = A["conv_summary"]
    P(f"Convergence: each unique count is recomputed at 75 % and 100 % of the samples. Growth over the "
      f"last quarter above {a.conv_threshold:g} % marks the count `sampling_limited` (still rising). "
      f"Over the {n_ok} aggregated workloads:\n")
    for m in UNIQUE:
        c = conv[m]
        P(f"* `{m}`: sampling_limited on {c['n_lim']} of {c['n']}; growth {c['desc']}.")
    P("")

    P("## V3: period sensitivity (period 5003 / period 20011)\n")
    if A["v3"]:
        P("Four times denser sampling. A ratio above 1 means the period-20011 value is sampling-limited.\n")
        for hdr, ms in ((["footprint", "fp user", "fp kernel", "unique br", "br user", "br kernel"], UNIQUE),
                        ([f"{f} {x}" for f in ("literal", "weff", "ge1pct") for x in SCOPES], LITERAL + WEFF + GE1)):
            P("| Benchmark | status | " + " | ".join(hdr) + " |")
            P("|---|---|" + "---|" * len(hdr))
            for w, st, rat in A["v3"]:
                P(f"| {w} | {st} | " + " | ".join(f3(rat.get(m)) for m in ms) + " |")
            P("")
    else:
        P("No V3 benchmark configured.\n")

    P("## V1: synthetic truth\n")
    c = A["v1"]
    sgn = lambda d, m: ((num(get(d, "observed", m)) - num(get(d, "expected", m))) / num(get(d, "expected", m))
                        if num(get(d, "observed", m)) is not None and num(get(d, "expected", m)) else None)
    if c:
        o, e = c.get("observed", {}), c.get("expected", {})
        P(f"{'PASS' if c.get('pass') else 'FAIL'} (`{tilde(a.v1_dir)}`): footprint {o.get('footprint_lines')} lines "
          f"(expected {e.get('footprint_lines')}), unique taken branches {o.get('unique_taken_branches')} "
          f"(expected {e.get('unique_taken_branches')}), literal weighted averages "
          + ", ".join(pct(100 * sgn(c, m), 2, True) if sgn(c, m) is not None else "n/a" for m in LITERAL)
          + " (all, noret, indirect; gate 1 %)."
          + (f" The least-sampled V1 branch has {c['min_sampled_entries_per_site']} sampled executions and every "
             "T_b is exact (`branches_target_count_mismatch` empty), so V1 tests C_b, not T_b."
             if c.get("min_sampled_entries_per_site") and not c.get("branches_target_count_mismatch") else "")
          + " Analyzer source of the V1 run: " + A["v1_src_note"] + ".\n")
    else:
        P("pending (no check_v1.json).\n")
    d = A["v1_defect"]
    if d:
        P(f"Defect found and fixed (not a gate result): under contract v1 (bare event, `{tilde(a.v1_defect_dir)}`) the "
          "LBR was frozen at the PMI after interrupt skid, which biased which 32-branch windows were sampled, "
          "i.e. C_b. V1 read the literal weighted averages "
          + ", ".join(pct(100 * sgn(d, m), 1, True) if sgn(d, m) is not None else "n/a" for m in LITERAL)
          + " (all, noret, indirect) while T_b and the unique counts were exact: a C_b bias, separate from the "
          "T_b bias above. Contract v1.1 samples with `:pp`, where PEBS writes the LBR at the overflowing "
          "branch, and the bias is gone. No production episode used the v1 event"
          + (" (checked)." if not A["v1_event_seen"] else f" — EXCEPT {', '.join(A['v1_event_seen'])} (status contract_mismatch).")
          + "\n")

    P("## V4 and the August reference\n")
    walls = [r["wall_dev_pct"] for r in ok if r["wall_dev_pct"] is not None]
    inw = sum(1 for r in ok if r["wall_within_10pct"])
    P(f"* All {n_ok} aggregated workloads passed V4 (exit 0, output check, lost < 1 %, sample coverage "
      "within 2 %, no throttling, occupancy). Witness clean on "
      f"{sum(1 for r in ok if r['witness_clean'])} of {n_ok}; ISO-PROOF recorded on "
      f"{sum(1 for r in ok if r['iso_proof_present'])} of {n_ok}.")
    P(f"* Wall time vs August (LBR overhead; guide: within ~10 %): within on {inw} of {len(walls)}; deviation "
      + (f"median {statistics.median(walls):+.1f} %, range {min(walls):+.1f} to {max(walls):+.1f} %." if walls else "n/a."))
    ip = [r["ipc_ratio"] for r in ok if r["ipc_ratio"] is not None]
    ia = [r["instr_ratio_extrap"] for r in ok if r["instr_ratio_extrap"] is not None]
    P(f"* IPC / August IPC, all workloads: {med_range(ip)[0]} (n={len(ip)}). Instructions / August "
      f"extrapolated instructions: {med_range(ia)[0]} (n={len(ia)}). August counted in windows only "
      "(`raw_sums.seconds` of `wall_s`), so (a) carries the windowing error; (b) does not depend on it.")
    flagged = [r for r in A["gates"] if r["output_unverifiable"]]
    P(f"* The guide's gate \"instructions within 1 % of August\" for the {len(flagged)} benchmarks whose SPEC "
      "output cannot be verified is NOT evaluable: August has no whole-run instruction total. Reported as "
      "`NO_PROOF` with two labelled substitutes:\n")
    if flagged:
        P("| Benchmark | output_check | (a) instr / August extrapolated | (b) IPC / August IPC | wall dev |")
        P("|---|---|---|---|---|")
        for r in flagged:
            P(f"| {r['workload']} | {r['output_check'] or r['status']} | {f3(r['instr_ratio_extrap'], 4)} | "
              f"{f3(r['ipc_ratio'], 4)} | {pct(r['wall_dev_pct'], 1, True)} |")
        P("")

    P("## Wrapper code inside the fence\n")
    P("The fence also holds the `runuser` parent and the `bash` that waits on the start FIFO and then "
      "execs the benchmark. Their code is inside every number. Below: footprint and unique taken branches "
      "in `/usr/bin/bash` and in `runuser` (its binary plus its anonymous pages), from "
      "`top_objects_by_footprint` and `top_processes`. Kernel and shared-library code (ld.so, libc) "
      "that they ran cannot be separated from the benchmark's, so these are lower bounds of the "
      "wrapper's share.\n")
    if ok:
        P("| Workload | bash KB | bash branches | runuser KB | runuser branches | share of footprint | share of branches | runuser samples |")
        P("|---|---|---|---|---|---|---|---|")
        for r in ok:
            P(f"| {r['workload']} | {r['wrapper_bash_bytes'] / 1000:.1f} | {r['wrapper_bash_branches']} | "
              f"{r['wrapper_runuser_bytes'] / 1000:.1f} | {r['wrapper_runuser_branches']} | {pct(r['wrapper_bytes_pct'], 2)} | "
              f"{pct(r['wrapper_branches_pct'], 2)} | {pct(r['runuser_sample_share_pct'], 4)} |")
        wb = [r["wrapper_bytes_pct"] for r in ok if r["wrapper_bytes_pct"] is not None]
        P(f"\nShare of footprint: {med_range(wb, ' %')[0]} (n={len(wb)}).\n")
    ks = [100 * num(r["_s"].get("footprint_bytes_kernel")) / num(r["_s"].get("footprint_bytes"))
          for r in ok if num(r["_s"].get("footprint_bytes"))]
    if ks:
        P(f"Kernel share of the footprint: {med_range(ks, ' %')[0]} (n={len(ks)}).\n")

    P("## Files\n")
    P("| File | What |\n|---|---|")
    P("| `per_benchmark/<workload>.summary.json` | the episode's summary.json, copied (aggregated episodes only): analyzer output plus `workload`, `capture`, `exact_counts`, `gates_v4` |")
    P("| `frontend_footprint_rows_long.csv` | one row per (workload, metric); aggregated workloads only |")
    P("| `gates.csv` | one row per workload: V4, convergence, August, wrapper, V3 |")
    P("| `gates_global.csv` | V1, V2 per program, V3 per benchmark, analyzer identity |")
    P("| `plots/` | preliminary SPEC-only violins, one per headline metric: footprint, unique branches, and the three target metrics (literal, weff, ge1pct) for all / noret / indirect (`plot_frontend_footprint.py`) |\n")

    P("## `frontend_footprint_rows_long.csv`\n")
    P("Columns: `" + ",".join(LONG_COLS) + "`. `family`/`subgroup` as in `workload_index.csv`. `analyzer_sha` "
      "= the analyzer commit. `period` = sampling period. An empty `value` = undefined (no branch of that "
      "kind was sampled). The `weff_targets_*` and `wavg_targets_ge1pct_*` rows exist only when the analyzer "
      "emitted them (older summaries lack them). The Server and Agentic CSVs use the same metric names, so "
      "one plotting script reads all three. Bytes are B; KB in the text and plots = 1000 B.\n")
    P("| Metric | Definition |\n|---|---|")
    for m, doc in METRIC_DOCS:
        P(f"| `{m}` | {doc} |")
    P("\nAll unique counts are sampled lower bounds (above). Canonical addresses: file-backed code is keyed "
      "by (path, inode) + file offset, so a shared library counts once across processes; kernel by "
      "address; anonymous/JIT code by (pid, address).\n")

    P("## `gates.csv`\n")
    P("Booleans are 1/0; empty = not available.\n")
    P("| Column | Meaning |\n|---|---|")
    done = set()
    for col, doc in GATE_DOCS:  # the per-metric families are documented once, as a pattern
        for pre, pat, d in (("conv_growth_pct_", "conv_growth_pct_<m>", "100 x (m at 100 % of the samples - m at 75 %) / m at 100 %"),
                            ("conv_", "conv_<m>", f"sampling_limited if conv_growth_pct_<m> > {a.conv_threshold:g}, else converged"),
                            ("v3_ratio_", "v3_ratio_<m>", "m at period 5003 / m at period 20011")):
            if col.startswith(pre):
                if pat not in done:
                    done.add(pat)
                    ms = UNIQUE if pre.startswith("conv") else V3_METRICS
                    P(f"| `{pat}` | {d}; m in " + ", ".join(f"`{x}`" for x in ms) + " |")
                break
        else:
            P(f"| `{col}` | {doc} |")
    P("\n## `gates_global.csv`\n")
    P("Columns: `" + ",".join(GLOBAL_COLS) + "`. Gates: `V1` (synthetic truth), `V1_defect` (the failed "
      "contract-v1 run, kept as the record of the defect), `V2` (one name per program: recall, precision, "
      "PT and LBR set sizes, relative error of the literal, weff and ge1pct target metrics and of the literal "
      "metric with LBR's C_b and PT's T_b (`*_rel_err_lbr_C_pt_T`), recall at 25/50/75 % of the LBR samples; "
      "the contract sets no pass threshold, so the verdict is REPORTED unless the PT reference is invalid), "
      "`V3` (ratios per benchmark), `analyzer` (SHA identity), `August` (the NO_PROOF gate and its substitutes). "
      "`pending` = input absent.\n")

    P("## Regenerate\n")
    P("```bash")
    P(f"python3 local_agents/kit/frontend_footprint/aggregate.py {A['cmdline']}")
    P("~/miniforge3/envs/infersuite-full/bin/python3 local_agents/kit/frontend_footprint/plot_frontend_footprint.py \\")
    P(f"    {tilde(os.path.join(a.out, 'frontend_footprint_rows_long.csv'))} --out {tilde(os.path.join(a.out, 'plots'))}")
    P("```")
    return "\n".join(L) + "\n"


# ---- main ------------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data-root", default=os.path.join(INFRA, "data_frontend_footprint"))
    ap.add_argument("--family", default="spec26")
    ap.add_argument("--index-csv", default=os.path.join(REPO, "local_agents/RealData/data/l3_study/workload_index.csv"))
    ap.add_argument("--out", default=os.path.join(REPO, "spec26/frontend_footprint_x86"))
    ap.add_argument("--v1-dir", default=os.path.join(VALID, "v1"))
    ap.add_argument("--v1-defect-dir", default=os.path.join(VALID, "v1_contract_v1_bare_event"))
    ap.add_argument("--v2-dir", default=os.path.join(VALID, "v2"))
    ap.add_argument("--v2-names", default=",".join(V2_NAMES))
    ap.add_argument("--v3-root", default=os.path.join(INFRA, "data_frontend_footprint_c5003"))
    ap.add_argument("--v3-benchmarks", default=",".join(V3_BENCHES))
    ap.add_argument("--v3-period", type=int, default=5003)
    ap.add_argument("--august-dir", default=os.path.join(REPO, "spec26/infra_kit/x86_results"))
    ap.add_argument("--expect", nargs="+", help="expected workloads (space or comma separated); "
                    "default: every --family row of --index-csv")
    ap.add_argument("--no-proof", default=",".join(NO_PROOF),
                    help="benchmarks whose SPEC output cannot be verified (flagged even when missing)")
    ap.add_argument("--event", default=CONTRACT_EVENT)
    ap.add_argument("--period", type=int, default=CONTRACT_PERIOD)
    ap.add_argument("--conv-threshold", type=float, default=2.0, help="sampling_limited above this %% growth")
    ap.add_argument("--wall-tol", type=float, default=10.0, help="wall time vs August tolerance, %%")
    a = ap.parse_args()
    for k in PATH_ARGS:
        v = getattr(a, k)
        setattr(a, k, os.path.abspath(os.path.expanduser(v)) if v else v)

    sub, index_order = read_index(a.index_csv, a.family)
    expect = [w for x in a.expect for w in x.split(",") if w] if a.expect else index_order
    no_proof = {w for w in a.no_proof.split(",") if w}

    eps, cont, root_ok = scan_root(a.data_root)
    if not root_ok:
        warn(f"data root {a.data_root} does not exist: every expected workload is missing")
    E = {w: evaluate(w, d, a.event, a.period) for w, d in eps.items()}
    v3_bench = [w for w in a.v3_benchmarks.split(",") if w]
    v3eps, v3cont, _ = scan_root(a.v3_root)
    V3E = {w: evaluate(w, d, a.event, a.v3_period) for w, d in v3eps.items()}
    v3_set = list(dict.fromkeys(v3_bench + sorted(v3eps)))

    # one analyzer SHA across everything that is aggregated (main and V3)
    shas = {}
    for tag, D in (("main", E), ("V3", V3E)):
        for w, ep in D.items():
            if ep["status"] == "ok":
                shas.setdefault(ep["s"].get("analyzer_sha"), []).append(f"{tag}:{w}")
    if len(shas) > 1:
        print("aggregate: ERROR the aggregated episodes carry more than one analyzer SHA:", file=sys.stderr)
        for k, v in shas.items():
            print(f"  {k!r}: {', '.join(v)}", file=sys.stderr)
        print("aggregate: nothing written; re-analyze with one analyzer commit", file=sys.stderr)
        return 2
    sha = next(iter(shas), None)
    if sha in ("uncommitted", "test", "", None) and shas:
        warn(f"analyzer_sha is {sha!r}, not a commit")

    workloads = sorted(set(expect) | set(E) | set(cont))
    gates, long_rows, why = [], [], {}
    events, periods, cpus, perfv, srcs, labels = set(), set(), set(), set(), set(), set()
    v1_event_seen, has_comp = [], {}
    for w in workloads:
        base = w.split("@")[0]
        ep = E.get(w)
        s = ep["s"] if ep else {}
        status = ep["status"] if ep else "missing"
        if ep and ep.get("why"):
            why[w] = ep["why"]
        g = s.get("gates_v4") or {}
        cap = s.get("capture") or {}
        ff = cap.get("frontend_footprint") or {}
        ex = s.get("exact_counts") or {}
        if ep and ep.get("event") == "br_inst_retired.near_taken":
            v1_event_seen.append(w)
        r = {c: None for c in GATE_COLS}
        r.update(workload=w, family=a.family, subgroup=sub.get(base, ""), expected=w in expect, status=status,
                 in_long_csv=status == "ok", contaminated_attempts=cont.get(w, 0), _s=s)
        if not sub.get(base) and w in E:
            warn(f"{w}: no {a.family} row in {a.index_csv}; subgroup left empty")
        if ep and s:
            oc = cap.get("output_check")
            wit = cap.get("foreign_witness") or g.get("witness")
            r.update(analyzer_sha=s.get("analyzer_sha"), period=ep["period"], event=ep["event"],
                     contract_ok=ep["contract_ok"], exit_status=cap.get("bench_exit_status"),
                     output_check=(oc or {}).get("status") if isinstance(oc, dict) else g.get("output_check"),
                     output_ok=g.get("output_ok"), lost_pct=num(g.get("lost_pct")), lost_ok=g.get("lost_ok"),
                     sample_coverage=num(g.get("sample_coverage")), coverage_ok=g.get("coverage_ok"),
                     throttle_events=g.get("throttle_events"), throttle_ok=g.get("throttle_ok"),
                     mean_cores=num(g.get("mean_cores")), occupancy_ok=g.get("occupancy_ok"),
                     witness_rows=get(wit, "witness_rows"), witness_foreign_rows=get(wit, "rows_with_foreign_task"),
                     witness_mean_foreign_cpu_pct=get(wit, "mean_foreign_cpu_pct"), witness_clean=witness_clean(wit),
                     iso_proof_present=bool(cap.get("iso_proof") or g.get("iso_proof")),
                     analyzer_ok=g.get("analyzer_ok", "error" not in s), v4_all_ok=g.get("all_ok"))
            for m, (gr, verdict) in convergence(s, a.conv_threshold).items():
                r[f"conv_growth_pct_{m}"], r[f"conv_{m}"] = gr, verdict
            r["sampling_limited"] = ";".join(m for m in UNIQUE if r[f"conv_{m}"] == "sampling_limited")
            r.update(wrapper_share(s, ep["dir"]))
            r["wall_s"] = num(cap.get("wall_s"))
            r["instructions"], r["cycles"] = num(ex.get("instructions")), num(ex.get("cycles"))
            r["ipc"] = ratio(r["instructions"], r["cycles"])
        aug = august(a.august_dir, base) if "@" not in w else {}
        if aug:
            r["aug_wall_s"], r["aug_ipc"] = aug.get("wall_s"), aug.get("ipc")
            if r["wall_s"] is not None and aug.get("wall_s"):
                r["wall_dev_pct"] = 100.0 * (r["wall_s"] / aug["wall_s"] - 1)
                r["wall_within_10pct"] = abs(r["wall_dev_pct"]) <= a.wall_tol
            if aug.get("instr") and aug.get("seconds") and aug.get("wall_s"):
                r["aug_instructions_extrap"] = aug["instr"] * aug["wall_s"] / aug["seconds"]
            r["instr_ratio_extrap"] = ratio(r["instructions"], r["aug_instructions_extrap"])
            r["ipc_ratio"] = ratio(r["ipc"], r["aug_ipc"])
        r["output_unverifiable"] = base in no_proof or r["output_check"] == "unavailable"
        r["aug_instr_1pct_gate"] = "NO_PROOF" if r["output_unverifiable"] else "not_required"
        if w in v3_set:
            v = V3E.get(w)
            r["v3_status"] = v["status"] if v else "missing"
            r["v3_contaminated_attempts"] = v3cont.get(w, 0)
            if v and v["status"] == "ok" and status == "ok":
                for m in V3_METRICS:
                    r[f"v3_ratio_{m}"] = ratio(v["s"].get(m), s.get(m))
        gates.append(r)
        if status == "ok":
            for bag, v in ((events, ep["event"]), (periods, ep["period"]), (cpus, cap.get("cpus_measured")),
                           (perfv, ff.get("perf_version")), (srcs, s.get("analyzer_src_sha256")),
                           (labels, ff.get("contract"))):
                if v:
                    bag.add(v)
            bt = get(s, "unique_taken_branches_by_type", "all") or {}
            vals = {m: s.get(m) for m in UNIQUE + WAVG}
            vals.update({m: s[m] for m in COMPANIONS if m in s})
            has_comp[w] = any(m in s for m in COMPANIONS)
            vals.update({f"unique_taken_branches_{t}": bt.get(t, 0) for t in TYPES})
            for t in sorted(set(bt) - set(TYPES)):  # e.g. PT-only types; never expected in LBR data
                vals[f"unique_taken_branches_{t}"] = bt[t]
            for m in [m for m in METRICS if m in vals] + sorted(set(vals) - set(METRICS)):
                v = vals.get(m)
                v = v if isinstance(v, (int, float)) and not isinstance(v, bool) else num(v)
                long_rows.append([w, a.family, r["subgroup"], m, fmt(v), s.get("analyzer_sha") or "", fmt(ep["period"])])
    for w, v in V3E.items():
        if v["status"] == "ok" and v["s"].get("analyzer_src_sha256"):
            srcs.add(v["s"]["analyzer_src_sha256"])
    if len(srcs) > 1:
        warn(f"several analyzer source sha256 under one analyzer SHA: {sorted(srcs)}")
    comp_state = ("nodata" if not has_comp else "all" if all(has_comp.values()) else
                  "none" if not any(has_comp.values()) else "some")
    if comp_state == "some":
        warn("the companion metrics (weff_*, wavg_targets_ge1pct_*) are in some summaries only: "
             + ", ".join(w for w, x in sorted(has_comp.items()) if not x) + " lack them")

    # ---- global gates ----
    glob = []
    v1r, v1c = v1_rows(a.v1_dir, "V1", "check_v1.json")
    glob += v1r
    v1d_rows, v1d = v1_rows(a.v1_defect_dir, "V1_defect", "check_v1.json (contract v1, bare event)")
    for row in v1d_rows:
        if row[5] in ("PASS", "FAIL"):
            row[5] = "DEFECT_FIXED_IN_v1.1" if row[5] == "FAIL" else "unaffected"
    glob += v1d_rows
    v1_src = get(load_json(os.path.join(a.v1_dir, "summary.json")) or {}, "analyzer_src_sha256")
    v1_src_note = ("same source as production" if v1_src and v1_src in srcs else
                   f"DIFFERENT from production (`{v1_src}`)" if v1_src and srcs else
                   f"`{v1_src}` (no production data to compare)" if v1_src else "unknown")
    glob.append(["analyzer", "production", "analyzer_sha", sha or "", "one SHA", "OK" if sha else "no data",
                 "summary.json of every aggregated episode (main + V3)"])
    glob.append(["analyzer", "production", "analyzer_src_sha256", ";".join(sorted(srcs)), "one value",
                 "OK" if len(srcs) == 1 else ("no data" if not srcs else "SEVERAL"), "summary.json"])
    glob.append(["analyzer", "V1", "analyzer_src_sha256", v1_src or "", "= production",
                 "same" if v1_src in srcs else ("n/a" if not v1_src or not srcs else "DIFFERENT"), "v1/summary.json"])
    v2 = v2_load(a.v2_dir, [n for n in a.v2_names.split(",") if n])
    glob += v2_rows(v2)
    for n, c in v2.items():
        lsum = load_json(os.path.join(a.v2_dir, n, "lbr", "summary.json")) if c else None
        x = get(lsum or {}, "analyzer_src_sha256")
        if x:
            glob.append(["analyzer", n, "analyzer_src_sha256", x, "= production",
                         "same" if x in srcs else ("n/a" if not srcs else "DIFFERENT"), f"v2/{n}/lbr/summary.json"])
    v3_tab = []
    for w in v3_set:
        r = next((g for g in gates if g["workload"] == w), None)
        st = r["v3_status"] if r else ("missing" if w not in V3E else V3E[w]["status"])
        if r and r["status"] != "ok" and st == "ok":
            st = f"ok (20011 run: {r['status']})"
        rat = {m: r[f"v3_ratio_{m}"] for m in V3_METRICS} if r else {}
        v3_tab.append((w, st, rat))
        if not any(v is not None for v in rat.values()):
            glob.append(["V3", w, "ratio", "", "", "pending" if "ok" not in st else st, f"{tilde(a.v3_root)} ({st})"])
        for m in V3_METRICS:
            if rat.get(m) is not None:
                glob.append(["V3", w, f"ratio_{m}", rat[m], "", "REPORTED", f"period {a.v3_period} / {a.period}"])
    for r in gates:
        if r["output_unverifiable"]:
            glob.append(["August", r["workload"], "instructions_within_1pct", "", "1 %", "NO_PROOF",
                         "August has no whole-run instruction total"])
            rep = lambda v: "REPORTED" if v is not None else f"pending ({r['status']})"
            glob.append(["August", r["workload"], "substitute_a_instr_ratio_extrap", r["instr_ratio_extrap"], "",
                         rep(r["instr_ratio_extrap"]), "instructions / (August raw instructions x wall_s / seconds)"])
            glob.append(["August", r["workload"], "substitute_b_ipc_ratio", r["ipc_ratio"], "",
                         rep(r["ipc_ratio"]), "(instructions / cycles) / August IPC"])

    # ---- convergence summary ----
    ok_rows = [r for r in gates if r["status"] == "ok"]
    conv_summary = {}
    for m in UNIQUE:
        vals = [(r[f"conv_growth_pct_{m}"], r["workload"]) for r in ok_rows if r[f"conv_growth_pct_{m}"] is not None]
        n_lim = sum(1 for r in ok_rows if r[f"conv_{m}"] == "sampling_limited")
        desc = (f"median {statistics.median(v for v, _ in vals):.2f} %, max {max(vals)[0]:.2f} % ({max(vals)[1]})"
                if vals else "n/a")
        conv_summary[m] = {"n": len(vals), "n_lim": n_lim, "desc": desc}
    by_sub = {}
    for r in ok_rows:
        by_sub[r["subgroup"] or "?"] = by_sub.get(r["subgroup"] or "?", 0) + 1

    # ---- write ----
    os.makedirs(os.path.join(a.out, "per_benchmark"), exist_ok=True)
    keep = set()
    for r in ok_rows:
        dst = os.path.join(a.out, "per_benchmark", f"{r['workload']}.summary.json")
        shutil.copyfile(os.path.join(E[r["workload"]]["dir"], "summary.json"), dst)
        keep.add(os.path.basename(dst))
    for f in os.listdir(os.path.join(a.out, "per_benchmark")):
        if f.endswith(".summary.json") and f not in keep:
            os.remove(os.path.join(a.out, "per_benchmark", f))
    with open(os.path.join(a.out, "frontend_footprint_rows_long.csv"), "w", newline="") as f:
        cw = csv.writer(f, lineterminator="\n")
        cw.writerow(LONG_COLS)
        cw.writerows(long_rows)
    with open(os.path.join(a.out, "gates.csv"), "w", newline="") as f:
        cw = csv.writer(f, lineterminator="\n")
        cw.writerow(GATE_COLS)
        for r in gates:
            cw.writerow([fmt(r[c]) for c in GATE_COLS])
    with open(os.path.join(a.out, "gates_global.csv"), "w", newline="") as f:
        cw = csv.writer(f, lineterminator="\n")
        cw.writerow(GLOBAL_COLS)
        for row in glob:
            cw.writerow([fmt(x) if not isinstance(x, str) else x for x in row])
    cmd = []  # the regenerate command: every flag that differs from its default
    for act in ap._actions:
        if act.dest in ("help", "expect"):
            continue
        v, d = getattr(a, act.dest), act.default
        if isinstance(d, str) and d and act.dest in PATH_ARGS:
            d = os.path.abspath(os.path.expanduser(d))
        if v != d:
            cmd.append(f"{act.option_strings[0]} {tilde(v)}")
    if a.expect:
        cmd.append("--expect " + " ".join(expect))
    A = {"args": a, "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
         "gates": gates, "why": why, "by_sub": by_sub, "events": events, "periods": periods, "cpus": cpus,
         "perfv": perfv, "src": srcs, "sha": sha, "stale_label": any(l.rstrip().endswith(" v1") for l in labels)
         and CONTRACT_EVENT in events, "v2": v2, "v3": v3_tab, "v1": v1c, "v1_defect": v1d,
         "v1_src_note": v1_src_note, "v1_event_seen": v1_event_seen, "conv_summary": conv_summary,
         "comp_state": comp_state,
         "cmdline": " ".join(cmd)}
    with open(os.path.join(a.out, "MANIFEST.md"), "w") as f:
        f.write(manifest(A))

    # ---- console summary ----
    cnt = {}
    for r in gates:
        cnt[r["status"]] = cnt.get(r["status"], 0) + 1
    print(f"aggregate: {len(gates)} workloads: " + ", ".join(f"{k} {v}" for k, v in sorted(cnt.items())))
    for st in ("missing", "incomplete", "gate_failed", "contract_mismatch"):
        ws = [r["workload"] for r in gates if r["status"] == st]
        if ws:
            print(f"aggregate: {st}: " + ", ".join(w + (f" ({why[w]})" if why.get(w) else "") for w in ws))
    print(f"aggregate: contaminated attempts (excluded): {sum(cont.values())} "
          + (str(dict(sorted(cont.items()))) if cont else ""))
    lim = [r["workload"] for r in ok_rows if r["conv_unique_taken_branches"] == "sampling_limited"]
    print(f"aggregate: unique_taken_branches sampling_limited on {len(lim)} of {len(ok_rows)}" + (f": {', '.join(lim)}" if lim else ""))
    print(f"aggregate: analyzer_sha {sha!r}; V1 {'PASS' if v1c and v1c.get('pass') else 'FAIL' if v1c else 'pending'}; "
          f"V2 " + ", ".join(f"{n} {'ok' if c else 'pending'}" for n, c in v2.items()) + "; V3 "
          + ", ".join(f"{w} {st}" for w, st, _ in v3_tab))
    print(f"aggregate: wrote {a.out}/ (per_benchmark/ {len(keep)} summaries, {len(long_rows)} long rows, "
          f"gates.csv {len(gates)} rows, gates_global.csv {len(glob)} rows, MANIFEST.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
