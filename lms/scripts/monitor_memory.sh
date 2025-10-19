#!/bin/bash
# LMS Memory Monitoring Script
# Monitors memory usage and logs warnings during high usage
# Run every 5 minutes via cron during peak hours

LOG_FILE="/home/ec2-user/lmslogs/memory_monitor.log"
ALERT_FILE="/home/ec2-user/lmslogs/memory_alerts.log"
MEMORY_THRESHOLD=80  # Alert when memory usage exceeds 80%
SWAP_THRESHOLD=50    # Alert when swap usage exceeds 50%

# Get current memory stats
MEMORY_TOTAL=$(free | grep Mem | awk '{print $2}')
MEMORY_USED=$(free | grep Mem | awk '{print $3}')
MEMORY_PERCENT=$((MEMORY_USED * 100 / MEMORY_TOTAL))

SWAP_TOTAL=$(free | grep Swap | awk '{print $2}')
SWAP_USED=$(free | grep Swap | awk '{print $3}')
if [ "$SWAP_TOTAL" -gt 0 ]; then
    SWAP_PERCENT=$((SWAP_USED * 100 / SWAP_TOTAL))
else
    SWAP_PERCENT=0
fi

# Log current stats
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
echo "$TIMESTAMP | Memory: ${MEMORY_PERCENT}% | Swap: ${SWAP_PERCENT}%" >> "$LOG_FILE"

# Check for high memory usage
if [ "$MEMORY_PERCENT" -gt "$MEMORY_THRESHOLD" ]; then
    echo "[$TIMESTAMP] WARNING: High memory usage: ${MEMORY_PERCENT}%" >> "$ALERT_FILE"
    echo "Memory Details:" >> "$ALERT_FILE"
    free -h >> "$ALERT_FILE"
    echo "Top Memory Consumers:" >> "$ALERT_FILE"
    ps aux --sort=-%mem | head -10 >> "$ALERT_FILE"
    echo "---" >> "$ALERT_FILE"
fi

# Check for high swap usage
if [ "$SWAP_PERCENT" -gt "$SWAP_THRESHOLD" ]; then
    echo "[$TIMESTAMP] WARNING: High swap usage: ${SWAP_PERCENT}%" >> "$ALERT_FILE"
    echo "---" >> "$ALERT_FILE"
fi

# Keep logs manageable (last 5000 lines)
tail -n 5000 "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE" 2>/dev/null
tail -n 1000 "$ALERT_FILE" > "$ALERT_FILE.tmp" && mv "$ALERT_FILE.tmp" "$ALERT_FILE" 2>/dev/null

