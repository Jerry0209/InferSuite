#!/usr/bin/env python3
"""minimize_traj.py — strip a banked trajectory down to the part `sweagent run-replay`
actually reads, so the replay inputs can be moved between machines (here -> P7).

Why this exists: a banked .traj is 10-200 MB because it stores every observation the agent
ever saw — full file dumps, test output, build logs. `run-replay` reads NONE of that. Read
external/SWE-agent/sweagent/run/run_replay.py: `_get_config_from_agent` takes `replay_config`,
and `_create_actions_file` walks `history`, skips every item whose role is not "assistant",
and keeps exactly two fields of the ones it keeps — `content` and `tool_calls`. The replayed
action sequence is therefore a function of those fields alone; the observations are recomputed
by re-executing in the sandbox, which is the entire point of a replay.

Measured over the 298 banked typeid + multilingual trajectories (2026-08-21): 9.57 GB -> 27.9 MB
(351x; the 208 MB prometheus-9248 becomes 0.13 MB). That is what makes the replay set portable
at all — 18 of those files are over GitHub's 100 MB hard limit as banked.

This is a TRANSPORT format, not a replacement for the evidence. The banked .traj stays
byte-identical and stays on the machine that recorded it: it is the measurement record, and
every observation-derived number (token counts, per-call output sizes, the argv witness) needs
the full file. Only replay needs the minimized one.

Safety: the minimized copy is written only if the action list extracted from it — by the same
rule run_replay.py uses — is IDENTICAL to the one extracted from the source. A trajectory that
would replay differently is refused, not written.

Downstream unchanged: minimize (here) -> copy to P7 -> localize_traj.py (rewrites foreign repo
roots, drops harness-abort turns) -> `sweagent run-replay`. Path strings live in `replay_config`
and are preserved verbatim, so localization still works on the minimized file.

Usage:
  minimize_traj.py <traj> [--out <path>] [--quiet]
Prints the path written. Exit 1 if the trajectory cannot be minimized safely.
"""
import json, os, re, sys


def actions(data):
    """The action list run_replay.py builds — the invariant that must survive minimizing."""
    out = []
    for item in data.get("history") or []:
        if item.get("role") != "assistant":
            continue
        out.append((item.get("content"),
                    json.dumps(item.get("tool_calls"), sort_keys=True)))
    return out


def minimize(data):
    """replay_config + assistant turns, three fields each. Abort turns (assistant, no
    tool_calls) are KEPT: dropping them is localize_traj.py's job, and keeping them here is
    what lets the action-equivalence check above be exact rather than approximate."""
    return {
        "replay_config": data.get("replay_config"),
        "history": [{k: v for k, v in item.items()
                     if k in ("role", "content", "tool_calls")}
                    for item in data.get("history") or []
                    if item.get("role") == "assistant"],
    }


def main(argv):
    if not argv:
        sys.exit(__doc__)
    traj = argv[0]
    out = argv[argv.index("--out") + 1] if "--out" in argv else \
        re.sub(r"\.traj$", ".min.traj", traj)
    quiet = "--quiet" in argv

    src = json.loads(open(traj).read())
    if src.get("replay_config") is None:
        print(f"ERROR: {traj} has no replay_config — run-replay cannot use it "
              f"(old trajectory?)", file=sys.stderr)
        return 1
    small = minimize(src)
    if not small["history"]:
        print(f"ERROR: {traj} has no assistant turns — nothing to replay", file=sys.stderr)
        return 1

    text = json.dumps(small)
    if actions(json.loads(text)) != actions(src):     # refuse rather than write a wrong replay
        print(f"ERROR: {traj} action list changed under minimizing — refusing to write",
              file=sys.stderr)
        return 1

    with open(out, "w") as fh:
        fh.write(text)
    print(out)
    if not quiet:
        a, b = os.path.getsize(traj), len(text.encode())
        print(f"minimized {a / 1048576:.1f} MB -> {b / 1048576:.2f} MB ({a / b:.0f}x), "
              f"{len(small['history'])} assistant turns, action list identical",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
