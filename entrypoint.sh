#!/bin/bash
set -e

echo "[ENTRYPOINT] Starting Celery worker in background..."
celery -A worker worker --loglevel=info --pool=solo &

# Use $PORT provided by Render (or fallback to 8000 for local docker)
PORT="${PORT:-8000}"
echo "[ENTRYPOINT] Starting FastAPI web server on port $PORT..."
exec uvicorn main:app --host 0.0.0.0 --port "$PORT"
