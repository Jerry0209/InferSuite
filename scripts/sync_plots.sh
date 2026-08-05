#!/usr/bin/env bash
# sync_plots.sh — refresh the curated figure gallery at plots/ from the CURRENT generator
# output locations. plots/ is a VIEW: never edit it directly; regenerate figures at their
# source and re-run this script.
#
# SCOPE (narrowed 2026-08-04 to SWE-agent profiling): the only set is the SWE campaign.
# The frozen legacy snapshots (service/, gpu/, engine/, agents/{oc_clean,h100,local,local_api})
# and the results/ symlink data-view were deleted 2026-08-05 after verifying them on GitHub
# (recover with: git checkout 8d87e0ee -- <path>).
set -euo pipefail
cd "$(dirname "$0")/.."
R() { mkdir -p "plots/$2" && rsync -a --delete-after --exclude='*.json' "$1" "plots/$2/"; }

# ---------- live sets ----------
R "local_agents/SWE_clean/plots/" agents/swe_clean       # SWE-agent x GLM-5.2 hardened campaign

echo "synced -> plots/ ($(find plots -name '*.png' | wc -l) figures)"
