#!/bin/bash

# LMS Scale-Up Server Management Script
# This script increases performance by optimizing all system components

LMS_DIR="/home/ec2-user/lms"
LOGS_DIR="/home/ec2-user/lmslogs"

echo "🚀 LMS Scale-Up Server Manager"
echo "=============================="

case "$1" in
    "optimize-gunicorn")
        echo "🔧 Optimizing Gunicorn configuration..."
        
        # Backup current config
        cp gunicorn.conf.py gunicorn.conf.py.backup
        
        # Use optimized configuration
        cp gunicorn_optimized.conf.py gunicorn.conf.py
        
        echo "✅ Gunicorn configuration optimized"
        echo "   - Workers: 2 → 4"
        echo "   - Connections: 1000 → 2000"
        echo "   - Request limits increased"
        echo "   - Preload app enabled"
        ;;
        
    "increase-memory-limits")
        echo "🧠 Increasing memory limits..."
        
        # Update production.env with higher memory thresholds
        sed -i 's/MEMORY_THRESHOLD_MB=800/MEMORY_THRESHOLD_MB=1200/' production.env
        sed -i 's/MEMORY_WARNING_THRESHOLD_MB=600/MEMORY_WARNING_THRESHOLD_MB=800/' production.env
        sed -i 's/DASHBOARD_MEMORY_THRESHOLD_MB=400/DASHBOARD_MEMORY_THRESHOLD_MB=600/' production.env
        
        echo "✅ Memory thresholds increased"
        echo "   - Main threshold: 800MB → 1200MB"
        echo "   - Warning threshold: 600MB → 800MB"
        echo "   - Dashboard threshold: 400MB → 600MB"
        ;;
        
    "optimize-database")
        echo "🗄️ Optimizing database connections..."
        
        # Create database optimization script
        cat > optimize_db.py << 'EOF'
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from django.db import connection
from django.conf import settings

# Optimize database settings
cursor = connection.cursor()

# Increase connection pool
cursor.execute("ALTER SYSTEM SET max_connections = 200;")
cursor.execute("ALTER SYSTEM SET shared_buffers = '256MB';")
cursor.execute("ALTER SYSTEM SET effective_cache_size = '1GB';")
cursor.execute("ALTER SYSTEM SET work_mem = '16MB';")
cursor.execute("ALTER SYSTEM SET maintenance_work_mem = '128MB';")

print("✅ Database optimized for higher performance")
EOF
        
        source venv/bin/activate
        python optimize_db.py
        rm optimize_db.py
        
        echo "✅ Database optimization completed"
        ;;
        
    "increase-file-limits")
        echo "📁 Increasing file upload limits..."
        
        # Update Django settings for larger files
        cat >> production.env << 'EOF'

# INCREASED FILE LIMITS
MAX_UPLOAD_SIZE=1073741824  # 1GB
MAX_SCORM_SIZE=1073741824  # 1GB
MAX_VIDEO_SIZE=2147483648   # 2GB
EOF
        
        echo "✅ File upload limits increased"
        echo "   - Max upload: 1GB"
        echo "   - Max SCORM: 1GB" 
        echo "   - Max video: 2GB"
        ;;
        
    "restart-optimized")
        echo "🔄 Restarting with optimized settings..."
        
        # Kill existing processes
        pkill -f "gunicorn.*LMS_Project" 2>/dev/null
        sleep 3
        
        # Start with optimized configuration
        cd $LMS_DIR
        source venv/bin/activate
        
        # Set optimized environment variables
        export GUNICORN_WORKERS=4
        export GUNICORN_TIMEOUT=1800
        export DJANGO_ENV=staging
        
        # Start optimized server
        nohup python -m gunicorn --config gunicorn.conf.py LMS_Project.wsgi:application > $LOGS_DIR/gunicorn_startup.log 2>&1 &
        
        sleep 5
        echo "✅ Optimized server started"
        echo "   - Workers: 4"
        echo "   - Timeout: 30 minutes"
        echo "   - Optimized configuration active"
        ;;
        
    "monitor-performance")
        echo "📊 Monitoring system performance..."
        
        echo "=== SYSTEM RESOURCES ==="
        echo "CPU Usage:"
        top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1
        
        echo "Memory Usage:"
        free -h
        
        echo "Disk Usage:"
        df -h
        
        echo "=== LMS PROCESSES ==="
        ps aux | grep gunicorn | grep -v grep
        
        echo "=== ACTIVE CONNECTIONS ==="
        netstat -an | grep :8000 | wc -l
        
        echo "=== RECENT ERRORS ==="
        tail -10 $LOGS_DIR/gunicorn_error.log
        ;;
        
    "full-optimization")
        echo "🚀 Running full system optimization..."
        
        $0 optimize-gunicorn
        $0 increase-memory-limits
        $0 optimize-database
        $0 increase-file-limits
        $0 restart-optimized
        
        echo "✅ Full optimization completed!"
        echo "   - Gunicorn workers increased"
        echo "   - Memory limits raised"
        echo "   - Database optimized"
        echo "   - File limits increased"
        echo "   - Server restarted with optimizations"
        ;;
        
    *)
        echo "Usage: $0 {optimize-gunicorn|increase-memory-limits|optimize-database|increase-file-limits|restart-optimized|monitor-performance|full-optimization}"
        echo ""
        echo "Commands:"
        echo "  optimize-gunicorn     - Increase workers and connections"
        echo "  increase-memory-limits - Raise memory thresholds"
        echo "  optimize-database     - Optimize database performance"
        echo "  increase-file-limits  - Increase upload limits"
        echo "  restart-optimized     - Restart with optimizations"
        echo "  monitor-performance   - Check system performance"
        echo "  full-optimization     - Run all optimizations"
        exit 1
        ;;
esac
