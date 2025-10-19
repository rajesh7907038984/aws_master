#!/bin/bash

# Enhanced System Monitoring Script
# Monitors all system resources and provides optimization recommendations

LOG_FILE="/home/ec2-user/lmslogs/system_monitor.log"
ALERT_FILE="/home/ec2-user/lmslogs/system_alerts.log"

echo "📊 LMS System Performance Monitor"
echo "================================="

# Get current timestamp
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# CPU Information
echo "=== CPU STATUS ==="
CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)
CPU_CORES=$(nproc)
echo "CPU Usage: ${CPU_USAGE}%"
echo "CPU Cores: ${CPU_CORES}"

# Memory Information
echo "=== MEMORY STATUS ==="
MEMORY_TOTAL=$(free -h | grep Mem | awk '{print $2}')
MEMORY_USED=$(free -h | grep Mem | awk '{print $3}')
MEMORY_AVAILABLE=$(free -h | grep Mem | awk '{print $7}')
MEMORY_PERCENT=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')

echo "Total RAM: ${MEMORY_TOTAL}"
echo "Used RAM: ${MEMORY_USED} (${MEMORY_PERCENT}%)"
echo "Available RAM: ${MEMORY_AVAILABLE}"

# Disk Information
echo "=== DISK STATUS ==="
DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}' | cut -d'%' -f1)
DISK_AVAILABLE=$(df -h / | awk 'NR==2 {print $4}')
echo "Disk Usage: ${DISK_USAGE}%"
echo "Available Space: ${DISK_AVAILABLE}"

# LMS Process Information
echo "=== LMS PROCESSES ==="
GUNICORN_PROCESSES=$(ps aux | grep gunicorn | grep -v grep | wc -l)
GUNICORN_MEMORY=$(ps aux | grep gunicorn | grep -v grep | awk '{sum+=$6} END {print sum/1024 " MB"}')

echo "Gunicorn Processes: ${GUNICORN_PROCESSES}"
echo "Total Gunicorn Memory: ${GUNICORN_MEMORY}"

# Network Information
echo "=== NETWORK STATUS ==="
ACTIVE_CONNECTIONS=$(netstat -an | grep :8000 | wc -l)
echo "Active Connections: ${ACTIVE_CONNECTIONS}"

# Database Information
echo "=== DATABASE STATUS ==="
cd /home/ec2-user/lms
source venv/bin/activate
DB_SIZE=$(python manage.py shell -c "from django.db import connection; cursor = connection.cursor(); cursor.execute('SELECT pg_database_size(current_database())'); size = cursor.fetchone()[0]; print(round(size/1024/1024, 2))" 2>/dev/null || echo "N/A")
echo "Database Size: ${DB_SIZE} MB"

# S3 Information
echo "=== S3 STORAGE STATUS ==="
# AWS credentials should be set as environment variables
# export AWS_ACCESS_KEY_ID=your_access_key
# export AWS_SECRET_ACCESS_KEY=your_secret_key
S3_OBJECTS=$(aws s3 ls s3://lms-staging-nexsy-io --recursive --summarize 2>/dev/null | grep "Total Objects" | awk '{print $3}' || echo "N/A")
S3_SIZE=$(aws s3 ls s3://lms-staging-nexsy-io --recursive --summarize 2>/dev/null | grep "Total Size" | awk '{print $3}' || echo "N/A")
echo "S3 Objects: ${S3_OBJECTS}"
echo "S3 Size: ${S3_SIZE} bytes"

# Performance Recommendations
echo "=== PERFORMANCE RECOMMENDATIONS ==="

# CPU Recommendations
if (( $(echo "$CPU_USAGE > 80" | bc -l) )); then
    echo "⚠️  HIGH CPU USAGE: Consider increasing CPU cores or optimizing queries"
else
    echo "✅ CPU usage is healthy"
fi

# Memory Recommendations
if (( $(echo "$MEMORY_PERCENT > 80" | bc -l) )); then
    echo "⚠️  HIGH MEMORY USAGE: Consider increasing RAM or optimizing memory usage"
else
    echo "✅ Memory usage is healthy"
fi

# Disk Recommendations
if [ "$DISK_USAGE" -gt 80 ]; then
    echo "⚠️  HIGH DISK USAGE: Consider cleaning up files or increasing disk space"
else
    echo "✅ Disk usage is healthy"
fi

# Gunicorn Recommendations
if [ "$GUNICORN_PROCESSES" -lt 4 ]; then
    echo "💡 OPTIMIZATION: Consider increasing Gunicorn workers to 4"
else
    echo "✅ Gunicorn workers are optimized"
fi

# Connection Recommendations
if [ "$ACTIVE_CONNECTIONS" -gt 100 ]; then
    echo "⚠️  HIGH CONNECTION COUNT: Consider load balancing or increasing workers"
else
    echo "✅ Connection count is healthy"
fi

# Log current status
echo "[$TIMESTAMP] CPU:${CPU_USAGE}% MEM:${MEMORY_PERCENT}% DISK:${DISK_USAGE}% PROC:${GUNICORN_PROCESSES} CONN:${ACTIVE_CONNECTIONS}" >> "$LOG_FILE"

# Check for alerts
if (( $(echo "$CPU_USAGE > 90" | bc -l) )) || (( $(echo "$MEMORY_PERCENT > 90" | bc -l) )) || [ "$DISK_USAGE" -gt 90 ]; then
    echo "[$TIMESTAMP] CRITICAL: High resource usage detected" >> "$ALERT_FILE"
    echo "CPU: ${CPU_USAGE}%, Memory: ${MEMORY_PERCENT}%, Disk: ${DISK_USAGE}%" >> "$ALERT_FILE"
fi

echo "=== MONITORING COMPLETE ==="
echo "Logs saved to: $LOG_FILE"
echo "Alerts saved to: $ALERT_FILE"
