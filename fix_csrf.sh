#!/bin/bash
# Quick CSRF Fix Script
# This script adds common domain variants to CSRF_TRUSTED_ORIGINS

echo "================================"
echo "CSRF Error Quick Fix Script"
echo "================================"
echo ""

# Get the primary domain from .env
PRIMARY_DOMAIN=$(grep "^PRIMARY_DOMAIN=" /home/ec2-user/lms/.env | cut -d'=' -f2)

if [ -z "$PRIMARY_DOMAIN" ]; then
    echo "❌ ERROR: PRIMARY_DOMAIN not found in .env file"
    echo "Please set PRIMARY_DOMAIN in your .env file first"
    exit 1
fi

echo "✅ Found PRIMARY_DOMAIN: $PRIMARY_DOMAIN"
echo ""

# Check if ADDITIONAL_CSRF_ORIGINS already exists
if grep -q "^ADDITIONAL_CSRF_ORIGINS=" /home/ec2-user/lms/.env; then
    echo "ℹ️  ADDITIONAL_CSRF_ORIGINS already exists in .env"
    echo "Current value:"
    grep "^ADDITIONAL_CSRF_ORIGINS=" /home/ec2-user/lms/.env
    echo ""
    read -p "Do you want to update it? (y/n): " update_choice
    if [ "$update_choice" != "y" ]; then
        echo "Skipping update..."
        exit 0
    fi
    # Remove the old line
    sed -i '/^ADDITIONAL_CSRF_ORIGINS=/d' /home/ec2-user/lms/.env
fi

# Create common domain variants
DOMAIN_VARIANTS="https://${PRIMARY_DOMAIN},http://${PRIMARY_DOMAIN}"

# Check if domain doesn't start with www, add www variant
if [[ ! "$PRIMARY_DOMAIN" =~ ^www\. ]]; then
    DOMAIN_VARIANTS="${DOMAIN_VARIANTS},https://www.${PRIMARY_DOMAIN},http://www.${PRIMARY_DOMAIN}"
fi

# Add to .env file
echo "ADDITIONAL_CSRF_ORIGINS=${DOMAIN_VARIANTS}" >> /home/ec2-user/lms/.env

echo "✅ Added ADDITIONAL_CSRF_ORIGINS to .env:"
echo "   ${DOMAIN_VARIANTS}"
echo ""

# Ask if user wants to restart the service
echo "================================"
echo "Next Steps:"
echo "================================"
echo ""
echo "To apply changes, you need to restart your Django application."
echo ""
echo "Options:"
echo "1. If using systemd service: sudo systemctl restart lms-production"
echo "2. If using gunicorn: sudo systemctl restart gunicorn"
echo "3. If running manually: pkill -f gunicorn && cd /home/ec2-user/lms && gunicorn LMS_Project.wsgi:application --bind 0.0.0.0:8000"
echo ""
read -p "Do you want to restart lms-production service now? (y/n): " restart_choice

if [ "$restart_choice" = "y" ]; then
    echo ""
    echo "Restarting lms-production service..."
    if sudo systemctl restart lms-production 2>/dev/null; then
        echo "✅ Service restarted successfully!"
    else
        echo "⚠️  Could not restart service automatically."
        echo "Please restart manually using one of the commands above."
    fi
else
    echo ""
    echo "⚠️  Remember to restart your Django application manually!"
fi

echo ""
echo "================================"
echo "Additional Troubleshooting:"
echo "================================"
echo "1. Clear your browser cookies for $PRIMARY_DOMAIN"
echo "2. Try accessing in an incognito/private window"
echo "3. Check the full guide: /home/ec2-user/lms/FIX_CSRF_ERROR.md"
echo ""
echo "If the issue persists, enable DEBUG mode temporarily:"
echo "Edit: /home/ec2-user/lms/LMS_Project/settings/production.py"
echo "Set: DEBUG = True (line 375)"
echo "Then restart and check the detailed error page"
echo "IMPORTANT: Set DEBUG back to False after debugging!"
echo ""

