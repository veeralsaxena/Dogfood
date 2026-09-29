#!/bin/sh
set -e

echo "Initializing and seeding Veritas database..."
python3 src/seed.py

echo "Starting Veritas Server on port ${PORT:-8080}..."
exec uvicorn src.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8080}"
