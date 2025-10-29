#!/bin/bash

# Complete LMS Server Management Script with Session Preservation
# All restart operations now preserve user sessions to prevent auto-logout
# Usage: ./server_manager.sh [kill|restart|service-restart|quick|status|logs]

LMS_DIR="/home/ec2-user/lms"
LOGS_DIR="/home/ec2-user/lmslogs"

case "$1" in
    kill)
        echo "🛑 Killing ALL LMS server processes..."
        pkill -f "python.*manage.py runserver" 2>/dev/null
        pkill -f "gunicorn.*LMS_Project" 2>/dev/null
        pkill -f "gunicorn" 2>/dev/null
        pkill -f "start_lms.sh" 2>/dev/null
        lsof -ti:8000 | xargs kill -9 2>/dev/null || true
        ps aux | grep -E "(manage.py|gunicorn|LMS_Project)" | grep -v grep | awk '{print $2}' | xargs kill -9 2>/dev/null || true
        rm -f "$LOGS_DIR/gunicorn.pid" 2>/dev/null
        sleep 3
        if ! lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
            echo " All processes killed, port 8000 is free"
        else
            echo "  Some processes may still be running"
        fi
        ;;
    enable-services)
        echo " Enabling system services..."
        echo " Enabling nginx service..."
        sudo systemctl enable nginx
        echo " Enabling lms-production service..."
        sudo systemctl enable lms-production
        echo " Starting nginx..."
        sudo systemctl start nginx
        echo " Services enabled and nginx started"
        ;;
    restart)
        echo " Full server restart with checks..."
        cd $LMS_DIR
        
        echo "🛡️  Preserving user sessions to prevent auto-logout..."
        python3 manage.py preserve_sessions
        
        if [ $? -ne 0 ]; then
            echo " Session preservation failed, aborting restart"
            exit 1
        fi
        echo " Sessions preserved successfully"
        echo ""
        
        echo "🛑 Killing ALL server processes..."
        pkill -f "python.*manage.py runserver" 2>/dev/null || true
        pkill -f "gunicorn.*LMS_Project" 2>/dev/null || true
        pkill -f "gunicorn" 2>/dev/null || true
        lsof -ti:8000 | xargs kill -9 2>/dev/null || true
        ps aux | grep -E "(manage.py|gunicorn|LMS_Project)" | grep -v grep | awk '{print $2}' | xargs kill -9 2>/dev/null || true
        rm -f "$LOGS_DIR/gunicorn.pid" 2>/dev/null
        sleep 5
        
        echo "🧹 Cleaning up system resources..."
        find /tmp -name "django_session*" -delete 2>/dev/null || true
        
        echo "🔍 Verifying cleanup..."
        if ! lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
            echo " Port 8000 is free"
        else
            echo " Port 8000 still occupied, force killing..."
            lsof -ti:8000 | xargs kill -9 2>/dev/null || true
            sleep 2
        fi
        
        echo " Starting fresh server..."
        if [ -f "production.env" ]; then
            export $(cat production.env | grep -v '^#' | xargs)
        else
            echo " production.env not found!"
            exit 1
        fi
        
        python3 manage.py check --deploy
        python3 manage.py migrate --noinput
        python3 manage.py collectstatic --noinput --clear
        
        mkdir -p $LOGS_DIR
        nohup python3 -m gunicorn --config gunicorn.conf.py LMS_Project.wsgi:application > $LOGS_DIR/gunicorn_startup.log 2>&1 &
        
        sleep 3
        if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
            echo " Server restarted successfully!"
        else
            echo " Failed to restart server!"
            tail -10 $LOGS_DIR/gunicorn_startup.log
        fi
        ;;
    service-restart)
        echo " Production service restart..."
        cd $LMS_DIR
        
        echo "🛡️  Preserving user sessions to prevent auto-logout..."
        python3 manage.py preserve_sessions
        
        if [ $? -ne 0 ]; then
            echo " Session preservation failed, aborting restart"
            exit 1
        fi
        echo " Sessions preserved successfully"
        echo ""
        
        echo "🛑 Stopping LMS production service..."
        sudo systemctl stop lms-production 2>/dev/null || true
        
        echo "🔪 Killing any remaining processes..."
        pkill -f "python.*manage.py runserver" 2>/dev/null || true
        pkill -f "gunicorn.*LMS_Project" 2>/dev/null || true
        lsof -ti:8000 | xargs kill -9 2>/dev/null || true
        sleep 3
        
        echo " Starting LMS production service..."
        sudo systemctl start lms-production
        sleep 5
        
        echo "📊 Service Status:"
        sudo systemctl status lms-production --no-pager -l
        ;;
    quick)
        echo "⚡ Quick restart..."
        cd $LMS_DIR
        
        echo "🛡️  Preserving user sessions to prevent auto-logout..."
        python3 manage.py preserve_sessions
        
        if [ $? -ne 0 ]; then
            echo " Session preservation failed, aborting restart"
            exit 1
        fi
        echo " Sessions preserved successfully"
        echo ""
        
        # Quick kill and restart
        pkill -f "python.*manage.py runserver" 2>/dev/null || true
        pkill -f "gunicorn" 2>/dev/null || true
        lsof -ti:8000 | xargs kill -9 2>/dev/null || true
        sleep 3
        rm -f "$LOGS_DIR/gunicorn.pid" 2>/dev/null
        
        # Ensure nginx is running
        if ! systemctl is-active --quiet nginx; then
            sudo systemctl start nginx
        fi
        
        # Load environment and start
        export $(cat production.env | grep -v '^#' | xargs) 2>/dev/null
        nohup python3 -m gunicorn --config gunicorn.conf.py LMS_Project.wsgi:application > $LOGS_DIR/gunicorn_startup.log 2>&1 &
        
        sleep 2
        if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
            echo " Quick restart successful!"
        else
            echo " Quick restart failed!"
            tail -10 $LOGS_DIR/gunicorn_startup.log
        fi
        ;;
    status)
        echo "📊 Server Status:"
        echo "================"
        
        # Check Nginx status
        if systemctl is-active --quiet nginx; then
            echo " Nginx is active"
        else
            echo " Nginx is not active"
        fi
        
        # Check LMS Production service status
        if systemctl is-active --quiet lms-production 2>/dev/null; then
            echo " LMS Production service is active"
        else
            echo "  LMS Production service status unknown or inactive"
        fi
        
        # Check port 8000
        if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
            echo " Server is running on port 8000"
            PID=$(lsof -ti:8000)
            echo "🔢 Process ID: $PID"
            if curl -f -s -I http://localhost:8000/ > /dev/null 2>&1; then
                echo " Server is responding"
            else
                echo "  Server may not be responding properly"
            fi
        else
            echo " Server is not running on port 8000"
        fi
        
        # Check if domain is accessible
        DOMAIN_CHECK="${PRIMARY_DOMAIN:-${NGINX_SERVER_NAME:-localhost}}"
        if curl -f -s -I "https://${DOMAIN_CHECK}/" > /dev/null 2>&1; then
            echo " Domain https://${DOMAIN_CHECK} is accessible"
        else
            echo "  Domain may not be accessible or responding"
        fi
        ;;
    services-status)
        echo "🔍 System Services Status:"
        echo "========================="
        echo "Nginx status:"
        sudo systemctl status nginx --no-pager -l
        echo ""
        echo "LMS Production service status:"
        sudo systemctl status lms-production --no-pager -l 2>/dev/null || echo "LMS Production service not found"
        ;;
    logs)
        echo "📋 Recent logs:"
        echo "==============="
        if [ -f "$LOGS_DIR/gunicorn_error.log" ]; then
            echo "Error log (last 15 lines):"
            tail -15 "$LOGS_DIR/gunicorn_error.log"
        fi
        echo ""
        if [ -f "$LOGS_DIR/production_errors.log" ]; then
            echo "Production errors (last 10 lines):"
            tail -10 "$LOGS_DIR/production_errors.log"
        fi
        echo ""
        echo "Nginx error log (last 10 lines):"
        sudo tail -10 /var/log/nginx/error.log 2>/dev/null || echo "Nginx error log not accessible"
        ;;
    *)
        echo "🛠️  LMS Server Manager"
        echo "==================="
        echo ""
        echo "Usage: $0 {command}"
        echo ""
        echo "Commands:"
        echo "  kill             - Kill all server processes and free port 8000"
        echo "  restart          - Complete restart with full checks and cleanup"
        echo "  quick            - Quick restart without extensive checks"
        echo "  enable-services  - Enable nginx and lms-production services"
        echo "  status           - Check if server and services are running"
        echo "  services-status  - Detailed systemd services status"
        echo "  logs             - Show recent error logs (including nginx)"
        echo ""
        echo "Examples:"
        echo "  $0 enable-services    # Enable nginx and lms-production services"
        echo "  $0 kill              # Kill all processes"
        echo "  $0 restart           # Full restart with checks"
        echo "  $0 quick             # Quick restart"
        echo "  $0 status            # Check status"
        echo "  $0 services-status   # Detailed service status"
        echo ""
        echo " For Internal Server Error issues:"
        echo "  1. $0 enable-services"
        echo "  2. $0 restart"
        echo "  3. $0 status"
        echo ""
        exit 1
        ;;
esac
