# replay_trajs — the portable replay inputs for the P7 profiling pass

298 minimized trajectories (29 MB) covering every banked episode of the typeid sweep
(`ML_typeid`, 289) and the multilingual extension (`ML_multiling`, 9). These are the files to
carry to the P7 station to run instrumented replays. They are **transport copies, not
evidence** — see "What was removed".

## Why these exist

The banked trajectories total **9.57 GB**; 18 of them are over GitHub's 100 MB hard limit
(largest: `prometheus__prometheus-9248` at 208 MB), which is why
[`.gitignore`](../../../.gitignore) keeps `ML_typeid/data/` local. But `sweagent run-replay`
does not read the part that makes them big. Per
`agentic/swe_agent/external/SWE-agent/sweagent/run/run_replay.py`, it reads exactly two things:

- `replay_config` (`_get_config_from_agent`, L96-100)
- `history`, filtered to `role == "assistant"`, keeping only `content` and `tool_calls`
  (`_create_actions_file`, L156-166)

Everything else — every observation, file dump, test log and build log the agent ever saw — is
recomputed by re-executing in the sandbox, which is the point of a replay. Stripping it gives
**9.57 GB → 27.9 MB (351x)**; the 208 MB prometheus trajectory becomes 0.13 MB.

## What was removed, and what that costs

Removed: the `trajectory` array, `info`, and all non-assistant `history` turns (tool output,
user and system turns). **The replayed action sequence is unaffected** — that is asserted, not
assumed (below). What these files can no longer support is any *observation*-derived number:
token counts, per-call output sizes, the argv witness, anything reading what the agent saw.
For that, use the banked `.traj` on the machine that recorded it. The banked files stay
byte-identical and stay local; `MANIFEST.tsv` carries each source's SHA-256 so a transport
copy can always be traced back to the evidence it came from.

## Verification (2026-08-21)

Two independent checks, both over all 298:

1. **In the tool.** `minimize_traj.py` extracts the action list from source and minimized copy
   using run_replay.py's own rule and refuses to write on any difference. 298/298 written.
2. **In SWE-agent.** Driving the real `RunReplay._create_actions_file()` — full
   `RunSingleConfig` validation plus the function-calling assertions — over the localized
   copies: **298/298 replay-ready, 0 broken** (291 action-for-action exact; 7 with one
   harness-abort turn dropped, see below). Spot-checked head-to-head on
   `prometheus__prometheus-9248`: 237 actions from the 208 MB original and from the 0.13 MB
   copy, identical lists.

Two pre-existing conditions surfaced during this, neither caused by minimizing:

- **9 multilingual trajectories carry the foreign root `/home/thu/InferSuite`** — they were
  recorded on the P7. `RunSingleConfig` rejects them here until
  [`localize_traj.py`](../../kit/replay/localize_traj.py) rewrites the root. **On P7 they are
  native and need no localization.**
- **7 trajectories carry a harness-abort turn** (an assistant turn with no `tool_calls`, e.g.
  "Exit due to multiple consecutive command timeouts"), which `run-replay` asserts against.
  `localize_traj.py` drops them — they are not actions, nothing executed. Affected:
  `axios-5316`, `fluentd-3640`, `lombok-3486/3571/3674/3697`, `bat-1892`.

## Using them on P7

```bash
# 1. localize (rewrites foreign repo roots, drops harness-abort turns).
#    Prints the path to replay — the original if no rewrite was needed.
TRAJ=$(python3 local_agents/kit/replay/localize_traj.py \
         local_agents/ML_typeid/replay_trajs/<instance>.min.traj --repo /home/thu/InferSuite)

# 2. replay under the instrument stack (no model call, no proxy)
TRAJ_OVERRIDE="$TRAJ" ./measure.sh typeid replay <instance>
```

`TRAJ_OVERRIDE` is read by `typeid_replay_episode` in
[`run_glm_campaign.sh`](../../kit/campaign/run_glm_campaign.sh); without it the runner looks
for a banked `.traj` under `ML_*/data/`, which is not present on P7.

The 30-task profiling subset is [`../selection_30.tsv`](../selection_30.tsv); all 298 are
provided so the subset can be changed on P7 without another transfer.

## Files

| File | What |
|---|---|
| `<instance>.min.traj` | minimized trajectory, one per episode (298) |
| `MANIFEST.tsv` | `instance`, source campaign, source/minimized bytes, assistant turns, **source SHA-256** |

Regenerate with [`minimize_traj.py`](../../kit/replay/minimize_traj.py) on the machine holding
the banked data.
