# Quick Start Guide - K8s Fault Detection Agent

## Setup

### 1: Setup Python Environment

```bash
# Navigate to project directory
cd /path/to/k8s-fault-agent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Load environment
export $(cat .env | xargs)
```

### 3. Run the agent
- Make sure LiteLLM is up and running
- Run k8s_fault_agent.py
```bash
python k8s_fault_agent.py
```

### 4. View Trace in Langfuse

1. Go to https://cloud.langfuse.com
2. Click on "Tracing" under "Observalbility" section in sidebar
3. Click on any trace.
4. Expand to see its details.

### 5. Build Agent Image

```bash
# Build image
docker build -f Dockerfile -t k8s_fault_agent:1.0.0 .

# If using a registry, push it
# docker tag k8s_fault_agent:1.0.0 your-registry/k8s_fault_agent:1.0.0
# docker push your-registry/k8s_fault_agent:1.0.0
```

### 6. Deploy on Kubernetes

```bash
# Deploy all components
kubectl apply -f agent-deployment.yaml

# Check all pods are running
kubectl get pods -n k8s-fault-agent
```

---

## Testing

### Inject a Fault for Testing

```bash
# Create a pod that will crash
kubectl run test-crash --image=nginx:nonexistent -n test

# Create a pod that will be OOMKilled
kubectl run test-oom --image=nginx \
  --requests='memory=10Mi' \
  --limits='memory=10Mi' \
  -n test

# Wait 30 seconds for agent to detect it

# Check agent logs
kubectl logs -n k8s-fault-agent -l app=autonomous-agent
```