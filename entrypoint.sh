#!/bin/sh
set -e

echo "Initializing and seeding Hackathon Raptors Dogfood database..."
python3 src/seed.py

echo "Starting Dogfood Portal Server on port 8080..."
exec uvicorn src.main:app --host 0.0.0.0 --port 8080
