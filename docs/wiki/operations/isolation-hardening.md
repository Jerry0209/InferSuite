# Isolation & hardening

| Field | Value |
|---|---|
| Owner | LLM maintained, human reviewed |
| Status | Validated |
| Last updated | 2026-07-29 |
| Sources | [CLAUDE.md](../../../CLAUDE.md), [harden_isolation.sh](../../../scripts/harden_isolation.sh), [run_glm_campaign.sh](../../../local_agents/scripts/glm/run_glm_campaign.sh) |

## Purpose

How the measured CPU partition is made quiet enough to trust, and the ISO-PROOF gate that proves it
before any capture starts.

## Boot-time isolation (optional, operator-confirmed)

`sudo scripts/harden_isolation.sh --on` + reboot (revert with `--off`). **Never reboot or apply
GRUB changes without explicit user confirmation.**

### Decision: nohz_full + rcu_nocbs, never isolcpus

*Fact / Decision.* **Never use `isolcpus`** — it breaks scheduler load-balancing and stacks every
thread on one core. The correct mode is the script's **`nohz_full` + `rcu_nocbs`**: tick suppression
and RCU-callback offload on the measured cores, leaving the scheduler intact. The thesis campaigns
run under this boot.

## Runtime isolation

Applied and restored automatically by the kits: cpuset split (measured partition vs housekeeping),
CPU governor, no-turbo. The **litellm proxy** and the perf collectors themselves run on the
**housekeeping** cores so the profiler's own overhead does not pollute the measured partition —
hence measured-partition capacity claims are tool + harness only
(see [agent measurement design](../architecture/measurement-design.md)).

## The ISO-PROOF gate

*Fact.* k3s pods can escape runtime shields — leftover pods sit outside the system/user slices. The
shield pins their slice explicitly, and **ISO-PROOF verifies effective cpusets**, then requires the
measured cores to be **actually silent** before any capture starts. This is an observed-evidence
gate, not an "OK" line.

## Related pages

- [Service data path](../architecture/service-data-path.md) — where the k3s-pod-escape lesson bites.
- [Agent measurement design](../architecture/measurement-design.md) — the housekeeping/measured split.
