#!/bin/bash
# Crypto Sniper V2 — Render start command
exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}
