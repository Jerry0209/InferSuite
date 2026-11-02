#!/usr/bin/env python3
"""extract_metrics.py <episode-dir> [<episode-dir> ...] — turn raw window files into
derived microarchitectural metrics, writing metrics.json into each episode directory.

THE CO-COUNTED DENOMINATOR RULE (the single most important thing in this file)
-----------------------------------------------------------------------------
Exactly one counter group is live per window (WINSEC, currently 0.1 s), so an event's
counts cover only the windows where its own group ran. Dividing such a numerator by
instructions summed over ALL windows inflates the denominator by the number of groups
and understates the ratio by the same factor (~8x bug found in the agentic campaign on
2026-07-15; here it would be ~11x). Every ratio below therefore uses coI(event) =
instructions summed ONLY over the windows in which that event was actually counted —
accumulated per WINDOW, so a window where the event was <not counted> contributes to
neither the numerator nor its denominator.

Metric values are episode-SUM ratios (sum numerator / sum co-counted denominator), not
means of per-window ratios.

The eight shared-group metrics reproduce InferSuite's plot_glm_results.py::met()
formula-for-formula; the drill-group metrics are additional and must not be mixed into
SPEC-vs-agentic figures.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict

UNITS = {"msec", "usec", "nsec", "sec", "MiB", "KiB", "GiB", "B", "%"}

# count [unit] event cgroup [# comment]
LINE = re.compile(r"^\s+([\d.,]+|<not counted>|<not supported>)\s+(\S+)(?:\s+(\S+))?(?:\s+(\S+))?")
# perf appends a scaling annotation like "(63.42%)" whenever it multiplexed. The whole
# design exists to make this never happen, so it is recorded as a hard defect.
MUX = re.compile(r"\(\s*\d+[.,]\d+%\s*\)\s*$")


def parse_window(path: str) -> tuple[dict[str, float], list[str]]:
    """Return {event: count} for the fenced cgroup, plus any defects found."""
    vals: dict[str, float] = {}
    defects: list[str] = []
    with open(path, errors="replace") as f:
        for line in f:
            if "<not counted>" in line or "<not supported>" in line:
                defects.append(f"not-counted: {line.strip()}")
                continue
            if MUX.search(line):
                defects.append(f"MULTIPLEXED: {line.strip()}")
            m = LINE.match(line)
            if not m:
                continue
            raw, t2, t3, _t4 = m.groups()
            try:
                count = float(raw.replace(",", ""))
            except ValueError:
                continue
            event = t3 if t2 in UNITS else t2
            if not event or event.startswith("#"):
                continue
            vals[event] = vals.get(event, 0.0) + count
    return vals, defects


def load_episode(d: str, only_groups: set[str] | None = None):
    """Sum each event over its own group's windows, and the co-counted instructions.

    only_groups restricts the load to a subset of counter groups. Needed for the
    SPEC-vs-agentic comparison: SPEC rotates 11 groups and the agentic campaign rotated
    8, and the whole-episode aggregates (IPC in particular, which divides total
    instructions by total cycles over ALL windows) would otherwise be sampled over
    different group mixes on the two sides. Per-event ratios are immune — their
    co-counted denominators are already per-group — but IPC is not.
    """
    per_group: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    group_secs: dict[str, float] = defaultdict(float)
    group_wins: dict[str, int] = defaultdict(int)
    coI_w: dict[str, float] = {}      # event -> instructions over ITS OWN windows
    coC_w: dict[str, float] = {}      # event -> cycles over ITS OWN windows
    defects: list[str] = []

    winsec = 10.0
    meta_path = os.path.join(d, "metadata.json")
    if os.path.exists(meta_path):
        winsec = float(json.load(open(meta_path)).get("winsec", 10))

    for fn in sorted(os.listdir(d)):
        m = re.match(r"^group_(.+)_w(\d+)\.txt$", fn)
        if not m:
            continue
        g = m.group(1)
        if only_groups is not None and g not in only_groups:
            continue
        vals, defs = parse_window(os.path.join(d, fn))
        if not vals:
            defects.append(f"empty window: {fn}")
            continue
        defects += [f"{fn}: {x}" for x in defs]
        for k, v in vals.items():
            per_group[g][k] += v
        # Co-counted denominators accumulate PER WINDOW, over exactly the windows in
        # which each event was itself counted. Aggregating per group first and then
        # assigning the group's whole instruction total to every event is subtly wrong
        # when an event is <not counted> in some window: the numerator loses that
        # window but the denominator keeps it, biasing the ratio downward. Measured
        # 2026-08-05 at WINSEC=0.1: 39 windows (0.174%, all in w000-w010) had their
        # group's LAST event unscheduled — a counter-setup warm-up race.
        gi = vals.get("instructions", 0.0)
        gc = vals.get("cycles", 0.0)
        for k in vals:
            coI_w[k] = coI_w.get(k, 0.0) + gi
            coC_w[k] = coC_w.get(k, 0.0) + gc
        group_secs[g] += winsec
        group_wins[g] += 1

    S: dict[str, float] = defaultdict(float)          # event -> total over its windows
    for g, ev in per_group.items():
        for k, v in ev.items():
            S[k] += v
    return dict(S), coI_w, coC_w, dict(group_secs), dict(group_wins), defects


def load_tma(d: str) -> dict:
    """Continuous TMA census: time,count,unit,event,cgroup,run,pct,,"""
    path = os.path.join(d, "tma_cont.csv")
    tot: dict[str, float] = defaultdict(float)
    n = 0
    if not os.path.exists(path):
        return {}
    for line in open(path, errors="replace"):
        if line.startswith("#") or not line.strip():
            continue
        p = line.split(",")
        if len(p) < 5:
            continue
        try:
            tot[p[3]] += float(p[1])
        except ValueError:
            continue
        n += 1
    if not tot:
        return {}
    l1 = {k: tot.get(f"topdown-{k}", 0.0) for k in ("retiring", "bad-spec", "fe-bound", "be-bound")}
    denom = sum(l1.values()) or 1.0
    heavy = tot.get("topdown-heavy-ops", 0.0)
    misp = tot.get("topdown-br-mispredict", 0.0)
    flat = tot.get("topdown-fetch-lat", 0.0)
    memb = tot.get("topdown-mem-bound", 0.0)
    pct = lambda x: 100.0 * x / denom
    return {
        "n_reads": n,
        "slots": tot.get("slots", 0.0),
        "l1": {"retiring": pct(l1["retiring"]), "bad_spec": pct(l1["bad-spec"]),
               "fe_bound": pct(l1["fe-bound"]), "be_bound": pct(l1["be-bound"])},
        # L2 siblings are remainders, exactly as the agentic kit computes them.
        "l2": {"light_ops": pct(l1["retiring"] - heavy), "heavy_ops": pct(heavy),
               "fetch_lat": pct(flat), "fetch_bw": pct(l1["fe-bound"] - flat),
               "br_mispredict": pct(misp), "machine_clears": pct(l1["bad-spec"] - misp),
               "mem_bound": pct(memb), "core_bound": pct(l1["be-bound"] - memb)},
    }


def metrics(S: dict, coI: dict, coC: dict, secs: dict) -> dict:
    def co(k: str) -> float:
        return coI.get(k) or S.get("instructions", 0.0) or 1.0

    def has(*evs: str) -> bool:
        """True only if every event was ACTUALLY COUNTED in some window.

        A short episode can finish before its rotation reaches a given group — at
        WINSEC=10 both 721.gcc_r and 706.stockfish_r ended with dram_bw and fe_miss
        never sampled. Every S.get(ev, 0.0) below would then yield a clean-looking
        0.0, and "the dram_bw group never ran" would be indistinguishable in a figure
        from "this benchmark issued no DRAM reads". Metrics whose inputs were never
        counted are therefore None (undefined), not zero.
        """
        return all(e in S for e in evs)

    I = S.get("instructions", 0.0) or 1.0
    cyc = S.get("cycles", 0.0)
    l1 = S.get("mem_load_retired.l1_hit", 0.0)
    l2 = S.get("mem_load_retired.l2_hit", 0.0)
    l3 = S.get("mem_load_retired.l3_hit", 0.0)
    lm = S.get("mem_load_retired.l3_miss", 0.0)
    loads = l1 + l2 + l3 + lm
    fp_sc = sum(v for k, v in S.items() if k.startswith("fp_arith") and "scalar" in k)
    fp_pk = sum(v for k, v in S.items() if k.startswith("fp_arith")
                and ("packed" in k or k.endswith(".vector")))
    dsb, mite = S.get("idq.dsb_uops", 0.0), S.get("idq.mite_uops", 0.0)
    ms, lsd = S.get("idq.ms_uops", 0.0), S.get("lsd.uops", 0.0)
    ut = (dsb + mite + ms + lsd) or 1.0
    ck, cu = S.get("cycles:k", 0.0), S.get("cycles:u", 0.0)
    pend, pc = S.get("l1d_pend_miss.pending", 0.0), S.get("l1d_pend_miss.pending_cycles", 0.0)

    has_fp = any(k.startswith("fp_arith") for k in S)
    out = {
        # ---- the shared 8 (comparable to the agentic campaign) ----
        "IPC": I / cyc if cyc else None,
        "brMPKI": 1000 * S["branch-misses"] / co("branch-misses") if has("branch-misses") else None,
        "DSB_pct": 100 * dsb / ut if has("idq.dsb_uops") else None,
        "MITE_pct": 100 * mite / ut if has("idq.mite_uops") else None,
        "MS_pct": 100 * ms / ut if has("idq.ms_uops") else None,
        "LSD_pct": 100 * lsd / ut if has("lsd.uops") else None,
        "L1I_MPKI": (1000 * S["l2_rqsts.all_code_rd"] / co("l2_rqsts.all_code_rd")
                     if has("l2_rqsts.all_code_rd") else None),
        "L1D_MPKI": (1000 * (l2 + l3 + lm) / co("mem_load_retired.l2_hit")
                     if has("mem_load_retired.l2_hit") else None),
        "LLC_MPKI": (1000 * lm / co("mem_load_retired.l3_miss")
                     if has("mem_load_retired.l3_miss") else None),
        "AMAT_cyc": ((5 * l1 + 15 * l2 + 50 * l3 + 250 * lm) / loads
                     if has("mem_load_retired.l1_hit") and loads else None),
        "MLP": pend / pc if has("l1d_pend_miss.pending_cycles") and pc else None,
        "kernel_pct": 100 * ck / (ck + cu) if has("cycles:k", "cycles:u") and ck + cu else None,
        "vecFP_pct": (100 * fp_pk / (fp_pk + fp_sc) if has_fp and fp_pk + fp_sc else
                      (0.0 if has_fp else None)),
        "ctx_switches": S.get("context-switches") if has("context-switches") else None,
        "cpu_migrations": S.get("cpu-migrations") if has("cpu-migrations") else None,
        "page_faults": S.get("page-faults") if has("page-faults") else None,
    }

    # Rates for the raw priv-group counts, normalized by task-clock (msec, co-counted in the
    # same priv windows): switches per busy CPU-second. Task-clock, not wall, so the rate is
    # independent of fence concurrency; on SPEC's single pinned process the two coincide.
    tk = S.get("task-clock", 0.0)
    out["ctx_per_cpu_s"] = (S["context-switches"] / (tk / 1e3)
                            if has("context-switches", "task-clock") and tk else None)
    out["migr_per_cpu_s"] = (S["cpu-migrations"] / (tk / 1e3)
                             if has("cpu-migrations", "task-clock") and tk else None)
    out["pf_per_cpu_s"] = (S["page-faults"] / (tk / 1e3)
                           if has("page-faults", "task-clock") and tk else None)

    # ---- drill groups: SPEC-only, never mixed into the agentic comparison ----
    def share(ev: str):
        """Event as % of the cycles CO-COUNTED in that event's own windows.

        coC[ev] is summed over exactly the windows where ev was live, so this is the
        cycle-denominator analogue of coI — no reconstruction, no cross-group dilution.
        """
        if ev not in S:
            return None          # its group never ran; 0.0 would read as a measurement
        gc = coC.get(ev, 0.0)
        return 100 * S[ev] / gc if gc else 0.0

    # ---- per-window-grid parity keys (2026-08-21): the agentic 18-panel grid needs an
    # episode-card SPEC reference for every panel, computed HERE so both sides stay on the
    # one shared implementation. Same events, same co-counted denominators as above.
    out["branchDir_MPKI"] = (1000 * S["br_misp_retired.cond"] / co("br_misp_retired.cond")
                             if has("br_misp_retired.cond") else None)
    out["L2_MPKI"] = (1000 * (l3 + lm) / co("mem_load_retired.l3_hit")
                      if has("mem_load_retired.l3_hit") else None)
    if has("mem_load_retired.l1_hit") and loads:
        out["L1D_missrate_pct"] = 100 * (l2 + l3 + lm) / loads
        out["L2_missrate_pct"] = (100 * (l3 + lm) / (l2 + l3 + lm)) if (l2 + l3 + lm) else None
        out["LLC_missrate_pct"] = (100 * lm / (l3 + lm)) if (l3 + lm) else None
    else:
        out["L1D_missrate_pct"] = out["L2_missrate_pct"] = out["LLC_missrate_pct"] = None
    out["icache_data_stall_pct"] = share("icache_data.stalls")

    out["div_active_pct"] = share("arith.div_active")
    out["ports_1_pct"] = share("exe_activity.1_ports_util")
    out["ports_2_pct"] = share("exe_activity.2_ports_util")
    out["ports_0_pct"] = share("exe_activity.exe_bound_0_ports")
    out["stalls_l1d_miss_pct"] = share("memory_activity.stalls_l1d_miss")
    out["stalls_l2_miss_pct"] = share("memory_activity.stalls_l2_miss")
    out["stalls_l3_miss_pct"] = share("memory_activity.stalls_l3_miss")
    out["bound_on_loads_pct"] = share("exe_activity.bound_on_loads")
    out["bound_on_stores_pct"] = share("exe_activity.bound_on_stores")
    out["dsb2mite_penalty_pct"] = share("dsb2mite_switches.penalty_cycles")
    out["itlb_walk_pct"] = share("itlb_misses.walk_active")
    out["baclears_MPKI"] = 1000 * S["baclears.any"] / co("baclears.any") if has("baclears.any") else None
    out["dsb_miss_MPKI"] = (1000 * S["frontend_retired.any_dsb_miss"] / co("frontend_retired.any_dsb_miss")
                            if has("frontend_retired.any_dsb_miss") else None)
    mc, mi = S.get("br_misp_retired.cond", 0.0), S.get("br_misp_retired.indirect", 0.0)
    out["misp_indirect_pct"] = (100 * mi / (mc + mi) if has("br_misp_retired.cond") and mc + mi else None)

    # DRAM read bandwidth: 64 B per offcore data read, over the dram_bw windows only.
    # None, not 0.0: at WINSEC=10 short episodes ended before dram_bw was ever sampled,
    # and a 0.0 there reads as "issued no DRAM reads" rather than "never measured".
    dsecs = secs.get("dram_bw", 0.0)
    out["DRAM_read_GBs"] = ((S["offcore_requests.data_rd"] * 64 / dsecs / 1e9)
                            if has("offcore_requests.data_rd") and dsecs else None)
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    rows = []
    for d in sys.argv[1:]:
        if not os.path.isdir(d):
            print(f"skip (not a dir): {d}")
            continue
        S, coI, coC, secs, wins, defects = load_episode(d)
        if not S:
            print(f"skip (no windows): {d}")
            continue
        M = metrics(S, coI, coC, secs)
        tma = load_tma(d)
        meta = {}
        mp = os.path.join(d, "metadata.json")
        if os.path.exists(mp):
            meta = json.load(open(mp))
        res = {
            "benchmark": meta.get("benchmark", os.path.basename(d)),
            "wall_s": meta.get("wall_s"), "mean_cores": meta.get("mean_cores"),
            "windows_per_group": wins, "group_seconds": secs,
            "n_windows": sum(wins.values()),
            "metrics": M, "tma": tma,
            "raw_sums": S, "co_counted_instructions": coI, "co_counted_cycles": coC,
            "defects": defects,
        }
        json.dump(res, open(os.path.join(d, "metrics.json"), "w"), indent=1)
        status = "CLEAN" if not defects else f"{len(defects)} DEFECT(S)"
        # A metric is None when its counter group never got a window. Print "n/a" rather
        # than crashing or coercing to 0 — the distinction is the whole point.
        def fmt(v, p=2):
            return "n/a" if v is None else f"{v:.{p}f}"
        undef = [k for k, v in M.items() if v is None]
        print(f"{res['benchmark']:<18} windows={res['n_windows']:<4} "
              f"IPC={fmt(M['IPC'])} LLC_MPKI={fmt(M['LLC_MPKI'])} DSB={fmt(M['DSB_pct'], 0)}% "
              f"fe={fmt(tma.get('l1', {}).get('fe_bound'), 0)}% "
              f"be={fmt(tma.get('l1', {}).get('be_bound'), 0)}%  [{status}]"
              + (f"  {len(undef)} UNMEASURED: {','.join(undef[:4])}" if undef else ""))
        for x in defects[:5]:
            print(f"    ! {x}")
        rows.append(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
