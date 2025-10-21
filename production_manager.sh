#!/bin/bash

# Production Server Management Script
echo "🏗️ LMS Production Server Manager"
echo "==============================="

case "$1" in
    "start")
        echo "🚀 Starting production server..."
        sudo systemctl start lms-production
        sudo systemctl status lms-production
        ;;
    "stop")
        echo "🛑 Stopping production server..."
        sudo systemctl stop lms-production
        ;;
    "restart")
        echo "🔄 Restarting production server..."
        sudo systemctl restart lms-production
        sudo systemctl status lms-production
        ;;
    "status")
        echo "📊 Server status:"
        sudo systemctl status lms-production
        ;;
    "logs")
        echo "📋 Recent logs:"
        sudo journalctl -u lms-production -f
        ;;
    "deploy")
        echo "🚀 Deploying updates..."
        ./deploy.sh
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|deploy}"
        echo ""
        echo "Commands:"
        echo "  start   - Start the production server"
        echo "  stop    - Stop the production server"
        echo "  restart - Restart the production server"
        echo "  status  - Show server status"
        echo "  logs    - Show live logs"
        echo "  deploy  - Deploy updates"
        exit 1
        ;;
esac
