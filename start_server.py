#!/usr/bin/env python3
"""
Startup script for NeuroSphere Orchestrator
Starts FastAPI backend (port 8001) first, then Flask frontend (port 5000)
"""

import subprocess
import time
import sys
import socket
import os
from config_loader import get_setting, get_llm_config, get_secret

def check_port_available(port):
    """Check if a port is available"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', port))
    sock.close()
    return result != 0

def wait_for_port(port, timeout=30):
    """Wait for a port to become available (service started)"""
    for _ in range(timeout):
        if not check_port_available(port):
            return True
        time.sleep(1)
    return False

def main():
    # Set LLM configuration from centralized config
    llm_config = get_llm_config()
    os.environ.setdefault("LLM_MODEL", llm_config["model"])
    os.environ.setdefault("EMBED_DIM", str(get_setting("embed_dim", 768)))
    
    print("🚀 Starting NeuroSphere Orchestrator...")
    print(f"LLM Base URL: {llm_config['base_url']}")
    print(f"Database: {'Connected' if get_secret('DATABASE_URL') else 'Not configured'}")
    
    # Start FastAPI backend on port 8001
    print("📡 Starting FastAPI backend on port 8001...")
    fastapi_cmd = [
        sys.executable, "-m", "uvicorn", "app.main:app", 
        "--host", "0.0.0.0", 
        "--port", "8001", 
        "--log-level", "info"
    ]
    
    fastapi_process = subprocess.Popen(fastapi_cmd)
    
    # Wait for FastAPI to be ready
    if wait_for_port(8001, timeout=30):
        print("✅ FastAPI backend ready on port 8001")
    else:
        print("❌ FastAPI backend failed to start")
        fastapi_process.terminate()
        sys.exit(1)
    
    # Start Flask frontend on port 5000
    #print("🌐 Starting Flask frontend on port 5000...")
    #flask_cmd = [
    #    "gunicorn", 
    #    "--bind", "0.0.0.0:5000", 
    #    "--reuse-port", 
    #    "--reload", 
    #    "main:app"
    #]
    #
    #try:
    #    subprocess.run(flask_cmd)
    #except KeyboardInterrupt:
    #    print("\n🛑 Shutting down...")
    #    fastapi_process.terminate()
    #    fastapi_process.wait()

if __name__ == "__main__":
    main()
