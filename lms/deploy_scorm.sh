#!/bin/bash
# SCORM Module Deployment Script
# This script deploys the SCORM functionality to the LMS

set -e  # Exit on error

echo "🚀 Starting SCORM Module Deployment..."
echo ""

# Navigate to project directory
cd /home/ec2-user/lms

# Activate virtual environment
echo "📦 Activating virtual environment..."
source venv/bin/activate

# Run migrations
echo "🗄️  Running database migrations..."
python manage.py migrate scorm

# Collect static files (if needed)
echo "📁 Collecting static files..."
python manage.py collectstatic --noinput || true

# Clear any Python cache
echo "🧹 Clearing Python cache..."
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true

# Restart the LMS service
echo "🔄 Restarting LMS service..."
if [ -f /etc/systemd/system/lms-production.service ]; then
    sudo systemctl restart lms-production
    echo "✅ LMS service restarted"
elif [ -f gunicorn.conf.py ]; then
    # Kill existing gunicorn processes
    pkill -f gunicorn || true
    sleep 2
    # Start new gunicorn in background
    gunicorn LMS_Project.wsgi:application --config gunicorn.conf.py --daemon
    echo "✅ Gunicorn restarted"
else
    echo "⚠️  Could not determine how to restart the service"
    echo "Please restart your server manually"
fi

echo ""
echo "✅ SCORM Module Deployment Complete!"
echo ""
echo "📋 Next Steps:"
echo "1. Navigate to: https://staging.nexsy.io/courses/11/topic/create/"
echo "2. Click on 'Assessments' tab"
echo "3. Select 'SCORM Package' option"
echo "4. Upload a SCORM ZIP file"
echo ""
echo "📚 Documentation:"
echo "- Full documentation: /home/ec2-user/lms/scorm/README.md"
echo "- Implementation summary: /home/ec2-user/lms/SCORM_IMPLEMENTATION_SUMMARY.md"
echo ""

