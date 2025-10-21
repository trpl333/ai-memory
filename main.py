#!/usr/bin/env python3
"""
Entry point for gunicorn deployment on Replit
This file provides the ASGI application for gunicorn with uvicorn workers
For gunicorn, use: gunicorn -k uvicorn.workers.UvicornWorker main:app
"""
import os
from config_loader import get_setting, get_llm_config
from app.main import app

# Set configuration from centralized config
llm_config = get_llm_config()
os.environ.setdefault("LLM_BASE_URL", llm_config["base_url"])
os.environ.setdefault("LLM_MODEL", llm_config["model"])
os.environ.setdefault("EMBED_DIM", str(get_setting("embed_dim", 768)))

# Export app for ASGI servers
__all__ = ['app']

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )
