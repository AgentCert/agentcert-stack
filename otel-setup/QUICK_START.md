# Quick Start Guide - K8s Fault Detection Agent

## OpenTelemetry Collector Setup

### 1. Add Langfuse auth header
1. Create base64 encoded Langfuse auth header using your Langfuse public key and secret key.
```
echo -n "pk-public-key:sk-secret-key" | base64 -w0
```
2. Add Langfuse auth header in "langfuse-credentials" secret in otel-setup/otel-collector.yaml file

### 2. Deploy OpenTelemetry Collector
Deploy otel-setup/otel-collector.yaml
```
kubectl apply -f otel-setup/otel-collector.yaml
```