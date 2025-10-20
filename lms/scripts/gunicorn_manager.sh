#!/bin/bash

# Gunicorn Process Management Script
# Handles proper startup, shutdown, and monitoring of Gunicorn processes

set -e

# Configuration
PROJECT_DIR="/home/ec2-user/lms"
LOGS_DIR="/home/ec2-user/lmslogs"
PID_FILE="$LOGS_DIR/gunicorn.pid"
CONFIG_FILE="$PROJECT_DIR/gunicorn.conf.py"
VENV_DIR="$PROJECT_DIR/venv"
USER="ec2-user"
GROUP="ec2-user"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" >&2
}

warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

# Check if Gunicorn is running
is_running() {
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0
        else
            # PID file exists but process is dead
            rm -f "$PID_FILE"
            return 1
        fi
    fi
    return 1
}

# Clean up stale processes
cleanup_stale_processes() {
    log "Cleaning up stale Gunicorn processes..."
    
    # Kill any existing Gunicorn processes
    pkill -f "gunicorn.*LMS_Project.wsgi" || true
    
    # Remove stale PID file
    rm -f "$PID_FILE"
    
    # Wait a moment for processes to die
    sleep 2
    
    # Check if any processes are still running
    if pgrep -f "gunicorn.*LMS_Project.wsgi" > /dev/null; then
        warn "Some Gunicorn processes still running, force killing..."
        pkill -9 -f "gunicorn.*LMS_Project.wsgi" || true
        sleep 2
    fi
    
    log "Cleanup completed"
}

# Start Gunicorn
start_gunicorn() {
    log "Starting Gunicorn server..."
    
    # Check if already running
    if is_running; then
        warn "Gunicorn is already running (PID: $(cat $PID_FILE))"
        return 0
    fi
    
    # Clean up any stale processes first
    cleanup_stale_processes
    
    # Change to project directory
    cd "$PROJECT_DIR"
    
    # Set environment variables
    export DJANGO_SETTINGS_MODULE=LMS_Project.settings.production
    export DJANGO_ENV=production
    export PROJECT_ROOT="$PROJECT_DIR"
    export LOGS_DIR="$LOGS_DIR"
    export GUNICORN_BIND=0.0.0.0:8000
    export GUNICORN_WORKERS=1
    export GUNICORN_TIMEOUT=3600
    export SERVER_USER="$USER"
    export SERVER_GROUP="$GROUP"
    
    # Start Gunicorn
    sudo -u "$USER" "$VENV_DIR/bin/python" -m gunicorn --config "$CONFIG_FILE" LMS_Project.wsgi:application
    
    # Wait a moment for startup
    sleep 3
    
    # Check if started successfully
    if is_running; then
        log "Gunicorn started successfully (PID: $(cat $PID_FILE))"
    else
        error "Failed to start Gunicorn"
        return 1
    fi
}

# Stop Gunicorn
stop_gunicorn() {
    log "Stopping Gunicorn server..."
    
    if ! is_running; then
        warn "Gunicorn is not running"
        return 0
    fi
    
    local pid=$(cat "$PID_FILE")
    
    # Try graceful shutdown first
    log "Sending TERM signal to PID $pid..."
    kill -TERM "$pid" || true
    
    # Wait for graceful shutdown
    local count=0
    while [ $count -lt 30 ] && is_running; do
        sleep 1
        count=$((count + 1))
    done
    
    # Force kill if still running
    if is_running; then
        warn "Graceful shutdown failed, force killing..."
        kill -9 "$pid" || true
        sleep 2
    fi
    
    # Clean up PID file
    rm -f "$PID_FILE"
    
    log "Gunicorn stopped"
}

# Restart Gunicorn
restart_gunicorn() {
    log "Restarting Gunicorn server..."
    stop_gunicorn
    sleep 2
    start_gunicorn
}

# Check status
status_gunicorn() {
    if is_running; then
        local pid=$(cat "$PID_FILE")
        log "Gunicorn is running (PID: $pid)"
        
        # Show process info
        ps -p "$pid" -o pid,ppid,cmd,pcpu,pmem,etime
        return 0
    else
        warn "Gunicorn is not running"
        return 1
    fi
}

# Monitor memory usage
monitor_memory() {
    if is_running; then
        local pid=$(cat "$PID_FILE")
        local memory_mb=$(ps -p "$pid" -o rss= | awk '{print $1/1024}')
        log "Gunicorn memory usage: ${memory_mb}MB"
        
        # Alert if memory usage is too high
        if (( $(echo "$memory_mb > 500" | bc -l) )); then
            warn "High memory usage detected: ${memory_mb}MB"
        fi
    fi
}

# Main script logic
case "$1" in
    start)
        start_gunicorn
        ;;
    stop)
        stop_gunicorn
        ;;
    restart)
        restart_gunicorn
        ;;
    status)
        status_gunicorn
        ;;
    cleanup)
        cleanup_stale_processes
        ;;
    monitor)
        monitor_memory
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|cleanup|monitor}"
        echo ""
        echo "Commands:"
        echo "  start   - Start Gunicorn server"
        echo "  stop    - Stop Gunicorn server"
        echo "  restart - Restart Gunicorn server"
        echo "  status  - Check if Gunicorn is running"
        echo "  cleanup - Clean up stale processes"
        echo "  monitor - Monitor memory usage"
        exit 1
        ;;
esac
