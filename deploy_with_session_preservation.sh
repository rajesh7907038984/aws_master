#!/bin/bash

# ==============================================
# LMS DEPLOYMENT WITH SESSION PRESERVATION
# ==============================================
# This script handles deployment while preserving user sessions
# to prevent auto-logout after deployment
# ==============================================

set -e  # Exit on error

echo "🚀 LMS Deployment with Session Preservation"
echo "=========================================="
echo "📅 $(date)"
echo ""

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load environment variables
if [ -f ".env" ]; then
    echo "📋 Loading environment variables from .env..."
    export $(cat .env | grep -v '^#' | xargs)
    echo " Environment variables loaded"
else
    echo " No .env file found!"
    echo "   Please run ./setup_server.sh first"
    exit 1
fi

# Activate virtual environment
echo "🐍 Activating virtual environment..."
source venv/bin/activate

# Pre-deployment session preservation
echo "🛡️  Pre-deployment session preservation..."
python manage.py preserve_sessions

if [ $? -ne 0 ]; then
    echo " Session preservation failed"
    exit 1
fi

echo " Session preservation completed successfully"
echo ""

# Run deployment using existing restart script
echo "🔄 Running deployment..."
./restart_server.sh full

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Deployment completed successfully!"
    echo "   - User sessions preserved"
    echo "   - Server restarted"
    echo "   - No auto-logout issues expected"
    echo ""
    echo "📊 Session Status:"
    python manage.py preserve_sessions --check-only
else
    echo ""
    echo "❌ Deployment failed!"
    echo "   Check logs for details"
    exit 1
fi
