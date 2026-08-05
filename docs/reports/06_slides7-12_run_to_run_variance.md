# Report 06 — Run-to-run variance across all 24 episodes (deck slides 7–12)

**Date of study:** 2026-07-24 · **Author of record:** Tianrui (Jerry), with Claude Code
**Deck slides:** 7 (framing), 8 (wall shares), 9 (CPU-work shares), 10 (timeline
small-multiples), 11 (absolute values), 12 (tool-call/burst structure)
**Longer prose version:** [`../handwritten_notes/analysis.md`](../handwritten_notes/analysis.md), Part 2 + findings 2–3 · **Burst/boundary vocabulary:** Report 03

---

## 1. Key summary

Slides 2–6 compared one featured episode per task; the obvious objection is that single
episodes are noisy. This study answers it by comparing **every episode from both campaigns**
— Mohamad's certified 40-min campaign (12 episodes) vs the re-run (12 episodes), same four
tasks × 3 attempts, same machine, temperature 0.0 — with all 24 runs recomputed **directly
from the raw 10 Hz cgroup `cpu.stat` series** by one shared script, then rendered
share-normalized *and* absolute. Verdict: **within-campaign variance ≥ between-campaign
difference**. Shares and shapes reproduce (model wait 65–90 % of wall in all 24 episodes;
per-task CPU personalities match on clean runs; median tool-burst duration 0.31–0.94 s
everywhere), while absolutes are 2–3× draws from a wide distribution (Mohamad's two clean
scikit-learn runs: 7.0 and 20.0 min, 1,771 and 2,568 core-s; ours: 8.3 and 8.9 min, 1,449
and 1,389 core-s). The one alarming cross-campaign gap — "our astropy is 2.4× slower" —
decomposed into more turns (82→129, ×1.6) times slower API responses that day (11→17 s per
turn, ×1.5), i.e. pure waiting, inside the observed astropy range.

## 2. Methodology

### 2.1 Design decisions

| Decision | Value | Why |
|---|---|---|
| Recompute per-run metrics from raw pollers, not from either campaign's saved figures | `cpustat_scope1/2/3.tsv` (scope1 = harness, scope2 = tool, scope3 = litellm); cumulative `usage_usec`; core-seconds = sum of positive deltas (negative deltas = counter resets, skipped) | Both datasets rendered by identical code ⇒ no difference can come from plotter drift (Mohamad's older figures had a "peak parallelism" panel ours lack — a plotter-version red herring, same data underneath) |
| Validate the recompute against the certified plotter | featured-run totals vs `values_dump.json`: 1448.9 / 264.8 / 234.3 core-s (scikit r1 / astropy r2 / sympy r2) — exact match; the shares script prints this VALIDATION line on every run | An independent recompute is only trustworthy once it reproduces numbers the audit already certified |
| Show shares **and** absolutes | `cmp_wall_split`/`cmp_cpu_work` (%, slides 8–9) and `cmp_absolute` (min / core-s, slide 11) | Different questions: "does the split reproduce?" (yes) vs "how big is one draw?" (2–3× spread) — normalizing away the second would hide the study's honesty |
| Loop tagging from the trajectory tail | last 12 logged actions; ≥ 8 identical → LOOP | Cheap, name-blind detector for terminal lock-in (the temp-0.0 failure mode); looped episodes are real measurements *of a failure*, so they stay visible but flagged (⟳, red titles), and are excluded from task profiles |
| Mohamad django run_1 = unverifiable | its trajectory file is 0 bytes → status "?"; bars shown, excluded from loop-rate counting | No action stream ⇒ loop status cannot be established; hence "django looped in 5 of 6 *verifiable* attempts across both campaigns" |
| Turns = `STEP ` markers in `agent.log` | exact as logged by the harness | The harness's own step counter — no activation-clustering heuristic needed for SWE (contrast the OC caveat in CLAUDE.md) |
| Burst vocabulary = the certified constants | tool floor 0.005 / harness floor 0.02 cores, gaps < 0.4 s merged, heavy = peak > 0.3 cores | Same definitions as the audited featured-run figures (Report 03) — comparability, not convenience |
| Active-wall split is mutually exclusive | per 10 Hz sample: tool-above-floor wins, else harness-above-floor, else model wait | One second of wall belongs to one category; concurrent harness trickle under a tool burst reads as tool time by construction |

### 2.2 Run inventory (recomputed from banked data; wall = poller span, includes drain)

| Campaign · task | run_1 | run_2 | run_3 |
|---|---|---|---|
| Moh · scikit-learn | 7.0 m / 72 t / 1771 cs / ok | 40.9 m / 357 t / 1738 cs / ⟳ | 20.0 m / 140 t / 2568 cs / ok |
| Moh · astropy | 15.4 m / 82 t / 147 cs / ok | 40.8 m / 407 t / 642 cs / ⟳ | 24.8 m / 121 t / 203 cs / ok |
| Moh · sympy | 31.2 m / 188 t / 142 cs / ok | 40.8 m / 312 t / 412 cs / ok | 40.7 m / 436 t / 767 cs / ⟳ |
| Moh · django | 42.2 m / 304 t / 342 cs / ? | 40.8 m / 414 t / 790 cs / ⟳ | 40.8 m / 443 t / 806 cs / ⟳ |
| New · scikit-learn | 8.3 m / 65 t / 1449 cs / ok | 8.9 m / 62 t / 1389 cs / ok | 40.5 m / 247 t / 977 cs / ⟳ |
| New · astropy | 40.5 m / 268 t / 541 cs / ⟳ | 37.4 m / 129 t / 265 cs / ok | 40.8 m / 285 t / 721 cs / ⟳ |
| New · sympy | 40.9 m / 313 t / 330 cs / ⟳ | 25.9 m / 237 t / 234 cs / ok | 34.2 m / 257 t / 287 cs / ok |
| New · django | 40.8 m / 458 t / 743 cs / ⟳ | 40.8 m / 383 t / 486 cs / ⟳ | 40.8 m / 411 t / 569 cs / ⟳ |

(m = wall minutes, t = turns, cs = total core-seconds harness+tool+litellm, ⟳ = loop,
? = unverifiable. Loop rate: Mohamad 5/12 + 1 unverifiable, ours 7/12 — chance, not settings.)

### 2.3 Exact vs heuristic, and hazards

**Exact:** fence core-seconds and rates (kernel cgroup accounting); turns (harness log);
wall (poller timestamps — note it includes capture drain, hence django r1's 42.2 m > cap).
**Heuristic:** burst thresholds/gap-merge/heavy cut; the mutually-exclusive active-wall
split (fixed 0.1 s slots, tool-wins tie-break, tool/harness series aligned by index);
the tail-12/≥8 loop rule.

Hazards a reproducer must know:
1. **Cross-campaign single-run comparisons are lottery tickets.** Same task, same campaign
   varies 2.9× (Mohamad scikit 7.0 vs 20.0 min; his sympy 142 vs 412 core-s). The astropy
   "2.4× slower" scare (37.4 vs 15.4 min) fully decomposed into turns ×1.6 and per-turn API
   latency ×1.5 — more waiting, not more work — and both episodes sit inside the observed
   astropy range (15–37 min). Never compare one run to one run.
2. **Plotter-version red herrings.** Diffing his archived PNGs against ours flagged a panel
   difference that was a plotter upgrade, not a data difference. Re-render both datasets
   with one script before believing any figure-level discrepancy.
3. **Temperature 0.0 is not deterministic over a live API** — Mohamad's three django
   attempts ran 304/414/443 turns under identical settings. Loop *rate* differs by luck
   (5/12 vs 7/12); the loop pathology itself is what reproduces. (The django follow-up at
   temp 0.6 is Report 01.)
4. **Scope note:** these are the superseded temp-0.0 soft-isolated 40-min campaigns, not
   the thesis-scope `SWE_clean`/`OC_clean` runs; this study is about whether the
   *measurement method* reproduces, and it is what motivated the temp-0.6 default.

### 2.4 Reproduction recipe

```bash
# Both data roots must be on disk; Mohamad's is OUTSIDE the repo:
#   local_agents/superseded_40min/data                                (re-run, 12 episodes)
#   ~/llm-service-kernel-latest/archive/certified_glm_40min           (Mohamad, 12 episodes)
# (paths are constants MINE/MOH/OUT at the top of each script — edit there if moved)
python3 local_agents/kit/plot/cmp_allruns.py --view shares    # cmp_wall_split, cmp_cpu_work,
                                                          # cmp_timeline_{moh,new}
python3 local_agents/kit/plot/cmp_allruns.py --view absolute  # cmp_absolute, cmp_callstruct
                                                          # (+ cmp_whats_heavy → slide 13)
```

System `python3` (matplotlib is system-wide). No capture, no API cost — pure re-plot of
banked 10 Hz data; seconds per script. Acceptance gate: the shares script's printed
VALIDATION lines must match `values_dump.json` (1449/265/234 core-s for the featured runs).
Per-run inputs consumed: `glm_swe_<task>/run_N/{cpustat_scope1,2,3.tsv, agent.log,
traj/**/*.traj}`.

### 2.5 Scripts and artifacts

| Item | Location | Role |
|---|---|---|
| `cmp_allruns.py --view shares` | `local_agents/kit/` | raw-cpu.stat recompute, values_dump validation print, share grids (slides 8–9), timeline small-multiples (slide 10) |
| `cmp_allruns.py --view absolute` | `local_agents/kit/` | absolute wall/core-s grid (slide 11), call/burst structure (slide 12); also emits slide 13's what's-heavy figure |
| `values_dump.json` | `local_agents/superseded_40min/plots/` | certified plotter numbers used as the validation reference |
| Figures `cmp_*.png` | `local_agents/superseded_40min/plots/compare/` | `cmp_wall_split`, `cmp_cpu_work`, `cmp_timeline_moh`, `cmp_timeline_new`, `cmp_absolute`, `cmp_callstruct` |
| Mohamad campaign data | `~/llm-service-kernel-latest/archive/certified_glm_40min/` | 12 episode dirs (outside this repo) |
| Deck builder | session scratchpad only | presentation, not data |

## 3. Key insights (most → least important)

1. **Within-campaign variance ≥ between-campaign difference — so the campaigns agree.**
   Same-campaign spreads reach 2.9× (scikit 7.0 vs 20.0 min; sympy 142 vs 412 core-s);
   every cross-campaign gap fits inside them. Reproduction must be judged on shares and
   shapes, which is exactly what the method was designed to measure.
2. **Model wait is 65–90 % of wall in all 24 episodes** — both campaigns, clean or looped.
   The study's most robust result: no episode ever spent the majority of its time computing.
3. **Per-task CPU personalities reproduce on clean runs**: scikit-learn ≈ all-tool in all
   4 clean episodes (99 % vs 100 % tool), astropy tool-heavy in all 3 (83–92 % vs 88 %),
   sympy harness-leaning in all 4 (59–75 % vs 53–63 % harness). Every looped run shifts
   toward harness; django's loops land near 90 %.
4. **Absolutes are draws, not properties**: clean scikit-learn burns 1,771/2,568 core-s in
   one campaign and 1,449/1,389 in the other; loops pile up at the 40-min cap in both.
   Any single episode's minutes/core-seconds generalize to nothing.
5. **The price of one step is the stable constant**: median tool-burst duration 0.31–0.94 s
   in all 24 episodes. Episodes vary in *length* (clean scikit ≈ 60–140 turns; loops run to
   the cap at ~250–460 turns), not in per-step cost.
6. **Timeline shape is a task fingerprint**: scikit-learn's three ~20-core test bursts,
   astropy's spiky profile, sympy's sub-core trickle appear in both campaigns' clean runs;
   a loop is instantly recognizable as a solid harness wall into the cap — a CPU signature
   of failure that must never be presented as a task profile.
7. **Recompute-then-validate is the cheap insurance**: rebuilding all metrics from raw
   pollers and matching the certified `values_dump.json` exactly (1449/265/234) is what
   separates "the figures look similar" from "the numbers are the same" — and what caught
   the plotter-version red herring instead of chasing it.
