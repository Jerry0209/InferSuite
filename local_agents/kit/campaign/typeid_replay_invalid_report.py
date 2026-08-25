#!/usr/bin/env python3
"""typeid_replay_invalid_report.py — per-row diagnosis of the 28 replay-invalid census rows.

The replay-invalid gate fires when replay fence CPU / live fence CPU falls outside [0.5, 2].
This report establishes WHY each row diverged, from banked evidence only:

  live side   : episode_summary.json (wall_s, tool_cs_raw, exit_status, flags)
  replay side : cpustat_scope2.tsv span + usage delta (raw fence), agent.log markers
  decomposition: with two measurements of the same action sequence under different walls,
      fence = A + b*wall  solves per row into A (wall-invariant ACTION CPU) and
      b (wall-proportional BACKGROUND rate, cores). A leaked test server / daemon burning
      CPU through the live episode's model-wait gaps is exactly a large b: the replay
      compresses (no model wait) or stretches (drain cap) the wall, and the fence follows.

Causes are assigned from markers first, decomposition second:
  gradle-wrapper-offline : replay log shows gradle wrapper jar download attempts (lucene);
                           the JVM tests never started, the replay measured bootstrap only
  drain-cap-background   : replay wall pinned at REPLAY_DRAIN_S=2400 — a leaked process
                           never let the fence go quiet, background CPU accrued to the cap
  background-dominated   : b >= 0.02 cores and the live/replay walls differ >= 3x —
                           the live fence was mostly wall-proportional background burn
  small-fence-unstable   : none of the above; fences this small (<15 core-s) let a few
                           seconds of runtime/git swing the ratio outside the gate

Output: local_agents/ML_typeid/replay_invalid_report.tsv + a markdown table on stdout.
"""
import csv
import glob
import json
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ML = f"{REPO}/local_agents/ML_typeid"
DATA = f"{ML}/data"

mapd = dict(ln.strip().split("\t") for ln in open(f"{ML}/.replay_map.tsv") if "\t" in ln)


def cpustat_span(path):
    """(wall seconds, usage core-seconds) from a 10 Hz cpu.stat poll file.

    Usage is summed over POSITIVE increments, not last-minus-first: the tool fence is a
    docker cgroup that is destroyed and recreated when the container turns over, so the
    counter can reset to ~0 mid-file and a naive delta reads near zero (or negative).
    """
    t0 = t1 = prev = None
    used = 0
    with open(path) as fh:
        for ln in fh:
            p = ln.split()
            if len(p) < 3:
                continue
            try:
                t, u = float(p[0]), int(p[2])
            except ValueError:
                continue
            if t0 is None:
                t0 = t
            if prev is not None and u > prev:
                used += u - prev
            prev, t1 = u, t
    if t0 is None:
        return None, None
    return t1 - t0, used / 1e6


def grep_count(path, pat):
    if not os.path.exists(path):
        return 0
    rx = re.compile(pat, re.I)
    n = 0
    with open(path, errors="replace") as fh:
        for ln in fh:
            if rx.search(ln):
                n += 1
    return n


rows = [r for r in csv.DictReader(open(f"{ML}/cpu_matrix.tsv"), delimiter="\t")
        if "replay-invalid" in (r["flags"] or "")]
rows.sort(key=lambda r: float(r["live_ratio"]))

out = []
for r in rows:
    inst = r["instance"]
    live_dir = f"{DATA}/{mapd[inst]}/run_1"
    short = mapd[inst].replace("glm_swe_", "")
    rep_dir = f"{DATA}/glm_replay_swe_{short}/run_1"

    es = {}
    esp = f"{live_dir}/episode_summary.json"
    if os.path.exists(esp):
        es = json.load(open(esp))
    live_wall = float(es.get("wall_s") or 0)
    live_fence = float(es.get("tool_cs_raw") or 0)
    rep_wall, rep_fence = cpustat_span(f"{rep_dir}/cpustat_scope2.tsv")
    rep_wall = rep_wall or 0.0
    rep_fence = rep_fence or 0.0

    # markers
    wrapper = grep_count(f"{rep_dir}/agent.log", r"gradle-wrapper\.jar")
    cap = rep_wall >= 2390

    # decomposition fence = A + b*wall (guard the degenerate equal-wall case)
    A = b = None
    if abs(live_wall - rep_wall) > 60:
        b = (live_fence - rep_fence) / (live_wall - rep_wall)
        A = rep_fence - b * rep_wall

    if wrapper > 0:
        cause = "gradle-wrapper-offline"
    elif cap:
        cause = "drain-cap-background"
    elif b is not None and b >= 0.02 and max(live_wall, rep_wall) >= 3 * max(1.0, min(live_wall, rep_wall)):
        cause = "background-dominated"
    else:
        cause = "small-fence-unstable"

    out.append(dict(
        instance=inst, language=r["language"], ratio=float(r["live_ratio"]),
        live_wall_s=round(live_wall), live_fence_cs=round(live_fence, 1),
        replay_wall_s=round(rep_wall), replay_fence_cs=round(rep_fence, 1),
        action_cpu_cs=(round(A, 1) if A is not None else ""),
        background_cores=(round(b, 3) if b is not None else ""),
        e7_loop=("E7" in (r["flags"] or "")), exit_status=es.get("exit_status", ""),
        wrapper_marks=wrapper, cause=cause))

with open(f"{ML}/replay_invalid_report.tsv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(out[0].keys()), delimiter="\t")
    w.writeheader()
    for o in out:
        w.writerow(o)

print("| instance | lang | ratio | live wall/fence | replay wall/fence | bg cores | cause |")
print("|---|---|---|---|---|---|---|")
for o in out:
    print(f"| {o['instance']} | {o['language']} | {o['ratio']:.2f} "
          f"| {o['live_wall_s']} s / {o['live_fence_cs']} | {o['replay_wall_s']} s / {o['replay_fence_cs']} "
          f"| {o['background_cores']} | {o['cause']} |")
print(f"\n{len(out)} rows -> {ML}/replay_invalid_report.tsv")
from collections import Counter
print("causes:", dict(Counter(o["cause"] for o in out)))
