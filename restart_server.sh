#!/bin/bash

# ==============================================
# LMS SERVER RESTART SCRIPT
# ==============================================
# This script restarts the LMS server using .env configuration
# Usage: ./restart_server.sh [quick|full]
# ==============================================

set -e  # Exit on error

RESTART_MODE="${1:-full}"  # Default to full restart

echo " LMS Server Restart Script"
echo "=================================="
echo "📅 $(date)"
echo " Mode: $RESTART_MODE"
echo ""

# ==============================================
# LOAD ENVIRONMENT VARIABLES
# ==============================================

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env file
if [ -f ".env" ]; then
    echo "📋 Loading environment variables from .env..."
    export $(cat .env | grep -v '^#' | xargs)
    echo " Environment variables loaded"
else
    echo " No .env file found!"
    echo "   Please run ./setup_server.sh first"
    exit 1
fi

# Use environment variables
PROJECT_ROOT="${PROJECT_ROOT:-$(pwd)}"
LOGS_DIR="${LOGS_DIR:-$PROJECT_ROOT/logs}"
GUNICORN_BIND="${GUNICORN_BIND:-0.0.0.0:8000}"

# Extract port from GUNICORN_BIND
if [[ "$GUNICORN_BIND" == *":"* ]]; then
    SERVER_PORT="${GUNICORN_BIND##*:}"
else
    SERVER_PORT="8000"
fi

# ==============================================
# STOP EXISTING PROCESSES
# ==============================================

echo "🛑 Stopping existing LMS processes..."

# Graceful shutdown
pkill -TERM -f "python.*manage.py runserver" 2>/dev/null || true
pkill -TERM -f "gunicorn.*LMS_Project" 2>/dev/null || true

# Wait for graceful shutdown
sleep 3

# Force kill if still running
pkill -KILL -f "python.*manage.py runserver" 2>/dev/null || true
pkill -KILL -f "gunicorn.*LMS_Project" 2>/dev/null || true

# Kill processes on the server port
lsof -ti:$SERVER_PORT | xargs kill -9 2>/dev/null || true

# Remove stale PID file
rm -f "$LOGS_DIR/gunicorn.pid" 2>/dev/null || true

sleep 2

# Verify processes are stopped
if lsof -Pi :$SERVER_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "  Warning: Port $SERVER_PORT is still occupied"
    echo "   Attempting to forcefully free the port..."
    lsof -ti:$SERVER_PORT | xargs kill -9 2>/dev/null || true
    sleep 2
fi

if ! lsof -Pi :$SERVER_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo " All processes stopped, port $SERVER_PORT is free"
else
    echo " Failed to free port $SERVER_PORT"
    exit 1
fi

# ==============================================
# ACTIVATE VIRTUAL ENVIRONMENT
# ==============================================

echo "🐍 Activating virtual environment..."
source "$PROJECT_ROOT/venv/bin/activate"

# ==============================================
# PRE-START CHECKS (FULL MODE ONLY)
# ==============================================

if [ "$RESTART_MODE" == "full" ]; then
    echo "🔍 Running pre-start checks..."
    
    # Install/update dependencies (skip for Python 3.7 compatibility)
    echo "   - Skipping dependency update (already installed)..."
    
    # Django configuration check
    echo "   - Checking Django configuration..."
    python manage.py check --deploy
    
    if [ $? -ne 0 ]; then
        echo " Django configuration check failed"
        exit 1
    fi
    
    # Database migrations
    echo "   - Running database migrations..."
    python manage.py migrate --noinput
    
    if [ $? -ne 0 ]; then
        echo " Database migrations failed"
        exit 1
    fi
    
    # Collect static files
    echo "   - Collecting static files..."
    python manage.py collectstatic --noinput
    
    if [ $? -ne 0 ]; then
        echo " Static files collection failed"
        exit 1
    fi
    
    # Test database connection
    echo "   - Testing database connection..."
    python manage.py shell -c "
from django.db import connection
try:
    connection.ensure_connection()
    print(' Database connection successful')
except Exception as e:
    print(f' Database connection failed: {e}')
    exit(1)
    "
    
    if [ $? -ne 0 ]; then
        echo " Database connection test failed"
        exit 1
    fi
    
    echo " All pre-start checks passed"
fi

# ==============================================
# START SERVER
# ==============================================

echo " Starting LMS server..."
echo "   - Project: $PROJECT_ROOT"
echo "   - Logs: $LOGS_DIR"
echo "   - Bind: $GUNICORN_BIND"
echo ""

# Ensure logs directory exists
mkdir -p "$LOGS_DIR"

# Start Gunicorn
nohup gunicorn --config "$PROJECT_ROOT/gunicorn.conf.py" LMS_Project.wsgi:application \
    > "$LOGS_DIR/gunicorn_startup.log" 2>&1 &

# Wait for server to start
sleep 5

# ==============================================
# VERIFY SERVER IS RUNNING
# ==============================================

echo "🔍 Verifying server status..."

if lsof -Pi :$SERVER_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    PID=$(lsof -ti:$SERVER_PORT)
    echo " LMS server is running!"
    echo "   - Process ID: $PID"
    echo "   - Port: $SERVER_PORT"
    
    # Check if server is responding (only if it's a local port)
    if [ "$SERVER_PORT" -lt 65536 ]; then
        sleep 2
        if curl -f -s -I "http://localhost:$SERVER_PORT/" > /dev/null 2>&1; then
            echo "   - Health check:  Server is responding"
        else
            echo "   - Health check:   Server may not be responding yet"
            echo "   - Check logs: tail -f $LOGS_DIR/gunicorn_error.log"
        fi
    fi
else
    echo " Failed to start server!"
    echo ""
    echo "📋 Recent startup logs:"
    tail -20 "$LOGS_DIR/gunicorn_startup.log"
    echo ""
    echo "📋 Recent error logs:"
    tail -20 "$LOGS_DIR/gunicorn_error.log"
    exit 1
fi

# ==============================================
# RESTART SUMMARY
# ==============================================

echo ""
echo " Server Restart Completed Successfully!"
echo "==========================================="
echo ""
echo "📊 Server Status:"
echo "   - Status:  Running"
echo "   - PID: $(lsof -ti:$SERVER_PORT)"
echo "   - Port: $SERVER_PORT"
echo "   - Logs: $LOGS_DIR"
echo ""
echo "🔗 Access URLs:"
if [ ! -z "$PRIMARY_DOMAIN" ]; then
    echo "   - Production: https://$PRIMARY_DOMAIN"
fi
echo "   - Local: http://localhost:$SERVER_PORT"
echo ""
echo "📋 Useful Commands:"
echo "   - Check status: ./server_manager.sh status"
echo "   - View logs: tail -f $LOGS_DIR/gunicorn_error.log"
echo "   - Quick restart: ./restart_server.sh quick"
echo "   - Full restart: ./restart_server.sh full"
echo ""

