# Decision: lineage fork/exec fencing for OpenClaw

| Field | Value |
|---|---|
| Owner | LLM maintained, human reviewed |
| Status | Validated |
| Last updated | 2026-07-29 |
| Sources | [CLAUDE.md](../../../CLAUDE.md), [oc_lineage_watcher.py](../../../local_agents/scripts/glm/oc_lineage_watcher.py) |

## Context

OpenClaw runs the Node gateway and every tool it spawns inside **one** container — no container
boundary separates agent work from tool work. The fences must be reconstructed some other way.

## Decision

Split **agent** vs **toolexec** sub-cgroups by **process lineage** via the kernel's netlink proc
connector. A `fork` by the gateway stays agent-side; the moment it `exec`s a program it becomes a
**tool root** (name-blind), and cgroup inheritance carries all its descendants. Pre-move residency
is corrected at plot time; gate **E4** checks fence purity against the lineage log.

## Alternatives rejected

- **Name-based fencing.** *Fact:* fails both ways — spawned Node tools carry the gateway's process
  name (fully misattributed), and short-lived processes die between polls. Only the fork+exec rule
  works.

## Consequences

- Turn boundaries for OC **cannot** come from harness activity: the gateway has continuous
  background CPU, so activation-clustering over-segments episodes (~5× too many "turns"). OC turns
  come from the transcript's per-message timestamps; SWE turns (from harness activations) are
  validated against the logged step count. See [measurement ontology](../concepts/measurement-ontology.md).

## Related pages

- [Agent measurement design](../architecture/measurement-design.md) (fences are cgroups)
