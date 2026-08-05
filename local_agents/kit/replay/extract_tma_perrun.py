#!/usr/bin/env python3
"""Extract per-run TMA L1 (tool+harness) for all runs of both campaigns by invoking the
kit plotter per single-run spec and harvesting values_dump.json."""
import json, os, subprocess, sys, tempfile

PY = "/home/thu/miniforge3/envs/infersuite-full/bin/python3"
PLOTTER = "/home/thu/InferSuite/local_agents/kit/plot/plot_glm_results.py"
SP = "/tmp/claude-1006/-home-thu-InferSuite/d89d5011-7a68-46e3-b344-4c6f84677c31/scratchpad"
CAMPS = {
    "moh": "/home/thu/llm-service-kernel-latest/archive/certified_glm_40min",
    "new": "/home/thu/InferSuite/local_agents/superseded_40min/data",
}
TASKS = ["scikit-learn", "astropy", "sympy", "django"]
SKIP = {("moh", "django", 1)}  # empty traj

out = {}
for camp, root in CAMPS.items():
    for t in TASKS:
        for r in (1, 2, 3):
            if (camp, t, r) in SKIP:
                continue
            d = f"{root}/glm_swe_{t}/run_{r}"
            if not os.path.isdir(d):
                continue
            with tempfile.TemporaryDirectory(dir=SP) as td:
                spec = {
                    "data": root, "out": td,
                    "resolved": [[f"{t} (Python)", f"glm_swe_{t}", [f"run_{r}"]]],
                    "outcome": {f"{t} (Python)": "resolved"},
                    "stop_before_hw": True,
                }
                sp = f"{td}/spec.json"
                json.dump(spec, open(sp, "w"))
                env = dict(os.environ, PLOT_SPEC=sp, MPLBACKEND="Agg")
                res = subprocess.run([PY, PLOTTER], env=env, capture_output=True, text=True, timeout=900)
                vd = f"{td}/values_dump.json"
                if not os.path.exists(vd):
                    print(f"FAIL {camp} {t} r{r}: {res.stderr.strip().splitlines()[-1] if res.stderr else 'no dump'}", flush=True)
                    continue
                v = json.load(open(vd)).get(f"{t} (Python)", {})
                out[f"{camp}/{t}/r{r}"] = {
                    "tma_tool": v.get("tma_tool"), "tma_harness": v.get("tma_harness"),
                }
                print(f"OK {camp} {t} r{r}", flush=True)

json.dump(out, open("/home/thu/InferSuite/local_agents/superseded_40min/data/l3_study/tma_allruns.json", "w"), indent=1)
print(f"DONE {len(out)} runs -> {SP}/tma_allruns.json")
