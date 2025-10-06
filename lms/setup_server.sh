#!/bin/bash

# ==============================================
# LMS SERVER SETUP SCRIPT
# ==============================================
# This script sets up the LMS server using .env configuration
# Usage: ./setup_server.sh
# ==============================================

set -e  # Exit on error

echo " LMS Server Setup Script"
echo "=================================="
echo "📅 $(date)"
echo ""

# ==============================================
# LOAD ENVIRONMENT VARIABLES
# ==============================================

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env file
if [ -f ".env" ]; then
    echo "📋 Loading environment variables from .env..."
    export $(cat .env | grep -v '^#' | xargs)
    echo " Environment variables loaded"
else
    echo " No .env file found!"
    echo "   Please copy env_template to .env and configure it for your server:"
    echo "   cp env_template .env"
    echo "   nano .env"
    exit 1
fi

# ==============================================
# VALIDATE REQUIRED ENVIRONMENT VARIABLES
# ==============================================

echo "🔍 Validating environment variables..."

required_vars=(
    "PROJECT_ROOT"
    "STATIC_ROOT"
    "LOGS_DIR"
    "SERVER_USER"
    "SERVER_GROUP"
    "PRIMARY_DOMAIN"
    "DJANGO_SECRET_KEY"
    "AWS_DB_PASSWORD"
    "AWS_DB_HOST"
)

missing_vars=()
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        missing_vars+=("$var")
    fi
done

if [ ${#missing_vars[@]} -gt 0 ]; then
    echo " Missing required environment variables:"
    for var in "${missing_vars[@]}"; do
        echo "   - $var"
    done
    echo ""
    echo "Please set these variables in your .env file"
    exit 1
fi

echo " All required environment variables are set"

# ==============================================
# CREATE REQUIRED DIRECTORIES
# ==============================================

echo "📁 Creating required directories..."

# Create logs directory
if [ ! -d "$LOGS_DIR" ]; then
    echo "   Creating logs directory: $LOGS_DIR"
    mkdir -p "$LOGS_DIR"
fi

# Create static files directory
if [ ! -d "$STATIC_ROOT" ]; then
    echo "   Creating static files directory: $STATIC_ROOT"
    mkdir -p "$STATIC_ROOT"
fi

# Create media directory (if using local storage)
if [ ! -z "$MEDIA_ROOT" ] && [ ! -d "$MEDIA_ROOT" ]; then
    echo "   Creating media directory: $MEDIA_ROOT"
    mkdir -p "$MEDIA_ROOT"
fi

# Create SCORM uploads directory
if [ ! -z "$SCORM_ROOT_FOLDER" ] && [ ! -d "$SCORM_ROOT_FOLDER" ]; then
    echo "   Creating SCORM uploads directory: $SCORM_ROOT_FOLDER"
    mkdir -p "$SCORM_ROOT_FOLDER"
fi

# Set permissions
chmod 755 "$LOGS_DIR"
chmod 755 "$STATIC_ROOT"
[ ! -z "$MEDIA_ROOT" ] && [ -d "$MEDIA_ROOT" ] && chmod 755 "$MEDIA_ROOT"
[ ! -z "$SCORM_ROOT_FOLDER" ] && [ -d "$SCORM_ROOT_FOLDER" ] && chmod 755 "$SCORM_ROOT_FOLDER"

echo " Directories created successfully"

# ==============================================
# ACTIVATE VIRTUAL ENVIRONMENT
# ==============================================

echo "🐍 Activating virtual environment..."
if [ ! -d "$PROJECT_ROOT/venv" ]; then
    echo " Virtual environment not found at $PROJECT_ROOT/venv"
    echo "   Please create a virtual environment first:"
    echo "   python3 -m venv venv"
    exit 1
fi

source "$PROJECT_ROOT/venv/bin/activate"
echo " Virtual environment activated"

# ==============================================
# INSTALL/UPDATE DEPENDENCIES
# ==============================================

echo "📦 Checking Python dependencies..."
# Note: For Python 3.7 compatibility, dependencies are managed separately
# Use requirements-py37-installed.txt for this server's specific versions
echo " Using pre-installed dependencies (Python 3.7 compatible versions)"

# ==============================================
# CHECK DJANGO CONFIGURATION
# ==============================================

echo "🔍 Checking Django configuration..."
python manage.py check --deploy

if [ $? -ne 0 ]; then
    echo " Django configuration check failed"
    exit 1
fi

echo " Django configuration is valid"

# ==============================================
# RUN DATABASE MIGRATIONS
# ==============================================

echo "🗄️  Running database migrations..."
python manage.py migrate --noinput

if [ $? -ne 0 ]; then
    echo " Database migrations failed"
    exit 1
fi

echo " Database migrations completed"

# ==============================================
# COLLECT STATIC FILES
# ==============================================

echo "📁 Collecting static files..."
python manage.py collectstatic --noinput

if [ $? -ne 0 ]; then
    echo " Static files collection failed"
    exit 1
fi

echo " Static files collected"

# ==============================================
# TEST DATABASE CONNECTION
# ==============================================

echo "🔗 Testing database connection..."
python manage.py shell -c "
from django.db import connection
try:
    connection.ensure_connection()
    print(' Database connection successful')
except Exception as e:
    print(f' Database connection failed: {e}')
    exit(1)
"

if [ $? -ne 0 ]; then
    echo " Database connection test failed"
    exit 1
fi

# ==============================================
# GENERATE NGINX CONFIGURATION
# ==============================================

echo " Generating nginx configuration..."
python - <<EOF
import os

# Read environment variables
project_root = os.environ.get('PROJECT_ROOT', '/home/ec2-user/lms')
static_root = os.environ.get('STATIC_ROOT', '/home/ec2-user/lmsstaticfiles')
media_root = os.environ.get('MEDIA_ROOT', f'{project_root}/media')
primary_domain = os.environ.get('PRIMARY_DOMAIN', 'lms.nexsy.io')
alb_domain = os.environ.get('ALB_DOMAIN', '')
gunicorn_bind = os.environ.get('GUNICORN_BIND', '127.0.0.1:8000')

# Extract host and port from gunicorn bind
if ':' in gunicorn_bind:
    gunicorn_host, gunicorn_port = gunicorn_bind.split(':')
    if gunicorn_host == '0.0.0.0':
        gunicorn_host = '127.0.0.1'
else:
    gunicorn_host = '127.0.0.1'
    gunicorn_port = '8000'

# Generate nginx configuration
nginx_config = f"""# Nginx Configuration for LMS Production
# Auto-generated from .env configuration

server {{
    listen 80;
    server_name {primary_domain};
    
    # Redirect HTTP to HTTPS
    return 301 https://\$server_name\$request_uri;
}}

server {{
    listen 443 ssl http2;
    server_name {primary_domain};
    
    # SSL Configuration (managed by AWS ALB)
    # SSL certificates are handled by AWS Application Load Balancer
    
    # Security headers
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    
    # Client max body size for file uploads
    client_max_body_size 100M;
    
    # Proxy settings
    proxy_connect_timeout 60s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;
    
    # Static files (served by nginx for better performance)
    location /static/ {{
        alias {static_root}/;
        expires 1y;
        add_header Cache-Control "public, immutable";
        
        # Gzip compression
        gzip on;
        gzip_vary on;
        gzip_min_length 1024;
        gzip_types
            text/plain
            text/css
            text/xml
            text/javascript
            application/javascript
            application/xml+rss
            application/json;
    }}
    
    # Media files (served by nginx for better performance)
    location /media/ {{
        alias {media_root}/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }}
    
    # Health check endpoint
    location /health/ {{
        access_log off;
        return 200 "healthy\\n";
        add_header Content-Type text/plain;
    }}
    
    # Main application (proxy to Gunicorn)
    location / {{
        proxy_pass http://{gunicorn_host}:{gunicorn_port};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Port \$server_port;
        
        # WebSocket support (if needed)
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }}
    
    # Logging
    access_log /var/log/nginx/lms_access.log;
    error_log /var/log/nginx/lms_error.log;
}}
"""

# Add ALB health check server block if ALB domain is configured
if alb_domain:
    nginx_config += f"""
# Additional server block for ALB health checks
server {{
    listen 80;
    server_name {alb_domain};
    
    # Health check for ALB
    location /health/ {{
        access_log off;
        return 200 "healthy\\n";
        add_header Content-Type text/plain;
    }}
    
    # Proxy to Gunicorn for ALB health checks
    location / {{
        proxy_pass http://{gunicorn_host}:{gunicorn_port};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }}
}}
"""

# Write the configuration file
with open(f'{project_root}/nginx_generated.conf', 'w') as f:
    f.write(nginx_config)

print(f" Nginx configuration generated: {project_root}/nginx_generated.conf")
EOF

echo " Nginx configuration generated"

# ==============================================
# GENERATE SYSTEMD SERVICE FILE
# ==============================================

echo " Generating systemd service file..."
cat > "$PROJECT_ROOT/lms-production-generated.service" <<EOF
[Unit]
Description=LMS Production Django Application
After=network.target
Wants=network.target

[Service]
Type=simple
User=$SERVER_USER
Group=$SERVER_GROUP
WorkingDirectory=$PROJECT_ROOT
EnvironmentFile=$PROJECT_ROOT/.env
ExecStartPre=$PROJECT_ROOT/venv/bin/python $PROJECT_ROOT/manage.py collectstatic --noinput --clear
ExecStart=$PROJECT_ROOT/venv/bin/gunicorn --config $PROJECT_ROOT/gunicorn.conf.py LMS_Project.wsgi:application
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=10
StartLimitInterval=60
StartLimitBurst=3

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ReadWritePaths=$PROJECT_ROOT
ReadWritePaths=$LOGS_DIR

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=lms-production

[Install]
WantedBy=multi-user.target
EOF

echo " Systemd service file generated: $PROJECT_ROOT/lms-production-generated.service"

# ==============================================
# SETUP SUMMARY
# ==============================================

echo ""
echo " Server Setup Completed Successfully!"
echo "======================================"
echo ""
echo "📋 Configuration Summary:"
echo "   - Project Root: $PROJECT_ROOT"
echo "   - Static Files: $STATIC_ROOT"
echo "   - Logs Directory: $LOGS_DIR"
echo "   - Media Directory: $MEDIA_ROOT"
echo "   - Primary Domain: $PRIMARY_DOMAIN"
echo "   - Gunicorn Bind: ${GUNICORN_BIND}"
echo ""
echo "📁 Generated Files:"
echo "   - $PROJECT_ROOT/nginx_generated.conf"
echo "   - $PROJECT_ROOT/lms-production-generated.service"
echo ""
echo " Next Steps:"
echo ""
echo "1. Install and configure nginx (if not done already):"
echo "   sudo cp $PROJECT_ROOT/nginx_generated.conf /etc/nginx/sites-available/lms"
echo "   sudo ln -sf /etc/nginx/sites-available/lms /etc/nginx/sites-enabled/lms"
echo "   sudo nginx -t"
echo "   sudo systemctl restart nginx"
echo ""
echo "2. Install systemd service (optional - for auto-start on boot):"
echo "   sudo cp $PROJECT_ROOT/lms-production-generated.service /etc/systemd/system/lms-production.service"
echo "   sudo systemctl daemon-reload"
echo "   sudo systemctl enable lms-production"
echo ""
echo "3. Start the LMS server:"
echo "   ./restart_server.sh"
echo ""
echo " Your server is ready to use!"

