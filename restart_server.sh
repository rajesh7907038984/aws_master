#!/bin/bash

# Enhanced LMS Server Restart Script
# This script properly handles PID file cleanup and process management

LMS_DIR="/home/ec2-user/lms"
LOGS_DIR="/home/ec2-user/lmslogs"
PID_FILE="$LOGS_DIR/gunicorn.pid"

echo "🔄 LMS Server Restart Script"
echo "============================"

# Function to check if a process is running
check_process() {
    local pid=$1
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        return 0  # Process is running
    else
        return 1  # Process is not running
    fi
}

# Function to safely kill a process
safe_kill() {
    local pid=$1
    local signal=${2:-TERM}
    if [ -n "$pid" ] && check_process "$pid"; then
        echo "🛑 Sending $signal to process $pid"
        kill -$signal "$pid" 2>/dev/null
        sleep 2
        if check_process "$pid"; then
            echo "⚠️  Process $pid still running, force killing"
            kill -9 "$pid" 2>/dev/null
            sleep 1
        fi
    fi
}

# Function to clean up PID file
cleanup_pid_file() {
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE" 2>/dev/null)
        if [ -n "$pid" ]; then
            if check_process "$pid"; then
                echo "🛑 Killing process from PID file: $pid"
                safe_kill "$pid"
            else
                echo "🧹 Removing stale PID file"
            fi
        fi
        rm -f "$PID_FILE"
    fi
}

# Function to kill all LMS-related processes
kill_all_lms_processes() {
    echo "🛑 Killing all LMS-related processes..."
    
    # Kill processes by name patterns
    pkill -f "python.*manage.py runserver" 2>/dev/null || true
    pkill -f "gunicorn.*LMS_Project" 2>/dev/null || true
    pkill -f "gunicorn" 2>/dev/null || true
    pkill -f "start_lms.sh" 2>/dev/null || true
    
    # Kill processes on port 8000
    local port_pids=$(lsof -ti:8000 2>/dev/null)
    if [ -n "$port_pids" ]; then
        echo "🛑 Killing processes on port 8000: $port_pids"
        echo "$port_pids" | xargs kill -9 2>/dev/null || true
    fi
    
    # Kill any remaining Django/Gunicorn processes
    ps aux | grep -E "(manage.py|gunicorn|LMS_Project)" | grep -v grep | awk '{print $2}' | xargs kill -9 2>/dev/null || true
    
    # Clean up PID file
    cleanup_pid_file
    
    # Wait for processes to die
    sleep 3
    
    # Verify port 8000 is free
    if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "⚠️  Port 8000 still occupied, force killing remaining processes"
        lsof -ti:8000 | xargs kill -9 2>/dev/null || true
        sleep 2
    fi
    
    echo "✅ All LMS processes killed"
}

# Function to start the server
start_server() {
    echo "🚀 Starting LMS server..."
    
    cd "$LMS_DIR" || {
        echo "❌ Failed to change to LMS directory"
        exit 1
    }
    
    # Load environment variables
    if [ -f ".env" ]; then
        echo "📋 Loading environment variables..."
        export $(cat .env | grep -v '^#' | xargs)
    else
        echo "❌ .env file not found!"
        exit 1
    fi
    
    # Activate virtual environment
    if [ -f "venv/bin/activate" ]; then
        echo "🐍 Activating virtual environment..."
        source venv/bin/activate
    else
        echo "❌ Virtual environment not found!"
        exit 1
    fi
    
    # Run Django checks
    echo "🔍 Running Django system checks..."
    python manage.py check --deploy || {
        echo "❌ Django system check failed!"
        exit 1
    }
    
    # Run migrations
    echo "🗄️  Running database migrations..."
    python manage.py migrate --noinput || {
        echo "❌ Database migration failed!"
        exit 1
    }
    
    # Collect static files
    echo "📁 Collecting static files..."
    python manage.py collectstatic --noinput --clear || {
        echo "❌ Static file collection failed!"
        exit 1
    }
    
    # Create logs directory
    mkdir -p "$LOGS_DIR"
    
    # Start Gunicorn
    echo "🚀 Starting Gunicorn server..."
    nohup gunicorn --config gunicorn.conf.py LMS_Project.wsgi:application > "$LOGS_DIR/gunicorn_startup.log" 2>&1 &
    
    # Wait for server to start
    sleep 5
    
    # Check if server is running
    if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "✅ Server started successfully!"
        echo "🌐 Server is running on port 8000"
        
        # Test server response
        if curl -f -s -I http://localhost:8000/ > /dev/null 2>&1; then
            echo "✅ Server is responding to requests"
        else
            echo "⚠️  Server is running but may not be responding properly"
        fi
    else
        echo "❌ Failed to start server!"
        echo "📋 Check the startup log:"
        tail -20 "$LOGS_DIR/gunicorn_startup.log"
        exit 1
    fi
}

# Main execution
case "${1:-restart}" in
    "kill")
        kill_all_lms_processes
        ;;
    "start")
        start_server
        ;;
    "restart")
        kill_all_lms_processes
        start_server
        ;;
    "status")
        echo "📊 LMS Server Status"
        echo "==================="
        
        # Check if server is running on port 8000
        if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
            pid=$(lsof -ti:8000)
            echo "✅ Server is running on port 8000 (PID: $pid)"
            
            # Test server response
            if curl -f -s -I http://localhost:8000/ > /dev/null 2>&1; then
                echo "✅ Server is responding to requests"
            else
                echo "⚠️  Server is running but not responding properly"
            fi
        else
            echo "❌ Server is not running on port 8000"
        fi
        
        # Check PID file
        if [ -f "$PID_FILE" ]; then
            pid=$(cat "$PID_FILE" 2>/dev/null)
            if [ -n "$pid" ]; then
                if check_process "$pid"; then
                    echo "📄 PID file exists and process is running: $pid"
                else
                    echo "⚠️  PID file exists but process is not running: $pid"
                fi
            else
                echo "⚠️  PID file exists but is empty"
            fi
        else
            echo "📄 No PID file found"
        fi
        ;;
    *)
        echo "Usage: $0 {kill|start|restart|status}"
        echo ""
        echo "Commands:"
        echo "  kill     - Kill all LMS processes and clean up"
        echo "  start    - Start the LMS server"
        echo "  restart  - Kill all processes and start fresh (default)"
        echo "  status   - Check server status"
        exit 1
        ;;
esac

echo "✅ Script completed successfully"