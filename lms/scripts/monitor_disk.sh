#!/bin/bash
# LMS Disk Space Monitoring Script
# Monitors disk usage and sends alerts when space is low
# Run every hour via cron

LOG_FILE="/home/ec2-user/lmslogs/disk_monitor.log"
ALERT_FILE="/home/ec2-user/lmslogs/disk_alerts.log"
DISK_THRESHOLD=85  # Alert when disk usage exceeds 85%
CRITICAL_THRESHOLD=90  # Critical alert at 90%

# Get current disk usage (root partition)
DISK_USAGE=$(df / | grep / | awk '{print $5}' | sed 's/%//')
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Log current stats
echo "$TIMESTAMP | Disk Usage: ${DISK_USAGE}%" >> "$LOG_FILE"

# Check for high disk usage
if [ "$DISK_USAGE" -gt "$CRITICAL_THRESHOLD" ]; then
    echo "[$TIMESTAMP] CRITICAL: Disk usage at ${DISK_USAGE}%!" >> "$ALERT_FILE"
    echo "Disk Details:" >> "$ALERT_FILE"
    df -h >> "$ALERT_FILE"
    echo "Largest directories:" >> "$ALERT_FILE"
    du -sh /home/ec2-user/* 2>/dev/null | sort -hr | head -10 >> "$ALERT_FILE"
    echo "Largest files in /tmp:" >> "$ALERT_FILE"
    du -sh /tmp/* 2>/dev/null | sort -hr | head -10 >> "$ALERT_FILE"
    echo "---" >> "$ALERT_FILE"
elif [ "$DISK_USAGE" -gt "$DISK_THRESHOLD" ]; then
    echo "[$TIMESTAMP] WARNING: Disk usage at ${DISK_USAGE}%" >> "$ALERT_FILE"
    echo "Disk Details:" >> "$ALERT_FILE"
    df -h >> "$ALERT_FILE"
    echo "---" >> "$ALERT_FILE"
fi

# Keep logs manageable
tail -n 1000 "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE" 2>/dev/null
tail -n 500 "$ALERT_FILE" > "$ALERT_FILE.tmp" && mv "$ALERT_FILE.tmp" "$ALERT_FILE" 2>/dev/null

