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
# Apply configuration
kubectl apply -f litellm-deployment.yaml

# Check deployment
kubectl get pods -l app=litellm-proxy

# Check logs
kubectl logs -l app=litellm-proxy -f
```
