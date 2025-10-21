# Gunicorn configuration file for FastAPI/ASGI applications
# This ensures gunicorn uses the proper ASGI worker

import multiprocessing

# Server socket
bind = "0.0.0.0:5000"
backlog = 2048

# Worker processes
workers = 1  # Single worker for development
worker_class = "uvicorn.workers.UvicornWorker"  # ASGI worker for FastAPI
worker_connections = 1000
timeout = 30
keepalive = 2

# Restart workers when code changes (for development)
reload = True
reload_engine = 'auto'

# Logging
accesslog = '-'
errorlog = '-'
loglevel = 'info'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = 'neurosphere-orchestrator'

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# Allow port reuse
reuse_port = True
