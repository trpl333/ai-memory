#!/usr/bin/env python3
"""
Production-ready startup script for NeuroSphere Orchestrator
Works with both gunicorn and direct execution
"""
import os
from config_loader import get_setting, get_llm_config
from app.main import app

# Set defaults for production from centralized config
llm_config = get_llm_config()
os.environ["LLM_BASE_URL"] = llm_config["base_url"]
os.environ.setdefault("LLM_MODEL", llm_config["model"])
os.environ.setdefault("EMBED_DIM", str(get_setting("embed_dim", 768)))

# This file can be used by gunicorn: gunicorn run_app:app
# Or run directly: python run_app.py

if __name__ == "__main__":
    import uvicorn
    port = int(get_setting("port", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")