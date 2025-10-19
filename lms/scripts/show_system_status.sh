#!/bin/bash
# LMS System Status Dashboard
# Quick view of system health and monitoring alerts

echo "========================================"
echo "  LMS SYSTEM STATUS DASHBOARD"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"
echo ""

# Memory Status
echo "📊 MEMORY STATUS:"
echo "----------------------------------------"
free -h
echo ""

# Disk Status
echo "💾 DISK USAGE:"
echo "----------------------------------------"
df -h /
echo ""

# Swap Status
echo "🔄 SWAP USAGE:"
echo "----------------------------------------"
swapon --show
echo ""

# Gunicorn Workers
echo "⚙️  GUNICORN WORKERS:"
echo "----------------------------------------"
WORKER_COUNT=$(ps aux | grep gunicorn | grep -v grep | wc -l)
echo "Active Workers: $WORKER_COUNT"
ps aux | grep gunicorn | grep -v grep | awk '{print $2, $3, $4, $11}' | head -5
echo ""

# Large Files in /tmp
echo "📦 LARGE FILES IN /tmp (>100MB):"
echo "----------------------------------------"
LARGE_COUNT=$(find /tmp -type f -size +100M 2>/dev/null | wc -l)
if [ "$LARGE_COUNT" -gt 0 ]; then
    find /tmp -type f -size +100M -exec ls -lh {} \; 2>/dev/null | awk '{print $5, $9}'
else
    echo "No large files found"
fi
echo ""

# Recent Memory Alerts (if any)
echo "⚠️  RECENT MEMORY ALERTS (Last 5):"
echo "----------------------------------------"
if [ -f "/home/ec2-user/lmslogs/memory_alerts.log" ]; then
    tail -n 5 /home/ec2-user/lmslogs/memory_alerts.log 2>/dev/null || echo "No recent memory alerts"
else
    echo "No alerts logged yet"
fi
echo ""

# Recent Disk Alerts (if any)
echo "⚠️  RECENT DISK ALERTS (Last 5):"
echo "----------------------------------------"
if [ -f "/home/ec2-user/lmslogs/disk_alerts.log" ]; then
    tail -n 5 /home/ec2-user/lmslogs/disk_alerts.log 2>/dev/null || echo "No recent disk alerts"
else
    echo "No alerts logged yet"
fi
echo ""

# Recent Upload Activity
echo "📤 RECENT UPLOAD ACTIVITY:"
echo "----------------------------------------"
if [ -f "/home/ec2-user/lmslogs/upload_monitor.log" ]; then
    tail -n 5 /home/ec2-user/lmslogs/upload_monitor.log 2>/dev/null || echo "No recent upload activity"
else
    echo "No uploads monitored yet"
fi
echo ""

# System Uptime
echo "🕐 SYSTEM UPTIME:"
echo "----------------------------------------"
uptime
echo ""

echo "========================================"
echo "  Use 'tail -f /home/ec2-user/lmslogs/*_monitor.log'"
echo "  to watch live monitoring"
echo "========================================"

