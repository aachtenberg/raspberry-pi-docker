FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    requests \
    docker \
    prometheus-client

# Copy collector script
COPY telemetry_collector.py /app/

# Run as root to access Docker socket
# In production, add collector user to docker group instead

CMD ["python", "-u", "telemetry_collector.py"]
