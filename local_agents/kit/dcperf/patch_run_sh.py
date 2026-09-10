#!/usr/bin/env python3
"""patch_run_sh.py — generate the InferSuite-instrumented copy of DCPerf's feedsim run.sh.

Exactly two edits, so that DCPerf's workload configuration (every flag, thread count, graph
scale, jemalloc setting) is used verbatim and only the PLACEMENT of the two processes changes:

  1. the control shell pins itself to the housekeeping cores, so run.sh, search_qps.sh and
     DriverNodeRank (the load generator) never run on the measured partition;
  2. LeafNodeRank (the server under test) is launched into its own systemd scope under
     measured.slice -- the same mechanism run_glm_campaign.sh uses for the agent harness --
     with an explicit taskset to the measured cores.

Reads IS_CPUS_HOUSE / IS_CPUS_MEASURED / IS_LEAF_UNIT from the environment at run time.
Idempotent: regenerated from the pristine run.sh on every preflight.

    patch_run_sh.py <src run.sh> <dest run_infersuite.sh>
"""
import os
import sys

src, dst = sys.argv[1], sys.argv[2]
s = open(src).read()

# --- edit 1: keep the driver + control shell off the measured partition -------------------
anchor = "    set -u  # Enable unbound variables check from here onwards\n"
if anchor not in s:
    sys.exit("patch_run_sh: anchor for edit 1 not found (DCPerf run.sh changed?)")
s = s.replace(anchor, anchor + '''
    # [InferSuite] The load generator is the CLIENT, not the workload under test: pin this
    # shell (and therefore search_qps.sh and DriverNodeRank) to the housekeeping cores, the
    # same placement the litellm proxy gets during agent campaigns.
    taskset -pc "${IS_CPUS_HOUSE:?}" $$ >/dev/null 2>&1 || true
''')

# --- edit 2: the server runs inside the measured cgroup fence ------------------------------
old_leaf = ("    MALLOC_CONF=narenas:20,dirty_decay_ms:5000 "
            "build/workloads/ranking/LeafNodeRank \\\n")
if old_leaf not in s:
    sys.exit("patch_run_sh: anchor for edit 2 not found (DCPerf run.sh changed?)")
new_leaf = ('''    # [InferSuite] the SERVER is the measured workload: own systemd scope under
    # measured.slice (cgroup fence for perf --for-each-cgroup and the 10 Hz cpu.stat poller),
    # explicitly tasksetted to the measured cores. Flags below are DCPerf's, unmodified.
    systemd-run --collect --scope --slice=measured.slice --unit="${IS_LEAF_UNIT:?}" -- \\
      env MALLOC_CONF=narenas:20,dirty_decay_ms:5000 \\
      taskset -c "${IS_CPUS_MEASURED:?}" \\
      "${FEEDSIM_ROOT_SRC}/build/workloads/ranking/LeafNodeRank" \\\n''')
s = s.replace(old_leaf, new_leaf)

open(dst, "w").write(s)
os.chmod(dst, 0o755)
print(f"patch_run_sh: wrote {dst} (2 edits applied)")
