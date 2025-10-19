#!/bin/bash
# LMS Upload Activity Monitoring Script
# Tracks active uploads and system resources during upload operations
# Run every minute during business hours

LOG_FILE="/home/ec2-user/lmslogs/upload_monitor.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Count active upload processes
UPLOAD_COUNT=$(ps aux | grep -i "upload" | grep -v grep | wc -l)
GUNICORN_COUNT=$(ps aux | grep gunicorn | grep -v grep | wc -l)

# Get memory and disk stats
MEMORY_USED=$(free | grep Mem | awk '{print $3}')
MEMORY_TOTAL=$(free | grep Mem | awk '{print $2}')
MEMORY_PERCENT=$((MEMORY_USED * 100 / MEMORY_TOTAL))
DISK_USAGE=$(df / | grep / | awk '{print $5}' | sed 's/%//')

# Check for large files being written to /tmp
LARGE_FILES=$(find /tmp -type f -size +100M 2>/dev/null | wc -l)

# Log activity if uploads are detected or memory/disk is high
if [ "$UPLOAD_COUNT" -gt 0 ] || [ "$LARGE_FILES" -gt 0 ] || [ "$MEMORY_PERCENT" -gt 70 ] || [ "$DISK_USAGE" -gt 80 ]; then
    echo "$TIMESTAMP | Uploads: $UPLOAD_COUNT | Gunicorn: $GUNICORN_COUNT | Large Files: $LARGE_FILES | Mem: ${MEMORY_PERCENT}% | Disk: ${DISK_USAGE}%" >> "$LOG_FILE"
    
    # Log large files in /tmp if any
    if [ "$LARGE_FILES" -gt 0 ]; then
        echo "  Large files in /tmp:" >> "$LOG_FILE"
        find /tmp -type f -size +100M -exec ls -lh {} \; 2>/dev/null | awk '{print "    " $9 " - " $5}' >> "$LOG_FILE"
    fi
fi

# Keep log manageable
tail -n 2000 "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE" 2>/dev/null

