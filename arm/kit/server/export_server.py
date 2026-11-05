#!/usr/bin/env python3
"""export_server.py — banked ARM Server-set passes -> CSVs (arm_server_profiling.md §4).

  export_server.py [--raw DIR] [--out ARM_DIR]
  export_server.py --selftest [--raw DRIVER_SELFTEST_RAW]

Input: run_server.sh's tree <raw>/<workload>/<family>/a<N>/ (perf.json, meta.json or
capture.json, receipts) and <raw>/<workload>/<family>/DONE naming the accepted attempt. A pass
is ACCEPTED when DONE names it and its meta.json says valid. Only accepted passes feed windows,
votes and receipts; every attempt gets a passes.csv row. No accepted pass -> nothing is written.

Per workload x metric (server_arm_votes.csv) two values:
  value            the WHOLE-RUNTIME rule of the x86 Server votes (local_agents/JVMbench/README.md
                   §9): "sum the raw counters over every window the workload was measured in, then
                   take the ratio once". As on x86 (export_runtime_votes.py: counters summed across
                   all runs, co-counted denominators), a metric's terms are summed over EVERY window
                   (no task-clock floor) of EVERY accepted pass that counted all of them. So IPC
                   (cpu_cycles + inst_retired are in every family) and context switches (environment
                   events) pool all the workload's passes, as x86 IPC pooled its eight runs; a
                   family-specific metric comes from the pass(es) that carried its events.
  mean_of_windows  Jef's vote, export.py's rule: windows < min_task_clock_ns dropped, the plan's
                   expr per window over its own family's pass, mean of those windows.
The Server figures use `value`, like the x86 Server violins. Formulas, window floor and perf
JSON parsing come from export.py / arm_profile.py (imported, not copied).
"""
import argparse
import csv
import gzip
import json
import shutil
import statistics
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import arm_profile  # noqa: E402
import export as spec  # noqa: E402  (write, evalx, CODE, pass_metrics, scan)

PLAN, M, parse = arm_profile.PLAN, arm_profile.M, arm_profile.parse
RAW = arm_profile.ARM / "data/raw/server"
# fig02 of the x86 realistic Server set; same blob (8093d3b) on origin/dcperf, origin/spec-x86 and
# dcperf-arm. Rows with side "Server:<suite>" carry the per-workload whole-runtime vote in `median`
# (= `mean`; min/max there are the window IQR) — plot_paper_agg_compact_server.R, VOTE=runtime.
X86_NUMBERS = arm_profile.REPO / "local_agents/JVMbench/plots/paper_v1/multi_server_compact_realistic_numbers.csv"
# plan `x86` key (extract_metrics name) -> its label in the x86 Server tables (export_runtime_votes.py
# METRICS). Plan keys absent here (tma.l1.*, itlb_walk_pct) have no x86 Server value.
X86_LABEL = {"IPC": "IPC", "brMPKI": "Branch MPKI", "branchDir_MPKI": "Branch-direction MPKI",
             "baclears_MPKI": "BTB MPKI (BAClears)", "L1I_MPKI": "L1I MPKI (code-read)",
             "L1D_MPKI": "L1D-load MPKI", "L2_MPKI": "L2-load MPKI", "LLC_MPKI": "LLC MPKI",
             "DRAM_read_GBs": "DRAM read (GB/s)", "ctx_per_cpu_s": "Context switches (/CPU-s)"}
# workload -> (suite, category). suite = x86 workload_index.csv `subgroup` (RealData pack v1), which
# is also the "Server:<suite>" side in X86_NUMBERS. category = the suite group in JVMbench README §1 /
# RealData README §0 (Renaissance web/apache-spark/database, DaCapo server); a RealData workload takes
# the category of the toy it replaces (workload_index `pairs_with`); FeedSim = DCPerf's "ranking /
# inference" (DCPerf README §1), video-4k = DCPerf VideoTranscodeBench.
WORKLOADS = {
    "tomcat": ("DaCapo", "server"),
    "feedsim": ("DCPerf", "ranking"),
    "finagle-chirper": ("Renaissance", "web"),
    "finagle-http": ("Renaissance", "web"),
    "cassandra-ycsb20m": ("RealData", "server"),           # DaCapo cassandra
    "kafka-20g": ("RealData", "server"),                   # DaCapo kafka
    "naivebayes-rcv1": ("RealData", "apache-spark"),       # Renaissance naive-bayes
    "neo4j-livejournal": ("RealData", "database"),         # Renaissance neo4j-analytics
    "pagerank-livejournal": ("RealData", "apache-spark"),  # Renaissance page-rank
    "video-4k": ("RealData", "video-transcode"),           # DCPerf video_transcode
}
RECEIPTS = ("*_receipt.json", "*_receipt.txt", "feedsim_results.txt", ".load_json", "iso.json")
MAX_COPY = 1 << 20                                         # never copy a file > 1 MB
NEEDS = {n: set(c.co_names) for n, c in spec.CODE.items()}
VOTE_H = ["suite", "category", "workload", "metric", "family", "value", "mean_of_windows", "n_windows",
          "gap_pct", "runtime_windows", "runtime_families"]


def x86_values(path=X86_NUMBERS):
    """{(workload, x86 label): (suite, whole-runtime value)}."""
    if not Path(path).exists():
        print(f"WARN: no x86 Server table at {path}: x86 columns left empty")
        return {}
    return {(r["workload"], r["metric"]): (r["side"][len("Server:"):], float(r["median"]))
            for r in csv.DictReader(open(path, newline="")) if r["side"].startswith("Server:")}


def envs(wins):
    """perf windows -> formula namespaces, every window (no floor)."""
    out = []
    for w in wins:
        e = {k.replace("-", "_"): v for k, v in w["v"].items() if v is not None}
        e["win_s"] = w["win_s"]
        if "task_clock" in e:
            e["task_clock_s"] = e["task_clock"] / 1e9
        out.append(e)
    return out


def whole_runtime(name, passes):
    """x86 rule over {family: [env]}: sum the metric's terms over every window of every pass that
    counted all of them, evaluate once -> (value, n_windows, families)."""
    need, sums, n, fams = NEEDS[name], {}, 0, []
    for fam, es in passes.items():
        hit = [e for e in es if need <= e.keys()]
        fams += [fam] if hit else []
        n += len(hit)
        for e in hit:
            for k in need:
                sums[k] = sums.get(k, 0) + e[k]
    return (spec.evalx(name, sums) if n else None), n, fams


def condense(pdir, m):
    files = {}
    for pat in RECEIPTS:
        for f in sorted(pdir.glob(pat)):
            if f.stat().st_size > MAX_COPY:
                files[f.name] = {"skipped_bytes": f.stat().st_size}
                continue
            t = f.read_text(errors="replace")
            try:
                files[f.name] = json.loads(t)
            except ValueError:
                files[f.name] = t
    return {"attempt": pdir.name, "valid": m.get("valid"), "receipt": m.get("receipt"),
            "gates": m.get("gates"), "files": files}


def export(raw, out, include_invalid=False):
    """-> True if written. include_invalid (selftest only): with no accepted attempt, the last
    attempt that has a perf.json and a capture stands in."""
    att = []
    for wl, fam, a, pdir, m, done in spec.scan(raw):
        if not m and (pdir / "capture.json").exists():
            m = json.loads((pdir / "capture.json").read_text())
        if done and m.get("valid") is not True:
            print(f"WARN: {wl}/{fam}/DONE names {a}, whose meta is not valid: not used")
        att.append([wl, fam, a, pdir, m, done, done and m.get("valid") is True])
    if include_invalid:
        last = {(x[0], x[1]): x for x in att if x[4] and (x[3] / "perf.json").exists()}
        for k, x in last.items():
            x[6] = x[6] or not any(y[6] for y in att if (y[0], y[1]) == k)
    acc = [x for x in att if x[6]]
    if not acc:
        print(f"no accepted pass under {raw} ({len(att)} attempts): nothing written")
        return False

    met = {m["name"]: m for m in PLAN["metrics"]}
    wrows, votes, nused, missing = [], [], {}, {}
    for wl in sorted({x[0] for x in acc}):
        su, ca = WORKLOADS.get(wl, ("", ""))
        es, jef = {}, {}
        for _, fam, a, pdir, *_ in (x for x in acc if x[0] == wl):
            wins = parse(pdir / "perf.json")
            res, nd = spec.pass_metrics(fam, wins)
            nused[wl, fam, a] = len(wins) - nd
            es[fam] = envs(wins)
            for name, (vals, _, _) in res.items():
                jef[name] = [v for _, v in vals]
                wrows += [(su, ca, wl, name, f"{v:.6g}") for _, v in vals]
        for name in met:
            v, nw, fams = whole_runtime(name, es)
            mw = statistics.fmean(jef[name]) if jef.get(name) else None
            if v is None and mw is None:
                missing.setdefault(name, []).append(wl)
                continue
            gap = 100 * (mw - v) / v if v and mw is not None else None
            votes.append([su, ca, wl, name, met[name]["family"], v, mw, len(jef.get(name, [])), gap, nw,
                          ";".join(fams)])

    out = Path(out)
    proc, figs = out / "data/processed/server", out / "reports/figures/data"
    spec.write(proc / "server_arm_windows.csv.gz", ["suite", "category", "workload", "metric", "value"], wrows)
    spec.write(proc / "server_arm_votes.csv", VOTE_H, votes)
    spec.write(figs / "server_arm_votes.csv", VOTE_H, votes)
    gates = list(dict.fromkeys(k for x in att for k in (x[4].get("gates") or {})))
    prows = []
    for wl, fam, a, pdir, m, done, ok in att:
        g, sf, r = m.get("gates") or {}, m.get("steady_fenced") or {}, m.get("receipt") or {}
        prows.append([wl, WORKLOADS.get(wl, ("",))[0], fam, a, ok, done, m.get("valid"),
                      *[g.get(k) for k in gates],
                      ";".join(k for k, v in g.items() if not v) if m else "no capture.json",
                      m.get("wall_s"), m.get("capture_s"), sf.get("mean_cores"), sf.get("drift_pct"),
                      sf.get("residual_pct"), m.get("ghz_cycles_per_task_clock"), m.get("ghz_cycles_per_cnt"),
                      m.get("coverage"), r.get("status"), r.get("why"), m.get("n_windows"), m.get("n_active"),
                      m.get("n_mux_bad"), nused.get((wl, fam, a))])
    spec.write(proc / "passes.csv",
               ["workload", "suite", "family", "attempt", "accepted", "done", "valid", *[f"gate_{k}" for k in gates],
                "gates_failed", "wall_s", "capture_s", "mean_cores", "drift_pct", "residual_pct", "ghz",
                "ghz_cycles_per_cnt", "coverage", "receipt_status", "receipt_why", "n_windows", "n_active",
                "n_mux_bad", "n_windows_used"], prows)
    x86 = x86_values()
    for su, _, wl, *_ in votes:
        xs = {s for (w, _), (s, _) in x86.items() if w == wl}
        if xs and xs != {su}:
            print(f"WARN: {wl}: suite {su!r} here, {xs} in the x86 table")
    vs = []
    for su, ca, wl, name, _, v, mw, *_ in votes:
        lab = X86_LABEL.get(met[name]["x86"], "")
        vs.append([su, ca, wl, name, met[name]["parity"], lab, v, x86.get((wl, lab), (0, None))[1], mw])
    spec.write(figs / "server_arm_vs_x86.csv", ["suite", "category", "workload", "metric", "parity", "x86_metric",
                                                "arm_value", "x86_value", "arm_mean_of_windows"], vs)
    shutil.rmtree(proc / "receipts", ignore_errors=True)       # generated: rewritten whole every export
    for wl, fam, _, pdir, m, *_ in acc:
        p = proc / "receipts" / wl / f"{fam}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(condense(pdir, m), indent=1) + "\n")

    # ---- stdout summary
    fams = list(PLAN["families"])
    st = {(x[0], x[1]): "D" for x in acc}
    for x in att:
        st.setdefault((x[0], x[1]), "x")
    print(f"accepted {len(acc)} of {len(att)} attempts; {len(wrows)} window rows; {len(votes)} votes")
    print("coverage (D = accepted, x = attempted only): " + " ".join(f"{chr(65 + i)}={f}" for i, f in enumerate(fams)))
    print(f"{'':22s} " + "".join(chr(65 + i) for i in range(len(fams))))
    for wl in sorted({x[0] for x in att}):
        print(f"{wl:22s} " + "".join(st.get((wl, f), ".") for f in fams))
    nwl = len({x[0] for x in acc})
    allm = [n for n, w in missing.items() if len(w) == nwl]
    print("metrics with no data in any workload: " + (", ".join(allm) or "none"))
    for n, w in missing.items():
        if len(w) < nwl:
            print(f"  {n}: no data for {', '.join(w)}")
    print(f"-> {proc}  {figs}")
    return True


# ---------------------------------------------------------------- self-check
def selftest(driver_raw=None):
    def c(cyc, ins, **k):
        return {"cpu_cycles": cyc, "inst_retired": ins, **k}

    def rd(p):
        with (gzip.open(p, "rt", newline="") if p.suffix == ".gz" else open(p, newline="")) as fh:
            return list(csv.DictReader(fh))

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)

        def bank(raw, wl, fam, att, wins, valid=True, files=None):
            p = raw / wl / fam / att
            p.mkdir(parents=True)
            with open(p / "perf.json", "w") as fh:
                for i, w in enumerate(wins):
                    for e, v in {"task-clock": 1e8, "context-switches": 0, **w}.items():
                        fh.write(json.dumps({"interval": 0.1 * (i + 1), "counter-value": f"{v:f}", "unit": "",
                                             "event": e, "pcnt-running": 100.0}) + "\n")
            (p / "meta.json").write_text(json.dumps({
                "valid": valid, "gates": {"no_mux": True, "witness": valid, "receipt": True},
                "steady_fenced": {"mean_cores": 1.0, "drift_pct": 1.0, "residual_pct": 0.5},
                "receipt": {"status": "pass", "why": "test"}, "n_windows": len(wins)}))
            for n, body in (files or {}).items():
                (p / n).write_text(body)
            if valid:
                (p.parent / "DONE").write_text(att + "\n")

        raw, T, K, cs = td / "raw", "tomcat", "kafka-20g", "context-switches"
        # tomcat anchor: IPC 2, 1, (1 ms task-clock window, IPC 9: below the floor), 3
        bank(raw, T, "anchor", "a1", [c(1e8, 2e8, **{cs: 1}), c(1e8, 1e8, **{cs: 3}),
                                      c(1e6, 9e6, **{"task-clock": 1e6, cs: 5}), c(2e8, 6e8)],
             files={".load_json": '{"jar": "x"}', "dacapo_receipt.json": '{"ok": 1}',
                    "big_receipt.txt": "x" * (MAX_COPY + 1), "dacapo.log": "log"})
        bank(raw, T, "tlb-data", "a1", [c(1e8, 1e10, l1d_tlb_refill=1e9, l2d_tlb_refill=0, dtlb_walk=0)], valid=False)
        tlb = dict(l2d_tlb_refill=1e4, dtlb_walk=5e3, **{cs: 6})
        bank(raw, T, "tlb-data", "a2", [c(1e8, 1e8, l1d_tlb_refill=1e5, **tlb), c(1e8, 3e8, l1d_tlb_refill=1e5, **tlb)])
        bank(raw, K, "frequency", "a1", [c(3.3e8, 1e8, cnt_cycles=1e8), c(3.2e8, 1e8, cnt_cycles=1e8)])
        bank(raw, K, "branch", "a1", [c(1e8, 1e8, br_mis_pred_retired=1e5)], valid=False)
        assert export(raw, td / "out")
        proc, fig = td / "out/data/processed/server", td / "out/reports/figures/data"

        W = rd(proc / "server_arm_windows.csv.gz")
        assert [r["value"] for r in W if r["workload"] == T and r["metric"] == "IPC"] == ["2", "1", "3"], W
        assert {(r["suite"], r["category"]) for r in W if r["workload"] == T} == {("DaCapo", "server")}
        assert not any(r["workload"] == K and r["metric"] == "Branch MPKI" for r in W)   # invalid pass unused
        V = {(r["workload"], r["metric"]): r for r in rd(proc / "server_arm_votes.csv")}
        v = V[T, "IPC"]                     # pooled: anchor (all 4 windows) + tlb-data a2, a1 excluded
        assert float(v["mean_of_windows"]) == 2.0 and v["n_windows"] == "3", v
        assert abs(float(v["value"]) - 13.09 / 6.01) < 1e-12 and v["runtime_windows"] == "6", v
        assert v["runtime_families"] == "anchor;tlb-data", v
        v = V[T, "L1D-TLB MPKI"]            # windows 1.0 and 1/3 -> mean 2/3; whole runtime 2e5 / 4e8
        assert abs(float(v["mean_of_windows"]) - 2 / 3) < 1e-12 and abs(float(v["value"]) - 0.5) < 1e-12, v
        assert abs(float(v["gap_pct"]) - 100 / 3) < 1e-9, v
        v = V[T, "Context switches (/CPU-s)"]
        assert abs(float(v["mean_of_windows"]) - 40 / 3) < 1e-9 and abs(float(v["value"]) - 21 / 0.501) < 1e-9, v
        assert (T, "Frontend-bound (%)") not in V                  # events never counted -> no data
        assert abs(float(V[K, "Frequency (GHz)"]["value"]) - 3.25) < 1e-12
        assert V[K, "IPC"]["mean_of_windows"] == "" and V[K, "IPC"]["runtime_families"] == "frequency"
        assert (fig / "server_arm_votes.csv").read_bytes() == (proc / "server_arm_votes.csv").read_bytes()
        P = {(r["workload"], r["family"], r["attempt"]): r for r in rd(proc / "passes.csv")}
        assert len(P) == 5 and P[T, "tlb-data", "a1"]["accepted"] == "False", P
        assert P[T, "tlb-data", "a1"]["gates_failed"] == "witness" and P[T, "tlb-data", "a2"]["accepted"] == "True"
        assert P[T, "anchor", "a1"]["n_windows_used"] == "3" and P[K, "branch", "a1"]["gate_witness"] == "False"
        R = json.loads((proc / "receipts" / T / "anchor.json").read_text())
        assert R["files"][".load_json"] == {"jar": "x"} and R["files"]["dacapo_receipt.json"] == {"ok": 1}, R
        assert R["files"]["big_receipt.txt"] == {"skipped_bytes": MAX_COPY + 1} and "dacapo.log" not in R["files"]
        assert not (proc / "receipts" / K / "branch.json").exists()
        X = {(r["workload"], r["metric"]): r for r in rd(fig / "server_arm_vs_x86.csv")}
        assert X[T, "L1D-TLB MPKI"]["x86_value"] == "" and X[T, "L1D-TLB MPKI"]["parity"] == "none"
        assert X[T, "Context switches (/CPU-s)"]["parity"] == "exact"
        x86 = x86_values()
        if x86:
            assert float(X[T, "IPC"]["x86_value"]) == x86[T, "IPC"][1] and X[T, "IPC"]["x86_metric"] == "IPC"
            for wl, (su, _) in WORKLOADS.items():          # suite table == the x86 sides, 10 workloads
                assert {s for (w, _), (s, _) in x86.items() if w == wl} == {su}, wl
            assert all(lab in {m for _, m in x86} for lab in X86_LABEL.values())

        bad = td / "bad"                                   # only invalid attempts -> nothing written
        bank(bad, K, "branch", "a1", [c(1e8, 1e8)], valid=False)
        assert not export(bad, td / "bad_out") and not (td / "bad_out").exists()

        if driver_raw:                                     # replay the driver's own selftest tree
            assert not export(driver_raw, td / "drv_strict") and not (td / "drv_strict").exists()
            assert export(driver_raw, td / "drv", include_invalid=True)
            dv = {(r["workload"], r["metric"]): r for r in rd(td / "drv/data/processed/server/server_arm_votes.csv")}
            for (wl, n), r in dv.items():
                if n == "Frequency (GHz)":
                    assert abs(float(r["value"]) - M["nominal_ghz"]) <= M["freq_tolerance_ghz"], r
                if n == "IPC":
                    assert float(r["value"]) > 0 and r["runtime_windows"] != "0", r
            dp = rd(td / "drv/data/processed/server/passes.csv")
            assert len(dp) == len(list(Path(driver_raw).glob("*/*/a*"))) and all(r["gates_failed"] for r in dp)
    print("SELFTEST OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", help=f"raw tree (default {RAW}); with --selftest: a driver selftest tree to "
                                  "replay with invalid passes admitted")
    ap.add_argument("--out", default=str(arm_profile.ARM),
                    help="root for data/processed/server/ and reports/figures/data/ (default arm/)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest(a.raw)
    else:
        export(a.raw or RAW, a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
