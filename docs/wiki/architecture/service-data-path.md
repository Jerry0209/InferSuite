# Service data path

| Field | Value |
|---|---|
| Owner | LLM maintained, human reviewed |
| Status | Historical (source tree removed 2026-08-04) |
| Last updated | 2026-08-04 |
| Sources | [CLAUDE.md](../../../CLAUDE.md), `src/service/` and `deploy/` (removed from the working tree 2026-08-04 — repo narrowed to SWE-agent profiling; recover via git history, e.g. `git checkout <pre-removal-commit> -- src deploy`) |

> **Note (2026-08-04):** the service stack this page describes (`src/`, `deploy/`,
> `local_service/` incl. the `data_iso` campaign data, `benchmark_queries/`,
> `fastapi_runtime_assets/`) was removed from the working tree at the user's request. This
> page is kept as the architectural record; every path below now refers to git history.

## Purpose

The service is the non-agent subject of the study: a deployable RAG + semantic-cache + vLLM chatbot
whose CPU work OUTSIDE inference (retrieval, cache lookup, embedding) is measured against the CPU
work DURING inference (the vLLM serving engine). This page fixes the component boundaries so the
fenced CPU measurements map to named stages.

## Request path

```text
FastAPI orchestrator (orchestrator/chat.py, routes in api/)
  -> exact cache (Valkey)
  -> semantic cache (cache/: BGE embed -> Milvus -> MongoDB)
  -> RAG (rag/: BGE embed -> Milvus -> SeaweedFS chunk store, per-tenant routing)
  -> llm-d gateway
  -> vLLM (clients/vllm_client.py)
```

- **Embeddings** (`embeddings/bge.py`, bge-base-en-v1.5) run on the **CPU** — this is the bulk of
  the "outside inference" CPU work the study attributes.
- The **generation model** is set in `deploy/config.env`.
- *Fact.* Profile serving CPU with **whole-pod cgroup scope** (`perf -G` / `--for-each-cgroup`);
  process-scoped profiling misses the engine-core worker and reads ~idle
  (see [perf & TMA conventions](../profiling/perf-tma-conventions.md)).

## Deployment

Two scripts, one config file: `cp deploy/config.env.example deploy/config.env` → `./setup.sh` →
`./deploy.sh`; talk to it with `scripts/chat_cli.py --show-debug`. Targets: managed cloud cluster or
single-machine k3s / minikube. Kustomize bases in `deploy/k8s-*`; vendored llm-d / vLLM Helm charts
in `deploy/llmd-local/`; only the FastAPI image is built here (`Dockerfile.service`).

## Thesis-scope campaign

The thesis uses only the **isolated** service campaign `local_service/data_iso` (36-cell k3s run),
driven by `run_service_campaign.sh` and validated by `validate_service.py`.

*Limitation.* k3s pods can escape runtime shields — leftover pods sit outside the system/user
slices. The shield pins their slice explicitly and ISO-PROOF verifies effective cpusets, then
requires the measured cores to be silent before any capture starts
(see [isolation & hardening](../operations/isolation-hardening.md)).

## Related pages

- [Agent measurement design](measurement-design.md) — the agentic counterpart.
- [Measurement ontology](../concepts/measurement-ontology.md) — shared vocabulary.
