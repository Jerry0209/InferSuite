#!/usr/bin/env python3
"""Dump EVERY metric computable from the banked GLM-campaign data — one wide CSV per
(task, fence). L1+L2 from the continuous TMA census (tma_cont.csv); everything else
(L3-proxy raw ratios, signature metrics) from the windowed GP-counter groups with
co-counted denominators. Choose what to plot afterwards.

Usage:  python3 dump_all_metrics.py <data_root> [out.csv]
        (data_root = the campaign data dir holding glm_swe_* / glm-t06_swe_* run dirs)
"""
import sys, os, re, glob, csv

DATA = sys.argv[1] if len(sys.argv) > 1 else \
    "/home/thu/InferSuite/local_agents/superseded_40min/data"
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(DATA, "all_metrics.csv")

FENCE = {"harness": "glm-swe", "tool": "docker-", "litellm": "glm-proxy"}

def read_groups(rundir):
    """returns {fence: {event: summed_count}} and co-counted cycles/instr per event,
    aggregated over every group_*_w*.txt window in the run."""
    S = {f: {} for f in FENCE}
    CO = {f: {} for f in FENCE}          # event -> {"C":cycles,"I":instr} of its own windows
    for wf in glob.glob(f"{rundir}/group_*_w*.txt"):
        # collect this window's rows per fence
        rows = {f: {} for f in FENCE}
        for ln in open(wf):
            m = re.match(r"\s*([\d,]+|<not counted>)\s+([\w.:/-]+)\s+(\S+)", ln)
            if not m: continue
            val, ev, cg = m.group(1), m.group(2), m.group(3)
            if val.startswith("<"): continue
            for f, tag in FENCE.items():
                if tag in cg:
                    rows[f][ev] = rows[f].get(ev, 0) + float(val.replace(",", ""))
        for f in FENCE:
            wc = rows[f].get("cycles", 0); wi = rows[f].get("instructions", 0)
            for ev, v in rows[f].items():
                S[f][ev] = S[f].get(ev, 0) + v
                e = CO[f].setdefault(ev, {"C": 0.0, "I": 0.0})
                e["C"] += wc; e["I"] += wi
    return S, CO

def read_tma(rundir):
    """L1+L2 slot fractions per fence from tma_cont.csv (continuous PERF_METRICS census)."""
    f = f"{rundir}/tma_cont.csv"
    if not os.path.exists(f): return {}
    acc = {}
    for ln in open(f):
        if ln.startswith("#") or not ln.strip(): continue
        p = [x.strip() for x in ln.split(",")]
        if len(p) < 7 or not p[1] or p[1].startswith("<"): continue
        try: val = float(p[1])
        except: continue
        ev, cg = p[3], p[4]
        fence = next((k for k, t in FENCE.items() if t in cg), None)
        if not fence: continue
        acc.setdefault(fence, {}).setdefault(ev, 0.0)
        acc[fence][ev] += val
    out = {}
    for fence, d in acc.items():
        sl = d.get("slots", 0) or 1
        pct = lambda e: 100 * d.get(e, 0) / sl
        r, b, fe, be = (pct("topdown-retiring"), pct("topdown-bad-spec"),
                        pct("topdown-fe-bound"), pct("topdown-be-bound"))
        heavy = pct("topdown-heavy-ops"); mis = pct("topdown-br-mispredict")
        flat = pct("topdown-fetch-lat"); mem = pct("topdown-mem-bound")
        out[fence] = dict(
            L1_retiring=r, L1_bad_spec=b, L1_frontend=fe, L1_backend=be,
            L2_ret_heavy=heavy, L2_ret_light=max(0, r - heavy),
            L2_badspec_mispred=mis, L2_badspec_clears=max(0, b - mis),
            L2_fe_fetch_lat=flat, L2_fe_fetch_bw=max(0, fe - flat),
            L2_be_memory=mem, L2_be_core=max(0, be - mem))
    return out

def derive(S, CO):
    """everything the GP groups can give per fence — the L3-proxy + signature layer."""
    out = {}
    for f, d in S.items():
        if d.get("instructions", 0) < 1e5: continue
        co = CO[f]
        def coI(e): return (co.get(e, {}) or {}).get("I") or d.get("instructions", 1) or 1
        def coC(e): return (co.get(e, {}) or {}).get("C") or d.get("cycles", 1) or 1
        g = lambda e: d.get(e, 0)
        I, C = d.get("instructions", 1), d.get("cycles", 1)
        l1, l2, l3, lm = (g("mem_load_retired.l1_hit"), g("mem_load_retired.l2_hit"),
                          g("mem_load_retired.l3_hit"), g("mem_load_retired.l3_miss"))
        loads = (l1 + l2 + l3 + lm) or 1
        dsb, mite, ms, lsd = g("idq.dsb_uops"), g("idq.mite_uops"), g("idq.ms_uops"), g("lsd.uops")
        ut = (dsb + mite + ms + lsd) or 1
        fp_sc = sum(v for k, v in d.items() if k.startswith("fp_arith") and "scalar" in k)
        fp_pk = sum(v for k, v in d.items() if k.startswith("fp_arith")
                    and ("packed" in k or k.endswith(".vector")))
        out[f] = {
            "IPC": I / C,
            "branch_MPKI": 1000 * g("branch-misses") / coI("branch-misses"),
            "vecFP_pct": 100 * fp_pk / (fp_pk + fp_sc) if (fp_pk + fp_sc) else 0,
            # --- L3-proxy: fetch-latency children (fe_lat group) ---
            "codeRead_MPKI(L1I)": 1000 * g("l2_rqsts.all_code_rd") / coI("l2_rqsts.all_code_rd"),
            "icache_data_stall_pctCyc": 100 * g("icache_data.stalls") / coC("icache_data.stalls"),
            "icache_tag_stall_pctCyc": 100 * g("icache_tag.stalls") / coC("icache_tag.stalls"),
            "branch_resteer_pctCyc": 100 * g("int_misc.clear_resteer_cycles") / coC("int_misc.clear_resteer_cycles"),
            # --- L3-proxy: fetch-bandwidth uop delivery (fe group) ---
            "DSB_pct": 100 * dsb / ut, "MITE_pct": 100 * mite / ut,
            "MS_pct": 100 * ms / ut, "LSD_pct": 100 * lsd / ut,
            # --- L3-proxy: core-bound ports profile (core_ports group) ---
            "divider_active_pctCyc": 100 * g("arith.div_active") / coC("arith.div_active"),
            "ports0_pctCyc": 100 * g("exe_activity.exe_bound_0_ports") / coC("exe_activity.exe_bound_0_ports"),
            "ports1_pctCyc": 100 * g("exe_activity.1_ports_util") / coC("exe_activity.1_ports_util"),
            "ports2_pctCyc": 100 * g("exe_activity.2_ports_util") / coC("exe_activity.2_ports_util"),
            # --- L3-proxy: memory ladder (cache group) — hit-based proxy, NOT exact TMA L*-bound ---
            "L1D_MPKI": 1000 * (l2 + l3 + lm) / coI("mem_load_retired.l2_hit"),
            "L2_MPKI": 1000 * (l3 + lm) / coI("mem_load_retired.l3_hit"),
            "LLC_MPKI": 1000 * lm / coI("mem_load_retired.l3_miss"),
            "AMAT_cyc": (5 * l1 + 15 * l2 + 50 * l3 + 250 * lm) / loads,
            # --- L4: DRAM occupancy (dram_bw group) ---
            "DRAM_bw_bound_pctCyc": 100 * g("cpu/offcore_requests_outstanding.data_rd,cmask=4/")
                                    / coC("cpu/offcore_requests_outstanding.data_rd,cmask=4/"),
            "DRAM_any_read_pctCyc": 100 * g("offcore_requests_outstanding.cycles_with_data_rd")
                                    / coC("offcore_requests_outstanding.cycles_with_data_rd"),
            # --- MLP (mlp group) ---
            "MLP": g("l1d_pend_miss.pending") / (g("l1d_pend_miss.pending_cycles") or 1),
            # --- user/kernel split (priv group) ---
            "kernel_pctCyc": 100 * g("cycles:k") / ((g("cycles:k") + g("cycles:u")) or 1),
        }
    return out

rows = []
for rundir in sorted(glob.glob(f"{DATA}/glm*_swe_*/run_*")):
    cfg = rundir.split("/data/")[-1].rsplit("/run_", 1)[0]
    run = "run_" + rundir.rsplit("run_", 1)[-1]
    S, CO = read_groups(rundir)
    tma = read_tma(rundir)
    der = derive(S, CO)
    for fence in ("tool", "harness"):
        row = {"config": cfg, "run": run, "fence": fence}
        row.update(tma.get(fence, {}))
        row.update(der.get(fence, {}))
        if len(row) > 3:
            rows.append(row)

cols = ["config", "run", "fence"]
for r in rows:
    for k in r:
        if k not in cols: cols.append(k)
with open(OUT, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=cols); w.writeheader()
    for r in rows: w.writerow({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()})
print(f"wrote {OUT}: {len(rows)} (task,fence) rows, {len(cols)} metric columns")
print("columns:", ", ".join(cols[3:]))
