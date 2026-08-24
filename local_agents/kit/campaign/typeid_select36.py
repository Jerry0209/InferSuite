#!/usr/bin/env python3
"""typeid_select36.py — pick the 36 P7 profiling representatives from cpu_matrix.tsv,
COUNT view (leaf_label), 4 per language.

Rule (PI directive 2026-08-21): for each of the 9 languages take one task per populated
<language, leaf_label> cell among B/T/S/M; if a row has empty cells, take the extra picks
from that language's MAJORITY count category, so every language contributes exactly 4.

A cell counts as empty when it has no PROFILABLE candidate, not merely when n=0 — this
selection feeds dedicated-group replays on the P7, so:
  hard excludes: 'replay-invalid' flag, E7 loop flags, instance absent from .replay_map.tsv
                 (no banked replayable trajectory), leaf_label '?' (no evidence).
  soft order (mirrors typeid_select.py rank): coverage < 80, classified < 50, repo already
                 taken, confound repo (fmt / preact), then |fence - cell median|.
Majority = the language's largest leaf_label cell by RAW count (the category identity is a
fact about the language, not about eligibility); top-ups walk down that cell's ranking,
falling back to the next-largest cell if it runs out of eligible candidates.

Every pick is a PRIOR: the P7 replay + its gates are the verdict.

Usage: typeid_select36.py [--tsv]
"""
import csv, collections, statistics as st, sys, os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ML = f"{REPO}/local_agents/ML_typeid"
LANGS = ["C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript"]
LABS = ["B", "T", "S", "M"]
CONFOUND = {"fmtlib", "preactjs"}
HARD_FLAGS = ("replay-invalid", "E7-consecutive-loop", "E7-cyclic-loop")
PER_LANG = 4

replayable = {ln.split("\t")[0] for ln in open(f"{ML}/.replay_map.tsv") if "\t" in ln}
rows = list(csv.DictReader(open(f"{ML}/cpu_matrix.tsv"), delimiter="\t"))
for r in rows:
    r["fence_f"] = float(r["fence"]); r["cov_f"] = float(r["coverage"]); r["cls_f"] = float(r["classified_pct"])
    r["repo"] = r["instance"].split("__")[0] + "/" + r["instance"].split("__")[1].rsplit("-", 1)[0]
    r["hard_bad"] = [b for b in HARD_FLAGS if b in (r["flags"] or "")]
    if r["instance"] not in replayable:
        r["hard_bad"].append("no-replay-traj")

cells = collections.defaultdict(list)          # ALL rows per cell (raw counts, majority id)
elig = collections.defaultdict(list)           # profilable candidates per cell
for r in rows:
    if r["language"] in LANGS and r["leaf_label"] in LABS:
        cells[(r["language"], r["leaf_label"])].append(r)
        if not r["hard_bad"]:
            elig[(r["language"], r["leaf_label"])].append(r)

def rank(cands, med, taken_repos):
    return sorted(cands, key=lambda r: (r["cov_f"] < 80, r["cls_f"] < 50,
                                        r["repo"] in taken_repos,
                                        r["repo"].split("/")[0] in CONFOUND,
                                        abs(r["fence_f"] - med), r["instance"]))

picks, why = [], {}
picked_inst = set()

for lang in LANGS:
    taken = lambda: frozenset(p["repo"] for p in picks)
    lang_picks = 0
    empty = []
    # 1. one per populated-and-profilable cell, singleton cells first (their repo is forced)
    lab_order = sorted(LABS, key=lambda c: (len(elig[(lang, c)]) == 0, len(elig[(lang, c)])))
    for lab in lab_order:
        cs = [c for c in elig[(lang, lab)] if c["instance"] not in picked_inst]
        if not cs:
            nraw = len(cells[(lang, lab)])
            empty.append((lab, nraw))
            continue
        med = st.median([c["fence_f"] for c in cs])
        ranked = rank(cs, med, taken())
        p, ru = ranked[0], (ranked[1] if len(ranked) > 1 else None)
        picks.append(p); picked_inst.add(p["instance"]); lang_picks += 1
        nex = len(cells[(lang, lab)]) - len(cs)
        why[p["instance"]] = (f"cell {lang}×{lab} (n={len(cells[(lang, lab)])}"
                              + (f", {nex} excl" if nex else "") + f", median fence {med:.0f})",
                              ru["short"] if ru else "-")
    # 2. top up to 4 from the majority category (largest RAW cell), then next largest
    maj_order = sorted(LABS, key=lambda c: (-len(cells[(lang, c)]), c))
    for lab in maj_order:
        while lang_picks < PER_LANG:
            cs = [c for c in elig[(lang, lab)] if c["instance"] not in picked_inst]
            if not cs:
                break
            med = st.median([c["fence_f"] for c in cs])
            ranked = rank(cs, med, taken())
            p, ru = ranked[0], (ranked[1] if len(ranked) > 1 else None)
            picks.append(p); picked_inst.add(p["instance"]); lang_picks += 1
            elab = ",".join(f"{l}(n={n})" for l, n in empty) or "-"
            why[p["instance"]] = (f"top-up {lang}×{lab} (majority; empty: {elab})",
                                  ru["short"] if ru else "-")
        if lang_picks >= PER_LANG:
            break
    if lang_picks < PER_LANG:
        print(f"WARNING: {lang} has only {lang_picks} profilable picks", file=sys.stderr)

tsv = "--tsv" in sys.argv
hdr = ["#", "instance", "short", "lang", "mech", "leaf B/T/S", "label", "n_leaf",
       "fence", "cov%", "cls%", "why", "runner-up"]
if tsv:
    print("\t".join(hdr))
else:
    print(f"{'#':<3}{'instance':<38}{'lang':<11}{'lab':<4}{'leaf B/T/S':<12}{'n_leaf':>7}"
          f"{'fence':>7}{'cov':>5}{'cls':>5}  why  [runner-up]")
for i, p in enumerate(picks, 1):
    w, ru = why[p["instance"]]
    vals = [str(i), p["instance"], p["short"], p["language"], p["mech"],
            f"{p['leaf_B']}/{p['leaf_T']}/{p['leaf_S']}", p["leaf_label"], p["n_leaf"],
            f"{p['fence_f']:.0f}", f"{p['cov_f']:.0f}", f"{p['cls_f']:.0f}", w, ru]
    if tsv:
        print("\t".join(vals))
    else:
        print(f"{i:<3}{p['instance']:<38}{p['language']:<11}{p['leaf_label']:<4}{vals[5]:<12}"
              f"{p['n_leaf']:>7}{p['fence_f']:>7.0f}{p['cov_f']:>5.0f}{p['cls_f']:>5.0f}  {w}  [{ru}]")

cellset = {(p["language"], p["leaf_label"]) for p in picks}
print(("\t" if tsv else "\n") + f"{len(picks)} picks; cells covered: {len(cellset)}; "
      f"repos: {len({p['repo'] for p in picks})}; languages: {len({p['language'] for p in picks})}; "
      f"total fence {sum(p['fence_f'] for p in picks):.0f} core-s")
