#!/usr/bin/env python3
"""
Combined startup script for both Flask and FastAPI backends
This ensures FastAPI is running before Flask tries to connect to it
"""
import subprocess
import time
import sys
import socket

def check_port(port, timeout=30):
    """Wait for a port to become available"""
    for _ in range(timeout):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        if result == 0:
            return True
        time.sleep(1)
    return False

def main():
    print("🚀 Starting Peterson Insurance AI Phone System...")
    
    # Start FastAPI backend on port 8001
    print("📡 Starting FastAPI backend (AI orchestrator) on port 8001...")
    fastapi_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", 
         "--host", "0.0.0.0", "--port", "8001", "--log-level", "info"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )
    
    # Wait for FastAPI to be ready
    if check_port(8001, timeout=30):
        print("✅ FastAPI backend ready on port 8001")
    else:
        print("❌ FastAPI backend failed to start")
        fastapi_process.terminate()
        sys.exit(1)
    
    # Start Flask frontend on port 5000 with single worker for conversation memory
    print("🌐 Starting Flask phone system on port 5000...")
    try:
        subprocess.run([
            "gunicorn", 
            "--bind", "0.0.0.0:5000",
            "--workers", "1",  # Single worker to maintain conversation state
            "--threads", "4",  # Use threads for concurrency within the worker
            "--timeout", "120",
            "--reload",
            "main:app"
        ])
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        fastapi_process.terminate()
        fastapi_process.wait()

if __name__ == "__main__":
    main()
