#!/usr/bin/env python3
"""localize_traj.py — rewrite foreign tool-bundle paths in a recorded trajectory so
`sweagent run-replay` can run it on THIS machine.

Why this exists: a .traj embeds the sweagent config that produced it, including absolute
`tools/<bundle>` paths. Trajectories recorded on another workstation (e.g. SWE_clean, captured
under /home/mohamad/llm-service-kernel-latest) make run-replay die at startup with
PermissionError on those paths — the sandbox never launches ("ERROR: no sandbox for replay").

The banked trajectory is measurement evidence and is never modified: this writes a localized
COPY next to it (default `<name>.local.traj`) with only the repo-root prefix substituted.

Usage:
  localize_traj.py <traj> [--repo /home/thu/InferSuite] [--out <path>] [--print]
Exit 0 and print the path to use for replay (the copy, or the original if no rewrite needed).
"""
import json, os, re, sys

args = sys.argv[1:]
if not args:
    sys.exit(__doc__)
TRAJ = args[0]
REPO = args[args.index("--repo") + 1] if "--repo" in args else "/home/thu/InferSuite"
OUT = args[args.index("--out") + 1] if "--out" in args else None
PRINT_ONLY = "--print" in args

raw = open(TRAJ).read()
# any absolute path ending in .../agentic/swe_agent/... that isn't already this repo
FOREIGN = re.compile(r'(/[^"\\\s]*?)/agentic/swe_agent/')
roots = {m.group(1) for m in FOREIGN.finditer(raw)} - {REPO}

# Second reason a banked trajectory cannot replay (found 2026-08-17, 7 of 285 typeid
# trajectories): when the harness ABORTS an episode (consecutive command timeouts, EOF), it
# appends a synthetic assistant turn — "Exit due to multiple consecutive command timeouts" —
# with no tool_calls. `run-replay` walks `history` and asserts every assistant turn carries
# tool_calls, so it dies before launching the sandbox. Those turns are not actions: nothing
# executed, and the CPU physics of the episode is unaffected by dropping them. The banked file
# is evidence and stays byte-identical; the localized copy omits them.
data = json.loads(raw)
hist = data.get("history") or []
dropped = [i for i, it in enumerate(hist)
           if it.get("role") == "assistant" and not it.get("tool_calls")]

if not roots and not dropped:
    print(TRAJ)          # already local and replayable — use the banked file directly
    sys.exit(0)

if PRINT_ONLY:
    print("\n".join(sorted(roots)), file=sys.stderr)
    if dropped:
        print(f"non-tool assistant turns at history idx {dropped}", file=sys.stderr)
    print(TRAJ); sys.exit(0)

out = OUT or re.sub(r"\.traj$", ".local.traj", TRAJ)
new = raw
for r in roots:
    new = new.replace(r + "/agentic/swe_agent/", REPO + "/agentic/swe_agent/")
if dropped:
    data = json.loads(new)
    keep = set(range(len(data["history"]))) - set(dropped)
    data["history"] = [it for i, it in enumerate(data["history"]) if i in keep]
    new = json.dumps(data)
json.loads(new)          # fail loudly rather than write a corrupt trajectory
with open(out, "w") as fh:
    fh.write(new)
print(out)
if roots:
    print(f"localized {len(roots)} foreign root(s): {', '.join(sorted(roots))} -> {REPO}",
          file=sys.stderr)
if dropped:
    print(f"dropped {len(dropped)} non-tool assistant turn(s) at history idx {dropped} "
          f"(harness abort messages, not actions)", file=sys.stderr)
