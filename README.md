# AgentCert Stack

Infrastructure components and configurations for the AgentCert platform. Contains setup files for supporting services that run alongside the main AgentCert application.

## Contents

```
agentcert-stack/
└── litellm-setup/        # LiteLLM proxy configuration
    ├── docker-compose-litellm.yml   # Local Docker Compose
    ├── litellm_config.yaml          # LiteLLM model configuration
    ├── litellm-deployment.yaml      # Kubernetes deployment
    └── QUICK_START.md               # Setup guide
```

## LiteLLM Setup

LiteLLM acts as a unified LLM gateway, providing:
- OpenAI-compatible API for all LLM providers
- Request/response logging to Langfuse
- Model aliasing and load balancing
- API key management

### Local Development (Docker Compose)

```bash
cd litellm-setup

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Start LiteLLM
docker compose -f docker-compose-litellm.yml up -d

# Access at http://localhost:4000
```

### Kubernetes Deployment

```bash
cd litellm-setup

# Create secrets (edit with your keys first)
kubectl apply -f litellm-deployment.yaml
```

### Configuration

Edit `litellm_config.yaml` to configure:
- Model aliases and endpoints
- Langfuse callback for tracing
- Rate limits and fallbacks

```yaml
model_list:
  - model_name: gpt-4.1
    litellm_params:
      model: azure/gpt-4o
      api_base: ${AZURE_API_BASE}
      api_key: ${AZURE_API_KEY}

litellm_settings:
  callbacks: ["langfuse"]
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `LITELLM_MASTER_KEY` | Admin API key for LiteLLM |
| `AZURE_API_KEY` | Azure OpenAI API key |
| `AZURE_API_BASE` | Azure OpenAI endpoint |
| `LANGFUSE_HOST` | Langfuse server URL |
| `LANGFUSE_PUBLIC_KEY` | Langfuse public key |
| `LANGFUSE_SECRET_KEY` | Langfuse secret key |

## License

MIT License - see [LICENSE](LICENSE)
