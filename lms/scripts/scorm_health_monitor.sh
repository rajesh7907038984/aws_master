#!/bin/bash
# SCORM Health Monitor - Automated monitoring script
# Run this script weekly via cron to ensure SCORM system health

echo "🔍 SCORM Health Monitor - $(date)"
echo "=================================="

# Change to LMS directory
cd /home/ec2-user/lms

# Activate virtual environment
source venv/bin/activate

# Run health check with auto-fix
echo "Running SCORM health check..."
python manage.py monitor_scorm_health --auto-fix

# Check if any issues were found
if [ $? -eq 0 ]; then
    echo "✅ SCORM system is healthy"
else
    echo "⚠️  Some issues were found and fixed"
fi

# Optional: Re-analyze packages monthly (uncomment if needed)
# echo "Re-analyzing SCORM packages..."
# python manage.py analyze_scorm_packages --force

echo "🏁 SCORM Health Monitor completed - $(date)"
