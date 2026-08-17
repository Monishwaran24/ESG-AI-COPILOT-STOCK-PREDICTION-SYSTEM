# ============================================================
# ESG Stock Prediction System - Docker Image
# ============================================================
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies for ML libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create required directories
RUN mkdir -p logs backups data model

# Copy default ESG data to a non-volatile location (volumes may overwrite /app/data)
RUN mkdir -p /app/default_data && \
    if [ -f /app/data/esg_data.csv ]; then cp /app/data/esg_data.csv /app/default_data/; fi

# Ensure entrypoint script is executable
RUN chmod +x scripts/entrypoint.sh

# Expose the Flask port
EXPOSE 5000

# Run with the entrypoint
ENTRYPOINT ["./scripts/entrypoint.sh"]
