# agentic/swe_agent — the SWE-agent harness (measured subject)

The unmodified SWE-agent checkout that the GLM campaigns drive. **All measurement is external
to it** — cgroup fences, perf counting, and pollers live in `local_agents/kit/`; nothing in
here is instrumented. The campaign runner (`local_agents/kit/campaign/run_glm_campaign.sh`)
activates `.venv` and invokes `sweagent run-batch --config external/SWE-agent/config/default.yaml`
per episode, then copies the output into the run's `traj/`.

| Entry | What it is |
|---|---|
| `external/SWE-agent/` | The upstream SWE-agent checkout (harness code + configs). |
| `.venv/` | The harness venv (gitignored); campaign preflight checks it exists. |
| `runs/` | sweagent per-episode output (`runs/<tier>_live/<inst>_r<N>`), gitignored; the campaign copies each episode's dir into the banked run's `traj/`. |
| `trajectories/` | sweagent's default trajectory store, gitignored. |
| `evals/` | SWE-bench official-eval evidence for GLM-era episodes (django r1–r3, babel; per-instance `run_evaluation` logs + report JSONs) — kept as resolution-status proof for the campaign runs. |

History: this directory started as the June-2026 local-vLLM wiring experiment; its pre-GLM
top-level scripts (local-vLLM/minikube launchers, hosted-Claude API runs, their plotters,
figures, and eval logs) were deleted 2026-08-05 in the SWE-narrowing cleanup — recover from
git history if ever needed.
