#!/bin/bash
# Startup script for Replit - runs uvicorn instead of gunicorn for ASGI support
exec python -m uvicorn main:app --host 0.0.0.0 --port 5000 --reload --log-level info
