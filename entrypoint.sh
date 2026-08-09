#!/bin/bash
set -e

# Restrict PyTorch & NumPy CPU thread memory overhead for low-RAM cloud instances
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

echo "[ENTRYPOINT] Starting Celery worker in background..."
celery -A worker worker --loglevel=info --pool=solo &

# Use $PORT provided by Render (or fallback to 8000 for local docker)
PORT="${PORT:-8000}"
echo "[ENTRYPOINT] Starting FastAPI web server on 0.0.0.0:$PORT..."
exec uvicorn main:app --host 0.0.0.0 --port "$PORT"
