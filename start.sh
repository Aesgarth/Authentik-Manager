#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f ".env" ]; then
    echo "[.env file not found, copying from .env.example...]"
    cp .env.example .env
fi

cd backend
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
