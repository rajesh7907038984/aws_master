# LMS Server-Independent Deployment Guide

## 🎯 Overview

This LMS project is now **fully server-independent**. You can deploy it on any server by simply:
1. Configuring the `.env` file with your server-specific settings
2. Running the setup script
3. Restarting the server

**No code changes required!** All server-specific configurations are externalized to environment variables.

---

## 📋 Quick Start

### 1. Initial Server Setup

```bash
# Clone/copy the project to your server
cd /path/to/your/lms

# Copy the environment template
cp env_template .env

# Edit .env with your server-specific configuration
nano .env

# Run the setup script
./setup_server.sh

# Install nginx configuration (requires sudo)
sudo cp nginx_generated.conf /etc/nginx/sites-available/lms
sudo ln -sf /etc/nginx/sites-available/lms /etc/nginx/sites-enabled/lms
sudo nginx -t
sudo systemctl restart nginx

# Start the server
./restart_server.sh
```

### 2. Subsequent Restarts

```bash
# Quick restart (no migrations, no static files collection)
./restart_server.sh quick

# Full restart (with migrations and static files)
./restart_server.sh full

# Or use the traditional server manager
./server_manager.sh restart
```

---

## ⚙️ Configuration Guide

### Server-Specific Variables (Customize These)

Edit your `.env` file and configure the following server-specific variables:

```bash
# ==============================================
# SERVER-SPECIFIC CONFIGURATION
# ==============================================

# Project root directory (where manage.py is located)
PROJECT_ROOT=/home/ec2-user/lms

# Static files directory
STATIC_ROOT=/home/ec2-user/lmsstaticfiles

# Logs directory
LOGS_DIR=/home/ec2-user/lmslogs

# Media files directory (if using local storage)
MEDIA_ROOT=/home/ec2-user/lms/media_local

# SCORM uploads directory
SCORM_ROOT_FOLDER=/home/ec2-user/scorm_uploads

# Server user and group
SERVER_USER=ec2-user
SERVER_GROUP=ec2-user

# Server domain configuration
PRIMARY_DOMAIN=lms.example.com
ALB_DOMAIN=lms-alb-xxxxxx.region.elb.amazonaws.com

# Gunicorn configuration
GUNICORN_BIND=0.0.0.0:8000
GUNICORN_WORKERS=auto
GUNICORN_TIMEOUT=30
```

### Application Variables (Usually Same Across Servers)

```bash
# ==============================================
# DJANGO CORE CONFIGURATION
# ==============================================
DJANGO_SETTINGS_MODULE=LMS_Project.settings.production
DJANGO_ENV=production
DJANGO_SECRET_KEY="your-secret-key-here"

# ==============================================
# DATABASE CONFIGURATION
# ==============================================
AWS_DB_PASSWORD=your-database-password
AWS_DB_NAME=postgres
AWS_DB_USER=lms_admin
AWS_DB_HOST=your-database-host.rds.amazonaws.com
AWS_DB_PORT=5432

# ==============================================
# AWS S3 CONFIGURATION
# ==============================================
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_STORAGE_BUCKET_NAME=your-bucket-name
AWS_S3_REGION_NAME=eu-west-2

# ... (see env_template for full list)
```

---

##  How It Works

### Environment Variable Loading

The project uses a centralized environment loader (`core/env_loader.py`) that:
1. Reads the `.env` file from the project root
2. Loads all variables into the environment
3. Provides helper functions for type conversion (bool, int, list)
4. Validates required variables

### Server-Independent Configuration

All server-specific paths and configurations are read from environment variables:

| Component | Configuration | Environment Variable |
|-----------|---------------|---------------------|
| Django Settings | Static files root | `STATIC_ROOT` |
| Django Settings | Media files root | `MEDIA_ROOT` |
| Django Settings | Logs directory | `LOGS_DIR` |
| Gunicorn | Bind address | `GUNICORN_BIND` |
| Gunicorn | Number of workers | `GUNICORN_WORKERS` |
| Gunicorn | Timeout | `GUNICORN_TIMEOUT` |
| Gunicorn | User/Group | `SERVER_USER`, `SERVER_GROUP` |
| Gunicorn | PID file | `$LOGS_DIR/gunicorn.pid` |
| Nginx | Static files path | `STATIC_ROOT` |
| Nginx | Media files path | `MEDIA_ROOT` |
| Nginx | Domain name | `PRIMARY_DOMAIN` |
| Systemd | Working directory | `PROJECT_ROOT` |

---

## 📁 Generated Files

The `setup_server.sh` script generates server-specific configuration files:

### 1. `nginx_generated.conf`
- Dynamically generated nginx configuration
- Uses paths and domains from `.env`
- Ready to copy to `/etc/nginx/sites-available/`

### 2. `lms-production-generated.service`
- Dynamically generated systemd service file
- Uses paths and user from `.env`
- Ready to copy to `/etc/systemd/system/`

---

##  Deployment Workflows

### Development → Staging → Production

Each environment can have its own `.env` file:

```bash
# Development server
PROJECT_ROOT=/home/dev/lms
STATIC_ROOT=/home/dev/lmsstaticfiles
PRIMARY_DOMAIN=lms-dev.example.com
DJANGO_ENV=development

# Staging server
PROJECT_ROOT=/home/staging/lms
STATIC_ROOT=/home/staging/lmsstaticfiles
PRIMARY_DOMAIN=lms-staging.example.com
DJANGO_ENV=staging

# Production server
PROJECT_ROOT=/home/ec2-user/lms
STATIC_ROOT=/home/ec2-user/lmsstaticfiles
PRIMARY_DOMAIN=lms.example.com
DJANGO_ENV=production
```

### Migration Between Servers

To migrate from one server to another:

1. **Export from old server:**
   ```bash
   # Backup database
   python manage.py dumpdata > backup.json
   
   # Copy .env for reference
   cp .env old-server.env
   ```

2. **Setup new server:**
   ```bash
   # Copy project files
   rsync -avz /old/server/lms/ /new/server/lms/
   
   # Create new .env with new server paths
   cp env_template .env
   nano .env  # Configure for new server
   
   # Run setup
   ./setup_server.sh
   
   # Import database (if needed)
   python manage.py loaddata backup.json
   
   # Start server
   ./restart_server.sh
   ```

---

##  Restart Methods

### 1. Quick Restart (Fastest)
```bash
./restart_server.sh quick
```
- Stops and starts the server
- No migrations, no static files collection
- Use when only code changes (no DB changes)

### 2. Full Restart (Recommended)
```bash
./restart_server.sh full
```
- Stops the server
- Runs Django checks
- Applies database migrations
- Collects static files
- Tests database connection
- Starts the server

### 3. Server Manager (Legacy)
```bash
./server_manager.sh restart
```
- Full restart with additional cleanup
- Compatible with old deployment scripts

---

## 📊 Server Status Monitoring

### Check Server Status
```bash
./server_manager.sh status
```

Shows:
- Nginx status
- LMS service status
- Port availability
- Server responsiveness

### View Logs
```bash
# Gunicorn error logs
tail -f $LOGS_DIR/gunicorn_error.log

# Gunicorn access logs
tail -f $LOGS_DIR/gunicorn_access.log

# Django logs
tail -f $LOGS_DIR/production.log
tail -f $LOGS_DIR/production_errors.log

# Nginx logs
sudo tail -f /var/log/nginx/lms_error.log
```

---

## 🔐 Security Considerations

### Environment File Security

The `.env` file contains sensitive information. Protect it:

```bash
# Set restrictive permissions
chmod 600 .env

# Exclude from git (already in .gitignore)
# Never commit .env to version control

# Use different credentials for each environment
# Don't share production credentials with development
```

### Secret Key Generation

Generate a secure secret key for each environment:

```python
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key())
```

---

## 🐛 Troubleshooting

### Server Won't Start

1. **Check environment variables:**
   ```bash
   ./setup_server.sh
   # Review output for missing variables
   ```

2. **Check logs:**
   ```bash
   tail -f $LOGS_DIR/gunicorn_error.log
   tail -f $LOGS_DIR/production_errors.log
   ```

3. **Verify port is free:**
   ```bash
   lsof -i :8000
   # Kill processes if needed
   ```

4. **Test Django configuration:**
   ```bash
   source venv/bin/activate
   python manage.py check --deploy
   ```

### Database Connection Issues

1. **Verify credentials in .env:**
   ```bash
   grep AWS_DB .env
   ```

2. **Test database connection:**
   ```bash
   python manage.py dbshell
   ```

3. **Check network connectivity:**
   ```bash
   telnet $AWS_DB_HOST 5432
   ```

### Static Files Not Loading

1. **Collect static files:**
   ```bash
   python manage.py collectstatic --noinput
   ```

2. **Verify STATIC_ROOT:**
   ```bash
   ls -la $STATIC_ROOT
   ```

3. **Check nginx configuration:**
   ```bash
   sudo nginx -t
   cat $PROJECT_ROOT/nginx_generated.conf
   ```

---

## 📚 Advanced Configuration

### Custom Worker Count

```bash
# Auto-calculate based on CPU cores (recommended)
GUNICORN_WORKERS=auto

# Or specify a number
GUNICORN_WORKERS=4
```

### Custom Bind Address

```bash
# Bind to all interfaces
GUNICORN_BIND=0.0.0.0:8000

# Bind to specific interface
GUNICORN_BIND=127.0.0.1:8000

# Custom port
GUNICORN_BIND=0.0.0.0:9000
```

### Multiple Domains

Add to `.env`:
```bash
PRIMARY_DOMAIN=lms.example.com
ADDITIONAL_DOMAINS=www.lms.example.com,lms-app.example.com
```

Then manually edit `nginx_generated.conf` to include additional domains in the `server_name` directive.

---

##  Verification Checklist

After setup, verify:

- [ ] `.env` file is configured with correct paths
- [ ] All required directories exist and have correct permissions
- [ ] Virtual environment is activated
- [ ] Database migrations are applied
- [ ] Static files are collected
- [ ] Database connection works
- [ ] Nginx configuration is valid
- [ ] Server starts successfully
- [ ] Server responds to HTTP requests
- [ ] Domain resolves correctly (if using a domain)
- [ ] Logs are being written to `$LOGS_DIR`

---

## 🆘 Support

If you encounter issues:

1. Review this guide carefully
2. Check the logs in `$LOGS_DIR`
3. Verify all environment variables in `.env`
4. Run `./setup_server.sh` to validate configuration
5. Test with `./restart_server.sh full` to ensure all checks pass

---

**Remember:** All server-specific configuration is in `.env`. Change the file, restart the server. That's it! 

