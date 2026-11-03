#!/usr/bin/env python3
"""compare_v2.py — gate V2 of the front-end footprint contract: LBR estimate vs exact Intel PT.

Both directories hold the analyzer's tables (objects.tsv, lines.tsv, edges.tsv; plain or .zst)
and summary.json, from two separate executions of the same deterministic command. Canonical
keys — (path, inode) + file offset, [vdso] by name — do not depend on ASLR, so they match
across the runs; anonymous (JIT) code is keyed by pid and cannot match, so it is reported
separately. PT is user-only, so everything here is restricted to user objects.

Reports, recomputed from the tables:
  recall    = |LBR ∩ PT| / |PT|   for footprint lines and for unique taken branches (and edges)
  precision = |LBR ∩ PT| / |LBR|  should be ~1; anything else points at a canonicalization bug
                                  (or at a run that did not execute the same code)
  rel. error of wavg_targets_all / _noret / _indirect (LBR vs PT), each over user branches, for
            the literal metric (distinct targets T_b, a sampled lower bound) and its two
            frequency-weighted companions: weff_targets_* (inverse Simpson effective targets)
            and wavg_targets_ge1pct_* (targets with >= 1 % of the branch's executions)
  recall at 25/50/75/100 % of the LBR samples (from the first_seen column)

  compare_v2.py --pt DIR --lbr DIR [--name NAME] [--json out.json]
"""
import argparse
import collections
import json
import os
import subprocess
import sys

NEAR = {"COND", "UNCOND", "CALL", "IND_CALL", "IND", "RET", "JMP_UNK", "CALL_UNK"}
INDIRECT = {"IND", "IND_CALL"}


def rows(d, name):
    """Rows of a TSV table (header skipped), reading <name> or <name>.zst."""
    p = os.path.join(d, name)
    if os.path.exists(p):
        with open(p) as f:
            next(f, None)
            for ln in f:
                yield ln.rstrip("\n").split("\t")
        return
    if not os.path.exists(p + ".zst"):
        sys.exit(f"compare_v2: missing {p}[.zst]")
    proc = subprocess.Popen(["zstd", "-dc", p + ".zst"], stdout=subprocess.PIPE, text=True)
    next(proc.stdout, None)
    for ln in proc.stdout:
        yield ln.rstrip("\n").split("\t")
    proc.wait()


def load(d):
    ident = {}
    for o in rows(d, "objects.tsv"):
        oid, kind, path, inode, pid = int(o[0]), o[1], o[2], o[3], o[4]
        if kind == "file":
            ident[oid] = ("file", path, inode)
        elif kind == "special":
            ident[oid] = ("special", path)
        elif kind == "kernel":
            ident[oid] = ("kernel",)
        else:
            ident[oid] = ("anon", d, pid, oid)  # never equal across runs, by design
    lines = {}
    for r in rows(d, "lines.tsv"):
        lines[(ident[int(r[0])], int(r[1], 16))] = int(r[2])
    br = collections.defaultdict(lambda: [0, {}, None, 1 << 62])  # C, {target: count}, type, first_seen
    edges = set()
    for r in rows(d, "edges.tsv"):
        if r[4] not in NEAR:
            continue
        f = (ident[int(r[0])], int(r[1], 16))
        t = (ident[int(r[2])], int(r[3], 16))
        b = br[f]
        b[0] += int(r[5])
        b[1][t] = b[1].get(t, 0) + int(r[5])
        b[2] = r[4]
        b[3] = min(b[3], int(r[6]))
        edges.add((f, t))
    summ = {}
    for name in ("summary.json", "analyzer.json"):
        p = os.path.join(d, name)
        if os.path.exists(p):
            summ = json.load(open(p))
            break
    return lines, dict(br), edges, summ


def is_user(key):
    return key[0][0] != "kernel"


def matchable(key):
    return key[0][0] in ("file", "special")


def eff_targets(tc, exact):
    """Inverse Simpson effective number of targets 1 / sum p_t^2 of one branch, from its
    per-target counts: plug-in sum (n_t/n)^2 for exact counts (PT), the unbiased
    sum n_t(n_t-1) / (n(n-1)) for samples (LBR); 1 if n = 1; capped at the distinct count
    (which also covers an estimate of 0: every target seen once). Same rule as the analyzer."""
    n, T = sum(tc.values()), len(tc)
    if n <= 1:
        return 1.0
    if exact:
        sp2 = sum(c * c for c in tc.values()) / (n * n)
    else:
        sp2 = sum(c * (c - 1) for c in tc.values()) / (n * (n - 1))
    return min(1 / sp2, T) if sp2 > 0 else float(T)


def ge1pct_targets(tc):
    """Targets carrying >= 1 % of the branch's executions (at least 1)."""
    n = sum(tc.values())
    return max(1, sum(1 for c in tc.values() if 100 * c >= n))


def wavg(br, keys, types=None, exclude=None, per=lambda b: len(b[1])):
    """sum C_b * per(b) / sum C_b; per = distinct targets T_b (the literal metric) by default."""
    c = ct = 0
    for k in keys:
        b = br[k]
        if types is not None and b[2] not in types:
            continue
        if exclude is not None and b[2] in exclude:
            continue
        c += b[0]
        ct += b[0] * per(b)
    return ct / c if c else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pt", required=True)
    ap.add_argument("--lbr", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--json")
    a = ap.parse_args()
    pl, pb, pe, ps = load(a.pt)
    ll, lb, le, ls = load(a.lbr)

    # user space only (PT is /u); the main numbers use the matchable (file/special) objects
    P_lines = {k for k in pl if matchable(k)}
    L_lines = {k for k in ll if matchable(k)}
    P_br = {k for k in pb if matchable(k)}
    L_br = {k for k in lb if matchable(k)}
    P_ed = {e for e in pe if matchable(e[0])}
    L_ed = {e for e in le if matchable(e[0])}
    anon = {"pt_lines": sum(1 for k in pl if k[0][0] == "anon"), "lbr_lines": sum(1 for k in ll if k[0][0] == "anon"),
            "pt_branches": sum(1 for k in pb if k[0][0] == "anon"), "lbr_branches": sum(1 for k in lb if k[0][0] == "anon")}
    kernel_in_pt = sum(1 for k in pl if not is_user(k))

    def rp(P, L):
        i = len(P & L)
        return {"pt": len(P), "lbr": len(L), "both": i, "recall": i / len(P) if P else None,
                "precision": i / len(L) if L else None}

    # PT cannot say direct vs indirect by itself; the analyzer decodes the branch bytes from the
    # object files. Any site it could not decode borrows the LBR type of the same site.
    unk = [k for k in P_br if pb[k][2] in ("JMP_UNK", "CALL_UNK")]
    borrowed = 0
    for k in unk:
        if k in lb:
            pb[k][2] = lb[k][2]
            borrowed += 1

    # three families x three classes; the literal keys (wavg_targets_{all,noret,indirect}) are
    # unchanged, the companions sit beside them
    W = {}
    families = (("wavg_targets_", lambda b: len(b[1]), lambda b: len(b[1])),
                ("weff_targets_", lambda b: eff_targets(b[1], True), lambda b: eff_targets(b[1], False)),
                ("wavg_targets_ge1pct_", lambda b: ge1pct_targets(b[1]), lambda b: ge1pct_targets(b[1])))
    for prefix, per_pt, per_lbr in families:
        for cls, kw in (("all", {}), ("noret", {"exclude": {"RET"}}), ("indirect", {"types": INDIRECT})):
            wp, wl = wavg(pb, P_br, per=per_pt, **kw), wavg(lb, L_br, per=per_lbr, **kw)
            W[prefix + cls] = {"pt": wp, "lbr": wl, "rel_err": (wl - wp) / wp if (wp and wl is not None) else None}
    # Where the literal metric's error comes from: LBR's sampled C_b with PT's exact T_b, over the
    # LBR branches PT also saw. Close to PT means C_b is estimated well and the gap is T_b, a
    # rare-event unique count (v2_python: +0.5 % here vs -61 % for the literal metric).
    for cls, kw in (("all", {}), ("noret", {"exclude": {"RET"}}), ("indirect", {"types": INDIRECT})):
        c = ct = 0
        for k in L_br & P_br:
            t = lb[k][2]
            if ("types" in kw and t not in kw["types"]) or ("exclude" in kw and t in kw["exclude"]):
                continue
            c += lb[k][0]
            ct += lb[k][0] * len(pb[k][1])
        h, wp = (ct / c if c else None), W["wavg_targets_" + cls]["pt"]
        W["wavg_targets_" + cls]["hybrid_lbr_C_pt_T"] = {
            "value": h, "rel_err": (h - wp) / wp if (h is not None and wp) else None}

    # recall vs LBR sampling depth, from first_seen
    n_lbr = (ls.get("diagnostics") or {}).get("samples") or max([v for v in ll.values()] + [1])
    conv = []
    for q in (25, 50, 75, 100):
        cut = -(-n_lbr * q // 100)
        li = sum(1 for k in L_lines if ll[k] <= cut and k in P_lines)
        bi = sum(1 for k in L_br if lb[k][3] <= cut and k in P_br)
        conv.append({"pct": q, "samples": cut, "footprint_recall": li / len(P_lines) if P_lines else None,
                     "branch_recall": bi / len(P_br) if P_br else None})

    # where the misses and the precision losses are, per object
    per_obj = collections.defaultdict(lambda: [0, 0, 0, 0])  # pt lines, both, lbr-only lines, pt branches
    for k in P_lines:
        per_obj[k[0]][0] += 1
        if k in L_lines:
            per_obj[k[0]][1] += 1
    for k in L_lines - P_lines:
        per_obj[k[0]][2] += 1
    for k in P_br:
        per_obj[k[0]][3] += 1
    objs = sorted(per_obj.items(), key=lambda kv: -kv[1][0])[:15]

    # Process attribution check: with tsc=0 perf records no context-switch sideband, so a per-CPU
    # PT buffer shared by several processes (a shell and its child, g++ -> cc1plus -> as) is
    # decoded as ONE thread. Every process the LBR run saw (>= 1 % of samples) must also show
    # up in the PT run; if not, the PT reference is not valid for this command.
    procs = lambda s: [(p.get("comm"), p.get("share")) for p in s.get("top_processes", [])]
    sig = lambda s: {c for c, sh in procs(s) if sh and sh >= 0.01}
    missing = sorted(sig(ls) - sig(ps))
    res = {
        "gate": "V2", "name": a.name,
        "processes": {"pt": procs(ps), "lbr": procs(ls), "lbr_processes_missing_in_pt": missing,
                      "pt_attribution_ok": not missing},
        "footprint_lines": rp(P_lines, L_lines),
        "unique_taken_branches": rp(P_br, L_br),
        "edges": rp(P_ed, L_ed),
        "wavg": W,
        "lbr_lower_bound_ratio": {"footprint": len(L_lines) / len(P_lines) if P_lines else None,
                                  "unique_taken_branches": len(L_br) / len(P_br) if P_br else None},
        "recall_vs_lbr_samples": conv,
        "unmatchable_anon": anon,
        "pt_kernel_lines": kernel_in_pt,
        "pt_jmp_call_unclassified": len(unk), "pt_types_borrowed_from_lbr": borrowed,
        "per_object": [{"object": "/".join(map(str, o[:2])), "pt_lines": v[0], "line_recall": v[1] / v[0] if v[0] else None,
                        "lbr_only_lines": v[2], "pt_branches": v[3]} for o, v in objs],
        "pt_diagnostics": {k: (ps.get("diagnostics") or {}).get(k) for k in
                           ("samples", "pt_trace_errors", "unparsed_lines", "unmapped_entries", "discontinuity_rate",
                            "pt_jmp_call_sites_classified", "pt_jmp_call_sites_unreadable",
                            "pt_jmp_call_sites_decode_mismatch")},
        "lbr_diagnostics": {k: (ls.get("diagnostics") or {}).get(k) for k in
                            ("samples", "entries", "lost_samples", "unparsed_lines", "unmapped_entries",
                             "discontinuity_rate")},
    }
    if a.json:
        json.dump(res, open(a.json, "w"), indent=1)
    f = lambda v, p=3: "n/a" if v is None else f"{v:.{p}f}"
    pc = lambda v: "n/a" if v is None else f"{100 * v:+.2f} %"
    fl, bl = res["footprint_lines"], res["unique_taken_branches"]
    print(f"V2 {a.name}: footprint recall {f(fl['recall'])} (prec {f(fl['precision'])}, PT {fl['pt']} lines / LBR {fl['lbr']}), "
          f"branches recall {f(bl['recall'])} (prec {f(bl['precision'])}, PT {bl['pt']} / LBR {bl['lbr']}), "
          "wavg err literal/weff/ge1pct: " + "; ".join(
              f"{c[:3] if c == 'indirect' else c} " + "/".join(pc(W[p + c]["rel_err"]) for p in
                                                             ("wavg_targets_", "weff_targets_", "wavg_targets_ge1pct_"))
              for c in ("all", "noret", "indirect"))
          + "; recall@25/50/75% "
          + "/".join(f(c["footprint_recall"], 2) for c in conv[:3]) + " (lines), "
          + "/".join(f(c["branch_recall"], 2) for c in conv[:3]) + " (branches)")
    if missing:
        print(f"V2 {a.name}: WARNING processes {missing} carry >= 1 % of the LBR samples but are absent from the PT "
              f"decode: PT did not separate the processes (tsc=0 has no switch sideband); rerun with "
              f"PT_EVENT='intel_pt/cyc=0,mtc=0,noretcomp=0/u' (TSC on)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
