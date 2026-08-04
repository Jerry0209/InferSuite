#!/usr/bin/env bash
# sync_plots.sh — refresh the curated figure gallery at plots/ from the CURRENT generator
# output locations. plots/ is a VIEW: never edit it directly; regenerate figures at their
# source and re-run this script.
#
# SCOPE (narrowed 2026-08-04 to SWE-agent profiling): the only actively regenerated set is
# the SWE campaign. Everything else under plots/ (h100/, eks/, local_api/, service/,
# gpu/, engine/, agents/oc_clean) is a FROZEN snapshot — its sources were removed from the
# tree (git history has them) and it is deliberately NOT resynced or deleted here.
set -euo pipefail
cd "$(dirname "$0")/.."
R() { mkdir -p "plots/$2" && rsync -a --delete-after --exclude='*.json' "$1" "plots/$2/"; }

# ---------- live sets ----------
R "local_agents/SWE_clean/plots/" agents/swe_clean       # SWE-agent x GLM-5.2 hardened campaign

echo "synced -> plots/ ($(find plots -name '*.png' | wc -l) figures; legacy snapshots untouched)"
