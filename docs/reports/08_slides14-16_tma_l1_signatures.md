# Report 08 — TMA Level-1 and hardware signatures across campaigns (deck slides 14–16)

**Date of study:** 2026-07-24 · **Author of record:** Tianrui (Jerry), with Claude Code
**Deck slides:** 14 (featured TMA L1, side by side), 15 (per-side signature heatmaps),
16 (TMA L1 for every run) — these feed slide 18's Level-2 drill (Report 02)
**Longer prose version:** [`../handwritten_notes/analysis.md`](../handwritten_notes/analysis.md), Part 4 and finding 5

---

## 1. Key summary

After the wall-clock/core-second comparison showed that absolute numbers swing 2–3× between
attempts of the same task, the question became: does *anything* reproduce tightly between
Mohamad's certified campaign and the re-run? Method in one sentence: run the same kit plotter
over both campaigns' banked data — whole-episode TMA Level-1 buckets from the continuous
PERF_METRICS census plus an 8-metric hardware-signature heatmap on absolute, hardware-anchored
scales — for the featured episodes, then harvest per-run TMA for all 23 verifiable episodes
(and later the 2 django@0.6 episodes). Headline: **TMA shares are the most reproducible metric
of the whole comparison** — buckets match within 1–5 points on every clean fence across
campaigns (scikit-learn tool 43/24/1/33 vs 42/23/1/34, retiring/frontend/bad-spec/backend),
and the harness fence is nearly the same bar in all 24 episodes (~40/20/8/28) regardless of
task, campaign, or looping. The bucket mix is a property of *which code executes* (pytest,
OpenBLAS, CPython), not of episode length or path — so it survives the episode-to-episode
chaos that wrecks absolute comparisons.

## 2. Methodology

### 2.1 Load-bearing decisions

| Decision | Why |
|---|---|
| TMA from the **continuous PERF_METRICS census** (`TMA_EVENTS` + `start_tma_cont()` in `run_glm_campaign.sh`): PERF_METRICS MSR + fixed `slots` counter, `-I 10000` | Zero GP counters → 100 % duty cycle, immune to the multiplexing that is invalid for bursty agent loads; the 10 s interval is a *read* cadence, not sampling — events stay installed, counts exact (details in Report 02 §2.1) |
| **Same plotter over both campaigns**, specs differing only in `data` path (Mohamad's archive `~/llm-service-kernel-latest/archive/certified_glm_40min`, outside this repo) | Any cross-campaign difference is a data difference, never code drift |
| **Featured episodes, never pooled** (locked convention): ours scikit r1 / astropy r2 / sympy r2 / django r2 (+django@0.6 r1); Mohamad's run-1 set | Pooling runs blends different execution paths into a fictitious average; the featured run is documented in `plot_spec.json` |
| **Per-run harvest reuses the kit**: one single-run plot spec per episode → `plot_glm_results.py` with `stop_before_hw` → read `tma_tool`/`tma_harness` from its `values_dump.json` (`extract_tma_perrun.py`) | Reuses the kit's own window parsing and bucket normalization instead of re-implementing the math — a second implementation could only add disagreement |
| **Mohamad django run_1 excluded** (`SKIP` set in the extractor) | Its trajectory file is empty/unreadable — not verifiable ⇒ 23 episodes; the 2 django@0.6 entries (config `glm-t06_swe_django`) were appended by the same single-run-spec pattern after the slide-17 experiment (Report 01) |
| Signature shade = `clamp((v−lo)/(hi−lo))` on **fixed absolute anchors**: IPC 0–6 (six-wide Golden Cove retire width), branch MPKI 0–20, DSB 0–100 %, L1I MPKI 0–20 (the datacenter "instruction-footprint wall"), L1D 0–40, LLC 0–10, AMAT 5–50 cyc, MLP 1–16 (L1D fill buffers) | Hardware ceilings (or literature low→severe spans) are workload-set-independent, so a color means the same thing on both campaigns' figures; per-figure normalization would recolor with every dataset. The printed cell value is the truth; the shade is only position |
| **Every ratio uses co-counted denominators** (`met()`/`coI()`: instructions summed over exactly the windows where the numerator event was counted) | Dividing a one-group numerator by all-groups instructions understates ~8× (7.9× measured; diluted L1I MPKI 0.87 vs true 6.9 — bug found 2026-07-15 by the dedicated-group probe) |
| Honest labels | "L1I MPKI" = `l2_rqsts.all_code_rd` per co-counted kilo-instruction — a **code-read / L1I-pressure proxy**, not literal L1I misses. "AMAT" = a **fixed-latency model** (5/15/50/250 cyc weighted over the L1/L2/L3/DRAM load-hit ladder), not a measured latency. High IPC/retiring does **not** certify useful work — the interpreter retires many instructions per unit of progress |

### 2.2 Verification and hazards

- **Coexistence gate** (dry-run, added 2026-07-14): the continuous TMA session and the
  windowed GP groups run *simultaneously* on a busy dummy cgroup; both must show no
  `<not counted>` and no multiplex-percentage suffix before any capture starts
  (`run_glm_campaign.sh` ~:684–700).
- **Two instruments, one story**: the TMA buckets (PERF_METRICS census) and the signature
  metrics (windowed GP groups — different counter hardware, different sampling discipline)
  agree per fence: scikit tool = backend-bound with IPC 0.64–0.69 / DSB 82–84 % / L1I proxy
  at the floor (1.1–1.6); astropy+sympy tools = frontend-bound with L1I proxy 19–31.
- **All-runs figure diagnostics**: `cmp_tma_allruns.py` marks loop episodes (⟳) and missing
  data (—) on the bars, and its loop set is written into the script — the reproducibility
  claim is scoped to clean runs of the same task (plus the harness fence everywhere).
- **Interpretation hazard**: looped episodes' *tool* fences legitimately differ (his django
  loop was `git`-bound, ours a trivial shell command — finding 6); never read a looped bar
  as the task's profile.
- Featured-figure numbers are audit-covered (`audit_plots.py`, ALL MATCH) via
  `values_dump.json` on both sides.

### 2.3 Reproduction recipe

```bash
# Featured figures, both campaigns — plot-only: no capture, no API cost, minutes.
PLOT_SPEC=local_agents/superseded_40min/plot_spec.json \
  python3 local_agents/scripts/glm/plot_glm_results.py
#   -> plots/glm_tma_l1.png (Fig 4) and plots/glm_signature.png (Fig 5)
# Mohamad side: same command with a spec whose data= points at his archive and
#   out= plots/compare/moh_featured/ (runs = his run_1 per task).

# Per-run harvest (23 episodes; ~25 plotter invocations) + all-runs figure
python3 local_agents/scripts/glm/extract_tma_perrun.py
#   -> local_agents/superseded_40min/data/l3_study/tma_allruns.json
python3 local_agents/scripts/glm/cmp_tma_allruns.py
#   -> local_agents/superseded_40min/plots/compare/cmp_tma_l1_allruns.png
```

Check the constants at the top of `extract_tma_perrun.py` before running: `CAMPS` (both
campaign data roots — the Mohamad root lives outside this repo), `PY` (the interpreter used
for the plotter), and `SP` (a session temp dir — any writable scratch path works). Keys in
`tma_allruns.json` are `<camp>/<task>/r<N>` → `{tma_tool, tma_harness}` with buckets
`retiring/fe/bad/be` normalized to 100. What should reproduce on a fresh capture: the bucket
*shares* per fence and task (to a few points), not any absolute count.

### 2.4 Scripts and artifacts (scripts in `local_agents/scripts/glm/` unless noted)

| Item | Role |
|---|---|
| `run_glm_campaign.sh` (`TMA_EVENTS` ~:69, `start_tma_cont` ~:265, coexistence gate ~:684) | banks `tma_cont.csv` per episode — the census behind every TMA number |
| `plot_glm_results.py` (`met()` ~:280, Fig 4 TMA L1 ~:584, Fig 5 signature + anchors ~:606) | featured figures + `values_dump.json` (`tma_*`, signature cards) |
| `extract_tma_perrun.py` | per-run harvest via single-run specs → `tma_allruns.json` |
| `cmp_tma_allruns.py` | all-runs 2×2 figure (campaign × fence), loop/missing marks |
| `events.md` | event → metric → formula reference; co-counted-denominator rule (§ "TMA_EVENTS") |
| `local_agents/superseded_40min/data/l3_study/tma_allruns.json` | banked per-run TMA (25 entries: 23 + 2 django@0.6) |
| figures | `local_agents/superseded_40min/plots/{glm_tma_l1,glm_signature}.png`, `plots/compare/moh_featured/` (same names, his data), `plots/compare/cmp_tma_l1_allruns.png` |

## 3. Key insights (most → least important)

1. **TMA L1 is the most reproducible metric in the whole comparison.** Clean fences agree
   within 1–5 points across campaigns: scikit-learn tool 43/24/1/33 (Mohamad) vs 42/23/1/34
   (re-run); sympy tool 29/34/19/19 and 28/34/19/20 (his clean pair) vs 31/32/19/18 and
   32/31/19/18 (ours). This directly satisfies the acceptance criterion ("successful runs of
   each task share a similar distribution") — at the microarchitecture level the
   distributions are the tightest of all.
2. **The harness fence is nearly the same bar 24 times** — ~40 % retiring, ~20 % frontend,
   ~8 % bad-spec, ~28 % backend — regardless of task, campaign, or looping; the two
   django@0.6 episodes later landed on the same constant (≈45/22/8/25). The agent program's
   microarchitectural profile belongs to the agent, not the task (per-window confirmation in
   Report 04, insight 5).
3. **Why it reproduces when absolutes don't**: the bucket mix is a property of the code
   executed, not of how long the episode ran or which path it took. Episode length varies
   2–3×; the instruction mix doesn't.
4. **Per-fence bound attribution (the mentor's TODO, at fence granularity)**: scikit-learn's
   tool fence is backend-bound (33–35 %); astropy's and sympy's tool fences are
   frontend-bound (31–35 %) with high bad-speculation (11–19 %) — interpreter churn. The
   Level-2 split of these buckets (core-bound vs memory, fetch-lat vs fetch-bw) is Report 02;
   the Level-3 memory verdict is Report 04.
5. **The signature heatmaps agree cell by cell on absolute scales**: scikit tool IPC 0.69 vs
   0.64 with DSB 82 vs 84 %; harness IPC 2.4–2.9 in both campaigns; the tool-side
   instruction-cache pain (L1I-pressure proxy 19–31 on astropy/sympy in both, scikit tool at
   the 1.1–1.6 floor) shows up on both sides. Fixed hardware anchors are what make
   "same color = same meaning" hold across figures and campaigns.
6. **Read IPC only together with the TMA buckets**: the harness's IPC 2.4–2.9 and 40 %
   retiring measure smooth instruction *flow*, not useful work — CPython retires many
   instructions per unit of real progress (and this study's CUDA-busy-wait result makes the
   same point at IPC 3.6).
7. **Reuse the kit for derived numbers.** The per-run harvest is 47 lines because it drives
   the kit plotter per single-run spec instead of re-parsing windows; the earlier co-counted
   denominator bug (~8× dilution) is exactly the class of error a second implementation
   would reintroduce silently.

---

**Method update (2026-07-30).** `run_glm_campaign.sh` changed after this report was written,
in ways that do not alter this study's banked data but do alter the harness a reproducer runs:
the dry-run numpy workloads now resolve a numpy-capable interpreter (`dry_python()`; bare
`python3` no longer has numpy on this workstation), the ISO-PROOF quiet check settles-and-retries
up to 8×4 s (2.0 %/core threshold unchanged — the single sample used to land in the
cpuset-migration drain), and episode liveness keys on the highest `STEP N` seen rather than the
literal "STEP 2" banner (which SWE-agent does not always emit). Evidence and rationale:
report 16 §2.2. The method as described in this report is what was in force when this study's
data was captured.

---

**Method update (2026-07-30, evening).** `plot_glm_results.py` changed after this report: the
harness-anatomy figure's cost-dynamics row had a hardcoded 1×4 sub-grid and crashed on specs
with 5+ tasks — silently, because every preceding figure (including all of this report's) had
already been written. The grid now scales with the task count. No figure this report documents
changes in content; the fix exists so the mentor-requested 5- and 6-task cross-campaign
variants (`local_agents/cross_campaign/`, report 14) render completely.
