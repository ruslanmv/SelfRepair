#!/bin/bash
set -e

echo "=============================================="
echo "  SelfRepair — maintenance console (HF Space)"
echo "  Port: ${PORT:-7860}"
echo "=============================================="

mkdir -p "${SELFREPAIR_DB_DIR:-/tmp/selfrepair}"

echo "Checking webapp module..."
python3 -c "from webapp.main import app; print('Module loaded OK')"

echo "Starting uvicorn..."
exec python3 -m uvicorn webapp.main:app \
    --host "${HOST:-0.0.0.0}" \
    --port "${PORT:-7860}" \
    --workers 1 \
    --log-level info
