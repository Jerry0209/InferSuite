#!/usr/bin/env python3
"""plot_iso36_selection.py — the selection matrix: which ⟨language × count-label⟩ cells the
36 ML_iso36 profiling picks came from, drawn over the count-view cell populations.

Cell shade = count-view population (cpu_matrix.tsv leaf_label, as in fig 08d). Each cell
lists its picked tasks (bold; '+' marks a majority top-up landing in that cell). The small
corner number is the cell population, with the profilable subset in parentheses when it
differs (hard excludes: replay-invalid, E7 loops, no banked trajectory).

    /home/thu/miniforge3/envs/infersuite-full/bin/python local_agents/kit/plot/plot_iso36_selection.py
"""
import collections
import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# repo root from __file__, not a hardcoded home path — this ran on the P7 (~/InferSuite)
# and now also on the type-id machine (~/InferSuite-Jerry) for the resolution-clean revision
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ML = f"{REPO}/local_agents/ML_typeid"
OUT = f"{REPO}/local_agents/ML_iso36/plots"

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["DejaVu Serif"], "font.size": 10,
    "figure.dpi": 150, "savefig.dpi": 300, "savefig.bbox": "tight",
})
LANGS = ["C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript"]
LABS = ["B", "T", "S", "M"]
LABNAME = {"B": "build", "T": "test", "S": "search", "M": "mixed"}
MECH = {"C": "B", "C++": "B", "Rust": "A", "Go": "A", "Java": "J", "PHP": "I", "Ruby": "I",
        "JavaScript": "N", "TypeScript": "N"}
HARD = ("replay-invalid", "E7-consecutive-loop", "E7-cyclic-loop")
ACCENT = "#2a78d6"

replayable = {ln.split("\t")[0] for ln in open(f"{ML}/.replay_map.tsv") if "\t" in ln}
rows = list(csv.DictReader(open(f"{ML}/cpu_matrix.tsv"), delimiter="\t"))
tot, elig = collections.Counter(), collections.Counter()
for r in rows:
    if r["language"] in LANGS and r["leaf_label"] in LABS:
        tot[(r["language"], r["leaf_label"])] += 1
        if not any(b in (r["flags"] or "") for b in HARD) and r["instance"] in replayable:
            elig[(r["language"], r["leaf_label"])] += 1

sel = [r for r in csv.DictReader(open(f"{ML}/selection_36_count.tsv"), delimiter="\t")
       if "__" in r.get("instance", "")]
picks = collections.defaultdict(list)
for r in sel:
    picks[(r["lang"], r["label"])].append((r["short"], "top-up" in r["why"], r["fence"]))

fig, ax = plt.subplots(figsize=(12.6, 9.2))
vmax = max(tot.values())
for i, lang in enumerate(LANGS):
    for j, lab in enumerate(LABS):
        n, e = tot[(lang, lab)], elig[(lang, lab)]
        a = 0.06 + 0.5 * (n / vmax) if n else 0.0
        ax.add_patch(plt.Rectangle((j, i), 1, 1, fc=ACCENT, alpha=a, ec="white", lw=2))
        if n:
            pop = f"n={n}" + (f" ({e} prof.)" if e != n else "")
            ax.text(j + 0.045, i + 0.10, pop, ha="left", va="top", fontsize=7.6, color="#444444")
        else:
            ax.text(j + 0.5, i + 0.5, "empty", ha="center", va="center", fontsize=8,
                    color="#999999", style="italic")
        if n and not e:
            ax.text(j + 0.5, i + 0.58, "no profilable\ncandidate", ha="center", va="center",
                    fontsize=7.6, color="#8a3333", style="italic")
        # cells whose members are profilable but were excluded by the resolution screening —
        # the audit trail is the TSV `why` column and the doc's Revisions section
        RESOLUTION_EXCLUDED = {("Ruby", "B"): "not live-resolvable\n(fpm-1829, 6 attempts)",
                               ("Ruby", "S"): "no resolvable\ncandidate"}
        if n and e and not picks.get((lang, lab)) and (lang, lab) in RESOLUTION_EXCLUDED:
            ax.text(j + 0.5, i + 0.58, RESOLUTION_EXCLUDED[(lang, lab)], ha="center",
                    va="center", fontsize=7.6, color="#8a3333", style="italic")
        ps = picks.get((lang, lab), [])
        for k, (short, topup, fence) in enumerate(ps):
            ax.text(j + 0.5, i + 0.40 + 0.155 * k, ("+ " if topup else "") + short,
                    ha="center", va="center", fontsize=8.0, fontweight="bold",
                    color="#123f6e")
    ax.text(-0.12, i + 0.5, lang, ha="right", va="center", fontsize=11)
    ax.text(-1.55, i + 0.5, f"class {MECH[lang]}", ha="left", va="center", fontsize=8, color="#8a8880")
    npick = sum(len(picks.get((lang, l), [])) for l in LABS)
    ax.text(len(LABS) + 0.12, i + 0.5, f"{npick} picks", ha="left", va="center", fontsize=8.6,
            color="#52514e")
for j, lab in enumerate(LABS):
    ax.text(j + 0.5, -0.28, f"{lab}\n{LABNAME[lab]}", ha="center", va="center", fontsize=10.5)
    cn = sum(len(picks.get((l, lab), [])) for l in LANGS)
    ax.text(j + 0.5, len(LANGS) + 0.30, f"{cn}", ha="center", va="center", fontsize=10.5,
            fontweight="bold", color="#123f6e")
ax.text(-0.12, len(LANGS) + 0.30, "picks", ha="right", va="center", fontsize=9, color="#52514e")

ax.set_xlim(-1.7, len(LABS) + 1.1)
ax.set_ylim(len(LANGS) + 0.75, -0.75)
ax.axis("off")
ax.set_title("ML_iso36 selection — 36 picks on the count-view type matrix", fontsize=13, pad=18)
fig.text(0.5, 0.015,
         "cell shade = count-view population (300 tasks) · bold = picked task · '+' = majority top-up "
         "(its home cell was empty or had no profilable candidate)\n"
         "resolution-clean revision 2026-08-27 (4 slots re-picked or converted) + 2026-08-29 Ruby×B conversion "
         "(fpm-1829 not live-resolvable → jekyll-8167): every pick officially RESOLVED — see multi_full_stratification.md\n"
         "profilable = not replay-invalid, no E7 loop flags, banked trajectory exists · "
         "4 picks per language, one per profilable cell, extras to the majority category",
         ha="center", fontsize=8, color="#666666")
os.makedirs(OUT, exist_ok=True)
fig.savefig(f"{OUT}/iso36_selection_matrix.png")
print(f"{OUT}/iso36_selection_matrix.png")
