# Gunicorn Configuration for LMS
# This replaces Django's runserver for production/staging use
# All configuration is read from environment variables for server independence

import multiprocessing
import os

# Get environment from environment variable (staging by default)
DJANGO_ENV = os.environ.get('DJANGO_ENV', 'staging')

# Get configuration from environment variables
LOGS_DIR = os.environ.get('LOGS_DIR', '/home/ec2-user/lmslogs')
SERVER_USER = os.environ.get('SERVER_USER', 'ec2-user')
SERVER_GROUP = os.environ.get('SERVER_GROUP', 'ec2-user')
GUNICORN_BIND = os.environ.get('GUNICORN_BIND', '0.0.0.0:8000')
GUNICORN_TIMEOUT = int(os.environ.get('GUNICORN_TIMEOUT', '1800'))

# Calculate workers - optimized for 2 CPU cores (3.8GB RAM)
workers_env = os.environ.get('GUNICORN_WORKERS', 'auto')
if workers_env == 'auto':
    # For 2 CPUs with limited RAM, use fewer workers
    cpu_count = multiprocessing.cpu_count()
    if cpu_count <= 2:
        workers = 3  # Conservative for low memory
    else:
        workers = cpu_count * 2 + 1
else:
    workers = int(workers_env)

# Server socket
bind = GUNICORN_BIND
backlog = 2048

# Worker processes - optimized for performance
worker_class = "sync"
worker_connections = 1000
timeout = max(GUNICORN_TIMEOUT, 1800)  # Minimum 1800 seconds (30 minutes) for large file uploads
keepalive = 5  # Increased for better connection reuse

# Restart workers after this many requests, to prevent memory leaks
max_requests = 500  # Reduced to recycle workers more often and free memory
max_requests_jitter = 100  # Increased jitter for better distribution

# Logging - use environment variable for log directory
accesslog = f"{LOGS_DIR}/gunicorn_access.log"
errorlog = f"{LOGS_DIR}/gunicorn_error.log"
loglevel = "warning"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming - use environment
proc_name = f"lms-{DJANGO_ENV}"

# Server mechanics
daemon = False
pidfile = f"{LOGS_DIR}/gunicorn.pid"
user = SERVER_USER
group = SERVER_GROUP
tmp_upload_dir = None

# SSL (if needed)
# keyfile = "/path/to/keyfile"
# certfile = "/path/to/certfile"

# Security - increased limits for large file uploads
limit_request_line = 8190
limit_request_fields = 200
limit_request_field_size = 16380

# Performance
preload_app = True
worker_tmp_dir = "/dev/shm"

# Graceful timeout for worker restart
graceful_timeout = 30

# Environment variables - dynamically set based on DJANGO_ENV
raw_env = [
    f'DJANGO_SETTINGS_MODULE=LMS_Project.settings',
    f'DJANGO_ENV={DJANGO_ENV}',
]

# Application
wsgi_module = "LMS_Project.wsgi:application"

# Security headers
def when_ready(server):
    """Called just after the server is started."""
    server.log.info(f"LMS {DJANGO_ENV.upper()} Server Started with Gunicorn")
    server.log.info(f"Workers: {server.cfg.workers}")
    server.log.info(f"🌐 Binding to: {server.cfg.bind}")

def worker_int(worker):
    """Called just after a worker has been forked."""
    worker.log.info("👷 Worker spawned (pid: %s)", worker.pid)

def pre_fork(server, worker):
    """Called just before a worker is forked."""
    server.log.info("Worker will be spawned")

def post_fork(server, worker):
    """Called just after a worker has been forked."""
    server.log.info("✅ Worker spawned (pid: %s)", worker.pid)

def worker_abort(worker):
    """Called when a worker receives the SIGABRT signal."""
    worker.log.info("⚠️ Worker received SIGABRT signal")

def on_exit(server):
    """Called just before exiting."""
    server.log.info(f"🛑 LMS {DJANGO_ENV.upper()} Server shutting down")

def on_reload(server):
    """Called to recycle workers during a reload via SIGHUP."""
    server.log.info(f"🔄 LMS {DJANGO_ENV.upper()} Server reloading")
