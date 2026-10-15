# LiteLLM Proxy Setup Guide

### Step 1: Get Your API Keys

1. OpenRouter API Key
2. Gemini API Key
3. Langfuse API Keys

### Step 2: Set Environment Variables


```bash
export $(cat .env | xargs)
```


### Step 3: Start LiteLLM Proxy 

#### a. Docker version

```bash
# Start LiteLLM proxy with Docker Compose
docker-compose -f docker-compose-litellm.yml up -d

# Wait for it to be ready

# Check if running
curl http://localhost:4000/health
```


#### b. Kubernetes version

```bash
# Apply configuration — images are resolved from IMAGE_REGISTRY in .env
# (same rule as setup.sh apply_manifest_resolved / scripts/lib/resolve_image_env.py):
#   IMAGE_REGISTRY set   -> <IMAGE_REGISTRY>/<IMAGE_MIRROR_NAMESPACE>/<public name>
#   IMAGE_REGISTRY empty -> upstream public name
python3 ../../scripts/lib/resolve_image_env.py --rewrite-manifests ../../.env \
    < litellm-deployment.yaml | kubectl apply -f -

# Check deployment
kubectl get pods -l app=litellm-proxy

# Check logs
kubectl logs -l app=litellm-proxy -f
```
