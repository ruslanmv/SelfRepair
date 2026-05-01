#!/bin/bash

echo "=== RepoGuardian Enterprise Web UI ==="
echo "Starting on port ${PORT:-7860}..."
echo "Working directory: $(pwd)"
echo "Contents: $(ls -la)"

# Ensure writable directories
mkdir -p "${WORK_DIR:-/tmp/repoguardian/work}"
mkdir -p "${STATE_DIR:-/tmp/repoguardian/state}"
mkdir -p "${STATUS_SITE_DIR:-/tmp/repoguardian/status-site}"

echo "Checking webapp module..."
python3 -c "from webapp.main import app; print('Module loaded OK')" 2>&1 || echo "Module import failed!"

echo "Starting uvicorn..."
# Start the FastAPI web application
exec python3 -m uvicorn webapp.main:app \
    --host "${HOST:-0.0.0.0}" \
    --port "${PORT:-7860}" \
    --workers 1 \
    --log-level info
