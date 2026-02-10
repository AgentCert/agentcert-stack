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

Required keys:
- `OPENAI_API_KEY` - Get from https://openrouter.ai/settings/keys
- `OTEL_EXPORTER_OTLP_ENDPOINT` - otlp-grpc URL of otel-collector service

### 3. Test Locally

```bash
# Load environment
export $(cat .env | xargs)

# Run test suite
python test_agent.py
```

### 4. View Trace in Langfuse

1. Go to https://cloud.langfuse.com
2. Click on "Tracing" under "Observalbility" section in sidebar
3. Click on any trace.
4. Expand to see its details.
