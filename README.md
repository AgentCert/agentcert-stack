<div align="center">

# agentcert-stack

**Bootstrap kit for the LLM gateway every AgentCert workload talks to.**

This repository is the **source of truth** for the LiteLLM proxy that fronts Azure
OpenAI, Google Gemini, OpenAI, and OpenRouter for every component in the AgentCert
platform. It ships a model registry, Langfuse callbacks, Docker Compose for local
development, Kubernetes manifests for production, and a smart bring-up script that
synchronises credentials and deployment names across the rest of the monorepo.

![LiteLLM](https://img.shields.io/badge/LiteLLM-v1.82.0--stable-1C3D5A?style=flat-square)
![Kubernetes](https://img.shields.io/badge/Kubernetes-1.28+-326CE5?style=flat-square&logo=kubernetes)
![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker)
![License](https://img.shields.io/badge/License-MIT-lightgrey?style=flat-square)

</div>

---

## Table of Contents

- [What this delivers](#what-this-delivers)
- [Repository layout](#repository-layout)
- [Models registered out of the box](#models-registered-out-of-the-box)
- [Quick start — Docker Compose (local dev)](#quick-start--docker-compose-local-dev)
- [Quick start — Kubernetes (production)](#quick-start--kubernetes-production)
- [Configuration & credentials](#configuration--credentials)
- [`build-litellm.sh` in detail](#build-litellmsh-in-detail)
- [How this relates to `agent-charts/litellm`](#how-this-relates-to-agent-chartslitellm)
- [Observability](#observability)
- [License](#license)

---

## What this delivers

A single endpoint — `http://litellm-proxy.litellm.svc.cluster.local:4000` (or
`http://localhost:14000` in Compose) — that:

- Speaks the **OpenAI Chat Completions API** so every agent and pipeline in the platform
  can use the same SDK regardless of the underlying provider.
- **Hides provider credentials** from agents. Agents authenticate with one
  `LITELLM_MASTER_KEY`; the proxy holds the real provider keys.
- **Routes by model alias** — agents request `gpt-4o`, `gemini-3-flash`, etc.; the proxy
  picks the right backend.
- **Falls back** to free tiers automatically when configured.
- **Reports every call to Langfuse** (request, response, tokens, latency) so the
  certifier can build a trace-driven scorecard.

Without this stack up, the rest of AgentCert won't work — the agents, the certifier
pipeline, and the chaos experiment runners all assume the proxy is reachable.

---

## Repository layout

```
agentcert-stack/
├── litellm-setup/
│   ├── docker-compose-litellm.yml    # Local dev: LiteLLM container, port 14000, health checks
│   ├── litellm_config.yaml           # Model registry + Langfuse callbacks + retry policy
│   ├── litellm-deployment.yaml       # Production K8s: Namespace + Secret + ConfigMap +
│   │                                 #                 Deployment + Service + ServiceAccount
│   ├── .env                          # Credential template (overwritten by build-litellm.sh)
│   ├── build-litellm.sh              # One-shot bring-up: validate + apply + sync
│   └── QUICK_START.md                # Step-by-step setup guide
├── LICENSE
└── README.md
```

---

## Models registered out of the box

From [`litellm-setup/litellm_config.yaml`](litellm-setup/litellm_config.yaml):

| Alias | Provider | Context window | Notes |
|---|---|---|---|
| `gemini-3-flash` | Google Generative Language | 1M | **Default model** |
| `gemini-2.5-flash` | Google Generative Language | 1M | |
| `gemini-2.5-flash-lite` | Google Generative Language | 1M | |
| `gpt-4o` | Azure OpenAI | 128K | 16.4K max output |
| `auto-free` | OpenRouter free tier (with fallbacks) | varies | Free-credit safety net |

Retry policy: **3 retries with 2 s backoff**. Langfuse success and failure callbacks are
enabled for every model.

---

## Quick start — Docker Compose (local dev)

```bash
cd litellm-setup

# 1. Provide credentials (.env is git-ignored)
cat > .env <<'EOF'
LITELLM_MASTER_KEY=sk-agentcert-dev
GEMINI_API_KEY=...
OPENROUTER_API_KEY=...
AZURE_OPENAI_KEY=...
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_SECRET_KEY=sk-...
EOF

# 2. Start
docker compose -f docker-compose-litellm.yml up -d

# 3. Verify
curl -fsS http://localhost:14000/health/liveliness
curl -s -X POST http://localhost:14000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-3-flash","messages":[{"role":"user","content":"hello"}]}'
```

Endpoint inside the Compose network: `http://litellm:4000`. On the host: `http://localhost:14000`.

---

## Quick start — Kubernetes (production)

Two paths:

### A — Direct `kubectl apply` (single-shot)

```bash
cd litellm-setup
# Edit litellm-deployment.yaml's Secret block with real values, then:
kubectl apply -f litellm-deployment.yaml
```

This creates the `litellm` namespace, the `Secret`, the `ConfigMap` (model registry +
callbacks), the `Deployment` (`litellm/litellm:v1.82.0-stable`, 512Mi/1Gi memory,
100m/500m CPU, HTTP `/health/liveliness` probes), the `ClusterIP` `Service` on `:4000`,
and the `ServiceAccount`.

### B — Driven by `build-litellm.sh` (recommended)

```bash
cd litellm-setup
./build-litellm.sh
```

The script reads `.env`, prompts for a deployment **profile** (`azure` / `openai` /
`all`), validates that the keys for that profile are present, applies the manifests,
and — if a `litmusportal-server` deployment exists in the cluster — syncs
`http://litellm-proxy.litellm.svc.cluster.local:4000/v1` into its env so AgentCert
ChaosCenter picks it up automatically.

In-cluster endpoint after either path:

```
http://litellm-proxy.litellm.svc.cluster.local:4000
```

---

## Configuration & credentials

Required for at least one provider:

| Variable | Required for | Description |
|---|---|---|
| `LITELLM_MASTER_KEY` | Always | Admin/Auth key that agents present in `Authorization: Bearer ...` |
| `LANGFUSE_HOST` | Recommended | e.g. `https://cloud.langfuse.com` |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | Recommended | Trace ingestion |
| `AZURE_OPENAI_KEY` / `AZURE_OPENAI_ENDPOINT` | `gpt-4o` | Azure OpenAI access |
| `GEMINI_API_KEY` | Gemini aliases | Google Generative Language API key |
| `OPENROUTER_API_KEY` | `auto-free` | OpenRouter fallback |

`build-litellm.sh` validates the right subset of these depending on the profile you pick.

---

## `build-litellm.sh` in detail

A 230-line bash driver in [`litellm-setup/build-litellm.sh`](litellm-setup/build-litellm.sh).
At a glance:

1. Sources `.env` (and verifies the keys for the chosen profile).
2. Prompts the operator for the profile — `azure`, `openai`, or `all`.
3. Searches for a downstream `agent-charts/litellm/` directory in two locations relative
   to itself:
   ```bash
   LITELLM_DIR_DEFAULT_A="${SCRIPT_DIR}/../agent-charts/litellm"
   LITELLM_DIR_DEFAULT_B="${SCRIPT_DIR}/../../agent-charts/litellm"
   ```
4. Applies the manifests there, substituting `LITELLM_MODEL_NAME` and other
   profile-specific values into the rendered ConfigMap.
5. If `litmusportal-server` is running, patches its env to point at the freshly-deployed
   proxy DNS.
6. Writes the final image tag + profile back into `.env`.

The result is **idempotent** — re-running it picks up any credential changes and rolls
the Deployment without manual `kubectl` plumbing.

---

## How this relates to `agent-charts/litellm`

| Repo | Role |
|---|---|
| **`agentcert-stack`** *(this repo)* | Source of truth: `litellm_config.yaml`, base manifests, bring-up script |
| [`agent-charts/litellm`](../agent-charts/litellm) | Downstream consumer: the **rendered** manifests with the `custom_callbacks.py` LegacySpanEmitter for Langfuse |

`build-litellm.sh` is the bridge — it owns the template-to-manifest pipeline so the two
trees stay in sync without hand-edits.

---

## Observability

Every LLM call routed through this proxy is logged to Langfuse with:

- Request body and response body.
- Token counts (prompt / completion / total).
- Latency.
- Per-callback metadata stamped by the [`agent-sidecar`](../agent-sidecar) — `agent_id`,
  `experiment_id`, `experiment_run_id`, `workflow_name`, `scan_id`.

That trace stream is the input the [`certifier`](../certifier) Phase-0+1 pipeline
consumes when generating a certification report.

---

## License

MIT — see [LICENSE](LICENSE).
