FROM python:3.13-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent code
COPY k8s_fault_agent.py .

# Run agent
CMD ["python", "k8s_fault_agent.py"]