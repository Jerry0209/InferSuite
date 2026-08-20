#!/usr/bin/env python3
"""typeid_procconn_check.py — cross-check the COUNT-weighted column against kernel truth.

The count column in cpu_matrix.tsv is built from exit receipts, which do not say whether a
task is a process or a thread; typeid_cpu_matrix.py guesses from the name shape (THREADISH).
Replays run with TYPEID_PROCCONN=1 also bank procconn.tsv, where the kernel states it outright:
a FORK event carries child_pid AND child_tgid, and `child_pid != child_tgid` IS a thread.

This script joins the two per episode and reports, for every replay dir that has both files:

  * how many counted "leaf commands" the kernel says were threads   (heuristic false negatives)
  * how many excluded receipts the kernel says were processes       (heuristic false positives)
  * the count-weighted label under the heuristic vs under kernel truth
  * an exec-based count (one EXEC event = one command, the literal definition) and its label

Usage: typeid_procconn_check.py [--data DIR]
"""
import collections
import csv
import glob
import importlib.util
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ML = f"{REPO}/local_agents/ML_typeid"
spec = importlib.util.spec_from_file_location("tcm", f"{REPO}/local_agents/kit/campaign/typeid_cpu_matrix.py")
tcm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tcm)
MARGIN = tcm.MARGIN


def label_of(counter, floor=20):
    n = sum(counter.values())
    if not n or n < floor:
        return "?", n
    sh = {k: 100 * v / n for k, v in counter.items()}
    o = sorted(sh, key=sh.get, reverse=True)
    if len(o) == 1 or sh[o[0]] - sh[o[1]] >= MARGIN:
        return o[0][0], n
    return "M", n


def analyze(rd):
    # --- kernel truth from the proc connector -------------------------------------------
    is_thread, execs = {}, collections.Counter()
    lost = 0
    for ln in open(f"{rd}/procconn.tsv", errors="replace"):
        f = ln.rstrip("\n").split("\t")
        if len(f) < 4:
            continue
        if f[1] == "FORK":
            is_thread[int(f[2])] = f[2] != f[3]          # child_pid != child_tgid
        elif f[1] == "EXEC":
            execs[int(f[2])] += 1
        elif f[1] == "LOST":
            lost += 1

    # --- receipts, same filtering as typeid_cpu_matrix.py -------------------------------
    roots, argvmap = set(), {}
    for fn in ("cmdlog.tsv", "pidcpu.tsv"):
        for ln in open(f"{rd}/{fn}", errors="replace"):
            f = ln.rstrip("\n").split("\t")
            if len(f) > 1 and f[1].strip().isdigit():
                roots.add(int(f[1]))
                if fn == "cmdlog.tsv" and len(f) > 2:
                    argvmap[int(f[1])] = f[2]
    rec, seen = [], set()
    for ln in open(f"{rd}/taskstats.tsv", errors="replace"):
        f = ln.rstrip("\n").split("\t")
        if len(f) >= 10 and f[1] == "P":
            key = (f[2], f[9])
            if key in seen:
                continue
            seen.add(key)
            rec.append((int(f[2]), int(f[3]), f[5]))
    parent = {p: pp for p, pp, _ in rec}
    kids = set(parent.values())
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

    heur, kern, exec_cnt = collections.Counter(), collections.Counter(), collections.Counter()
    fn_thread = 0        # counted by the heuristic, but the kernel says thread
    fp_proc = 0          # dropped by the heuristic, but the kernel says process
    unknown = 0          # no FORK event seen (started before the listener, or lost)
    for p, pp, comm in rec:
        if not infence(p):
            continue
        cls = tcm.COARSE.get(tcm.tag_of(comm) or "")
        if not cls or p in kids:
            continue
        heuristic_says_thread = bool(tcm.THREADISH.search(comm.strip()))
        kt = is_thread.get(p)
        if kt is None:
            unknown += 1
        if not heuristic_says_thread:
            heur[cls] += 1
            if kt is True:
                fn_thread += 1
        elif kt is False:
            fp_proc += 1
        if kt is False or (kt is None and not heuristic_says_thread):
            kern[cls] += 1          # kernel-confirmed process (unknowns keep the heuristic)
        if execs.get(p):
            exec_cnt[cls] += execs[p]

    lab_h, n_h = label_of(heur)
    lab_k, n_k = label_of(kern)
    lab_e, n_e = label_of(exec_cnt)
    return dict(n_heur=n_h, label_heur=lab_h, n_kernel=n_k, label_kernel=lab_k,
                n_exec=n_e, label_exec=lab_e, threads_counted=fn_thread,
                procs_dropped=fp_proc, unknown=unknown, procconn_lost=lost)


def main():
    data = f"{ML}/data"
    if "--data" in sys.argv:
        data = sys.argv[sys.argv.index("--data") + 1]
    mat = {r["short"]: r for r in csv.DictReader(open(f"{ML}/cpu_matrix.tsv"), delimiter="\t")}
    rows = []
    for rd in sorted(glob.glob(f"{data}/glm_replay_swe_*/run_1")):
        if not (os.path.exists(f"{rd}/procconn.tsv") and os.path.exists(f"{rd}/taskstats.tsv")):
            continue
        short = os.path.basename(os.path.dirname(rd)).replace("glm_replay_swe_", "")
        try:
            a = analyze(rd)
        except OSError as e:
            print(f"{short}: {e}", file=sys.stderr)
            continue
        a["short"] = short
        a["language"] = mat.get(short, {}).get("language", "?")
        rows.append(a)
    if not rows:
        sys.exit("no replay dir has both procconn.tsv and taskstats.tsv "
                 "(run a replay with TYPEID_PROCCONN=1)")

    print(f"{'episode':<26}{'lang':<12}{'heur':>7}{'kernel':>8}{'exec':>8}   "
          f"{'labels h/k/e':<14}{'thr counted':>12}{'proc dropped':>13}")
    agree_k = agree_e = comparable = 0
    for r in sorted(rows, key=lambda r: r["short"]):
        print(f"{r['short']:<26}{r['language']:<12}{r['n_heur']:>7,}{r['n_kernel']:>8,}"
              f"{r['n_exec']:>8,}   {r['label_heur']}/{r['label_kernel']}/{r['label_exec']:<10}"
              f"{r['threads_counted']:>12,}{r['procs_dropped']:>13,}")
        if r["label_heur"] != "?" and r["label_kernel"] != "?":
            comparable += 1
            agree_k += r["label_heur"] == r["label_kernel"]
            agree_e += r["label_heur"] == r["label_exec"]
    tot_h = sum(r["n_heur"] for r in rows)
    tot_thr = sum(r["threads_counted"] for r in rows)
    tot_drop = sum(r["procs_dropped"] for r in rows)
    print(f"\nepisodes cross-checked: {len(rows)}   comparable rows: {comparable}")
    print(f"heuristic vs kernel: labels agree {agree_k}/{comparable}")
    print(f"heuristic vs exec-count: labels agree {agree_e}/{comparable}")
    print(f"counted commands that were really threads: {tot_thr:,} / {tot_h:,} "
          f"({100 * tot_thr / max(tot_h, 1):.2f}%)")
    print(f"real processes wrongly dropped as threads: {tot_drop:,}")
    print(f"receipts with no FORK event (listener started later / lost): "
          f"{sum(r['unknown'] for r in rows):,}")
    out = f"{ML}/procconn_check.tsv"
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter="\t")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
