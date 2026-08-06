# Figure gallery (curated view)

This directory is a *view*: never edit figures here — regenerate at the source and re-run
`scripts/sync_plots.sh`.

**Live sets:**

- `agents/swe_clean/` ← `local_agents/SWE_clean/plots/` — the hardened SWE-agent × GLM-5.2
  campaign on SWE-bench (Xeon w5-3425 workstation, nohz_full boot isolation, ISO-PROOF gate,
  zero-mux windowed counters, continuous TMA). The MANIFEST at the source documents every
  figure; `plot_spec.json` there names the featured runs.
- `spec26/` ← `spec26/plots/` — the SPEC CPU 2026 traditional-workload baseline that anchors
  the agentic numbers (26 benchmarks, ref inputs, 1 copy on 1 isolated SMT-free core, the same
  eight certified counter groups). Its MANIFEST states which population feeds each figure and
  carries the standing SMT/contention caveats; see `spec26/README.md`.

**History:** until 2026-08-05 this tree also carried frozen snapshots of the retired
service/GPU/engine/OpenClaw studies (`service/`, `gpu/`, `engine/`,
`agents/{oc_clean,h100,local,local_api}`), and a sibling `results/` tree held a symlink
data-view. All were deleted in the SWE-narrowing cleanup after verifying them on GitHub —
recover any of them with `git checkout 8d87e0ee -- <path>`.
