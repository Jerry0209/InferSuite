#!/usr/bin/env python3
"""typeid_select.py — pick the <=30 P7 representatives from cpu_matrix.tsv (ownership view).

Rules (sampling frame, ML_typeid/README.md "Selection of the <=30"):
  1. one representative per populated <language, own_label> cell, labels B/T/M only ('?' =
     low-evidence carries no type evidence and is never selected);
  2. remaining slots, in order: second repo per language (language-level claims need >=2
     repos), then magnitude spread (largest and smallest fence per language not yet covered);
  3. within a cell: E7-clean (no starvation/loop flags in the live ledger), coverage >=80%,
     classified >=50%, then closest to the cell's MEDIAN fence; runner-up = next by the same
     order. Prefer a repo not already picked; avoid W-CONFOUND repos (fmt=11/12 of C++,
     preact=17/31 of JS) when an alternative exists in the cell.
Every pick is a PRIOR: the P7 live episode + layer-3 gate is the verdict.

Usage: typeid_select.py [--n 30] [--tsv]   -> prints the pick list (+ runner-ups)
"""
import csv, collections, statistics as st, sys, os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ML = f"{REPO}/local_agents/ML_typeid"
N = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 30
CONFOUND = {"fmtlib", "preactjs"}
BAD_FLAGS = ("starv", "loop", "uniq", "drain")

rows = [r for r in csv.DictReader(open(f"{ML}/cpu_matrix.tsv"), delimiter="\t")]
for r in rows:
    r["fence_f"] = float(r["fence"]); r["cov_f"] = float(r["coverage"]); r["cls_f"] = float(r["classified_pct"])
    r["repo"] = r["short"].split("-")[0] if r["short"].split("-")[0] != "apache" else r["short"].rsplit("-", 1)[0]
    r["e7ok"] = not any(b in (r["flags"] or "") for b in BAD_FLAGS)
    r["repo"] = r["instance"].split("__")[0] + "/" + r["instance"].split("__")[1].rsplit("-", 1)[0]

def rank(cands, med, taken=frozenset()):
    return sorted(cands, key=lambda r: (not r["e7ok"], r["cov_f"] < 80, r["cls_f"] < 50,
                                        r["repo"] in taken, r["repo"].split("/")[1] in CONFOUND,
                                        abs(r["fence_f"] - med)))

picks, why = [], {}
picked_inst = set()
cells = collections.defaultdict(list)
for r in rows:
    if r["own_label"] in ("B", "T", "M"):
        cells[(r["language"], r["own_label"])].append(r)

# 1. one per populated cell
# fill single-member cells first so their (forced) repo counts as taken for the big cells
for (lang, lab), cs in sorted(cells.items(), key=lambda kv: len(kv[1])):
    med = st.median([c["fence_f"] for c in cs])
    ranked = rank(cs, med, frozenset(p["repo"] for p in picks))
    p = ranked[0]; ru = ranked[1] if len(ranked) > 1 else None
    picks.append(p); picked_inst.add(p["instance"])
    why[p["instance"]] = (f"cell {lang}×{lab} (n={len(cs)}, median fence {med:.0f})",
                          ru["short"] if ru else "-")

# 2. second repo per language
langs = sorted({r["language"] for r in rows})
for lang in langs:
    if len(picks) >= N: break
    have = {p["repo"] for p in picks if p["language"] == lang}
    if len(have) >= 2: continue
    cands = [r for r in rows if r["language"] == lang and r["own_label"] in ("B", "T", "M")
             and r["repo"] not in have and r["instance"] not in picked_inst]
    if not cands: continue
    med = st.median([c["fence_f"] for c in cands])
    ranked = rank(cands, med, frozenset(p["repo"] for p in picks)); p = ranked[0]
    picks.append(p); picked_inst.add(p["instance"])
    why[p["instance"]] = (f"2nd repo for {lang}", ranked[1]["short"] if len(ranked) > 1 else "-")

# 3. magnitude spread: largest then smallest typed fence per language not yet represented
for extreme in ("max", "min"):
    for lang in langs:
        if len(picks) >= N: break
        cands = [r for r in rows if r["language"] == lang and r["own_label"] in ("B", "T", "M")
                 and r["instance"] not in picked_inst and r["e7ok"] and r["cov_f"] >= 80]
        if not cands: continue
        taken = {q["repo"] for q in picks}
        ordered = sorted(cands, key=lambda r: r["fence_f"], reverse=(extreme == "max"))
        p = ordered[0]
        for alt in ordered[1:4]:                      # a fresh repo within 1.5x of the extreme wins
            if alt["repo"] not in taken and p["repo"] in taken and \
               (alt["fence_f"] >= p["fence_f"] / 1.5 if extreme == "max" else alt["fence_f"] <= p["fence_f"] * 1.5):
                p = alt; break
        have = [q["fence_f"] for q in picks if q["language"] == lang]
        if have and ((extreme == "max" and p["fence_f"] <= max(have) * 1.5) or
                     (extreme == "min" and p["fence_f"] >= min(have) / 1.5)):
            continue  # doesn't widen the spread meaningfully
        picks.append(p); picked_inst.add(p["instance"])
        why[p["instance"]] = (f"magnitude {extreme} for {lang}", "-")

picks = picks[:N]
tsv = "--tsv" in sys.argv
hdr = ["#", "instance", "lang", "mech", "own B/T/S", "label", "fence", "cov%", "cls%", "why", "runner-up"]
if tsv:
    print("\t".join(hdr))
else:
    print(f"{'#':<3}{'instance':<36}{'lang':<11}{'m':<3}{'own B/T/S':<11}{'lab':<4}{'fence':>7}{'cov':>6}{'cls':>6}  why  [runner-up]")
for i, p in enumerate(picks, 1):
    w, ru = why[p["instance"]]
    vals = [str(i), p["instance"], p["language"], p["mech"], f"{p['own_B']}/{p['own_T']}/{p['own_S']}",
            p["own_label"], f"{p['fence_f']:.0f}", f"{p['cov_f']:.0f}", f"{p['cls_f']:.0f}", w, ru]
    if tsv:
        print("\t".join(vals))
    else:
        print(f"{i:<3}{p['instance']:<36}{p['language']:<11}{p['mech']:<3}{vals[4]:<11}{p['own_label']:<4}"
              f"{p['fence_f']:>7.0f}{p['cov_f']:>6.0f}{p['cls_f']:>6.0f}  {w}  [{ru}]")
print(f"\n{len(picks)} picks; cells covered: {len({(p['language'], p['own_label']) for p in picks})}; "
      f"repos: {len({p['repo'] for p in picks})}; languages: {len({p['language'] for p in picks})}")
