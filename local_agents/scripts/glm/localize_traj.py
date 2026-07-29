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
if not roots:
    print(TRAJ)          # already local — replay the banked file directly
    sys.exit(0)

if PRINT_ONLY:
    print("\n".join(sorted(roots)), file=sys.stderr)
    print(TRAJ); sys.exit(0)

out = OUT or re.sub(r"\.traj$", ".local.traj", TRAJ)
new = raw
for r in roots:
    new = new.replace(r + "/agentic/swe_agent/", REPO + "/agentic/swe_agent/")
json.loads(new)          # fail loudly rather than write a corrupt trajectory
with open(out, "w") as fh:
    fh.write(new)
print(out)
print(f"localized {len(roots)} foreign root(s): {', '.join(sorted(roots))} -> {REPO}",
      file=sys.stderr)
