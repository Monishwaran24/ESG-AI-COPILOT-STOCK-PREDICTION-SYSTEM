#!/bin/bash
# ============================================================
# ESG Stock Prediction System - Docker Entrypoint
# ============================================================
# This script runs when the container starts.
# It ensures data files exist and starts the Flask app.
# ============================================================

set -e

echo "============================================================"
echo "  ESG Stock Prediction System v2.0"
echo "============================================================"

# Copy default data files if they don't exist (for fresh volumes)
if [ ! -f /app/data/esg_data.csv ]; then
    if [ -f /app/default_data/esg_data.csv ]; then
        cp /app/default_data/esg_data.csv /app/data/
        echo "[INIT] Restored esg_data.csv from default_data"
    else
        echo "[INIT] No default esg_data.csv found — app will use built-in fallback data"
    fi
fi

# Ensure database files exist
if [ ! -f /app/esg_stock.db ]; then
    echo "[INIT] No existing esg_stock.db — will be created on first run"
fi
if [ ! -f /app/users.db ]; then
    echo "[INIT] No existing users.db — will be created on first run"
fi

# Ensure log and backup directories exist
mkdir -p /app/logs /app/backups

echo "[INIT] Starting Flask application..."
echo "------------------------------------------------------------"

# Start the Flask app
exec python app.py
