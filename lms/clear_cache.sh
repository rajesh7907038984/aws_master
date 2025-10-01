#!/bin/bash

# LMS Cache Clearing Script
# This script clears various caches to ensure frontend changes are reflected

echo "🧹 Clearing LMS caches..."

# Clear Django cache
echo "📦 Clearing Django cache..."
cd /home/ec2-user/lms
source venv/bin/activate
python manage.py clear_cache 2>/dev/null || echo "Cache clearing command not available"

# Touch all static files to update timestamps
echo "📁 Updating static file timestamps..."
find /home/ec2-user/lms -name "*.js" -path "*/static/*" -exec touch {} \;
find /home/ec2-user/lms -name "*.css" -path "*/static/*" -exec touch {} \;
find /home/ec2-user/lms -name "*.html" -path "*/templates/*" -exec touch {} \;

# Collect static files
echo "📦 Collecting static files..."
python manage.py collectstatic --noinput

# Clear browser cache instructions
echo ""
echo "🌐 Browser Cache Clearing Instructions:"
echo "1. Open your browser's Developer Tools (F12)"
echo "2. Right-click the refresh button and select 'Empty Cache and Hard Reload'"
echo "3. Or use Ctrl+Shift+R (Windows/Linux) or Cmd+Shift+R (Mac)"
echo "4. Or clear browser cache in settings"
echo ""
echo "✅ Cache clearing completed!"
echo "🔄 Please refresh your browser with hard reload (Ctrl+Shift+R)"
