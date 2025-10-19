# Optimized Gunicorn Configuration for Higher Performance
# This configuration increases workers, connections, and performance

import multiprocessing
import os

# Get environment from environment variable
DJANGO_ENV = os.environ.get('DJANGO_ENV', 'staging')
LOGS_DIR = os.environ.get('LOGS_DIR', '/home/ec2-user/lmslogs')
SERVER_USER = os.environ.get('SERVER_USER', 'ec2-user')
SERVER_GROUP = os.environ.get('SERVER_GROUP', 'ec2-user')
GUNICORN_BIND = os.environ.get('GUNICORN_BIND', '0.0.0.0:8000')
GUNICORN_TIMEOUT = int(os.environ.get('GUNICORN_TIMEOUT', '1800'))

# INCREASED WORKERS - Optimized for 2 CPU cores with more RAM
workers_env = os.environ.get('GUNICORN_WORKERS', 'auto')
if workers_env == 'auto':
    cpu_count = multiprocessing.cpu_count()
    if cpu_count <= 2:
        workers = 4  # INCREASED from 2 to 4 for better performance
    else:
        workers = cpu_count * 2  # More aggressive scaling
else:
    workers = int(workers_env)

# Server socket
bind = GUNICORN_BIND
backlog = 4096  # INCREASED from 2048

# Worker processes - optimized for performance
worker_class = "sync"
worker_connections = 2000  # INCREASED from 1000 for better throughput
keepalive = 5  # INCREASED from 2 for better connection reuse

# INCREASED request limits for better performance
max_requests = 2000  # INCREASED from 1000
max_requests_jitter = 200  # INCREASED from 100

# Logging
accesslog = "{}/gunicorn_access.log".format(LOGS_DIR)
errorlog = "{}/gunicorn_error.log".format(LOGS_DIR)
loglevel = "warning"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "lms-{}-optimized".format(DJANGO_ENV)

# Server mechanics
daemon = False
pidfile = "{}/gunicorn.pid".format(LOGS_DIR)
user = SERVER_USER
group = SERVER_GROUP
tmp_upload_dir = None

# INCREASED limits for better performance
limit_request_line = 16380  # INCREASED from 8190
limit_request_fields = 400  # INCREASED from 200
limit_request_field_size = 32760  # INCREASED from 16380

# Performance optimization
preload_app = True  # ENABLED for better performance
worker_tmp_dir = "/dev/shm"

# Timeouts
graceful_timeout = 600  # INCREASED from 300 (10 minutes)
timeout = GUNICORN_TIMEOUT

# File upload limits
client_max_body_size = "1G"  # INCREASED from 600M to 1GB

# Environment variables
raw_env = [
    "DJANGO_SETTINGS_MODULE=LMS_Project.settings",
    "DJANGO_ENV={}".format(DJANGO_ENV),
]

# Application
wsgi_module = "LMS_Project.wsgi:application"

# Callbacks
def when_ready(server):
    server.log.info("LMS {} Server Started with OPTIMIZED Gunicorn".format(DJANGO_ENV.upper()))
    server.log.info("Workers: {} (INCREASED)".format(server.cfg.workers))
    server.log.info("Connections per worker: {} (INCREASED)".format(server.cfg.worker_connections))
    server.log.info("🌐 Binding to: {}".format(server.cfg.bind))

def worker_int(worker):
    worker.log.info("👷 Worker spawned (pid: %s)", worker.pid)

def pre_fork(server, worker):
    server.log.info("Worker will be spawned")

def post_fork(server, worker):
    worker.log.info(" Worker spawned (pid: %s)", worker.pid)
    try:
        from django.contrib.sessions.models import Session
        from django.utils import timezone
        active_sessions = Session.objects.filter(expire_date__gt=timezone.now()).count()
        worker.log.info(" Active sessions: %s", active_sessions)
    except Exception as e:
        worker.log.warning(" Could not check active sessions: %s", e)

def worker_abort(worker):
    worker.log.info(" Worker received SIGABRT signal")

def on_exit(server):
    server.log.info("🛑 LMS {} Server shutting down".format(DJANGO_ENV.upper()))

def on_reload(server):
    server.log.info(" LMS {} Server reloading".format(DJANGO_ENV.upper()))
