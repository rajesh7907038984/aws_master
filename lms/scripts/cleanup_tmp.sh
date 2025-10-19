#!/bin/bash
# LMS Temporary Files Cleanup Script
# Cleans up old upload files and Django temporary files
# Run daily via cron

LOG_FILE="/home/ec2-user/lmslogs/cleanup.log"
RETENTION_DAYS=1  # Keep files for 1 day

echo "======================================" >> "$LOG_FILE"
echo "Cleanup started: $(date)" >> "$LOG_FILE"

# Check disk space before cleanup
echo "Disk space before cleanup:" >> "$LOG_FILE"
df -h /tmp >> "$LOG_FILE"

# Clean up Django upload temporary files (older than RETENTION_DAYS)
echo "Cleaning Django upload files..." >> "$LOG_FILE"
DELETED_COUNT=$(find /tmp -type f \( -name "*.upload.*" -o -name "tmp*.zip" -o -name "tmp*_upload_*" \) -mtime +${RETENTION_DAYS} 2>/dev/null | wc -l)
find /tmp -type f \( -name "*.upload.*" -o -name "tmp*.zip" -o -name "tmp*_upload_*" \) -mtime +${RETENTION_DAYS} -delete 2>/dev/null
echo "Deleted $DELETED_COUNT upload files" >> "$LOG_FILE"

# Clean up old Django session files
echo "Cleaning Django session files..." >> "$LOG_FILE"
SESSION_COUNT=$(find /tmp -type f -name "django_*" -mtime +${RETENTION_DAYS} 2>/dev/null | wc -l)
find /tmp -type f -name "django_*" -mtime +${RETENTION_DAYS} -delete 2>/dev/null
echo "Deleted $SESSION_COUNT session files" >> "$LOG_FILE"

# Clean up empty directories in /tmp
find /tmp -type d -empty -delete 2>/dev/null

# Check disk space after cleanup
echo "Disk space after cleanup:" >> "$LOG_FILE"
df -h /tmp >> "$LOG_FILE"

echo "Cleanup completed: $(date)" >> "$LOG_FILE"
echo "======================================" >> "$LOG_FILE"

# Keep only last 1000 lines of log file
tail -n 1000 "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"

