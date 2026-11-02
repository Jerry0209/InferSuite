#!/usr/bin/env python3
"""validate_spec.py <episode-dir> [...] — certify SPEC episodes before any number from
them is plotted or compared against the agentic campaign.

This is the SPEC counterpart of InferSuite's validate_glm_agents.py. Gates that test the
INSTRUMENT carry over unchanged in spirit (E1/E2/E3/E6/E10/E11); the agent-specific ones
(E4 lineage, E5 agent work, E7 action-uniqueness) have no SPEC meaning and are replaced
by gates that test what can actually go wrong here: multiplexing, a crashed or truncated
run, hidden threads, and the co-counted denominator rule.

Design rule, inherited: a gate that cannot be evaluated reports "no proof" and is NOT
silently counted as a pass. Absence of evidence is never evidence of correctness.

Exit status: 0 if every episode passes every evaluable gate, 1 otherwise.
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
from collections import defaultdict
import statistics
from statistics import median

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_metrics import MUX, parse_window  # noqa: E402  (same parser as the extractor)

ELAPSED = re.compile(r"^\s*([\d.,]+)\s+seconds time elapsed")
CPUS_UTIL = re.compile(r"#\s*([\d.,]+)\s*CPUs utilized")
WINFILE = re.compile(r"^group_(.+)_w(\d+)\.txt$")


def f(x: str) -> float:
    return float(x.replace(",", ""))


class Report:
    def __init__(self, name: str):
        self.name, self.lines, self.fails, self.noproof = name, [], [], []

    def ok(self, gate: str, msg: str):
        self.lines.append(f"  {gate:<28s} OK        {msg}")

    def fail(self, gate: str, msg: str):
        self.lines.append(f"  {gate:<28s} FAIL      {msg}")
        self.fails.append(f"{gate}: {msg}")

    def warn(self, gate: str, msg: str):
        self.lines.append(f"  {gate:<28s} WARN      {msg}")

    def none(self, gate: str, msg: str):
        self.lines.append(f"  {gate:<28s} NO PROOF  {msg}")
        self.noproof.append(f"{gate}: {msg}")


# ---------------------------------------------------------------- loaders
def load_windows(d: str):
    """-> {(group, widx): (values, defects, raw_text)}"""
    out = {}
    for fn in sorted(os.listdir(d)):
        m = WINFILE.match(fn)
        if not m:
            continue
        p = os.path.join(d, fn)
        vals, defs = parse_window(p)
        with open(p, errors="replace") as fh:
            txt = fh.read()
        out[(m.group(1), int(m.group(2)))] = (vals, defs, txt)
    return out


def load_cpustat(d: str):
    """-> [(t, usage_usec, user_usec, system_usec)] from the 10 Hz cgroup poller."""
    rows = []
    p = os.path.join(d, "cpustat_scope1.tsv")
    if not os.path.exists(p):
        return rows
    for ln in open(p, errors="replace"):
        parts = ln.split()
        if len(parts) < 3:
            continue
        try:
            t = float(parts[0])
        except ValueError:
            continue
        kv = {}
        for i in range(1, len(parts) - 1, 2):
            try:
                kv[parts[i]] = int(parts[i + 1])
            except (ValueError, IndexError):
                pass
        if "usage_usec" in kv and kv["usage_usec"] >= 0:
            rows.append((t, kv["usage_usec"], kv.get("user_usec", 0), kv.get("system_usec", 0)))
    return rows


def interp(rows, t, idx):
    """Value of field `idx` at time t by linear interpolation over the poller series."""
    if not rows:
        return None
    if t <= rows[0][0]:
        return rows[0][idx]
    if t >= rows[-1][0]:
        return rows[-1][idx]
    lo, hi = 0, len(rows) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if rows[mid][0] <= t:
            lo = mid
        else:
            hi = mid
    t0, t1 = rows[lo][0], rows[hi][0]
    if t1 == t0:
        return rows[lo][idx]
    w = (t - t0) / (t1 - t0)
    return rows[lo][idx] + w * (rows[hi][idx] - rows[lo][idx])


def load_windows_tsv(d: str):
    """-> [(win, group, t_start, t_end, alive_after)] provenance of the shuffled order."""
    rows = []
    p = os.path.join(d, "windows.tsv")
    if not os.path.exists(p):
        return rows
    for ln in open(p, errors="replace"):
        parts = ln.rstrip("\n").split("\t")
        if len(parts) < 5 or parts[0] == "win":
            continue
        try:
            rows.append((int(parts[0]), parts[1], float(parts[2]), float(parts[3]), int(parts[4])))
        except ValueError:
            continue
    return rows


# ---------------------------------------------------------------- gates
def gate_S1_no_multiplexing(R, wins):
    """Multiplexing and <not counted> are NOT the same defect.

    A scaling annotation means perf time-sliced the group and EXTRAPOLATED the numbers —
    every value in that window is an estimate, which is exactly what this methodology
    exists to prevent. One occurrence is disqualifying.

    <not counted> means an event was never scheduled, so that window simply contributes
    nothing for it. extract_metrics excludes such a window from BOTH the numerator and
    that event's co-counted denominator, so the ratio stays exact — the cost is sampling,
    not correctness. At WINSEC=0.1 this appears as a counter-setup warm-up race in the
    first ~10 windows (measured: 0.174% of 22418 windows, always the group's last event).
    Failing an otherwise perfect 2306-window episode over 2 such windows would be wrong,
    so it is rate-limited instead.
    """
    mux, notc = [], []
    for (g, w), (_v, defs, _t) in sorted(wins.items()):
        for dfc in defs:
            (mux if "MULTIPLEX" in dfc else notc).append(f"{g}_w{w:03d}: {dfc[:90]}")
    if not wins:
        R.none("S1 zero-multiplexing", "no window files")
        return
    if mux:
        R.fail("S1 zero-multiplexing",
               f"{len(mux)} MULTIPLEXED window(s) of {len(wins)} — values are "
               f"extrapolated; first: {mux[0]}")
        return
    rate = 100.0 * len(notc) / len(wins)
    if not notc:
        R.ok("S1 zero-multiplexing",
             f"{len(wins)} windows, no scaling annotation and no <not counted>")
        return
    # A <not counted> window costs SAMPLES for one event, never correctness: it is
    # excluded from that event's numerator AND its co-counted denominator, so the ratio
    # stays exact. Quantify the worst per-event loss rather than judging a whole-episode
    # rate — the artifact is a fixed ~1-3 windows of counter-setup warm-up, so on a 12 s
    # episode it reads as 3.5% while being the same absolute effect as 0.09% on a 300 s
    # one. What matters is how many of ITS OWN windows an event lost.
    per_event = defaultdict(int)
    for x in notc:
        mm = re.search(r"<not counted>\s+(\S+)", x)
        if mm:
            per_event[mm.group(1)] += 1
    ngroups = len({g for (g, _w) in wins}) or 1
    per_group_windows = len(wins) / ngroups
    worst_ev, worst_n = max(per_event.items(), key=lambda t: t[1], default=("?", 0))
    worst_pct = 100.0 * worst_n / max(per_group_windows, 1)
    msg = (f"{len(wins)} windows, ZERO multiplexed; {len(notc)} <not counted> "
           f"({rate:.3f}%); worst event {worst_ev} lost {worst_n}/{per_group_windows:.0f} "
           f"of its own windows ({worst_pct:.1f}%)")
    if worst_pct <= 25.0:
        R.ok("S1 zero-multiplexing", msg + " — ratios exact, sampling slightly reduced")
    else:
        R.warn("S1 zero-multiplexing", msg + " — ratios still exact but NOISY for that event")


def gate_S2_correctness(R, meta):
    rc = meta.get("bench_exit_status")
    oc = (meta.get("output_check") or {}).get("status")
    if rc is None and oc is None:
        R.none("S2 run correctness", "metadata predates the exit-status/output check")
        return
    if rc != 0:
        R.fail("S2 run correctness", f"benchmark exit status {rc} — not a completed run")
    elif oc == "pass":
        n = (meta.get("output_check") or {}).get("n_checked", "?")
        R.ok("S2 run correctness", f"exit 0 and specdiff clean on {n} output file(s)")
    elif oc == "fail":
        R.fail("S2 run correctness", "specdiff MISCOMPARE — the benchmark computed wrong results")
    elif oc == "unmatched":
        R.fail("S2 run correctness", "no validated output produced")
    else:
        R.none("S2 run correctness", f"exit 0 but output check inconclusive ({oc})")


def gate_S3_single_thread(R, rows, max_cores):
    if len(rows) < 2 or rows[-1][0] <= rows[0][0]:
        R.none("S3 single-thread", "cpu.stat poller series too short")
        return
    dt = rows[-1][0] - rows[0][0]
    occ = (rows[-1][1] - rows[0][1]) / 1e6 / dt
    # Peak over ~0.1 s spans, found by walking forward to the next sample that far ahead.
    # The old form compared ADJACENT samples and required a >0.05 s gap between them —
    # which silently reported peak 0.00 once the poller was sped up to 100 Hz, since no
    # adjacent pair is ever 0.05 s apart.
    peak = 0.0
    j = 0
    for i in range(len(rows)):
        while j < len(rows) and rows[j][0] - rows[i][0] < 0.1:
            j += 1
        if j >= len(rows):
            break
        d = rows[j][0] - rows[i][0]
        if d > 0:
            peak = max(peak, (rows[j][1] - rows[i][1]) / 1e6 / d)
    if occ > max_cores:
        R.fail("S3 single-thread",
               f"mean occupancy {occ:.3f} cores > {max_cores} — profile is a THREAD BLEND")
    else:
        R.ok("S3 single-thread", f"mean {occ:.3f} cores (peak {peak:.2f}) over {dt:.0f}s")


def gate_S4_rotation(R, wins, wtsv, gorder):
    seen = defaultdict(int)
    for (g, _w) in wins:
        seen[g] += 1
    missing = [g for g in gorder if g not in seen]
    if not wins:
        R.none("S4 group coverage", "no windows")
        return
    if missing:
        R.fail("S4 group coverage",
               f"{len(missing)} group(s) never counted: {','.join(missing)}")
    else:
        lo, hi = min(seen.values()), max(seen.values())
        R.ok("S4 group coverage",
             f"all {len(gorder)} groups counted ({lo}-{hi} windows each)")

    # The rotation must be SHUFFLED: a fixed order is systematic sampling that can
    # phase-lock with a benchmark's own periodicity, which is exactly what SPEC's
    # regular loop nests would do to us.
    if not wtsv:
        R.none("S4 shuffled rotation", "windows.tsv absent")
        return
    n = len(gorder)
    cycles = [tuple(r[1] for r in wtsv[i:i + n]) for i in range(0, len(wtsv) - n + 1, n)]
    full = [c for c in cycles if len(c) == n and len(set(c)) == n]
    if len(full) < 2:
        R.none("S4 shuffled rotation", f"only {len(full)} complete cycle(s) — cannot judge")
    elif len(set(full)) == 1:
        R.fail("S4 shuffled rotation",
               f"all {len(full)} cycles used the identical order — rotation was NOT shuffled")
    else:
        R.ok("S4 shuffled rotation",
             f"{len(set(full))} distinct orders over {len(full)} complete cycles")


def gate_S5_cocounted(R, d, wins):
    """Recompute the co-counted denominators from raw windows and check metrics.json.

    This is the gate that guards the ~8x understatement bug: an event's denominator must
    be summed ONLY over the windows where that event's own group was live.
    """
    mp = os.path.join(d, "metrics.json")
    if not os.path.exists(mp):
        R.none("S5 co-counted denominators", "metrics.json not extracted yet")
        return
    M = json.load(open(mp))
    stored_i = M.get("co_counted_instructions") or {}
    stored_c = M.get("co_counted_cycles") or {}
    if not stored_i:
        R.none("S5 co-counted denominators", "metrics.json has no co-counted tables")
        return

    # Independent recomputation straight from the window files, PER WINDOW — the same
    # rule extract_metrics applies. Accumulating per group first and then handing every
    # event the group's whole instruction total silently re-introduces the window an
    # event was <not counted> in, which is precisely the bias the per-window form fixes.
    per_group = defaultdict(lambda: defaultdict(float))
    coI, coC = defaultdict(float), defaultdict(float)
    for (g, _w), (vals, _d, _t) in wins.items():
        gi, gc = vals.get("instructions", 0.0), vals.get("cycles", 0.0)
        for k, v in vals.items():
            per_group[g][k] += v
            coI[k] += gi
            coC[k] += gc

    def worst(stored, mine):
        w, key = 0.0, None
        for k, v in mine.items():
            s = stored.get(k)
            if s is None:
                return math.inf, f"{k} missing from metrics.json"
            denom = max(abs(v), 1.0)
            rel = abs(s - v) / denom
            if rel > w:
                w, key = rel, k
        return w, key

    wi, ki = worst(stored_i, coI)
    wc, kc = worst(stored_c, coC)
    if wi > 1e-6 or wc > 1e-6:
        R.fail("S5 co-counted denominators",
               f"recomputation disagrees (instructions {wi:.2e} at {ki}, cycles {wc:.2e} at {kc})")
        return

    # The recomputation matching only proves the extractor is self-consistent. It must
    # ALSO differ from the naive whole-episode total, or the co-counting collapsed into
    # a global denominator (the ~8x bug) while still agreeing with itself.
    #
    # Judge this ONLY on events that appear in exactly one group — the unambiguous case,
    # where a correct denominator must be that one group's instructions (~total/ngroups)
    # and a collapsed one would be the whole-episode total. Shared events like `cycles`
    # legitimately span most groups (note `priv` carries cycles:u/:k rather than plain
    # `cycles`, so "appears in every group" is not a usable test), and their ratio of
    # ~1.0 is correct rather than a defect.
    ngroups = len(per_group)
    occur = {k: sum(1 for ev in per_group.values() if k in ev) for k in coI}
    tot_i = sum(ev.get("instructions",
                       ev.get("instructions:u", 0.0) + ev.get("instructions:k", 0.0))
                for ev in per_group.values())
    single = [k for k, c in occur.items() if c == 1 and coI[k] > 0]
    ratios = [tot_i / coI[k] for k in single]
    if not ratios:
        R.warn("S5 co-counted denominators",
               f"exact match, but no event is unique to a single group — nothing to judge")
    elif min(ratios) > 1.5:
        R.ok("S5 co-counted denominators",
             f"exact match; the {len(single)} single-group events use denominators "
             f"{min(ratios):.1f}-{max(ratios):.1f}x smaller than the episode total "
             f"across {ngroups} groups (cross-group dilution avoided)")
    else:
        R.fail("S5 co-counted denominators",
               f"single-group events have denominators only {min(ratios):.2f}x below the "
               f"episode total — co-counting collapsed into a global denominator")


def gate_E1_window_length(R, wins, winsec):
    els = []
    for (_g, _w), (_v, _d, txt) in wins.items():
        for ln in txt.splitlines():
            m = ELAPSED.search(ln)
            if m:
                els.append(f(m.group(1)))
                break
    if not els:
        R.none("E1 window length", "no 'seconds time elapsed' footers")
        return
    med = median(els)
    off = max(abs(e - winsec) for e in els)
    if abs(med - winsec) <= 0.25 * winsec and off <= 0.5 * winsec:
        R.ok("E1 window length", f"median {med:.2f}s vs configured {winsec}s ({len(els)} windows)")
    else:
        R.fail("E1 window length",
               f"median {med:.2f}s vs configured {winsec}s, worst deviation {off:.2f}s")


def gate_E2_cpus_formula(R, wins, winsec):
    """Our task-clock -> CPUs derivation vs perf's OWN '# N CPUs utilized' comment."""
    diffs = []
    for (_g, _w), (vals, _d, txt) in wins.items():
        tc = vals.get("task-clock")
        if tc is None:
            continue
        elapsed = winsec
        for ln in txt.splitlines():
            m = ELAPSED.search(ln)
            if m:
                elapsed = f(m.group(1))
                break
        for ln in txt.splitlines():
            m = CPUS_UTIL.search(ln)
            if m:
                diffs.append(abs(tc / 1e3 / elapsed - f(m.group(1))))
                break
    if not diffs:
        R.none("E2 CPUs formula", "no task-clock rows with a CPUs-utilized comment")
        return
    md = median(diffs)
    if md <= 0.02:
        R.ok("E2 CPUs formula", f"median |diff| {md:.4f} CPUs vs perf's own comment ({len(diffs)} rows)")
    else:
        R.fail("E2 CPUs formula", f"median |diff| {md:.4f} CPUs — our derivation disagrees with perf")


def gate_E3_cpustat_vs_pmu(R, wins, wtsv, rows):
    """Kernel cgroup accounting vs the PMU, same window and same scope."""
    if not rows or not wtsv:
        R.none("E3 cpu.stat vs PMU", "poller series or windows.tsv missing")
        return
    span = {(w[0], w[1]): (w[2], w[3]) for w in wtsv}
    agree = []
    for (g, wi), (vals, _d, txt) in wins.items():
        tc = vals.get("task-clock")
        se = span.get((wi, g))
        if tc is None or not se:
            continue
        t0, t1 = se
        u0, u1 = interp(rows, t0, 1), interp(rows, t1, 1)
        if u0 is None or u1 is None or t1 <= t0:
            continue
        # Compare each instrument's OCCUPANCY RATE over the interval it actually
        # observed, not both over the windows.tsv span. Those timestamps bracket perf's
        # launch and reap, so the span (0.125 s at WINSEC=0.1) is longer than the
        # interval perf had counters installed (~0.1035 s). Dividing task-clock by the
        # span understates PMU occupancy by exactly the duty cycle — 0.83 vs 1.00 CPUs,
        # which is the 0.14 dCPUs this gate was reporting as an instrument disagreement
        # when both instruments were in fact correct.
        pmu_dt = None
        for ln in txt.splitlines():
            m = ELAPSED.search(ln)
            if m:
                pmu_dt = f(m.group(1))
                break
        if not pmu_dt or pmu_dt <= 0:
            continue
        agree.append(abs((u1 - u0) / 1e6 / (t1 - t0) - tc / 1e3 / pmu_dt))
    if not agree:
        R.none("E3 cpu.stat vs PMU", "no overlapping window/poller samples")
        return
    md = median(agree)
    if md <= 0.05:
        R.ok("E3 cpu.stat vs PMU",
             f"median |dCPUs| {md:.3f} over {len(agree)} windows (independent subsystems agree)")
    else:
        R.fail("E3 cpu.stat vs PMU", f"median |dCPUs| {md:.3f} over {len(agree)} windows")


def gate_E6_kernel_share(R, wins, wtsv, rows):
    """PMU cycles:k/(u+k) vs the scheduler's own user/system split."""
    if not rows or not wtsv:
        R.none("E6 kernel share", "poller series or windows.tsv missing")
        return
    span = {(w[0], w[1]): (w[2], w[3]) for w in wtsv}
    agree = []
    for (g, wi), (vals, _d, _t) in wins.items():
        ck, cu = vals.get("cycles:k"), vals.get("cycles:u")
        se = span.get((wi, g))
        if ck is None or cu is None or not se or (ck + cu) <= 0:
            continue
        t0, t1 = se
        s0, s1 = interp(rows, t0, 3), interp(rows, t1, 3)
        us0, us1 = interp(rows, t0, 2), interp(rows, t1, 2)
        if None in (s0, s1, us0, us1):
            continue
        dsys, dusr = s1 - s0, us1 - us0
        if dsys + dusr <= 0:
            continue
        agree.append(abs(ck / (ck + cu) - dsys / (dsys + dusr)))
    if not agree:
        R.none("E6 kernel share", "no windows with both cycles:k/:u and poller coverage")
        return
    md = median(agree)
    if md <= 0.10:
        R.ok("E6 kernel share", f"median |delta| {100*md:.1f}pp over {len(agree)} windows")
    else:
        R.fail("E6 kernel share", f"median |delta| {100*md:.1f}pp — PMU and scheduler disagree")


def gate_E10_tma(R, d, meta, wins, wtsv=None):
    p = os.path.join(d, "tma_cont.csv")
    if not os.path.exists(p):
        R.none("E10 continuous TMA", "tma_cont.csv absent")
        return
    tot, times, n, mux = defaultdict(float), [], 0, 0
    for ln in open(p, errors="replace"):
        if ln.startswith("#") or not ln.strip():
            continue
        parts = ln.split(",")
        if len(parts) < 5:
            continue
        try:
            times.append(float(parts[0]))
            tot[parts[3]] += float(parts[1])
        except ValueError:
            continue
        if MUX.search(ln):
            mux += 1
        n += 1
    if not tot:
        R.none("E10 continuous TMA", "no parseable rows")
        return
    l1 = {k: tot.get(f"topdown-{k}", 0.0) for k in ("retiring", "bad-spec", "fe-bound", "be-bound")}
    tot_l1 = sum(l1.values())
    msgs = []
    bad = False
    if mux:
        msgs.append(f"{mux} multiplexed rows"); bad = True
    if tot_l1 <= 0:
        msgs.append("L1 topdown events all zero"); bad = True
    else:
        msgs.append("L1 " + " ".join(f"{k}={100*v/tot_l1:.0f}%" for k, v in l1.items()))
    # Coverage: the census must span the episode, not a slice of it.
    wall = meta.get("wall_s")
    if wall and times:
        # perf -I timestamps are ELAPSED SINCE THE CENSUS STARTED, so a reading at
        # t=10 already accounts for 0..10 s. Coverage is therefore max(t)/wall, not the
        # span between the first and last reading — the span form ignored everything
        # before the first reading and understated every episode (729.abc_r read 10%
        # against a true 90%, 782.lbm_r 94% against 99%).
        ut = sorted(set(times))
        cov = max(ut) / wall
        msgs.append(f"coverage {100*min(cov,1.0):.0f}% of {wall:.0f}s wall")
        # Low coverage is only a DEFECT if the census could have done better. With a 10 s
        # read interval a 10-12 s episode yields 1-2 readings by construction, so the TMA
        # shares rest on almost no samples (729.abc_r reported bad-spec 49% off ~1 read).
        # That is an instrument-resolution limit, not a broken capture: report it as
        # unjudgeable so it can never be mistaken for a verified TMA breakdown.
        if cov < 0.80:
            bad = True
    # Cross-instrument check. TMA counts no `cycles`, but exactly one group is live per
    # window and the windows tile the episode, so summing `cycles` over ALL windows is
    # the episode's cycle count — measured by a different instrument than the continuous
    # census. slots/cycle must then land on the core's real issue width (Golden Cove: 6).
    slots = tot.get("slots", 0.0)
    # The `priv` group counts cycles:u and cycles:k INSTEAD of plain `cycles` (it spends its
    # four GP slots on the privilege split), so a bare v["cycles"] sum silently drops one
    # group's windows from the denominator while the continuous census still covers them.
    # With 11 groups that inflated slots/cycle by ~11/10: it read 6.62 across the suite
    # against a true 6.01. Fixed 2026-08-06 — the gate passed either way (band 3.5-8.5), but
    # the NUMBER is the cross-instrument evidence, so it has to be right.
    cyc_win = sum(v.get("cycles", 0.0) or (v.get("cycles:u", 0.0) + v.get("cycles:k", 0.0))
                  for v, _d, _t in wins.values())
    if slots > 0 and cyc_win > 0:
        # DUTY-CYCLE CORRECTION. The windowed groups are torn down and re-armed between
        # windows (~20 ms of perf setup per window, fixed), so they observe only part of
        # the episode, while the continuous TMA census observes all of it. Comparing raw
        # sums therefore measures the duty cycle, not the issue width: at WINSEC=0.1 this
        # read 8.10 where WINSEC=5 read 6.77, and 6.77/8.10 = 0.836 — exactly the 83.4%
        # duty measured independently. Scale the windowed cycles back up to whole-episode
        # equivalent before comparing against the core's real issue width.
        # Duty must come from perf's OWN "seconds time elapsed" per window, not from
        # windows.tsv: those timestamps are taken before launching and after reaping
        # perf, so t_end - t_start includes the setup gap and sums to ~100% by
        # construction (measured 97.3%, which told us nothing). Perf's elapsed is the
        # interval it actually had counters installed.
        duty = None
        counted = 0.0
        for _v, _d, txt in wins.values():
            for ln in txt.splitlines():
                m = ELAPSED.search(ln)
                if m:
                    counted += f(m.group(1))
                    break
        if wtsv and counted > 0:
            span = max(e for *_x, e, _a in wtsv) - min(s for _w, _g, s, _e, _a in wtsv)
            if span > 0:
                duty = min(1.0, counted / span)
        if duty and duty > 0:
            width = slots / (cyc_win / duty)
            msgs.append(f"slots/cycle {width:.2f} (duty {100*duty:.1f}%-corrected)")
        else:
            width = slots / cyc_win
            msgs.append(f"slots/cycle {width:.2f} (uncorrected — no windows.tsv)")
        if not 3.5 <= width <= 8.5:
            bad = True
    else:
        msgs.append("slots/cycle not evaluable")
    (R.fail if bad else R.ok)("E10 continuous TMA", f"{n} reads; " + "; ".join(msgs))


def gate_E11_witness(R, d, rows):
    """Kernel threads belong to no cgroup, so fence totals are a LOWER bound. This
    bounds how much measured-core time the fence did NOT account for."""
    p = os.path.join(d, "procstat_partition.tsv")
    if not os.path.exists(p) or not rows:
        R.none("E11 partition witness", "witness or poller series missing")
        return
    meta = json.load(open(os.path.join(d, "metadata.json")))
    meas = set()
    for part in (meta.get("cpus_measured") or "").split(","):
        if not part:
            continue
        a, _, b = part.partition("-")
        try:
            meas |= set(range(int(a), int(b or a) + 1))
        except ValueError:
            pass
    if not meas:
        R.none("E11 partition witness", "cpus_measured unparseable")
        return
    first, last = {}, {}
    for ln in open(p, errors="replace"):
        q = ln.split()
        if len(q) < 9 or not q[1].startswith("cpu"):
            continue
        try:
            c = int(q[1][3:])
        except ValueError:
            continue
        if c not in meas:
            continue
        try:
            busy = sum(int(x) for x in (q[2], q[3], q[4], q[7], q[8]))  # u,n,s,irq,sirq
        except ValueError:
            continue
        if c not in first:
            first[c] = busy
        last[c] = busy
    if not first:
        R.none("E11 partition witness", "no measured-core rows in the witness")
        return
    part_busy_s = sum(last[c] - first[c] for c in first) / os.sysconf("SC_CLK_TCK")
    fence_s = (rows[-1][1] - rows[0][1]) / 1e6
    resid = part_busy_s - fence_s
    dt = rows[-1][0] - rows[0][0]
    cap = dt * len(meas)
    pct = 100 * resid / cap if cap > 0 else 0.0
    if pct <= 1.0:
        R.ok("E11 partition witness",
             f"unfenced residual {resid:.1f}s = {pct:.2f}% of partition capacity")
    else:
        R.fail("E11 partition witness",
               f"unfenced residual {resid:.1f}s = {pct:.2f}% of capacity (>1%) — "
               f"something outside the fence used the measured cores")


def gate_S6_isolation(R, meta):
    iso = meta.get("iso_proof")
    if iso in (None, ""):
        R.none("S6 isolation proof", "metadata has no iso_proof")
        return
    smt, host = meta.get("smt"), meta.get("smt_host")
    gov, turbo = meta.get("governor"), meta.get("no_turbo")
    bits = [f"ambient={iso}", f"smt={smt}(host {host})", f"gov={gov}", f"no_turbo={turbo}"]
    R.ok("S6 isolation proof", " ".join(str(b) for b in bits))


# ---------------------------------------------------------------- driver
def validate(d: str) -> Report:
    R = Report(os.path.basename(d.rstrip("/")))
    mp = os.path.join(d, "metadata.json")
    meta = json.load(open(mp)) if os.path.exists(mp) else {}
    winsec = float(meta.get("winsec", 10))
    gorder = (meta.get("gorder") or "").split()
    max_cores = float(os.environ.get("MAX_MEAN_CORES", "1.05"))

    wins = load_windows(d)
    wtsv = load_windows_tsv(d)
    rows = load_cpustat(d)

    gate_S1_no_multiplexing(R, wins)
    gate_S2_correctness(R, meta)
    gate_S3_single_thread(R, rows, max_cores)
    gate_S4_rotation(R, wins, wtsv, gorder)
    gate_S5_cocounted(R, d, wins)
    gate_S6_isolation(R, meta)
    gate_E1_window_length(R, wins, winsec)
    gate_E2_cpus_formula(R, wins, winsec)
    gate_E3_cpustat_vs_pmu(R, wins, wtsv, rows)
    gate_E6_kernel_share(R, wins, wtsv, rows)
    gate_E10_tma(R, d, meta, wins, wtsv)
    gate_E11_witness(R, d, rows)
    return R


def main() -> int:
    dirs = [a for a in sys.argv[1:] if os.path.isdir(a)]
    if not dirs:
        print(__doc__)
        return 2
    reports = [validate(d) for d in sorted(dirs)]
    bad = 0
    for R in reports:
        verdict = "PASS" if not R.fails else f"FAIL ({len(R.fails)})"
        print(f"\n=== {R.name}  [{verdict}]")
        for ln in R.lines:
            print(ln)
        if R.fails:
            bad += 1
    print("\n" + "=" * 72)
    npf = sum(len(R.noproof) for R in reports)
    print(f"{len(reports) - bad}/{len(reports)} episodes pass every evaluable gate; "
          f"{npf} gate(s) could not be evaluated (reported as NO PROOF, not as passes).")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
