#!/usr/bin/env python3
"""export.py — banked ARM SPEC perf passes -> CSVs (arm_spec_profiling.md §5 formulas, §7 layout).

  export.py [--raw DIR] [--out-processed DIR] [--out-figures DIR]
  export.py --selftest        synthetic raw tree -> export -> hand-computed asserts

Only passes named by a DONE marker are used; every attempt still gets an episodes.csv row.
Per window of a used pass: windows with task-clock < min_task_clock_ns are dropped, then every
[[metrics]] expr of the pass's family is evaluated over that window's counts (event names with
'-' -> '_', plus win_s and task_clock_s). Vote = mean of a metric's windows; ratio_of_sums =
the expr once over the sums of those same windows. perf JSON parsing and the plan come from
arm_profile.py.
"""
import argparse
import csv
import gzip
import io
import json
import statistics
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import arm_profile  # noqa: E402

PLAN, M, parse = arm_profile.PLAN, arm_profile.M, arm_profile.parse
X86 = arm_profile.REPO / "spec26/infra_kit/x86_results"
SUITE = {b: s for s, bl in PLAN["suites"].items() for b in bl}
CODE = {m["name"]: compile(m["expr"], m["name"], "eval") for m in PLAN["metrics"]}


def g(x):
    """CSV cell: empty for None, shortest round-trip repr for floats."""
    return "" if x is None else repr(x) if isinstance(x, float) else x


def write(path, header, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = gzip.GzipFile(path, "wb", mtime=0) if path.suffix == ".gz" else open(path, "wb")
    with io.TextIOWrapper(raw, encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows([g(x) for x in r] for r in rows)


# ---------------------------------------------------------------- metrics
def evalx(name, env):
    """Restricted eval (no builtins). Missing event or zero denominator -> None (skip)."""
    try:
        return float(eval(CODE[name], {"__builtins__": {}}, env))
    except (ZeroDivisionError, NameError):
        return None


def pass_metrics(fam, wins):
    """One used pass -> {metric: ([(win, value)], ratio_of_sums, n_skipped)}, n_dropped."""
    kept = []
    for w in wins:
        if (w["v"].get("task-clock") or 0) < M["min_task_clock_ns"]:
            continue
        env = {e.replace("-", "_"): v for e, v in w["v"].items() if v is not None}
        kept.append({**env, "win_s": w["win_s"], "task_clock_s": env["task_clock"] / 1e9})
    out = {}
    for m in PLAN["metrics"]:
        if m["family"] != fam:
            continue
        vals, sums = [], {}
        for i, env in enumerate(kept):
            v = evalx(m["name"], env)
            if v is None:
                continue
            vals.append((i, v))
            for k, x in env.items():
                sums[k] = sums.get(k, 0) + x
        out[m["name"]] = (vals, evalx(m["name"], sums) if vals else None, len(kept) - len(vals))
    return out, len(wins) - len(kept)


def determinism(inst):
    """{bench: {family: inst_retired total}} over used passes -> per-bench spread verdict."""
    out = {}
    for b, d in inst.items():
        d = {f: x for f, x in d.items() if x}
        if not d:
            continue
        lo, hi, med = min(d.values()), max(d.values()), statistics.median(d.values())
        wf = max(d, key=lambda f: abs(d[f] - med))
        out[b] = {"n_passes": len(d), "spread_pct": 100 * (hi - lo) / lo,
                  "ok": (hi - lo) / lo <= M["determinism_tol"], "worst_family": wf,
                  "worst_dev_pct": 100 * (d[wf] - med) / med}
    return out


@lru_cache(None)
def x86_json(bench):
    p = X86 / bench / "metrics.json"
    return json.loads(p.read_text()) if p.exists() else {}


def x86_value(bench, name):
    """`name` is a key of metrics.json "metrics", or a dotted path from its root (tma.l1.fe_bound)."""
    if not name:
        return None
    node = x86_json(bench) if "." in name else x86_json(bench).get("metrics", {})
    for k in name.split("."):
        node = node.get(k) if isinstance(node, dict) else None
    return float(node) if isinstance(node, (int, float)) else None


# ---------------------------------------------------------------- export
def scan(raw):
    """Every attempt dir -> (bench, family, attempt, pass_dir, meta, is_DONE_attempt)."""
    for pdir in sorted(Path(raw).glob("*/*/a*")):
        if not pdir.is_dir():
            continue
        fdir = pdir.parent
        done = (fdir / "DONE").read_text().strip() if (fdir / "DONE").exists() else None
        mp = pdir / "meta.json"
        yield (fdir.parent.name, fdir.name, pdir.name, pdir,
               json.loads(mp.read_text()) if mp.exists() else {}, pdir.name == done)


def episode(b, f, a, m, done, d):
    s, w, d = m.get("sums") or {}, m.get("witness") or {}, d.get(b, {})
    return [b, SUITE.get(b, ""), f, a, m.get("valid"), done, m.get("wall_s"), m.get("n_windows"),
            m.get("n_active"), m.get("n_mux_bad"), m.get("min_pcnt_running"), s.get("inst_retired"),
            s.get("cpu_cycles"), m.get("ghz_cycles_per_task_clock"), m.get("ghz_cycles_per_cnt"),
            m.get("bench_rc"), m.get("perf_rc"), (m.get("output_check") or {}).get("status"),
            w.get("clean"), w.get("max_foreign_task_pct"), w.get("max_foreign_total_pct"),
            w.get("siblings_max_pct"), w.get("cpu8_mean_busy_pct"),
            (m.get("iso") or {}).get("measured_max_busy_pct_1p5s"),
            ";".join(k for k, v in (m.get("gates") or {}).items() if not v),
            d.get("n_passes"), d.get("spread_pct"), d.get("ok")]


def export(raw, proc, figs):
    att = list(scan(raw))
    if not att:
        raise SystemExit(f"no attempts under {raw}: nothing exported (existing CSVs untouched)")
    used = [x for x in att if x[5]]
    inst = {}
    for b, f, _, _, m, _ in used:
        inst.setdefault(b, {})[f] = (m.get("sums") or {}).get("inst_retired")
    det = determinism(inst)
    met = {m["name"]: m for m in PLAN["metrics"]}
    wrows, votes, skips, nwin, dropped = [], [], {}, {n: 0 for n in met}, 0
    for b, f, _, pdir, _, _ in used:
        res, nd = pass_metrics(f, parse(pdir / "perf.json"))
        dropped += nd
        for name, (vals, ros, sk) in res.items():
            skips[name] = skips.get(name, 0) + sk
            nwin[name] += len(vals)
            wrows += [(b, SUITE.get(b, ""), i, name, f"{v:.6g}") for i, v in vals]
            vote = statistics.fmean(v for _, v in vals) if vals else None
            gap = 100 * (vote - ros) / ros if vals and ros else None
            votes.append((b, SUITE.get(b, ""), name, f, vote, ros, gap, len(vals)))
    proc, figs = Path(proc), Path(figs)
    write(proc / "spec26_arm_windows.csv.gz", ["benchmark", "suite", "win", "metric", "value"], wrows)
    write(proc / "spec26_arm_votes.csv", ["benchmark", "suite", "metric", "family", "value",
                                          "ratio_of_sums", "gap_pct", "n_windows"], votes)
    write(proc / "episodes.csv",
          ["benchmark", "suite", "family", "attempt", "valid", "done", "wall_s", "n_windows", "n_active",
           "n_mux_bad", "min_pcnt_running", "inst_retired", "cpu_cycles", "ghz_cycles_per_task_clock",
           "ghz_cycles_per_cnt", "bench_rc", "perf_rc", "output_status", "witness_clean",
           "witness_max_foreign_task_pct", "witness_max_foreign_total_pct", "siblings_max_pct",
           "cpu8_mean_busy_pct", "iso_measured_max_busy_pct", "gates_failed", "det_n_passes",
           "det_spread_pct", "det_ok"],
          [episode(b, f, a, m, done, det) for b, f, a, _, m, done in att])
    write(proc / "determinism.csv", ["benchmark", "n_passes", "spread_pct", "ok", "worst_family", "worst_dev_pct"],
          [[b, *d.values()] for b, d in det.items()])
    fv = [v for v in votes if v[4] is not None]
    write(figs / "spec26_arm_votes.csv", ["benchmark", "suite", "metric", "value"], [v[:3] + v[4:5] for v in fv])
    write(figs / "metric_parity.csv", ["metric", "x86_name", "label", "note"],
          [[m["name"], m["x86"], m["parity"], m.get("note", "")] for m in PLAN["metrics"]]
          + [["", x, lab, "no Arm counterpart (no macro-op/uop-cache event)"]
             for lab, xs in PLAN["parity_x86_only"].items() for x in xs])
    write(figs / "spec26_arm_vs_x86.csv", ["benchmark", "suite", "metric", "arm_value", "arm_ratio_of_sums",
                                           "x86_name", "x86_value", "parity"],
          [[b, s, n, v, r, met[n]["x86"], x86_value(b, met[n]["x86"]), met[n]["parity"]]
           for b, s, n, _, v, r, _, _ in fv])
    # ---- stdout summary
    fams = list(PLAN["families"])
    st = {}
    for b, f, _, _, _, done in att:
        st[b, f] = "D" if done or st.get((b, f)) == "D" else "x"
    print(f"passes used {len(used)} of {len(att)} attempts; {len(wrows)} window rows; "
          f"{dropped} windows dropped (< {M['min_task_clock_ns'] / 1e6:g} ms task-clock)")
    print("coverage (D = DONE, x = attempted, no DONE): " + " ".join(f"{chr(65 + i)}={f}" for i, f in enumerate(fams)))
    print(f"{'':18s} " + "".join(chr(65 + i) for i in range(len(fams))))
    for b in sorted({b for b, *_ in att}):
        print(f"{b:18s} " + "".join(st.get((b, f), ".") for f in fams))
    bad = {b: d for b, d in det.items() if not d["ok"]}
    print(f"determinism: {len(det) - len(bad)}/{len(det)} OK" + "".join(
        f"\n  FAIL {b} spread={d['spread_pct']:.3f}% worst={d['worst_family']} ({d['worst_dev_pct']:+.3f}%)"
        for b, d in bad.items()))
    print("metrics with zero windows: " + (", ".join(n for n, k in nwin.items() if not k) or "none"))
    if any(skips.values()):
        print("skipped windows: " + ", ".join(f"{n}={k}" for n, k in skips.items() if k))
    print(f"-> {proc}  {figs}")


# ---------------------------------------------------------------- self-check
def selftest():
    A, B = "706.stockfish_r", "709.cactus_r"          # SPEC-int, SPEC-fp

    def bank(fdir, att, wins, inst, done=True):
        p = fdir / att
        p.mkdir(parents=True)
        with open(p / "perf.json", "w") as fh:
            for i, w in enumerate(wins):
                for e, v in {"task-clock": 1e8, **w}.items():
                    fh.write(json.dumps({"interval": 0.1 * (i + 1), "counter-value": f"{v:f}", "unit": "",
                                         "event": e, "pcnt-running": 100.0}) + "\n")
        (p / "meta.json").write_text(json.dumps({"valid": done, "gates": {"frequency": done},
                                                 "sums": {"inst_retired": inst}}))
        if done:
            (fdir / "DONE").write_text(att + "\n")

    def c(cyc, ins, **k):
        return {"cpu_cycles": cyc, "inst_retired": ins, **k}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        raw, proc, fig = td / "raw", td / "proc", td / "fig"
        # A anchor: IPC 2, 1, (1-ms window, IPC 9: dropped), 3 -> mean 2, ratio of sums 9/4
        cs = "context-switches"
        bank(raw / A / "anchor", "a1", [c(1e8, 2e8, **{cs: 1}), c(1e8, 1e8, **{cs: 3}),
                                        c(1e6, 9e6, **{"task-clock": 1e6}), c(2e8, 6e8, **{cs: 0})], 1e9)
        bank(raw / A / "branch", "a1", [c(1e8, 1e8, br_mis_pred_retired=5e5), c(1e8, 1e8, br_mis_pred_retired=1e5)], 1e9)
        bank(raw / A / "frequency", "a1", [c(3.3e8, 1e8, cnt_cycles=1e8), c(3.2e8, 1e8, cnt_cycles=1e8)], 1.002e9)
        bank(raw / B / "anchor", "a1", [c(1e8, 1.5e8), c(2e8, 3e8)], 1e9)
        bank(raw / B / "branch", "a1", [c(1e8, 1e8, br_mis_pred_retired=0)], 1.01e9)        # +1 %: gate fails
        bank(raw / B / "frequency", "a1", [c(2e8, 1e8, cnt_cycles=1e8)], 1e9, done=False)  # invalid, 2 GHz
        bank(raw / B / "frequency", "a2", [c(3.3e8, 1e8, cnt_cycles=1e8)] * 3, 1e9)
        export(raw, proc, fig)

        def rd(p):
            with (gzip.open(p, "rt", newline="") if p.suffix == ".gz" else open(p, newline="")) as fh:
                return list(csv.DictReader(fh))
        W = rd(proc / "spec26_arm_windows.csv.gz")
        ipc = [(r["win"], float(r["value"])) for r in W if r["benchmark"] == A and r["metric"] == "IPC"]
        assert ipc == [("0", 2.0), ("1", 1.0), ("2", 3.0)], ipc
        assert {r["suite"] for r in W if r["benchmark"] == B} == {"SPEC-fp"}
        V = {(r["benchmark"], r["metric"]): r for r in rd(proc / "spec26_arm_votes.csv")}
        v = V[A, "IPC"]
        assert float(v["value"]) == 2.0 and float(v["ratio_of_sums"]) == 2.25 and v["n_windows"] == "3", v
        assert abs(float(v["gap_pct"]) - 100 * (2 - 2.25) / 2.25) < 1e-6, v
        assert float(V[A, "Branch MPKI"]["value"]) == 3.0 == float(V[A, "Branch MPKI"]["ratio_of_sums"])
        assert abs(float(V[A, "Context switches (/CPU-s)"]["value"]) - 40 / 3) < 1e-6
        assert abs(float(V[A, "Frequency (GHz)"]["value"]) - 3.25) < 1e-9
        assert abs(float(V[B, "Frequency (GHz)"]["value"]) - 3.3) < 1e-9   # invalid a1 (2 GHz) not used
        assert V[A, "Frontend-bound (%)"]["n_windows"] == "0"           # events absent -> skipped
        E = rd(proc / "episodes.csv")
        assert len(E) == 7 and [r["done"] for r in E].count("False") == 1, E
        D = {r["benchmark"]: r for r in rd(proc / "determinism.csv")}
        assert D[A]["ok"] == "True" and abs(float(D[A]["spread_pct"]) - 0.2) < 1e-9, D[A]
        assert D[B]["ok"] == "False" and D[B]["worst_family"] == "branch", D[B]
        assert abs(float(D[B]["spread_pct"]) - 1.0) < 1e-9 and D[B]["n_passes"] == "3"
        assert {r["det_ok"] for r in E if r["benchmark"] == B} == {"False"}
        X = {(r["benchmark"], r["metric"]): r for r in rd(fig / "spec26_arm_vs_x86.csv")}
        x = x86_json(A)
        if x:
            assert float(X[A, "IPC"]["x86_value"]) == x["metrics"]["IPC"]
            assert x86_value(A, "tma.l1.fe_bound") == x["tma"]["l1"]["fe_bound"]
        assert X[A, "Frequency (GHz)"]["x86_value"] == ""
        P = rd(fig / "metric_parity.csv")
        assert {r["label"] for r in P if not r["metric"]} == {"none"} and len(P) == len(PLAN["metrics"]) + 6
    print("SELFTEST OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(arm_profile.RAW))
    ap.add_argument("--out-processed", default=str(arm_profile.ARM / "data/processed/spec26"))
    ap.add_argument("--out-figures", default=str(arm_profile.ARM / "reports/figures/data"))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    else:
        export(a.raw, a.out_processed, a.out_figures)
    return 0


if __name__ == "__main__":
    sys.exit(main())
