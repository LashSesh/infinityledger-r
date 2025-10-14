FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and configuration
COPY src/ /app/src
COPY src/schemas/ /app/schemas
COPY config.yaml /app/config.yaml

# Create required directories
RUN mkdir -p /app/store /app/ledger

# Set environment variables
ENV PYTHONPATH=/app/src:/app
ENV MEF_SEED=MEF_SEED_42
ENV MEF_DETERMINISTIC=true

# Expose API port
EXPOSE 8080

# Health check for orchestrators and CI
HEALTHCHECK --interval=5s --timeout=1s --retries=20 CMD curl -fsS http://localhost:8080/healthz || exit 1

# Run the API server
CMD ["python", "src/api/server.py"]
