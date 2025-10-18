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
GUNICORN_TIMEOUT = int(os.environ.get('GUNICORN_TIMEOUT', '60'))  # Optimized timeout for better performance

# Calculate workers - optimized for 2 CPU cores (3.8GB RAM)
workers_env = os.environ.get('GUNICORN_WORKERS', 'auto')
if workers_env == 'auto':
    # For 2 CPUs with limited RAM, use fewer workers
    cpu_count = multiprocessing.cpu_count()
    if cpu_count <= 2:
        workers = 2  # Increased from 1 to 2 for better performance
    else:
        workers = cpu_count  # More conservative
else:
    workers = int(workers_env)

# Server socket
bind = GUNICORN_BIND
backlog = 2048

# Worker processes - optimized for performance and memory
worker_class = "sync"  # Keep sync for stability
worker_connections = 1000  # Increased from 500 for better throughput
keepalive = 2  # Reduced for better memory management

# Restart workers after this many requests, to prevent memory leaks
# SESSION-AWARE: Optimized worker recycling to preserve user sessions
max_requests = 1000  # Increased for better performance while preventing memory leaks
max_requests_jitter = 100  # Reasonable jitter for better memory management

# Logging - use environment variable for log directory
accesslog = "{}/gunicorn_access.log".format(LOGS_DIR)
errorlog = "{}/gunicorn_error.log".format(LOGS_DIR)
loglevel = "warning"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming - use environment
proc_name = "lms-{}".format(DJANGO_ENV)

# Server mechanics
daemon = False
pidfile = "{}/gunicorn.pid".format(LOGS_DIR)
user = SERVER_USER
group = SERVER_GROUP
tmp_upload_dir = None

# SSL (if needed)
# keyfile = "/path/to/keyfile"
# certfile = "/path/to/certfile"

limit_request_line = 8190
limit_request_fields = 200
limit_request_field_size = 16380

# Performance and memory optimization
preload_app = False  # Disabled to reduce memory usage at startup
worker_tmp_dir = "/dev/shm"

# Graceful timeout for worker restart
graceful_timeout = 15  # Optimized for faster worker recycling
timeout = GUNICORN_TIMEOUT  # Use the timeout setting

# Additional timeout settings for better handling
capture_output = True  # Capture worker output for debugging

# Environment variables - dynamically set based on DJANGO_ENV
raw_env = [
    "DJANGO_SETTINGS_MODULE=LMS_Project.settings",
    "DJANGO_ENV={}".format(DJANGO_ENV),
]

# Application
wsgi_module = "LMS_Project.wsgi:application"

# Security headers
def when_ready(server):
    """Called just after the server is started."""
    server.log.info("LMS {} Server Started with Gunicorn".format(DJANGO_ENV.upper()))
    server.log.info("Workers: {}".format(server.cfg.workers))
    server.log.info("🌐 Binding to: {}".format(server.cfg.bind))

def worker_int(worker):
    """Called just after a worker has been forked."""
    worker.log.info("👷 Worker spawned (pid: %s)", worker.pid)

def pre_fork(server, worker):
    """Called just before a worker is forked."""
    server.log.info("Worker will be spawned")

def post_fork(server, worker):
    """Called just after a worker has been forked."""
    server.log.info(" Worker spawned (pid: %s)", worker.pid)
    
    # SESSION-AWARE: Initialize session recovery for new workers
    try:
        from django.contrib.sessions.models import Session
        from django.utils import timezone
        active_sessions = Session.objects.filter(expire_date__gt=timezone.now()).count()
        worker.log.info(" Active sessions: %s", active_sessions)
    except Exception as e:
        worker.log.warning(" Could not check active sessions: %s", e)

def worker_abort(worker):
    """Called when a worker receives the SIGABRT signal."""
    worker.log.info(" Worker received SIGABRT signal")

def on_exit(server):
    """Called just before exiting."""
    server.log.info("🛑 LMS {} Server shutting down".format(DJANGO_ENV.upper()))

def on_reload(server):
    """Called to recycle workers during a reload via SIGHUP."""
    server.log.info(" LMS {} Server reloading".format(DJANGO_ENV.upper()))
