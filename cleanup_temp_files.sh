#!/bin/bash
# SCORM Temporary File Cleanup Script
# Runs every hour to clean up old temporary files

TEMP_DIR="/tmp"
MAX_AGE=3600  # 1 hour in seconds

echo "Starting SCORM temp file cleanup at $(date)"

# Find and remove old temporary files
find "$TEMP_DIR" -name "tmp*" -type f -mtime +0 -delete 2>/dev/null
find "$TEMP_DIR" -name "*.tmp" -type f -mtime +0 -delete 2>/dev/null

# Count remaining temp files
REMAINING=$(find "$TEMP_DIR" -name "tmp*" -type f | wc -l)
echo "Cleanup completed. Remaining temp files: $REMAINING"
