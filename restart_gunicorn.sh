#!/bin/bash
# Script to gracefully restart Gunicorn workers

echo "Restarting Gunicorn workers..."

# Find all gunicorn processes
PIDS=$(ps aux | grep '[p]ython3 -m gunicorn' | awk '{print $2}')

if [ -z "$PIDS" ]; then
    echo "No Gunicorn processes found"
    exit 1
fi

# Send HUP signal to gracefully restart workers
for PID in $PIDS; do
    echo "Sending HUP signal to PID $PID"
    kill -HUP $PID 2>/dev/null || true
done

echo "Waiting for workers to restart..."
sleep 3

# Check if gunicorn is still running
NEW_PIDS=$(ps aux | grep '[p]ython3 -m gunicorn' | awk '{print $2}')
if [ -z "$NEW_PIDS" ]; then
    echo "ERROR: Gunicorn stopped. Please start it manually."
    exit 1
else
    echo "✓ Gunicorn workers restarted successfully"
    echo "✓ New code changes are now active"
    ps aux | grep '[p]ython3 -m gunicorn' | wc -l | xargs echo "  Active workers:"
fi

