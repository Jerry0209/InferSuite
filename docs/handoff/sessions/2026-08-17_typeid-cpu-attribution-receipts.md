# Session 2026-08-17 — typeid CPU attribution: per-PID sampler, taskstats receipts, token-free replay sweep

**Goal:** turn the collapsed ⟨language × realized-behaviour⟩ matrix (215/225 search-led — no
stratification power) into a measured ⟨language × CPU-type⟩ matrix, by attributing tool-fence
CPU to the processes that actually burned it, without spending API tokens.
**Machine state at start:** local type-id box (`bz-network-ws02`, i7-14700, 28 threads, no
isolation), branch `multiling-type-id`. 285/285 typeid live episodes banked with trajectories;
GLM sweep complete. No other captures running. Passwordless sudo available.

## Decisions
| # | Decision | Why | Made by |
|---|---|---|---|
| 1 | Classify types from **CPU consumption by process**, not action counts | measured on 8 tasks with instruction-weighted truth: action mix vs CPU mix are opposite answers (jq: build actions 18% vs build CPU 92%; E is literally 0% of CPU everywhere) | user |
| 2 | Presence-weighted estimation (cmdlog ticks × fence delta) is **rejected** | validated against l3 truth: keeps the leader only 6/9, inflates `search` 1.5–66× (a grep alive during a compile takes an equal share) | Claude, user confirmed |
| 3 | Re-runs are **replays of banked trajectories** (`sweagent run-replay`), never new live episodes | zero tokens; model wait was 86.9% of live wall (67.4 h across 285); replay reproduced live fence CPU to 0.98–1.04 same-machine (n=3), step counts 41/41, 64/64, 92/92 | user |
| 4 | Add 2 Hz **per-PID `/proc` sampler** (`pidcpu_poll.py`) to typeid instruments | joins "who ran" to "how much CPU" exactly; no perf, no isolation needed | Claude |
| 5 | Add **taskstats exit receipts** (`taskstats_listen.py`, netlink, sudo) | the sampler structurally misses processes shorter than its interval (jq coverage 12.3%); faster polling bought coverage, not accuracy (2→10 Hz: jq 12→25%, error 7.7→7.7 pt). Exit-time accounting closes it: coverage 96.7–97.0% on all three strict cases | user asked to try; validated |
| 6 | Accounting uses **P receipts only** (per-task); G aggregates dropped | every thread dies exactly once → Σ P is double-count-free; single-threaded processes emit no G row at all | Claude |
| 7 | Fence attribution = **offline lineage walk** over receipt ppid graph, roots = pids ever seen in the tool cgroup | receipts are machine-wide; ppid chains resolve regardless of death order | Claude |
| 8 | Matrix and ≤30 selection use the **OWNERSHIP** view; PROCESS view banked alongside | ownership (nearest driver front-end owns the CPU) reproduces the P7 window truth ≤9.1 pt on all 3 strict cases; process view is the mechanism measurement but its coarse S/T/B projection is context-blind for driver children and repo-payload binaries | Claude, pending user confirmation on selection |
| 9 | Full replay sweep launched over 285 banked + 11 old consumed instances | user asked "rerun 300"; 296 replayable, 4 gaps have no trajectory anywhere | user |

## What changed
- **New instruments** (repo, uncommitted): `local_agents/kit/campaign/pidcpu_poll.py` (2 Hz
  per-PID utime/stime + per-tick cgroup total for residual bounding),
  `local_agents/kit/campaign/taskstats_listen.py` (netlink exit receipts; `--probe` gates on
  capability; self-test: receipt 1.507 s vs `/usr/bin/time` 1.50 s).
- **run_glm_campaign.sh**: `start_pidcpu` (env `PIDCPU_IV`), `start_taskstats` (probe-gated),
  new `typeid_replay_episode` + `typeid-replay` dispatch (user-scope, no proxy, times image
  pull separately).
- **measure.sh**: `./measure.sh typeid replay <instance>` and `typeid replay-sweep`.
- **local_agents/kit/campaign/typeid_replay_sweep.sh**: resumable sweep driver; worklist from
  metadata.json `extra.instance` (never short-name reconstruction — `-t<num>` collides for
  apache druid-13704 vs lucene-13704); redoes any replay lacking receipts; disk floor + GC;
  `STOP_REPLAY` stopfile.
- **local_agents/kit/campaign/typeid_cpu_matrix.py**: builds `ML_typeid/cpu_matrix.tsv`
  (both views + coverage + classified% + labels with MARGIN=10); `matrix` subcommand prints
  ⟨language × CPU-type⟩. Verified end-to-end on the 3 receipt-bearing dirs.
- **Captures (gitignored data):** pilot replays `glm_replay_swe_{tokio-rs-t6838,google-t1100,
  php-cs-fixer-t7875}` (pidcpu only), strict set `…-{L3t,L3f}{7523,2681,6551}` (pidcpu, 2 Hz +
  10 Hz), receipt set `…-X{2681,6551,7523}` (full instruments). **Full sweep launched 15:14**,
  log `local_agents/ML_typeid/replay_sweep.log`, ~10–15 h expected, stop via
  `touch local_agents/ML_typeid/STOP_REPLAY`.
- Analysis scratchpad (session-local, promoted where durable): `two_axes.py` (figs 1–3),
  `cpu_axis.py` (rejected presence estimator), `validate_estimator.py`, `pilot_report.py`,
  `receipt_report.py`, figs 4–6.

## Defects found
- **Presence-weighted CPU estimation** would have shipped `search` = 31.8% of corpus tool CPU;
  instruction-weighted truth on the 9 P7 tasks puts search at 0.8–15.8% per task (gson ×66
  inflation). Rejected before any figure used it.
- **`typeid_sweep.sh` (committed) computes `SHORT="${INST%%__*}-${INST#*__}"` but the banked
  dirs use `-t<num>`** — the committed name also collides (apache druid vs lucene both →
  `apache-t13704` under the banked scheme; the banked tree disambiguated lucene by hand as
  `apache-lucene-13704`). Replay sweep sidesteps by keying on metadata; the live sweep script
  still carries the hazard for any future org with two repos.
- **tokio "A-class refutation" is an ontology artifact**: window truth (ownership) says
  compile 11%, exact per-process receipts say rustc+ld = 51.9 core-s ≈ half the fence
  (`TAG_PRIORITY` swallow, third independent confirmation). The 5/9 validation scoring of
  class A/N should be re-judged on the process view before being quoted.
- Earlier session figure claim "9 languages, 41 repos" for the typeid ledger corrected to
  **35 repos** (225 classified rows at the time).
- **7/285 banked trajectories cannot `run-replay` as-is** (axios-5316, fluentd-3640,
  lombok-3486/3571/3674/3697, bat-1892): when the harness aborts an episode (consecutive
  command timeouts ×6, EOF ×1) it appends a synthetic assistant turn without `tool_calls`;
  `run-replay` asserts on it before launching the sandbox (fails in 3 s, no measurement
  wasted). Fixed in `localize_traj.py`: the `.local.traj` copy drops those turns (they are
  not actions — nothing executed); the banked file stays byte-identical. Sweep part A now
  routes every trajectory through the localizer. The 7 are re-tried on the next sweep
  invocation (resumable). First noticed at 18:59 (`FAIL episode axios-t5316`), 24 done at
  that point.

## Sweep outcome (2026-08-19 05:48)
- **296/296 replayed with receipts, 0 unrecoverable failures**, 38 h wall (15:14 Aug 17 →
  05:48 Aug 19; part A 278 + 7 retried after the localizer fix + part B 11). Zero tokens.
- Corpus-wide replay/live fence ratio (n=284): **median 0.995, IQR 0.93–1.09**; 163 within
  ±10%, 231 within 0.8–1.25×.
- **Matrix** (`ML_typeid/cpu_matrix.tsv`, ownership view, n=296): B 56 / T 160 / M 9 / ? 71.
  S column empty after gating — every S candidate was an ~11 core-s all-scaffold fence
  (agent never invoked the toolchain) or git-checkout CPU. C 12/6/1, Rust 17/20/5,
  Go 14/17/3 populate two–three types each; Java/JS/TS/Ruby are T-only; C++ B-only.
- **Selection** (`ML_typeid/selection_30.tsv`): 30 picks, 16 populated cells covered, 28
  repos, 9 languages; runner-up per cell where one exists. All picks are priors.
- Figures (scratchpad): fig7_matrix.png (matrix + picks).

## Defects found (sweep phase)
- **lucene is replay-invalid** (8/9 rows at 0.07–0.29× live): gradlew's `timeout 5 curl
  services.gradle.org` network check fails in the replay container, so gradle never runs
  the JVM tests — replay measured bootstrap, not tests (java cmdlog hits 3566 live vs 615
  replay). Caught by the new `replay-invalid` gate (ratio outside [0.5, 2]) → labelled `?`.
  Would otherwise have shipped 8 lucene rows as T on 16–49 core-s of gradle failure.
- **Retried dirs double-counted receipts** (bat-1892 coverage 199%): the listener from the
  3-second failed first attempt kept writing after the dir was recreated. Fixed by
  deduping receipts on (pid, btime); only the 7 retries were exposed.
- **5 caddy replays are drain-capped** (ratio 0.32–0.44): `go test ./...` on caddy exceeds
  the 2400 s replay drain; caught by the same gate. Re-run at REPLAY_DRAIN_S=3600 if caddy
  cells matter (caddy-4774 selected for Go×B is a clean 0.98 row).
- Live-vs-replay ratio >2 on ~12 tiny PHP/Java fences (2–14 core-s): swe-rex bootstrap
  dominates both numerators; not a physics disagreement, and all were already `?`.

## Corpus completed + tagger census (2026-08-19 evening)
- **The 4 gaps were re-run live** by the user (14:44–15:58, fresh tokens, `gaps_run.log`):
  prometheus-9248 (217 core-s, classified), terraform-35543 (2.4, classified),
  carbon-2813 (4.9, **starved**), laravel-51890 (7.9, classified). Replayed 17:11–18:44.
  **Corpus is now 300/300**; all four land in no-evidence (prometheus coverage 52%,
  terraform ratio 4.98, carbon 2.99, laravel thin fence).
- **`other` census over 300 replays**: 1,374 core-s unnamed (3.1% of 44.3k core-s of
  in-fence receipts), 43,922 distinct comms but only 58 with >=1 core-s. Six families fixed
  in `typeid_cpu_matrix.py`; **`other` now 80 core-s (0.2%)**, nothing above 3.8 core-s.
  Two were the SAME bug: `comm` is truncated to 15 chars, so `lto1-ltrans` (482 core-s,
  redis/valkey LTO) and `integration.tes` never matched existing entries. Others: esbuild/swc
  -> compile (136 core-s — the class-N transpile term the window analysis measured as 0%),
  Rust test-thread names -> test-run, chromium threads -> test-run, clippy/rustfmt -> lint,
  javap/nm/strings -> search, dd/cmp/uname -> scaffold, py3compile/localedef -> pkg.
- **Defect introduced and caught in the same session**: the Rust thread-name rule
  (`::`, `/src/`) was unanchored and matched full argv, tagging every compile whose command
  line mentions a `/src/` path as test-run (`ld -o redis-server …/src/…`). It flipped redis
  and nlohmann BUILD->TEST in the ownership view. Now anchored (`^(?!/)[^ ]*(::|/src/)`),
  with a fixed regression list of known commands checked after every tagger edit.
- **Matrix n=300** (ownership) B 55 / T 162 / M 8 / ? 75; process B 94 / T 126 / M 3 / ? 77.
  The lto1 fix recovered 6 process-view rows (5 redis + valkey) from ? to B: C goes 5/8 ->
  11/8. Selection re-run: **identical 30 picks**.
- **Count-weighted classification piloted and rejected as the label** (supervisor's ask):
  leaf-command counts give B 61 / T 109 / S 60 / M 42 / ? 28 and agree with ownership on
  112/225 rows — but a counted search costs 2.2 ms vs 13.4 (test) and 35.7 (build), and the
  flips are toolchain plumbing (vue: `sort|uniq|wc` x4500; jq: 3,680 configure seds).
  Banked as columns `n_leaf, leaf_B, leaf_T, leaf_S, leaf_label` instead. The episodes where
  search leads BY CPU are all thin fences already gated `?` — the empty S column is a
  magnitude fact, not a weighting artifact.

## Open threads
- **Present the 30 to the user; P7 layer-3 verdicts on the picks** (the whole point).
- lucene: re-replay with network (or pre-warmed gradle) if Java×B/M cells are wanted — all
  9 lucene rows currently carry no CPU-type evidence.
- **Coverage/label gates for the matrix**: flag rows with coverage <80% or classified <50%
  as low-evidence rather than dropping.
- **Gaps with no trajectory**: prometheus-9248 (lost in migration), terraform-35543,
  carbon-2813, laravel-51890 — all four were rejected/lost episodes; decide exclude vs re-run
  live ($).
- **Weighting caveat to carry into any report**: core-second vs instruction weighting agree
  ≤2 pt on the 4 checkable tasks; busy-wait remains undetectable by any per-process counter —
  P7 TMA stays the verdict layer.
- 3× repeat replays for composition spread, and per-repo payload-binary registry (jq-style
  `other` comms), both cheap, not yet done.
- Study report for the receipt methodology: **user-invoked only** — not written yet.
