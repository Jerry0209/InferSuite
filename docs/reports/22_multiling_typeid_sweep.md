# Report 22 — First-live-run type identification over SWE-bench Multilingual (ML_typeid)

**Date of study:** 2026-08-10 → 2026-08-17 · **Author of record:** Jerry, with Claude Code
**Deck slides:** none yet — this study *selects* the ≤30 ⟨language, type⟩ representatives the
next P7 profiling campaign (and its slides) will be built on.
**Cross-refs:** `local_agents/ML_typeid/README.md` (operating protocol) · report 17 (the static
sampling frame this supersedes with measurements) · `sampling_frame/classification_protocol.md`
(label semantics) · branch `multiling-type-id`.

---

## 1. Key summary

The mentor's question: what *type* of workload is each SWE-bench Multilingual task under
SWE-agent × GLM-5.2, measured — not predicted — so that ≤30 ⟨language, type⟩ representatives
can be chosen for isolated profiling on the P7 workstation. Method in one sentence: one cheap
live episode per remaining task (285 of 300; 15 were consumed by earlier campaigns) on a
non-P7 machine, under classification-only instruments — exact cgroup fences, a 2 Hz argv
witness, per-call token logging; no isolation, no PMU — each episode reduced to
**mechanism (static, argv-witnessed) × realized behaviour × magnitude bin × viability flags**
in `typing_ledger.tsv`. Headline: **all 285 episodes classified with zero failures** — 284 in
one resumable 85 h run (2026-08-10 17:11 → 08-14 06:35, ~1.57 B prompt tokens), the 285th
re-run 2026-08-17 after a name-collision skip (§2.2 H2); the behavioural axis **collapses
corpus-wide** (search-led in 266/285; edit- and build-led lead **zero** episodes), the only
real behavioural structure is interpreted-suite search/test co-dominance (all 15 mixed
episodes are PHP/Ruby, across 6 repos), and magnitude bins are nested by mechanism
(Rust 36/42 `large` vs PHP 18/39 `below-floor`).

## 2. Methodology

### 2.1 Load-bearing decisions

| decision | value | why |
|---|---|---|
| Machine | local i7-14700 (`bz-network-ws02`), not P7 | P7 is shared and contended; classification needs no valid counter rates, so the sweep costs the P7 nothing |
| No isolation / no PMU | TYPEID mode: skip shield, ISO-PROOF, perf, TMA, records | isolation exists to make *rates* valid; `cpu.stat` fence *attribution* is exact kernel accounting under any contention; magnitudes are used only as coarse bins and re-judged by the P7 layer-3 stop gate before any profiling minutes |
| Episode scopes | `systemd-run --user` (no sudo), full-online-range taskset | fences without P7 partition assumptions; the certified sudo/slice path stays untouched |
| Label rules | imported from `behavior_classify.py` (`act_class`/`episode_label`/`credits`), unchanged | byte-identical rules to the 16 previously measured episodes — labels stay comparable; forking the rules would fork the ontology |
| Process witness | live 2 Hz argv log of the tool cgroup (`cmdlog.tsv`) | realized-mechanism evidence (the gin failure mode: class A, warm cache, compile ≈ 0) + the mandatory bootstrap correction; poll counts are presence, never weights |
| Token time-series | per-episode litellm proxy + `usage_logger.py` callback → `proxy_usage.jsonl` | the `.traj` banks only cumulative usage; the callback gives per-call rows on the host epoch clock (same clock as the pollers) with zero workload perturbation |
| Agent config | frozen certified config: temp 0.6, `LOOP_GUARD_N=12`, drain 2400 s | behaviour differences must be attributable to tasks, not config drift; temp 0.0 is a known agent-breaker |
| Sweep order | language-interleaved round-robin | the ⟨language, type⟩ matrix fills evenly; a partial sweep is still a stratified sample |
| Magnitude bins | `below-floor` < 10 ≤ `measurable` < 60 ≤ `large` core-s (`TYPEID_FLOOR`/`TYPEID_LARGE`) | PROVISIONAL this-machine values (P7 floor is 20 core-s); bins are ordinal screens, pending calibration by re-running 2–3 banked instances here |
| Hygiene / halts | image pull→run→rmi+prune per episode; abort on 2 consecutive starved episodes; `STOP` file | bounded disk on a 285-image corpus; credit exhaustion mimics model failure (empty turns) and must halt, not burn days |

### 2.2 Verification and hazards

**Verification before spend:** (V1) the classifier run on the banked `rubocop-13668` episode
reproduces its published record — realized S, tool fence 59.07 vs 59.1 core-s, uniqueness
0.973; (V2) a zero-token infra episode (unfunded key → upstream 429) exercised proxy,
callback, sandbox creation, cgroup discovery, and teardown before any paid call; (V3) on the
first paid episode, per-call accounting was exact: 132 JSONL rows = 132 `api_calls`.

**Hazards hit (a reproducer will hit them too):**

| # | hazard | resolution |
|---|---|---|
| H1 | dangling-image accumulation: 271 GB by episode 126 — `docker rmi` only *untags*; swe-rex builds a derived image per episode that keeps the base entry alive, and the tagged-only GC never frees it | `docker image prune -f` folded into the driver per episode — never between episodes (it can race swe-rex's next legacy build) |
| H2 | run-dir name collision: `apache__druid-13704` and `apache__lucene-13704` both mapped to short `apache-t13704`; lucene silently skipped as "banked" | shorts now derive from the full `owner-repo-number`; lucene re-run 2026-08-17 (realized S, 10.2 core-s, flag-free) |
| H3 | liveness probes: `pgrep -f` matches the probing shell's own command line — days of false "sweep running" | bracket-pattern probes (`pgrep -f '[t]ypeid_sweep'`) or `pgrep -x` |
| H4 | degenerate episodes are common: 37/285 (13 %) E7 consecutive-loop (loop-guard interventions included), 2 cyclic-loop, 14 mechanism-not-witnessed; ~110 episodes carry minor call/step offsets (model retries) | all recorded as *flags*, not failures — episodes stay classified but flagged rows are ineligible as representatives |

**Known limits:** one seed per task (temp 0.6) — a realized label is a *prior* the P7 episode
must confirm; single-episode magnitude carries the 5.33× seed-noise floor (report 17), which
is why bins, not numbers, are recorded; the argv witness misses processes shorter than ~0.5 s.

### 2.3 Reproduction recipe

```bash
git checkout multiling-type-id
./measure.sh typeid preflight                     # env checks, no spend
nohup ./measure.sh typeid sweep > local_agents/ML_typeid/nohup.log 2>&1 &
./measure.sh typeid matrix                        # live ⟨language, type⟩ matrix
touch local_agents/ML_typeid/STOP                 # clean stop; rerun sweep to resume
```

Costs: ~85 h wall serialized (mean episode 989 s, median 836 s, max 2492 s at the drain cap);
~1.57 B prompt tokens ≈ 5.5 M/episode (context re-send dominated); ~1–4 GB image pull per
episode, disk bounded by rotation. Prereqs on a fresh machine: SWE-agent venv at the banked
hash `3ea751c0` + swe-rex 1.4.0, litellm venv from `litellm_venv_freeze.txt`, funded key at
`~/.glm_key`. What reproduces: the label distribution, the co-dominance structure, the bin
nesting — not per-task trajectories (stochastic agent).

### 2.4 Scripts and artifacts

| item | repo location | role |
|---|---|---|
| `typeid_sweep.sh` | `local_agents/kit/campaign/` | resumable driver: image lifecycle, episode, classify, halts |
| `typeid_classify.py` | `local_agents/kit/campaign/` | population, per-episode record, ledger, matrix |
| `run_glm_campaign.sh` (`typeid-*` stages) | `local_agents/kit/campaign/` | TYPEID light mode: user-scoped episode, pollers, cmdlog |
| `usage_logger.py` + `litellm_glm_typeid.yaml` | `local_agents/kit/campaign/` | per-call token JSONL via proxy callback |
| `behavior_classify.py` | `local_agents/kit/replay/` | the imported (frozen) behavioural label rules |
| `typing_ledger.tsv` | `local_agents/ML_typeid/` | one row per attempt — the study's product (tracked) |
| per-episode data | `local_agents/ML_typeid/data/glm_swe_*/run_1/` | traj, 3 fence pollers, cmdlog, usage JSONL, summary (local-only) |

## 3. Key insights (most → least important)

1. **The behavioural axis collapses at corpus scale.** Edit- and build-dominated episodes do
   not exist (0/285 each); search leads 266/285. The mentor's search/edit/test/build task
   typology is a property of *this agent*, not of the tasks — report 17's 16-episode claim,
   now at 18× the sample.
2. **The only real behavioural structure is interpreted-suite co-dominance.** All 15 mixed
   episodes are PHP (11) or Ruby (4), spread over 6 repos — cheap, fast test suites pull the
   agent into the verify loop. A language-family-level claim (was n=1 in July).
3. **Test-led behaviour exists but is rare and fragile.** 4 episodes: 1 is a degenerate
   artifact (`jq-2650`, T=91 % from a cyclic loop, no toolchain witnessed) and 3 are viable —
   `rubocop-13627` (T=79 %, flag-free, `large`), `phpspreadsheet-3463` (63 %), `tokio-4898`
   (53 %). The T column of the selection matrix rests on these three.
4. **Magnitude is nested by mechanism, orthogonal to behaviour.** `large` fences: Rust 36/42,
   Go 31/39, Java 29/42, C++ 11/11; `below-floor`: PHP 18/39, Ruby 8/43 (36 tasks total).
   Compiled/AOT/JVM tasks are nearly all profitable to profile; 36 interpreted-side tasks
   would have parked on the P7 — the sweep's cheapest concrete saving.
5. **Degeneracy gating is load-bearing, not paranoia.** 13 % of episodes tripped E7; without
   the flags, roughly one in eight "representatives" would be a loop artifact.
6. **Token cost is context re-send.** ~5.5 M prompt tokens/episode against ~1.5 k received;
   Δprompt attribution pins the growth to file-view and test-output observations — the
   single biggest lever on agent API cost in this corpus.
